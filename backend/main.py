from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from contextlib import asynccontextmanager
from services.data_fetcher import start_scheduler, stop_scheduler, get_latest_data
from services.ais_stream import start_ais_stream, stop_ais_stream
from services.carrier_tracker import start_carrier_tracker, stop_carrier_tracker
import asyncio
import uvicorn
import logging
import hashlib
import json as json_mod

logging.basicConfig(level=logging.INFO)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Start background data fetching, AIS stream, and carrier tracker
    start_carrier_tracker()
    start_ais_stream()
    start_scheduler()
    yield
    # Shutdown: Stop all background services
    stop_ais_stream()
    stop_scheduler()
    stop_carrier_tracker()

app = FastAPI(title="Live Risk Dashboard API", lifespan=lifespan)

from fastapi.middleware.gzip import GZipMiddleware
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # For prototyping, allow all
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from services.data_fetcher import update_all_data

@app.get("/api/refresh")
async def force_refresh():
    # Force an immediate synchronous update of the data payload
    import threading
    t = threading.Thread(target=update_all_data)
    t.start()
    return {"status": "refreshing in background"}

@app.get("/api/live-data")
async def live_data():
    return get_latest_data()

@app.get("/api/live-data/fast")
async def live_data_fast(request: Request):
    d = get_latest_data()
    payload = {
        "commercial_flights": d.get("commercial_flights", []),
        "military_flights": d.get("military_flights", []),
        "private_flights": d.get("private_flights", []),
        "private_jets": d.get("private_jets", []),
        "tracked_flights": d.get("tracked_flights", []),
        "ships": d.get("ships", []),
        "cctv": d.get("cctv", []),
        "uavs": d.get("uavs", []),
        "liveuamap": d.get("liveuamap", []),
        "gps_jamming": d.get("gps_jamming", []),
        "news": d.get("news", []),
    }
    # ETag includes last_updated timestamp so it changes on every data refresh,
    # not just when item counts change (old bug: positions went stale)
    last_updated = d.get("last_updated", "")
    counts = "|".join(f"{k}:{len(v) if isinstance(v, list) else 0}" for k, v in payload.items())
    etag = hashlib.md5(f"{last_updated}|{counts}".encode()).hexdigest()[:16]
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag, "Cache-Control": "no-cache"})
    return Response(
        content=json_mod.dumps(payload),
        media_type="application/json",
        headers={"ETag": etag, "Cache-Control": "no-cache"}
    )

@app.get("/api/live-data/slow")
async def live_data_slow(request: Request):
    d = get_latest_data()
    payload = {
        "last_updated": d.get("last_updated"),
        "stocks": d.get("stocks", {}),
        "oil": d.get("oil", {}),
        "weather": d.get("weather"),
        "earthquakes": d.get("earthquakes", []),
        "frontlines": d.get("frontlines"),
        "gdelt": d.get("gdelt", []),
        "airports": d.get("airports", []),
        "satellites": d.get("satellites", []),
        "tfrs": d.get("tfrs", []),
        "weather_alerts": d.get("weather_alerts", []),
        "natural_events": d.get("natural_events", []),
        "firms_hotspots": d.get("firms_hotspots", []),
        "power_outages": d.get("power_outages", []),
        "internet_outages": d.get("internet_outages", []),
        "air_quality": d.get("air_quality", []),
        "space_weather": d.get("space_weather", []),
        "radioactivity": d.get("radioactivity", []),
        "piracy_incidents": d.get("piracy_incidents", []),
        "border_crossings": d.get("border_crossings", []),
        "cyber_threats": d.get("cyber_threats", []),
        "checkpoint_stats": d.get("checkpoint_stats", {}),
        "reservoirs": d.get("reservoirs", []),
        "cell_towers": d.get("cell_towers", []),
        "global_events": d.get("global_events", []),
        "social_media": d.get("social_media", [])
    }
    # ETag based on last_updated + item counts + checkpoint live count
    last_updated = d.get("last_updated", "")
    cp_count = len(d.get("cyber_threats", []))
    counts = "|".join(f"{k}:{len(v) if isinstance(v, list) else 0}" for k, v in payload.items())
    etag = hashlib.md5(f"slow|{last_updated}|{counts}|cp{cp_count}".encode()).hexdigest()[:16]
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag, "Cache-Control": "no-cache"})
    return Response(
        content=json_mod.dumps(payload, default=str),
        media_type="application/json",
        headers={"ETag": etag, "Cache-Control": "no-cache"}
    )

@app.get("/api/live-data/static")
async def live_data_static(request: Request):
    """Static datasets — fetched once by the frontend, cached aggressively."""
    d = get_latest_data()
    payload = {
        "military_bases": d.get("military_bases", []),
        "nuclear_facilities": d.get("nuclear_facilities", []),
        "submarine_cables": d.get("submarine_cables", []),
        "cable_landing_points": d.get("cable_landing_points", []),
        "embassies": d.get("embassies", []),
        "volcanoes": d.get("volcanoes", []),
        "noaa_nwr": d.get("noaa_nwr", []),
        "kiwisdr_nodes": d.get("kiwisdr_nodes", [])
    }
    counts = "|".join(f"{k}:{len(v) if isinstance(v, list) else 0}" for k, v in payload.items())
    etag = hashlib.md5(f"static|{counts}".encode()).hexdigest()[:16]
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag, "Cache-Control": "max-age=3600"})
    return Response(
        content=json_mod.dumps(payload, default=str),
        media_type="application/json",
        headers={"ETag": etag, "Cache-Control": "max-age=3600"}
    )

@app.get("/api/live-data/osint")
async def live_data_osint(request: Request):
    """OSINT data tier — Kismet, Snort, Nmap, Nuclei from host-side agent."""
    d = get_latest_data()
    payload = {
        "kismet_devices": d.get("kismet_devices", []),
        "snort_alerts": d.get("snort_alerts", []),
        "nmap_hosts": d.get("nmap_hosts", []),
        "nuclei_vulns": d.get("nuclei_vulns", []),
    }
    counts = "|".join(f"{k}:{len(v) if isinstance(v, list) else 0}" for k, v in payload.items())
    etag = hashlib.md5(f"osint|{counts}".encode()).hexdigest()[:16]
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag, "Cache-Control": "no-cache"})
    return Response(
        content=json_mod.dumps(payload, default=str),
        media_type="application/json",
        headers={"ETag": etag, "Cache-Control": "no-cache"}
    )


@app.get("/api/live-data/regional")
async def live_data_regional(lat: float, lng: float, radius: float = 5.0, country: str = "", region: str = ""):
    """Return all data filtered to a geographic region + regional news & social media.

    Filters existing global data by bounding box + country code, then fetches
    fresh regional news from GDELT, Reddit, Bluesky, and Mastodon.
    """
    import asyncio
    d = get_latest_data()

    lat_min, lat_max = lat - radius, lat + radius
    lng_min, lng_max = lng - radius, lng + radius
    cc_upper = country.upper() if country else ""

    def in_region(item):
        if not isinstance(item, dict):
            return False
        if cc_upper:
            item_cc = (item.get('country_code') or item.get('country') or
                       item.get('cc') or item.get('flag') or '').upper()
            if item_cc == cc_upper:
                return True
        ilat = item.get('lat') or item.get('latitude')
        ilng = item.get('lon') or item.get('lng') or item.get('longitude')
        try:
            ilat, ilng = float(ilat), float(ilng)
            return lat_min <= ilat <= lat_max and lng_min <= ilng <= lng_max
        except (TypeError, ValueError):
            return False

    # Filter all geo-tagged arrays from existing global data
    filtered = {}
    geo_keys = [
        'news', 'gdelt', 'global_events', 'earthquakes', 'cyber_threats',
        'piracy_incidents', 'natural_events', 'firms_hotspots', 'power_outages',
        'internet_outages', 'weather_alerts', 'liveuamap', 'commercial_flights',
        'private_flights', 'private_jets', 'military_flights', 'ships',
        'tracked_flights', 'military_bases', 'nuclear_facilities', 'embassies',
        'volcanoes', 'cell_towers', 'border_crossings', 'noaa_nwr',
        'kiwisdr_nodes', 'kismet_devices', 'snort_alerts', 'nmap_hosts',
        'nuclei_vulns', 'cctv', 'air_quality', 'radioactivity', 'satellites',
    ]
    for key in geo_keys:
        val = d.get(key, [])
        if isinstance(val, list):
            filtered[key] = [item for item in val if in_region(item)]
        else:
            filtered[key] = val

    # Fetch regional news & social media from dedicated sources
    from services.regional_feed import fetch_regional_feeds
    region_name = region or cc_upper
    regional = await asyncio.to_thread(fetch_regional_feeds, lat, lng, region_name, cc_upper)

    # REPLACE global news entirely with regional search results.
    # Global news has imprecise geocoding (country-center coords) that leaks
    # unrelated articles into the region.  Regional feed does targeted web
    # searches for "Nashville breaking news" etc., so it's higher quality.
    filtered['news'] = regional.get('news', [])

    # For social media: use regional results only (Reddit/Bluesky/Mastodon
    # searched specifically for this region).
    filtered['social_media'] = regional.get('social_media', [])

    # Non-geo data
    filtered['stocks'] = d.get('stocks', {})
    filtered['oil'] = d.get('oil', {})
    filtered['weather'] = d.get('weather')
    filtered['frontlines'] = d.get('frontlines')
    filtered['last_updated'] = d.get('last_updated')

    filtered['_regional'] = {
        'center': {'lat': lat, 'lng': lng},
        'radius_deg': radius,
        'country': cc_upper,
        'region': region_name,
        'news_count': len(filtered.get('news', [])),
        'social_count': len(filtered.get('social_media', [])),
        'total_items': sum(len(v) for v in filtered.values() if isinstance(v, list)),
    }

    return filtered


@app.get("/api/live-data/regional/stream")
async def live_data_regional_stream(lat: float, lng: float, radius: float = 5.0, country: str = "", region: str = ""):
    """SSE stream that sends regional data progressively as each source completes.

    First event: geo-filtered existing data (immediate).
    Subsequent events: news/social chunks as each web search finishes.
    Final event: 'done'.
    """
    from services.regional_feed import fetch_regional_feeds_streaming

    cc_upper = country.upper() if country else ""
    region_name = region or cc_upper

    async def event_generator():
        # 1) Immediately send geo-filtered existing data (map layers, flights, etc.)
        d = get_latest_data()
        lat_min, lat_max = lat - radius, lat + radius
        lng_min, lng_max = lng - radius, lng + radius

        def in_region(item):
            if not isinstance(item, dict):
                return False
            if cc_upper:
                item_cc = (item.get('country_code') or item.get('country') or
                           item.get('cc') or item.get('flag') or '').upper()
                if item_cc == cc_upper:
                    return True
            ilat = item.get('lat') or item.get('latitude')
            ilng = item.get('lon') or item.get('lng') or item.get('longitude')
            try:
                ilat, ilng = float(ilat), float(ilng)
                return lat_min <= ilat <= lat_max and lng_min <= ilng <= lng_max
            except (TypeError, ValueError):
                return False

        filtered = {}
        geo_keys = [
            'news', 'gdelt', 'global_events', 'earthquakes', 'cyber_threats',
            'piracy_incidents', 'natural_events', 'firms_hotspots', 'power_outages',
            'internet_outages', 'weather_alerts', 'liveuamap', 'commercial_flights',
            'private_flights', 'private_jets', 'military_flights', 'ships',
            'tracked_flights', 'military_bases', 'nuclear_facilities', 'embassies',
            'volcanoes', 'cell_towers', 'border_crossings', 'noaa_nwr',
            'kiwisdr_nodes', 'kismet_devices', 'snort_alerts', 'nmap_hosts',
            'nuclei_vulns', 'cctv', 'air_quality', 'radioactivity', 'satellites',
        ]
        for key in geo_keys:
            val = d.get(key, [])
            if isinstance(val, list):
                filtered[key] = [item for item in val if in_region(item)]
            else:
                filtered[key] = val

        # Clear news/social — will be filled by stream chunks
        filtered['news'] = []
        filtered['social_media'] = []
        filtered['stocks'] = d.get('stocks', {})
        filtered['oil'] = d.get('oil', {})
        filtered['weather'] = d.get('weather')
        filtered['frontlines'] = d.get('frontlines')
        filtered['last_updated'] = d.get('last_updated')
        filtered['_regional'] = {
            'center': {'lat': lat, 'lng': lng},
            'radius_deg': radius,
            'country': cc_upper,
            'region': region_name,
        }

        # Send initial geo data immediately
        yield f"event: init\ndata: {json_mod.dumps(filtered, default=str)}\n\n"

        # 2) Stream news/social as each source completes
        def _run_stream():
            results = []
            for source_name, category, items in fetch_regional_feeds_streaming(
                lat, lng, region_name, cc_upper
            ):
                results.append((source_name, category, items))
            return results

        loop = asyncio.get_event_loop()
        # Run the blocking generator in a thread, collecting results
        # We use a queue approach so we can yield as they arrive
        import queue
        q: queue.Queue = queue.Queue()
        sentinel = object()

        def _producer():
            try:
                for source_name, category, items in fetch_regional_feeds_streaming(
                    lat, lng, region_name, cc_upper
                ):
                    q.put((source_name, category, items))
            except Exception as e:
                logging.getLogger(__name__).debug(f"Stream producer error: {e}")
            finally:
                q.put(sentinel)

        import threading
        thread = threading.Thread(target=_producer, daemon=True)
        thread.start()

        while True:
            # Poll queue with small sleep to stay async-friendly
            try:
                item = await asyncio.to_thread(q.get, timeout=1)
            except Exception:
                # queue.get timeout — check if thread is done
                if not thread.is_alive():
                    break
                continue

            if item is sentinel:
                break

            source_name, category, items = item
            chunk = {
                'source': source_name,
                'category': category,
                'items': items,
                'count': len(items),
            }
            yield f"event: chunk\ndata: {json_mod.dumps(chunk, default=str)}\n\n"

        yield f"event: done\ndata: {{}}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/checkpoint/status")
async def checkpoint_status():
    """Check Point ThreatCloud SSE feed status."""
    from services.data_fetcher import _checkpoint_attacks, _checkpoint_stats, _checkpoint_thread
    return {
        "buffer_size": len(_checkpoint_attacks),
        "attacks_today": _checkpoint_stats.get("today", 0),
        "thread_alive": _checkpoint_thread.is_alive() if _checkpoint_thread else False,
        "last_5": [
            {"type": a.get("type"), "name": a.get("attack_name", "")[:60],
             "src": a.get("source_country"), "dst": a.get("country")}
            for a in list(_checkpoint_attacks)[-5:]
        ] if _checkpoint_attacks else [],
    }


@app.get("/api/osint/health")
async def osint_health():
    """Check OSINT agent reachability and tool availability."""
    import asyncio
    from services.osint_bridge import fetch_agent_health
    return await asyncio.to_thread(fetch_agent_health)


class OsintScanRequest(BaseModel):
    tool: str
    target: str
    scan_type: str = "quick"


@app.post("/api/osint/scan")
async def osint_trigger_scan(body: OsintScanRequest):
    """Trigger an on-demand scan via the OSINT agent."""
    import asyncio
    from services.osint_bridge import trigger_scan
    result = await asyncio.to_thread(trigger_scan, body.tool, body.target, scan_type=body.scan_type)

    # Schedule a delayed re-fetch so scan results appear in live-data quickly
    # instead of waiting for the 15-minute polling interval
    if result.get("job_id") or result.get("status") == "ok":
        from services.data_fetcher import scheduler, fetch_osint_nmap, fetch_osint_nuclei
        from datetime import datetime, timedelta
        if body.tool == "nmap":
            # Quick scans finish in ~10s, service scans ~30s
            for delay in [15, 30, 60]:
                scheduler.add_job(fetch_osint_nmap, 'date',
                    run_date=datetime.now() + timedelta(seconds=delay),
                    id=f'nmap-refresh-{delay}', replace_existing=True)
        elif body.tool == "nuclei":
            # Nuclei scans take 30s-5min
            for delay in [30, 60, 120, 300]:
                scheduler.add_job(fetch_osint_nuclei, 'date',
                    run_date=datetime.now() + timedelta(seconds=delay),
                    id=f'nuclei-refresh-{delay}', replace_existing=True)

    return result


@app.get("/api/osint/job/{job_id}")
async def osint_job_status(job_id: str):
    """Check status of an async scan job on the OSINT agent."""
    import asyncio
    from services.osint_bridge import fetch_job_status
    return await asyncio.to_thread(fetch_job_status, job_id)


@app.get("/api/osint/search/history")
async def api_osint_search_history():
    """Return OSINT search history from the agent."""
    import asyncio
    from services.osint_bridge import fetch_search_history
    return await asyncio.to_thread(fetch_search_history)


class OsintSearchRequest(BaseModel):
    query: str


@app.post("/api/osint/search")
async def api_osint_search(body: OsintSearchRequest):
    """Deep OSINT search — auto-detects input type, runs appropriate tools."""
    import asyncio
    from services.osint_bridge import deep_osint_search
    return await asyncio.to_thread(deep_osint_search, body.query)


# --- F.R.I.D.A.Y. Analysis Engine ---

@app.get("/api/syd/status")
async def api_friday_status():
    """Check F.R.I.D.A.Y. AI analysis engine status."""
    from services.osint_bridge import friday_status
    return await asyncio.to_thread(friday_status)


class FridayQueryRequest(BaseModel):
    question: str
    scan_data: str = ""
    module: str = "nmap"
    history: list = []


class FridayChatRequest(BaseModel):
    question: str
    context: str = ""


@app.post("/api/syd/query")
async def api_friday_query(body: FridayQueryRequest):
    """Ask F.R.I.D.A.Y. — auto-routes to scan analysis, entity analysis, OSINT, or general."""
    from services.osint_bridge import friday_query
    return await asyncio.to_thread(friday_query, body.question, body.scan_data, body.module, body.history)


@app.post("/api/syd/chat")
async def api_friday_chat(body: FridayChatRequest):
    """General F.R.I.D.A.Y. chat — works with or without entity context."""
    from services.osint_bridge import friday_chat
    return await asyncio.to_thread(friday_chat, body.question, body.context)


class FridayAnalyzeRequest(BaseModel):
    scan_data: str
    module: str = "nmap"


@app.post("/api/syd/analyze")
async def api_friday_analyze(body: FridayAnalyzeRequest):
    """Quick analysis — auto-detects entity type."""
    from services.osint_bridge import friday_analyze
    return await asyncio.to_thread(friday_analyze, body.scan_data, body.module)


@app.post("/api/syd/extract")
async def api_friday_extract(body: FridayAnalyzeRequest):
    """Extract facts only — no LLM, pure deterministic parsing."""
    from services.osint_bridge import friday_extract
    return await asyncio.to_thread(friday_extract, body.scan_data, body.module)


# ---------------------------------------------------------------------------
# LLM Provider Settings — proxy to OSINT agent
# ---------------------------------------------------------------------------

@app.get("/api/llm/status")
async def api_llm_status():
    """Get current LLM provider status from the OSINT agent."""
    import asyncio
    from services.osint_bridge import _get
    return await asyncio.to_thread(_get, "/llm/status")


class LlmProviderUpdate(BaseModel):
    provider: str
    ollama_base_url: str = ""
    ollama_model: str = ""


@app.put("/api/llm/provider")
async def api_set_llm_provider(body: LlmProviderUpdate):
    """Switch LLM provider on the OSINT agent."""
    import asyncio
    from services.osint_bridge import _put
    payload = {"provider": body.provider}
    if body.ollama_base_url:
        payload["ollama_base_url"] = body.ollama_base_url
    if body.ollama_model:
        payload["ollama_model"] = body.ollama_model
    return await asyncio.to_thread(_put, "/llm/provider", payload)


@app.get("/api/ollama/models")
async def api_ollama_models():
    """List available Ollama models from the OSINT agent."""
    import asyncio
    from services.osint_bridge import _get
    return await asyncio.to_thread(_get, "/ollama/models")


# ---------------------------------------------------------------------------
# User Scanner — Email/Username OSINT + Hudson Rock
# ---------------------------------------------------------------------------

class EmailScanBody(BaseModel):
    email: str


@app.post("/api/osint/email-scan")
async def api_osint_email_scan(body: EmailScanBody):
    """Scan email across 107 platforms for registrations."""
    import asyncio
    from services.osint_bridge import user_scanner_email
    return await asyncio.to_thread(user_scanner_email, body.email)


class UsernameScanBody(BaseModel):
    username: str


@app.post("/api/osint/username-scan")
async def api_osint_username_scan(body: UsernameScanBody):
    """Scan username across 91 platforms for account existence."""
    import asyncio
    from services.osint_bridge import user_scanner_username
    return await asyncio.to_thread(user_scanner_username, body.username)


class HudsonRockBody(BaseModel):
    target: str
    is_email: bool = False


@app.post("/api/osint/hudson-rock")
async def api_osint_hudson_rock(body: HudsonRockBody):
    """Query Hudson Rock infostealer intelligence."""
    import asyncio
    from services.osint_bridge import user_scanner_hudson_rock
    return await asyncio.to_thread(user_scanner_hudson_rock, body.target, body.is_email)


@app.get("/api/debug-latest")
async def debug_latest_data():
    return list(get_latest_data().keys())


@app.get("/api/health")
async def health_check():
    import time
    d = get_latest_data()
    last = d.get("last_updated")
    return {
        "status": "ok",
        "last_updated": last,
        "sources": {
            "flights": len(d.get("commercial_flights", [])),
            "military": len(d.get("military_flights", [])),
            "ships": len(d.get("ships", [])),
            "satellites": len(d.get("satellites", [])),
            "earthquakes": len(d.get("earthquakes", [])),
            "cctv": len(d.get("cctv", [])),
            "news": len(d.get("news", [])),
        },
        "uptime_seconds": round(time.time() - _start_time),
    }

_start_time = __import__("time").time()

from services.radio_intercept import get_top_broadcastify_feeds, get_openmhz_systems, get_recent_openmhz_calls, find_nearest_openmhz_system

@app.get("/api/radio/top")
async def get_top_radios():
    return get_top_broadcastify_feeds()

@app.get("/api/radio/openmhz/systems")
async def api_get_openmhz_systems():
    return get_openmhz_systems()

@app.get("/api/radio/openmhz/calls/{sys_name}")
async def api_get_openmhz_calls(sys_name: str):
    return get_recent_openmhz_calls(sys_name)

@app.get("/api/radio/nearest")
async def api_get_nearest_radio(lat: float, lng: float):
    return find_nearest_openmhz_system(lat, lng)

from services.radio_intercept import find_nearest_openmhz_systems_list

@app.get("/api/radio/nearest-list")
async def api_get_nearest_radios_list(lat: float, lng: float, limit: int = 5):
    return find_nearest_openmhz_systems_list(lat, lng, limit=limit)

from services.network_utils import fetch_with_curl

@app.get("/api/route/{callsign}")
async def get_flight_route(callsign: str):
    r = fetch_with_curl("https://api.adsb.lol/api/0/routeset", method="POST", json_data={"planes": [{"callsign": callsign}]}, timeout=10)
    if r.status_code == 200:
        data = r.json()
        route_list = []
        if isinstance(data, dict):
            route_list = data.get("value", [])
        elif isinstance(data, list):
            route_list = data
        
        if route_list and len(route_list) > 0:
            route = route_list[0]
            airports = route.get("_airports", [])
            if len(airports) >= 2:
                return {
                    "orig_loc": [airports[0].get("lon", 0), airports[0].get("lat", 0)],
                    "dest_loc": [airports[-1].get("lon", 0), airports[-1].get("lat", 0)]
                }
    return {}

from services.region_dossier import get_region_dossier

@app.get("/api/region-dossier")
def api_region_dossier(lat: float, lng: float):
    """Sync def so FastAPI runs it in a threadpool — prevents blocking the event loop."""
    return get_region_dossier(lat, lng)

# ---------------------------------------------------------------------------
# API Settings — key registry & management
# ---------------------------------------------------------------------------
from services.api_settings import get_api_keys, update_api_key
from pydantic import BaseModel

class ApiKeyUpdate(BaseModel):
    env_key: str
    value: str

@app.get("/api/settings/api-keys")
async def api_get_keys():
    return get_api_keys()

@app.put("/api/settings/api-keys")
async def api_update_key(body: ApiKeyUpdate):
    ok = update_api_key(body.env_key, body.value)
    if ok:
        return {"status": "updated", "env_key": body.env_key}
    return {"status": "error", "message": "Failed to update .env file"}

# ---------------------------------------------------------------------------
# Satellite Pass Prediction — SGP4-based AOS/TCA/LOS
# ---------------------------------------------------------------------------
@app.get("/api/satellite/passes")
def api_satellite_passes(lat: float, lon: float, hours: int = 24, min_el: float = 10.0, norad_id: int = None):
    """Predict upcoming satellite passes for observer location using SGP4."""
    import math
    from sgp4.api import Satrec, jday, WGS72
    from datetime import datetime, timedelta

    d = get_latest_data()
    gp_data = d.get("_sat_gp_cache", {}).get("data")
    if not gp_data:
        # Try to get from the data_fetcher cache directly
        from services.data_fetcher import _sat_gp_cache
        gp_data = _sat_gp_cache.get("data", [])
    if not gp_data:
        return {"passes": [], "error": "No satellite catalog available"}

    def ecef_to_topo(sat_x, sat_y, sat_z, obs_lat, obs_lon, obs_alt_km=0):
        """Convert ECEF satellite position to topocentric az/el from observer."""
        lat_r = math.radians(obs_lat)
        lon_r = math.radians(obs_lon)
        R = 6378.137
        f = 1 / 298.257223563
        C = 1 / math.sqrt(1 - (2*f - f*f) * math.sin(lat_r)**2)
        S = (1 - (2*f - f*f)) * C
        ox = (R * C + obs_alt_km) * math.cos(lat_r) * math.cos(lon_r)
        oy = (R * C + obs_alt_km) * math.cos(lat_r) * math.sin(lon_r)
        oz = (R * S + obs_alt_km) * math.sin(lat_r)
        rx, ry, rz = sat_x - ox, sat_y - oy, sat_z - oz
        # Rotate to topocentric SEZ
        sin_lat, cos_lat = math.sin(lat_r), math.cos(lat_r)
        sin_lon, cos_lon = math.sin(lon_r), math.cos(lon_r)
        south = sin_lat*cos_lon*rx + sin_lat*sin_lon*ry - cos_lat*rz
        east = -sin_lon*rx + cos_lon*ry
        zenith = cos_lat*cos_lon*rx + cos_lat*sin_lon*ry + sin_lat*rz
        rng = math.sqrt(south**2 + east**2 + zenith**2)
        el = math.degrees(math.asin(zenith / rng)) if rng > 0 else 0
        az = math.degrees(math.atan2(east, -south)) % 360
        return az, el, rng

    # Filter to specific NORAD ID or pick top intel satellites
    targets = []
    if norad_id:
        targets = [s for s in gp_data if s.get("NORAD_CAT_ID") == norad_id]
    else:
        # Pick ISS + a few notable satellites
        notable_ids = {25544, 48274, 43013, 41866, 40069, 28654, 33591, 39084, 25338}
        targets = [s for s in gp_data if s.get("NORAD_CAT_ID") in notable_ids]
        if not targets:
            targets = gp_data[:20]

    now = datetime.utcnow()
    passes = []
    step_sec = 30  # 30-second resolution

    for sat in targets[:50]:  # Cap at 50 sats to prevent OOM
        try:
            epoch = sat.get("EPOCH", "")
            if not epoch:
                continue
            satrec = Satrec()
            # Build from GP elements
            ep = datetime.strptime(epoch[:19], "%Y-%m-%dT%H:%M:%S")
            yr2 = ep.year % 100
            day_of_year = (ep - datetime(ep.year, 1, 1)).total_seconds() / 86400 + 1
            satrec.sgp4init(
                WGS72, 'i', int(sat.get("NORAD_CAT_ID", 0)),
                (jday(ep.year, ep.month, ep.day, ep.hour, ep.minute, ep.second)[0] +
                 jday(ep.year, ep.month, ep.day, ep.hour, ep.minute, ep.second)[1] - 2433281.5),
                float(sat.get("BSTAR", 0) or 0),
                0.0, 0.0,
                float(sat.get("ECCENTRICITY", 0) or 0),
                math.radians(float(sat.get("ARG_OF_PERICENTER", 0) or 0)),
                math.radians(float(sat.get("INCLINATION", 0) or 0)),
                math.radians(float(sat.get("MEAN_ANOMALY", 0) or 0)),
                float(sat.get("MEAN_MOTION", 15) or 15) * 2 * math.pi / 1440,
                math.radians(float(sat.get("RA_OF_ASC_NODE", 0) or 0)),
            )
        except Exception:
            continue

        # Scan for passes
        in_pass = False
        pass_data = None
        max_el = 0

        for t_offset in range(0, hours * 3600, step_sec):
            t = now + timedelta(seconds=t_offset)
            jd, fr = jday(t.year, t.month, t.day, t.hour, t.minute, t.second)
            e, r_teme, v_teme = satrec.sgp4(jd, fr)
            if e != 0:
                continue

            # TEME to ECEF (simplified — ignore polar motion)
            gmst = _gmst(jd + fr) if '_gmst' in dir() else 0
            try:
                from services.data_fetcher import _gmst
                gmst = _gmst(jd + fr)
            except Exception:
                gmst_sec = 67310.54841 + (876600.0*3600 + 8640184.812866) * ((jd + fr - 2451545.0)/36525.0)
                gmst = (gmst_sec % 86400) / 86400.0 * 2 * math.pi

            cos_g, sin_g = math.cos(gmst), math.sin(gmst)
            x_ecef = cos_g * r_teme[0] + sin_g * r_teme[1]
            y_ecef = -sin_g * r_teme[0] + cos_g * r_teme[1]
            z_ecef = r_teme[2]

            az, el, rng = ecef_to_topo(x_ecef, y_ecef, z_ecef, lat, lon)

            if el >= min_el:
                if not in_pass:
                    in_pass = True
                    pass_data = {
                        "norad_id": sat.get("NORAD_CAT_ID"),
                        "name": sat.get("OBJECT_NAME", "Unknown"),
                        "aos": t.isoformat() + "Z",
                        "aos_az": round(az, 1),
                        "max_el": round(el, 1),
                        "tca": t.isoformat() + "Z",
                        "tca_az": round(az, 1),
                        "los": None, "los_az": None,
                        "points": []
                    }
                    max_el = el
                if el > max_el:
                    max_el = el
                    pass_data["max_el"] = round(el, 1)
                    pass_data["tca"] = t.isoformat() + "Z"
                    pass_data["tca_az"] = round(az, 1)
                pass_data["points"].append({
                    "t": t.isoformat() + "Z",
                    "az": round(az, 1), "el": round(el, 1),
                    "range_km": round(rng, 0)
                })
            else:
                if in_pass and pass_data:
                    pass_data["los"] = t.isoformat() + "Z"
                    pass_data["los_az"] = round(az, 1)
                    passes.append(pass_data)
                    in_pass = False
                    pass_data = None

        # Close any pass still open at end of window
        if in_pass and pass_data:
            passes.append(pass_data)

    passes.sort(key=lambda p: p["aos"])
    return {"passes": passes[:100], "observer": {"lat": lat, "lon": lon}, "window_hours": hours}


# ---------------------------------------------------------------------------
# AI Track Analysis — LLM-based anomaly assessment
# ---------------------------------------------------------------------------
from fastapi.responses import StreamingResponse

@app.get("/api/analyze/{entity_type}/{entity_id}")
def api_analyze_track(entity_type: str, entity_id: str):
    """AI-powered track/entity analysis using Claude API if available."""
    import os
    d = get_latest_data()

    # Gather entity data based on type
    entity_data = None
    if entity_type == "flight":
        for cat in ["commercial_flights", "military_flights", "private_flights", "private_jets", "tracked_flights"]:
            for f in d.get(cat, []):
                if f.get("hex") == entity_id or f.get("flight", "").strip() == entity_id:
                    entity_data = f
                    break
            if entity_data:
                break
    elif entity_type == "ship":
        for s in d.get("ships", []):
            if str(s.get("mmsi")) == entity_id or s.get("name", "") == entity_id:
                entity_data = s
                break
    elif entity_type == "satellite":
        for s in d.get("satellites", []):
            if str(s.get("id")) == entity_id:
                entity_data = s
                break

    if not entity_data:
        return {"analysis": f"No data found for {entity_type} {entity_id}", "source": "system"}

    # Build analysis prompt
    context = json_mod.dumps(entity_data, indent=2, default=str)
    prompt = f"""You are a senior intelligence analyst. Analyze this {entity_type} track data and identify any anomalies, assess threat level, and provide operational intelligence assessment.

Entity Type: {entity_type}
Entity ID: {entity_id}
Current Data:
{context}

Provide a brief but thorough intelligence assessment including:
1. Entity identification and classification
2. Any anomalous behavior (unusual altitude, speed, heading, position)
3. Operational context (what might this entity be doing)
4. Threat assessment (LOW/MEDIUM/HIGH/CRITICAL)
5. Recommended monitoring priority"""

    # Determine LLM provider preference
    llm_provider = os.environ.get("LLM_PROVIDER", "claude")

    # Try Claude API if provider is claude and ANTHROPIC_API_KEY is set
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if llm_provider == "claude" and api_key:
        try:
            import requests
            resp = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json"
                },
                json={
                    "model": "claude-haiku-4-5-20251001",
                    "max_tokens": 500,
                    "messages": [{"role": "user", "content": prompt}]
                },
                timeout=30
            )
            if resp.status_code == 200:
                result = resp.json()
                text = result.get("content", [{}])[0].get("text", "Analysis unavailable")
                return {"analysis": text, "source": "claude-haiku", "entity": entity_data}
        except Exception as e:
            logger.warning(f"Claude API analysis failed: {e}")

    # Try Ollama if provider is ollama (or Claude failed)
    ollama_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model = os.environ.get("OLLAMA_MODEL", "llama3")
    if llm_provider == "ollama" or (llm_provider == "claude" and not api_key):
        try:
            import urllib.request
            system_msg = (
                "You are a senior intelligence analyst. "
                "CRITICAL: ONLY use data explicitly provided. NEVER invent or guess values. "
                "Quote exact callsigns, registrations, coordinates, speeds, and altitudes from the data. "
                "If a field is missing, say 'not available'. Keep analysis concise."
            )
            payload = json_mod.dumps({
                "model": ollama_model,
                "messages": [
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": prompt},
                ],
                "stream": False,
                "options": {"num_predict": 1024, "temperature": 0.3},
            }).encode()
            req = urllib.request.Request(
                f"{ollama_url}/api/chat",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            resp = urllib.request.urlopen(req, timeout=60)
            data = json_mod.loads(resp.read())
            msg = data.get("message", {})
            text = msg.get("content", "").strip() if isinstance(msg, dict) else ""
            if text:
                return {"analysis": text, "source": f"ollama/{ollama_model}", "entity": entity_data}
        except Exception as e:
            logger.warning(f"Ollama analysis failed: {e}")

    # Fallback: rule-based analysis
    analysis = _rule_based_analysis(entity_type, entity_data)
    return {"analysis": analysis, "source": "rule-engine", "entity": entity_data}


def _rule_based_analysis(entity_type, data):
    """Rule-based track analysis fallback when no LLM is available."""
    lines = [f"INTELLIGENCE ASSESSMENT — {entity_type.upper()}"]
    lines.append(f"{'='*50}")

    if entity_type == "flight":
        callsign = data.get("flight", "UNKNOWN").strip()
        alt = data.get("alt_baro", 0)
        gs = data.get("gs", 0)
        squawk = data.get("squawk", "")
        lines.append(f"CALLSIGN: {callsign}")
        lines.append(f"ALTITUDE: {alt} ft | SPEED: {gs} kts")
        if squawk == "7700":
            lines.append("⚠ SQUAWK 7700 — EMERGENCY DECLARED")
            lines.append("THREAT LEVEL: HIGH — Aircraft in distress")
        elif squawk == "7600":
            lines.append("⚠ SQUAWK 7600 — RADIO FAILURE")
            lines.append("THREAT LEVEL: MEDIUM — Communications lost")
        elif squawk == "7500":
            lines.append("⚠ SQUAWK 7500 — HIJACK")
            lines.append("THREAT LEVEL: CRITICAL — Possible hijacking")
        elif alt == 0 and gs > 50:
            lines.append("NOTE: Ground-level high-speed movement — possible military low-level ops")
            lines.append("THREAT LEVEL: MEDIUM")
        elif alt > 50000:
            lines.append("NOTE: Extreme altitude — possible U-2/RQ-4 reconnaissance platform")
            lines.append("THREAT LEVEL: HIGH — ISR asset")
        else:
            lines.append("ASSESSMENT: Normal flight parameters")
            lines.append("THREAT LEVEL: LOW")
    elif entity_type == "ship":
        name = data.get("name", "UNKNOWN")
        stype = data.get("type", "unknown")
        speed = data.get("speed", 0)
        lines.append(f"VESSEL: {name} | TYPE: {stype}")
        if stype in ("carrier", "military_vessel"):
            lines.append("CLASSIFICATION: Military vessel — high monitoring priority")
            lines.append("THREAT LEVEL: HIGH")
        elif speed == 0:
            lines.append("NOTE: Vessel stationary — possible anchorage or loiter")
            lines.append("THREAT LEVEL: LOW")
        else:
            lines.append("ASSESSMENT: Normal maritime traffic")
            lines.append("THREAT LEVEL: LOW")
    elif entity_type == "satellite":
        name = data.get("name", "UNKNOWN")
        lines.append(f"SATELLITE: {name}")
        cat = data.get("category", "")
        if "SIGINT" in cat or "IMINT" in cat or "ELINT" in cat:
            lines.append(f"CLASSIFICATION: {cat} — Intelligence collection platform")
            lines.append("THREAT LEVEL: HIGH — Active ISR")
        else:
            lines.append(f"CATEGORY: {cat}")
            lines.append("THREAT LEVEL: LOW")

    return "\n".join(lines)


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

# Application successfully initialized with background scraping tasks
