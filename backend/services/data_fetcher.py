import yfinance as yf
import feedparser
import requests
import logging
from services.network_utils import fetch_with_curl
import csv
import os
import re
import random
import math
import json
import time
import threading
import io
from apscheduler.schedulers.background import BackgroundScheduler
import concurrent.futures
from sgp4.api import Satrec, WGS72
from sgp4.api import jday
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()
from services.cctv_pipeline import init_db, TFLJamCamIngestor, LTASingaporeIngestor, AustinTXIngestor, NYCDOTIngestor, TDOTSmartWayIngestor, ClarksvilleCityIngestor, KYTCFortCampbellIngestor, ClarksvilleAreaWebcamIngestor, NC5SkynetIngestor, WSMVWeatherCamIngestor, NPSSmokiesIngestor, ResortCamsTNIngestor, GatlinburgTouristIngestor, CaltransIngestor, FL511Ingestor, VDOTIngestor, LA511Ingestor, LAWetmetIngestor, KSLAStaticIngestor, get_all_cameras

logger = logging.getLogger(__name__)

def _gmst(jd_ut1):
    """Greenwich Mean Sidereal Time in radians from Julian Date."""
    t = (jd_ut1 - 2451545.0) / 36525.0
    gmst_sec = 67310.54841 + (876600.0 * 3600 + 8640184.812866) * t + 0.093104 * t * t - 6.2e-6 * t * t * t
    gmst_rad = (gmst_sec % 86400) / 86400.0 * 2 * math.pi
    return gmst_rad

# Pre-compiled regex patterns for airline code extraction (used in hot loop)
_RE_AIRLINE_CODE_1 = re.compile(r'^([A-Z]{3})\d')
_RE_AIRLINE_CODE_2 = re.compile(r'^([A-Z]{3})[A-Z\d]')


# ---------------------------------------------------------------------------
# OpenSky Network API Client (OAuth2)
# ---------------------------------------------------------------------------
class OpenSkyClient:
    def __init__(self, client_id, client_secret):
        self.client_id = client_id
        self.client_secret = client_secret
        self.token = None
        self.expires_at = 0

    def get_token(self):
        import time
        if self.token and time.time() < self.expires_at - 60:
            return self.token
        
        url = "https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token"
        data = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret
        }
        try:
            r = requests.post(url, data=data, timeout=10)
            if r.status_code == 200:
                res = r.json()
                self.token = res.get("access_token")
                self.expires_at = time.time() + res.get("expires_in", 1800)
                logger.info("OpenSky OAuth2 token refreshed.")
                return self.token
            else:
                logger.error(f"OpenSky Auth Failed: {r.status_code} {r.text}")
        except Exception as e:
            logger.error(f"OpenSky Auth Exception: {e}")
        return None

# User provided credentials
opensky_client = OpenSkyClient(
    client_id=os.environ.get("OPENSKY_CLIENT_ID", ""),
    client_secret=os.environ.get("OPENSKY_CLIENT_SECRET", "")
)

# Throttling and caching for OpenSky to observe the 400 req/day limit
last_opensky_fetch = 0
cached_opensky_flights = []



# In-memory store
latest_data = {
    "last_updated": None,
    "news": [],
    "stocks": {},
    "oil": {},
    "flights": [],
    "ships": [],
    "military_flights": [],
    "tracked_flights": [],
    "cctv": [],
    "weather": None,
    # bikeshare removed per user request
    "traffic": [],
    "earthquakes": [],
    "uavs": [],
    "frontlines": None,
    "gdelt": [],
    "liveuamap": [],
    "kismet_devices": [],
    "snort_alerts": [],
    "nmap_hosts": [],
    "nuclei_vulns": [],
}

# Thread lock for safe reads/writes to latest_data
_data_lock = threading.Lock()

# ---------------------------------------------------------------------------
# Plane-Alert DB — load tracked aircraft from CSV on startup
# ---------------------------------------------------------------------------

# Category → color mapping
_PINK_CATEGORIES = {
    "Dictator Alert", "Head of State", "Da Comrade", "Oligarch",
    "Governments", "Royal Aircraft", "Quango",
}
_RED_CATEGORIES = {
    "Don't you know who I am?", "As Seen on TV", "Joe Cool",
    "Vanity Plate", "Football", "Bizjets",
}
_DARKBLUE_CATEGORIES = {
    "USAF", "United States Navy", "United States Marine Corps",
    "Special Forces", "Hired Gun", "Oxcart", "Gunship", "Nuclear",
    "CAP", "Zoomies",
}

def _category_to_color(cat: str) -> str:
    if cat in _PINK_CATEGORIES:
        return "pink"
    if cat in _RED_CATEGORIES:
        return "red"
    if cat in _DARKBLUE_CATEGORIES:
        return "darkblue"
    return "white"

# Load once on module import
_PLANE_ALERT_DB: dict = {}  # uppercase ICAO hex → dict of aircraft info

def _load_plane_alert_db():
    """Parse plane_alert_db.json into a dict keyed by uppercase ICAO hex."""
    global _PLANE_ALERT_DB
    import json
    json_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "data", "plane_alert_db.json"
    )
    if not os.path.exists(json_path):
        logger.warning(f"Plane-Alert JSON DB not found at {json_path}")
        return
    try:
        with open(json_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
            for icao_hex, info in data.items():
                info["color"] = _category_to_color(info.get("category", ""))
                _PLANE_ALERT_DB[icao_hex] = info
        logger.info(f"Plane-Alert JSON DB loaded: {len(_PLANE_ALERT_DB)} aircraft")
    except Exception as e:
        logger.error(f"Failed to load Plane-Alert JSON DB: {e}")

_load_plane_alert_db()

def enrich_with_plane_alert(flight: dict) -> dict:
    """If flight's icao24 is in the Plane-Alert DB, add alert metadata."""
    icao = flight.get("icao24", "").strip().upper()
    if icao and icao in _PLANE_ALERT_DB:
        info = _PLANE_ALERT_DB[icao]
        flight["alert_category"] = info["category"]
        flight["alert_color"] = info["color"]
        flight["alert_operator"] = info["operator"]
        flight["alert_type"] = info["ac_type"]
        flight["alert_tag1"] = info["tag1"]
        flight["alert_tag2"] = info["tag2"]
        flight["alert_tag3"] = info["tag3"]
        flight["alert_link"] = info["link"]
        # Override registration if DB has a better one
        if info["registration"]:
            flight["registration"] = info["registration"]

    return flight

# (json imported at module top)
_TRACKED_NAMES_DB: dict = {} # Map from uppercase registration to {name, category}

def _load_tracked_names():
    global _TRACKED_NAMES_DB
    json_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "data", "tracked_names.json"
    )
    if not os.path.exists(json_path):
        return
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            # data has:
            # "names": [ {"name": "...", "category": "..."} ]
            # "details": { "Name": { "category": "...", "registrations": ["..."] } }
            for name, info in data.get("details", {}).items():
                cat = info.get("category", "Other")
                for reg in info.get("registrations", []):
                    reg_clean = reg.strip().upper()
                    if reg_clean:
                        _TRACKED_NAMES_DB[reg_clean] = {"name": name, "category": cat}
        logger.info(f"Tracked Names DB loaded: {len(_TRACKED_NAMES_DB)} registrations")
    except Exception as e:
        logger.error(f"Failed to load Tracked Names DB: {e}")

_load_tracked_names()

def enrich_with_tracked_names(flight: dict) -> dict:
    """If flight's registration matches our Excel extraction, tag it as tracked."""
    reg = flight.get("registration", "").strip().upper()
    callsign = flight.get("callsign", "").strip().upper()
    
    match = None
    if reg and reg in _TRACKED_NAMES_DB:
        match = _TRACKED_NAMES_DB[reg]
    elif callsign and callsign in _TRACKED_NAMES_DB:
        match = _TRACKED_NAMES_DB[callsign]
        
    if match:
        # Don't overwrite Plane-Alert DB operator if it exists unless we want Excel to take precedence.
        # Let's let Excel take precedence as it has cleaner individual names (e.g. Elon Musk instead of FALCON LANDING LLC).
        flight["alert_operator"] = match["name"]
        flight["alert_category"] = match["category"]
        if "alert_color" not in flight:
            flight["alert_color"] = "pink"

    return flight


def generate_machine_assessment(title, description, risk_score):
    if risk_score < 8:
        return None
        
    import random
    keywords = [word.lower() for word in title.split() + description.split()]
    
    assessment = "ANALYSIS: "
    if any(k in keywords for k in ["strike", "missile", "attack", "bomb", "drone"]):
        assessment += f"{random.randint(75, 95)}% probability of kinetic escalation within 24 hours. Recommend immediate asset relocation from projected blast radius."
    elif any(k in keywords for k in ["sanction", "trade", "economy", "tariff", "boycott"]):
        assessment += f"Significant economic severing detected. {random.randint(60, 85)}% chance of reciprocal sanctions. Global supply chains may experience cascading latency."
    elif any(k in keywords for k in ["cyber", "hack", "breach", "ddos", "ransomware"]):
        assessment += f"Asymmetric digital warfare signature matched. {random.randint(80, 99)}% probability of infrastructure probing. Initiate air-gapping protocol for critical nodes."
    elif any(k in keywords for k in ["troop", "deploy", "border", "navy", "carrier"]):
        assessment += f"Force projection detected. {random.randint(70, 90)}% probability of theater escalation. Monitor adjacent maritime and airspace for mobilization."
    else:
        assessment += f"Anomalous geopolitical shift detected. Confidence interval {random.randint(60, 90)}%. Awaiting further signals intelligence for definitive vector."
        
    return assessment

# ---------------------------------------------------------------------------
# Keyword → coordinate mapping for geocoding news articles
# ---------------------------------------------------------------------------
_KEYWORD_COORDS = {
    "venezuela": (7.119, -66.589),
    "brazil": (-14.235, -51.925),
    "argentina": (-38.416, -63.616),
    "colombia": (4.570, -74.297),
    "mexico": (23.634, -102.552),
    "united states": (38.907, -77.036),
    " usa ": (38.907, -77.036),
    " us ": (38.907, -77.036),
    "washington": (38.907, -77.036),
    "canada": (56.130, -106.346),
    "ukraine": (49.487, 31.272),
    "kyiv": (50.450, 30.523),
    "russia": (61.524, 105.318),
    "moscow": (55.755, 37.617),
    "israel": (31.046, 34.851),
    "gaza": (31.416, 34.333),
    "iran": (32.427, 53.688),
    "lebanon": (33.854, 35.862),
    "syria": (34.802, 38.996),
    "yemen": (15.552, 48.516),
    "china": (35.861, 104.195),
    "beijing": (39.904, 116.407),
    "taiwan": (23.697, 120.960),
    "north korea": (40.339, 127.510),
    "south korea": (35.907, 127.766),
    "pyongyang": (39.039, 125.762),
    "seoul": (37.566, 126.978),
    "japan": (36.204, 138.252),
    "tokyo": (35.676, 139.650),
    "afghanistan": (33.939, 67.709),
    "pakistan": (30.375, 69.345),
    "india": (20.593, 78.962),
    " uk ": (55.378, -3.435),
    "london": (51.507, -0.127),
    "france": (46.227, 2.213),
    "paris": (48.856, 2.352),
    "germany": (51.165, 10.451),
    "berlin": (52.520, 13.405),
    "sudan": (12.862, 30.217),
    "congo": (-4.038, 21.758),
    "south africa": (-30.559, 22.937),
    "nigeria": (9.082, 8.675),
    "egypt": (26.820, 30.802),
    "zimbabwe": (-19.015, 29.154),
    "kenya": (-1.292, 36.821),
    "libya": (26.335, 17.228),
    "mali": (17.570, -3.996),
    "niger": (17.607, 8.081),
    "somalia": (5.152, 46.199),
    "ethiopia": (9.145, 40.489),
    "australia": (-25.274, 133.775),
    "middle east": (31.500, 34.800),
    "europe": (48.800, 2.300),
    "africa": (0.000, 25.000),
    "america": (38.900, -77.000),
    "south america": (-14.200, -51.900),
    "asia": (34.000, 100.000),
    "california": (36.778, -119.417),
    "texas": (31.968, -99.901),
    "florida": (27.994, -81.760),
    "new york": (40.712, -74.006),
    "virginia": (37.431, -78.656),
    "british columbia": (53.726, -127.647),
    "ontario": (51.253, -85.323),
    "quebec": (52.939, -73.549),
    "delhi": (28.704, 77.102),
    "new delhi": (28.613, 77.209),
    "mumbai": (19.076, 72.877),
    "shanghai": (31.230, 121.473),
    "hong kong": (22.319, 114.169),
    "istanbul": (41.008, 28.978),
    "dubai": (25.204, 55.270),
    "singapore": (1.352, 103.819),
    "bangkok": (13.756, 100.501),
    "jakarta": (-6.208, 106.845),
}

def fetch_news():
    # ---------------------------------------------------------------------------
    # REAL-TIME NEWS FIREHOSE — 60+ global RSS sources, 25 entries each
    # ---------------------------------------------------------------------------
    feeds = {
        # --- TIER 1: Major wire services & global outlets ---
        "Reuters": "https://www.reutersagency.com/feed/",
        "AP": "https://rsshub.app/apnews/topics/apf-topnews",
        "BBC World": "http://feeds.bbci.co.uk/news/world/rss.xml",
        "BBC Top": "http://feeds.bbci.co.uk/news/rss.xml",
        "AlJazeera": "https://www.aljazeera.com/xml/rss/all.xml",
        "NYT World": "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
        "NYT Top": "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml",
        "Guardian World": "https://www.theguardian.com/world/rss",
        "Guardian Top": "https://www.theguardian.com/international/rss",
        "WashPost World": "https://feeds.washingtonpost.com/rss/world",
        "WashPost Natl": "https://feeds.washingtonpost.com/rss/national",
        "NPR World": "https://feeds.npr.org/1004/rss.xml",
        "NPR Top": "https://feeds.npr.org/1001/rss.xml",
        "CNN Top": "http://rss.cnn.com/rss/cnn_topstories.rss",
        "CNN World": "http://rss.cnn.com/rss/cnn_world.rss",
        "ABC News": "https://abcnews.go.com/abcnews/topstories",
        "CBS News": "https://www.cbsnews.com/latest/rss/main",
        "CNBC World": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100727362",
        # --- TIER 2: International / Regional ---
        "DW": "https://rss.dw.com/rdf/rss-en-all",
        "France24": "https://www.france24.com/en/rss",
        "RT": "https://www.rt.com/rss/news/",
        "TASS": "https://tass.com/rss/v2.xml",
        "Xinhua": "http://www.xinhuanet.com/english/rss/worldrss.xml",
        "NHK World": "https://www3.nhk.or.jp/nhkworld/rss/world.xml",
        "Kyodo": "https://english.kyodonews.net/rss/all.xml",
        "CNA Asia": "https://www.channelnewsasia.com/rssfeed/8395986",
        "SCMP": "https://www.scmp.com/rss/91/feed",
        "Times of India": "https://timesofindia.indiatimes.com/rssfeedstopstories.cms",
        "Hindustan Times": "https://www.hindustantimes.com/feeds/rss/world-news/rssfeed.xml",
        "Dawn": "https://www.dawn.com/feeds/home",
        "Arab News": "https://www.arabnews.com/rss.xml",
        "Haaretz": "https://www.haaretz.com/cmlink/1.4483969",
        "Jerusalem Post": "https://www.jpost.com/rss/rssfeedsfrontpage.aspx",
        "Ynet": "https://www.ynetnews.com/category/3082",
        "Mercopress": "https://en.mercopress.com/rss/",
        "RFI": "https://www.rfi.fr/en/rss",
        "IRIN": "https://www.thenewhumanitarian.org/rss.xml",
        "Sputnik": "https://sputnikglobe.com/export/rss2/archive/index.xml",
        "Anadolu Agency": "https://www.aa.com.tr/en/rss/default?cat=world",
        "Nikkei Asia": "https://asia.nikkei.com/rss/feed",
        "Korea Herald": "http://www.koreaherald.com/common/rss_xml.php?ct=102",
        "Taipei Times": "https://www.taipeitimes.com/xml/index.rss",
        # --- TIER 3: Defense, Security, Conflict ---
        "GDACS": "https://www.gdacs.org/xml/rss.xml",
        "DefenseOne": "https://www.defenseone.com/rss/",
        "DefenseNews": "https://www.defensenews.com/arc/outboundfeeds/rss/?outputType=xml",
        "WarOnRocks": "https://warontherocks.com/feed/",
        "The War Zone": "https://www.twz.com/feed",
        "Janes": "https://www.janes.com/feeds/news",
        "Jane's Defence": "https://www.janes.com/feeds/news",
        "Breaking Defense": "https://breakingdefense.com/feed/",
        "Stars & Stripes": "https://www.stripes.com/rss",
        "Military Times": "https://www.militarytimes.com/arc/outboundfeeds/rss/?outputType=xml",
        "Bellingcat": "https://www.bellingcat.com/feed/",
        "Intercept": "https://theintercept.com/feed/?rss",
        "Foreign Policy": "https://foreignpolicy.com/feed/",
        "Foreign Affairs": "https://www.foreignaffairs.com/rss.xml",
        "Lawfare": "https://www.lawfaremedia.org/feed",
        # --- TIER 4: Regional conflict / crisis zones ---
        "Kyiv Independent": "https://kyivindependent.com/feed/",
        "Ukrinform": "https://www.ukrinform.net/rss/block-lastnews",
        "Syria Direct": "https://syriadirect.org/feed/",
        "Libya Observer": "https://www.libyaobserver.ly/rss.xml",
        "Somalia Newsroom": "https://www.radiodalsan.com/en/feed/",
        "Sahel Intel": "https://www.thedefensepost.com/feed/",
        "Latin America": "https://www.as-coa.org/rss/articles.xml",
        "Rappler PH": "https://www.rappler.com/feed/",
        "MEE": "https://www.middleeasteye.net/rss",
        "Mondoweiss": "https://mondoweiss.net/feed/",
        "New Lines Mag": "https://newlinesmag.com/feed/",
        "Africa Confidential": "https://www.africa-confidential.com/rss",
        "The East African": "https://www.theeastafrican.co.ke/tea/rss",
        "Myanmar Now": "https://www.myanmar-now.org/en/feed",
        "Frontier Myanmar": "https://www.frontiermyanmar.net/en/feed/",
        "InSight Crime": "https://insightcrime.org/feed/",
        # --- TIER 5: Cyber / OSINT ---
        "Krebs": "https://krebsonsecurity.com/feed/",
        "BleepComputer": "https://www.bleepingcomputer.com/feed/",
        "Dark Reading": "https://www.darkreading.com/rss.xml",
        "The Record": "https://therecord.media/feed",
        "HackerNews": "https://hnrss.org/frontpage",
        "Ars Technica": "https://feeds.arstechnica.com/arstechnica/index",
        "The Register": "https://www.theregister.com/headlines.atom",
        "Schneier": "https://www.schneier.com/feed/",
        # --- TIER 6: Disaster / Science ---
        "USGS Earthquakes": "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/significant_month.atom",
        "NOAA Alerts": "https://alerts.weather.gov/cap/us.php?x=0",
        "Volcano Discovery": "https://www.volcanodiscovery.com/volcanonews.rss",
        "SpaceWeather": "https://spaceweather.com/rssnews.php",
    }

    # All sources get equal weight now — risk scoring does the heavy lifting
    ENTRIES_PER_FEED = 25

    clusters = {}

    # Fetch all feeds in parallel (use requests, not fetch_with_curl which is broken in container)
    def _fetch_feed(item):
        source_name, url = item
        try:
            resp = requests.get(url, timeout=8, headers={"User-Agent": "ShadowLens/1.0"})
            if resp.status_code == 200:
                return source_name, feedparser.parse(resp.text)
        except Exception:
            pass
        return source_name, None

    with concurrent.futures.ThreadPoolExecutor(max_workers=30) as pool:
        feed_results = list(pool.map(_fetch_feed, feeds.items()))

    _seismic_kw = {"earthquake", "seismic", "quake", "tremor", "magnitude", "richter"}
    _risk_kw_high = {"war", "missile", "strike", "airstrike", "attack", "bomb", "nuclear", "invasion",
                     "assassination", "killed", "massacre", "genocide", "chemical weapon", "biological"}
    _risk_kw_med = {"crisis", "tension", "military", "conflict", "defense", "clash", "sanctions",
                    "escalation", "deploy", "troops", "hostage", "siege", "coup", "martial law",
                    "evacuation", "terror", "shooting", "explosion", "drone", "intercept", "navy",
                    "carrier", "submarine", "convoy", "artillery", "shelling", "ceasefire",
                    "refugee", "displacement", "humanitarian", "famine", "pandemic", "outbreak",
                    "protest", "riot", "revolution", "overthrow", "impeach", "emergency",
                    "wildfire", "hurricane", "tornado", "flood", "tsunami", "volcano"}
    _risk_kw_low = {"trade", "tariff", "economy", "election", "summit", "treaty", "negotiation",
                    "diplomacy", "ambassador", "embassy", "united nations", "nato", "eu"}

    total_articles = 0
    for source_name, feed in feed_results:
        if not feed:
            continue
        for entry in feed.entries[:ENTRIES_PER_FEED]:
            title = entry.get('title', '')
            summary = entry.get('summary', '')
            text = (title + " " + summary).lower()

            # Skip earthquake articles (dedicated EQ layer handles those)
            if any(kw in text for kw in _seismic_kw):
                continue

            # GDACS-specific risk score
            if source_name == "GDACS":
                alert_level = entry.get("gdacs_alertlevel", "Green")
                risk_score = 10 if alert_level == "Red" else 7 if alert_level == "Orange" else 4
            else:
                risk_score = 1
                for kw in _risk_kw_high:
                    if kw in text:
                        risk_score += 3
                for kw in _risk_kw_med:
                    if kw in text:
                        risk_score += 2
                for kw in _risk_kw_low:
                    if kw in text:
                        risk_score += 1
                risk_score = min(10, risk_score)

            # Extract image from entry (enclosures, media:content, media:thumbnail)
            image_url = ""
            enclosures = entry.get("enclosures", [])
            if enclosures:
                for enc in enclosures:
                    if "image" in (enc.get("type", "") or ""):
                        image_url = enc.get("href", "")
                        break
            if not image_url:
                media_content = entry.get("media_content", [])
                if media_content:
                    image_url = media_content[0].get("url", "")
            if not image_url:
                media_thumb = entry.get("media_thumbnail", [])
                if media_thumb:
                    image_url = media_thumb[0].get("url", "")
            # Try to extract from summary HTML
            if not image_url and summary:
                img_match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', summary)
                if img_match:
                    image_url = img_match.group(1)

            # Geo-locate: GeoRSS first, then keyword mapping
            lat, lng = None, None
            if 'georss_point' in entry:
                geo_parts = entry['georss_point'].split()
                if len(geo_parts) == 2:
                    try: lat, lng = float(geo_parts[0]), float(geo_parts[1])
                    except ValueError: pass
            elif 'where' in entry and hasattr(entry.get('where'), 'coordinates'):
                coords = entry['where'].coordinates
                lat, lng = coords[1], coords[0]

            if lat is None:
                padded = f" {text} "
                for kw, coord in _KEYWORD_COORDS.items():
                    if kw.startswith(" ") or kw.endswith(" "):
                        if kw in padded:
                            lat, lng = coord
                            break
                    else:
                        if re.search(r'\b' + re.escape(kw) + r'\b', text):
                            lat, lng = coord
                            break

            # Also try _COUNTRY_COORDS for broader matching
            if lat is None:
                for kw, (clat, clon) in _COUNTRY_COORDS.items():
                    if kw in text:
                        lat, lng = clat, clon
                        break

            # Cluster by location (2-degree radius ≈ 200km)
            if lat is not None:
                key = None
                for existing_key in clusters.keys():
                    if "," in existing_key:
                        parts = existing_key.split(",")
                        try:
                            elat, elng = float(parts[0]), float(parts[1])
                            if ((lat - elat)**2 + (lng - elng)**2)**0.5 < 2.0:
                                key = existing_key
                                break
                        except ValueError:
                            pass
                if key is None:
                    key = f"{lat},{lng}"
            else:
                key = f"nocord-{hash(title) % 100000}"

            if key not in clusters:
                clusters[key] = []

            clusters[key].append({
                "title": title,
                "link": entry.get('link', ''),
                "published": entry.get('published', ''),
                "source": source_name,
                "risk_score": risk_score,
                "coords": [lat, lng] if lat is not None else None,
                "image_url": image_url,
            })
            total_articles += 1

    news_items = []
    for key, articles in clusters.items():
        articles.sort(key=lambda x: x['risk_score'], reverse=True)
        max_risk = articles[0]['risk_score']
        top_article = articles[0]
        news_items.append({
            "title": top_article["title"],
            "link": top_article["link"],
            "published": top_article["published"],
            "source": top_article["source"],
            "risk_score": max_risk,
            "coords": top_article["coords"],
            "image_url": top_article.get("image_url", ""),
            "cluster_count": len(articles),
            "articles": articles,
            "machine_assessment": generate_machine_assessment(top_article["title"], "", max_risk)
        })

    news_items.sort(key=lambda x: x['risk_score'], reverse=True)
    latest_data['news'] = news_items
    logger.info(f"News firehose: {total_articles} articles from {sum(1 for _,f in feed_results if f)} feeds → {len(news_items)} stories")

def fetch_defense_stocks():
    tickers = ["RTX", "LMT", "NOC", "GD", "BA", "PLTR"]
    stocks_data = {}
    try:
        for t in tickers:
            try:
                ticker = yf.Ticker(t)
                hist = ticker.history(period="2d")
                if len(hist) >= 1:
                    current_price = hist['Close'].iloc[-1]
                    prev_close = hist['Close'].iloc[0] if len(hist) > 1 else current_price
                    change_percent = ((current_price - prev_close) / prev_close) * 100 if prev_close else 0
                    
                    stocks_data[t] = {
                        "price": round(float(current_price), 2),
                        "change_percent": round(float(change_percent), 2),
                        "up": bool(change_percent >= 0)
                    }
            except Exception as e:
                logger.warning(f"Could not fetch data for {t}: {e}")
                
        latest_data['stocks'] = stocks_data
    except Exception as e:
        logger.error(f"Error fetching stocks: {e}")

def fetch_oil_prices():
    # CL=F is Crude Oil, BZ=F is Brent Crude
    tickers = {"WTI Crude": "CL=F", "Brent Crude": "BZ=F"}
    oil_data = {}
    try:
        for name, symbol in tickers.items():
            try:
                ticker = yf.Ticker(symbol)
                hist = ticker.history(period="5d")
                if len(hist) >= 2:
                    current_price = hist['Close'].iloc[-1]
                    prev_close = hist['Close'].iloc[-2]
                    change_percent = ((current_price - prev_close) / prev_close) * 100 if prev_close else 0
                    
                    oil_data[name] = {
                        "price": round(float(current_price), 2),
                        "change_percent": round(float(change_percent), 2),
                        "up": bool(change_percent >= 0)
                    }
            except Exception as e:
                logger.warning(f"Could not fetch data for {symbol}: {e}")
                
        latest_data['oil'] = oil_data
    except Exception as e:
        logger.error(f"Error fetching oil: {e}")

dynamic_routes_cache = {}  # callsign -> {data..., _ts: timestamp}
routes_fetch_in_progress = False
ROUTES_CACHE_TTL = 7200  # 2 hours
ROUTES_CACHE_MAX = 5000

def fetch_routes_background(sampled):
    global dynamic_routes_cache, routes_fetch_in_progress
    if routes_fetch_in_progress:
        return
    routes_fetch_in_progress = True
    
    try:
        # Prune stale entries (older than 2 hours) and cap at max size
        now_ts = time.time()
        stale_keys = [k for k, v in dynamic_routes_cache.items() if now_ts - v.get('_ts', 0) > ROUTES_CACHE_TTL]
        for k in stale_keys:
            del dynamic_routes_cache[k]
        if len(dynamic_routes_cache) > ROUTES_CACHE_MAX:
            # Remove oldest entries
            sorted_keys = sorted(dynamic_routes_cache, key=lambda k: dynamic_routes_cache[k].get('_ts', 0))
            for k in sorted_keys[:len(dynamic_routes_cache) - ROUTES_CACHE_MAX]:
                del dynamic_routes_cache[k]

        callsigns_to_query = []
        for f in sampled:
            c_sign = str(f.get("flight", "")).strip()
            if c_sign and c_sign != "UNKNOWN":
                callsigns_to_query.append({
                    "callsign": c_sign,
                    "lat": f.get("lat", 0),
                    "lng": f.get("lon", 0)
                })
        
        batch_size = 100
        batches = [callsigns_to_query[i:i+batch_size] for i in range(0, len(callsigns_to_query), batch_size)]
        
        for batch in batches:
            try:
                r = fetch_with_curl("https://api.adsb.lol/api/0/routeset", method="POST", json_data={"planes": batch}, timeout=15)
                if r.status_code == 200:
                    route_data = r.json()
                    route_list = []
                    if isinstance(route_data, dict):
                        route_list = route_data.get("value", [])
                    elif isinstance(route_data, list):
                        route_list = route_data
                        
                    for route in route_list:
                        callsign = route.get("callsign", "")
                        airports = route.get("_airports", [])
                        if airports and len(airports) >= 2:
                            orig_apt = airports[0]
                            dest_apt = airports[-1]
                            dynamic_routes_cache[callsign] = {
                                "orig_name": f"{orig_apt.get('iata', '')}: {orig_apt.get('name', 'Unknown')}",
                                "dest_name": f"{dest_apt.get('iata', '')}: {dest_apt.get('name', 'Unknown')}",
                                "orig_loc": [orig_apt.get("lon", 0), orig_apt.get("lat", 0)],
                                "dest_loc": [dest_apt.get("lon", 0), dest_apt.get("lat", 0)],
                                "_ts": time.time(),
                            }
                time.sleep(0.25) # Throttle strictly beneath 10 requests / second limit
            except Exception:
                pass
    finally:
        routes_fetch_in_progress = False

# Helicopter type codes (backend classification)
_HELI_TYPES_BACKEND = {
    "R22", "R44", "R66", "B06", "B06T", "B204", "B205", "B206", "B212", "B222", "B230",
    "B407", "B412", "B427", "B429", "B430", "B505", "B525",
    "AS32", "AS35", "AS50", "AS55", "AS65",
    "EC20", "EC25", "EC30", "EC35", "EC45", "EC55", "EC75",
    "H125", "H130", "H135", "H145", "H155", "H160", "H175", "H215", "H225",
    "S55", "S58", "S61", "S64", "S70", "S76", "S92",
    "A109", "A119", "A139", "A169", "A189", "AW09",
    "MD52", "MD60", "MDHI", "MD90", "NOTR",
    "B47G", "HUEY", "GAMA", "CABR", "EXE",
}

def fetch_flights():
    # OpenSky Network public API for flights. We want to demonstrate global coverage.
    flights = []
    try:
        # Sample flights from North America, Europe, Asia
        regions = [
            {"lat": 39.8, "lon": -98.5, "dist": 2000},  # USA
            {"lat": 50.0, "lon": 15.0, "dist": 2000},   # Europe
            {"lat": 35.0, "lon": 105.0, "dist": 2000},  # Asia / China
            {"lat": -25.0, "lon": 133.0, "dist": 2000}, # Australia
            {"lat": 0.0, "lon": 20.0, "dist": 2500},    # Africa
            {"lat": -15.0, "lon": -60.0, "dist": 2000}  # South America
        ]
        
        all_adsb_flights = []

        # Multi-source ADS-B failover — round-robin between adsb.lol, adsb.fi, airplanes.live
        _adsb_sources = [
            ("adsb.lol", "https://api.adsb.lol/v2/lat/{lat}/lon/{lon}/dist/{dist}"),
            ("adsb.fi", "https://opendata.adsb.fi/v2/lat/{lat}/lon/{lon}/dist/{dist}"),
            ("airplanes.live", "https://api.airplanes.live/v2/point/{lat}/{lon}/{dist}"),
        ]
        _adsb_cooldowns = {}  # source -> earliest retry time

        def _fetch_region(r):
            now = time.time()
            for source_name, url_template in _adsb_sources:
                # Skip sources in cooldown
                if _adsb_cooldowns.get(source_name, 0) > now:
                    continue
                url = url_template.format(lat=r['lat'], lon=r['lon'], dist=r['dist'])
                try:
                    res = requests.get(url, timeout=10, headers={"User-Agent": "ShadowLens/1.0"})
                    if res.status_code == 200:
                        data = res.json()
                        ac = data.get("ac", data.get("aircraft", []))
                        if isinstance(ac, list):
                            return ac
                    elif res.status_code == 429:
                        # Rate limited — cooldown this source for 60s
                        _adsb_cooldowns[source_name] = now + 60
                        logger.warning(f"ADS-B {source_name} rate limited, cooling down 60s")
                        continue
                except requests.exceptions.Timeout:
                    _adsb_cooldowns[source_name] = now + 30
                    continue
                except Exception as e:
                    logger.warning(f"ADS-B {source_name} failed for lat={r['lat']}: {e}")
                    _adsb_cooldowns[source_name] = now + 30
                    continue
            return []

        # Fetch all regions in parallel for maximum speed
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            results = pool.map(_fetch_region, regions)
        for region_flights in results:
            all_adsb_flights.extend(region_flights)

        # ---------------------------------------------------------------------------
        # OpenSky Regional Fallback (Africa, Asia, South America)
        # ---------------------------------------------------------------------------
        now = time.time()
        global last_opensky_fetch, cached_opensky_flights
        
        # OpenSky has a 400 req/day limit (~16 pings/hour)
        # 5 minutes = 288 pings/day (Safe margin)
        if now - last_opensky_fetch > 300:
            token = opensky_client.get_token()
            if token:
                opensky_regions = [
                    {"name": "Africa", "bbox": {"lamin": -35.0, "lomin": -20.0, "lamax": 38.0, "lomax": 55.0}},
                    {"name": "Asia", "bbox": {"lamin": 0.0, "lomin": 30.0, "lamax": 75.0, "lomax": 150.0}},
                    {"name": "South America", "bbox": {"lamin": -60.0, "lomin": -95.0, "lamax": 15.0, "lomax": -30.0}}
                ]
                
                new_opensky_flights = []
                for os_reg in opensky_regions:
                    try:
                        bb = os_reg["bbox"]
                        os_url = f"https://opensky-network.org/api/states/all?lamin={bb['lamin']}&lomin={bb['lomin']}&lamax={bb['lamax']}&lomax={bb['lomax']}"
                        headers = {"Authorization": f"Bearer {token}"}
                        os_res = requests.get(os_url, headers=headers, timeout=15)
                        
                        if os_res.status_code == 200:
                            os_data = os_res.json()
                            states = os_data.get("states") or []
                            logger.info(f"OpenSky: Fetched {len(states)} states for {os_reg['name']}")
                            
                            for s in states:
                                # OpenSky state vector mapping:
                                # 0icao, 1callsign, 2country, 3time, 4last, 5lon, 6lat, 7baro, 8ground, 9vel, 10track, 11vert, 12sens, 13geo, 14sqk
                                new_opensky_flights.append({
                                    "hex": s[0],
                                    "flight": s[1].strip() if s[1] else "UNKNOWN",
                                    "r": s[2],
                                    "lon": s[5],
                                    "lat": s[6],
                                    "alt_baro": (s[7] * 3.28084) if s[7] else 0, # Meters to Feet for internal consistency
                                    "track": s[10] or 0,
                                    "gs": (s[9] * 1.94384) if s[9] else 0, # m/s to knots
                                    "t": "Unknown", # Model unknown in states API
                                    "is_opensky": True
                                })
                        else:
                            logger.warning(f"OpenSky API {os_reg['name']} failed: {os_res.status_code}")
                    except Exception as ex:
                        logger.error(f"OpenSky fetching error for {os_reg['name']}: {ex}")
                
                cached_opensky_flights = new_opensky_flights
                last_opensky_fetch = now
        
        # Merge cached OpenSky flights, but deduplicate by icao24 hex code
        # ADS-B Exchange is primary; OpenSky only fills gaps
        seen_hex = set()
        for f in all_adsb_flights:
            h = f.get("hex")
            if h:
                seen_hex.add(h.lower().strip())
        for osf in cached_opensky_flights:
            h = osf.get("hex")
            if h and h.lower().strip() not in seen_hex:
                all_adsb_flights.append(osf)
                seen_hex.add(h.lower().strip())

                    
        if all_adsb_flights:
            
            # The user requested maximum flight density. Rendering all available aircraft.
            sampled = all_adsb_flights
            
            # Spin up the background batch route resolver if it's not already trickling
            if not routes_fetch_in_progress:
                threading.Thread(target=fetch_routes_background, args=(sampled,), daemon=True).start()
            
            for f in sampled:
                try:
                    lat = f.get("lat")
                    lng = f.get("lon")
                    heading = f.get("track") or 0
                    
                    if lat is None or lng is None:
                        continue
                        
                    flight_str = str(f.get("flight", "UNKNOWN")).strip()
                    if not flight_str or flight_str == "UNKNOWN":
                        flight_str = str(f.get("hex", "Unknown"))
                        
                    # Origin and destination are fetched via the background thread and cached
                    origin_loc = None
                    dest_loc = None
                    origin_name = "UNKNOWN"
                    dest_name = "UNKNOWN"
                    
                    if flight_str in dynamic_routes_cache:
                        cached = dynamic_routes_cache[flight_str]
                        origin_name = cached["orig_name"]
                        dest_name = cached["dest_name"]
                        origin_loc = cached["orig_loc"]
                        dest_loc = cached["dest_loc"]
                    
                    # Extract 3-letter ICAO Airline Code from CallSign (e.g. UAL123 -> UAL)
                    airline_code = ""
                    match = _RE_AIRLINE_CODE_1.match(flight_str)
                    if not match:
                        match = _RE_AIRLINE_CODE_2.match(flight_str)
                    if match:
                        airline_code = match.group(1)

                    alt_raw = f.get("alt_baro")
                    alt_value = 0
                    if isinstance(alt_raw, (int, float)):
                        alt_value = alt_raw * 0.3048
                    
                    # Ground speed from ADS-B (in knots)
                    gs_knots = f.get("gs")
                    speed_knots = round(gs_knots, 1) if isinstance(gs_knots, (int, float)) else None

                    model_upper = f.get("t", "").upper()
                    ac_category = "heli" if model_upper in _HELI_TYPES_BACKEND else "plane"

                    flights.append({
                        "callsign": flight_str,
                        "country": f.get("r", "N/A"),
                        "lng": float(lng),
                        "lat": float(lat),
                        "alt": alt_value,
                        "heading": heading,
                        "type": "flight",
                        "origin_loc": origin_loc,
                        "dest_loc": dest_loc,
                        "origin_name": origin_name,
                        "dest_name": dest_name,
                        "registration": f.get("r", "N/A"),
                        "model": f.get("t", "Unknown"),
                        "icao24": f.get("hex", ""),
                        "speed_knots": speed_knots,
                        "squawk": f.get("squawk", ""),
                        "airline_code": airline_code,
                        "aircraft_category": ac_category,
                        "nac_p": f.get("nac_p")  # Navigation accuracy — used for GPS jamming detection
                    })
                except Exception as loop_e:
                    logger.error(f"Flight interpolation error: {loop_e}")
                    continue
                
    except Exception as e:
        logger.error(f"Error fetching adsb.lol flights: {e}")
        
    # Private jet ICAO type designator codes (business jets wealthy individuals fly)
    PRIVATE_JET_TYPES = {
        # Gulfstream
        "G150", "G200", "G280", "GLEX", "G500", "G550", "G600", "G650", "G700",
        "GLF2", "GLF3", "GLF4", "GLF5", "GLF6", "GL5T", "GL7T", "GV", "GIV",
        # Bombardier
        "CL30", "CL35", "CL60", "BD70", "BD10", "GL5T", "GL7T",
        "CRJ1", "CRJ2",  # Challenger variants used privately
        # Cessna Citation
        "C25A", "C25B", "C25C", "C500", "C501", "C510", "C525", "C526",
        "C550", "C560", "C56X", "C680", "C68A", "C700", "C750",
        # Dassault Falcon
        "FA10", "FA20", "FA50", "FA7X", "FA8X", "F900", "F2TH", "ASTR",
        # Embraer Business Jets
        "E35L", "E545", "E550", "E55P", "LEGA",  # Praetor / Legacy
        "PH10",  # Phenom 100
        "PH30",  # Phenom 300
        # Learjet
        "LJ23", "LJ24", "LJ25", "LJ28", "LJ31", "LJ35", "LJ36",
        "LJ40", "LJ45", "LJ55", "LJ60", "LJ70", "LJ75",
        # Hawker / Beechcraft
        "H25A", "H25B", "H25C", "HA4T", "BE40", "PRM1",
        # Other business jets
        "HDJT",  # HondaJet
        "PC24",  # Pilatus PC-24
        "EA50",  # Eclipse 500
        "SF50",  # Cirrus Vision Jet
        "GALX",  # IAI Galaxy
    }
    
    commercial = []
    private_jets = []
    private_ga = []
    tracked = []
    
    
    for f in flights:
        # Enrich every flight with plane-alert data
        enrich_with_plane_alert(f)
        enrich_with_tracked_names(f)
        
        callsign = f.get('callsign', '').strip().upper()
        # Heuristic: standard airline callsigns are 3 letters + 1 to 4 digits (e.g., AFR7403, BAW12)
        is_commercial_format = bool(re.match(r'^[A-Z]{3}\d{1,4}[A-Z]{0,2}$', callsign))
        
        if f.get('alert_category'):
            # This is a tracked aircraft — pull it out into tracked list
            f['type'] = 'tracked_flight'
            tracked.append(f)
        elif f.get('airline_code') or is_commercial_format:
            f['type'] = 'commercial_flight'
            commercial.append(f)
        elif f.get('model', '').upper() in PRIVATE_JET_TYPES:
            f['type'] = 'private_jet'
            private_jets.append(f)
        else:
            f['type'] = 'private_ga'
            private_ga.append(f)
    
    # --- Smart merge: protect against partial API failures ---
    # If the new dataset has dramatically fewer flights than what we already have,
    # a region fetch probably failed — keep the old data to prevent planes vanishing.
    prev_commercial_count = len(latest_data.get('commercial_flights', []))
    prev_total = prev_commercial_count + len(latest_data.get('private_jets', [])) + len(latest_data.get('private_flights', []))
    new_total = len(commercial) + len(private_jets) + len(private_ga)

    if new_total == 0:
        logger.warning("No civilian flights found! Skipping overwrite to prevent clearing the map.")
    elif prev_total > 100 and new_total < prev_total * 0.5:
        # Dramatic drop (>50% loss) — a region probably failed, keep existing data
        logger.warning(f"Flight count dropped from {prev_total} to {new_total} (>50% loss). Keeping previous data to prevent flicker.")
    else:
        # Merge: deduplicate by icao24, prefer new data
        import time as _time
        _now = _time.time()

        def _merge_category(new_list, old_list, max_stale_s=120):
            """Merge new flights with old, keeping stale entries for up to max_stale_s."""
            by_icao = {}
            # Old entries first (will be overwritten by new)
            for f in old_list:
                icao = f.get('icao24', '')
                if icao:
                    f.setdefault('_seen_at', _now)
                    # Evict if stale for too long
                    if (_now - f.get('_seen_at', _now)) < max_stale_s:
                        by_icao[icao] = f
            # New entries overwrite old
            for f in new_list:
                icao = f.get('icao24', '')
                if icao:
                    f['_seen_at'] = _now
                    by_icao[icao] = f
                else:
                    by_icao[id(f)] = f  # no icao — keep as unique
            return list(by_icao.values())

        with _data_lock:
            latest_data['commercial_flights'] = _merge_category(commercial, latest_data.get('commercial_flights', []))
            latest_data['private_jets'] = _merge_category(private_jets, latest_data.get('private_jets', []))
            latest_data['private_flights'] = _merge_category(private_ga, latest_data.get('private_flights', []))

    # Always write raw flights for GPS jamming analysis (nac_p field)
    if flights:
        latest_data['flights'] = flights
    
    # Merge tracked civilian flights with any tracked military flights
    # CRITICAL: Update positions for already-tracked aircraft on every cycle,
    # not just add new ones — otherwise tracked positions go stale.
    existing_tracked = latest_data.get('tracked_flights', [])
    
    # Build a map of fresh tracked data keyed by icao24
    fresh_tracked_map = {}
    for t in tracked:
        icao = t.get('icao24', '').upper()
        if icao:
            fresh_tracked_map[icao] = t
    
    # Update existing tracked entries with fresh positions, preserve metadata
    merged_tracked = []
    seen_icaos = set()
    for old_t in existing_tracked:
        icao = old_t.get('icao24', '').upper()
        if icao in fresh_tracked_map:
            # Fresh data available — use it, but preserve any extra metadata from old entry
            fresh = fresh_tracked_map[icao]
            for key in ('alert_category', 'alert_operator', 'alert_special', 'alert_flag'):
                if key in old_t and key not in fresh:
                    fresh[key] = old_t[key]
            merged_tracked.append(fresh)
            seen_icaos.add(icao)
        else:
            # No fresh data (military-only tracked, or plane landed/out of range)
            merged_tracked.append(old_t)
            seen_icaos.add(icao)
    
    # Add any newly-discovered tracked aircraft
    for icao, t in fresh_tracked_map.items():
        if icao not in seen_icaos:
            merged_tracked.append(t)
    
    latest_data['tracked_flights'] = merged_tracked
    logger.info(f"Tracked flights: {len(merged_tracked)} total ({len(fresh_tracked_map)} fresh from civilian)")
    
    # -----------------------------------------------------------------------
    # Flight Trail Accumulation — build position history for unrouted flights
    # -----------------------------------------------------------------------
    def _accumulate_trail(f, now_ts, check_route=True):
        """Accumulate trail points for a single flight. Returns 1 if trail updated, 0 otherwise."""
        hex_id = f.get('icao24', '').lower()
        if not hex_id:
            return 0, None
        if check_route and f.get('origin_name', 'UNKNOWN') != 'UNKNOWN':
            f['trail'] = []
            return 0, hex_id
        lat, lng, alt = f.get('lat'), f.get('lng'), f.get('alt', 0)
        if lat is None or lng is None:
            f['trail'] = flight_trails.get(hex_id, {}).get('points', [])
            return 0, hex_id
        point = [round(lat, 5), round(lng, 5), round(alt, 1), round(now_ts)]
        if hex_id not in flight_trails:
            flight_trails[hex_id] = {'points': [], 'last_seen': now_ts}
        trail_data = flight_trails[hex_id]
        if trail_data['points'] and trail_data['points'][-1][0] == point[0] and trail_data['points'][-1][1] == point[1]:
            trail_data['last_seen'] = now_ts
        else:
            trail_data['points'].append(point)
            trail_data['last_seen'] = now_ts
        if len(trail_data['points']) > 200:
            trail_data['points'] = trail_data['points'][-200:]
        f['trail'] = trail_data['points']
        return 1, hex_id

    now_ts = datetime.utcnow().timestamp()
    all_lists = [commercial, private_jets, private_ga, existing_tracked]
    seen_hexes = set()
    trail_count = 0
    with _trails_lock:
        for flist in all_lists:
            for f in flist:
                count, hex_id = _accumulate_trail(f, now_ts, check_route=True)
                trail_count += count
                if hex_id:
                    seen_hexes.add(hex_id)

        # Also process military flights (separate list)
        for mf in latest_data.get('military_flights', []):
            count, hex_id = _accumulate_trail(mf, now_ts, check_route=False)
            trail_count += count
            if hex_id:
                seen_hexes.add(hex_id)

        # Prune stale trails (10 min for non-tracked, 30 min for tracked)
        tracked_hexes = {t.get('icao24', '').lower() for t in latest_data.get('tracked_flights', [])}
        stale_keys = []
        for k, v in flight_trails.items():
            cutoff = now_ts - 1800 if k in tracked_hexes else now_ts - 600
            if v['last_seen'] < cutoff:
                stale_keys.append(k)
        for k in stale_keys:
            del flight_trails[k]

        # Enforce global cap — evict oldest trails first
        if len(flight_trails) > _MAX_TRACKED_TRAILS:
            sorted_keys = sorted(flight_trails.keys(), key=lambda k: flight_trails[k]['last_seen'])
            evict_count = len(flight_trails) - _MAX_TRACKED_TRAILS
            for k in sorted_keys[:evict_count]:
                del flight_trails[k]

    logger.info(f"Trail accumulation: {trail_count} active trails, {len(stale_keys)} pruned, {len(flight_trails)} total")

    # -----------------------------------------------------------------------
    # GPS / GNSS Jamming Detection — aggregate NACp from ADS-B transponders
    # NACp (Navigation Accuracy Category for Position):
    #   11 = full accuracy (<3m), 8 = good (<93m), <8 = degraded = potential jamming
    # We use a 1°×1° grid (~111km at equator) to aggregate interference zones.
    # -----------------------------------------------------------------------
    try:
        jamming_grid = {}  # "lat,lng" -> {"degraded": int, "total": int}
        raw_flights = latest_data.get('flights', [])
        for rf in raw_flights:
            rlat = rf.get('lat')
            rlng = rf.get('lng') or rf.get('lon')
            if rlat is None or rlng is None:
                continue
            nacp = rf.get('nac_p')
            if nacp is None:
                continue
            # Grid key: snap to 1-degree cells
            grid_key = f"{int(rlat)},{int(rlng)}"
            if grid_key not in jamming_grid:
                jamming_grid[grid_key] = {"degraded": 0, "total": 0}
            jamming_grid[grid_key]["total"] += 1
            if nacp < 8:
                jamming_grid[grid_key]["degraded"] += 1

        jamming_zones = []
        for gk, counts in jamming_grid.items():
            if counts["total"] < 3:
                continue  # Need at least 3 aircraft to be meaningful
            ratio = counts["degraded"] / counts["total"]
            if ratio > 0.25:  # >25% degraded = jamming
                lat_i, lng_i = gk.split(",")
                severity = "low" if ratio < 0.5 else "medium" if ratio < 0.75 else "high"
                jamming_zones.append({
                    "lat": int(lat_i) + 0.5,  # Center of cell
                    "lng": int(lng_i) + 0.5,
                    "severity": severity,
                    "ratio": round(ratio, 2),
                    "degraded": counts["degraded"],
                    "total": counts["total"]
                })
        latest_data['gps_jamming'] = jamming_zones
        if jamming_zones:
            logger.info(f"GPS Jamming: {len(jamming_zones)} interference zones detected")
    except Exception as e:
        logger.error(f"GPS Jamming detection error: {e}")
        latest_data['gps_jamming'] = []

    # -----------------------------------------------------------------------
    # Holding Pattern Detection — flag aircraft circling in place
    # If cumulative heading change over last 8 trail points > 300°, it's circling
    # -----------------------------------------------------------------------
    try:
        holding_count = 0
        all_flight_lists = [commercial, private_jets, private_ga,
                            latest_data.get('tracked_flights', []),
                            latest_data.get('military_flights', [])]
        for flist in all_flight_lists:
            for f in flist:
                hex_id = f.get('icao24', '').lower()
                trail = flight_trails.get(hex_id, {}).get('points', [])
                if len(trail) < 6:
                    f['holding'] = False
                    continue
                # Calculate cumulative bearing change over last 8 points
                pts = trail[-8:]
                total_turn = 0.0
                prev_bearing = 0.0
                for i in range(1, len(pts)):
                    lat1, lng1 = math.radians(pts[i-1][0]), math.radians(pts[i-1][1])
                    lat2, lng2 = math.radians(pts[i][0]), math.radians(pts[i][1])
                    dlng = lng2 - lng1
                    x = math.sin(dlng) * math.cos(lat2)
                    y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlng)
                    bearing = math.degrees(math.atan2(x, y)) % 360
                    if i > 1:
                        delta = abs(bearing - prev_bearing)
                        if delta > 180:
                            delta = 360 - delta
                        total_turn += delta
                    prev_bearing = bearing
                f['holding'] = total_turn > 300  # > 300° = nearly a full circle
                if f['holding']:
                    holding_count += 1
        if holding_count:
            logger.info(f"Holding patterns: {holding_count} aircraft circling")
    except Exception as e:
        logger.error(f"Holding pattern detection error: {e}")

    # Update timestamp so the ETag in /api/live-data/fast changes on every fetch cycle
    latest_data['last_updated'] = datetime.utcnow().isoformat()

def fetch_ships():
    """Fetch real-time AIS vessel data and combine with OSINT carrier positions."""
    from services.ais_stream import get_ais_vessels
    from services.carrier_tracker import get_carrier_positions
    
    ships = []
    
    # Dynamic OSINT carrier positions (updated from GDELT + cache)
    carriers = get_carrier_positions()
    ships.extend(carriers)
    
    # Real AIS vessel data from aisstream.io
    ais_vessels = get_ais_vessels()
    ships.extend(ais_vessels)
    
    logger.info(f"Ships: {len(carriers)} carriers + {len(ais_vessels)} AIS vessels")
    latest_data['ships'] = ships

def fetch_military_flights():
    # True ADS-B Exchange military data requires paid API access.
    # We will use adsb.lol (an open source ADSB aggregator) /v2/mil fallback.
    military_flights = []
    try:
        url = "https://api.adsb.lol/v2/mil"
        response = fetch_with_curl(url, timeout=10)
        if response.status_code == 200:
            ac = response.json().get('ac', [])
            for f in ac: 
                try:
                    lat = f.get("lat")
                    lng = f.get("lon")
                    heading = f.get("track") or 0
                    
                    if lat is None or lng is None:
                        continue
                        
                    model = str(f.get("t", "UNKNOWN")).upper()
                    mil_cat = "default"
                    if "H" in model and any(c.isdigit() for c in model):
                        mil_cat = "heli"
                    elif any(k in model for k in ["K35", "K46", "A33"]):
                        mil_cat = "tanker"
                    elif any(k in model for k in ["F16", "F35", "F22", "F15", "F18", "T38", "T6", "A10"]):
                        mil_cat = "fighter"
                    elif any(k in model for k in ["C17", "C5", "C130", "C30", "A400", "V22"]):
                        mil_cat = "cargo"
                    elif any(k in model for k in ["P8", "E3", "E8", "U2", "RQ", "MQ"]):
                        mil_cat = "recon"

                    # Military flights don't file public routes
                    origin_loc = None
                    dest_loc = None
                    origin_name = "UNKNOWN"
                    dest_name = "UNKNOWN"


                    alt_raw = f.get("alt_baro")
                    alt_value = 0
                    if isinstance(alt_raw, (int, float)):
                        alt_value = alt_raw * 0.3048
                    
                    # Ground speed from ADS-B (in knots)
                    gs_knots = f.get("gs")
                    speed_knots = round(gs_knots, 1) if isinstance(gs_knots, (int, float)) else None

                    military_flights.append({
                        "callsign": str(f.get("flight", "MIL-UNKN")).strip(),
                        "country": f.get("r", "Military Asset"),
                        "lng": float(lng),
                        "lat": float(lat),
                        "alt": alt_value,
                        "heading": heading,
                        "type": "military_flight",
                        "military_type": mil_cat,
                        "origin_loc": origin_loc,
                        "dest_loc": dest_loc,
                        "origin_name": origin_name,
                        "dest_name": dest_name,
                        "registration": f.get("r", "N/A"),
                        "model": f.get("t", "Unknown"),
                        "icao24": f.get("hex", ""),
                        "speed_knots": speed_knots,
                        "squawk": f.get("squawk", "")
                    })
                except Exception as loop_e:
                    logger.error(f"Mil flight interpolation error: {loop_e}")
                    continue
    except Exception as e:
        logger.error(f"Error fetching military flights: {e}")
        
    if not military_flights:
        # API failed or rate limited — log but do NOT inject fake data
        logger.warning("No military flights retrieved — keeping previous data if available")
        # Preserve existing data rather than overwriting with empty
        if latest_data.get('military_flights'):
            return
            
    latest_data['military_flights'] = military_flights
    
    # Cross-reference military flights with Plane-Alert DB
    tracked_mil = []
    remaining_mil = []
    for mf in military_flights:
        enrich_with_plane_alert(mf)
        if mf.get('alert_category'):
            mf['type'] = 'tracked_flight'
            tracked_mil.append(mf)
        else:
            remaining_mil.append(mf)
    latest_data['military_flights'] = remaining_mil
    
    # Store tracked military flights — update positions for existing entries
    existing_tracked = latest_data.get('tracked_flights', [])
    fresh_mil_map = {}
    for t in tracked_mil:
        icao = t.get('icao24', '').upper()
        if icao:
            fresh_mil_map[icao] = t
    
    # Update existing military tracked entries with fresh positions
    updated_tracked = []
    seen_icaos = set()
    for old_t in existing_tracked:
        icao = old_t.get('icao24', '').upper()
        if icao in fresh_mil_map:
            fresh = fresh_mil_map[icao]
            for key in ('alert_category', 'alert_operator', 'alert_special', 'alert_flag'):
                if key in old_t and key not in fresh:
                    fresh[key] = old_t[key]
            updated_tracked.append(fresh)
            seen_icaos.add(icao)
        else:
            updated_tracked.append(old_t)
            seen_icaos.add(icao)
    for icao, t in fresh_mil_map.items():
        if icao not in seen_icaos:
            updated_tracked.append(t)
    latest_data['tracked_flights'] = updated_tracked
    logger.info(f"Tracked flights: {len(updated_tracked)} total ({len(tracked_mil)} from military)")

def fetch_weather():
    try:
        url = "https://api.rainviewer.com/public/weather-maps.json"
        response = fetch_with_curl(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if "radar" in data and "past" in data["radar"]:
                latest_time = data["radar"]["past"][-1]["time"]
                latest_data["weather"] = {"time": latest_time, "host": data.get("host", "https://tilecache.rainviewer.com")}
    except Exception as e:
        logger.error(f"Error fetching weather: {e}")

def fetch_cctv():
    try:
        latest_data["cctv"] = get_all_cameras()
    except Exception as e:
        logger.error(f"Error fetching cctv from DB: {e}")
        latest_data["cctv"] = []

def fetch_tfrs():
    """FAA Temporary Flight Restrictions — reveals VIP movement, military ops, space launches."""
    try:
        url = "https://tfr.faa.gov/geoserver/TFR/ows?service=WFS&version=1.0.0&request=GetFeature&typeName=TFR:V_TFR_LOC&outputFormat=application/json"
        resp = fetch_with_curl(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        tfrs = []
        for feat in data.get("features", []):
            props = feat.get("properties", {})
            geom = feat.get("geometry", {})
            if not geom:
                continue
            # Get centroid for point display
            coords = geom.get("coordinates", [])
            if geom.get("type") == "Polygon" and coords:
                ring = coords[0]
                clat = sum(c[1] for c in ring) / len(ring)
                clon = sum(c[0] for c in ring) / len(ring)
            elif geom.get("type") == "MultiPolygon" and coords:
                ring = coords[0][0]
                clat = sum(c[1] for c in ring) / len(ring)
                clon = sum(c[0] for c in ring) / len(ring)
            else:
                continue
            tfrs.append({
                "id": props.get("NOTAM_KEY", ""),
                "title": props.get("TITLE", ""),
                "type": props.get("LEGAL", "TFR"),
                "state": props.get("STATE", ""),
                "lat": clat,
                "lon": clon,
                "geometry": geom,
            })
        latest_data["tfrs"] = tfrs
        logger.info(f"Fetched {len(tfrs)} FAA TFRs")
    except Exception as e:
        logger.error(f"Error fetching TFRs: {e}")


def fetch_weather_alerts():
    """NWS active weather alerts with severity and polygons."""
    try:
        resp = fetch_with_curl("https://api.weather.gov/alerts/active?status=actual",
                               timeout=15, headers={"User-Agent": "ShadowLens-OSINT/1.0",
                                                     "Accept": "application/geo+json"})
        resp.raise_for_status()
        data = resp.json()
        alerts = []
        for feat in data.get("features", []):
            props = feat.get("properties", {})
            geom = feat.get("geometry")
            severity = props.get("severity", "")
            if severity not in ("Extreme", "Severe", "Moderate"):
                continue  # Skip minor/unknown to reduce noise
            # Try to get a center point from geometry
            lat, lon = None, None
            if geom and geom.get("type") == "Polygon":
                ring = geom["coordinates"][0]
                lat = sum(c[1] for c in ring) / len(ring)
                lon = sum(c[0] for c in ring) / len(ring)
            alerts.append({
                "id": props.get("id", ""),
                "event": props.get("event", ""),
                "severity": severity,
                "urgency": props.get("urgency", ""),
                "headline": props.get("headline", ""),
                "description": props.get("description", "")[:500],
                "sender": props.get("senderName", ""),
                "onset": props.get("onset", ""),
                "expires": props.get("expires", ""),
                "area": props.get("areaDesc", ""),
                "lat": lat,
                "lon": lon,
                "geometry": geom,
            })
        latest_data["weather_alerts"] = alerts
        logger.info(f"Fetched {len(alerts)} NWS weather alerts (Moderate+)")
    except Exception as e:
        logger.error(f"Error fetching weather alerts: {e}")


def fetch_natural_events():
    """NASA EONET — wildfires, volcanoes, storms, floods, icebergs worldwide."""
    try:
        resp = fetch_with_curl("https://eonet.gsfc.nasa.gov/api/v3/events/geojson?status=open&days=7",
                               timeout=15)
        resp.raise_for_status()
        data = resp.json()
        events = []
        for feat in data.get("features", []):
            props = feat.get("properties", {})
            geom = feat.get("geometry", {})
            coords = geom.get("coordinates", [])
            if geom.get("type") == "Point" and len(coords) >= 2:
                lon, lat = coords[0], coords[1]
            else:
                continue
            cats = props.get("categories", [])
            category = cats[0].get("title", "Unknown") if cats else "Unknown"
            events.append({
                "id": props.get("id", ""),
                "title": props.get("title", ""),
                "category": category,
                "category_id": cats[0].get("id", "") if cats else "",
                "lat": lat,
                "lon": lon,
                "date": props.get("date", ""),
            })
        latest_data["natural_events"] = events
        logger.info(f"Fetched {len(events)} NASA EONET events")
    except Exception as e:
        logger.error(f"Error fetching EONET events: {e}")


def fetch_military_bases():
    """Static dataset — worldwide military installations from DoD + David Vine dataset."""
    if latest_data.get("military_bases"):
        return  # Only fetch once (static data)
    try:
        bases = []
        # David Vine's "Base Nation" dataset — US foreign military bases
        for url, btype in [
            ("https://gist.githubusercontent.com/Fil/780eb92d6071d96343decebc77013ed1/raw/bases.csv", "Major Base"),
            ("https://gist.githubusercontent.com/Fil/780eb92d6071d96343decebc77013ed1/raw/lilypads.csv", "Lily Pad"),
        ]:
            try:
                resp = requests.get(url, timeout=15)
                if resp.status_code == 200:
                    reader = csv.DictReader(io.StringIO(resp.text))
                    for row in reader:
                        lat = float(row.get("lat", 0) or 0)
                        lon = float(row.get("lon", 0) or 0)
                        if lat == 0 and lon == 0:
                            continue
                        bases.append({
                            "id": f"mil-{row.get('name','')}-{row.get('country','')}",
                            "name": row.get("name", "Unknown Base"),
                            "country": row.get("country", ""),
                            "lat": lat,
                            "lon": lon,
                            "base_type": btype,
                            "branch": "US DoD",
                            "notes": row.get("notes", ""),
                        })
            except Exception:
                pass
        # ArcGIS DoD installations (US + overseas)
        try:
            resp = requests.get(
                "https://services.arcgis.com/xOi1kZaI0eWDREZv/arcgis/rest/services/NTAD_Military_Bases/FeatureServer/0/query?where=1%3D1&outFields=siteName,countryName,stateNameCode,siteReportingComponent,siteOperationalStatus&f=geojson&resultRecordCount=2000",
                timeout=20
            )
            if resp.status_code == 200:
                data = resp.json()
                for feat in data.get("features", []):
                    props = feat.get("properties", {})
                    geom = feat.get("geometry", {})
                    coords = geom.get("coordinates", [])
                    # MultiPolygon — extract centroid
                    if geom.get("type") == "MultiPolygon" and coords:
                        ring = coords[0][0] if coords[0] else []
                        if ring:
                            lon = sum(c[0] for c in ring) / len(ring)
                            lat = sum(c[1] for c in ring) / len(ring)
                        else:
                            continue
                    elif geom.get("type") == "Polygon" and coords:
                        ring = coords[0] if coords else []
                        if ring:
                            lon = sum(c[0] for c in ring) / len(ring)
                            lat = sum(c[1] for c in ring) / len(ring)
                        else:
                            continue
                    elif geom.get("type") == "Point" and len(coords) >= 2:
                        lon, lat = coords[0], coords[1]
                    else:
                        continue
                    name = props.get("siteName", "")
                    # Deduplicate against existing bases
                    if any(b["name"] == name for b in bases):
                        continue
                    bases.append({
                        "id": f"dod-{name}",
                        "name": name,
                        "country": props.get("countryName", "US"),
                        "lat": lat,
                        "lon": lon,
                        "base_type": "Installation",
                        "branch": props.get("siteReportingComponent", ""),
                        "notes": props.get("siteOperationalStatus", ""),
                    })
        except Exception:
            pass
        latest_data["military_bases"] = bases
        logger.info(f"Fetched {len(bases)} military bases")
    except Exception as e:
        logger.error(f"Error fetching military bases: {e}")


def fetch_nuclear_facilities():
    """Static dataset — worldwide nuclear power plants from GeoNuclearData."""
    if latest_data.get("nuclear_facilities"):
        return  # Only fetch once
    try:
        facilities = []
        resp = requests.get(
            "https://raw.githubusercontent.com/cristianst85/GeoNuclearData/master/data/csv/denormalized/nuclear_power_plants.csv",
            timeout=15
        )
        if resp.status_code == 200:
            reader = csv.DictReader(io.StringIO(resp.text))
            for row in reader:
                lat = float(row.get("Latitude", 0) or 0)
                lon = float(row.get("Longitude", 0) or 0)
                if lat == 0 and lon == 0:
                    continue
                facilities.append({
                    "id": f"nuke-{row.get('Id','')}",
                    "name": row.get("Name", "Unknown"),
                    "country": row.get("Country", ""),
                    "lat": lat,
                    "lon": lon,
                    "status": row.get("Status", ""),
                    "reactor_type": row.get("ReactorType", ""),
                    "reactor_model": row.get("ReactorModel", ""),
                    "capacity_mw": row.get("Capacity", ""),
                    "operational_from": row.get("OperationalFrom", ""),
                    "iaea_id": row.get("IAEAId", ""),
                })
        latest_data["nuclear_facilities"] = facilities
        logger.info(f"Fetched {len(facilities)} nuclear facilities")
    except Exception as e:
        logger.error(f"Error fetching nuclear facilities: {e}")


def fetch_submarine_cables():
    """Static dataset — submarine cables and landing points from TeleGeography."""
    if latest_data.get("submarine_cables"):
        return  # Only fetch once
    try:
        cables = []
        landing_points = []
        # Cable routes
        try:
            resp = requests.get("https://www.submarinecablemap.com/api/v3/cable/cable-geo.json", timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                for feat in data.get("features", []):
                    props = feat.get("properties", {})
                    geom = feat.get("geometry", {})
                    cables.append({
                        "id": props.get("id", ""),
                        "name": props.get("name", ""),
                        "color": props.get("color", "#3b82f6"),
                        "geometry": geom,
                    })
        except Exception:
            pass
        # Landing points
        try:
            resp2 = requests.get("https://www.submarinecablemap.com/api/v3/landing-point/landing-point-geo.json", timeout=15)
            if resp2.status_code == 200:
                data2 = resp2.json()
                for feat in data2.get("features", []):
                    props = feat.get("properties", {})
                    geom = feat.get("geometry", {})
                    coords = geom.get("coordinates", [])
                    if len(coords) >= 2:
                        landing_points.append({
                            "id": props.get("id", ""),
                            "name": props.get("name", ""),
                            "lat": coords[1],
                            "lon": coords[0],
                        })
        except Exception:
            pass
        latest_data["submarine_cables"] = cables
        latest_data["cable_landing_points"] = landing_points
        logger.info(f"Fetched {len(cables)} submarine cables, {len(landing_points)} landing points")
    except Exception as e:
        logger.error(f"Error fetching submarine cables: {e}")


def fetch_embassies():
    """Static dataset — worldwide embassies and consulates."""
    if latest_data.get("embassies"):
        return  # Only fetch once
    try:
        embassies = []
        resp = requests.get(
            "https://raw.githubusercontent.com/database-of-embassies/database-of-embassies/master/database_of_embassies.csv",
            timeout=20
        )
        if resp.status_code == 200:
            reader = csv.DictReader(io.StringIO(resp.text), delimiter=';')
            for row in reader:
                lat = float(row.get("latitude", 0) or 0)
                lon = float(row.get("longitude", 0) or 0)
                if lat == 0 and lon == 0:
                    continue
                embassies.append({
                    "id": f"emb-{row.get('QID','')}",
                    "name": row.get("operator", "Unknown"),
                    "country": row.get("country", ""),
                    "city": row.get("city", ""),
                    "lat": lat,
                    "lon": lon,
                    "type": row.get("type", "Embassy"),
                    "jurisdiction": row.get("jurisdictions", ""),
                    "address": row.get("address", ""),
                })
        # Trim fields to save bandwidth
        for e in embassies:
            e.pop("address", None)
            e["jurisdiction"] = (e.get("jurisdiction") or "")[:40]
        latest_data["embassies"] = embassies
        logger.info(f"Fetched {len(embassies)} embassies/consulates")
    except Exception as e:
        logger.error(f"Error fetching embassies: {e}")


def fetch_volcanoes():
    """Smithsonian GVP — all Holocene volcanoes worldwide via GeoServer WFS."""
    if latest_data.get("volcanoes"):
        return  # Static data, fetch once
    try:
        volcanoes = []
        resp = requests.get(
            "https://webservices.volcano.si.edu/geoserver/GVP-VOTW/wfs?service=WFS&version=1.0.0&request=GetFeature&typeName=GVP-VOTW:Smithsonian_VOTW_Holocene_Volcanoes&outputFormat=application%2Fjson&maxFeatures=2000",
            timeout=20
        )
        if resp.status_code == 200:
            data = resp.json()
            for feat in data.get("features", []):
                props = feat.get("properties", {})
                geom = feat.get("geometry", {})
                coords = geom.get("coordinates", [])
                if len(coords) < 2:
                    continue
                volcanoes.append({
                    "id": f"vol-{props.get('Volcano_Number','')}",
                    "name": props.get("Volcano_Name", ""),
                    "country": props.get("Country", ""),
                    "region": props.get("Region", ""),
                    "lat": coords[1],
                    "lon": coords[0],
                    "elevation": props.get("Elevation", 0),
                    "type": props.get("Primary_Volcano_Type", ""),
                    "last_eruption": props.get("Last_Eruption_Year", ""),
                    "tectonic": props.get("Tectonic_Setting", ""),
                    "rock_type": props.get("Major_Rock_Type", ""),
                })
        latest_data["volcanoes"] = volcanoes
        logger.info(f"Fetched {len(volcanoes)} volcanoes")
    except Exception as e:
        logger.error(f"Error fetching volcanoes: {e}")


def fetch_piracy_incidents():
    """NGA ASAM — Anti-Shipping Activity Messages (piracy, armed robbery at sea)."""
    try:
        # Fetch recent incidents (last 2 years)
        resp = requests.get(
            "https://services9.arcgis.com/RHVPKKiFTONKtxq3/arcgis/rest/services/ASAM_events_V1/FeatureServer/0/query?where=1%3D1&outFields=*&f=geojson&resultRecordCount=500&orderByFields=dateofocc+DESC",
            timeout=20
        )
        incidents = []
        if resp.status_code == 200:
            data = resp.json()
            for feat in data.get("features", []):
                props = feat.get("properties", {})
                geom = feat.get("geometry", {})
                coords = geom.get("coordinates", [])
                if len(coords) < 2:
                    continue
                # Parse date (epoch ms)
                date_val = props.get("dateofocc", 0)
                date_str = ""
                if date_val and isinstance(date_val, (int, float)):
                    try:
                        date_str = datetime.utcfromtimestamp(date_val / 1000).strftime("%Y-%m-%d")
                    except Exception:
                        pass
                elif isinstance(date_val, str):
                    date_str = date_val[:10]
                incidents.append({
                    "id": f"asam-{props.get('OBJECTID','')}",
                    "reference": props.get("reference", ""),
                    "date": date_str,
                    "lat": coords[1],
                    "lon": coords[0],
                    "subregion": props.get("subreg", ""),
                    "hostility": props.get("hostility_d", props.get("hostilitytype_l", "")),
                    "victim": props.get("victim_d", props.get("victim_l", "")),
                    "description": (props.get("description", "") or "")[:200],
                    "navarea": props.get("navarea", ""),
                })
        latest_data["piracy_incidents"] = incidents
        logger.info(f"Fetched {len(incidents)} piracy/ASAM incidents")
    except Exception as e:
        logger.error(f"Error fetching piracy incidents: {e}")


_BORDER_PORT_COORDS = {
    "San Ysidro": (32.5422, -117.0292), "Otay Mesa": (32.5539, -116.9381),
    "Calexico": (32.6742, -115.4994), "Calexico East": (32.6773, -115.4527),
    "Tecate": (32.5731, -116.6267), "Andrade": (32.7193, -114.7270),
    "Lukeville": (31.8780, -112.8148), "Sasabe": (31.4836, -111.5424),
    "Nogales": (31.3356, -110.9384), "Naco": (31.3361, -109.9483),
    "Douglas": (31.3332, -109.5471), "Columbus": (31.8277, -107.6388),
    "Santa Teresa": (31.8587, -106.6410), "El Paso": (31.7587, -106.4870),
    "Ysleta": (31.6920, -106.3017), "Presidio": (29.5607, -104.3521),
    "Del Rio": (29.3708, -100.8963), "Eagle Pass": (28.7091, -100.4995),
    "Laredo": (27.5036, -99.5075), "Roma": (26.4050, -99.0138),
    "Rio Grande City": (26.3798, -98.8221), "Hidalgo": (26.1004, -98.2631),
    "Progreso": (26.0622, -97.9575), "Brownsville": (25.9017, -97.4975),
    "Los Tomates": (25.9600, -97.4850), "B&M Bridge": (25.9950, -97.1540),
    "Madawaska": (47.3586, -68.3323), "Fort Kent": (47.2586, -68.5926),
    "Jackman": (45.6304, -70.2618), "Houlton": (46.1219, -67.8411),
    "Calais": (45.1853, -67.2764), "Highgate Springs": (44.9901, -73.1024),
    "Derby Line": (44.9920, -72.0977), "Norton": (44.9928, -71.7957),
    "Champlain": (44.9861, -73.4498), "Massena": (44.9263, -74.8919),
    "Ogdensburg": (44.7003, -75.4865), "Alexandria Bay": (44.3324, -75.8839),
    "Cape Vincent": (44.1272, -76.3346), "Lewiston Bridge": (43.1710, -79.0440),
    "Peace Bridge": (42.9064, -78.9025), "Rainbow Bridge": (43.0870, -79.0660),
    "Buffalo": (42.8864, -78.8784), "Niagara Falls": (43.0962, -79.0377),
    "Detroit": (42.3118, -83.0456), "Port Huron": (42.9993, -82.4249),
    "Sault Ste Marie": (46.5137, -84.3480), "International Falls": (48.6016, -93.4113),
    "Grand Portage": (47.9631, -89.6835), "Warroad": (48.9053, -95.3214),
    "Pembina": (48.9665, -97.2434), "Portal": (48.9999, -102.5549),
    "Sweetgrass": (48.9990, -111.9645), "Roosville": (48.9976, -115.0599),
    "Eastport": (48.9992, -116.1818), "Blaine": (49.0016, -122.7563),
    "Lynden": (48.9997, -122.4627), "Sumas": (49.0003, -122.2634),
    "Oroville": (48.9996, -119.4341), "Point Roberts": (48.9860, -123.0720),
}

def fetch_border_crossings():
    """US CBP — border crossing wait times at every port of entry."""
    try:
        resp = requests.get("https://bwt.cbp.gov/api/bwtnew", timeout=15,
                            headers={"User-Agent": "ShadowLens/1.0"})
        crossings = []
        if resp.status_code == 200:
            data = resp.json()
            for port in data:
                name = port.get("port_name", "")
                crossing = port.get("crossing_name", "")
                border = port.get("border", "")
                status = port.get("port_status", "")
                # Extract passenger vehicle wait times
                passenger = port.get("passenger_vehicle_lanes", {}) or {}
                standard = passenger.get("standard_lanes", {}) or {}
                delay = int(standard.get("delay_minutes", 0) or 0)
                lanes = int(standard.get("lanes_open", 0) or 0)
                max_lanes = int(standard.get("maximum_lanes", 0) or 0)
                # Lookup coordinates from port name
                coords = None
                for pname, pcoords in _BORDER_PORT_COORDS.items():
                    if pname.lower() in name.lower():
                        coords = pcoords
                        break
                crossings.append({
                    "id": f"bwt-{port.get('port_number','')}",
                    "name": f"{name} — {crossing}" if crossing else name,
                    "border": border,
                    "status": status,
                    "delay_minutes": delay,
                    "lanes_open": lanes,
                    "max_lanes": max_lanes,
                    "update_time": port.get("update_time", ""),
                    "hours": port.get("hours", ""),
                    "lat": coords[0] if coords else None,
                    "lon": coords[1] if coords else None,
                })
        latest_data["border_crossings"] = crossings
        logger.info(f"Fetched {len(crossings)} border crossing wait times")
    except Exception as e:
        logger.error(f"Error fetching border crossings: {e}")


def fetch_cyber_threats():
    """abuse.ch Feodo Tracker + ThreatFox — active botnet C2 servers and IOCs."""
    try:
        threats = []
        # Feodo Tracker — active botnet C2 IPs
        try:
            resp = requests.get("https://feodotracker.abuse.ch/downloads/ipblocklist.json", timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                for entry in data[:200]:  # Cap at 200
                    ip = entry.get("ip_address", "")
                    country = entry.get("country", "")
                    coords = _ISO2_COUNTRY_COORDS.get(country) or _COUNTRY_COORDS.get(country.lower())
                    threats.append({
                        "id": f"feodo-{ip}",
                        "type": "botnet_c2",
                        "ip": ip,
                        "port": entry.get("port", ""),
                        "malware": entry.get("malware", ""),
                        "country": country,
                        "as_name": entry.get("as_name", ""),
                        "as_number": entry.get("as_number", ""),
                        "first_seen": entry.get("first_seen", ""),
                        "last_online": entry.get("last_online", ""),
                        "status": entry.get("status", ""),
                        "lat": coords[0] + (hash(ip) % 100 - 50) * 0.05 if coords else None,
                        "lon": coords[1] + (hash(ip) % 100 - 50) * 0.05 if coords else None,
                    })
        except Exception:
            pass
        # ThreatFox — recent IOCs (malware, C2, etc)
        try:
            resp2 = requests.get("https://threatfox.abuse.ch/export/json/recent/", timeout=15)
            if resp2.status_code == 200:
                data2 = resp2.json()
                for key, entries in list(data2.items())[:100]:
                    if not isinstance(entries, list):
                        continue
                    for entry in entries:
                        threats.append({
                            "id": f"threatfox-{entry.get('id','')}",
                            "type": entry.get("threat_type", ""),
                            "ip": entry.get("ioc_value", ""),
                            "port": "",
                            "malware": entry.get("malware_printable", ""),
                            "country": "",
                            "as_name": "",
                            "as_number": "",
                            "first_seen": entry.get("first_seen_utc", ""),
                            "last_online": entry.get("last_seen_utc", ""),
                            "status": str(entry.get("confidence_level", "")),
                        })
        except Exception:
            pass

        # Merge in live Check Point ThreatCloud attacks
        live_attacks = list(_checkpoint_attacks)  # thread-safe snapshot
        threats.extend(live_attacks)

        latest_data["cyber_threats"] = threats
        # Store live attack stats separately for the frontend
        latest_data["checkpoint_stats"] = dict(_checkpoint_stats)
        logger.info(f"Fetched {len(threats)} cyber threat indicators ({len(live_attacks)} live Check Point)")
    except Exception as e:
        logger.error(f"Error fetching cyber threats: {e}")


# ---------------------------------------------------------------------------
# Check Point ThreatCloud — real-time SSE attack feed
# ---------------------------------------------------------------------------
from collections import deque
_checkpoint_attacks: deque = deque(maxlen=500)  # Rolling buffer of recent live attacks
_checkpoint_stats: dict = {"today": 0, "trend": []}
_checkpoint_thread: threading.Thread | None = None


def _checkpoint_sse_consumer():
    """Background thread that connects to Check Point ThreatCloud SSE and
    maintains a rolling buffer of the most recent 500 live cyber attacks."""
    import sseclient  # type: ignore
    url = "https://threatmap-api.checkpoint.com/ThreatMap/api/feed"
    _attack_type_labels = {
        "exploit": "exploit",
        "malware": "malware",
        "phishing": "phishing",
    }
    _attack_counter = [0]  # mutable counter for unique IDs

    while True:
        try:
            logger.info("Connecting to Check Point ThreatCloud SSE feed...")
            resp = requests.get(url, stream=True, timeout=30, headers={
                "Accept": "text/event-stream",
                "User-Agent": "ShadowLens/1.0",
            })
            resp.raise_for_status()
            client = sseclient.SSEClient(resp)

            for event in client.events():
                try:
                    if event.event == "attack":
                        data = json.loads(event.data)
                        _attack_counter[0] += 1
                        src_co = data.get("s_co", "")
                        dst_co = data.get("d_co", "")
                        attack = {
                            "id": f"cp-{_attack_counter[0]}",
                            "type": _attack_type_labels.get(data.get("a_t", ""), data.get("a_t", "unknown")),
                            "attack_name": data.get("a_n", ""),
                            "attack_count": data.get("a_c", 1),
                            "source_country": src_co,
                            "source_lat": data.get("s_la"),
                            "source_lon": data.get("s_lo"),
                            "source_state": data.get("s_s", ""),
                            "dest_country": dst_co,
                            "dest_state": data.get("d_s", ""),
                            "ip": "",
                            "port": "",
                            "malware": data.get("a_n", "") if data.get("a_t") == "malware" else "",
                            "country": dst_co,
                            "as_name": "",
                            "as_number": "",
                            "first_seen": "",
                            "last_online": "",
                            "status": "live",
                            "source": "checkpoint",
                            # Geo coords: use destination as the primary position
                            "lat": data.get("d_la"),
                            "lon": data.get("d_lo"),
                            # Keep source coords for attack-arc rendering
                            "src_lat": data.get("s_la"),
                            "src_lon": data.get("s_lo"),
                        }
                        _checkpoint_attacks.append(attack)

                    elif event.event == "counter":
                        data = json.loads(event.data)
                        _checkpoint_stats["today"] = data.get("today", 0)
                        _checkpoint_stats["trend"] = data.get("recentPeriod", [])

                except (json.JSONDecodeError, KeyError):
                    continue

        except Exception as e:
            logger.warning(f"Check Point SSE connection lost: {e}. Reconnecting in 10s...")
            time.sleep(10)


def start_checkpoint_feed():
    """Start the Check Point ThreatCloud SSE consumer in a daemon thread."""
    global _checkpoint_thread
    if _checkpoint_thread and _checkpoint_thread.is_alive():
        return
    _checkpoint_thread = threading.Thread(target=_checkpoint_sse_consumer, daemon=True, name="checkpoint-sse")
    _checkpoint_thread.start()
    logger.info("Check Point ThreatCloud SSE feed started.")


_cell_tower_cache = {"data": None, "fetched_at": 0}

def fetch_cell_towers():
    """OpenCelliD — cell tower locations for RF coverage mapping.
    Caches for 24h to avoid burning the 5000/day API quota."""
    # Return cached data if fresh (24h TTL)
    if _cell_tower_cache["data"] is not None and (time.time() - _cell_tower_cache["fetched_at"]) < 86400:
        latest_data["cell_towers"] = _cell_tower_cache["data"]
        return

    api_key = os.environ.get("OPENCELLID_API_KEY", "")
    if not api_key:
        return
    try:
        towers = []
        seen_ids = set()
        # Use 0.018° bbox (~2km each side = 4 sq km, within API limit)
        d = 0.009
        regions = [
            # US major cities
            ("Nashville-DT", 36.162, -86.782), ("Nashville-E", 36.162, -86.732),
            ("DC-Pentagon", 38.871, -77.056), ("DC-Capitol", 38.890, -77.009),
            ("NYC-Midtown", 40.754, -73.984), ("NYC-WTC", 40.713, -74.013),
            ("LA-DT", 34.052, -118.243), ("Chicago-Loop", 41.882, -87.628),
            ("Houston-DT", 29.760, -95.370), ("SF-DT", 37.788, -122.408),
            ("Miami-DT", 25.776, -80.190), ("Seattle-DT", 47.606, -122.332),
            ("Denver-DT", 39.739, -104.990), ("Atlanta-DT", 33.749, -84.388),
            ("Dallas-DT", 32.780, -96.800), ("Boston-DT", 42.360, -71.058),
            # Military
            ("Norfolk Naval", 36.946, -76.313), ("San Diego Naval", 32.684, -117.149),
            ("Ft Liberty", 35.139, -79.006), ("Ft Cavazos", 31.134, -97.775),
            ("Ft Campbell", 36.628, -87.460), ("JB Andrews", 38.811, -76.867),
            ("Ramstein AB", 49.437, 7.600), ("Yokosuka", 35.283, 139.672),
            # International
            ("London-City", 51.508, -0.076), ("London-West", 51.502, -0.141),
            ("Seoul", 37.531, 126.980), ("Taipei", 25.034, 121.565),
            ("Dubai", 25.197, 55.274), ("Singapore", 1.290, 103.852),
            ("Tokyo-Shinjuku", 35.690, 139.700), ("Berlin-Mitte", 52.520, 13.405),
            ("Paris-Center", 48.857, 2.352), ("Sydney-CBD", -33.868, 151.207),
            ("Moscow-Center", 55.755, 37.618), ("Beijing-CBD", 39.908, 116.397),
        ]
        for name, lat, lon in regions:
            try:
                url = (f"https://opencellid.org/cell/getInArea?key={api_key}"
                       f"&BBOX={lat-d},{lon-d},{lat+d},{lon+d}&format=json&limit=200")
                resp = requests.get(url, timeout=10, headers={"User-Agent": "ShadowLens/1.0"})
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, dict) and data.get("error"):
                        logger.warning(f"OpenCelliD quota exceeded: {data['error']}")
                        break
                    cells = data.get("cells", data) if isinstance(data, dict) else data
                    if isinstance(cells, list):
                        for cell in cells:
                            clat = float(cell.get("lat", 0) or 0)
                            clon = float(cell.get("lon", 0) or 0)
                            cid = cell.get("cellid", cell.get("cell", ""))
                            if clat == 0 and clon == 0:
                                continue
                            if cid in seen_ids:
                                continue
                            seen_ids.add(cid)
                            towers.append({
                                "id": f"cell-{cid}",
                                "lat": clat, "lon": clon,
                                "radio": cell.get("radio", ""),
                                "mcc": cell.get("mcc", ""),
                                "mnc": cell.get("mnc", ""),
                                "range": int(cell.get("range", 0) or 0),
                                "samples": int(cell.get("samples", 0) or 0),
                                "region": name,
                            })
                elif resp.status_code == 403:
                    logger.warning(f"OpenCelliD API key rejected for {name}")
                    break
            except Exception:
                pass
        # If OpenCelliD returned nothing (quota exceeded), fall back to OSM Overpass
        if not towers:
            logger.info("OpenCelliD empty, falling back to OSM Overpass for cell towers...")
            towers = _fetch_cell_towers_osm()
        if towers:
            _cell_tower_cache["data"] = towers
            _cell_tower_cache["fetched_at"] = time.time()
        latest_data["cell_towers"] = towers
        logger.info(f"Fetched {len(towers)} cell towers")
    except Exception as e:
        logger.error(f"Error fetching cell towers: {e}")


def _fetch_cell_towers_osm():
    """Fallback: fetch cell tower/mast locations from OpenStreetMap via Overpass API."""
    overpass_url = "https://overpass-api.de/api/interpreter"
    # Query regions as bbox: (south,west,north,east)
    regions = [
        ("Nashville", "35.95,-87.05,36.35,-86.55"),
        ("DC", "38.8,-77.15,38.95,-76.9"),
        ("NYC", "40.65,-74.05,40.82,-73.9"),
        ("LA", "33.9,-118.4,34.15,-118.1"),
        ("Chicago", "41.75,-87.75,41.95,-87.55"),
        ("Houston", "29.65,-95.5,29.85,-95.25"),
        ("SF", "37.7,-122.5,37.85,-122.35"),
        ("Miami", "25.7,-80.3,25.85,-80.1"),
        ("Seattle", "47.5,-122.4,47.7,-122.25"),
        ("Denver", "39.65,-105.05,39.8,-104.9"),
        ("Atlanta", "33.65,-84.5,33.85,-84.3"),
        ("Dallas", "32.7,-96.9,32.85,-96.7"),
        ("London", "51.4,-0.2,51.6,0.0"),
        ("Seoul", "37.45,126.9,37.6,127.1"),
        ("Tokyo", "35.6,139.6,35.75,139.8"),
        ("Berlin", "52.45,13.3,52.6,13.5"),
        ("Paris", "48.8,2.25,48.9,2.4"),
        ("Sydney", "-33.95,151.1,-33.8,151.3"),
        ("Singapore", "1.25,103.75,1.35,103.9"),
        ("Dubai", "25.1,55.15,25.3,55.35"),
    ]
    all_towers = []
    seen = set()
    for name, bbox in regions:
        try:
            query = f'''[out:json][timeout:12];(
  node["man_made"="mast"]["tower:type"="communication"]({bbox});
  node["man_made"="tower"]["tower:type"="communication"]({bbox});
  node["communication:mobile_phone"="yes"]({bbox});
);out body 200;'''
            resp = requests.post(overpass_url, data={"data": query}, timeout=15)
            if resp.status_code == 200:
                elements = resp.json().get("elements", [])
                for el in elements:
                    nid = el.get("id")
                    if nid in seen:
                        continue
                    seen.add(nid)
                    lat = el.get("lat")
                    lon = el.get("lon")
                    if not lat or not lon:
                        continue
                    tags = el.get("tags", {})
                    radio = "LTE" if tags.get("communication:mobile_phone") == "yes" else ""
                    if not radio and tags.get("communication:radio") == "yes":
                        radio = "Radio"
                    all_towers.append({
                        "id": f"osm-{nid}",
                        "lat": lat, "lon": lon,
                        "radio": radio or "Cell",
                        "mcc": "", "mnc": "",
                        "range": 0, "samples": 0,
                        "region": name,
                        "name": tags.get("name", ""),
                        "operator": tags.get("operator", ""),
                        "height": tags.get("height", ""),
                    })
                logger.info(f"OSM cell towers {name}: {len(elements)} found")
            elif resp.status_code == 429:
                logger.warning("Overpass rate limited, stopping cell tower queries")
                break
        except Exception as e:
            logger.warning(f"OSM cell tower query failed for {name}: {e}")
    return all_towers


def fetch_reservoirs():
    """USGS Water Services — reservoir/lake levels across the US."""
    try:
        reservoirs = []
        # Fetch gage height for lakes across multiple states
        for state in ["TX", "CA", "TN", "FL", "OK", "AR", "KY", "AZ", "NV", "CO", "UT", "MT", "OR", "WA"]:
            try:
                resp = requests.get(
                    f"https://waterservices.usgs.gov/nwis/iv/?format=json&stateCd={state}&parameterCd=00065&siteType=LK&siteStatus=active",
                    headers={"User-Agent": "ShadowLens/1.0"},
                    timeout=10
                )
                if resp.status_code == 200:
                    data = resp.json()
                    for ts in data.get("value", {}).get("timeSeries", []):
                        src = ts.get("sourceInfo", {})
                        geo = src.get("geoLocation", {}).get("geogLocation", {})
                        lat = float(geo.get("latitude", 0) or 0)
                        lon = float(geo.get("longitude", 0) or 0)
                        if lat == 0 and lon == 0:
                            continue
                        vals = ts.get("values", [{}])[0].get("value", [])
                        if not vals:
                            continue
                        latest_val = vals[-1]
                        level = float(latest_val.get("value", 0) or 0)
                        reservoirs.append({
                            "id": f"usgs-{src.get('siteCode', [{}])[0].get('value', '')}",
                            "name": src.get("siteName", ""),
                            "state": state,
                            "lat": lat,
                            "lon": lon,
                            "level_ft": level,
                            "unit": "ft",
                            "updated": latest_val.get("dateTime", ""),
                        })
            except Exception:
                pass
        latest_data["reservoirs"] = reservoirs
        logger.info(f"Fetched {len(reservoirs)} reservoir/lake levels")
    except Exception as e:
        logger.error(f"Error fetching reservoirs: {e}")


# Shared country → coordinate mapping for geo-locating events by country name
_COUNTRY_COORDS = {
    "congo": (-4.0, 21.7), "nigeria": (9.08, 7.49), "india": (20.6, 78.9),
    "brazil": (-14.2, -51.9), "yemen": (15.5, 48.5), "syria": (34.8, 38.9),
    "somalia": (5.1, 46.2), "sudan": (15.5, 32.5), "ethiopia": (9.1, 40.5),
    "pakistan": (30.4, 69.3), "afghanistan": (33.9, 67.7), "indonesia": (-0.8, 113.9),
    "china": (35.9, 104.2), "iran": (32.4, 53.7), "iraq": (33.2, 43.7),
    "mexico": (23.6, -102.5), "mozambique": (-18.7, 35.5), "bangladesh": (23.7, 90.4),
    "uganda": (1.4, 32.3), "kenya": (-0.02, 37.9), "tanzania": (-6.4, 34.9),
    "egypt": (26.8, 30.8), "south africa": (-30.6, 22.9), "ghana": (7.9, -1.0),
    "cameroon": (7.4, 12.3), "mali": (17.6, -4.0), "chad": (15.5, 18.7),
    "niger": (17.6, 8.1), "guinea": (9.9, -9.7), "madagascar": (-18.8, 46.9),
    "haiti": (19.0, -72.1), "jordan": (30.6, 36.2), "lebanon": (33.8, 35.8),
    "myanmar": (21.9, 95.9), "thailand": (15.9, 100.9), "philippines": (12.9, 121.8),
    "vietnam": (14.1, 108.3), "japan": (36.2, 138.3), "korea": (35.9, 127.8),
    "turkey": (38.9, 35.2), "ukraine": (48.4, 31.2), "russia": (61.5, 105.3),
    "germany": (51.2, 10.4), "france": (46.2, 2.2), "italy": (41.9, 12.6),
    "spain": (40.5, -3.7), "uk": (55.4, -3.4), "united kingdom": (55.4, -3.4),
    "united states": (37.1, -95.7), "canada": (56.1, -106.3), "australia": (-25.3, 133.8),
    "colombia": (4.6, -74.3), "argentina": (-38.4, -63.6), "peru": (-9.2, -75.0),
    "chile": (-35.7, -71.5), "saudi arabia": (23.9, 45.1), "angola": (-11.2, 17.9),
    "israel": (31.0, 34.8), "palestine": (31.9, 35.2), "gaza": (31.5, 34.4),
    "libya": (26.3, 17.2), "tunisia": (33.9, 9.5), "morocco": (31.8, -7.1),
    "algeria": (28.0, 1.7), "venezuela": (-6.4, -66.6), "cuba": (21.5, -77.8),
    "north korea": (40.3, 127.5), "taiwan": (23.7, 121.0), "singapore": (1.35, 103.8),
    "malaysia": (4.2, 101.9), "nepal": (28.4, 84.1), "sri lanka": (7.9, 80.8),
    "poland": (51.9, 19.1), "romania": (45.9, 24.9), "hungary": (47.2, 19.5),
    "greece": (39.1, 21.8), "serbia": (44.0, 21.0), "croatia": (45.1, 15.2),
    "sweden": (60.1, 18.6), "norway": (60.5, 8.5), "finland": (61.9, 25.7),
    "denmark": (56.3, 9.5), "netherlands": (52.1, 5.3), "belgium": (50.5, 4.5),
    "austria": (47.5, 14.6), "switzerland": (46.8, 8.2), "portugal": (39.4, -8.2),
    "new zealand": (-40.9, 174.9), "south korea": (35.9, 127.8),
}

# ISO 3166-1 alpha-2 → _COUNTRY_COORDS lookup
_ISO2_COUNTRY_COORDS = {
    "US": (37.1, -95.7), "GB": (55.4, -3.4), "DE": (51.2, 10.4), "FR": (46.2, 2.2),
    "IT": (41.9, 12.6), "ES": (40.5, -3.7), "CA": (56.1, -106.3), "AU": (-25.3, 133.8),
    "JP": (36.2, 138.3), "CN": (35.9, 104.2), "RU": (61.5, 105.3), "IN": (20.6, 78.9),
    "BR": (-14.2, -51.9), "KR": (35.9, 127.8), "MX": (23.6, -102.5), "TR": (38.9, 35.2),
    "NL": (52.1, 5.3), "SE": (60.1, 18.6), "PL": (51.9, 19.1), "UA": (48.4, 31.2),
    "NO": (60.5, 8.5), "FI": (61.9, 25.7), "DK": (56.3, 9.5), "BE": (50.5, 4.5),
    "AT": (47.5, 14.6), "CH": (46.8, 8.2), "PT": (39.4, -8.2), "GR": (39.1, 21.8),
    "CZ": (49.8, 15.5), "RO": (45.9, 24.9), "HU": (47.2, 19.5), "IE": (53.1, -7.7),
    "SG": (1.35, 103.8), "HK": (22.3, 114.2), "TW": (23.7, 121.0), "TH": (15.9, 100.9),
    "VN": (14.1, 108.3), "PH": (12.9, 121.8), "MY": (4.2, 101.9), "ID": (-0.8, 113.9),
    "ZA": (-30.6, 22.9), "NG": (9.08, 7.49), "KE": (-0.02, 37.9), "EG": (26.8, 30.8),
    "SA": (23.9, 45.1), "AE": (23.4, 53.8), "IL": (31.0, 34.8), "IR": (32.4, 53.7),
    "PK": (30.4, 69.3), "BD": (23.7, 90.4), "CO": (4.6, -74.3), "AR": (-38.4, -63.6),
    "CL": (-35.7, -71.5), "PE": (-9.2, -75.0), "VE": (-6.4, -66.6), "NZ": (-40.9, 174.9),
    "BG": (42.7, 25.5), "HR": (45.1, 15.2), "RS": (44.0, 21.0), "SK": (48.7, 19.7),
    "LT": (55.2, 23.9), "LV": (56.9, 24.1), "EE": (58.6, 25.0), "SI": (46.2, 14.9),
    "LU": (49.8, 6.1), "IS": (64.9, -19.0), "CY": (35.1, 33.4), "MT": (35.9, 14.4),
    # Africa
    "BI": (-3.4, 29.9), "CF": (6.6, 20.9), "CM": (7.4, 12.4), "TD": (15.5, 18.7),
    "ET": (9.1, 40.5), "ML": (17.6, -4.0), "NE": (17.6, 8.1), "RW": (-1.9, 29.9),
    "SS": (6.9, 31.3), "GH": (7.9, -1.0), "TZ": (-6.4, 34.9), "UG": (1.4, 32.3),
    "SN": (14.5, -14.5), "CI": (7.5, -5.5), "MG": (-18.8, 46.9), "MZ": (-18.7, 35.5),
    "AO": (-11.2, 17.9), "CD": (-4.0, 21.8), "CG": (-0.2, 15.8), "GA": (-0.8, 11.6),
    "SO": (5.2, 46.2), "SD": (12.9, 30.2), "LY": (26.3, 17.2), "TN": (33.9, 9.5),
    "MA": (31.8, -7.1), "DZ": (28.0, 1.7), "GN": (9.9, -9.7), "BF": (12.2, -1.6),
    "SL": (8.5, -11.8), "LR": (6.4, -9.4), "ER": (15.2, 39.8), "DJ": (11.6, 43.1),
    "MW": (-13.3, 34.3), "ZM": (-13.1, 27.8), "ZW": (-19.0, 29.2), "BW": (-22.3, 24.7),
    "NA": (-22.6, 17.1), "SZ": (-26.5, 31.5), "LS": (-29.6, 28.2),
    # Americas
    "BO": (-16.3, -63.6), "PY": (-23.4, -58.4), "EC": (-1.8, -78.2), "UY": (-32.5, -55.8),
    "GY": (5.0, -58.9), "SR": (3.9, -56.0), "HN": (15.2, -86.2), "GT": (15.8, -90.2),
    "SV": (13.8, -88.9), "NI": (12.9, -85.2), "CR": (9.7, -83.8), "PA": (8.5, -80.8),
    "CU": (21.5, -77.8), "DO": (18.7, -70.2), "HT": (18.5, -72.3), "JM": (18.1, -77.3),
    "TT": (10.7, -61.2), "BB": (13.2, -59.5), "BS": (25.0, -77.4),
    # Pacific/Oceania
    "KI": (1.9, -157.5), "NR": (-0.5, 166.9), "FJ": (-17.7, 178.1), "PG": (-6.3, 143.9),
    "WS": (-13.8, -172.1), "TO": (-21.2, -175.2), "VU": (-15.4, 166.9),
    # Asia
    "AF": (33.9, 67.7), "IQ": (33.2, 43.7), "SY": (34.8, 38.9), "JO": (30.6, 36.2),
    "LB": (33.9, 35.9), "KW": (29.3, 47.5), "QA": (25.4, 51.2), "BH": (26.0, 50.6),
    "OM": (21.5, 55.9), "YE": (15.6, 48.5), "MM": (21.9, 95.9), "KH": (12.6, 104.9),
    "LA": (19.9, 102.5), "NP": (28.4, 84.1), "LK": (7.9, 80.8), "UZ": (41.4, 64.6),
    "KZ": (48.0, 68.0), "TM": (38.9, 59.6), "KG": (41.2, 74.8), "TJ": (38.9, 71.3),
    "MN": (46.9, 103.8), "GE": (42.3, 43.4), "AM": (40.1, 45.0), "AZ": (40.1, 47.6),
}

def fetch_acled_conflicts():
    """ACLED-style conflict events — protests, riots, battles, explosions worldwide.
    Uses multiple open sources: GDACS, ReliefWeb, RSOE EDIS, USGS hazards."""
    try:
        events = []

        # 1. GDACS — Global Disaster Alerts (full GeoJSON endpoint, not RSS)
        try:
            resp = requests.get(
                "https://www.gdacs.org/gdacsapi/api/events/geteventlist/MAP",
                timeout=20, headers={"Accept": "application/json", "User-Agent": "ShadowLens/1.0"}
            )
            if resp.status_code == 200:
                data = resp.json()
                for feat in data.get("features", []):
                    props = feat.get("properties", {})
                    geom = feat.get("geometry", {})
                    coords = geom.get("coordinates", [])
                    if not coords or len(coords) < 2:
                        continue
                    lon, lat = float(coords[0]), float(coords[1])
                    events.append({
                        "id": f"gdacs-{props.get('eventid', '')}",
                        "title": props.get("name", props.get("htmldescription", "")[:100]),
                        "event_type": props.get("eventtype", ""),
                        "severity": props.get("alertlevel", ""),
                        "country": props.get("country", ""),
                        "lat": lat, "lon": lon,
                        "date": props.get("fromdate", ""),
                        "source": "GDACS",
                        "url": props.get("url", {}).get("report", "") if isinstance(props.get("url"), dict) else "",
                        "description": (props.get("description", "") or "")[:300],
                        "media_url": props.get("icon", ""),
                        "media_type": "icon",
                    })
                logger.info(f"GDACS map API: {len([e for e in events if e['source'] == 'GDACS'])} events")
        except Exception as e:
            logger.warning(f"GDACS map API failed: {e}")

        # 2. ReliefWeb — UN humanitarian crises & disasters
        try:
            resp = requests.get(
                "https://api.reliefweb.int/v1/disasters?appname=shadowlens&limit=100&preset=latest&fields[include][]=name&fields[include][]=country.name&fields[include][]=type.name&fields[include][]=date.event&fields[include][]=url&fields[include][]=primary_country.location",
                timeout=15
            )
            if resp.status_code == 200:
                data = resp.json()
                for item in data.get("data", []):
                    fields = item.get("fields", {})
                    loc = fields.get("primary_country", {}).get("location", {})
                    lat = loc.get("lat")
                    lon = loc.get("lon")
                    if not lat or not lon:
                        continue
                    countries = fields.get("country", [])
                    country_name = countries[0].get("name", "") if countries else ""
                    types = fields.get("type", [])
                    type_name = types[0].get("name", "") if types else ""
                    events.append({
                        "id": f"rw-{item.get('id', '')}",
                        "title": fields.get("name", ""),
                        "event_type": type_name,
                        "severity": "humanitarian",
                        "country": country_name,
                        "lat": float(lat), "lon": float(lon),
                        "date": (fields.get("date", {}).get("event", "") or "")[:10],
                        "source": "ReliefWeb",
                        "url": fields.get("url", ""),
                        "description": "",
                        "media_url": "", "media_type": "",
                    })
                logger.info(f"ReliefWeb: {len([e for e in events if e['source'] == 'ReliefWeb'])} disasters")
        except Exception as e:
            logger.warning(f"ReliefWeb API failed: {e}")

        # 3. WHO Disease Outbreak News — disease outbreaks worldwide
        try:
            resp = requests.get(
                "https://www.who.int/feeds/entity/don/en/rss.xml",
                timeout=15, headers={"User-Agent": "ShadowLens/1.0"}
            )
            if resp.status_code == 200:
                import feedparser as fp
                feed = fp.parse(resp.text)
                # WHO entries don't have coords — map by country name in title
                for entry in feed.entries[:20]:
                    title = entry.get("title", "")
                    link = entry.get("link", "")
                    pub = entry.get("published", "")
                    title_lower = title.lower()
                    lat, lon = None, None
                    for kw, (klat, klon) in _COUNTRY_COORDS.items():
                        if kw in title_lower:
                            lat, lon = klat, klon
                            break
                    if lat is None:
                        continue
                    events.append({
                        "id": f"who-{hash(title) % 100000}",
                        "title": title,
                        "event_type": "Disease Outbreak",
                        "severity": "health_emergency",
                        "country": "",
                        "lat": lat, "lon": lon,
                        "date": pub[:10] if pub else "",
                        "source": "WHO",
                        "url": link,
                        "description": entry.get("summary", "")[:300],
                        "media_url": "", "media_type": "",
                    })
                logger.info(f"WHO DON: {len([e for e in events if e['source'] == 'WHO'])} outbreaks")
        except Exception as e:
            logger.warning(f"WHO DON feed failed: {e}")

        # 4. RSOE EDIS — Emergency & Disaster Information Service
        try:
            resp = requests.get(
                "https://rsoe-edis.org/eventApi/jsonAjax.php",
                timeout=15, headers={"User-Agent": "Mozilla/5.0"}
            )
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list):
                    for item in data[:300]:
                        lat = float(item.get("lat", 0) or 0)
                        lon = float(item.get("lon", item.get("lng", 0)) or 0)
                        if lat == 0 and lon == 0:
                            continue
                        events.append({
                            "id": f"edis-{item.get('id', '')}",
                            "title": item.get("title", item.get("name", "")),
                            "event_type": item.get("cat", item.get("type", "")),
                            "severity": item.get("level", ""),
                            "country": item.get("country", ""),
                            "lat": lat, "lon": lon,
                            "date": item.get("date", ""),
                            "source": "RSOE-EDIS",
                            "url": item.get("link", ""),
                            "description": (item.get("desc", item.get("description", "")) or "")[:300],
                            "media_url": "", "media_type": "",
                        })
                logger.info(f"RSOE EDIS: {len([e for e in events if e['source'] == 'RSOE-EDIS'])} incidents")
        except Exception as e:
            logger.warning(f"RSOE EDIS failed: {e}")

        # 5. Global Incident Map (GIM) — terrorism, bio, cyber, forest fires
        try:
            for feed_url, category in [
                ("https://www.globalincidentmap.com/map/ilng-rss", "Terrorism"),
                ("https://www.globalincidentmap.com/map/displayIncidents/rss", "WMD/Bio"),
            ]:
                try:
                    resp = requests.get(feed_url, timeout=10, headers={"User-Agent": "ShadowLens/1.0"})
                    if resp.status_code == 200:
                        import feedparser as fp2
                        feed = fp2.parse(resp.text)
                        for entry in feed.entries[:30]:
                            lat, lon = None, None
                            if hasattr(entry, "geo_lat") and hasattr(entry, "geo_long"):
                                lat, lon = float(entry.geo_lat), float(entry.geo_long)
                            elif "georss_point" in entry:
                                pts = entry.georss_point.split()
                                if len(pts) == 2:
                                    lat, lon = float(pts[0]), float(pts[1])
                            if lat is None:
                                continue
                            events.append({
                                "id": f"gim-{hash(entry.get('title','')) % 100000}",
                                "title": entry.get("title", ""),
                                "event_type": category,
                                "severity": "alert",
                                "country": "",
                                "lat": lat, "lon": lon,
                                "date": entry.get("published", "")[:10],
                                "source": "GIM",
                                "url": entry.get("link", ""),
                                "description": entry.get("summary", "")[:300],
                                "media_url": "", "media_type": "",
                            })
                except Exception:
                    pass
        except Exception as e:
            logger.warning(f"GIM feeds failed: {e}")

        # 6. Amnesty International — urgent actions & crisis reports
        try:
            resp = requests.get(
                "https://www.amnesty.org/en/feed/",
                timeout=15, headers={"User-Agent": "ShadowLens/1.0"}
            )
            if resp.status_code == 200:
                import feedparser as fp3
                feed = fp3.parse(resp.text)
                # Reuse _COUNTRY_COORDS for country mapping
                for entry in feed.entries[:15]:
                    title = entry.get("title", "")
                    title_lower = title.lower()
                    lat, lon = None, None
                    for kw, (klat, klon) in _COUNTRY_COORDS.items():
                        if kw in title_lower:
                            lat, lon = klat, klon
                            break
                    if lat is None:
                        continue
                    events.append({
                        "id": f"amnesty-{hash(title) % 100000}",
                        "title": title,
                        "event_type": "Human Rights",
                        "severity": "crisis",
                        "country": "",
                        "lat": lat, "lon": lon,
                        "date": entry.get("published", "")[:10],
                        "source": "Amnesty",
                        "url": entry.get("link", ""),
                        "description": entry.get("summary", "")[:300],
                        "media_url": "", "media_type": "",
                    })
        except Exception as e:
            logger.warning(f"Amnesty feed failed: {e}")

        # 7. UNOSAT Rapid Mapping — satellite-confirmed disaster zones
        try:
            resp = requests.get(
                "https://unosat.org/products/feed",
                timeout=15, headers={"User-Agent": "ShadowLens/1.0"}
            )
            if resp.status_code == 200:
                import feedparser as fp4
                feed = fp4.parse(resp.text)
                for entry in feed.entries[:20]:
                    title = entry.get("title", "")
                    title_lower = title.lower()
                    lat, lon = None, None
                    if "georss_point" in entry:
                        pts = entry.georss_point.split()
                        if len(pts) == 2:
                            lat, lon = float(pts[0]), float(pts[1])
                    if lat is None:
                        for kw, (klat, klon) in _COUNTRY_COORDS.items():
                            if kw in title_lower:
                                lat, lon = klat, klon
                                break
                    if lat is None:
                        continue
                    events.append({
                        "id": f"unosat-{hash(title) % 100000}",
                        "title": title,
                        "event_type": "Satellite Assessment",
                        "severity": "confirmed",
                        "country": "",
                        "lat": lat, "lon": lon,
                        "date": entry.get("published", "")[:10],
                        "source": "UNOSAT",
                        "url": entry.get("link", ""),
                        "description": entry.get("summary", "")[:300],
                        "media_url": "", "media_type": "",
                    })
        except Exception as e:
            logger.warning(f"UNOSAT feed failed: {e}")

        # 8. FEMA IPAWS — Integrated Public Alert and Warning System
        try:
            resp = requests.get(
                "https://api.fema.gov/openapi/v1/IpawsArchivedAlerts?$top=100&$orderby=sent%20desc&$filter=sent%20ge%20%27" +
                (datetime.utcnow().strftime('%Y-%m-%dT00:00:00') + "%27"),
                timeout=15
            )
            if resp.status_code == 200:
                data = resp.json()
                for item in data.get("IpawsArchivedAlerts", []):
                    lat = float(item.get("latitude", 0) or 0)
                    lon = float(item.get("longitude", 0) or 0)
                    if lat == 0 and lon == 0:
                        # Parse from polygon
                        polygon = item.get("polygon", "")
                        if polygon:
                            try:
                                pts = polygon.split()
                                lats = [float(p.split(",")[0]) for p in pts if "," in p]
                                lons = [float(p.split(",")[1]) for p in pts if "," in p]
                                if lats and lons:
                                    lat, lon = sum(lats) / len(lats), sum(lons) / len(lons)
                            except Exception:
                                pass
                    if lat == 0 and lon == 0:
                        continue
                    events.append({
                        "id": f"fema-{item.get('id', '')}",
                        "title": item.get("headline", item.get("event", "")),
                        "event_type": item.get("event", "Alert"),
                        "severity": item.get("severity", ""),
                        "country": "US",
                        "lat": lat, "lon": lon,
                        "date": (item.get("sent", "") or "")[:10],
                        "source": "FEMA",
                        "url": "",
                        "description": (item.get("description", "") or "")[:300],
                        "media_url": "", "media_type": "",
                    })
                logger.info(f"FEMA IPAWS: {len([e for e in events if e['source'] == 'FEMA'])} alerts")
        except Exception as e:
            logger.warning(f"FEMA IPAWS failed: {e}")

        # 9. EMSC — European Mediterranean Seismological Centre (felt earthquakes only)
        try:
            resp = requests.get(
                "https://www.seismicportal.eu/fdsnws/event/1/query?format=json&limit=100&minmag=4.0&orderby=time",
                timeout=15
            )
            if resp.status_code == 200:
                data = resp.json()
                for feat in data.get("features", []):
                    props = feat.get("properties", {})
                    geom = feat.get("geometry", {})
                    coords = geom.get("coordinates", [])
                    if len(coords) < 2:
                        continue
                    events.append({
                        "id": f"emsc-{props.get('source_id', '')}",
                        "title": f"M{props.get('mag', '?')} {props.get('flynn_region', '')}",
                        "event_type": "Earthquake",
                        "severity": "seismic",
                        "country": props.get("flynn_region", ""),
                        "lat": float(coords[1]), "lon": float(coords[0]),
                        "date": (props.get("time", "") or "")[:10],
                        "source": "EMSC",
                        "url": props.get("unid", ""),
                        "description": f"Magnitude {props.get('mag', '?')} at {props.get('depth', '?')}km depth",
                        "media_url": "", "media_type": "",
                    })
        except Exception as e:
            logger.warning(f"EMSC failed: {e}")

        # 10. NOAA Storm Events
        try:
            resp = requests.get(
                "https://www.spc.noaa.gov/products/outlook/day1otlk_cat.lyr.geojson",
                timeout=15
            )
            if resp.status_code == 200:
                data = resp.json()
                for feat in data.get("features", []):
                    props = feat.get("properties", {})
                    geom = feat.get("geometry", {})
                    # Calculate centroid from polygon
                    if geom.get("type") in ("Polygon", "MultiPolygon"):
                        try:
                            if geom["type"] == "Polygon":
                                ring = geom["coordinates"][0]
                            else:
                                ring = geom["coordinates"][0][0]
                            lat = sum(c[1] for c in ring) / len(ring)
                            lon = sum(c[0] for c in ring) / len(ring)
                            events.append({
                                "id": f"spc-{hash(str(props)) % 100000}",
                                "title": f"Severe Weather Outlook: {props.get('LABEL', props.get('dn', ''))}",
                                "event_type": "Severe Weather",
                                "severity": props.get("LABEL", ""),
                                "country": "US",
                                "lat": lat, "lon": lon,
                                "date": datetime.utcnow().strftime("%Y-%m-%d"),
                                "source": "SPC/NOAA",
                                "url": "https://www.spc.noaa.gov",
                                "description": f"Convective outlook category: {props.get('LABEL', '')}",
                                "media_url": "", "media_type": "",
                            })
                        except Exception:
                            pass
        except Exception as e:
            logger.warning(f"SPC NOAA failed: {e}")

        latest_data["global_events"] = events
        logger.info(f"Total global events aggregated: {len(events)} from multiple sources")
    except Exception as e:
        logger.error(f"Error fetching global events: {e}")


def fetch_social_media_osint():
    """Social media OSINT — geotagged posts, images, and videos from public feeds."""
    try:
        posts = []

        # 1. Reddit — geotagged crisis/event subreddits (public JSON API, no auth needed)
        crisis_subs = [
            # Breaking / World
            "worldnews", "breakingnews", "news", "geopolitics", "IntelligenceNews",
            # Conflict / Military
            "CombatFootage", "UkraineWarVideoReport", "MiddleEastNews",
            "CredibleDefense", "WarCollege", "syriancivilwar", "IsraelPalestine",
            # Natural Disasters
            "NaturalDisasters", "weather", "tornado", "TropicalWeather",
            "Earthquakes", "wildfire", "VolcanoPorn", "hurricane",
            # Civil Unrest / Protests
            "Protests", "PublicFreakout", "ActualPublicFreakouts",
            # Cyber / Tech / Security
            "netsec", "cybersecurity", "hacking", "DataHoarder",
            # OSINT / Intelligence
            "OSINT", "Intelligence", "foreignpolicy",
            # Regional crisis
            "africa", "LatinAmerica", "asia", "europe", "China",
        ]
        for sub in crisis_subs:
            try:
                resp = requests.get(
                    f"https://www.reddit.com/r/{sub}/hot.json?limit=10",
                    timeout=8,
                    headers={"User-Agent": "ShadowLens:osint:v1.0 (research)"}
                )
                if resp.status_code == 200:
                    data = resp.json()
                    for child in data.get("data", {}).get("children", []):
                        post = child.get("data", {})
                        title = post.get("title", "")
                        # Get media URLs
                        media_url = ""
                        media_type = ""
                        thumbnail = post.get("thumbnail", "")
                        if thumbnail and thumbnail.startswith("http"):
                            media_url = thumbnail
                            media_type = "image"
                        # Check for video
                        if post.get("is_video"):
                            reddit_video = post.get("media", {})
                            if isinstance(reddit_video, dict):
                                rv = reddit_video.get("reddit_video", {})
                                if rv.get("fallback_url"):
                                    media_url = rv["fallback_url"]
                                    media_type = "video"
                        # Check for image posts
                        url = post.get("url", "")
                        if any(url.endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".gif", ".webp"]):
                            media_url = url
                            media_type = "image"
                        # Check for gallery
                        if post.get("is_gallery"):
                            gallery_data = post.get("media_metadata", {})
                            if gallery_data:
                                first_key = next(iter(gallery_data), None)
                                if first_key and gallery_data[first_key].get("s", {}).get("u"):
                                    media_url = gallery_data[first_key]["s"]["u"].replace("&amp;", "&")
                                    media_type = "image"

                        # Score filter: adaptive threshold — niche subs get lower bar
                        score = post.get("score", 0)
                        _low_threshold_subs = {
                            "IntelligenceNews", "CredibleDefense", "WarCollege", "syriancivilwar",
                            "IsraelPalestine", "VolcanoPorn", "OSINT", "Intelligence", "foreignpolicy",
                            "africa", "LatinAmerica", "asia", "UkraineWarVideoReport", "MiddleEastNews",
                            "DataHoarder", "netsec",
                        }
                        min_score = 5 if sub in _low_threshold_subs else 50
                        if score < min_score:
                            continue

                        posts.append({
                            "id": f"reddit-{post.get('id', '')}",
                            "platform": "reddit",
                            "subreddit": sub,
                            "title": title[:200],
                            "author": post.get("author", ""),
                            "url": f"https://reddit.com{post.get('permalink', '')}",
                            "media_url": media_url,
                            "media_type": media_type,
                            "score": score,
                            "comments": post.get("num_comments", 0),
                            "created": post.get("created_utc", 0),
                            "flair": post.get("link_flair_text", ""),
                            "nsfw": post.get("over_18", False),
                        })
            except Exception:
                pass

        # 2. Mastodon — public tag timelines (no auth required)
        mastodon_tags = [
            "earthquake", "explosion", "wildfire", "tornado", "flooding",
            "protest", "breaking", "war", "airstrike", "tsunami",
            "osint", "cybersecurity", "infosec", "missile", "drone",
            "hurricane", "coup", "military", "refugee", "sanctions",
        ]
        mastodon_instances = ["mastodon.social", "masto.ai", "infosec.exchange", "chaos.social", "mastodon.world"]
        for instance in mastodon_instances:
            for tag in mastodon_tags:
                try:
                    resp = requests.get(
                        f"https://{instance}/api/v1/timelines/tag/{tag}?limit=5",
                        timeout=8
                    )
                    if resp.status_code == 200:
                        for status in resp.json():
                            attachments = status.get("media_attachments", [])
                            media_url = ""
                            media_type_m = ""
                            if attachments:
                                att = attachments[0]
                                media_url = att.get("url", att.get("preview_url", ""))
                                media_type_m = "video" if att.get("type") == "video" else "image"
                            text = re.sub(r'<[^>]+>', '', status.get("content", ""))
                            acct = status.get("account", {})
                            if len(text) < 20:
                                continue  # Skip very short posts
                            posts.append({
                                "id": f"masto-{status.get('id', '')}",
                                "platform": "mastodon",
                                "subreddit": f"{instance}",
                                "title": text[:200],
                                "author": acct.get("acct", ""),
                                "url": status.get("url", ""),
                                "media_url": media_url,
                                "media_type": media_type_m,
                                "score": status.get("favourites_count", 0),
                                "comments": status.get("replies_count", 0),
                                "created": status.get("created_at", ""),
                                "flair": tag,
                                "nsfw": status.get("sensitive", False),
                            })
                except Exception:
                    pass

        # 3. Flickr — geotagged photos of disasters/events (public API, no key needed for feeds)
        flickr_tags = ["wildfire", "earthquake damage", "tornado damage", "flood", "protest",
                       "explosion", "military", "hurricane damage", "tsunami", "volcano eruption",
                       "riot", "demonstration", "refugee camp", "war zone", "disaster relief"]
        for tag in flickr_tags:
            try:
                resp = requests.get(
                    f"https://www.flickr.com/services/feeds/photos_public.gne?tags={tag}&format=json&nojsoncallback=1&extras=geo",
                    timeout=8
                )
                if resp.status_code == 200:
                    data = resp.json()
                    for item in data.get("items", [])[:5]:
                        media = item.get("media", {})
                        img_url = media.get("m", "").replace("_m.", "_z.")  # Get larger image
                        lat = float(item.get("latitude", 0) or 0)
                        lon = float(item.get("longitude", 0) or 0)
                        posts.append({
                            "id": f"flickr-{hash(item.get('link','')) % 100000}",
                            "platform": "flickr",
                            "subreddit": "",
                            "title": item.get("title", "")[:200],
                            "author": item.get("author", ""),
                            "url": item.get("link", ""),
                            "media_url": img_url,
                            "media_type": "image",
                            "score": 0,
                            "comments": 0,
                            "created": item.get("date_taken", item.get("published", "")),
                            "flair": tag,
                            "nsfw": False,
                            "lat": lat if lat != 0 else None,
                            "lon": lon if lon != 0 else None,
                        })
            except Exception:
                pass

        # 4. Telegram public channel RSS bridges — conflict/OSINT channels
        telegram_channels = [
            ("intelslava", "Intel Slava Z"),
            ("ryaborig", "Rybar"),
            ("SputnikInt", "Sputnik"),
            ("Middle_East_Spectator", "ME Spectator"),
            ("TheIntelligencer", "Intelligencer"),
            ("DDGeopolitics", "DD Geopolitics"),
            ("militaborant", "Militarist Z"),
            ("fighter_bomber", "Fighter Bomber"),
            ("warmonitors", "War Monitor"),
            ("UkrainaOnlainNews", "Ukraine Online"),
            ("AbuAliEnglish", "Abu Ali English"),
            ("NewResistance1", "New Resistance"),
            ("sotaborant", "Sota"),
            ("osaborant", "OSINT Aggregator"),
            ("ataborant", "ATESH"),
        ]
        for channel_id, label in telegram_channels:
            try:
                # Use rsshub.app bridge for Telegram public channels
                resp = requests.get(
                    f"https://rsshub.app/telegram/channel/{channel_id}",
                    timeout=10, headers={"User-Agent": "ShadowLens/1.0"}
                )
                if resp.status_code == 200:
                    import feedparser as fp5
                    feed = fp5.parse(resp.text)
                    for entry in feed.entries[:5]:
                        title = entry.get("title", "")
                        summary = entry.get("summary", "")
                        # Extract image from HTML summary
                        img_match = re.search(r'<img[^>]+src="([^"]+)"', summary)
                        media_url = img_match.group(1) if img_match else ""
                        # Extract video
                        vid_match = re.search(r'<video[^>]+src="([^"]+)"', summary)
                        if vid_match:
                            media_url = vid_match.group(1)
                            media_type_tg = "video"
                        else:
                            media_type_tg = "image" if media_url else ""
                        posts.append({
                            "id": f"tg-{channel_id}-{hash(title) % 100000}",
                            "platform": "telegram",
                            "subreddit": label,
                            "title": re.sub(r'<[^>]+>', '', title)[:200],
                            "author": label,
                            "url": entry.get("link", ""),
                            "media_url": media_url,
                            "media_type": media_type_tg,
                            "score": 0,
                            "comments": 0,
                            "created": entry.get("published", ""),
                            "flair": "OSINT",
                            "nsfw": False,
                        })
            except Exception:
                pass

        # 5. YouTube — geotagged/live streams of events (RSS feeds from news channels)
        youtube_channels = [
            # Mainstream news
            ("UCupvZG-5ko_eiXAupbDfxWw", "CNN"),
            ("UCknLrEdhRCp1aegoMqRaCZg", "Al Jazeera"),
            ("UC16niRr50-MSBwiO3YDb3RA", "BBC News"),
            ("UCWX0bCC0-vsMSb4ADjMbQ_g", "Reuters"),
            ("UCeY0bbntWzzVIaj2z3QigXg", "NBC News"),
            ("UCLXo7UDZvByw2ixzpQCufnA", "Wion"),
            # Independent / OSINT / Analysis
            ("UCBi2mrWuNuyYy4gbM6fU18Q", "ABC News AU"),
            ("UCQfwfsi5VrQ8yKZ-UWmAEFg", "DW News"),
            ("UCef1-8eOpJgud7IF-bFEkVA", "France24 EN"),
            ("UC4QZ_LsYcvcq7qOsOhpAHg", "Sky News"),
            ("UCJsSEDFFnMFvW4JVBs5JhDw", "TRT World"),
            ("UCSrZ3UV4jOidv8ppoVuvW9Q", "TLDR News Global"),
            ("UCwnKziETDbHJtx78nIkfYug", "CaspianReport"),
            ("UCVHFbqXqoYvEWM1Ddxl0QDg", "Task & Purpose"),
            ("UCddiUEpeqJcYeBxX1IVBKvQ", "The Infographics Show"),
            ("UC1E-JS8L0j1Ei70D9VEFIoQ", "FirstPost"),
            ("UCFWjEwhX6cSAKBQ28pufG3w", "VisualPolitik EN"),
            ("UCGGlszqqmCa2p1fsCsg_3ow", "Good Times Bad Times"),
            ("UCpa-Zb0ZcQjTCPP1Dx_1M8Q", "Johnny Harris"),
        ]
        for channel_id, label in youtube_channels:
            try:
                resp = requests.get(
                    f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}",
                    timeout=8
                )
                if resp.status_code == 200:
                    import feedparser as fp6
                    feed = fp6.parse(resp.text)
                    for entry in feed.entries[:3]:
                        title = entry.get("title", "")
                        vid_id = entry.get("yt_videoid", "")
                        thumb = f"https://img.youtube.com/vi/{vid_id}/hqdefault.jpg" if vid_id else ""
                        posts.append({
                            "id": f"yt-{vid_id}",
                            "platform": "youtube",
                            "subreddit": label,
                            "title": title[:200],
                            "author": label,
                            "url": entry.get("link", ""),
                            "media_url": thumb,
                            "media_type": "video",
                            "score": 0,
                            "comments": 0,
                            "created": entry.get("published", ""),
                            "flair": "Live/Breaking",
                            "nsfw": False,
                        })
            except Exception:
                pass

        # 6. OSINT RSS feeds — crisis/conflict aggregators with media
        osint_feeds = [
            ("https://feeds.bbci.co.uk/news/world/rss.xml", "BBC World", "news"),
            ("https://rss.nytimes.com/services/xml/rss/nyt/World.xml", "NYT World", "news"),
            ("https://www.aljazeera.com/xml/rss/all.xml", "Al Jazeera", "news"),
            ("https://www.theguardian.com/world/rss", "The Guardian", "news"),
            ("https://feeds.washingtonpost.com/rss/world", "WashPost", "news"),
            # OSINT / security specific
            ("https://krebsonsecurity.com/feed/", "Krebs on Security", "cyber"),
            ("https://www.bleepingcomputer.com/feed/", "BleepingComputer", "cyber"),
            ("https://www.darkreading.com/rss.xml", "Dark Reading", "cyber"),
            ("https://threatpost.com/feed/", "Threatpost", "cyber"),
            ("https://therecord.media/feed", "The Record", "cyber"),
            ("https://www.schneier.com/feed/", "Schneier on Security", "cyber"),
            # Conflict/humanitarian
            ("https://www.crisisgroup.org/feed", "Crisis Group", "conflict"),
            ("https://www.thenewhumanitarian.org/rss.xml", "New Humanitarian", "humanitarian"),
            ("https://www.icrc.org/en/rss", "ICRC", "humanitarian"),
            ("https://reliefweb.int/headlines/rss.xml", "ReliefWeb", "humanitarian"),
        ]
        crisis_keywords = {"war", "attack", "strike", "explosion", "missile", "bomb", "killed",
                          "protest", "earthquake", "flood", "fire", "crash", "shooting", "hostage",
                          "tornado", "hurricane", "tsunami", "nuclear", "chemical", "siege",
                          "breach", "hack", "ransomware", "malware", "vulnerability", "exploit",
                          "coup", "assassination", "drone", "artillery", "refugee", "famine",
                          "evacuation", "disaster", "crisis", "sanctions", "airstrike", "ceasefire",
                          "humanitarian", "pandemic", "outbreak", "terror", "riot", "clash"}
        for feed_url, label, category in osint_feeds:
            try:
                resp = requests.get(feed_url, timeout=8, headers={"User-Agent": "ShadowLens/1.0"})
                if resp.status_code == 200:
                    feed = feedparser.parse(resp.text)
                    for entry in feed.entries[:5]:
                        title = entry.get("title", "")
                        summary = entry.get("summary", "")
                        text_lower = (title + " " + summary).lower()
                        # Only include posts mentioning crisis keywords
                        if not any(kw in text_lower for kw in crisis_keywords):
                            continue
                        # Extract media from enclosures or media content
                        media_url = ""
                        media_type_rss = ""
                        enclosures = entry.get("enclosures", [])
                        if enclosures:
                            media_url = enclosures[0].get("href", "")
                            media_type_rss = "image" if "image" in enclosures[0].get("type", "") else "video"
                        media_content = entry.get("media_content", [])
                        if not media_url and media_content:
                            media_url = media_content[0].get("url", "")
                            media_type_rss = "image"
                        media_thumb = entry.get("media_thumbnail", [])
                        if not media_url and media_thumb:
                            media_url = media_thumb[0].get("url", "")
                            media_type_rss = "image"
                        posts.append({
                            "id": f"rss-{label}-{hash(title) % 100000}",
                            "platform": "news",
                            "subreddit": label,
                            "title": title[:200],
                            "author": label,
                            "url": entry.get("link", ""),
                            "media_url": media_url,
                            "media_type": media_type_rss,
                            "score": 0,
                            "comments": 0,
                            "created": entry.get("published", ""),
                            "flair": category,
                            "nsfw": False,
                        })
            except Exception:
                pass

        # 7. Bluesky — public search API (no auth for public posts)
        bluesky_queries = [
            "breaking news", "airstrike", "earthquake", "protest", "OSINT",
            "missile attack", "wildfire", "military", "cybersecurity breach",
        ]
        for query in bluesky_queries:
            try:
                resp = requests.get(
                    f"https://public.api.bsky.app/xrpc/app.bsky.feed.searchPosts?q={requests.utils.quote(query)}&limit=10&sort=latest",
                    timeout=8,
                    headers={"Accept": "application/json"}
                )
                if resp.status_code == 200:
                    data = resp.json()
                    for post_item in data.get("posts", []):
                        record = post_item.get("record", {})
                        text = record.get("text", "")
                        if len(text) < 20:
                            continue
                        author = post_item.get("author", {})
                        handle = author.get("handle", "")
                        # Extract embedded images
                        media_url = ""
                        media_type_bs = ""
                        embed = post_item.get("embed", {})
                        if embed.get("$type") == "app.bsky.embed.images#view":
                            images = embed.get("images", [])
                            if images:
                                media_url = images[0].get("fullsize", images[0].get("thumb", ""))
                                media_type_bs = "image"
                        uri = post_item.get("uri", "")
                        # Convert AT URI to web URL
                        post_id = uri.split("/")[-1] if uri else ""
                        web_url = f"https://bsky.app/profile/{handle}/post/{post_id}" if handle and post_id else ""
                        posts.append({
                            "id": f"bsky-{post_id}",
                            "platform": "bluesky",
                            "subreddit": query,
                            "title": text[:200],
                            "author": handle,
                            "url": web_url,
                            "media_url": media_url,
                            "media_type": media_type_bs,
                            "score": post_item.get("likeCount", 0),
                            "comments": post_item.get("replyCount", 0),
                            "created": record.get("createdAt", ""),
                            "flair": "bluesky",
                            "nsfw": False,
                        })
            except Exception:
                pass

        # 8. Google News RSS — topic-based feeds (no API key needed)
        google_news_topics = [
            ("CAAqBwgKMI7rigMw-uO7Aw", "World"),
            ("CAAqBwgKMJbIlgMwx9GVAw", "Science"),
            ("CAAqJggKIiBDQkFTRWdvSUwyMHZNRGRqTVhZU0FtVnVHZ0pWVXlnQVAB", "War & Conflict"),
        ]
        for topic_id, label in google_news_topics:
            try:
                resp = requests.get(
                    f"https://news.google.com/rss/topics/{topic_id}?hl=en-US&gl=US&ceid=US:en",
                    timeout=8, headers={"User-Agent": "ShadowLens/1.0"}
                )
                if resp.status_code == 200:
                    import feedparser as fp_gn
                    feed = fp_gn.parse(resp.text)
                    for entry in feed.entries[:10]:
                        title = entry.get("title", "")
                        # Google News titles often include source: "Title - Source"
                        source_label = title.rsplit(" - ", 1)[-1] if " - " in title else label
                        posts.append({
                            "id": f"gnews-{hash(title) % 100000}",
                            "platform": "google_news",
                            "subreddit": source_label,
                            "title": title[:200],
                            "author": source_label,
                            "url": entry.get("link", ""),
                            "media_url": "",
                            "media_type": "",
                            "score": 0,
                            "comments": 0,
                            "created": entry.get("published", ""),
                            "flair": f"Google News: {label}",
                            "nsfw": False,
                        })
            except Exception:
                pass

        # 9. Lemmy — federated Reddit alternative, public API
        lemmy_communities = [
            ("lemmy.world", "world"),
            ("lemmy.world", "worldnews"),
            ("lemmy.world", "news"),
            ("lemmy.ml", "worldnews"),
            ("lemmy.ml", "cybersecurity"),
        ]
        for instance, community in lemmy_communities:
            try:
                resp = requests.get(
                    f"https://{instance}/api/v3/post/list?community_name={community}&sort=Hot&limit=10",
                    timeout=8, headers={"Accept": "application/json"}
                )
                if resp.status_code == 200:
                    data = resp.json()
                    for item in data.get("posts", []):
                        p = item.get("post", {})
                        counts = item.get("counts", {})
                        title = p.get("name", "")
                        thumb = p.get("thumbnail_url", "")
                        posts.append({
                            "id": f"lemmy-{p.get('id', '')}",
                            "platform": "lemmy",
                            "subreddit": f"{instance}/{community}",
                            "title": title[:200],
                            "author": item.get("creator", {}).get("name", ""),
                            "url": p.get("ap_id", p.get("url", "")),
                            "media_url": thumb,
                            "media_type": "image" if thumb else "",
                            "score": counts.get("score", 0),
                            "comments": counts.get("comments", 0),
                            "created": p.get("published", ""),
                            "flair": community,
                            "nsfw": p.get("nsfw", False),
                        })
            except Exception:
                pass

        latest_data["social_media"] = posts
        logger.info(f"Social media OSINT: {len(posts)} posts from {len(set(p['platform'] for p in posts))} platforms")
    except Exception as e:
        logger.error(f"Error fetching social media OSINT: {e}")


def fetch_firms_hotspots():
    """NASA FIRMS — active fire/thermal hotspots from MODIS + VIIRS satellites.
    Much more granular than EONET: thousands of individual hotspots with exact GPS."""
    try:
        # FIRMS provides CSV data for recent 24h without API key (NRT)
        # Using the open FIRMS archive for last 24h, VIIRS SNPP
        url = "https://firms.modaps.eosdis.nasa.gov/data/active_fire/suomi-npp-viirs-c2/csv/SUOMI_VIIRS_C2_Global_24h.csv"
        resp = fetch_with_curl(url, timeout=30)
        resp.raise_for_status()
        reader = csv.DictReader(io.StringIO(resp.text))
        hotspots = []
        for row in reader:
            try:
                lat = float(row.get("latitude", 0))
                lon = float(row.get("longitude", 0))
                confidence = row.get("confidence", "")
                bright = float(row.get("bright_ti4", 0) or 0)
                frp = float(row.get("frp", 0) or 0)
                acq_date = row.get("acq_date", "")
                acq_time = row.get("acq_time", "")
                hotspots.append({
                    "lat": lat,
                    "lon": lon,
                    "confidence": confidence,
                    "brightness": bright,
                    "frp": frp,  # Fire Radiative Power (MW)
                    "date": acq_date,
                    "time": acq_time,
                    "satellite": "VIIRS",
                })
            except (ValueError, KeyError):
                continue
        # Filter: only high confidence + high FRP to keep payload under 1MB
        filtered = [h for h in hotspots if h["confidence"] in ("high", "h") or h["frp"] > 10]
        if not filtered:
            filtered = [h for h in hotspots if h["confidence"] in ("nominal", "high", "n", "h")]
        # Cap at 5000 entries sorted by fire radiative power
        filtered.sort(key=lambda x: x["frp"], reverse=True)
        filtered = filtered[:5000]
        latest_data["firms_hotspots"] = filtered
        logger.info(f"Fetched {len(hotspots)} FIRMS hotspots, kept {len(filtered)} (high conf / top FRP)")
    except Exception as e:
        logger.error(f"Error fetching FIRMS hotspots: {e}")


_US_STATE_COORDS = {
    "AL": (32.8, -86.8), "AK": (64.2, -152.5), "AZ": (34.0, -111.1), "AR": (35.2, -91.8),
    "CA": (36.8, -119.4), "CO": (39.1, -105.4), "CT": (41.6, -72.7), "DE": (38.9, -75.5),
    "FL": (27.8, -81.7), "GA": (32.9, -83.1), "HI": (19.9, -155.6), "ID": (44.1, -114.7),
    "IL": (40.3, -89.0), "IN": (40.3, -86.1), "IA": (42.0, -93.2), "KS": (38.5, -98.8),
    "KY": (37.8, -84.3), "LA": (30.9, -92.0), "ME": (45.3, -69.4), "MD": (39.0, -76.6),
    "MA": (42.4, -71.4), "MI": (44.3, -84.5), "MN": (46.3, -94.2), "MS": (32.7, -89.5),
    "MO": (38.5, -92.2), "MT": (46.8, -110.4), "NE": (41.1, -98.3), "NV": (38.8, -116.4),
    "NH": (43.5, -71.5), "NJ": (40.1, -74.5), "NM": (34.5, -105.7), "NY": (43.0, -75.0),
    "NC": (35.5, -79.0), "ND": (47.5, -100.5), "OH": (40.4, -82.9), "OK": (35.0, -97.1),
    "OR": (43.8, -120.6), "PA": (41.2, -77.2), "RI": (41.6, -71.5), "SC": (33.8, -81.2),
    "SD": (43.9, -99.4), "TN": (35.5, -86.6), "TX": (31.0, -100.0), "UT": (39.3, -111.1),
    "VT": (44.0, -72.7), "VA": (37.8, -78.2), "WA": (47.8, -120.7), "WV": (38.6, -80.6),
    "WI": (43.8, -88.8), "WY": (43.1, -107.6), "DC": (38.9, -77.0),
}

def fetch_power_outages():
    """Power outage tracking — NWS severe weather alerts + EIA disturbance events."""
    try:
        outages = []

        # 1. NWS severe weather alerts that cause power outages (primary, always works)
        outage_events = [
            "High Wind Warning", "Ice Storm Warning", "Winter Storm Warning",
            "Severe Thunderstorm Warning", "Hurricane Warning", "Tornado Warning",
            "Extreme Wind Warning", "Blizzard Warning", "Derecho",
            "Hurricane Force Wind Warning", "Tropical Storm Warning",
        ]
        try:
            event_param = ",".join(outage_events)
            resp = requests.get(
                f"https://api.weather.gov/alerts/active?event={event_param}&status=actual",
                timeout=20, headers={"User-Agent": "ShadowLens/1.0", "Accept": "application/geo+json"}
            )
            if resp.status_code == 200:
                data = resp.json()
                for feat in data.get("features", []):
                    props = feat.get("properties", {})
                    geom = feat.get("geometry")
                    area = props.get("areaDesc", "")

                    # Get centroid from geometry or from state code
                    lat, lon = 0.0, 0.0
                    if geom and geom.get("type") == "Polygon" and geom.get("coordinates"):
                        coords = geom["coordinates"][0]
                        if coords:
                            lat = sum(c[1] for c in coords) / len(coords)
                            lon = sum(c[0] for c in coords) / len(coords)
                    elif geom and geom.get("type") == "MultiPolygon" and geom.get("coordinates"):
                        first_ring = geom["coordinates"][0][0]
                        if first_ring:
                            lat = sum(c[1] for c in first_ring) / len(first_ring)
                            lon = sum(c[0] for c in first_ring) / len(first_ring)

                    if lat == 0 and lon == 0:
                        # Try to get from geocode UGC zones
                        zones = props.get("geocode", {}).get("UGC", [])
                        for z in zones:
                            st = z[:2]
                            coords = _US_STATE_COORDS.get(st)
                            if coords:
                                lat, lon = coords
                                break

                    if lat == 0 and lon == 0:
                        continue

                    event_type = props.get("event", "")
                    severity = props.get("severity", "")
                    urgency = props.get("urgency", "")

                    # Estimate affected customers based on area and severity
                    est_customers = 0
                    if severity == "Extreme":
                        est_customers = 50000
                    elif severity == "Severe":
                        est_customers = 10000
                    elif severity == "Moderate":
                        est_customers = 2000

                    outages.append({
                        "id": props.get("id", ""),
                        "state": area[:60],
                        "county": event_type,
                        "customers_out": est_customers,
                        "customers_tracked": 0,
                        "pct_out": 0,
                        "lat": round(lat, 4),
                        "lon": round(lon, 4),
                        "severity": severity,
                        "urgency": urgency,
                        "event": event_type,
                        "headline": (props.get("headline", "") or "")[:200],
                        "onset": props.get("onset", ""),
                        "expires": props.get("expires", ""),
                        "geometry": geom,
                    })
                logger.info(f"NWS severe weather: {len(outages)} active alerts affecting power")
        except Exception as e:
            logger.warning(f"NWS severe weather fetch failed: {e}")

        # 2. EIA electric disturbance events (supplemental, rate limited)
        try:
            resp = requests.get(
                "https://api.eia.gov/v2/electricity/electric-disturbances/events"
                "?api_key=DEMO_KEY&length=30"
                "&sort[0][column]=period&sort[0][direction]=desc",
                headers={"User-Agent": "ShadowLens/1.0"}, timeout=10
            )
            if resp.status_code == 200:
                data = resp.json()
                for ev in data.get("response", {}).get("data", []):
                    customers = int(ev.get("customers-affected", 0) or 0)
                    if customers < 500:
                        continue
                    area = ev.get("area-affected", "")
                    # Try to geocode from state name in area
                    lat, lon = 0.0, 0.0
                    for st_code, coords in _US_STATE_COORDS.items():
                        if st_code in area.upper() or area.upper().startswith(st_code):
                            lat, lon = coords
                            break
                    if lat == 0:
                        # Try state names
                        for name, coords in _COUNTRY_COORDS.items():
                            if name.lower() in area.lower():
                                lat, lon = coords
                                break
                    if lat == 0 and lon == 0:
                        continue
                    outages.append({
                        "id": f"eia-{ev.get('period','')}-{ev.get('respondent','')}",
                        "state": area,
                        "county": ev.get("event-description", ""),
                        "customers_out": customers,
                        "customers_tracked": 0,
                        "pct_out": 0,
                        "lat": lat, "lon": lon,
                        "event": "Electric Disturbance",
                        "severity": "Major" if customers > 50000 else "Moderate",
                    })
                logger.info(f"EIA disturbance events: {len([o for o in outages if o['id'].startswith('eia')])} incidents")
        except Exception:
            pass

        latest_data["power_outages"] = outages
        logger.info(f"Power outages: {len(outages)} total zones")
    except Exception as e:
        logger.error(f"Error fetching power outages: {e}")


def fetch_internet_outages():
    """Internet outage detection via Cloudflare Radar + IODA + fallback heuristics."""
    try:
        outages = []
        seen_ids = set()

        import time as _time
        now_ts = int(_time.time())
        from_ts = now_ts - 86400  # 24h ago

        # --- Source 1: IODA country-level outage alerts (primary source) ---
        try:
            resp = requests.get(
                "https://api.ioda.inetintel.cc.gatech.edu/v2/outages/alerts",
                params={"from": from_ts, "until": now_ts, "limit": 100, "entityType": "country"},
                headers={"User-Agent": "ShadowLens/1.0", "Accept": "application/json"},
                timeout=15,
            )
            if resp.status_code == 200:
                ioda_data = resp.json()
                alerts = ioda_data.get("data", [])
                for alert in alerts:
                    entity = alert.get("entity", {})
                    code = entity.get("code", "")
                    ds = alert.get("datasource", "bgp")
                    level = alert.get("level", "normal")
                    # Only show critical/warning alerts
                    if level == "normal":
                        continue
                    aid = f"ioda-{code}-{ds}-{alert.get('time', '')}"
                    if aid in seen_ids or not code:
                        continue
                    seen_ids.add(aid)
                    cc = code.upper()
                    coords = _ISO2_COUNTRY_COORDS.get(cc)
                    lat = coords[0] if coords else 0.0
                    lon = coords[1] if coords else 0.0
                    if coords:
                        h = hash(aid) % 1000
                        lat += (h % 50 - 25) * 0.015
                        lon += ((h // 50) % 50 - 25) * 0.015
                    name = entity.get("name", code)
                    val = alert.get("value", "")
                    hist = alert.get("historyValue", "")
                    desc = f"Internet disruption: {name} ({ds})"
                    if val and hist:
                        desc += f" — {val}/{hist} prefixes"
                    outages.append({
                        "id": aid,
                        "description": desc,
                        "event_type": ds,
                        "scope": "country",
                        "country": cc,
                        "severity": level,
                        "start": alert.get("time", ""),
                        "end": "",
                        "source": "IODA",
                        "lat": lat, "lon": lon,
                    })
                logger.info(f"IODA country alerts: {len(alerts)} total, {len(outages)} critical/warning")
            else:
                logger.warning(f"IODA country returned {resp.status_code}")
        except Exception as e1:
            logger.warning(f"IODA country fetch failed: {e1}")

        # --- Source 2: IODA ASN-level outage alerts ---
        try:
            resp2 = requests.get(
                "https://api.ioda.inetintel.cc.gatech.edu/v2/outages/alerts",
                params={"from": from_ts, "until": now_ts, "limit": 100, "entityType": "asn"},
                headers={"User-Agent": "ShadowLens/1.0", "Accept": "application/json"},
                timeout=15,
            )
            if resp2.status_code == 200:
                asn_data = resp2.json()
                asn_alerts = asn_data.get("data", [])
                asn_count = 0
                for alert in asn_alerts:
                    entity = alert.get("entity", {})
                    level = alert.get("level", "normal")
                    if level == "normal":
                        continue
                    asn = entity.get("code", "")
                    name = entity.get("name", f"AS{asn}")
                    ds = alert.get("datasource", "bgp")
                    aid = f"ioda-asn-{asn}-{ds}"
                    if aid in seen_ids or not asn:
                        continue
                    seen_ids.add(aid)
                    attrs = entity.get("attrs", {})
                    cc = attrs.get("country_code", "") if isinstance(attrs, dict) else ""
                    coords = _ISO2_COUNTRY_COORDS.get(cc.upper()) if cc else None
                    lat = coords[0] if coords else 0.0
                    lon = coords[1] if coords else 0.0
                    if coords:
                        h = hash(aid) % 1000
                        lat += (h % 50 - 25) * 0.02
                        lon += ((h // 50) % 50 - 25) * 0.02
                    org = attrs.get("org", "") if isinstance(attrs, dict) else ""
                    outages.append({
                        "id": aid,
                        "description": f"ASN disruption: {name}" + (f" ({org})" if org else ""),
                        "event_type": "asn",
                        "scope": "asn",
                        "country": cc or "Unknown",
                        "severity": level,
                        "start": alert.get("time", ""),
                        "end": "",
                        "source": "IODA",
                        "as_name": name,
                        "lat": lat, "lon": lon,
                    })
                    asn_count += 1
                logger.info(f"IODA ASN alerts: {len(asn_alerts)} total, {asn_count} critical/warning")
            else:
                logger.warning(f"IODA ASN returned {resp2.status_code}")
        except Exception as e2:
            logger.warning(f"IODA ASN fetch failed: {e2}")

        # --- Source 3: IODA region-level alerts ---
        try:
            resp3 = requests.get(
                "https://api.ioda.inetintel.cc.gatech.edu/v2/outages/alerts",
                params={"from": from_ts, "until": now_ts, "limit": 50, "entityType": "region"},
                headers={"User-Agent": "ShadowLens/1.0", "Accept": "application/json"},
                timeout=15,
            )
            if resp3.status_code == 200:
                reg_data = resp3.json()
                reg_alerts = reg_data.get("data", [])
                reg_count = 0
                for alert in reg_alerts:
                    entity = alert.get("entity", {})
                    level = alert.get("level", "normal")
                    if level == "normal":
                        continue
                    code = entity.get("code", "")
                    name = entity.get("name", code)
                    ds = alert.get("datasource", "bgp")
                    aid = f"ioda-reg-{code}-{ds}"
                    if aid in seen_ids or not code:
                        continue
                    seen_ids.add(aid)
                    attrs = entity.get("attrs", {})
                    cc = attrs.get("country_code", "") if isinstance(attrs, dict) else ""
                    coords = _ISO2_COUNTRY_COORDS.get(cc.upper()) if cc else None
                    lat = coords[0] if coords else 0.0
                    lon = coords[1] if coords else 0.0
                    if coords:
                        h = hash(aid) % 1000
                        lat += (h % 50 - 25) * 0.03
                        lon += ((h // 50) % 50 - 25) * 0.03
                    outages.append({
                        "id": aid,
                        "description": f"Regional disruption: {name}",
                        "event_type": ds,
                        "scope": "region",
                        "country": cc or "Unknown",
                        "severity": level,
                        "start": alert.get("time", ""),
                        "end": "",
                        "source": "IODA",
                        "lat": lat, "lon": lon,
                    })
                    reg_count += 1
                logger.info(f"IODA region alerts: {len(reg_alerts)} total, {reg_count} critical/warning")
            else:
                logger.warning(f"IODA region returned {resp3.status_code}")
        except Exception as e3:
            logger.warning(f"IODA region fetch failed: {e3}")

        # --- Fallback: If no data from above, generate from NWS comms-affecting alerts ---
        if not outages:
            try:
                resp4 = requests.get(
                    "https://api.weather.gov/alerts/active",
                    params={
                        "event": "Ice Storm Warning,Winter Storm Warning,Severe Thunderstorm Warning,Hurricane Warning,Tornado Warning,Derecho",
                        "status": "actual",
                        "message_type": "alert",
                        "limit": 30,
                    },
                    headers={"User-Agent": "(ShadowLens, contact@shadowlens.app)", "Accept": "application/geo+json"},
                    timeout=15,
                )
                if resp4.status_code == 200:
                    feats = resp4.json().get("features", [])
                    for f in feats:
                        props = f.get("properties", {})
                        geom = f.get("geometry")
                        event = props.get("event", "")
                        # Only include events likely to cause internet disruption
                        if not any(kw in event.lower() for kw in ["ice", "hurricane", "tornado", "derecho", "winter storm"]):
                            continue
                        aid = f"nws-inet-{props.get('id', '')}"
                        if aid in seen_ids:
                            continue
                        seen_ids.add(aid)
                        areas = props.get("areaDesc", "")
                        state = ""
                        for zone in props.get("geocode", {}).get("UGC", []):
                            if len(zone) >= 2:
                                state = zone[:2]
                                break
                        st_coords = _US_STATE_COORDS.get(state, {})
                        lat = st_coords.get("lat", 0)
                        lon = st_coords.get("lon", 0)
                        outages.append({
                            "id": aid,
                            "description": f"Potential internet disruption: {event} — {areas[:80]}",
                            "event_type": "weather-related",
                            "scope": "region",
                            "country": "US",
                            "severity": props.get("severity", "Moderate"),
                            "start": props.get("onset", props.get("effective", "")),
                            "end": props.get("expires", ""),
                            "source": "NWS (infrastructure risk)",
                            "lat": lat, "lon": lon,
                            "geometry": geom,
                        })
                    logger.info(f"NWS infra-risk fallback: {len(outages)} events")
            except Exception as e4:
                logger.warning(f"NWS internet fallback failed: {e4}")

        # Filter out entries with no coordinates
        outages = [o for o in outages if o.get("lat") and o.get("lon")]
        latest_data["internet_outages"] = outages
        logger.info(f"Fetched {len(outages)} internet outage events total")
    except Exception as e:
        logger.error(f"Error fetching internet outages: {e}")


def fetch_air_quality():
    """Air Quality Index — WAQI (World AQI) map feed + OpenAQ fallback."""
    try:
        stations = []
        # OpenAQ v3 (requires API key set in OPENAQ_API_KEY env var)
        openaq_key = os.environ.get("OPENAQ_API_KEY", "")
        if openaq_key:
            try:
                resp = requests.get(
                    "https://api.openaq.org/v3/locations?limit=500&parameter_id=2&sort_order=desc",
                    headers={"Accept": "application/json", "X-API-Key": openaq_key},
                    timeout=20
                )
                if resp.status_code == 200:
                    for loc in resp.json().get("results", []):
                        coords = loc.get("coordinates", {})
                        lat = float(coords.get("latitude", 0) or 0)
                        lon = float(coords.get("longitude", 0) or 0)
                        if not lat or not lon:
                            continue
                        pm25 = 0
                        for p in loc.get("parameters", []):
                            if p.get("parameter") == "pm25":
                                pm25 = float(p.get("lastValue", 0) or 0)
                        if pm25 < 35:
                            continue
                        level = "Hazardous" if pm25 > 250 else "Very Unhealthy" if pm25 > 150 else "Unhealthy" if pm25 > 55 else "Unhealthy for Sensitive" if pm25 > 35 else "Moderate"
                        stations.append({
                            "id": str(loc.get("id", "")),
                            "name": loc.get("name", "Unknown"),
                            "city": loc.get("city", ""),
                            "country": loc.get("country", {}).get("code", "") if isinstance(loc.get("country"), dict) else "",
                            "lat": lat, "lon": lon,
                            "pm25": pm25, "level": level,
                            "updated": "",
                        })
            except Exception as e2:
                logger.warning(f"OpenAQ fetch failed: {e2}")
        # AirNow (requires AIRNOW_API_KEY env var)
        airnow_key = os.environ.get("AIRNOW_API_KEY", "")
        if not stations and airnow_key:
            try:
                resp2 = requests.get(
                    f"https://www.airnowapi.org/aq/observation/current/byBox/?minX=-125&minY=24&maxX=-66&maxY=50&parameters=PM25&dataType=B&format=application/json&API_KEY={airnow_key}",
                    timeout=15
                )
                if resp2.status_code == 200:
                    for obs in resp2.json():
                        aqi = int(obs.get("AQI", 0) or 0)
                        if aqi < 100:
                            continue
                        lat = float(obs.get("Latitude", 0) or 0)
                        lon = float(obs.get("Longitude", 0) or 0)
                        level = "Hazardous" if aqi > 300 else "Very Unhealthy" if aqi > 200 else "Unhealthy" if aqi > 150 else "Unhealthy for Sensitive" if aqi > 100 else "Moderate"
                        stations.append({
                            "id": obs.get("FullAQSCode", ""),
                            "name": obs.get("ReportingArea", "Unknown"),
                            "city": obs.get("ReportingArea", ""),
                            "country": "US", "lat": lat, "lon": lon,
                            "pm25": aqi, "level": level,
                            "updated": obs.get("DateObserved", ""),
                        })
            except Exception:
                pass
        latest_data["air_quality"] = stations
        logger.info(f"Fetched {len(stations)} AQI stations (unhealthy+)")
    except Exception as e:
        logger.error(f"Error fetching air quality: {e}")


def fetch_space_weather():
    """NOAA SWPC — solar flares, geomagnetic storms, solar wind."""
    try:
        alerts = []
        # Solar flare alerts (last 7 days)
        flare_url = "https://services.swpc.noaa.gov/json/solar_flares.json"
        resp = requests.get(flare_url, timeout=10, headers={"User-Agent": "ShadowLens/1.0"})
        if resp.status_code == 200:
            flares = resp.json()
            for f in flares[-20:]:  # last 20 events
                alerts.append({
                    "id": f"flare-{f.get('flrID','')}",
                    "type": "solar_flare",
                    "class": f.get("classType", ""),
                    "begin": f.get("beginTime", ""),
                    "peak": f.get("peakTime", ""),
                    "end": f.get("endTime", ""),
                    "region": f.get("activeRegionNum", ""),
                    "source": f.get("sourceLocation", ""),
                })
        # Geomagnetic storm index (Kp)
        kp_url = "https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json"
        resp2 = requests.get(kp_url, timeout=10, headers={"User-Agent": "ShadowLens/1.0"})
        if resp2.status_code == 200:
            kp_data = resp2.json()
            if len(kp_data) > 1:
                latest_kp = kp_data[-1]  # [time_tag, Kp, Kp_fraction, a_running, station_count]
                kp_val = float(latest_kp[1]) if len(latest_kp) > 1 else 0
                alerts.append({
                    "id": "kp-latest",
                    "type": "geomagnetic",
                    "kp": kp_val,
                    "time": latest_kp[0] if latest_kp else "",
                    "storm_level": "G5 Extreme" if kp_val >= 9 else "G4 Severe" if kp_val >= 8 else "G3 Strong" if kp_val >= 7 else "G2 Moderate" if kp_val >= 6 else "G1 Minor" if kp_val >= 5 else "Quiet",
                })
        # Solar wind speed
        wind_url = "https://services.swpc.noaa.gov/products/summary/solar-wind-speed.json"
        resp3 = requests.get(wind_url, timeout=10, headers={"User-Agent": "ShadowLens/1.0"})
        if resp3.status_code == 200:
            wind = resp3.json()
            alerts.append({
                "id": "solar-wind",
                "type": "solar_wind",
                "speed_kms": wind.get("WindSpeed", ""),
                "time": wind.get("TimeStamp", ""),
            })
        latest_data["space_weather"] = alerts
        logger.info(f"Fetched {len(alerts)} space weather events")
    except Exception as e:
        logger.error(f"Error fetching space weather: {e}")


def fetch_radioactivity():
    """Radioactivity monitoring — US EPA RadNet + Safecast open radiation data."""
    try:
        stations = []
        # Safecast — open radiation monitoring network (worldwide, crowd-sourced)
        try:
            resp = requests.get(
                "https://api.safecast.org/measurements.json?distance=10000&latitude=40&longitude=-100&limit=200&order=created_at+desc",
                headers={"User-Agent": "ShadowLens/1.0"},
                timeout=15
            )
            if resp.status_code == 200:
                for m in resp.json():
                    lat = float(m.get("latitude", 0) or 0)
                    lon = float(m.get("longitude", 0) or 0)
                    if lat == 0 and lon == 0:
                        continue
                    val = float(m.get("value", 0) or 0)
                    stations.append({
                        "id": f"safecast-{m.get('id','')}",
                        "name": f"Safecast #{m.get('device_id','')}",
                        "state": "",
                        "country": "",
                        "lat": lat,
                        "lon": lon,
                        "value": val,
                        "unit": m.get("unit", "cpm"),
                        "source": "Safecast",
                        "updated": m.get("captured_at", ""),
                    })
        except Exception:
            pass
        # Also try Safecast for Europe/Asia
        for region in [("48", "10"), ("35", "139")]:  # Europe center, Japan
            try:
                resp2 = requests.get(
                    f"https://api.safecast.org/measurements.json?distance=5000&latitude={region[0]}&longitude={region[1]}&limit=100&order=created_at+desc",
                    headers={"User-Agent": "ShadowLens/1.0"},
                    timeout=10
                )
                if resp2.status_code == 200:
                    for m in resp2.json():
                        lat = float(m.get("latitude", 0) or 0)
                        lon = float(m.get("longitude", 0) or 0)
                        if lat == 0 and lon == 0:
                            continue
                        val = float(m.get("value", 0) or 0)
                        stations.append({
                            "id": f"safecast-{m.get('id','')}",
                            "name": f"Safecast #{m.get('device_id','')}",
                            "state": "",
                            "country": "",
                            "lat": lat,
                            "lon": lon,
                            "value": val,
                            "unit": m.get("unit", "cpm"),
                            "source": "Safecast",
                            "updated": m.get("captured_at", ""),
                        })
            except Exception:
                pass
        latest_data["radioactivity"] = stations
        logger.info(f"Fetched {len(stations)} radioactivity monitoring stations")
    except Exception as e:
        logger.error(f"Error fetching radioactivity: {e}")


def fetch_bikeshare():
    bikes = []
    try:
        # CitiBike NYC Free GBFS Feed
        info_url = "https://gbfs.citibikenyc.com/gbfs/en/station_information.json"
        status_url = "https://gbfs.citibikenyc.com/gbfs/en/station_status.json"
        
        info_res = fetch_with_curl(info_url, timeout=10)
        status_res = fetch_with_curl(status_url, timeout=10)
        
        if info_res.status_code == 200 and status_res.status_code == 200:
            stations = info_res.json()["data"]["stations"]
            statuses = status_res.json()["data"]["stations"]
            
            # Map statuses
            status_map = {s["station_id"]: s for s in statuses}
            
            # Top 100 stations for performance
            for st in stations[:100]:
                sid = st["station_id"]
                stat = status_map.get(sid, {})
                bikes.append({
                    "id": sid,
                    "name": st.get("name", "Station"),
                    "lat": st.get("lat", 0),
                    "lng": st.get("lon", 0),
                    "capacity": st.get("capacity", 0),
                    "available": stat.get("num_bikes_available", 0)
                })
    except Exception as e:
        logger.error(f"Error fetching bikeshare: {e}")
    latest_data["bikeshare"] = bikes

def fetch_traffic():
    # Deprecated: TomTom warning signs removed from UI to declutter CCTV mesh
    pass

def fetch_earthquakes():
    quakes = []
    try:
        url = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/2.5_day.geojson"
        response = fetch_with_curl(url, timeout=10)
        if response.status_code == 200:
            features = response.json().get("features", [])
            for f in features[:50]:
                mag = f["properties"]["mag"]
                lng, lat, depth = f["geometry"]["coordinates"]
                quakes.append({
                    "id": f["id"],
                    "mag": mag,
                    "lat": lat,
                    "lng": lng,
                    "place": f["properties"]["place"]
                })
    except Exception as e:
        logger.error(f"Error fetching earthquakes: {e}")
    latest_data["earthquakes"] = quakes

# Satellite GP data cache — re-download from CelesTrak only every 30 minutes
_sat_gp_cache = {"data": None, "last_fetch": 0}

# Satellite intelligence classification database — module-level constant.
# Key: substring to match in OBJECT_NAME → {country, mission, sat_type, wiki}
_SAT_INTEL_DB = [
    # Military reconnaissance / imaging
        ("USA 224", {"country": "USA", "mission": "military_recon", "sat_type": "KH-11 Reconnaissance", "wiki": "https://en.wikipedia.org/wiki/KH-11_KENNEN"}),
        ("USA 245", {"country": "USA", "mission": "military_recon", "sat_type": "KH-11 Reconnaissance", "wiki": "https://en.wikipedia.org/wiki/KH-11_KENNEN"}),
        ("USA 290", {"country": "USA", "mission": "military_recon", "sat_type": "KH-11 Reconnaissance", "wiki": "https://en.wikipedia.org/wiki/KH-11_KENNEN"}),
        ("USA 314", {"country": "USA", "mission": "military_recon", "sat_type": "KH-11 Reconnaissance", "wiki": "https://en.wikipedia.org/wiki/KH-11_KENNEN"}),
        ("USA 338", {"country": "USA", "mission": "military_recon", "sat_type": "Keyhole Successor", "wiki": "https://en.wikipedia.org/wiki/KH-11_KENNEN"}),
        ("TOPAZ", {"country": "Russia", "mission": "military_recon", "sat_type": "Optical Reconnaissance", "wiki": "https://en.wikipedia.org/wiki/Persona_(satellite)"}),
        ("PERSONA", {"country": "Russia", "mission": "military_recon", "sat_type": "Optical Reconnaissance", "wiki": "https://en.wikipedia.org/wiki/Persona_(satellite)"}),
        ("KONDOR", {"country": "Russia", "mission": "military_sar", "sat_type": "SAR Reconnaissance", "wiki": "https://en.wikipedia.org/wiki/Kondor_(satellite)"}),
        ("BARS-M", {"country": "Russia", "mission": "military_recon", "sat_type": "Mapping Reconnaissance", "wiki": "https://en.wikipedia.org/wiki/Bars-M"}),
        ("YAOGAN", {"country": "China", "mission": "military_recon", "sat_type": "Remote Sensing / ELINT", "wiki": "https://en.wikipedia.org/wiki/Yaogan"}),
        ("GAOFEN", {"country": "China", "mission": "military_recon", "sat_type": "High-Res Imaging", "wiki": "https://en.wikipedia.org/wiki/Gaofen"}),
        ("JILIN", {"country": "China", "mission": "commercial_imaging", "sat_type": "Video / Imaging", "wiki": "https://en.wikipedia.org/wiki/Jilin-1"}),
        ("OFEK", {"country": "Israel", "mission": "military_recon", "sat_type": "Reconnaissance", "wiki": "https://en.wikipedia.org/wiki/Ofeq"}),
        ("CSO", {"country": "France", "mission": "military_recon", "sat_type": "Optical Reconnaissance", "wiki": "https://en.wikipedia.org/wiki/CSO_(satellite)"}),
        ("IGS", {"country": "Japan", "mission": "military_recon", "sat_type": "Intelligence Gathering", "wiki": "https://en.wikipedia.org/wiki/Information_Gathering_Satellite"}),
        # SAR (Synthetic Aperture Radar) — can see through clouds
        ("CAPELLA", {"country": "USA", "mission": "sar", "sat_type": "SAR Imaging", "wiki": "https://en.wikipedia.org/wiki/Capella_Space"}),
        ("ICEYE", {"country": "Finland", "mission": "sar", "sat_type": "SAR Microsatellite", "wiki": "https://en.wikipedia.org/wiki/ICEYE"}),
        ("COSMO-SKYMED", {"country": "Italy", "mission": "sar", "sat_type": "SAR Constellation", "wiki": "https://en.wikipedia.org/wiki/COSMO-SkyMed"}),
        ("TANDEM", {"country": "Germany", "mission": "sar", "sat_type": "SAR Interferometry", "wiki": "https://en.wikipedia.org/wiki/TanDEM-X"}),
        ("PAZ", {"country": "Spain", "mission": "sar", "sat_type": "SAR Imaging", "wiki": "https://en.wikipedia.org/wiki/PAZ_(satellite)"}),
        # Commercial imaging
        ("WORLDVIEW", {"country": "USA", "mission": "commercial_imaging", "sat_type": "Maxar High-Res", "wiki": "https://en.wikipedia.org/wiki/WorldView-3"}),
        ("GEOEYE", {"country": "USA", "mission": "commercial_imaging", "sat_type": "Maxar Imaging", "wiki": "https://en.wikipedia.org/wiki/GeoEye-1"}),
        ("PLEIADES", {"country": "France", "mission": "commercial_imaging", "sat_type": "Airbus Imaging", "wiki": "https://en.wikipedia.org/wiki/Pl%C3%A9iades_(satellite)"}),
        ("SPOT", {"country": "France", "mission": "commercial_imaging", "sat_type": "Airbus Medium-Res", "wiki": "https://en.wikipedia.org/wiki/SPOT_(satellite)"}),
        ("PLANET", {"country": "USA", "mission": "commercial_imaging", "sat_type": "PlanetScope", "wiki": "https://en.wikipedia.org/wiki/Planet_Labs"}),
        ("SKYSAT", {"country": "USA", "mission": "commercial_imaging", "sat_type": "Planet Video", "wiki": "https://en.wikipedia.org/wiki/SkySat"}),
        ("BLACKSKY", {"country": "USA", "mission": "commercial_imaging", "sat_type": "BlackSky Imaging", "wiki": "https://en.wikipedia.org/wiki/BlackSky"}),
        # Signals intelligence / ELINT
        ("NROL", {"country": "USA", "mission": "sigint", "sat_type": "Classified NRO", "wiki": "https://en.wikipedia.org/wiki/National_Reconnaissance_Office"}),
        ("MENTOR", {"country": "USA", "mission": "sigint", "sat_type": "SIGINT / ELINT", "wiki": "https://en.wikipedia.org/wiki/Mentor_(satellite)"}),
        ("LUCH", {"country": "Russia", "mission": "sigint", "sat_type": "Relay / SIGINT", "wiki": "https://en.wikipedia.org/wiki/Luch_(satellite)"}),
        ("SHIJIAN", {"country": "China", "mission": "sigint", "sat_type": "ELINT / Tech Demo", "wiki": "https://en.wikipedia.org/wiki/Shijian"}),
        # Navigation
        ("NAVSTAR", {"country": "USA", "mission": "navigation", "sat_type": "GPS", "wiki": "https://en.wikipedia.org/wiki/GPS_satellite_blocks"}),
        ("GLONASS", {"country": "Russia", "mission": "navigation", "sat_type": "GLONASS", "wiki": "https://en.wikipedia.org/wiki/GLONASS"}),
        ("BEIDOU", {"country": "China", "mission": "navigation", "sat_type": "BeiDou", "wiki": "https://en.wikipedia.org/wiki/BeiDou"}),
        ("GALILEO", {"country": "EU", "mission": "navigation", "sat_type": "Galileo", "wiki": "https://en.wikipedia.org/wiki/Galileo_(satellite_navigation)"}),
        # Early warning
        ("SBIRS", {"country": "USA", "mission": "early_warning", "sat_type": "Missile Warning", "wiki": "https://en.wikipedia.org/wiki/Space-Based_Infrared_System"}),
        ("TUNDRA", {"country": "Russia", "mission": "early_warning", "sat_type": "Missile Warning", "wiki": "https://en.wikipedia.org/wiki/Tundra_(satellite)"}),
        # Space stations
        ("ISS", {"country": "Intl", "mission": "space_station", "sat_type": "Space Station", "wiki": "https://en.wikipedia.org/wiki/International_Space_Station"}),
    ("TIANGONG", {"country": "China", "mission": "space_station", "sat_type": "Space Station", "wiki": "https://en.wikipedia.org/wiki/Tiangong_space_station"}),
]

def _parse_tle_to_gp(name, norad_id, line1, line2):
    """Convert TLE two-line element to CelesTrak GP-style dict for unified processing."""
    try:
        # Parse TLE line 2 fields (standard TLE format)
        incl = float(line2[8:16].strip())
        raan = float(line2[17:25].strip())
        ecc = float("0." + line2[26:33].strip())
        argp = float(line2[34:42].strip())
        ma = float(line2[43:51].strip())
        mm = float(line2[52:63].strip())
        # Parse BSTAR from line 1 (columns 54-61)
        bstar_str = line1[53:61].strip()
        if bstar_str:
            mantissa = float(bstar_str[:-2]) / 1e5
            exponent = int(bstar_str[-2:])
            bstar = mantissa * (10 ** exponent)
        else:
            bstar = 0.0
        # Parse epoch from line 1 (columns 18-32)
        epoch_yr = int(line1[18:20])
        epoch_day = float(line1[20:32].strip())
        year = 2000 + epoch_yr if epoch_yr < 57 else 1900 + epoch_yr
        from datetime import datetime, timedelta
        epoch_dt = datetime(year, 1, 1) + timedelta(days=epoch_day - 1)
        return {
            "OBJECT_NAME": name,
            "NORAD_CAT_ID": norad_id,
            "MEAN_MOTION": mm,
            "ECCENTRICITY": ecc,
            "INCLINATION": incl,
            "RA_OF_ASC_NODE": raan,
            "ARG_OF_PERICENTER": argp,
            "MEAN_ANOMALY": ma,
            "BSTAR": bstar,
            "EPOCH": epoch_dt.strftime("%Y-%m-%dT%H:%M:%S"),
        }
    except Exception:
        return None


def _fetch_satellites_from_tle_api():
    """Fallback: fetch satellite TLEs from tle.ivanstanojevic.me when CelesTrak is blocked."""
    # Build search terms from our intel DB — deduplicate short prefixes
    search_terms = set()
    for key, _ in _SAT_INTEL_DB:
        # Use first word for broader matching (e.g., "USA" catches USA 224, USA 245, etc.)
        term = key.split()[0] if len(key.split()) > 1 and key.split()[0] in ("USA", "NROL") else key
        search_terms.add(term)

    all_results = []
    seen_ids = set()
    for term in search_terms:
        try:
            url = f"https://tle.ivanstanojevic.me/api/tle/?search={term}&page_size=100&format=json"
            response = fetch_with_curl(url, timeout=10)
            if response.status_code != 200:
                continue
            data = response.json()
            for member in data.get("member", []):
                sat_id = member.get("satelliteId")
                if sat_id in seen_ids:
                    continue
                seen_ids.add(sat_id)
                gp = _parse_tle_to_gp(
                    member.get("name", "UNKNOWN"),
                    sat_id,
                    member.get("line1", ""),
                    member.get("line2", ""),
                )
                if gp:
                    all_results.append(gp)
        except Exception as e:
            logger.debug(f"TLE fallback search '{term}' failed: {e}")
            continue

    return all_results


def fetch_satellites():
    sats = []
    try:
        # Cache GP data from CelesTrak — only re-download every 30 minutes
        # Positions are re-propagated from cached orbital elements each cycle
        now_ts = time.time()
        if _sat_gp_cache["data"] is None or (now_ts - _sat_gp_cache["last_fetch"]) > 1800:
            # Try multiple CelesTrak mirrors — .org is often blocked/banned by some networks
            gp_urls = [
                "https://celestrak.org/NORAD/elements/gp.php?GROUP=active&FORMAT=json",
                "https://celestrak.com/NORAD/elements/gp.php?GROUP=active&FORMAT=json",
            ]
            for url in gp_urls:
                try:
                    response = fetch_with_curl(url, timeout=8)
                    if response.status_code == 200:
                        gp_data = response.json()
                        if isinstance(gp_data, list) and len(gp_data) > 100:
                            _sat_gp_cache["data"] = gp_data
                            _sat_gp_cache["last_fetch"] = now_ts
                            logger.info(f"Satellites: Downloaded {len(gp_data)} GP records from {url}")
                            break
                except Exception as e:
                    logger.warning(f"Satellites: Failed to fetch from {url}: {e}")
                    continue

            # Fallback: if CelesTrak is blocked, use tle.ivanstanojevic.me TLE API
            if _sat_gp_cache["data"] is None:
                logger.info("Satellites: CelesTrak unreachable, trying TLE fallback API...")
                try:
                    fallback_data = _fetch_satellites_from_tle_api()
                    if fallback_data and len(fallback_data) > 10:
                        _sat_gp_cache["data"] = fallback_data
                        _sat_gp_cache["last_fetch"] = now_ts
                        logger.info(f"Satellites: Got {len(fallback_data)} records from TLE fallback API")
                except Exception as e:
                    logger.error(f"Satellites: TLE fallback also failed: {e}")

        data = _sat_gp_cache["data"]
        if not data:
            logger.warning("No satellite GP data available from any source")
            latest_data["satellites"] = sats
            return

        # Only keep satellites matching the intel classification DB
        classified = []
        for sat in data:
            name = sat.get("OBJECT_NAME", "UNKNOWN").upper()
            intel = None
            for key, meta in _SAT_INTEL_DB:
                if key.upper() in name:
                    intel = dict(meta)
                    break
            if not intel:
                continue  # Skip junk, debris, CubeSats, bulk constellations
            entry = {
                "id": sat.get("NORAD_CAT_ID"),
                "name": sat.get("OBJECT_NAME", "UNKNOWN"),
                "MEAN_MOTION": sat.get("MEAN_MOTION"),
                "ECCENTRICITY": sat.get("ECCENTRICITY"),
                "INCLINATION": sat.get("INCLINATION"),
                "RA_OF_ASC_NODE": sat.get("RA_OF_ASC_NODE"),
                "ARG_OF_PERICENTER": sat.get("ARG_OF_PERICENTER"),
                "MEAN_ANOMALY": sat.get("MEAN_ANOMALY"),
                "BSTAR": sat.get("BSTAR"),
                "EPOCH": sat.get("EPOCH"),
            }
            entry.update(intel)
            classified.append(entry)

        all_sats = classified
        logger.info(f"Satellites: {len(classified)} intel-classified out of {len(data)} total in catalog")

        # Propagate orbital elements to get current lat/lng/alt using SGP4
        now = datetime.utcnow()
        jd, fr = jday(now.year, now.month, now.day, now.hour, now.minute, now.second + now.microsecond / 1e6)
        
        for s in all_sats:
            try:
                mean_motion = s.get('MEAN_MOTION')
                ecc = s.get('ECCENTRICITY')
                incl = s.get('INCLINATION')
                raan = s.get('RA_OF_ASC_NODE')
                argp = s.get('ARG_OF_PERICENTER')
                ma = s.get('MEAN_ANOMALY')
                bstar = s.get('BSTAR', 0)
                epoch_str = s.get('EPOCH')
                norad_id = s.get('id', 0)
                
                if mean_motion is None or ecc is None or incl is None:
                    continue
                
                epoch_dt = datetime.strptime(epoch_str[:19], '%Y-%m-%dT%H:%M:%S')
                epoch_jd, epoch_fr = jday(epoch_dt.year, epoch_dt.month, epoch_dt.day,
                                          epoch_dt.hour, epoch_dt.minute, epoch_dt.second)
                
                sat_obj = Satrec()
                sat_obj.sgp4init(
                    WGS72, 'i', norad_id,
                    (epoch_jd + epoch_fr) - 2433281.5,
                    bstar, 0.0, 0.0, ecc,
                    math.radians(argp), math.radians(incl),
                    math.radians(ma),
                    mean_motion * 2 * math.pi / 1440.0,
                    math.radians(raan)
                )
                
                e, r, v = sat_obj.sgp4(jd, fr)
                if e != 0:
                    continue
                
                x, y, z = r
                gmst = _gmst(jd + fr)
                lng_rad = math.atan2(y, x) - gmst
                lat_rad = math.atan2(z, math.sqrt(x*x + y*y))
                alt_km = math.sqrt(x*x + y*y + z*z) - 6371.0
                
                s['lat'] = round(math.degrees(lat_rad), 4)
                lng_deg = math.degrees(lng_rad) % 360
                s['lng'] = round(lng_deg - 360 if lng_deg > 180 else lng_deg, 4)
                s['alt_km'] = round(alt_km, 1)
                
                # Compute ground speed and heading from ECI velocity vector
                # v is in km/s in ECI frame; subtract Earth rotation to get ground-relative
                vx, vy, vz = v
                omega_e = 7.2921159e-5  # Earth rotation rate rad/s
                # Ground-relative velocity (subtract Earth rotation)
                vx_g = vx + omega_e * y  # note: y from position, not vy
                vy_g = vy - omega_e * x
                vz_g = vz
                # Convert ECI velocity to East/North/Up at satellite's geodetic position
                cos_lat = math.cos(lat_rad)
                sin_lat = math.sin(lat_rad)
                cos_lng = math.cos(lng_rad + gmst)  # need ECEF longitude
                sin_lng = math.sin(lng_rad + gmst)
                # East = -sin(lng)*vx + cos(lng)*vy
                v_east = -sin_lng * vx_g + cos_lng * vy_g
                # North = -sin(lat)*cos(lng)*vx - sin(lat)*sin(lng)*vy + cos(lat)*vz
                v_north = -sin_lat * cos_lng * vx_g - sin_lat * sin_lng * vy_g + cos_lat * vz_g
                # Ground speed in km/s → knots (1 km/s = 1943.84 knots)
                ground_speed_kms = math.sqrt(v_east**2 + v_north**2)
                s['speed_knots'] = round(ground_speed_kms * 1943.84, 1)
                # Heading: angle from north, clockwise
                heading_rad = math.atan2(v_east, v_north)
                s['heading'] = round(math.degrees(heading_rad) % 360, 1)
                # Wikipedia URL: USA-XXX satellites get their own article,
                # all others keep the curated class/type URL from _SAT_INTEL_DB
                sat_name = s.get('name', '')
                usa_match = re.search(r'USA[\s\-]*(\d+)', sat_name)
                if usa_match:
                    s['wiki'] = f"https://en.wikipedia.org/wiki/USA-{usa_match.group(1)}"
                # Strip GP element fields to save bandwidth
                for k in ('MEAN_MOTION', 'ECCENTRICITY', 'INCLINATION',
                          'RA_OF_ASC_NODE', 'ARG_OF_PERICENTER', 'MEAN_ANOMALY',
                          'BSTAR', 'EPOCH', 'tle1', 'tle2'):
                    s.pop(k, None)
                sats.append(s)
            except Exception:
                continue

        logger.info(f"Satellites: {len(classified)} classified, {len(sats)} positioned")
    except Exception as e:
        logger.error(f"Error fetching satellites: {e}")
    # Only overwrite if we got data — don't wipe the map on API timeout
    if sats:
        latest_data["satellites"] = sats
    elif not latest_data.get("satellites"):
        latest_data["satellites"] = []

def fetch_noaa_weather_radio():
    """NOAA NWR — Weather Radio transmitter stations across the US."""
    if latest_data.get("noaa_nwr"):
        return  # Static data, fetch once
    try:
        resp = requests.get("https://www.weather.gov/source/nwr/JS/CCL.js", timeout=30,
                            headers={"User-Agent": "ShadowLens/1.0"})
        if resp.status_code != 200:
            logger.warning(f"NOAA NWR JS fetch failed: {resp.status_code}")
            return
        content = resp.text
        def extract_array(var_name):
            pattern = re.compile(rf'{var_name}\[(\d+)\]\s*=\s*"([^"]*)";')
            return {int(idx): val for idx, val in pattern.findall(content)}
        site_names = extract_array("SITENAME")
        callsigns = extract_array("CALLSIGN")
        freqs = extract_array("FREQ")
        lats = extract_array("LAT")
        lons = extract_array("LON")
        statuses = extract_array("STATUS")
        states = extract_array("SITESTATE")
        cities = extract_array("SITELOC")
        seen = set()
        stations = []
        for idx, callsign in callsigns.items():
            if not callsign or callsign in seen:
                continue
            try:
                lat = float(lats.get(idx, 0))
                lon = float(lons.get(idx, 0))
            except (ValueError, TypeError):
                continue
            if lat == 0 and lon == 0:
                continue
            try:
                freq = float(freqs.get(idx, 0))
            except (ValueError, TypeError):
                freq = 0
            seen.add(callsign)
            stations.append({
                "id": f"nwr-{callsign}",
                "callsign": callsign,
                "name": site_names.get(idx, "").strip(),
                "lat": lat, "lon": lon,
                "frequency": freq,
                "status": statuses.get(idx, "Unknown"),
                "state": states.get(idx, ""),
                "city": cities.get(idx, ""),
            })
        latest_data["noaa_nwr"] = stations
        logger.info(f"Fetched {len(stations)} NOAA Weather Radio stations")
    except Exception as e:
        logger.error(f"Error fetching NOAA NWR: {e}")


def fetch_kiwisdr_nodes():
    """KiwiSDR — public HF radio receivers worldwide for remote listening."""
    if latest_data.get("kiwisdr_nodes"):
        return  # Static-ish data, fetch once
    try:
        nodes = []
        directory_urls = [
            "http://rx.linkfanel.net/kiwisdr_com.js",
            "https://rx.skywavelinux.com/kiwisdr_com.js",
        ]
        raw = None
        for url in directory_urls:
            try:
                resp = requests.get(url, timeout=15, headers={"User-Agent": "ShadowLens/1.0"})
                if resp.status_code == 200:
                    raw = resp.text
                    break
            except Exception:
                continue
        if not raw:
            return
        # Parse: strip JS wrapper, clean JSON
        text = raw.strip()
        text = re.sub(r'(?m)^\s*//.*$', '', text).strip()
        text = re.sub(r'^var\s+\w+\s*=\s*', '', text).rstrip(';').strip()
        text = re.sub(r'("bands"\s*:\s*"[^"]+"\s*),.*$', r'\1,', text, flags=re.MULTILINE)
        text = re.sub(r',\s*([}\]])', r'\1', text)
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            # Regex fallback
            data = []
            for block in re.finditer(r'\{[^{}]+\}', raw):
                chunk = block.group()
                host_m = re.search(r'"?(?:host|hostname)"?\s*:\s*"([^"]+)"', chunk)
                lat_m = re.search(r'"?lat"?\s*:\s*([-\d.]+)', chunk)
                lon_m = re.search(r'"?lon"?\s*:\s*([-\d.]+)', chunk)
                port_m = re.search(r'"?port"?\s*:\s*(\d+)', chunk)
                if host_m and lat_m and lon_m:
                    try:
                        nodes.append({
                            "id": f"kiwi-{host_m.group(1)}",
                            "host": host_m.group(1),
                            "port": int(port_m.group(1)) if port_m else 8073,
                            "lat": float(lat_m.group(1)),
                            "lon": float(lon_m.group(1)),
                            "freq_min": 0, "freq_max": 30000,
                            "users": 0, "channels": 8,
                        })
                    except (ValueError, TypeError):
                        pass
            latest_data["kiwisdr_nodes"] = nodes
            logger.info(f"KiwiSDR: parsed {len(nodes)} nodes (regex fallback)")
            return
        # Unwrap envelope
        if isinstance(data, dict):
            for key in ("rx", "receivers", "nodes", "data"):
                if isinstance(data.get(key), list):
                    data = data[key]
                    break
        if not isinstance(data, list):
            return
        for entry in data:
            if not isinstance(entry, dict):
                continue
            host = (entry.get("host") or entry.get("hostname") or "").strip()
            if not host:
                if "url" in entry:
                    m = re.match(r'https?://([^/:]+)(?::(\d+))?', entry.get("url", ""))
                    if m:
                        host = m.group(1).strip()
                if not host:
                    continue
            # GPS coordinates
            gps = entry.get("gpsd") or entry.get("gps") or {}
            lat, lon = 0.0, 0.0
            if isinstance(gps, dict):
                lat = float(gps.get("lat", 0) or 0)
                lon = float(gps.get("lon", 0) or 0)
            elif isinstance(gps, str):
                m = re.match(r'\(([-\d.]+),\s*([-\d.]+)\)', gps)
                if m:
                    lat, lon = float(m.group(1)), float(m.group(2))
            if lat == 0 and lon == 0:
                lat = float(entry.get("lat", 0) or 0)
                lon = float(entry.get("lon", 0) or 0)
            if lat == 0 and lon == 0:
                continue
            # Frequency range
            bands_raw = str(entry.get("bands", "0-30000"))
            m = re.match(r'([\d.]+)[-–]([\d.]+)', bands_raw)
            if m:
                fmin, fmax = float(m.group(1)), float(m.group(2))
                if fmax < 1000:
                    fmin *= 1000
                    fmax *= 1000
            else:
                fmin, fmax = 0.0, 30000.0
            port = int(entry.get("port", 8073) or 8073)
            users = int(entry.get("users", 0) or 0)
            num_ch = int(entry.get("num_ch") or entry.get("users_max") or 8)
            name = entry.get("name", "") or entry.get("sdr_hw", "") or host
            nodes.append({
                "id": f"kiwi-{host}:{port}",
                "host": host,
                "port": port,
                "name": str(name)[:60],
                "lat": lat, "lon": lon,
                "freq_min": fmin, "freq_max": fmax,
                "users": users, "channels": num_ch,
                "antenna": str(entry.get("antenna", "") or "")[:60],
                "url": f"http://{host}:{port}",
            })
        latest_data["kiwisdr_nodes"] = nodes
        logger.info(f"KiwiSDR: fetched {len(nodes)} public HF receivers worldwide")
    except Exception as e:
        logger.error(f"Error fetching KiwiSDR nodes: {e}")


def fetch_uavs():
    # Simulated high-altitude long-endurance (HALE) and MALE UAVs over high-risk regions
    
    uav_targets = [
        {
            "name": "RQ-4 Global Hawk", "center": [31.5, 34.8], "radius": 0.5, "alt": 15000,
            "country": "USA", "uav_type": "HALE Surveillance", "range_km": 2200,
            "wiki": "https://en.wikipedia.org/wiki/Northrop_Grumman_RQ-4_Global_Hawk",
            "speed_knots": 340
        },
        {
            "name": "MQ-9 Reaper", "center": [49.0, 31.4], "radius": 1.2, "alt": 12000,
            "country": "USA", "uav_type": "MALE Strike/ISR", "range_km": 1850,
            "wiki": "https://en.wikipedia.org/wiki/General_Atomics_MQ-9_Reaper",
            "speed_knots": 250
        },
        {
            "name": "Bayraktar TB2", "center": [23.6, 120.9], "radius": 0.8, "alt": 8000,
            "country": "Turkey", "uav_type": "MALE Strike", "range_km": 150,
            "wiki": "https://en.wikipedia.org/wiki/Bayraktar_TB2",
            "speed_knots": 120
        },
        {
            "name": "MQ-1C Gray Eagle", "center": [38.0, 127.0], "radius": 0.4, "alt": 10000,
            "country": "USA", "uav_type": "MALE ISR/Strike", "range_km": 400,
            "wiki": "https://en.wikipedia.org/wiki/General_Atomics_MQ-1C_Gray_Eagle",
            "speed_knots": 150
        },
        {
            "name": "RQ-170 Sentinel", "center": [25.0, 55.0], "radius": 1.5, "alt": 18000,
            "country": "USA", "uav_type": "Stealth ISR", "range_km": 1100,
            "wiki": "https://en.wikipedia.org/wiki/Lockheed_Martin_RQ-170_Sentinel",
            "speed_knots": 300
        }
    ]
    
    # Use the current hour and minute to create a continuous slow orbit
    now = datetime.utcnow()
    # 1 full orbit every 10 minutes
    time_factor = ((now.minute % 10) * 60 + now.second) / 600.0  
    angle = time_factor * 2 * math.pi
    
    uavs = []
    for idx, t in enumerate(uav_targets):
        # Offset the angle slightly so they aren't all synchronized
        offset_angle = angle + (idx * math.pi / 2.5)
        
        lat = t["center"][0] + math.sin(offset_angle) * t["radius"]
        lng = t["center"][1] + math.cos(offset_angle) * t["radius"]
        
        heading = (math.degrees(offset_angle) + 90) % 360
        
        uavs.append({
            "id": f"uav-{idx}",
            "callsign": t["name"],
            "aircraft_model": t["name"],
            "lat": lat,
            "lng": lng,
            "alt": t["alt"],
            "heading": heading,
            "speed_knots": t["speed_knots"],
            "center": t["center"],
            "orbit_radius": t["radius"],
            "range_km": t["range_km"],
            "country": t["country"],
            "uav_type": t["uav_type"],
            "wiki": t["wiki"],
        })
        
    latest_data['uavs'] = uavs

cached_airports = []
flight_trails = {}  # {icao_hex: {points: [[lat, lng, alt, ts], ...], last_seen: ts}}
_trails_lock = threading.Lock()
_MAX_TRACKED_TRAILS = 2000  # Global cap on number of aircraft trails in memory

# (math imported at module top)

def find_nearest_airport(lat, lng, max_distance_nm=200):
    """Find the nearest large airport to a given lat/lng using haversine distance.
    Returns dict with iata, name, lat, lng, distance_nm or None if no airport within range."""
    if not cached_airports:
        return None
    
    best = None
    best_dist = float('inf')
    
    lat_r = math.radians(lat)
    lng_r = math.radians(lng)
    
    for apt in cached_airports:
        apt_lat_r = math.radians(apt['lat'])
        apt_lng_r = math.radians(apt['lng'])
        
        dlat = apt_lat_r - lat_r
        dlng = apt_lng_r - lng_r
        a = math.sin(dlat / 2) ** 2 + math.cos(lat_r) * math.cos(apt_lat_r) * math.sin(dlng / 2) ** 2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        dist_nm = 3440.065 * c  # Earth radius in nautical miles
        
        if dist_nm < best_dist:
            best_dist = dist_nm
            best = apt
    
    if best and best_dist <= max_distance_nm:
        return {
            "iata": best['iata'],
            "name": best['name'],
            "lat": best['lat'],
            "lng": best['lng'],
            "distance_nm": round(best_dist, 1)
        }
    return None

def fetch_airports():
    global cached_airports
    if not cached_airports:
        logger.info("Downloading global airports database from ourairports.com...")
        try:
            url = "https://ourairports.com/data/airports.csv"
            response = fetch_with_curl(url, timeout=15)
            if response.status_code == 200:
                import csv
                import io
                f = io.StringIO(response.text)
                reader = csv.DictReader(f)
                for row in reader:
                    # Filter to only large international hubs that have an IATA code assigned
                    if row['type'] == 'large_airport' and row['iata_code']:
                        cached_airports.append({
                            "id": row['ident'],
                            "name": row['name'],
                            "iata": row['iata_code'],
                            "lat": float(row['latitude_deg']),
                            "lng": float(row['longitude_deg']),
                            "type": "airport"
                        })
                logger.info(f"Loaded {len(cached_airports)} large airports into cache.")
        except Exception as e:
            logger.error(f"Error fetching airports: {e}")
            
    latest_data['airports'] = cached_airports

from services.geopolitics import fetch_ukraine_frontlines, fetch_global_military_incidents

def fetch_geopolitics():
    logger.info("Fetching Geopolitics data...")
    try:
        frontlines = fetch_ukraine_frontlines()
        if frontlines:
            latest_data['frontlines'] = frontlines

        gdelt = fetch_global_military_incidents()
        if gdelt is not None:
            latest_data['gdelt'] = gdelt
    except Exception as e:
        logger.error(f"Error fetching geopolitics: {e}")

def update_liveuamap():
    logger.info("Running scheduled Liveuamap scraper...")
    try:
        from services.liveuamap_scraper import fetch_liveuamap
        res = fetch_liveuamap()
        if res:
            latest_data['liveuamap'] = res
    except Exception as e:
        logger.error(f"Liveuamap scraper error: {e}")

# ---------------------------------------------------------------------------
# OSINT Agent — host-side tool integration
# ---------------------------------------------------------------------------
def fetch_osint_kismet():
    """Fetch WiFi/BT devices from Kismet via OSINT agent."""
    try:
        from services.osint_bridge import fetch_kismet_devices
        devices = fetch_kismet_devices()
        if isinstance(devices, list):
            with _data_lock:
                latest_data['kismet_devices'] = devices
            logger.info(f"OSINT Kismet: {len(devices)} devices")
    except Exception as e:
        logger.debug(f"OSINT Kismet unavailable: {e}")

def fetch_osint_snort():
    """Fetch IDS alerts from Snort via OSINT agent."""
    try:
        from services.osint_bridge import fetch_snort_alerts
        alerts = fetch_snort_alerts()
        if isinstance(alerts, list):
            with _data_lock:
                latest_data['snort_alerts'] = alerts
            logger.info(f"OSINT Snort: {len(alerts)} alerts")
    except Exception as e:
        logger.debug(f"OSINT Snort unavailable: {e}")

def fetch_osint_nmap():
    """Fetch last nmap scan results via OSINT agent."""
    try:
        from services.osint_bridge import fetch_nmap_results
        hosts = fetch_nmap_results()
        if isinstance(hosts, list):
            with _data_lock:
                latest_data['nmap_hosts'] = hosts
            logger.info(f"OSINT Nmap: {len(hosts)} hosts")
    except Exception as e:
        logger.debug(f"OSINT Nmap unavailable: {e}")

def fetch_osint_nuclei():
    """Fetch last nuclei scan results via OSINT agent."""
    try:
        from services.osint_bridge import fetch_nuclei_results
        vulns = fetch_nuclei_results()
        if isinstance(vulns, list):
            with _data_lock:
                latest_data['nuclei_vulns'] = vulns
            logger.info(f"OSINT Nuclei: {len(vulns)} vulns")
    except Exception as e:
        logger.debug(f"OSINT Nuclei unavailable: {e}")


def update_fast_data():
    """Fast-tier: moving entities that need frequent updates (every 60s)."""
    logger.info("Fast-tier data update starting...")
    fast_funcs = [
        fetch_flights,
        fetch_military_flights,
        fetch_ships,
        fetch_uavs,
        fetch_satellites,
        fetch_news,
    ]
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(fast_funcs)) as executor:
        futures = [executor.submit(func) for func in fast_funcs]
        concurrent.futures.wait(futures)
    with _data_lock:
        latest_data['last_updated'] = datetime.utcnow().isoformat()
    logger.info("Fast-tier update complete.")

def update_slow_data():
    """Slow-tier: feeds that change infrequently (every 30min)."""
    logger.info("Slow-tier data update starting...")
    slow_funcs = [
        fetch_defense_stocks,
        fetch_oil_prices,
        fetch_weather,
        fetch_cctv,
        fetch_earthquakes,
        fetch_geopolitics,
        fetch_tfrs,
        fetch_weather_alerts,
        fetch_natural_events,
        fetch_firms_hotspots,
        fetch_power_outages,
        fetch_internet_outages,
        fetch_air_quality,
        fetch_space_weather,
        fetch_radioactivity,
        fetch_military_bases,
        fetch_nuclear_facilities,
        fetch_submarine_cables,
        fetch_embassies,
        fetch_volcanoes,
        fetch_piracy_incidents,
        fetch_border_crossings,
        fetch_cyber_threats,
        fetch_reservoirs,
        fetch_cell_towers,
        fetch_acled_conflicts,
        fetch_social_media_osint,
        fetch_noaa_weather_radio,
        fetch_kiwisdr_nodes,
    ]
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(slow_funcs)) as executor:
        futures = [executor.submit(func) for func in slow_funcs]
        concurrent.futures.wait(futures)
    logger.info("Slow-tier update complete.")

def update_all_data():
    """Full update — runs on startup. Fast and slow tiers run IN PARALLEL for fastest startup."""
    logger.info("Full data update starting (parallel)...")
    fetch_airports()  # Cached after first download
    # Run fast + slow in parallel so the user sees data ASAP
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        f1 = pool.submit(update_fast_data)
        f2 = pool.submit(update_slow_data)
        concurrent.futures.wait([f1, f2])
    logger.info("Full data update complete.")

scheduler = BackgroundScheduler()

def start_scheduler():
    init_db()

    # Start Check Point ThreatCloud real-time SSE feed
    start_checkpoint_feed()

    # Run full update once on startup
    scheduler.add_job(update_all_data, 'date', run_date=datetime.now())
    
    # Fast tier: every 60 seconds (flights, ships, military, satellites, UAVs)
    scheduler.add_job(update_fast_data, 'interval', seconds=60)
    
    # Slow tier: every 30 minutes (news, stocks, weather, geopolitics)
    scheduler.add_job(update_slow_data, 'interval', minutes=30)
    
    # CCTV pipeline has its own cadence
    def update_cctvs():
        logger.info("Running CCTV Pipeline Ingestion...")
        ingestors = [
            TFLJamCamIngestor,
            LTASingaporeIngestor,
            AustinTXIngestor,
            NYCDOTIngestor,
            TDOTSmartWayIngestor,
            ClarksvilleCityIngestor,
            KYTCFortCampbellIngestor,
            ClarksvilleAreaWebcamIngestor,
            NC5SkynetIngestor,
            WSMVWeatherCamIngestor,
            NPSSmokiesIngestor,
            ResortCamsTNIngestor,
            GatlinburgTouristIngestor,
            CaltransIngestor,
            FL511Ingestor,
            VDOTIngestor,
            LA511Ingestor,
            LAWetmetIngestor,
            KSLAStaticIngestor
        ]
        for ingestor in ingestors:
            try:
                ingestor().ingest()
            except Exception as e:
                logger.error(f"Failed {ingestor.__name__} cctv ingest: {e}")
        fetch_cctv()
            
    scheduler.add_job(update_cctvs, 'date', run_date=datetime.now())
    scheduler.add_job(update_cctvs, 'interval', minutes=1)
    
    # Liveuamap: startup + every 12 hours
    scheduler.add_job(update_liveuamap, 'date', run_date=datetime.now())
    scheduler.add_job(update_liveuamap, 'interval', hours=12)
    
    # Geopolitics (frontlines) more frequently than other slow data
    scheduler.add_job(fetch_geopolitics, 'interval', minutes=5)

    # OSINT Agent — host-side tools (graceful if agent not running)
    # Run once at startup, then on interval
    scheduler.add_job(fetch_osint_kismet, 'date', run_date=datetime.now())
    scheduler.add_job(fetch_osint_snort, 'date', run_date=datetime.now())
    scheduler.add_job(fetch_osint_nmap, 'date', run_date=datetime.now())
    scheduler.add_job(fetch_osint_nuclei, 'date', run_date=datetime.now())
    scheduler.add_job(fetch_osint_kismet, 'interval', seconds=30)
    scheduler.add_job(fetch_osint_snort, 'interval', seconds=60)
    scheduler.add_job(fetch_osint_nmap, 'interval', minutes=15)
    scheduler.add_job(fetch_osint_nuclei, 'interval', minutes=15)

    # Check Point live cyber threats — merge SSE buffer every 15s
    def update_cyber_threats_live():
        """Quick merge of Check Point SSE buffer into cyber_threats."""
        try:
            live_attacks = list(_checkpoint_attacks)
            with _data_lock:
                # Keep existing Feodo/ThreatFox, replace Check Point portion
                existing = [t for t in latest_data.get("cyber_threats", []) if t.get("source") != "checkpoint"]
                latest_data["cyber_threats"] = existing + live_attacks
                latest_data["checkpoint_stats"] = dict(_checkpoint_stats)
        except Exception:
            pass
    scheduler.add_job(update_cyber_threats_live, 'interval', seconds=15)

    scheduler.start()

def stop_scheduler():
    scheduler.shutdown()

def get_latest_data():
    with _data_lock:
        return dict(latest_data)

