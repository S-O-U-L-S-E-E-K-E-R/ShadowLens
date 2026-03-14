"""OSINT Agent — Host-side FastAPI bridge for local security tools.

Runs on the HOST at port 8002. The Docker backend reaches it via host.docker.internal:8002.
"""

import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

from config import detect_tools, HOST_LAT, HOST_LON
from runners.kismet import KismetRunner
from runners.snort import SnortRunner
from runners.nmap import NmapRunner
from runners.nuclei import NucleiRunner
from runners.harvester import HarvesterRunner
from runners.whatweb import WhatWebRunner
from runners.spiderfoot import SpiderFootRunner
from runners.deep_search import DeepSearchRunner
from runners.autorecon import AutoReconRunner
from runners.base import get_job, list_jobs

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Singleton runners
kismet = KismetRunner()
snort = SnortRunner()
nmap = NmapRunner()
nuclei = NucleiRunner()
harvester = HarvesterRunner()
whatweb = WhatWebRunner()
spiderfoot = SpiderFootRunner()
deep_search = DeepSearchRunner()
autorecon = AutoReconRunner()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("OSINT Agent starting on port 8002")
    logger.info(f"Tool availability: {detect_tools()}")
    # Initialize F.R.I.D.A.Y. engine in background (loads LLM, FAISS, extractors)
    try:
        from syd.engine import get_engine
        friday = get_engine()
        friday.initialize(background=True)
        logger.info("F.R.I.D.A.Y. engine initialization started in background")
    except Exception as e:
        logger.warning(f"F.R.I.D.A.Y. engine not available: {e}")
    yield
    logger.info("OSINT Agent shutting down")


app = FastAPI(title="ShadowLens OSINT Agent", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Health & Tool Detection ---

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "agent": "osint-agent",
        "location": {"lat": HOST_LAT, "lon": HOST_LON},
        "tools": detect_tools(),
    }


@app.get("/tools")
async def tools():
    return detect_tools()


# --- Kismet (WiFi/BT Devices) ---

@app.get("/kismet/devices")
async def kismet_devices():
    try:
        devices = await kismet.get_devices()
        return {"status": "ok", "data": devices, "count": len(devices)}
    except Exception as e:
        logger.error(f"Kismet error: {e}")
        return {"status": "error", "data": [], "error": str(e)}


# --- Snort (IDS Alerts) ---

@app.get("/snort/alerts")
async def snort_alerts(limit: int = 200):
    try:
        alerts = await snort.get_alerts(limit)
        return {"status": "ok", "data": alerts, "count": len(alerts)}
    except Exception as e:
        logger.error(f"Snort error: {e}")
        return {"status": "error", "data": [], "error": str(e)}


# --- Nmap (Network Scanning) ---

@app.get("/nmap/results")
async def nmap_results():
    try:
        hosts = await nmap.get_results()
        return {"status": "ok", "data": hosts, "count": len(hosts)}
    except Exception as e:
        return {"status": "error", "data": [], "error": str(e)}


class NmapScanRequest(BaseModel):
    target: str
    scan_type: str = "quick"  # quick, service, full


@app.post("/nmap/scan")
async def nmap_scan(req: NmapScanRequest):
    result = await nmap.start_scan(req.target, req.scan_type)
    return result


# --- Nuclei (Vulnerability Scanning) ---

@app.get("/nuclei/results")
async def nuclei_results():
    try:
        vulns = await nuclei.get_results()
        return {"status": "ok", "data": vulns, "count": len(vulns)}
    except Exception as e:
        return {"status": "error", "data": [], "error": str(e)}


class NucleiScanRequest(BaseModel):
    target: str
    templates: str = ""


@app.post("/nuclei/scan")
async def nuclei_scan(req: NucleiScanRequest):
    result = await nuclei.start_scan(req.target, req.templates)
    return result


# --- WhatWeb (Technology Detection) ---

class WhatWebRequest(BaseModel):
    target: str


@app.post("/whatweb/analyze")
async def whatweb_analyze(req: WhatWebRequest):
    result = await whatweb.analyze(req.target)
    return result


# --- theHarvester (OSINT Recon) ---

class HarvesterRequest(BaseModel):
    domain: str
    sources: str = "all"


@app.post("/harvester/run")
async def harvester_run(req: HarvesterRequest):
    result = await harvester.run(req.domain, req.sources)
    return result


# --- SpiderFoot ---

@app.get("/spiderfoot/scans")
async def spiderfoot_scans():
    return await spiderfoot.get_scans()


class SpiderFootScanRequest(BaseModel):
    target: str
    use_case: str = "passive"  # passive, footprint, investigate, all


@app.post("/spiderfoot/scan")
async def spiderfoot_scan(req: SpiderFootScanRequest):
    """Run a SpiderFoot CLI scan (passive OSINT by default)."""
    result = await spiderfoot.run_scan(req.target, req.use_case)
    return result


@app.get("/spiderfoot/results/{target}")
async def spiderfoot_cached_results(target: str, use_case: str = "passive"):
    """Get cached SpiderFoot results for a target."""
    cached = await spiderfoot.get_cached_results(target, use_case)
    if cached:
        return {"status": "ok", "data": cached}
    return {"status": "no_results", "data": None}


# --- AutoRecon (Deep Reconnaissance) ---

class AutoReconRequest(BaseModel):
    target: str
    ports: str = ""


@app.post("/autorecon/scan")
async def autorecon_scan(req: AutoReconRequest):
    result = await autorecon.start_scan(req.target, req.ports)
    return result


@app.get("/autorecon/results")
async def autorecon_results():
    try:
        data = await autorecon.get_results()
        return {"status": "ok", "data": data}
    except Exception as e:
        return {"status": "error", "data": {}, "error": str(e)}


# --- Deep OSINT Search ---

SEARCH_HISTORY_PATH = "/tmp/osint-results/search_history.json"
SEARCH_HISTORY_MAX = 100


def _load_history() -> list[dict]:
    """Load search history from disk."""
    try:
        if os.path.isfile(SEARCH_HISTORY_PATH):
            with open(SEARCH_HISTORY_PATH, "r") as f:
                data = json.load(f)
            if isinstance(data, list):
                return data
    except Exception:
        pass
    return []


def _save_history(history: list[dict]) -> None:
    """Persist search history to disk (max SEARCH_HISTORY_MAX entries, FIFO)."""
    os.makedirs(os.path.dirname(SEARCH_HISTORY_PATH), exist_ok=True)
    # Keep only the most recent entries
    history = history[-SEARCH_HISTORY_MAX:]
    try:
        with open(SEARCH_HISTORY_PATH, "w") as f:
            json.dump(history, f, default=str)
    except Exception as exc:
        logger.warning(f"Failed to save search history: {exc}")


class DeepSearchRequest(BaseModel):
    query: str


@app.get("/search/history")
async def search_history():
    """Return persisted search history."""
    return _load_history()


@app.post("/search")
async def deep_osint_search(req: DeepSearchRequest):
    """Run deep OSINT search — auto-detects input type and runs appropriate tools."""
    result = await deep_search.search(req.query)

    # Append to search history
    entry = {
        "query": req.query,
        "type": result.get("type", "unknown"),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tools_run": result.get("tools_run", []),
        "summary": result.get("summary", "")[:300],
    }
    history = _load_history()
    history.append(entry)
    _save_history(history)

    return result


# --- API Key Management ---

class ApiKeyUpdate(BaseModel):
    key: str
    value: str


@app.put("/api-keys")
async def update_api_key(req: ApiKeyUpdate):
    """Save an API key to the agent's local .env file."""
    import os, re
    from pathlib import Path

    env_path = Path(__file__).parent / ".env"

    # Update in-memory
    os.environ[req.key] = req.value

    # Update on disk
    if env_path.exists():
        content = env_path.read_text()
        pattern = re.compile(rf"^{re.escape(req.key)}=.*$", re.MULTILINE)
        if pattern.search(content):
            content = pattern.sub(f"{req.key}={req.value}", content)
        else:
            content = content.rstrip("\n") + f"\n{req.key}={req.value}\n"
    else:
        content = f"{req.key}={req.value}\n"

    env_path.write_text(content)
    return {"status": "ok", "key": req.key}


# --- Job Tracking ---

@app.get("/jobs/{job_id}")
async def job_status(job_id: str):
    job = get_job(job_id)
    if job is None:
        return {"error": "Job not found"}
    return job


@app.get("/jobs")
async def all_jobs():
    return list_jobs()


# --- F.R.I.D.A.Y. Analysis Engine ---

@app.get("/syd/status")
async def friday_status():
    """Check F.R.I.D.A.Y. engine status — model loaded, indexes ready, etc."""
    try:
        from syd.engine import get_engine
        return get_engine().status()
    except Exception as e:
        return {"ready": False, "error": str(e)}


class FridayQueryRequest(BaseModel):
    question: str
    scan_data: str = ""
    module: str = "nmap"
    history: list = []


class FridayChatRequest(BaseModel):
    question: str
    context: str = ""


@app.post("/syd/query")
async def friday_query(req: FridayQueryRequest):
    """F.R.I.D.A.Y. query — auto-routes to scan analysis, entity analysis, OSINT, or general."""
    import asyncio
    from syd.engine import get_engine

    engine = get_engine()
    if not engine.ready:
        return {"error": "F.R.I.D.A.Y. engine not ready. Still loading.", "ready": False}

    result = await asyncio.to_thread(engine.chat, req.question, req.scan_data, req.history)
    return result


@app.post("/syd/chat")
async def friday_chat(req: FridayChatRequest):
    """General F.R.I.D.A.Y. chat — works with or without entity context."""
    import asyncio
    from syd.engine import get_engine

    engine = get_engine()
    if not engine.ready:
        return {"error": "F.R.I.D.A.Y. engine not ready. Still loading.", "ready": False}

    result = await asyncio.to_thread(engine.chat, req.question, req.context)
    return result


class FridayAnalyzeRequest(BaseModel):
    scan_data: str
    module: str = "nmap"


@app.post("/syd/analyze")
async def friday_analyze(req: FridayAnalyzeRequest):
    """Quick analysis — auto-detects entity type and returns summary."""
    import asyncio
    from syd.engine import get_engine

    engine = get_engine()
    result = await asyncio.to_thread(engine.analyze_entity, req.scan_data)
    return result


@app.post("/syd/extract")
async def friday_extract(req: FridayAnalyzeRequest):
    """Just extract facts — no LLM, no RAG. Pure deterministic parsing."""
    import asyncio
    from syd.engine import get_engine

    engine = get_engine()
    facts = await asyncio.to_thread(engine.extract_facts, req.scan_data, req.module)
    facts_text = engine.facts_to_text(facts, req.module)
    return {'facts': facts, 'facts_text': facts_text, 'module': req.module}


# --- LLM Provider Settings ---

@app.get("/llm/status")
async def llm_status():
    """Return current LLM provider config and availability."""
    from config import get_llm_provider, get_ollama_config
    try:
        from syd.engine import get_engine
        engine = get_engine()
        claude_ok = engine._claude_path is not None
        ollama_ok = engine._ollama_available
    except Exception:
        claude_ok = False
        ollama_ok = False
    return {
        "provider": get_llm_provider(),
        "claude_available": claude_ok,
        "ollama_available": ollama_ok,
        "ollama": get_ollama_config(),
    }


class LlmProviderUpdate(BaseModel):
    provider: str  # "claude" or "ollama"
    ollama_base_url: Optional[str] = None
    ollama_model: Optional[str] = None


@app.put("/llm/provider")
async def set_llm_provider(req: LlmProviderUpdate):
    """Switch LLM provider between claude and ollama."""
    if req.provider not in ("claude", "ollama"):
        return {"status": "error", "message": "Provider must be 'claude' or 'ollama'"}

    os.environ["LLM_PROVIDER"] = req.provider
    if req.ollama_base_url:
        os.environ["OLLAMA_BASE_URL"] = req.ollama_base_url
    if req.ollama_model:
        os.environ["OLLAMA_MODEL"] = req.ollama_model

    # Re-probe Ollama if switching to it
    if req.provider == "ollama":
        try:
            from syd.engine import get_engine
            engine = get_engine()
            engine._probe_ollama()
        except Exception:
            pass

    return {
        "status": "ok",
        "provider": req.provider,
        "ollama_base_url": os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"),
        "ollama_model": os.environ.get("OLLAMA_MODEL", "llama3"),
    }


@app.get("/ollama/models")
async def ollama_models():
    """List available Ollama models."""
    import urllib.request
    ollama_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
    try:
        req = urllib.request.Request(f"{ollama_url}/api/tags", headers={"User-Agent": "ShadowLens/1.0"})
        resp = urllib.request.urlopen(req, timeout=5)
        data = json.loads(resp.read())
        models = [m.get("name", "") for m in data.get("models", [])]
        return {"status": "ok", "models": models}
    except Exception as e:
        return {"status": "error", "models": [], "error": str(e)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8002, reload=True)
