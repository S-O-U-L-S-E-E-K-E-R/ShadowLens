<p align="center">
  <h1 align="center">S H A D O W L E N S</h1>
  <p align="center"><strong>Real-Time Geospatial Intelligence Platform</strong></p>
</p>

---

![ShadowLens](https://github.com/user-attachments/assets/63c8d39a-b629-42f0-9367-b96fea1ee636)

**ShadowLens** is a real-time geospatial intelligence dashboard that aggregates live data from 60+ open-source intelligence (OSINT) feeds and renders them on a unified map interface. It tracks aircraft, ships, satellites, earthquakes, conflict zones, CCTV networks, GPS jamming, cyber threats, and breaking geopolitical events — all updating in real time.

Built with **Next.js 16**, **MapLibre GL**, **FastAPI**, and **Python**.

### F.R.I.D.A.Y. — AI Analysis Engine

ShadowLens includes **F.R.I.D.A.Y.**, an AI analysis engine powered by **Claude Code CLI**. Select a flight, ship, military base, network host, or any other entity and F.R.I.D.A.Y. provides:

* **Instant fact extraction** — Deterministic parsing of entity data (no AI, instant)
* **Deep LLM analysis** — Claude-powered RAG pipeline with FAISS indexes for vulnerability assessment, risk analysis, and recommendations
* **Anti-hallucination validation** — 3-stage pipeline ensures answers are grounded in actual data
* **Specialized modules** — Nmap scan parser, BloodHound AD attack path analysis, Volatility memory forensics
* **Tool access** — F.R.I.D.A.Y. can run OSINT tools directly when answering research questions

Requires [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) installed and authenticated on the host.

### OSINT Agent — 18+ Security Tools

The integrated OSINT agent (port 8002) provides one-click access to:

`nmap` · `nuclei` · `whatweb` · `theHarvester` · `spiderfoot` · `sherlock` · `h8mail` · `whois` · `dmitry` · `subfinder` · `dnsrecon` · `shodan` · `phoneinfoga` · `maigret` · `holehe` · `autorecon` · `kismet` · `snort`

Deep OSINT search auto-detects input type (IP, domain, email, phone, username, hash) and runs the appropriate tool combination.

---

## Quick Start

### Docker (Recommended)

```bash
git clone https://github.com/S-O-U-L-S-E-E-K-E-R/ShadowLens.git
cd ShadowLens

# First time: run setup to install everything
chmod +x setup.sh
./setup.sh

# Edit .env with your API keys (AIS_API_KEY required at minimum)
nano .env

# Launch
./start.sh
```

`setup.sh` handles the full first-time install:
1. Creates `.env` from template
2. Sets up OSINT agent Python venv and dependencies
3. Installs OSINT tools via apt/pip/go (nmap, nuclei, whatweb, sherlock, etc.)
4. Builds Docker images

`start.sh` launches everything:
1. Starts Docker containers (frontend on port 3000, backend on port 8001)
2. Starts the OSINT agent on port 8002
3. Waits for F.R.I.D.A.Y. engine to initialize

Open `http://localhost:3000` to view the dashboard.

### Windows

```bash
# From the project root
cd frontend
npm install
cd ../backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
cd ../frontend
npm run dev
```

`npm run dev` starts both the Next.js frontend (port 3000) and the FastAPI backend concurrently. Docker must be running separately if using containers.

### After a Reboot

```bash
cd /path/to/ShadowLens
./start.sh
```

### Requirements

* **Docker** and **docker compose** (for containerized deployment)
* **Python 3.10+** with venv (for OSINT agent)
* **Node.js 18+** and **npm** (for development mode only)
* **[Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code)** (required for F.R.I.D.A.Y. AI analysis — must be installed and authenticated on the host)
* **Go** (optional — for installing nuclei, subfinder, phoneinfoga)

The `setup.sh` script auto-installs these OSINT tools:

| Tool | Install Method | Purpose |
|---|---|---|
| nmap | apt | Port and service scanning |
| nuclei | go install | Vulnerability scanning |
| whatweb | apt | Web technology fingerprinting |
| theHarvester | pip | Email and domain OSINT |
| sherlock | pip | Username search across sites |
| h8mail | pip | Breach data lookups |
| maigret | pip | Username search (extended) |
| holehe | pip | Email registration checker |
| subfinder | go install | Subdomain discovery |
| dnsrecon | apt | DNS enumeration |
| whois | apt | Domain registration lookup |
| dmitry | apt | Host intelligence gathering |
| shodan | pip | Internet-wide scanner CLI |
| spiderfoot | pip | OSINT investigation framework |
| autorecon | pip | Full reconnaissance framework |
| phoneinfoga | go install | Phone number OSINT |
| kismet | apt | WiFi/Bluetooth monitoring |
| snort | apt | Network intrusion detection |

---

## Features

### 37 Data Layers

All layers are independently toggleable from the left panel:

**Aviation**

| Layer | Source | Update | Key Required |
|---|---|---|---|
| Commercial Flights | adsb.lol / adsb.fi / airplanes.live (round-robin) | ~60s | No |
| Private Flights | ADS-B Exchange | ~60s | No |
| Private Jets | ADS-B Exchange + Plane-Alert DB | ~60s | No |
| Military Flights | adsb.lol /v2/mil endpoint | ~60s | No |
| Tracked Aircraft | ADS-B + Plane-Alert watchlist | ~60s | No |
| Flight Restrictions (TFR) | FAA NOTAM | ~300s | No |

* OpenSky Network used as fallback for regions where primary sources are rate-limited (requires OAuth2 credentials)
* Flight route lookup via adsb.lol API
* Holding pattern detection (>300 deg total turn)
* Shape-accurate SVG icons by aircraft type (airliner, turboprop, bizjet, helicopter, fighter)

**Maritime**

| Layer | Source | Update | Key Required |
|---|---|---|---|
| Carriers / Military / Cargo | AIS Stream WebSocket | Real-time | Yes |
| Civilian Vessels | AIS Stream WebSocket | Real-time | Yes |
| Cruise / Passenger | AIS Stream WebSocket | Real-time | Yes |

* 11 US Navy carrier strike groups tracked via GDELT news scraping with fallback OSINT positions
* Vessel classification by AIS type code (tanker, cargo, passenger, yacht, military, fishing)
* Flag state detection from MMSI Maritime Identification Digits
* Carrier positions auto-update at 00:00 and 12:00 UTC

**Space**

| Layer | Source | Update | Key Required |
|---|---|---|---|
| Satellites | CelesTrak TLE + SGP4 propagation | ~30min | No |

* 2,000+ active satellites with real-time orbital position calculation
* Color-coded by mission type: military recon, SAR, SIGINT, navigation, early warning, commercial imaging, space station
* Satellite pass prediction API for any observer location (AOS/TCA/LOS)
* Fallback to tle.ivanstanojevic.me when CelesTrak is blocked

**Geopolitics and Conflict**

| Layer | Source | Update | Key Required |
|---|---|---|---|
| Ukraine Frontline | DeepState Map (GitHub mirror) | ~30min | No |
| Global Incidents | GDELT + LiveUAMap | ~6h / ~5min | No |
| Global Events | GDACS + ReliefWeb + WHO | ~30min | No |
| Piracy Incidents | NGA ASAM | ~30min | No |

**Environment and Hazards**

| Layer | Source | Update | Key Required |
|---|---|---|---|
| Earthquakes (24h) | USGS | ~10min | No |
| Weather Alerts | NOAA NWS CAP | ~10min | No |
| Natural Events | GDACS (floods, cyclones, tsunamis) | ~10min | No |
| Fire Hotspots | NASA FIRMS (MODIS/VIIRS) | ~30min | No |
| Volcanoes | Smithsonian GVP | ~30min | No |
| Air Quality | OpenAQ / AirNow EPA | ~10min | Optional |
| Space Weather | NOAA SWPC | ~10min | No |
| Radioactivity | EPA RadNet + EURDEP | ~10min | No |
| Day/Night Cycle | Solar terminator calculation | Continuous | No |

**Infrastructure**

| Layer | Source | Update | Key Required |
|---|---|---|---|
| CCTV Mesh | 21 ingestors (see below) | ~60s | Mixed |
| Military Bases | Hardcoded DB (200+ US/NATO) | Startup | No |
| Nuclear Facilities | IAEA GIS (200+ reactors) | Startup | No |
| Submarine Cables | TeleGeography | Startup | No |
| Cable Landing Points | TeleGeography | Startup | No |
| Embassies | Wikidata | Startup | No |
| Cell Towers | OpenCellID | 7-day cache | Yes |
| Reservoirs / Dams | USGS Water | Startup | No |
| Border Crossings | US CBP | Startup | No |
| KiwiSDR Nodes | KiwiSDR network | ~1h | No |

**Signals and Cyber**

| Layer | Source | Update | Key Required |
|---|---|---|---|
| GPS Jamming | NAC-P analysis from ADS-B | ~60s | No |
| Cyber Threats | abuse.ch | ~10min | No |
| Power Outages | PowerOutage.us | Manual | No |
| Internet Outages | Cloudflare + IODA | Manual | No |

**Local / Network OSINT** (requires OSINT agent)

| Layer | Source | Update | Key Required |
|---|---|---|---|
| WiFi/BT Devices | Kismet | ~15min | Optional |
| IDS Alerts | Snort | ~15min | No |
| Network Hosts | Nmap | ~15min | No |
| Vulnerabilities | Nuclei | ~15min | No |

### CCTV Sources (21 Ingestors)

Transport for London JamCams, Singapore LTA, Austin TX TxDOT, NYC DOT, Tennessee DOT SmartWay, Clarksville City, Fort Campbell (KYTC), Clarksville Area Webcams, NC5 Skynet, WSMV Weather Cams, NPS Great Smoky Mountains, Resort Cams TN, Gatlinburg Tourist, Caltrans CA, Florida 511, Virginia DOT, Louisiana 511, Louisiana Wetmet, KSLA Static, Global OpenStreetMap crawling.

### Additional Features

* **Region Dossier** — Right-click anywhere for country profile (population, capital, languages, currencies, leader, government type), local Wikipedia summary
* **News Feed** — 60+ RSS sources (Reuters, AP, BBC, Al Jazeera, NYT, defense/security outlets, regional conflict sources, cyber security feeds)
* **Regional Feed** — Location-aware news from Google, Bing, DuckDuckGo, GDELT, Reddit, Bluesky, Mastodon (via SSE streaming)
* **Radio Scanner** — Broadcastify top feeds + OpenMHz scanner systems with nearest-system lookup
* **Global Markets Ticker** — Defense sector stocks (RTX, LMT, NOC, BA) and oil prices (WTI, Brent) via yfinance
* **Flight Route Lookup** — Origin/destination for any tracked flight
* **Satellite Pass Prediction** — SGP4-based AOS/TCA/LOS for any observer location
* **Measurement Tool** — Point-to-point distance and bearing on the map
* **API Key Management** — In-app settings panel for configuring all API keys

---

## Architecture

```
ShadowLens/
|
|-- Frontend (Next.js, port 3000) ----- Docker container
|   |-- MapLibre GL map with 37 data layers
|   |-- News feed, radio scanner, markets ticker
|   |-- F.R.I.D.A.Y. analysis panel
|   |-- OSINT search bar (auto-detects input type)
|
|-- Backend (FastAPI, port 8001) ------- Docker container
|   |-- Data fetcher scheduler (60+ sources)
|   |-- AIS WebSocket client (real-time ships)
|   |-- Carrier tracker (GDELT OSINT)
|   |-- CCTV pipeline (21 ingestors)
|   |-- Region dossier (Nominatim + RestCountries + Wikidata + Wikipedia)
|   |-- Satellite pass predictor (SGP4)
|   |-- Regional news aggregator (Google/Bing/Reddit/Bluesky/Mastodon)
|
|-- OSINT Agent (FastAPI, port 8002) --- Host process (not Docker)
|   |-- 18+ security tool runners
|   |-- F.R.I.D.A.Y. engine (FAISS RAG + LLM)
|   |-- Deep search (auto-detection pipeline)
|   |-- Job queue for async scans
```

The backend runs inside Docker and reaches the OSINT agent on the host via `host.docker.internal:8002`.

---

## Project Structure

```
ShadowLens/
|-- setup.sh                        # First-time setup (installs all tools + builds Docker)
|-- start.sh                        # One-command startup (Docker + OSINT Agent + F.R.I.D.A.Y.)
|-- start.bat                       # Windows startup (dev mode)
|-- docker-compose.yml              # Frontend + Backend containers
|-- .env.example                    # Template for all environment variables
|
|-- backend/                        # FastAPI backend (Docker, port 8001 -> 8000)
|   |-- main.py                     # API routes, middleware, OSINT/F.R.I.D.A.Y. proxy
|   |-- services/
|   |   |-- data_fetcher.py         # Core scheduler — fetches 60+ data sources
|   |   |-- ais_stream.py           # AIS WebSocket client (real-time vessels)
|   |   |-- carrier_tracker.py      # OSINT carrier position tracker
|   |   |-- cctv_pipeline.py        # 21 CCTV camera ingestors
|   |   |-- geopolitics.py          # GDELT + Ukraine frontline
|   |   |-- region_dossier.py       # Right-click country/city intelligence
|   |   |-- regional_feed.py        # Location-aware news + social media
|   |   |-- osint_bridge.py         # Proxy to host OSINT agent
|   |   |-- api_settings.py         # API key registry and management
|   |   |-- network_utils.py        # HTTP client with curl fallback
|   |   |-- radio_intercept.py      # Broadcastify + OpenMHz scanner feeds
|   |   +-- liveuamap_scraper.py    # Ukraine conflict map scraper
|
|-- frontend/                       # Next.js frontend (Docker, port 3000)
|   +-- src/
|       |-- app/page.tsx            # Main dashboard — state, polling, layout
|       +-- components/
|           |-- MaplibreViewer.tsx   # Core map — all GeoJSON layers + rendering
|           |-- NewsFeed.tsx        # News feed + entity panels + F.R.I.D.A.Y. chat
|           |-- FindLocateBar.tsx   # OSINT search bar with type detection
|           |-- WorldviewLeftPanel.tsx   # Data layer toggles
|           |-- WorldviewRightPanel.tsx  # Recording, display, orbit tracking
|           |-- SettingsPanel.tsx   # API key management UI
|           |-- RadioInterceptPanel.tsx  # Scanner-style radio monitoring
|           |-- MarketsPanel.tsx    # Defense stocks + oil ticker
|           +-- ...                 # Legend, filters, onboarding, scale bar
|
|-- osint-agent/                    # Host-side OSINT engine (port 8002)
|   |-- main.py                     # FastAPI — scan endpoints, F.R.I.D.A.Y. API
|   |-- config.py                   # Tool detection, host geolocation
|   |-- runners/                    # Tool wrappers
|   |   |-- nmap.py                 # Port/service scanning (RFC1918 validated)
|   |   |-- nuclei.py              # Vulnerability scanning
|   |   |-- kismet.py              # WiFi/BT device tracking
|   |   |-- snort.py               # IDS alert parsing
|   |   |-- harvester.py           # theHarvester domain recon
|   |   |-- spiderfoot.py          # SpiderFoot OSINT investigation
|   |   |-- whatweb.py             # Web technology fingerprinting
|   |   |-- deep_search.py         # Multi-tool OSINT (auto-detects input type)
|   |   |-- person_search.py       # People lookup
|   |   +-- autorecon.py           # Full reconnaissance framework
|   +-- syd/                        # F.R.I.D.A.Y. engine
|       |-- engine.py               # Core RAG pipeline
|       |-- nmap_fact_extractor.py  # Nmap scan parser
|       |-- bloodhound_fact_extractor.py  # AD attack path parser
|       |-- volatility_fact_extractor.py  # Memory forensics parser
|       +-- rag_data/               # FAISS indexes + knowledge chunks
```

---

## Environment Variables

Copy `.env.example` to `.env` and fill in your keys:

```env
# Required
AIS_API_KEY=                    # Maritime vessel tracking (aisstream.io)

# Recommended
OPENSKY_CLIENT_ID=              # Flight data — higher rate limits (opensky-network.org)
OPENSKY_CLIENT_SECRET=          # Paired with Client ID above

# Optional
OPENCELLID_API_KEY=             # Cell tower locations
LTA_ACCOUNT_KEY=                # Singapore CCTV cameras
TDOT_SMARTWAY_API_KEY=          # Tennessee DOT cameras

# OSINT Tools (all optional, enable as needed)
SHODAN_API_KEY=                 # Internet-wide scanner
HIBP_API_KEY=                   # Breach database lookups
VIRUSTOTAL_API_KEY=             # Malware/URL scanning
CENSYS_API_ID=                  # Certificate/host search
CENSYS_API_SECRET=              # Paired with Censys ID
HUNTER_API_KEY=                 # Email finder
GREYNOISE_API_KEY=              # Scanner intelligence
ABUSEIPDB_API_KEY=              # IP reputation
IPINFO_API_KEY=                 # IP geolocation
NUMVERIFY_API_KEY=              # Phone number lookup
KISMET_API_KEY=                 # Wireless IDS auth
# See .env.example for the full list
```

---

## API Endpoints

| Endpoint | Description |
|---|---|
| `GET /api/live-data/fast` | Real-time tier: flights, ships, CCTV, GPS jamming, news (~60s) |
| `GET /api/live-data/slow` | Cached tier: earthquakes, satellites, stocks, weather, GDELT (~5-30min) |
| `GET /api/live-data/static` | Static tier: military bases, nuclear facilities, cables, embassies (~1h) |
| `GET /api/live-data/osint` | Network OSINT: Kismet, Snort, Nmap, Nuclei results |
| `GET /api/live-data/regional` | Location-filtered data + regional news/social media |
| `GET /api/live-data/regional/stream` | SSE stream with progressive news chunks |
| `GET /api/region-dossier` | Country profile, leader, Wikipedia summary for any coordinates |
| `GET /api/satellite/passes` | SGP4 pass prediction for observer location |
| `GET /api/route/{callsign}` | Flight route origin/destination lookup |
| `POST /api/osint/scan` | Trigger nmap/nuclei/whatweb/harvester/spiderfoot scan |
| `POST /api/osint/search` | Deep OSINT search (auto-detects input type) |
| `POST /api/syd/query` | F.R.I.D.A.Y. analysis with scan context |
| `POST /api/syd/chat` | F.R.I.D.A.Y. general chat |
| `GET /api/settings/api-keys` | View configured API keys (obfuscated) |
| `PUT /api/settings/api-keys` | Update an API key |
| `GET /api/health` | Uptime, last update times, source counts |

---

## Performance

* **Gzip Compression** — API payloads compressed ~92%
* **ETag Caching** — 304 Not Modified responses skip redundant JSON parsing
* **Viewport Culling** — Only features within visible map bounds (+20% buffer) are rendered
* **Clustered Rendering** — Ships, CCTV, and earthquakes use MapLibre clustering
* **Debounced Viewport Updates** — 300ms debounce prevents GeoJSON rebuild thrash during pan/zoom
* **Position Interpolation** — Smooth 10s tick animation between data refreshes
* **Coordinate Precision** — Lat/lng rounded to 5 decimals (~1m) to reduce JSON size

---

## Disclaimer

This is an **educational and research tool** built entirely on publicly available, open-source intelligence (OSINT) data. No classified, restricted, or non-public data sources are used. Carrier positions are estimates based on public reporting.

**Do not use this tool for any operational, military, or intelligence purpose.**

---

## License

This project is for educational and personal research purposes. See individual API provider terms of service for data usage restrictions.
