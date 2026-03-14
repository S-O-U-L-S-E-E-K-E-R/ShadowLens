"""OSINT Bridge — Docker-side client that calls the host OSINT agent over HTTP.

The OSINT agent runs on the HOST at port 8002. From inside Docker, it's reached
via host.docker.internal:8002 (set via extra_hosts in docker-compose.yml).

All functions return [] on connection failure (graceful degradation).
"""

import logging
import os

import requests

logger = logging.getLogger(__name__)

OSINT_AGENT_URL = os.environ.get("OSINT_AGENT_URL", "http://host.docker.internal:8002")
CONNECT_TIMEOUT = 5
READ_TIMEOUT = 15
SCAN_READ_TIMEOUT = 90  # scans (whatweb, harvester, nmap) can take much longer
LONG_SCAN_READ_TIMEOUT = 300  # spiderfoot passive scans can take 2-5 minutes


def _get(endpoint: str) -> list | dict:
    """GET request to the OSINT agent. Returns data or [] on failure."""
    try:
        resp = requests.get(
            f"{OSINT_AGENT_URL}{endpoint}",
            timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
        )
        if resp.status_code == 200:
            body = resp.json()
            return body.get("data", body) if isinstance(body, dict) else body
        logger.warning(f"OSINT agent {endpoint} returned {resp.status_code}")
    except requests.ConnectionError:
        logger.debug(f"OSINT agent not reachable at {OSINT_AGENT_URL}")
    except requests.Timeout:
        logger.warning(f"OSINT agent timeout on {endpoint}")
    except Exception as e:
        logger.warning(f"OSINT bridge error on {endpoint}: {e}")
    return []


def _post(endpoint: str, json_data: dict, read_timeout: int = READ_TIMEOUT) -> dict:
    """POST request to the OSINT agent."""
    try:
        resp = requests.post(
            f"{OSINT_AGENT_URL}{endpoint}",
            json=json_data,
            timeout=(CONNECT_TIMEOUT, read_timeout),
        )
        if resp.status_code == 200:
            return resp.json()
        logger.warning(f"OSINT agent POST {endpoint} returned {resp.status_code}")
    except requests.ConnectionError:
        logger.debug(f"OSINT agent not reachable at {OSINT_AGENT_URL}")
    except Exception as e:
        logger.warning(f"OSINT bridge POST error on {endpoint}: {e}")
    return {"status": "unavailable", "data": []}


def _put(endpoint: str, json_data: dict, read_timeout: int = READ_TIMEOUT) -> dict:
    """PUT request to the OSINT agent."""
    try:
        resp = requests.put(
            f"{OSINT_AGENT_URL}{endpoint}",
            json=json_data,
            timeout=(CONNECT_TIMEOUT, read_timeout),
        )
        if resp.status_code == 200:
            return resp.json()
        logger.warning(f"OSINT agent PUT {endpoint} returned {resp.status_code}")
    except requests.ConnectionError:
        logger.debug(f"OSINT agent not reachable at {OSINT_AGENT_URL}")
    except Exception as e:
        logger.warning(f"OSINT bridge PUT error on {endpoint}: {e}")
    return {"status": "unavailable", "data": []}


def fetch_kismet_devices() -> list:
    """Fetch WiFi/BT devices from Kismet via the OSINT agent."""
    return _get("/kismet/devices")


def fetch_snort_alerts() -> list:
    """Fetch IDS alerts from Snort via the OSINT agent."""
    return _get("/snort/alerts")


def fetch_nmap_results() -> list:
    """Fetch last nmap scan results via the OSINT agent."""
    return _get("/nmap/results")


def fetch_nuclei_results() -> list:
    """Fetch last nuclei scan results via the OSINT agent."""
    return _get("/nuclei/results")


def fetch_spiderfoot_scans() -> list:
    """Fetch list of SpiderFoot scans from the OSINT agent."""
    return _get("/spiderfoot/scans")


def trigger_scan(tool: str, target: str, **kwargs) -> dict:
    """Trigger an on-demand scan via the OSINT agent."""
    if tool == "nmap":
        return _post("/nmap/scan", {"target": target, **kwargs}, read_timeout=SCAN_READ_TIMEOUT)
    elif tool == "nuclei":
        return _post("/nuclei/scan", {"target": target, **kwargs}, read_timeout=SCAN_READ_TIMEOUT)
    elif tool == "whatweb":
        return _post("/whatweb/analyze", {"target": target}, read_timeout=SCAN_READ_TIMEOUT)
    elif tool == "harvester":
        return _post("/harvester/run", {"domain": target, **kwargs}, read_timeout=SCAN_READ_TIMEOUT)
    elif tool == "spiderfoot":
        use_case = kwargs.get("use_case", "passive")
        return _post("/spiderfoot/scan", {"target": target, "use_case": use_case}, read_timeout=LONG_SCAN_READ_TIMEOUT)
    elif tool == "autorecon":
        ports = kwargs.get("ports", "")
        return _post("/autorecon/scan", {"target": target, "ports": ports}, read_timeout=LONG_SCAN_READ_TIMEOUT)
    return {"status": "unknown_tool", "data": []}


SEARCH_READ_TIMEOUT = 300  # deep searches can take up to 5 minutes


def deep_osint_search(query: str) -> dict:
    """Run deep OSINT search via the agent — auto-detects input type."""
    return _post("/search", {"query": query}, read_timeout=SEARCH_READ_TIMEOUT)


def fetch_search_history() -> list:
    """Fetch OSINT search history from the agent."""
    return _get("/search/history")


def fetch_job_status(job_id: str) -> dict:
    """Check status of an async job on the OSINT agent."""
    try:
        resp = requests.get(
            f"{OSINT_AGENT_URL}/jobs/{job_id}",
            timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
        )
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return {"error": "Job not found or agent unreachable"}


def fetch_agent_health() -> dict:
    """Check OSINT agent health and tool availability."""
    try:
        resp = requests.get(
            f"{OSINT_AGENT_URL}/health",
            timeout=(CONNECT_TIMEOUT, 5),
        )
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return {"status": "unreachable", "tools": {}}


# --- F.R.I.D.A.Y. Analysis Engine ---

FRIDAY_QUERY_TIMEOUT = 120
FRIDAY_OSINT_TIMEOUT = 660  # OSINT with HexStrike tools can take up to 10 minutes

def friday_status() -> dict:
    """Check F.R.I.D.A.Y. engine status."""
    return _get("/syd/status")

def friday_query(question: str, scan_data: str, module: str = "nmap", history: list = None) -> dict:
    """Ask F.R.I.D.A.Y. a question — auto-routes to appropriate analysis mode."""
    return _post("/syd/query", {
        "question": question,
        "scan_data": scan_data,
        "module": module,
        "history": history or [],
    }, read_timeout=FRIDAY_OSINT_TIMEOUT)

def friday_chat(question: str, context: str = "") -> dict:
    """General F.R.I.D.A.Y. chat — works with or without entity context."""
    return _post("/syd/chat", {
        "question": question,
        "context": context,
    }, read_timeout=FRIDAY_OSINT_TIMEOUT)

def friday_analyze(scan_data: str, module: str = "nmap") -> dict:
    """Quick analysis — auto-detects entity type."""
    return _post("/syd/analyze", {
        "scan_data": scan_data,
        "module": module,
    }, read_timeout=60)

def friday_extract(scan_data: str, module: str = "nmap") -> dict:
    """Just extract facts — no LLM needed."""
    return _post("/syd/extract", {
        "scan_data": scan_data,
        "module": module,
    }, read_timeout=30)
