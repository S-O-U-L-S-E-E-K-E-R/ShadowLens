"""Configuration for the OSINT agent — tool paths, timeouts, host location."""

import json
import logging
import shutil
import subprocess
import os
import urllib.request
from pathlib import Path

# Load .env file if it exists (for API keys set via settings panel)
_env_file = Path(__file__).parent / ".env"
if _env_file.exists():
    for line in _env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, val = line.partition("=")
            key, val = key.strip(), val.strip().strip('"').strip("'")
            if key and val and key not in os.environ:
                os.environ[key] = val

logger = logging.getLogger(__name__)


def _detect_location() -> tuple[float, float]:
    """Detect host location using best available source.

    Priority:
    1. Environment variables (OSINT_HOST_LAT/LON) — user override
    2. gpsd — real GPS hardware
    3. IP geolocation APIs — fallback
    """
    # 1. Explicit env override
    env_lat = os.environ.get("OSINT_HOST_LAT")
    env_lon = os.environ.get("OSINT_HOST_LON")
    if env_lat and env_lon:
        logger.info(f"Location from env: {env_lat}, {env_lon}")
        return float(env_lat), float(env_lon)

    # 2. Try gpsd for real GPS fix
    try:
        result = subprocess.run(
            ["gpspipe", "-w", "-n", "10"],
            capture_output=True, text=True, timeout=8
        )
        for line in result.stdout.strip().split("\n"):
            try:
                obj = json.loads(line)
                if obj.get("class") == "TPV" and obj.get("lat") and obj.get("lon"):
                    lat, lon = obj["lat"], obj["lon"]
                    logger.info(f"Location from GPS: {lat}, {lon}")
                    return lat, lon
            except (json.JSONDecodeError, KeyError):
                continue
    except (FileNotFoundError, subprocess.TimeoutExpired, Exception) as e:
        logger.debug(f"gpsd not available: {e}")

    # 3. IP geolocation fallback (try multiple services)
    for url in [
        "http://ip-api.com/json/?fields=lat,lon,status",
        "https://ipwho.is/",
        "https://ipinfo.io/json",
    ]:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "osint-agent/1.0"})
            resp = urllib.request.urlopen(req, timeout=5)
            data = json.loads(resp.read())

            if "lat" in data and "lon" in data:
                lat, lon = float(data["lat"]), float(data["lon"])
                logger.info(f"Location from {url}: {lat}, {lon}")
                return lat, lon
            elif "latitude" in data and "longitude" in data:
                lat, lon = float(data["latitude"]), float(data["longitude"])
                logger.info(f"Location from {url}: {lat}, {lon}")
                return lat, lon
            elif "loc" in data:
                parts = data["loc"].split(",")
                lat, lon = float(parts[0]), float(parts[1])
                logger.info(f"Location from {url}: {lat}, {lon}")
                return lat, lon
        except Exception as e:
            logger.debug(f"IP geolocation failed for {url}: {e}")

    logger.warning("Could not detect location, using 0,0")
    return 0.0, 0.0


# Detect once at import time
HOST_LAT, HOST_LON = _detect_location()

# Tool binary paths — auto-detected or overridden via env
TOOL_PATHS = {
    "nmap": os.environ.get("NMAP_PATH", shutil.which("nmap") or "/usr/bin/nmap"),
    "nuclei": os.environ.get("NUCLEI_PATH", shutil.which("nuclei") or "/usr/local/bin/nuclei"),
    "whatweb": os.environ.get("WHATWEB_PATH", shutil.which("whatweb") or "/usr/bin/whatweb"),
    "theharvester": os.environ.get("THEHARVESTER_PATH", shutil.which("theHarvester") or "/usr/bin/theHarvester"),
    "spiderfoot": os.environ.get("SPIDERFOOT_PATH", shutil.which("spiderfoot") or "/usr/bin/spiderfoot"),
    "sherlock": os.environ.get("SHERLOCK_PATH", shutil.which("sherlock") or "/usr/bin/sherlock"),
    "h8mail": os.environ.get("H8MAIL_PATH", shutil.which("h8mail") or "/usr/bin/h8mail"),
    "whois": os.environ.get("WHOIS_PATH", shutil.which("whois") or "/usr/bin/whois"),
    "dmitry": os.environ.get("DMITRY_PATH", shutil.which("dmitry") or "/usr/bin/dmitry"),
    "subfinder": os.environ.get("SUBFINDER_PATH", shutil.which("subfinder") or "/usr/bin/subfinder"),
    "dnsrecon": os.environ.get("DNSRECON_PATH", shutil.which("dnsrecon") or "/usr/bin/dnsrecon"),
    "emailharvester": os.environ.get("EMAILHARVESTER_PATH", shutil.which("emailharvester") or "/usr/bin/emailharvester"),
    "dig": os.environ.get("DIG_PATH", shutil.which("dig") or "/usr/bin/dig"),
    "shodan": os.environ.get("SHODAN_PATH", shutil.which("shodan") or "/usr/bin/shodan"),
    "phoneinfoga": os.environ.get("PHONEINFOGA_PATH", shutil.which("phoneinfoga") or "/usr/local/bin/phoneinfoga"),
    "maigret": os.environ.get("MAIGRET_PATH", shutil.which("maigret") or os.path.expanduser("~/.local/bin/maigret")),
    "holehe": os.environ.get("HOLEHE_PATH", shutil.which("holehe") or os.path.expanduser("~/.local/bin/holehe")),
    "autorecon": os.environ.get("AUTORECON_PATH", shutil.which("autorecon") or os.path.expanduser("~/.local/bin/autorecon")),
}

# Kismet API
KISMET_API_URL = os.environ.get("KISMET_API_URL", "http://localhost:2501")
KISMET_API_KEY = os.environ.get("KISMET_API_KEY", "")
KISMET_DB_PATH = os.environ.get("KISMET_DB_PATH", os.path.expanduser("~/.kismet/devicetracker.db3"))

# Snort log paths
SNORT_LOG_DIR = os.environ.get("SNORT_LOG_DIR", "/var/log/snort")
SNORT_ALERT_FILE = os.environ.get("SNORT_ALERT_FILE", "alert_json.txt")

# SpiderFoot API
SPIDERFOOT_URL = os.environ.get("SPIDERFOOT_URL", "http://localhost:5001")

# Timeouts (seconds)
SCAN_TIMEOUT = int(os.environ.get("SCAN_TIMEOUT", "300"))
TOOL_TIMEOUT = int(os.environ.get("TOOL_TIMEOUT", "60"))

# Nmap safety: only allow RFC1918 by default
NMAP_ALLOWED_RANGES = os.environ.get("NMAP_ALLOWED_RANGES", "10.0.0.0/8,172.16.0.0/12,192.168.0.0/16").split(",")

# Results directory for large scan outputs
RESULTS_DIR = os.environ.get("OSINT_RESULTS_DIR", "/tmp/osint-results")
os.makedirs(RESULTS_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# LLM Provider — "claude" (default) or "ollama"
# ---------------------------------------------------------------------------
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "claude")
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3")


def get_llm_provider() -> str:
    return os.environ.get("LLM_PROVIDER", "claude")


def set_llm_provider(provider: str):
    os.environ["LLM_PROVIDER"] = provider


def get_ollama_config() -> dict:
    return {
        "base_url": os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"),
        "model": os.environ.get("OLLAMA_MODEL", "llama3"),
    }


def detect_tools() -> dict:
    """Return availability status for each tool."""
    status = {}
    for name, path in TOOL_PATHS.items():
        status[name] = {
            "path": path,
            "available": os.path.isfile(path) and os.access(path, os.X_OK) if path else False,
        }
    # Kismet — check API reachability lazily (don't block startup)
    status["kismet"] = {"path": KISMET_API_URL, "available": True}  # optimistic
    status["snort"] = {
        "path": os.path.join(SNORT_LOG_DIR, SNORT_ALERT_FILE),
        "available": os.path.isdir(SNORT_LOG_DIR),
    }
    return status
