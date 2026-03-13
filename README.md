<p align="center">
  <h1 align="center">🛰️ S H A D O W L E N S</h1>
  <p align="center"><strong>Global Threat Intercept — Real-Time Geospatial Intelligence Platform</strong></p>
  <p align="center">

  </p>
</p>

---
![ShadowLens](https://github.com/user-attachments/assets/000b94eb-bf33-4e8b-8c60-15ca4a723c68)
**ShadowLens** is a real-time, full-spectrum geospatial intelligence dashboard that aggregates live data from dozens of open-source intelligence (OSINT) feeds and renders them on a unified dark-ops map interface. It tracks aircraft, ships, satellites, earthquakes, conflict zones, CCTV networks, GPS jamming, and breaking geopolitical events — all updating in real time.

Built with **Next.js**, **MapLibre GL**, **FastAPI**, and **Python**, it's designed for analysts, researchers, and enthusiasts who want a single-pane-of-glass view of global activity.

### 🤖 F.R.I.D.A.Y. — AI Analysis Engine

ShadowLens includes **F.R.I.D.A.Y.**, a local LLM-powered analysis engine that can analyze any entity on the map. Select a flight, ship, military base, network host, or any other entity and F.R.I.D.A.Y. provides:

* **Instant fact extraction** — Deterministic parsing of entity data (no AI, instant)
* **Deep LLM analysis** — Full RAG pipeline with Qwen 2.5 14B for vulnerability assessment, risk analysis, and recommendations
* **Anti-hallucination validation** — 3-stage pipeline ensures answers are grounded in actual data
* **Nmap / BloodHound / Volatility** — Specialized modules for security scan analysis

### 🔍 OSINT Agent — 20+ Security Tools

The integrated OSINT agent provides one-click access to:

`nmap` · `nuclei` · `whatweb` · `theHarvester` · `spiderfoot` · `sherlock` · `h8mail` · `whois` · `dmitry` · `subfinder` · `dnsrecon` · `shodan` · `phoneinfoga` · `maigret` · `holehe` · `autorecon` · `kismet` · `snort`

---

## Interesting Use Cases

* Track private jets of billionaires
* Monitor satellites passing overhead
* Watch naval traffic worldwide
* Detect GPS jamming zones
* Follow earthquakes and disasters in real time
* Run nmap scans on discovered hosts and analyze results with F.R.I.D.A.Y.
* Deep OSINT searches on any target — auto-detects IPs, domains, emails, usernames

---

## ⚡ Quick Start

```bash
git clone https://github.com/S-O-U-L-S-E-E-K-E-R/ShadowLens.git
cd ShadowLens
./start.sh
```

This starts everything — Docker containers, OSINT agent, and F.R.I.D.A.Y. engine.

Open `http://localhost:3000` to view the dashboard.

### Requirements

* **Docker** and **docker compose**
* **Python 3.10+** with venv (for OSINT agent)
* **NVIDIA GPU** (optional, for fast F.R.I.D.A.Y. inference — falls back to CPU)

### After a Reboot

```bash
cd /path/to/ShadowLens
./start.sh
```

That's it — one script handles everything.

---

## ✨ Features

### 🛩️ Aviation Tracking

* **Commercial Flights** — Real-time positions via OpenSky Network (~5,000+ aircraft)
* **Private Aircraft** — Light GA, turboprops, bizjets tracked separately
* **Private Jets** — High-net-worth individual aircraft with owner identification
* **Military Flights** — Tankers, ISR, fighters, transports via adsb.lol military endpoint
* **Flight Trail Accumulation** — Persistent breadcrumb trails for all tracked aircraft
* **Holding Pattern Detection** — Automatically flags aircraft circling (>300° total turn)
* **Aircraft Classification** — Shape-accurate SVG icons: airliners, turboprops, bizjets, helicopters
* **Grounded Detection** — Aircraft below 100ft AGL rendered with grey icons

### 🚢 Maritime Tracking

* **AIS Vessel Stream** — 25,000+ vessels via aisstream.io WebSocket (real-time)
* **Ship Classification** — Cargo, tanker, passenger, yacht, military vessel types with color-coded icons
* **Carrier Strike Group Tracker** — All 11 active US Navy aircraft carriers with OSINT-estimated positions
  * Automated GDELT news scraping for carrier movement intelligence
  * 50+ geographic region-to-coordinate mappings
  * Disk-cached positions, auto-updates at 00:00 & 12:00 UTC
* **Cruise & Passenger Ships** — Dedicated layer for cruise liners and ferries
* **Clustered Display** — Ships cluster at low zoom with count labels, decluster on zoom-in

### 🛰️ Space & Satellites

* **Orbital Tracking** — Real-time satellite positions via CelesTrak TLE data + SGP4 propagation (2,000+ active satellites, no API key required)
* **Mission-Type Classification** — Color-coded by mission: military recon (red), SAR (cyan), SIGINT (white), navigation (blue), early warning (magenta), commercial imaging (green), space station (gold)

### 🌍 Geopolitics & Conflict

* **Global Incidents** — GDELT-powered conflict event aggregation (last 8 hours, ~1,000 events)
* **Ukraine Frontline** — Live warfront GeoJSON from DeepState Map
* **SIGINT/RISINT News Feed** — Real-time RSS aggregation from multiple intelligence-focused sources
* **Region Dossier** — Right-click anywhere on the map for:
  * Country profile (population, capital, languages, currencies, area)
  * Head of state & government type (Wikidata SPARQL)
  * Local Wikipedia summary with thumbnail

### 📷 Surveillance

* **CCTV Mesh** — 2,000+ live traffic cameras from:
  * 🇬🇧 Transport for London JamCams
  * 🇺🇸 Austin, TX TxDOT
  * 🇺🇸 NYC DOT
  * 🇸🇬 Singapore LTA
  * Custom URL ingestion
* **Feed Rendering** — Automatic detection & rendering of video, MJPEG, HLS, embed, satellite tile, and image feeds
* **Clustered Map Display** — Green dots cluster with count labels, decluster on zoom

### 📡 Signal Intelligence

* **GPS Jamming Detection** — Real-time analysis of aircraft NAC-P (Navigation Accuracy Category) values
  * Grid-based aggregation identifies interference zones
  * Red overlay squares with "GPS JAM XX%" severity labels
* **Radio Intercept Panel** — Scanner-style UI for monitoring communications

### 🌐 Additional Layers

* **Earthquakes (24h)** — USGS real-time earthquake feed with magnitude-scaled markers
* **Day/Night Cycle** — Solar terminator overlay showing global daylight/darkness
* **Global Markets Ticker** — Live financial market indices (minimizable)
* **Measurement Tool** — Point-to-point distance & bearing measurement on the map

---

## 🏗️ Architecture

```
┌────────────────────────────────────────────────────────┐
│                   FRONTEND (Next.js)                   │
│                                                        │
│  ┌─────────────┐  ┌──────────┐  ┌──────────────────┐  │
│  │ MapLibre GL │  │ NewsFeed │  │  F.R.I.D.A.Y.    │  │
│  │  2D WebGL   │  │  SIGINT  │  │  AI Analysis     │  │
│  │ Map Render  │  │  Intel   │  │  Panel           │  │
│  └──────┬──────┘  └────┬─────┘  └────────┬─────────┘  │
│         └───────────────┼────────────────┘             │
│                         │ REST API                     │
├─────────────────────────┼──────────────────────────────┤
│               BACKEND (FastAPI · Docker)               │
│                         │                              │
│  ┌──────────────────────┼───────────────────────────┐  │
│  │          Data Fetcher (Scheduler)                │  │
│  │  ┌──────────┬──────────┬──────────┬───────────┐  │  │
│  │  │ OpenSky  │ adsb.lol │CelesTrak │   USGS    │  │  │
│  │  │ Flights  │ Military │   Sats   │  Quakes   │  │  │
│  │  ├──────────┼──────────┼──────────┼───────────┤  │  │
│  │  │  AIS WS  │ Carrier  │  GDELT   │   CCTV    │  │  │
│  │  │  Ships   │ Tracker  │ Conflict │  Cameras  │  │  │
│  │  ├──────────┼──────────┼──────────┼───────────┤  │  │
│  │  │ DeepState│   RSS    │  Region  │    GPS    │  │  │
│  │  │ Frontline│  Intel   │ Dossier  │  Jamming  │  │  │
│  │  └──────────┴──────────┴──────────┴───────────┘  │  │
│  └──────────────────────────────────────────────────┘  │
│                         │ Proxy                        │
├─────────────────────────┼──────────────────────────────┤
│            OSINT AGENT (Host · Port 8002)              │
│                         │                              │
│  ┌──────────────────────┼───────────────────────────┐  │
│  │  ┌────────┐  ┌───────┴──────┐  ┌─────────────┐  │  │
│  │  │  Nmap  │  │ F.R.I.D.A.Y. │  │  Nuclei     │  │  │
│  │  │ Scans  │  │  LLM Engine  │  │  Vuln Scan  │  │  │
│  │  ├────────┤  │  Qwen 14B    │  ├─────────────┤  │  │
│  │  │WhatWeb │  │  FAISS RAG   │  │ SpiderFoot  │  │  │
│  │  ├────────┤  │  3-Stage     │  ├─────────────┤  │  │
│  │  │Harvest │  │  Pipeline    │  │  AutoRecon  │  │  │
│  │  ├────────┤  └──────────────┘  ├─────────────┤  │  │
│  │  │Sherlock│  ┌──────────────┐  │   Kismet    │  │  │
│  │  ├────────┤  │   Deep OSINT │  ├─────────────┤  │  │
│  │  │Maigret │  │   Search     │  │   Snort     │  │  │
│  │  └────────┘  └──────────────┘  └─────────────┘  │  │
│  └──────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────┘
```

---

## 📊 Data Sources & APIs

| Source | Data | Update Frequency | API Key Required |
|---|---|---|---|
| [OpenSky Network](https://opensky-network.org) | Commercial & private flights | ~60s | Optional (anonymous limited) |
| [adsb.lol](https://adsb.lol) | Military aircraft | ~60s | No |
| [aisstream.io](https://aisstream.io) | AIS vessel positions | Real-time WebSocket | **Yes** |
| [CelesTrak](https://celestrak.org) | Satellite orbital positions (TLE + SGP4) | ~60s | No |
| [USGS Earthquake](https://earthquake.usgs.gov) | Global seismic events | ~60s | No |
| [GDELT Project](https://www.gdeltproject.org) | Global conflict events | ~6h | No |
| [DeepState Map](https://deepstatemap.live) | Ukraine frontline | ~30min | No |
| [Transport for London](https://api.tfl.gov.uk) | London CCTV JamCams | ~5min | No |
| [TxDOT](https://its.txdot.gov) | Austin TX traffic cameras | ~5min | No |
| [NYC DOT](https://webcams.nyctmc.org) | NYC traffic cameras | ~5min | No |
| [Singapore LTA](https://datamall.lta.gov.sg) | Singapore traffic cameras | ~5min | **Yes** |
| [RestCountries](https://restcountries.com) | Country profile data | On-demand (cached 24h) | No |
| [Wikidata SPARQL](https://query.wikidata.org) | Head of state data | On-demand (cached 24h) | No |
| [Wikipedia API](https://en.wikipedia.org/api) | Location summaries & aircraft images | On-demand (cached) | No |
| [CARTO Basemaps](https://carto.com) | Dark map tiles | Continuous | No |

---

## 🚀 Getting Started

### 🐳 Docker Setup (Recommended for Self-Hosting)

You can run the dashboard easily using the pre-built Docker images hosted on GitHub Container Registry (GHCR).

1. Create a `docker-compose.yml` file:

```yaml
version: '3.8'

services:
  backend:
    image: ghcr.io/<your-username>/live-risk-dashboard-backend:main
    container_name: shadowlens-backend
    ports:
      - "8000:8000"
    environment:
      - AIS_API_KEY=${AIS_API_KEY}
      - OPENSKY_CLIENT_ID=${OPENSKY_CLIENT_ID}
      - OPENSKY_CLIENT_SECRET=${OPENSKY_CLIENT_SECRET}
    volumes:
      - backend_data:/app/data
    restart: unless-stopped

  frontend:
    image: ghcr.io/<your-username>/live-risk-dashboard-frontend:main
    container_name: shadowlens-frontend
    ports:
      - "3000:3000"
    environment:
      - NEXT_PUBLIC_API_URL=http://localhost:8000
    depends_on:
      - backend
    restart: unless-stopped

volumes:
  backend_data:
```

1. Create a `.env` file in the same directory with your API keys.
2. Run `docker-compose up -d`.
3. Access the dashboard at `http://localhost:3000`.

---

### 📦 Quick Start (No Code Required)

If you just want to run the dashboard without dealing with terminal commands:

1. Go to the **[Releases](../../releases)** tab on the right side of this GitHub page.
2. Download the `ShadowLens_v0.3.zip` file.
3. Extract the folder to your computer.
4. **Windows:** Double-click `start.bat`.
   **Mac/Linux:** Open terminal, type `chmod +x start.sh`, and run `./start.sh`.
5. It will automatically install everything and launch the dashboard!

---

### 💻 Developer Setup

If you want to modify the code or run from source:

#### Prerequisites

* **Node.js** 18+ and **npm**
* **Python** 3.10+ with `pip`
* API keys for: `aisstream.io` (required), and optionally `opensky-network.org` (OAuth2), `lta.gov.sg`

### Installation

```bash
# Clone the repository
git clone https://github.com/S-O-U-L-S-E-E-K-E-R/ShadowLens.git
cd ShadowLens

# Backend setup
cd backend
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux
pip install -r requirements.txt

# Create .env with your API keys
echo "AIS_API_KEY=your_aisstream_key" >> .env
echo "OPENSKY_CLIENT_ID=your_opensky_client_id" >> .env
echo "OPENSKY_CLIENT_SECRET=your_opensky_secret" >> .env

# Frontend setup
cd ../frontend
npm install
```

### Running

```bash
# From the frontend directory — starts both frontend & backend concurrently
npm run dev
```

This starts:

* **Next.js** frontend on `http://localhost:3000`
* **FastAPI** backend on `http://localhost:8000`

---

## 🎛️ Data Layers

All layers are independently toggleable from the left panel:

| Layer | Default | Description |
|---|---|---|
| Commercial Flights | ✅ ON | Airlines, cargo, GA aircraft |
| Private Flights | ✅ ON | Non-commercial private aircraft |
| Private Jets | ✅ ON | High-value bizjets with owner data |
| Military Flights | ✅ ON | Military & government aircraft |
| Tracked Aircraft | ✅ ON | Special interest watch list |
| Satellites | ✅ ON | Orbital assets by mission type |
| Carriers / Mil / Cargo | ✅ ON | Navy carriers, cargo ships, tankers |
| Civilian Vessels | ❌ OFF | Yachts, fishing, recreational |
| Cruise / Passenger | ✅ ON | Cruise ships and ferries |
| Earthquakes (24h) | ✅ ON | USGS seismic events |
| CCTV Mesh | ❌ OFF | Surveillance camera network |
| Ukraine Frontline | ✅ ON | Live warfront positions |
| Global Incidents | ✅ ON | GDELT conflict events |
| GPS Jamming | ✅ ON | NAC-P degradation zones |
| Day / Night Cycle | ✅ ON | Solar terminator overlay |

---

## 🔧 Performance

The platform is optimized for handling massive real-time datasets:

* **Gzip Compression** — API payloads compressed ~92% (11.6 MB → 915 KB)
* **ETag Caching** — `304 Not Modified` responses skip redundant JSON parsing
* **Viewport Culling** — Only features within the visible map bounds (+20% buffer) are rendered
* **Clustered Rendering** — Ships, CCTV, and earthquakes use MapLibre clustering to reduce feature count
* **Debounced Viewport Updates** — 300ms debounce prevents GeoJSON rebuild thrash during pan/zoom
* **Position Interpolation** — Smooth 10s tick animation between data refreshes
* **React.memo** — Heavy components wrapped to prevent unnecessary re-renders
* **Coordinate Precision** — Lat/lng rounded to 5 decimals (~1m) to reduce JSON size

---

## 📁 Project Structure

```
ShadowLens/
├── start.sh                        # One-command startup (Docker + OSINT Agent)
├── docker-compose.yml              # Frontend + Backend containers
│
├── backend/                        # FastAPI backend (Docker container, port 8001)
│   ├── main.py                     # API routes, middleware, OSINT/FRIDAY proxy
│   ├── services/
│   │   ├── data_fetcher.py         # Core scheduler — fetches all data sources
│   │   ├── osint_bridge.py         # Proxy to OSINT agent (port 8002)
│   │   ├── ais_stream.py           # AIS WebSocket client (25K+ vessels)
│   │   ├── carrier_tracker.py      # OSINT carrier position tracker
│   │   ├── cctv_pipeline.py        # Multi-source CCTV camera ingestion
│   │   ├── geopolitics.py          # GDELT + Ukraine frontline fetcher
│   │   ├── region_dossier.py       # Right-click country/city intelligence
│   │   ├── network_utils.py        # HTTP client with curl fallback
│   │   └── regional_feed.py        # Regional news/threat feeds
│
├── frontend/                       # Next.js frontend (Docker container, port 3000)
│   └── src/
│       ├── app/page.tsx            # Main dashboard — state, polling, layout
│       └── components/
│           ├── MaplibreViewer.tsx   # Core map — all GeoJSON layers
│           ├── NewsFeed.tsx         # SIGINT feed + entity panels + F.R.I.D.A.Y.
│           ├── WorldviewLeftPanel.tsx   # Data layer toggles
│           ├── WorldviewRightPanel.tsx  # Search + filter sidebar
│           └── ...                 # Markets, Radio, Legend, Settings, etc.
│
├── osint-agent/                    # Host-side OSINT engine (port 8002)
│   ├── main.py                     # FastAPI — scan endpoints, F.R.I.D.A.Y. API
│   ├── config.py                   # Tool detection, host location
│   ├── runners/                    # Tool wrappers (nmap, nuclei, spiderfoot, etc.)
│   └── syd/                        # F.R.I.D.A.Y. engine package
│       ├── engine.py               # Core 3-stage RAG pipeline (FridayEngine)
│       ├── nmap_fact_extractor.py  # Nmap scan parser
│       ├── bloodhound_fact_extractor.py  # AD attack path parser
│       ├── volatility_fact_extractor.py  # Memory forensics parser
│       ├── models/                 # LLM model (Qwen 2.5 14B GGUF)
│       └── rag_data/               # FAISS indexes + knowledge chunks
```

---

## 🔑 Environment Variables

Create a `.env` file in the `backend/` directory:

```env
# Required
AIS_API_KEY=your_aisstream_key                # Maritime vessel tracking (aisstream.io)

# Optional (enhances data quality)
OPENSKY_CLIENT_ID=your_opensky_client_id      # OAuth2 — higher rate limits for flight data
OPENSKY_CLIENT_SECRET=your_opensky_secret     # OAuth2 — paired with Client ID above
LTA_ACCOUNT_KEY=your_lta_key                  # Singapore CCTV cameras
```

---

## ⚠️ Disclaimer

This is an **educational and research tool** built entirely on publicly available, open-source intelligence (OSINT) data. No classified, restricted, or non-public data sources are used. Carrier positions are estimates based on public reporting. The military-themed UI is purely aesthetic.

**Do not use this tool for any operational, military, or intelligence purpose.**

---

## 📜 License

This project is for educational and personal research purposes. See individual API provider terms of service for data usage restrictions.

---

<p align="center">
  <sub>Built with ☕ and too many API calls</sub>
</p>
