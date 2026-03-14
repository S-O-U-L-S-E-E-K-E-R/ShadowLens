import sqlite3
import requests
from services.network_utils import fetch_with_curl
import logging
from abc import ABC, abstractmethod
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

DB_PATH = "cctv.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cameras (
            id TEXT PRIMARY KEY,
            source_agency TEXT,
            lat REAL,
            lon REAL,
            direction_facing TEXT,
            media_url TEXT,
            refresh_rate_seconds INTEGER,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

class BaseCCTVIngestor(ABC):
    def __init__(self):
        self.conn = sqlite3.connect(DB_PATH)

    @abstractmethod
    def fetch_data(self) -> List[Dict[str, Any]]:
        pass

    def ingest(self):
        try:
            cameras = self.fetch_data()
            cursor = self.conn.cursor()
            for cam in cameras:
                cursor.execute("""
                    INSERT INTO cameras 
                    (id, source_agency, lat, lon, direction_facing, media_url, refresh_rate_seconds)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                    media_url=excluded.media_url,
                    last_updated=CURRENT_TIMESTAMP
                """, (
                    cam.get("id"),
                    cam.get("source_agency"),
                    cam.get("lat"),
                    cam.get("lon"),
                    cam.get("direction_facing", "Unknown"),
                    cam.get("media_url"),
                    cam.get("refresh_rate_seconds", 60)
                ))
            self.conn.commit()
            logger.info(f"Successfully ingested {len(cameras)} cameras from {self.__class__.__name__}")
        except Exception as e:
            logger.error(f"Failed to ingest cameras in {self.__class__.__name__}: {e}")

class TFLJamCamIngestor(BaseCCTVIngestor):
    def fetch_data(self) -> List[Dict[str, Any]]:
        # Transport for London Open Data API
        url = "https://api.tfl.gov.uk/Place/Type/JamCam"
        response = fetch_with_curl(url, timeout=15)
        response.raise_for_status()
        
        data = response.json()
        cameras = []
        for item in data:
            # TfL returns URLs without protocols sometimes or with a base path
            vid_url = None
            img_url = None
            
            for prop in item.get('additionalProperties', []):
                if prop.get('key') == 'videoUrl':
                    vid_url = prop.get('value')
                elif prop.get('key') == 'imageUrl':
                    img_url = prop.get('value')
            
            media = vid_url if vid_url else img_url
            if media:
                cameras.append({
                    "id": f"TFL-{item.get('id')}",
                    "source_agency": "TfL",
                    "lat": item.get('lat'),
                    "lon": item.get('lon'),
                    "direction_facing": item.get('commonName', 'Unknown'),
                    "media_url": media,
                    "refresh_rate_seconds": 15
                })
        return cameras

class LTASingaporeIngestor(BaseCCTVIngestor):
    def fetch_data(self) -> List[Dict[str, Any]]:
        # Singapore Land Transport Authority (LTA) Traffic Images API
        url = "https://api.data.gov.sg/v1/transport/traffic-images"
        response = fetch_with_curl(url, timeout=15)
        response.raise_for_status()
        
        data = response.json()
        cameras = []
        if "items" in data and len(data["items"]) > 0:
            for item in data["items"][0].get("cameras", []):
                loc = item.get("location", {})
                if "latitude" in loc and "longitude" in loc and "image" in item:
                    cameras.append({
                        "id": f"SGP-{item.get('camera_id', 'UNK')}",
                        "source_agency": "Singapore LTA",
                        "lat": loc.get("latitude"),
                        "lon": loc.get("longitude"),
                        "direction_facing": f"Camera {item.get('camera_id')}",
                        "media_url": item.get("image"),
                        "refresh_rate_seconds": 60
                    })
        return cameras



class AustinTXIngestor(BaseCCTVIngestor):
    def fetch_data(self) -> List[Dict[str, Any]]:
        # City of Austin Traffic Cameras Open Data
        url = "https://data.austintexas.gov/resource/b4k4-adkb.json?$limit=2000"
        response = fetch_with_curl(url, timeout=15)
        response.raise_for_status()
        
        data = response.json()
        cameras = []
        for item in data:
            cam_id = item.get("camera_id")
            if not cam_id: continue
            
            loc = item.get("location", {})
            coords = loc.get("coordinates", [])
            
            # coords is usually [lon, lat]
            if len(coords) == 2:
                cameras.append({
                    "id": f"ATX-{cam_id}",
                    "source_agency": "Austin TxDOT",
                    "lat": coords[1],
                    "lon": coords[0],
                    "direction_facing": item.get("location_name", "Austin TX Camera"),
                    "media_url": f"https://cctv.austinmobility.io/image/{cam_id}.jpg",
                    "refresh_rate_seconds": 60
                })
        return cameras

class NYCDOTIngestor(BaseCCTVIngestor):
    def fetch_data(self) -> List[Dict[str, Any]]:
        url = "https://webcams.nyctmc.org/api/cameras"
        response = fetch_with_curl(url, timeout=15)
        response.raise_for_status()
        
        data = response.json()
        cameras = []
        for item in data:
            cam_id = item.get("id")
            if not cam_id: continue
            
            lat = item.get("latitude")
            lon = item.get("longitude")
            if lat and lon:
                cameras.append({
                    "id": f"NYC-{cam_id}",
                    "source_agency": "NYC DOT",
                    "lat": lat,
                    "lon": lon,
                    "direction_facing": item.get("name", "NYC Camera"),
                    "media_url": f"https://webcams.nyctmc.org/api/cameras/{cam_id}/image",
                    "refresh_rate_seconds": 30
                })
        return cameras

class TDOTSmartWayIngestor(BaseCCTVIngestor):
    """Tennessee DOT SmartWay — 666 cameras statewide (Nashville, Knoxville, Memphis, Chattanooga)."""
    API_URL = "https://www.tdot.tn.gov/opendata/api/public/RoadwayCameras"
    API_KEY = "8d3b7a82635d476795c09b2c41facc60"

    def fetch_data(self) -> List[Dict[str, Any]]:
        response = fetch_with_curl(self.API_URL, timeout=15, headers={"ApiKey": self.API_KEY})
        response.raise_for_status()

        data = response.json()
        cameras = []
        for item in data:
            if str(item.get("active", "")).lower() != "true":
                continue
            lat = item.get("lat")
            lng = item.get("lng")
            if not lat or not lng:
                continue

            # Prefer HLS stream, fall back to thumbnail snapshot
            media = item.get("httpsVideoUrl") or item.get("httpVideoUrl") or item.get("thumbnailUrl")
            if not media:
                continue

            jurisdiction = item.get("jurisdiction", "Tennessee")
            route = item.get("route", "")
            title = item.get("title", f"{route} Camera")

            cameras.append({
                "id": f"TDOT-{item.get('id')}",
                "source_agency": f"TDOT SmartWay ({jurisdiction})",
                "lat": lat,
                "lon": lng,
                "direction_facing": title,
                "media_url": media,
                "refresh_rate_seconds": 30
            })
        return cameras


class ClarksvilleCityIngestor(BaseCCTVIngestor):
    """City of Clarksville, TN traffic cameras via ipcamlive.com snapshots."""
    CAMERAS = [
        ("61310cec8872e", "Exit 11 (I-24/US-79)", 36.5830, -87.3180),
        ("613a762a8184d", "Exit 4 (I-24/US-41A Bypass)", 36.5540, -87.3720),
        ("614a400064a41", "Peachers Mill Rd & 101st Airborne Div Pkwy", 36.5640, -87.3850),
        ("61310c8c412d5", "Peachers Mill Rd & Providence Blvd", 36.5520, -87.3780),
        ("68396965be373", "Peachers Mill Rd & Tiny Town Rd", 36.5750, -87.3950),
        ("61310b91aac5c", "2nd St & Riverside Dr", 36.5310, -87.3595),
        ("61310c11c88f4", "Wilma Rudolph Blvd & Forrest Hills Dr", 36.5710, -87.3380),
        ("61310bc852732", "Wilma Rudolph Blvd & Terminal Rd", 36.5620, -87.3290),
        ("6138e5bb22549", "Madison St & Hwy 76", 36.5470, -87.3100),
        ("64f77b13b6139", "Fire Station Rd & Hwy 76", 36.5500, -87.2700),
        ("654bec1f29e78", "Trenton Rd & Spring Creek Pkwy", 36.5880, -87.3300),
        ("654becee17d17", "Whitfield Rd & 101st Airborne Div Pkwy", 36.5700, -87.4100),
        ("6839cd98c0e23", "Ft. Campbell Blvd & Tiny Town Rd", 36.5850, -87.4200),
        ("6839ce06c0b9c", "Trenton Rd & Tiny Town Rd", 36.5950, -87.3500),
    ]

    def fetch_data(self) -> List[Dict[str, Any]]:
        cameras = []
        for alias, name, lat, lon in self.CAMERAS:
            cameras.append({
                "id": f"CLK-{alias[:8]}",
                "source_agency": "Clarksville TN",
                "lat": lat,
                "lon": lon,
                "direction_facing": name,
                "media_url": f"https://ipcamlive.com/player/snapshot.php?alias={alias}",
                "refresh_rate_seconds": 120
            })
        return cameras


class KYTCFortCampbellIngestor(BaseCCTVIngestor):
    """KYTC/TRIMARC cameras around Fort Campbell, KY."""
    CAMERAS = [
        ("CCTV_02_US41ALT_0003", "US 41 SB @ Gate 4 Ft Campbell", 36.644468, -87.437173),
        ("CCTV_02_US41ALT_0000", "US 41 @ State Line Rd", 36.640966, -87.436028),
        ("CCTV_02_US41ALT_0010", "US 41 ALT NB @ MP 1.0", 36.654513, -87.440427),
        ("CCTV_02_US41ALT_0025", "US 41 @ Gate 7 Ft Campbell", 36.676534, -87.446923),
        ("CCTV_02_US41ALT_0028", "US 41 SB @ Gate 7 Ft Campbell", 36.678014, -87.447352),
        ("CCTV_02_US41ALT_0045", "US 41 NB @ I-24 Overpass", 36.704193, -87.455099),
        ("CCTV_02_US41ALT_0135", "US 41 NB @ Pennyrile Overpass", 36.831821, -87.472866),
        ("CCTV_02_KY911_0001", "KY 911 WB @ Screaming Eagle Blvd", 36.665415, -87.440701),
        ("CCTV_02_24_0926", "I-24 WB @ MP 92.6", 36.648675, -87.350857),
    ]

    def fetch_data(self) -> List[Dict[str, Any]]:
        cameras = []
        for cam_id, name, lat, lon in self.CAMERAS:
            cameras.append({
                "id": f"KYTC-{cam_id}",
                "source_agency": "KYTC Fort Campbell",
                "lat": lat,
                "lon": lon,
                "direction_facing": name,
                "media_url": f"https://www.trimarc.org/images/milestone/{cam_id}.jpg",
                "refresh_rate_seconds": 60
            })
        return cameras


class ClarksvilleAreaWebcamIngestor(BaseCCTVIngestor):
    """Additional community/news webcams around the Clarksville-Fort Campbell region."""
    CAMERAS = [
        ("HOPK-SKYLINE", "Hopkinsville KY Skyline", 36.8655, -87.4889,
         "https://camstreamer.com/embed/1TYFkRuIEQt9xwhJTd3JLDRJdQoNr13bgzlQHpI3"),
        ("CADIZ-MAIN", "Cadiz KY Downtown Main St", 36.866, -87.835,
         "https://www.youtube.com/embed/nNK_Ks6XAfU"),
        ("CLK-DWNTWN", "Clarksville Downtown Commons", 36.5286, -87.3583,
         "https://www.youtube.com/embed/7Alo1kted1M"),
    ]

    def fetch_data(self) -> List[Dict[str, Any]]:
        cameras = []
        for cam_id, name, lat, lon, url in self.CAMERAS:
            cameras.append({
                "id": cam_id,
                "source_agency": "Community Webcam",
                "lat": lat,
                "lon": lon,
                "direction_facing": name,
                "media_url": url,
                "refresh_rate_seconds": 300
            })
        return cameras


class NC5SkynetIngestor(BaseCCTVIngestor):
    """NewsChannel 5 Skynet weather cameras — live HLS via wetmet.net signed tokens."""
    import re as _re

    # (wetmet_uid, name, lat, lon)
    CAMERAS = [
        ("bc96b515e35c6ce61b1dee41c5221459", "NC5 Clarksville", 36.5297, -87.3595),
        ("7f9e5ba3df3a2bdc98cf75dd8c381a78", "NC5 Hopkinsville KY", 36.8655, -87.4889),
        ("964042cef2f7abd0d96aeb924edf740e", "NC5 Dickson", 36.077, -87.387),
        ("7df258412b45c8abd3f71048134a9ce1", "NC5 Columbia", 35.6151, -87.0353),
        ("5d9ad72fba7d263d610c72ea835f27dc", "NC5 Cookeville", 36.1628, -85.5016),
        ("ac0e41cfe7f27c0a16b1f48accfa848c", "NC5 Franklin", 35.9251, -86.8689),
        ("fba376469c1f281a2a9a22a2f800ef60", "NC5 Gallatin", 36.3884, -86.4466),
        ("27a3ebfbb2fd9e818eed58bfa68ad1ff", "NC5 Lebanon", 36.2081, -86.2911),
        ("cccd7433c66548f26eda074d65d7107d", "NC5 Murfreesboro", 35.8456, -86.3903),
        ("e6e9ca1b082ffa211279348d590f0daa", "NC5 Nashville", 36.1627, -86.7816),
        ("ce41f7a597d707fe305acddf98ba595e", "NC5 Downtown Nashville", 36.1627, -86.7766),
        ("34228c9b3248f8fad664765ce5ec637a", "NC5 Acme Feed & Seed Nashville", 36.1615, -86.7745),
        ("8d1cc18aa9e1373a08f9a1eb3da6adff", "NC5 First Horizon Park Nashville", 36.1703, -86.7886),
        ("40ac8b4402caeda392799bc388fededd", "NC5 Nashville Shores", 36.1320, -86.6220),
    ]

    def _get_hls_url(self, uid: str) -> str:
        """Fetch the wetmet widget page and extract the signed HLS URL."""
        import re
        try:
            resp = fetch_with_curl(f"https://api.wetmet.net/widgets/stream/frame.php?uid={uid}", timeout=10)
            match = re.search(r"var vurl = '(https://[^']+\.m3u8[^']*)'", resp.text)
            if match:
                return match.group(1)
        except Exception as e:
            logger.warning(f"NC5 wetmet fetch failed for {uid}: {e}")
        return ""

    def fetch_data(self) -> List[Dict[str, Any]]:
        cameras = []
        for uid, name, lat, lon in self.CAMERAS:
            hls_url = self._get_hls_url(uid)
            if not hls_url:
                continue
            cameras.append({
                "id": f"NC5-{uid[:8]}",
                "source_agency": "NewsChannel 5 Skynet",
                "lat": lat,
                "lon": lon,
                "direction_facing": name,
                "media_url": hls_url,
                "refresh_rate_seconds": 1800  # token valid ~30 min
            })
        return cameras


class WSMVWeatherCamIngestor(BaseCCTVIngestor):
    """WSMV Channel 4 weather cameras — YouTube live embeds."""
    CAMERAS = [
        ("WSMV-NASH-DT", "WSMV Downtown Nashville", 36.1627, -86.7816,
         "https://www.youtube.com/embed/ATbtGvbExP4"),
        ("WSMV-NASH-W", "WSMV West Nashville", 36.1560, -86.8450,
         "https://www.youtube.com/embed/802ZoL3nrg8"),
        ("WSMV-NOLENS", "WSMV Nolensville", 35.9523, -86.6694,
         "https://www.youtube.com/embed/jDZSTsuyzoc"),
        ("WSMV-CLK", "WSMV Clarksville F&M Bank", 36.5297, -87.3595,
         "https://www.youtube.com/embed/7Alo1kted1M"),
        ("WSMV-NASH-S", "WSMV Downtown South View", 36.1580, -86.7780,
         "https://www.youtube.com/embed/s3ObT04gzlo"),
        ("WSMV-NASH-NE", "WSMV Downtown Northeast View", 36.1680, -86.7700,
         "https://www.youtube.com/embed/Gw0FXKfyBno"),
    ]

    def fetch_data(self) -> List[Dict[str, Any]]:
        cameras = []
        for cam_id, name, lat, lon, url in self.CAMERAS:
            cameras.append({
                "id": cam_id,
                "source_agency": "WSMV Channel 4",
                "lat": lat,
                "lon": lon,
                "direction_facing": name,
                "media_url": url,
                "refresh_rate_seconds": 300
            })
        return cameras


class LA511Ingestor(BaseCCTVIngestor):
    """Louisiana DOTD 511 — ~336 cameras with HLS streams statewide."""
    ICONS_URL = "https://511la.org/map/mapIcons/Cameras"
    TOOLTIP_URL = "https://511la.org/tooltip/Cameras/{cam_id}"

    def fetch_data(self) -> List[Dict[str, Any]]:
        import re
        try:
            resp = fetch_with_curl(self.ICONS_URL, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            items = data.get("item2", data.get("item1", []))
            if isinstance(data, list):
                items = data
        except Exception as e:
            logger.warning(f"LA511 icons fetch failed: {e}")
            return []

        cameras = []
        for item in items:
            cam_id = item.get("itemId")
            loc = item.get("location", [])
            if not cam_id or len(loc) < 2:
                continue
            lat, lon = loc[0], loc[1]

            # Fetch tooltip for name + HLS URL
            name = f"LA Camera {cam_id}"
            media = ""
            try:
                tip = fetch_with_curl(self.TOOLTIP_URL.format(cam_id=cam_id), timeout=5)
                html = tip.text
                # Extract name
                name_match = re.search(r'data-fs-title="([^"]+)"', html)
                if name_match:
                    name = name_match.group(1)
                # Extract HLS URL
                url_match = re.search(r'data-videourl="([^"]+\.m3u8[^"]*)"', html)
                if url_match:
                    media = url_match.group(1)
                # Fallback to snapshot image
                if not media:
                    img_match = re.search(r'data-lazy="(/map/Cctv/[^"]+)"', html)
                    if img_match:
                        media = f"https://511la.org{img_match.group(1)}"
            except Exception:
                pass

            if not media:
                continue

            cameras.append({
                "id": f"LA511-{cam_id}",
                "source_agency": "LA DOTD 511",
                "lat": lat,
                "lon": lon,
                "direction_facing": name,
                "media_url": media,
                "refresh_rate_seconds": 30
            })
        return cameras


class LAWetmetIngestor(BaseCCTVIngestor):
    """Louisiana TV station weather cameras — wetmet.net HLS + static images."""
    # (uid, name, lat, lon)
    CAMERAS = [
        # WAFB Baton Rouge
        ("bbe5daec661dbf8916c7023eced6535a", "WAFB Our Lady of the Lake Essen", 30.4100, -91.1550),
        ("ac755b628025f38d166712996a7535e1", "WAFB Our Lady of the Lake Livingston", 30.5020, -90.7510),
        ("ba5c5d389f06a57bb89f5c20123bec18", "WAFB L'Auberge Casino Baton Rouge", 30.4460, -91.1870),
        ("839e2564099671a2cd045181d6652504", "WAFB False River New Roads", 30.7020, -91.4370),
        ("02ca6c028bee6c8e7ee076bc93345289", "WAFB Port Allen City Hall", 30.4520, -91.2100),
        # KALB Alexandria
        ("8f586e9d33b1ee476b59d3c12dcb7c09", "KALB AEX Airport Alexandria", 31.3274, -92.5486),
        ("c5174fcaf4aae4cc467772d6b1f6d2d0", "KALB Pineville", 31.3224, -92.4343),
        ("f5b2e068bf500a40ff9811ab8cd0e4e3", "KALB Marksville", 31.1277, -92.0662),
        ("53d13e01ddd1216b9580ce11a90e4b81", "KALB Alexandria", 31.3113, -92.4451),
        # KPLC Lake Charles
        ("0013a45b516be4a854155269398b7289", "KPLC South Lake Charles", 30.2266, -93.2174),
        ("eb5c08d2784b7e23b1a1714d14826351", "KPLC Jennings", 30.2224, -92.6571),
        ("00c66b20e8c841a102bcc0bdd88c3ece", "KPLC DeRidder (nr Fort Johnson)", 30.8463, -93.2891),
    ]

    def _get_hls_url(self, uid: str) -> str:
        import re
        try:
            resp = fetch_with_curl(f"https://api.wetmet.net/widgets/stream/frame.php?uid={uid}", timeout=10)
            match = re.search(r"var vurl = '(https://[^']+\.m3u8[^']*)'", resp.text)
            if match:
                return match.group(1)
        except Exception as e:
            logger.warning(f"LA wetmet fetch failed for {uid}: {e}")
        return ""

    def fetch_data(self) -> List[Dict[str, Any]]:
        cameras = []
        for uid, name, lat, lon in self.CAMERAS:
            hls_url = self._get_hls_url(uid)
            if not hls_url:
                # Fallback to static image
                hls_url = f"https://api.wetmet.net/widgets/image/frame.php?uid={uid}&type=image&format=image.jpg"
            cameras.append({
                "id": f"LAWX-{uid[:8]}",
                "source_agency": "LA Weather Cam",
                "lat": lat,
                "lon": lon,
                "direction_facing": name,
                "media_url": hls_url,
                "refresh_rate_seconds": 1800
            })
        return cameras


class KSLAStaticIngestor(BaseCCTVIngestor):
    """KSLA Shreveport static weather camera images."""
    CAMERAS = [
        ("KSLA-SHV", "KSLA Shreveport Skycam", 32.5252, -93.7502,
         "https://webpubcontent.gray.tv/ksla/weather/kslaskycam.jpg"),
        ("KSLA-TXK", "KSLA Texarkana", 33.4418, -94.0477,
         "https://webpubcontent.gray.tv/ksla/weather/texarkana.jpg"),
    ]

    def fetch_data(self) -> List[Dict[str, Any]]:
        cameras = []
        for cam_id, name, lat, lon, url in self.CAMERAS:
            cameras.append({
                "id": cam_id,
                "source_agency": "LA Weather Cam",
                "lat": lat,
                "lon": lon,
                "direction_facing": name,
                "media_url": url,
                "refresh_rate_seconds": 300
            })
        return cameras


class NPSSmokiesIngestor(BaseCCTVIngestor):
    """Great Smoky Mountains National Park webcams — direct JPEG snapshots."""
    CAMERAS = [
        ("NPS-GRSM-LR", "Smokies Look Rock", 35.634, -83.943,
         "https://www.nps.gov/featurecontent/ard/webcams/images/grsm.jpg"),
        ("NPS-GRSM-KW", "Smokies Kuwohi (Clingmans Dome)", 35.563, -83.498,
         "https://www.nps.gov/featurecontent/ard/webcams/images/grcd.jpg"),
        ("NPS-GRSM-PK", "Smokies Purchase Knob", 35.584, -83.073,
         "https://www.nps.gov/featurecontent/ard/webcams/images/grpk.jpg"),
        ("NPS-GRSM-NG", "Smokies Newfound Gap", 35.611, -83.425,
         "https://grsmnfgap.air-resource.net/gsng.jpg"),
    ]

    def fetch_data(self) -> List[Dict[str, Any]]:
        cameras = []
        for cam_id, name, lat, lon, url in self.CAMERAS:
            cameras.append({
                "id": cam_id,
                "source_agency": "NPS Great Smokies",
                "lat": lat,
                "lon": lon,
                "direction_facing": name,
                "media_url": url,
                "refresh_rate_seconds": 900
            })
        return cameras


class ResortCamsTNIngestor(BaseCCTVIngestor):
    """ResortCams.com Tennessee — live stream thumbnails."""
    CAMERAS = [
        ("RC-GATSUM", "Gatlinburg Summit", 35.715, -83.515, "gatlinburgsummit"),
        ("RC-BOONE", "Boone Lake", 36.415, -82.434, "boonelake"),
        ("RC-BUFFALO", "Buffalo Mountain", 36.335, -82.301, "buffalomountain"),
        ("RC-GRNVL", "Greeneville", 36.163, -82.831, "greeneville"),
        ("RC-LAFOL", "LaFollette", 36.382, -84.120, "lafollette"),
    ]

    def fetch_data(self) -> List[Dict[str, Any]]:
        cameras = []
        for cam_id, name, lat, lon, stream in self.CAMERAS:
            url = f"https://stream.resortcams.com/thumbnail?application=live&streamname={stream}.stream&size=1280x720"
            try:
                resp = fetch_with_curl(url, timeout=5)
                if resp.status_code != 200:
                    continue
            except Exception:
                continue
            cameras.append({
                "id": cam_id,
                "source_agency": "ResortCams",
                "lat": lat,
                "lon": lon,
                "direction_facing": name,
                "media_url": url,
                "refresh_rate_seconds": 60
            })
        return cameras


class GatlinburgTouristIngestor(BaseCCTVIngestor):
    """Gatlinburg/Pigeon Forge/Sevierville tourist cameras."""
    CAMERAS = [
        ("GAT-ANAKSTA", "Anakeesta AnaVista 360 Gatlinburg", 35.712, -83.514,
         "https://anakeesta.roundshot.com/"),
        ("GAT-SKYLIFT", "SkyLift Park Gatlinburg", 35.710, -83.515,
         "https://cdn.skylinewebcams.com/live4212.jpg"),
        ("GAT-FIREFLY", "Anakeesta Firefly Village", 35.712, -83.514,
         "https://cdn.skylinewebcams.com/live5213.jpg"),
        ("PF-GRAVITY", "Pigeon Forge Outdoor Gravity Park", 35.810, -83.575,
         "https://cdn.skylinewebcams.com/live5537.jpg"),
        ("JB-JONES", "Jonesborough TN", 36.294, -82.474,
         "https://cdn.skylinewebcams.com/live4213.jpg"),
        ("NASH-SKYLINE1", "Nashville Downtown Skyline", 36.162, -86.778,
         "https://cdn.skylinewebcams.com/live4584.jpg"),
    ]

    def fetch_data(self) -> List[Dict[str, Any]]:
        cameras = []
        for cam_id, name, lat, lon, url in self.CAMERAS:
            cameras.append({
                "id": cam_id,
                "source_agency": "Tourist Webcam",
                "lat": lat,
                "lon": lon,
                "direction_facing": name,
                "media_url": url,
                "refresh_rate_seconds": 600
            })
        return cameras


class CaltransIngestor(BaseCCTVIngestor):
    """Caltrans (California DOT) — ~3,400 cameras with HLS streams across 12 districts."""
    DISTRICTS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]

    def fetch_data(self) -> List[Dict[str, Any]]:
        cameras = []
        for dist in self.DISTRICTS:
            dn = f"{dist:02d}"
            url = f"https://cwwp2.dot.ca.gov/data/d{dist}/cctv/cctvStatusD{dn}.json"
            try:
                resp = fetch_with_curl(url, timeout=15)
                resp.raise_for_status()
                data = resp.json().get("data", [])
                for item in data:
                    cctv = item.get("cctv", item)
                    loc = cctv.get("location", {})
                    img = cctv.get("imageData", {})
                    lat = loc.get("latitude")
                    lon = loc.get("longitude")
                    if not lat or not lon:
                        continue
                    if str(cctv.get("inService", "")).lower() != "true":
                        continue
                    media = img.get("streamingVideoURL") or img.get("static", {}).get("currentImageURL", "")
                    if not media:
                        continue
                    name = loc.get("locationName", f"D{dist} Camera")
                    cameras.append({
                        "id": f"CALTR-D{dist}-{cctv.get('index', len(cameras))}",
                        "source_agency": f"Caltrans D{dist}",
                        "lat": float(lat),
                        "lon": float(lon),
                        "direction_facing": name,
                        "media_url": media,
                        "refresh_rate_seconds": 30
                    })
            except Exception as e:
                logger.warning(f"Caltrans D{dist} fetch failed: {e}")
        return cameras


class FL511Ingestor(BaseCCTVIngestor):
    """Florida 511 traffic cameras — ~4,600 cameras via ArcGIS."""
    API_URL = "https://services.arcgis.com/3wFbqsFPLeKqOlIK/arcgis/rest/services/FL511_Traffic_Cameras/FeatureServer/0/query"

    def fetch_data(self) -> List[Dict[str, Any]]:
        cameras = []
        offset = 0
        while True:
            params = f"?where=1%3D1&outFields=*&f=json&resultRecordCount=2000&resultOffset={offset}"
            try:
                resp = fetch_with_curl(self.API_URL + params, timeout=20)
                resp.raise_for_status()
                data = resp.json()
                features = data.get("features", [])
                if not features:
                    break
                for feat in features:
                    attrs = feat.get("attributes", {})
                    lat = attrs.get("LATITUDE")
                    lon = attrs.get("LONGITUDE")
                    img = attrs.get("IMAGE")
                    if not lat or not lon or not img:
                        continue
                    cameras.append({
                        "id": f"FL511-{attrs.get('ID', len(cameras))}",
                        "source_agency": "FL511",
                        "lat": lat,
                        "lon": lon,
                        "direction_facing": attrs.get("DESCRIPT", "FL Camera"),
                        "media_url": img,
                        "refresh_rate_seconds": 60
                    })
                offset += len(features)
                if not data.get("exceededTransferLimit", False):
                    break
            except Exception as e:
                logger.warning(f"FL511 fetch failed at offset {offset}: {e}")
                break
        return cameras


class VDOTIngestor(BaseCCTVIngestor):
    """Virginia DOT cameras via Iteris GeoJSON feed."""

    def fetch_data(self) -> List[Dict[str, Any]]:
        url = "http://files4.iteriscdn.com/WebApps/VA/SafeTravel/data/local/icons/metadata/icons.cameras.geojsonp"
        try:
            resp = fetch_with_curl(url, timeout=15)
            resp.raise_for_status()
            import re, json as _json
            # Strip JSONP callback wrapper
            text = resp.text.strip()
            match = re.search(r'\((\{.*\})\)', text, re.DOTALL)
            if not match:
                return []
            data = _json.loads(match.group(1))
            cameras = []
            for feat in data.get("features", []):
                coords = feat.get("geometry", {}).get("coordinates", [])
                props = feat.get("properties", {})
                if len(coords) < 2:
                    continue
                cam_id = props.get("id", "")
                # Try to get image URL from the properties
                views = props.get("views", [])
                media = ""
                if views:
                    media = views[0].get("src", "") if isinstance(views[0], dict) else ""
                if not media:
                    media = props.get("image_url", props.get("url", ""))
                cameras.append({
                    "id": f"VDOT-{cam_id}",
                    "source_agency": "VDOT",
                    "lat": coords[1],
                    "lon": coords[0],
                    "direction_facing": props.get("description", props.get("location_description", "VA Camera")),
                    "media_url": media,
                    "refresh_rate_seconds": 60
                })
            return cameras
        except Exception as e:
            logger.warning(f"VDOT fetch failed: {e}")
            return []


class GlobalOSMCrawlingIngestor(BaseCCTVIngestor):
    def fetch_data(self) -> List[Dict[str, Any]]:
        # This will pull physical street surveillance cameras across all global hotspots
        # using OpenStreetMap Overpass mapping their exact geospatial coordinates to Google Street View
        regions = [
            ("35.6,139.6,35.8,139.8", "Tokyo"),
            ("48.8,2.3,48.9,2.4", "Paris"),
            ("40.6,-74.1,40.8,-73.9", "NYC Expanded"),
            ("34.0,-118.4,34.2,-118.2", "Los Angeles"),
            ("-33.9,151.1,-33.7,151.3", "Sydney"),
            ("52.4,13.3,52.6,13.5", "Berlin"),
            ("25.1,55.2,25.3,55.4", "Dubai"),
            ("19.3,-99.2,19.5,-99.0", "Mexico City"),
            ("-23.6,-46.7,-23.4,-46.5", "Sao Paulo"),
            ("39.6,-105.1,39.9,-104.8", "Denver")
        ]
        
        query_parts = [f'node["man_made"="surveillance"]({bbox});' for bbox, city in regions]
        query = "".join(query_parts)
        url = f"https://overpass-api.de/api/interpreter?data=[out:json];({query});out%202000;"
        
        try:
            response = fetch_with_curl(url, timeout=15)
            response.raise_for_status()
            data = response.json()
            
            cameras = []
            for item in data.get('elements', []):
                lat = item.get("lat")
                lon = item.get("lon")
                cam_id = item.get("id")
                
                if lat and lon:
                    # Find which city this belongs to
                    source_city = "Global OSINT"
                    for bbox, city in regions:
                        s, w, n, e = map(float, bbox.split(','))
                        if s <= lat <= n and w <= lon <= e:
                            source_city = f"OSINT: {city}"
                            break
                            
                    # Attempt to parse camera direction for a cool realistic bearing angle if OSM mapped it
                    direction_str = item.get("tags", {}).get("camera:direction", "0")
                    try:
                        bearing = int(float(direction_str))
                    except:
                        bearing = 0
                        
                    mapbox_key = "YOUR_MAPBOX_TOKEN_HERE"
                    mapbox_url = f"https://api.mapbox.com/styles/v1/mapbox/satellite-streets-v12/static/{lon},{lat},18,{bearing},60/600x400?access_token={mapbox_key}"
                    
                    cameras.append({
                        "id": f"OSM-{cam_id}",
                        "source_agency": source_city,
                        "lat": lat,
                        "lon": lon,
                        "direction_facing": item.get("tags", {}).get("surveillance:type", "Street Level Camera"),
                        "media_url": mapbox_url,
                        "refresh_rate_seconds": 3600
                    })
            return cameras
        except Exception:
            return []



def _detect_media_type(url: str) -> str:
    """Detect the media type from a camera URL for proper frontend rendering."""
    if not url:
        return "image"
    url_lower = url.lower()
    if any(ext in url_lower for ext in ['.mp4', '.webm', '.ogg']):
        return "video"
    if any(kw in url_lower for kw in ['.mjpg', '.mjpeg', 'mjpg', 'axis-cgi/mjpg', 'mode=motion']):
        return "mjpeg"
    if '.m3u8' in url_lower or 'hls' in url_lower:
        return "hls"
    if any(kw in url_lower for kw in ['embed', 'maps/embed', 'iframe']):
        return "embed"
    if 'mapbox.com' in url_lower or 'satellite' in url_lower:
        return "satellite"
    return "image"

def get_all_cameras() -> List[Dict[str, Any]]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM cameras")
    rows = cursor.fetchall()
    conn.close()
    cameras = []
    for row in rows:
        cam = dict(row)
        cam['media_type'] = _detect_media_type(cam.get('media_url', ''))
        cameras.append(cam)
    return cameras

