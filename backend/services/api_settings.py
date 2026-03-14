"""
API Settings management — serves the API key registry and allows updates.
Keys are stored in the backend .env file and loaded via python-dotenv.
"""
import os
import re
from pathlib import Path

# Path to the backend .env file
ENV_PATH = Path(__file__).parent.parent / ".env"

# ---------------------------------------------------------------------------
# API Registry — every external service the dashboard depends on
# ---------------------------------------------------------------------------
API_REGISTRY = [
    {
        "id": "opensky_client_id",
        "env_key": "OPENSKY_CLIENT_ID",
        "name": "OpenSky Network — Client ID",
        "description": "OAuth2 client ID for the OpenSky Network API. Provides global flight state vectors with 400 requests/day.",
        "category": "Aviation",
        "url": "https://opensky-network.org/",
        "required": True,
    },
    {
        "id": "opensky_client_secret",
        "env_key": "OPENSKY_CLIENT_SECRET",
        "name": "OpenSky Network — Client Secret",
        "description": "OAuth2 client secret paired with the Client ID above. Used for authenticated token refresh.",
        "category": "Aviation",
        "url": "https://opensky-network.org/",
        "required": True,
    },
    {
        "id": "ais_api_key",
        "env_key": "AIS_API_KEY",
        "name": "AIS Stream",
        "description": "WebSocket API key for real-time Automatic Identification System (AIS) vessel tracking data worldwide.",
        "category": "Maritime",
        "url": "https://aisstream.io/",
        "required": True,
    },
    {
        "id": "adsb_lol",
        "env_key": None,
        "name": "ADS-B Exchange (adsb.lol)",
        "description": "Community-maintained ADS-B flight tracking API. No key required — public endpoint.",
        "category": "Aviation",
        "url": "https://api.adsb.lol/",
        "required": False,
    },
    {
        "id": "usgs_earthquakes",
        "env_key": None,
        "name": "USGS Earthquake Hazards",
        "description": "Real-time earthquake data feed from the United States Geological Survey. No key required.",
        "category": "Geophysical",
        "url": "https://earthquake.usgs.gov/",
        "required": False,
    },
    {
        "id": "celestrak",
        "env_key": None,
        "name": "CelesTrak (NORAD TLEs)",
        "description": "Satellite orbital element data from CelesTrak. Provides TLE sets for 2,000+ active satellites. No key required.",
        "category": "Space",
        "url": "https://celestrak.org/",
        "required": False,
    },
    {
        "id": "gdelt",
        "env_key": None,
        "name": "GDELT Project",
        "description": "Global Database of Events, Language, and Tone. Monitors news media for geopolitical events worldwide. No key required.",
        "category": "Intelligence",
        "url": "https://www.gdeltproject.org/",
        "required": False,
    },
    {
        "id": "nominatim",
        "env_key": None,
        "name": "Nominatim (OpenStreetMap)",
        "description": "Reverse geocoding service. Converts lat/lng coordinates to human-readable location names. No key required.",
        "category": "Geolocation",
        "url": "https://nominatim.openstreetmap.org/",
        "required": False,
    },
    {
        "id": "rainviewer",
        "env_key": None,
        "name": "RainViewer",
        "description": "Weather radar tile overlay. Provides global precipitation data as map tiles. No key required.",
        "category": "Weather",
        "url": "https://www.rainviewer.com/",
        "required": False,
    },
    {
        "id": "rss_feeds",
        "env_key": None,
        "name": "RSS News Feeds",
        "description": "Aggregates from NPR, BBC, Al Jazeera, NYT, Reuters, and AP for global news coverage. No key required.",
        "category": "Intelligence",
        "url": None,
        "required": False,
    },
    {
        "id": "yfinance",
        "env_key": None,
        "name": "Yahoo Finance (yfinance)",
        "description": "Defense sector stock tickers and commodity prices. Uses the yfinance Python library. No key required.",
        "category": "Markets",
        "url": "https://finance.yahoo.com/",
        "required": False,
    },
    {
        "id": "openmhz",
        "env_key": None,
        "name": "OpenMHz",
        "description": "Public radio scanner feeds for SIGINT interception. Streams police/fire/EMS radio traffic. No key required.",
        "category": "SIGINT",
        "url": "https://openmhz.com/",
        "required": False,
    },
    # ---- OSINT Tools ----
    {
        "id": "hibp_api_key",
        "env_key": "HIBP_API_KEY",
        "name": "Have I Been Pwned",
        "description": "Breach database API by Troy Hunt. Checks emails against 700+ data breaches and paste sites. Required for email OSINT.",
        "category": "OSINT",
        "url": "https://haveibeenpwned.com/API/Key",
        "required": True,
    },
    {
        "id": "shodan_api_key",
        "env_key": "SHODAN_API_KEY",
        "name": "Shodan",
        "description": "Internet-wide scanner. Queries open ports, services, banners, and vulnerabilities for any IP address.",
        "category": "OSINT",
        "url": "https://account.shodan.io/",
        "required": False,
    },
    {
        "id": "numverify_api_key",
        "env_key": "NUMVERIFY_API_KEY",
        "name": "Numverify",
        "description": "Phone number validation and lookup API. Returns carrier, line type, and location data for any phone number worldwide.",
        "category": "OSINT",
        "url": "https://numverify.com/",
        "required": False,
    },
    {
        "id": "spiderfoot_api_key",
        "env_key": "SPIDERFOOT_API_KEY",
        "name": "SpiderFoot HX (Cloud)",
        "description": "SpiderFoot HX cloud API key. Enables remote scanning via the SpiderFoot HX SaaS platform. Local SpiderFoot CLI works without a key.",
        "category": "OSINT",
        "url": "https://www.spiderfoot.net/",
        "required": False,
    },
    {
        "id": "censys_api_id",
        "env_key": "CENSYS_API_ID",
        "name": "Censys — API ID",
        "description": "Internet-wide scanning platform. Search certificates, hosts, and services. Pair with API Secret below.",
        "category": "OSINT",
        "url": "https://search.censys.io/account/api",
        "required": False,
    },
    {
        "id": "censys_api_secret",
        "env_key": "CENSYS_API_SECRET",
        "name": "Censys — API Secret",
        "description": "Secret key paired with Censys API ID above for authenticated queries.",
        "category": "OSINT",
        "url": "https://search.censys.io/account/api",
        "required": False,
    },
    {
        "id": "virustotal_api_key",
        "env_key": "VIRUSTOTAL_API_KEY",
        "name": "VirusTotal",
        "description": "Malware and URL scanner. Checks files, domains, and IPs against 70+ antivirus engines and threat feeds.",
        "category": "OSINT",
        "url": "https://www.virustotal.com/gui/my-apikey",
        "required": False,
    },
    {
        "id": "hunter_api_key",
        "env_key": "HUNTER_API_KEY",
        "name": "Hunter.io",
        "description": "Email finder and verifier. Discovers professional email addresses associated with a domain or company.",
        "category": "OSINT",
        "url": "https://hunter.io/api-keys",
        "required": False,
    },
    {
        "id": "fullcontact_api_key",
        "env_key": "FULLCONTACT_API_KEY",
        "name": "FullContact",
        "description": "Person and company enrichment API. Returns social profiles, demographics, and employment data from an email or name.",
        "category": "OSINT",
        "url": "https://www.fullcontact.com/",
        "required": False,
    },
    {
        "id": "ipinfo_api_key",
        "env_key": "IPINFO_API_KEY",
        "name": "IPinfo",
        "description": "IP geolocation and ASN data. Higher accuracy and rate limits than free ip-api.com. 50k lookups/month free.",
        "category": "OSINT",
        "url": "https://ipinfo.io/signup",
        "required": False,
    },
    {
        "id": "greynoise_api_key",
        "env_key": "GREYNOISE_API_KEY",
        "name": "GreyNoise",
        "description": "Internet-wide scanner intelligence. Identifies mass scanning IPs, botnets, and benign scanners. Community tier is free.",
        "category": "OSINT",
        "url": "https://www.greynoise.io/",
        "required": False,
    },
    {
        "id": "abuseipdb_api_key",
        "env_key": "ABUSEIPDB_API_KEY",
        "name": "AbuseIPDB",
        "description": "IP abuse/reputation database. Check if an IP has been reported for malicious activity. Free tier: 1000 checks/day.",
        "category": "OSINT",
        "url": "https://www.abuseipdb.com/account/api",
        "required": False,
    },
    {
        "id": "dehashed_api_key",
        "env_key": "DEHASHED_API_KEY",
        "name": "DeHashed",
        "description": "Credential and data breach search engine. Find leaked passwords, usernames, and personal data from breaches.",
        "category": "OSINT",
        "url": "https://www.dehashed.com/",
        "required": False,
    },
    {
        "id": "dehashed_email",
        "env_key": "DEHASHED_EMAIL",
        "name": "DeHashed — Email",
        "description": "Email address for DeHashed API authentication. Pair with DeHashed API key above.",
        "category": "OSINT",
        "url": "https://www.dehashed.com/",
        "required": False,
    },
    {
        "id": "leak_lookup_api_key",
        "env_key": "LEAK_LOOKUP_API_KEY",
        "name": "Leak-Lookup",
        "description": "Search 4B+ leaked records by email, username, password, hash, domain, or IP. Alternative to DeHashed.",
        "category": "OSINT",
        "url": "https://leak-lookup.com/",
        "required": False,
    },
    {
        "id": "emailrep_api_key",
        "env_key": "EMAILREP_API_KEY",
        "name": "EmailRep",
        "description": "Email reputation and risk scoring. Returns breach history, social presence, and disposable/spam classification.",
        "category": "OSINT",
        "url": "https://emailrep.io/",
        "required": False,
    },
    # ---- Threat Intelligence ----
    {
        "id": "hackerone_api_token",
        "env_key": "HACKERONE_API_TOKEN",
        "name": "HackerOne",
        "description": "Bug bounty platform API. Pull program scope, reports, and vulnerability data. Username: configured in CLAUDE.md.",
        "category": "Threat Intel",
        "url": "https://docs.hackerone.com/",
        "required": False,
    },
    {
        "id": "otx_api_key",
        "env_key": "OTX_API_KEY",
        "name": "AlienVault OTX",
        "description": "Open Threat Exchange. Community-driven threat intelligence with IOCs, pulses, and malware analysis. Free.",
        "category": "Threat Intel",
        "url": "https://otx.alienvault.com/api",
        "required": False,
    },
    {
        "id": "misp_api_key",
        "env_key": "MISP_API_KEY",
        "name": "MISP",
        "description": "Malware Information Sharing Platform API key. Query and share threat intelligence indicators.",
        "category": "Threat Intel",
        "url": "https://www.misp-project.org/",
        "required": False,
    },
    {
        "id": "misp_url",
        "env_key": "MISP_URL",
        "name": "MISP — Server URL",
        "description": "URL of your MISP instance (e.g., https://misp.local). Required for MISP API integration.",
        "category": "Threat Intel",
        "url": "https://www.misp-project.org/",
        "required": False,
    },
    # ---- Webcams ----
    {
        "id": "windy_webcams_api_key",
        "env_key": "WINDY_WEBCAMS_API_KEY",
        "name": "Windy Webcams",
        "description": "Windy Webcams API key for discovering live public webcams worldwide. Enables camera feed search in F.R.I.D.A.Y. Free tier available.",
        "category": "Intelligence",
        "url": "https://api.windy.com/keys",
        "required": False,
    },
    # ---- Local Tools ----
    {
        "id": "kismet_api_key",
        "env_key": "KISMET_API_KEY",
        "name": "Kismet",
        "description": "Kismet wireless IDS API key. Authenticates with the local Kismet instance for WiFi/BT device tracking.",
        "category": "Local Tools",
        "url": "http://localhost:2501/",
        "required": False,
    },
]


def _obfuscate(value: str) -> str:
    """Show first 4 chars, mask the rest with bullets."""
    if not value or len(value) <= 4:
        return "••••••••"
    return value[:4] + "•" * (len(value) - 4)


def get_api_keys():
    """Return the full API registry with obfuscated key values."""
    result = []
    for api in API_REGISTRY:
        entry = {
            "id": api["id"],
            "name": api["name"],
            "description": api["description"],
            "category": api["category"],
            "url": api["url"],
            "required": api["required"],
            "has_key": api["env_key"] is not None,
            "env_key": api["env_key"],
            "value_obfuscated": None,
            "is_set": False,
        }
        if api["env_key"]:
            raw = os.environ.get(api["env_key"], "")
            entry["value_obfuscated"] = _obfuscate(raw)
            entry["is_set"] = bool(raw)
        result.append(entry)
    return result


# OSINT-related env keys that should also be forwarded to the host OSINT agent
_OSINT_KEYS = {
    "HIBP_API_KEY", "SHODAN_API_KEY", "NUMVERIFY_API_KEY", "SPIDERFOOT_API_KEY",
    "CENSYS_API_ID", "CENSYS_API_SECRET", "VIRUSTOTAL_API_KEY", "HUNTER_API_KEY",
    "FULLCONTACT_API_KEY", "IPINFO_API_KEY", "GREYNOISE_API_KEY", "ABUSEIPDB_API_KEY",
    "DEHASHED_API_KEY", "DEHASHED_EMAIL", "LEAK_LOOKUP_API_KEY", "EMAILREP_API_KEY",
    "OTX_API_KEY", "MISP_API_KEY", "MISP_URL", "KISMET_API_KEY",
    "HACKERONE_API_TOKEN",
    "WINDY_WEBCAMS_API_KEY",
}


def update_api_key(env_key: str, new_value: str) -> bool:
    """Update a single key in the .env file and in the current process env."""
    # Create .env if it doesn't exist
    if not ENV_PATH.exists():
        ENV_PATH.write_text("")

    # Update os.environ immediately
    os.environ[env_key] = new_value

    # Update the .env file on disk
    content = ENV_PATH.read_text(encoding="utf-8")
    pattern = re.compile(rf"^{re.escape(env_key)}=.*$", re.MULTILINE)
    if pattern.search(content):
        content = pattern.sub(f"{env_key}={new_value}", content)
    else:
        content = content.rstrip("\n") + f"\n{env_key}={new_value}\n"

    ENV_PATH.write_text(content, encoding="utf-8")

    # Forward OSINT keys to the host agent
    if env_key in _OSINT_KEYS:
        _forward_key_to_agent(env_key, new_value)

    return True


def _forward_key_to_agent(env_key: str, value: str):
    """Forward an API key to the OSINT agent running on the host."""
    import requests
    agent_url = os.environ.get("OSINT_AGENT_URL", "http://host.docker.internal:8002")
    try:
        requests.put(
            f"{agent_url}/api-keys",
            json={"key": env_key, "value": value},
            timeout=5,
        )
    except Exception:
        pass  # Agent may not be running — that's fine
