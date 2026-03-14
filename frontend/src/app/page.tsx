"use client";

import { API_BASE } from "@/lib/api";
import { useEffect, useState, useRef, useCallback, useMemo } from "react";
import dynamic from 'next/dynamic';
import { motion } from "framer-motion";
import WorldviewLeftPanel from "@/components/WorldviewLeftPanel";
import WorldviewRightPanel from "@/components/WorldviewRightPanel";
import NewsFeed, { FridayPanel } from "@/components/NewsFeed";
import MarketsPanel from "@/components/MarketsPanel";
import FilterPanel from "@/components/FilterPanel";
// FindLocateBar removed — F.R.I.D.A.Y. handles all search/OSINT
import RadioInterceptPanel from "@/components/RadioInterceptPanel";
import SettingsPanel from "@/components/SettingsPanel";
import MapLegend from "@/components/MapLegend";
import ScaleBar from "@/components/ScaleBar";
import ErrorBoundary from "@/components/ErrorBoundary";
import OnboardingModal, { useOnboarding } from "@/components/OnboardingModal";

// Use dynamic loads for Maplibre to avoid SSR window is not defined errors
const MaplibreViewer = dynamic(() => import('@/components/MaplibreViewer'), { ssr: false });

export default function Dashboard() {
  const dataRef = useRef<any>({});
  const [dataVersion, setDataVersion] = useState(0);
  // Stable reference for child components — only changes when dataVersion increments
  const data = dataRef.current;
  const [uiVisible, setUiVisible] = useState(true);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [legendOpen, setLegendOpen] = useState(false);
  const [mapView, setMapView] = useState({ zoom: 2, latitude: 20 });
  const [measureMode, setMeasureMode] = useState(false);
  const [measurePoints, setMeasurePoints] = useState<{ lat: number; lng: number }[]>([]);

  const [activeLayers, setActiveLayers] = useState({
    flights: false,
    private: false,
    jets: false,
    military: false,
    tracked: false,
    satellites: false,
    ships_important: false,
    ships_civilian: false,
    ships_passenger: false,
    earthquakes: false,
    cctv: false,
    cctvFilters: {
      "TDOT SmartWay": true,
      "Clarksville/Ft Campbell": true,
      "NewsChannel 5": true,
      "WSMV": true,
      "Caltrans": true,
      "FL511": true,
      "NYC DOT": true,
      "Austin TxDOT": true,
      "TfL London": true,
      "Singapore LTA": true,
      "NPS / Parks": true,
      "LA DOTD 511": true,
      "LA Weather Cams": true,
      "Community / Tourist": true,
    } as Record<string, boolean>,
    ukraine_frontline: false,
    global_incidents: false,
    day_night: false,
    gps_jamming: false,
    tfrs: false,
    weather_alerts: false,
    natural_events: false,
    firms_hotspots: false,
    power_outages: false,
    internet_outages: false,
    air_quality: false,
    space_weather: false,
    radioactivity: false,
    military_bases: false,
    nuclear_facilities: false,
    submarine_cables: false,
    embassies: false,
    volcanoes: false,
    piracy: false,
    border_crossings: false,
    cyber_threats: false,
    reservoirs: false,
    cell_towers: false,
    global_events: false,
    social_media: false,
    noaa_nwr: false,
    kiwisdr_nodes: false,
    // OSINT / Local tools
    kismet_devices: false,
    snort_alerts: false,
    nmap_hosts: false,
    nuclei_vulns: false,
  });

  const [effects, setEffects] = useState({
    bloom: true,
  });

  const [activeStyle, setActiveStyle] = useState('DEFAULT');
  const stylesList = ['DEFAULT', 'FLIR', 'NVG', 'CRT'];

  const cycleStyle = () => {
    setActiveStyle((prev) => {
      const idx = stylesList.indexOf(prev);
      return stylesList[(idx + 1) % stylesList.length];
    });
  };

  const [selectedEntity, setSelectedEntity] = useState<{ type: string, id: string | number, extra?: any } | null>(null);
  const [activeFilters, setActiveFilters] = useState<Record<string, string[]>>({});
  const [flyToLocation, setFlyToLocation] = useState<{ lat: number, lng: number, ts: number } | null>(null);

  // Pinned locations from F.R.I.D.A.Y. OSINT/locate results — rendered as markers on map
  const [pinnedLocations, setPinnedLocations] = useState<{ lat: number; lng: number; label: string; source?: string; id: string }[]>([]);

  // Regional Focus Mode — right-click to lock onto a region
  const [regionalFocus, setRegionalFocus] = useState<{
    active: boolean;
    lat: number;
    lng: number;
    radiusDeg: number; // bounding box half-size in degrees (~500km default)
    name: string;
    countryCode: string;
  } | null>(null);

  // Eavesdrop Mode State
  const [isEavesdropping, setIsEavesdropping] = useState(false);
  const [eavesdropLocation, setEavesdropLocation] = useState<{ lat: number, lng: number } | null>(null);
  const [cameraCenter, setCameraCenter] = useState<{ lat: number, lng: number } | null>(null);

  // Mouse coordinate + reverse geocoding state
  const [mouseCoords, setMouseCoords] = useState<{ lat: number, lng: number } | null>(null);
  const [locationLabel, setLocationLabel] = useState('');

  // Onboarding & connection status
  const { showOnboarding, setShowOnboarding } = useOnboarding();
  const [backendStatus, setBackendStatus] = useState<'connecting' | 'connected' | 'disconnected'>('connecting');
  const geocodeCache = useRef<Map<string, string>>(new Map());
  const geocodeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const lastGeocodedPos = useRef<{ lat: number; lng: number } | null>(null);
  const geocodeAbort = useRef<AbortController | null>(null);

  const handleMouseCoords = useCallback((coords: { lat: number, lng: number }) => {
    setMouseCoords(coords);

    // Throttle reverse geocoding to every 1500ms + distance check
    if (geocodeTimer.current) clearTimeout(geocodeTimer.current);
    geocodeTimer.current = setTimeout(async () => {
      // Skip if cursor hasn't moved far enough (0.05 degrees ~= 5km)
      if (lastGeocodedPos.current) {
        const dLat = Math.abs(coords.lat - lastGeocodedPos.current.lat);
        const dLng = Math.abs(coords.lng - lastGeocodedPos.current.lng);
        if (dLat < 0.05 && dLng < 0.05) return;
      }

      const gridKey = `${(coords.lat).toFixed(2)},${(coords.lng).toFixed(2)}`;
      const cached = geocodeCache.current.get(gridKey);
      if (cached) {
        setLocationLabel(cached);
        lastGeocodedPos.current = coords;
        return;
      }

      // Cancel any in-flight geocode request
      if (geocodeAbort.current) geocodeAbort.current.abort();
      geocodeAbort.current = new AbortController();

      try {
        const res = await fetch(
          `https://nominatim.openstreetmap.org/reverse?lat=${coords.lat}&lon=${coords.lng}&format=json&zoom=10&addressdetails=1`,
          { headers: { 'Accept-Language': 'en' }, signal: geocodeAbort.current.signal }
        );
        if (res.ok) {
          const data = await res.json();
          const addr = data.address || {};
          const city = addr.city || addr.town || addr.village || addr.county || '';
          const state = addr.state || addr.region || '';
          const country = addr.country || '';
          const parts = [city, state, country].filter(Boolean);
          const label = parts.join(', ') || data.display_name?.split(',').slice(0, 3).join(',') || 'Unknown';

          // LRU-style cache pruning: keep max 500 entries (Map preserves insertion order)
          if (geocodeCache.current.size > 500) {
            const iter = geocodeCache.current.keys();
            for (let i = 0; i < 100; i++) {
              const key = iter.next().value;
              if (key !== undefined) geocodeCache.current.delete(key);
            }
          }
          geocodeCache.current.set(gridKey, label);
          setLocationLabel(label);
          lastGeocodedPos.current = coords;
        }
      } catch (e: any) {
        if (e.name !== 'AbortError') { /* Silently fail - keep last label */ }
      }
    }, 1500);
  }, []);

  // Region dossier state (right-click intelligence)
  const [regionDossier, setRegionDossier] = useState<any>(null);
  const [regionDossierLoading, setRegionDossierLoading] = useState(false);

  const handleMapRightClick = useCallback(async (coords: { lat: number, lng: number }) => {
    setSelectedEntity({ type: 'region_dossier', id: `${coords.lat.toFixed(4)}_${coords.lng.toFixed(4)}`, extra: coords });
    setRegionDossierLoading(true);
    setRegionDossier(null);
    try {
      const res = await fetch(`${API_BASE}/api/region-dossier?lat=${coords.lat}&lng=${coords.lng}`);
      if (res.ok) {
        const data = await res.json();
        setRegionDossier(data);
      }
    } catch (e) {
      console.error("Failed to fetch region dossier", e);
    } finally {
      setRegionDossierLoading(false);
    }
  }, []);

  // Middle-click → activate regional focus mode
  const handleMapMiddleClick = useCallback(async (coords: { lat: number, lng: number }) => {
    setRegionalFocus({
      active: true,
      lat: coords.lat,
      lng: coords.lng,
      radiusDeg: 5,
      name: 'Loading...',
      countryCode: '',
    });
    setFlyToLocation({ lat: coords.lat, lng: coords.lng, ts: Date.now() });
    // Clear any selected entity so NewsFeed shows the news + social panels
    setSelectedEntity(null);
    setRegionDossier(null);

    // Reverse geocode to get locality / state / country
    try {
      const geoRes = await fetch(
        `https://nominatim.openstreetmap.org/reverse?lat=${coords.lat}&lon=${coords.lng}&format=json&zoom=10&addressdetails=1`,
        { headers: { 'User-Agent': 'ShadowLens/1.0' } }
      );
      if (geoRes.ok) {
        const geoData = await geoRes.json();
        const addr = geoData.address || {};
        // Priority: state/province → country
        const regionName = addr.state || addr.province || addr.region || addr.country || geoData.display_name?.split(',')[0] || 'Unknown Region';
        const locality = addr.city || addr.town || addr.county || '';
        const cc = addr.country_code?.toUpperCase() || '';
        const displayName = locality ? `${locality}, ${regionName}` : regionName;
        setRegionalFocus(prev => prev ? { ...prev, name: displayName, countryCode: cc } : prev);
      }
    } catch { /* keep "Loading..." */ }
  }, []);

  // Clear dossier when selecting a different entity type
  useEffect(() => {
    if (selectedEntity?.type !== 'region_dossier') {
      setRegionDossier(null);
      setRegionDossierLoading(false);
    }
  }, [selectedEntity]);

  // Exit regional focus on Escape key
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && regionalFocus?.active) {
        setRegionalFocus(null);
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [regionalFocus]);

  // ETag tracking for conditional requests
  const fastEtag = useRef<string | null>(null);
  const slowEtag = useRef<string | null>(null);
  const osintEtag = useRef<string | null>(null);

  useEffect(() => {
    const fetchFastData = async () => {
      try {
        const headers: Record<string, string> = {};
        if (fastEtag.current) headers['If-None-Match'] = fastEtag.current;
        const res = await fetch(`${API_BASE}/api/live-data/fast`, { headers });
        if (res.status === 304) { setBackendStatus('connected'); return; }
        if (res.ok) {
          setBackendStatus('connected');
          fastEtag.current = res.headers.get('etag') || null;
          const json = await res.json();
          dataRef.current = { ...dataRef.current, ...json };
          setDataVersion(v => v + 1);
        }
      } catch (e) {
        console.error("Failed fetching fast live data", e);
        setBackendStatus('disconnected');
      }
    };

    const fetchSlowData = async () => {
      try {
        const headers: Record<string, string> = {};
        if (slowEtag.current) headers['If-None-Match'] = slowEtag.current;
        const res = await fetch(`${API_BASE}/api/live-data/slow`, { headers });
        if (res.status === 304) { setBackendStatus('connected'); return; }
        if (res.ok) {
          setBackendStatus('connected');
          slowEtag.current = res.headers.get('etag') || null;
          const json = await res.json();
          dataRef.current = { ...dataRef.current, ...json };
          setDataVersion(v => v + 1);
        }
      } catch (e) {
        console.error("Failed fetching slow live data", e);
      }
    };

    // Static datasets — fetched once (military bases, nuclear, cables, embassies)
    const fetchStaticData = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/live-data/static`);
        if (res.ok) {
          const json = await res.json();
          dataRef.current = { ...dataRef.current, ...json };
          setDataVersion(v => v + 1);
        }
      } catch (e) {
        console.error("Failed fetching static data", e);
      }
    };

    // OSINT data — host-side tools (Kismet, Snort, Nmap, Nuclei)
    const fetchOsintData = async () => {
      try {
        const headers: Record<string, string> = {};
        if (osintEtag.current) headers['If-None-Match'] = osintEtag.current;
        const res = await fetch(`${API_BASE}/api/live-data/osint`, { headers });
        if (res.status === 304) return;
        if (res.ok) {
          osintEtag.current = res.headers.get('etag') || null;
          const json = await res.json();
          dataRef.current = { ...dataRef.current, ...json };
          setDataVersion(v => v + 1);
        }
      } catch (e) {
        // OSINT agent may not be running — silently ignore
      }
    };

    fetchFastData();
    fetchSlowData();
    fetchStaticData();
    fetchOsintData();

    // Fast polling: 60s (matches backend update cadence — was 15s, wasting 75% on 304s)
    // Slow polling: 120s (backend updates every 30min)
    // OSINT polling: 30s (Kismet updates frequently)
    const fastInterval = setInterval(fetchFastData, 60000);
    const slowInterval = setInterval(fetchSlowData, 120000);
    const osintInterval = setInterval(fetchOsintData, 30000);

    return () => {
      clearInterval(fastInterval);
      clearInterval(slowInterval);
      clearInterval(osintInterval);
    };
  }, []);

  // Regional data — streamed progressively from backend SSE endpoint
  const [regionalData, setRegionalData] = useState<any>(null);
  const regionalEventSourceRef = useRef<EventSource | null>(null);

  useEffect(() => {
    if (!regionalFocus?.active) {
      setRegionalData(null);
      if (regionalEventSourceRef.current) {
        regionalEventSourceRef.current.close();
        regionalEventSourceRef.current = null;
      }
      return;
    }

    // Don't start stream until we have a real region name (not "Loading...")
    if (!regionalFocus.name || regionalFocus.name === 'Loading...') return;

    const startStream = () => {
      // Close previous stream
      if (regionalEventSourceRef.current) {
        regionalEventSourceRef.current.close();
      }

      const cc = regionalFocus.countryCode || '';
      const rn = encodeURIComponent(regionalFocus.name || '');
      const url = `${API_BASE}/api/live-data/regional/stream?lat=${regionalFocus.lat}&lng=${regionalFocus.lng}&radius=${regionalFocus.radiusDeg}&country=${cc}&region=${rn}`;

      const es = new EventSource(url);
      regionalEventSourceRef.current = es;

      // init event: geo-filtered map data (immediate)
      es.addEventListener('init', (e: MessageEvent) => {
        try {
          const base = JSON.parse(e.data);
          setRegionalData(base);
        } catch {}
      });

      // chunk event: news or social results from one source
      es.addEventListener('chunk', (e: MessageEvent) => {
        try {
          const chunk = JSON.parse(e.data);
          const { category, items } = chunk;
          if (!items?.length) return;

          setRegionalData((prev: any) => {
            if (!prev) return prev;
            const updated = { ...prev };
            if (category === 'news') {
              updated.news = [...(prev.news || []), ...items];
            } else if (category === 'social') {
              updated.social_media = [...(prev.social_media || []), ...items];
            }
            // Update counts in metadata
            if (updated._regional) {
              updated._regional = {
                ...updated._regional,
                news_count: updated.news?.length || 0,
                social_count: updated.social_media?.length || 0,
              };
            }
            return updated;
          });
        } catch {}
      });

      // done event: stream complete
      es.addEventListener('done', () => {
        es.close();
      });

      es.onerror = () => {
        es.close();
      };
    };

    startStream();

    // Re-stream every 90s while focused
    const interval = setInterval(startStream, 90000);
    return () => {
      clearInterval(interval);
      if (regionalEventSourceRef.current) {
        regionalEventSourceRef.current.close();
        regionalEventSourceRef.current = null;
      }
    };
  }, [regionalFocus?.active, regionalFocus?.lat, regionalFocus?.lng, regionalFocus?.name]); // eslint-disable-line react-hooks/exhaustive-deps

  // Use regional data when available, otherwise fall back to global data
  const filteredData = useMemo(() => {
    if (!regionalFocus?.active) return data;
    // If regional data hasn't loaded yet, do client-side filtering as fallback
    if (regionalData) return regionalData;

    const { lat, lng, radiusDeg } = regionalFocus;
    const latMin = lat - radiusDeg;
    const latMax = lat + radiusDeg;
    const lngMin = lng - radiusDeg;
    const lngMax = lng + radiusDeg;

    const inBounds = (itemLat: number, itemLng: number) =>
      itemLat >= latMin && itemLat <= latMax && itemLng >= lngMin && itemLng <= lngMax;

    const filtered: any = {};
    for (const [key, value] of Object.entries(data)) {
      if (Array.isArray(value) && value.length > 0) {
        const sample = value[0];
        if (sample && typeof sample === 'object') {
          const hasLat = 'lat' in sample || 'latitude' in sample;
          const hasLng = 'lon' in sample || 'lng' in sample || 'longitude' in sample;
          if (hasLat && hasLng) {
            filtered[key] = value.filter((item: any) => {
              const iLat = item.lat ?? item.latitude;
              const iLng = item.lon ?? item.lng ?? item.longitude;
              if (iLat == null || iLng == null) return false;
              return inBounds(iLat, iLng);
            });
            continue;
          }
        }
      }
      filtered[key] = value;
    }
    return filtered;
  }, [data, dataVersion, regionalFocus, regionalData]);  // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <main className="fixed inset-0 w-full h-full bg-black overflow-hidden font-sans">

      {/* MAPLIBRE WEBGL OVERLAY */}
      <ErrorBoundary name="Map">
        <MaplibreViewer
          data={filteredData}
          activeLayers={activeLayers}
          activeFilters={activeFilters}
          effects={{ ...effects, bloom: effects.bloom && activeStyle !== 'DEFAULT', style: activeStyle }}
          onEntityClick={setSelectedEntity}
          selectedEntity={selectedEntity}
          flyToLocation={flyToLocation}
          isEavesdropping={isEavesdropping}
          onEavesdropClick={setEavesdropLocation}
          onCameraMove={setCameraCenter}
          onMouseCoords={handleMouseCoords}
          onRightClick={handleMapRightClick}
          onMiddleClick={handleMapMiddleClick}
          regionDossier={regionDossier}
          regionDossierLoading={regionDossierLoading}
          onViewStateChange={setMapView}
          measureMode={measureMode}
          onMeasureClick={(pt: { lat: number; lng: number }) => {
            setMeasurePoints(prev => prev.length >= 3 ? prev : [...prev, pt]);
          }}
          measurePoints={measurePoints}
          regionalFocus={regionalFocus}
          pinnedLocations={pinnedLocations}
          onClearPins={() => setPinnedLocations([])}
          onRemovePin={(id: string) => setPinnedLocations(prev => prev.filter(p => p.id !== id))}
        />
      </ErrorBoundary>


      {uiVisible && (
        <>
          {/* WORLDVIEW HEADER */}
          <motion.div
            initial={{ opacity: 0, y: -20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 1 }}
            className="absolute top-6 left-6 z-[200] pointer-events-none flex items-center gap-4"
          >
            <div className="w-8 h-8 flex items-center justify-center">
              {/* Target Reticle Icon */}
              <div className="w-6 h-6 rounded-full border border-cyan-500 relative flex items-center justify-center">
                <div className="w-4 h-4 rounded-full bg-cyan-500/30"></div>
                <div className="absolute top-[-2px] bottom-[-2px] w-[1px] bg-cyan-500"></div>
                <div className="absolute left-[-2px] right-[-2px] h-[1px] bg-cyan-500"></div>
              </div>
            </div>
            <div className="flex flex-col">
              <h1 className="text-2xl font-bold tracking-[0.4em] text-white flex items-center gap-3" style={{ fontFamily: 'monospace' }}>
                S H A D O W <span className="text-cyan-400">L E N S</span>
              </h1>
              <span className={`text-[9px] font-mono tracking-[0.3em] mt-1 ml-1 ${regionalFocus?.active ? 'text-amber-400' : 'text-gray-500'}`}>
                {regionalFocus?.active
                  ? `REGIONAL THREAT INTERCEPT — ${regionalFocus.name.toUpperCase()}${regionalFocus.countryCode ? ` [${regionalFocus.countryCode}]` : ''}`
                  : 'GLOBAL THREAT INTERCEPT'
                }
              </span>
              {regionalFocus?.active && (
                <button
                  onClick={() => setRegionalFocus(null)}
                  className="text-[8px] text-gray-500 hover:text-red-400 font-mono tracking-wider ml-2 mt-1 border border-gray-700 hover:border-red-500/50 px-1.5 py-0.5 rounded transition-colors pointer-events-auto"
                >
                  ✕ EXIT REGION
                </button>
              )}
            </div>
          </motion.div>

          {/* SYSTEM METRICS TOP LEFT */}
          <div className="absolute top-2 left-6 text-[8px] font-mono tracking-widest text-cyan-500/50 z-[200] pointer-events-none">
            OPTIC VIS:113  SRC:180  DENS:1.42  0.8ms
          </div>

          {/* SYSTEM METRICS TOP RIGHT */}

          {/* LEFT HUD CONTAINER */}
          <div className="absolute left-6 top-24 bottom-6 w-80 flex flex-col gap-6 z-[200] pointer-events-none">
            {/* LEFT PANEL - DATA LAYERS */}
            <WorldviewLeftPanel data={filteredData} activeLayers={activeLayers} setActiveLayers={setActiveLayers} onSettingsClick={() => setSettingsOpen(true)} onLegendClick={() => setLegendOpen(true)} />

            {/* LEFT BOTTOM - DISPLAY CONFIG */}
            <WorldviewRightPanel effects={effects} setEffects={setEffects} setUiVisible={setUiVisible} />
          </div>

          {/* RIGHT HUD CONTAINER */}
          <div className="absolute right-6 top-24 bottom-6 w-80 flex flex-col gap-4 z-[200] pointer-events-auto overflow-y-auto styled-scrollbar pr-2">
            {/* F.R.I.D.A.Y. handles search/OSINT — FindLocateBar removed */}

            {/* TOP RIGHT - MARKETS */}
            <div className="flex-shrink-0">
              <MarketsPanel data={data} />
            </div>

            {/* SIGINT & RADIO INTERCEPTS */}
            <div className="flex-shrink-0">
              <RadioInterceptPanel
                data={data}
                isEavesdropping={isEavesdropping}
                setIsEavesdropping={setIsEavesdropping}
                eavesdropLocation={eavesdropLocation}
                cameraCenter={cameraCenter}
              />
            </div>

            {/* DATA FILTERS */}
            <div className="flex-shrink-0">
              <FilterPanel data={data} activeFilters={activeFilters} setActiveFilters={setActiveFilters} />
            </div>

            {/* F.R.I.D.A.Y. AI Analysis Panel */}
            <div className="flex-shrink-0">
              <FridayPanel
                selectedEntity={selectedEntity}
                regionDossier={regionDossier}
                regionalFocus={regionalFocus}
                regionalData={filteredData}
                activeLayers={activeLayers}
                onOsintResult={(result: any) => {
                  setSelectedEntity({
                    type: 'osint_search',
                    id: result.query || result.answer?.substring(0, 30) || 'osint',
                    extra: result,
                  });
                  const locs = (result.locations || []).filter((l: any) => l.lat != null && (l.lon != null || l.lng != null));
                  if (locs.length > 0) {
                    // Fly to first location
                    setFlyToLocation({ lat: locs[0].lat, lng: locs[0].lon ?? locs[0].lng, ts: Date.now() });
                    // Pin all locations on the map
                    const newPins = locs.map((l: any, i: number) => ({
                      lat: l.lat,
                      lng: l.lon ?? l.lng,
                      label: l.label || `Result ${i + 1}`,
                      source: l.source || 'osint',
                      id: `pin-${Date.now()}-${i}`,
                      media_url: l.media_url || '',
                      media_type: l.media_type || '',
                      thumbnail: l.thumbnail || '',
                    }));
                    setPinnedLocations(prev => [...prev, ...newPins]);
                  }
                }}
                onLocate={(lat: number, lng: number) => setFlyToLocation({ lat, lng, ts: Date.now() })}
                onEntitySelect={setSelectedEntity}
                data={filteredData}
              />
            </div>

            {/* BOTTOM RIGHT - NEWS FEED (fills remaining space) */}
            <div className="flex-1 min-h-0 flex flex-col">
              <NewsFeed data={filteredData} selectedEntity={selectedEntity} regionDossier={regionDossier} regionDossierLoading={regionDossierLoading} activeLayers={activeLayers} regionalFocus={regionalFocus} />
            </div>
          </div>

          {/* BOTTOM CENTER COORDINATE / LOCATION BAR */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 1, duration: 1 }}
            className="absolute bottom-6 left-1/2 -translate-x-1/2 z-[200] pointer-events-auto"
          >
            <div
              className="bg-black/60 backdrop-blur-md border border-gray-800 rounded-xl px-6 py-2.5 flex items-center gap-6 shadow-[0_4px_30px_rgba(0,0,0,0.5)] border-b-2 border-b-cyan-900 cursor-pointer"
              onClick={cycleStyle}
            >
              {/* Coordinates */}
              <div className="flex flex-col items-center min-w-[120px]">
                <div className="text-[8px] text-gray-600 font-mono tracking-[0.2em]">COORDINATES</div>
                <div className="text-[11px] text-cyan-400 font-mono font-bold tracking-wide">
                  {mouseCoords ? `${mouseCoords.lat.toFixed(4)}, ${mouseCoords.lng.toFixed(4)}` : '0.0000, 0.0000'}
                </div>
              </div>

              {/* Divider */}
              <div className="w-px h-8 bg-gray-700" />

              {/* Location name */}
              <div className="flex flex-col items-center min-w-[180px] max-w-[320px]">
                <div className="text-[8px] text-gray-600 font-mono tracking-[0.2em]">LOCATION</div>
                <div className="text-[10px] text-gray-300 font-mono truncate max-w-[320px]">
                  {locationLabel || 'Hover over map...'}
                </div>
              </div>

              {/* Divider */}
              <div className="w-px h-8 bg-gray-700" />

              {/* Style preset (compact) */}
              <div className="flex flex-col items-center">
                <div className="text-[8px] text-gray-600 font-mono tracking-[0.2em]">STYLE</div>
                <div className="text-[11px] text-cyan-400 font-mono font-bold">{activeStyle}</div>
              </div>
            </div>
          </motion.div>
        </>
      )}

      {/* RESTORE UI BUTTON (If Hidden) */}
      {!uiVisible && (
        <button
          onClick={() => setUiVisible(true)}
          className="absolute bottom-6 right-6 z-[200] bg-black/60 backdrop-blur-md border border-gray-800 rounded px-4 py-2 text-[10px] font-mono tracking-widest text-cyan-500 hover:text-cyan-300 hover:border-cyan-800 transition-colors pointer-events-auto"
        >
          RESTORE UI
        </button>
      )}

      {/* DYNAMIC SCALE BAR */}
      <div className="absolute bottom-[5.5rem] left-[26rem] z-[201] pointer-events-auto">
        <ScaleBar
          zoom={mapView.zoom}
          latitude={mapView.latitude}
          measureMode={measureMode}
          measurePoints={measurePoints}
          onToggleMeasure={() => {
            setMeasureMode(m => {
              if (m) setMeasurePoints([]); // Clear points when exiting measure mode
              return !m;
            });
          }}
          onClearMeasure={() => setMeasurePoints([])}
        />
      </div>

      {/* STATIC CRT VIGNETTE */}
      <div className="absolute inset-0 pointer-events-none z-[2]"
        style={{
          background: 'radial-gradient(circle, transparent 40%, rgba(0,0,0,0.8) 100%)'
        }}
      />

      {/* SCANLINES OVERLAY */}
      <div className="absolute inset-0 pointer-events-none z-[3] opacity-5 bg-[linear-gradient(rgba(255,255,255,0.1)_1px,transparent_1px)]" style={{ backgroundSize: '100% 4px' }}></div>

      {/* SETTINGS PANEL */}
      <SettingsPanel isOpen={settingsOpen} onClose={() => setSettingsOpen(false)} />

      {/* MAP LEGEND */}
      <MapLegend isOpen={legendOpen} onClose={() => setLegendOpen(false)} />

      {/* ONBOARDING MODAL */}
      {showOnboarding && (
        <OnboardingModal
          onClose={() => setShowOnboarding(false)}
          onOpenSettings={() => { setShowOnboarding(false); setSettingsOpen(true); }}
        />
      )}

      {/* BACKEND DISCONNECTED BANNER */}
      {backendStatus === 'disconnected' && (
        <div className="absolute top-0 left-0 right-0 z-[9000] flex items-center justify-center py-2 bg-red-950/90 border-b border-red-500/40 backdrop-blur-sm">
          <span className="text-[10px] font-mono tracking-widest text-red-400">
            BACKEND OFFLINE — Cannot reach {API_BASE}. Start the backend server or check your connection.
          </span>
        </div>
      )}

    </main>
  );
}
