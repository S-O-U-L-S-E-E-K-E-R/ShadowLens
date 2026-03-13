"use client";

import { useState, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { AlertTriangle, Clock, ChevronDown, ChevronUp, Crosshair, Search, Shield, Globe, Cpu, Fingerprint, Download, Brain, Send } from 'lucide-react';
import React, { useEffect, useRef, useCallback } from 'react';
import { API_BASE } from '@/lib/api';
import Hls from 'hls.js';
import WikiImage from '@/components/WikiImage';

function HlsVideo({ src, className }: { src: string; className?: string }) {
    const videoRef = useRef<HTMLVideoElement>(null);
    const hlsRef = useRef<Hls | null>(null);

    useEffect(() => {
        const video = videoRef.current;
        if (!video) return;

        // Destroy previous HLS instance before creating new one
        if (hlsRef.current) {
            hlsRef.current.destroy();
            hlsRef.current = null;
        }

        if (Hls.isSupported()) {
            const hls = new Hls({ enableWorker: false, lowLatencyMode: true });
            hlsRef.current = hls;
            hls.loadSource(src);
            hls.attachMedia(video);
            hls.on(Hls.Events.MANIFEST_PARSED, () => { video.play().catch(() => {}); });
            return () => { hls.destroy(); hlsRef.current = null; };
        } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
            video.pause();
            video.src = src;
            video.play().catch(() => {});
            return () => { video.pause(); video.removeAttribute('src'); video.load(); };
        }
    }, [src]);

    return <video ref={videoRef} autoPlay muted playsInline className={className} />;
}

// Format time from pubish string "Tue, 24 Feb 2026 15:30:00 GMT" to "15:30"
function formatTime(pubDate: string) {
    try {
        const d = new Date(pubDate);
        return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    } catch {
        return "00:00";
    }
}

// ICAO type designator → Wikipedia article title
const AIRCRAFT_WIKI: Record<string, string> = {
    // Boeing widebodies
    B741: 'Boeing 747', B742: 'Boeing 747', B743: 'Boeing 747', B744: 'Boeing 747-400', B748: 'Boeing 747-8',
    B752: 'Boeing 757', B753: 'Boeing 757', B762: 'Boeing 767', B763: 'Boeing 767', B764: 'Boeing 767',
    B772: 'Boeing 777', B773: 'Boeing 777', B77L: 'Boeing 777', B77W: 'Boeing 777', B778: 'Boeing 777X',
    B788: 'Boeing 787 Dreamliner', B789: 'Boeing 787 Dreamliner', B78X: 'Boeing 787 Dreamliner',
    // Boeing narrowbodies
    B712: 'Boeing 717', B731: 'Boeing 737', B732: 'Boeing 737', B733: 'Boeing 737', B734: 'Boeing 737',
    B735: 'Boeing 737', B736: 'Boeing 737', B737: 'Boeing 737', B738: 'Boeing 737 Next Generation',
    B739: 'Boeing 737 Next Generation', B37M: 'Boeing 737 MAX', B38M: 'Boeing 737 MAX', B39M: 'Boeing 737 MAX',
    // Airbus widebodies
    A306: 'Airbus A300', A310: 'Airbus A310', A332: 'Airbus A330', A333: 'Airbus A330', A338: 'Airbus A330neo',
    A339: 'Airbus A330neo', A342: 'Airbus A340', A343: 'Airbus A340', A345: 'Airbus A340', A346: 'Airbus A340',
    A359: 'Airbus A350', A35K: 'Airbus A350', A388: 'Airbus A380',
    // Airbus narrowbodies
    A318: 'Airbus A318', A319: 'Airbus A319', A320: 'Airbus A320', A321: 'Airbus A321',
    A19N: 'Airbus A319neo', A20N: 'Airbus A320neo family', A21N: 'Airbus A321neo',
    // Embraer
    E135: 'Embraer ERJ 145 family', E145: 'Embraer ERJ 145 family', E170: 'Embraer E-Jet family',
    E175: 'Embraer E-Jet family', E190: 'Embraer E-Jet family', E195: 'Embraer E-Jet family',
    E290: 'Embraer E-Jet E2 family', E295: 'Embraer E-Jet E2 family',
    // Bombardier / CRJ
    CRJ1: 'Bombardier CRJ100/200', CRJ2: 'Bombardier CRJ100/200', CRJ7: 'Bombardier CRJ700 series',
    CRJ9: 'Bombardier CRJ700 series', CRJX: 'Bombardier CRJ700 series',
    // Turboprops
    DH8A: 'De Havilland Canada Dash 8', DH8B: 'De Havilland Canada Dash 8',
    DH8C: 'De Havilland Canada Dash 8', DH8D: 'De Havilland Canada Dash 8',
    AT45: 'ATR 42', AT46: 'ATR 42', AT72: 'ATR 72', AT76: 'ATR 72',
    // Bizjets
    C56X: 'Cessna Citation Excel', C680: 'Cessna Citation Sovereign', C750: 'Cessna Citation X',
    CL30: 'Bombardier Challenger 300', CL35: 'Bombardier Challenger 350',
    CL60: 'Bombardier Challenger 600 series', GL5T: 'Bombardier Global 5000',
    GLEX: 'Bombardier Global Express', GLF4: 'Gulfstream IV', GLF5: 'Gulfstream V',
    GLF6: 'Gulfstream G650', G280: 'Gulfstream G280', GA5C: 'Gulfstream G500/G600',
    GA6C: 'Gulfstream G500/G600', LJ35: 'Learjet 35', LJ45: 'Learjet 45', LJ60: 'Learjet 60',
    F900: 'Dassault Falcon 900', FA7X: 'Dassault Falcon 7X', FA8X: 'Dassault Falcon 8X',
    // Military common
    C130: 'Lockheed C-130 Hercules', C17: 'Boeing C-17 Globemaster III',
    KC35: 'Boeing KC-135 Stratotanker', KC46: 'Boeing KC-46 Pegasus', K35R: 'Boeing KC-135 Stratotanker',
    E3CF: 'Boeing E-3 Sentry', E6B: 'Boeing E-6 Mercury', P8: 'Boeing P-8 Poseidon',
    B52H: 'Boeing B-52 Stratofortress', F16: 'General Dynamics F-16 Fighting Falcon',
    F15: 'McDonnell Douglas F-15 Eagle', F18H: 'Boeing F/A-18E/F Super Hornet',
    F35: 'Lockheed Martin F-35 Lightning II', F22: 'Lockheed Martin F-22 Raptor',
    A10: 'Fairchild Republic A-10 Thunderbolt II', V22: 'Bell Boeing V-22 Osprey',
    C5M: 'Lockheed C-5 Galaxy', C2: 'Grumman C-2 Greyhound',
    EUFI: 'Eurofighter Typhoon', RFAL: 'Dassault Rafale', TORN: 'Panavia Tornado',
    // GA
    C172: 'Cessna 172', C182: 'Cessna 182 Skylane', C206: 'Cessna 206', C208: 'Cessna 208 Caravan',
    C210: 'Cessna 210 Centurion', PA28: 'Piper PA-28 Cherokee', PA32: 'Piper PA-32',
    PA46: 'Piper PA-46 Malibu', BE36: 'Beechcraft Bonanza', BE9L: 'Beechcraft King Air',
    BE20: 'Beechcraft Super King Air', B350: 'Beechcraft King Air 350', PC12: 'Pilatus PC-12',
    PC24: 'Pilatus PC-24', TBM7: 'Daher TBM', TBM8: 'Daher TBM', TBM9: 'Daher TBM',
    // Helicopters
    R44: 'Robinson R44', R22: 'Robinson R22', R66: 'Robinson R66',
    B06: 'Bell 206', B407: 'Bell 407', B412: 'Bell 412',
    EC35: 'Airbus Helicopters H135', EC45: 'Airbus Helicopters H145',
    S76: 'Sikorsky S-76', S92: 'Sikorsky S-92',
    // Russian / other
    SU95: 'Sukhoi Superjet 100', AN12: 'Antonov An-12', AN26: 'Antonov An-26',
    IL76: 'Ilyushin Il-76', IL96: 'Ilyushin Il-96',
    A400: 'Airbus A400M Atlas', C295: 'Airbus C-295',
};

// Module-level cache for Wikipedia thumbnails (persists across re-renders)
const _wikiThumbCache: Record<string, { url: string | null; loading: boolean }> = {};

function useAircraftImage(model: string | undefined): { imgUrl: string | null; wikiUrl: string | null; loading: boolean } {
    const [, forceUpdate] = useState(0);
    const wikiTitle = model ? AIRCRAFT_WIKI[model] : undefined;
    const wikiUrl = wikiTitle ? `https://en.wikipedia.org/wiki/${wikiTitle.replace(/ /g, '_')}` : null;

    useEffect(() => {
        if (!wikiTitle) return;
        const key = wikiTitle;
        if (_wikiThumbCache[key]) return; // Already fetched or in-flight
        _wikiThumbCache[key] = { url: null, loading: true };
        fetch(`https://en.wikipedia.org/api/rest_v1/page/summary/${encodeURIComponent(wikiTitle)}`)
            .then(r => r.json())
            .then(d => {
                _wikiThumbCache[key] = { url: d.thumbnail?.source || null, loading: false };
                forceUpdate(n => n + 1);
            })
            .catch(() => {
                _wikiThumbCache[key] = { url: null, loading: false };
                forceUpdate(n => n + 1);
            });
    }, [wikiTitle]);

    if (!wikiTitle) return { imgUrl: null, wikiUrl: null, loading: false };
    const cached = _wikiThumbCache[wikiTitle];
    return { imgUrl: cached?.url || null, wikiUrl, loading: cached?.loading || false };
}


// Vessel type → Wikipedia article for generic ships (carriers have their own wiki field)
const VESSEL_TYPE_WIKI: Record<string, string> = {
    'tanker': 'https://en.wikipedia.org/wiki/Oil_tanker',
    'cargo': 'https://en.wikipedia.org/wiki/Container_ship',
    'passenger': 'https://en.wikipedia.org/wiki/Cruise_ship',
    'yacht': 'https://en.wikipedia.org/wiki/Superyacht',
    'military_vessel': 'https://en.wikipedia.org/wiki/Warship',
};

// ---------------------------------------------------------------------------
// OSINT Actions — context-aware scan/recon buttons for entities with
// actionable network targets (IPs, domains, URLs). Only rendered in the
// generic entity panel which already handles nmap_host, snort_alert,
// cyber_threat, nuclei_vuln, etc.  NOT placed in flight/ship/gdelt panels
// because those entities have no network targets.
// ---------------------------------------------------------------------------
const _isPrivateIP = (ip: string) => {
    const p = ip.split('.').map(Number);
    if (p.length !== 4) return true;
    return (p[0] === 10) ||
        (p[0] === 172 && p[1] >= 16 && p[1] <= 31) ||
        (p[0] === 192 && p[1] === 168) ||
        (p[0] === 127);
};

// ---------------------------------------------------------------------------
// F.R.I.D.A.Y. — Global AI analysis engine. Works with ANY entity type.
// Sends entity context to the LLM pipeline for analysis, risk assessment,
// vulnerability identification, and actionable recommendations.
// ---------------------------------------------------------------------------
// Build a compact summary of all active data layers for F.R.I.D.A.Y. context
// This is LIVE data — news, social, GDELT, flights, ships, etc. are real-time feeds
function buildLayerContext(data: any, activeLayers: any, isRegional?: boolean): any {
    if (!data) return null;
    const ctx: any = { _data_type: 'LIVE_REAL_TIME_FEEDS' };
    const summarize = (arr: any[], limit: number, pick: (item: any) => any) =>
        arr?.length ? { count: arr.length, items: arr.slice(0, limit).map(pick) } : undefined;

    // News, social, GDELT — ALWAYS included (these are the primary intel feeds)
    // Send more items when regional focus is active (data is already filtered/smaller)
    const newsLimit = isRegional ? 30 : 20;
    const socialLimit = isRegional ? 20 : 12;
    const gdeltLimit = isRegional ? 15 : 10;

    if (data.news?.length)
        ctx.live_news_feed = summarize(data.news, newsLimit, (n: any) => ({
            title: n.title, source: n.source_id || n.source, category: n.category,
            pubDate: n.pubDate, description: n.description?.substring(0, 250),
            link: n.link,
        }));
    if (data.social_media?.length)
        ctx.live_social_feed = summarize(data.social_media, socialLimit, (s: any) => ({
            platform: s.platform, author: s.author, text: s.text?.substring(0, 250),
            timestamp: s.timestamp, url: s.url,
        }));
    if (data.gdelt?.length)
        ctx.gdelt_global_events = summarize(data.gdelt, gdeltLimit, (g: any) => ({
            name: g.properties?.name, count: g.properties?.count, tone: g.properties?.avgTone,
            lat: g.geometry?.coordinates?.[1], lng: g.geometry?.coordinates?.[0],
            headlines: g.properties?._headlines_list?.slice(0, 3),
        }));
    if (data.liveuamap?.length)
        ctx.conflict_events = summarize(data.liveuamap, 10, (l: any) => ({
            title: l.title, source: l.source, time: l.time, lat: l.lat, lng: l.lng,
        }));

    // Flight layers — include if active OR if data exists (always useful context)
    if (data.commercial_flights?.length)
        ctx.commercial_flights = summarize(data.commercial_flights, 10, (f: any) => ({
            callsign: f.callsign, icao24: f.icao24, airline: f.airline, model: f.model,
            alt: f.alt_baro || f.altitude, speed: f.gs || f.speed, lat: f.lat, lon: f.lon,
            origin: f.origin, destination: f.destination, registration: f.registration,
        }));
    if (data.private_flights?.length)
        ctx.private_flights = summarize(data.private_flights, 8, (f: any) => ({
            callsign: f.callsign, icao24: f.icao24, model: f.model, alt: f.alt_baro || f.altitude,
            speed: f.gs || f.speed, registration: f.registration, owner: f.owner,
        }));
    if (data.private_jets?.length)
        ctx.private_jets = summarize(data.private_jets, 8, (f: any) => ({
            callsign: f.callsign, icao24: f.icao24, model: f.model, owner: f.owner,
            registration: f.registration, alt: f.alt_baro || f.altitude,
        }));
    if (data.military_flights?.length)
        ctx.military_flights = summarize(data.military_flights, 10, (f: any) => ({
            callsign: f.callsign, icao24: f.icao24, model: f.model, operator: f.operator || f.airline,
            alt: f.alt_baro || f.altitude, speed: f.gs || f.speed, country: f.country,
        }));
    if (data.tracked_flights?.length)
        ctx.tracked_flights = summarize(data.tracked_flights, 10, (f: any) => ({
            callsign: f.callsign, icao24: f.icao24, model: f.model, alert_color: f.alert_color,
            reason: f.reason, alt: f.alt_baro || f.altitude,
        }));
    if (data.ships?.length)
        ctx.ships = summarize(data.ships, 10, (s: any) => ({
            name: s.name || s.shipname, mmsi: s.mmsi, imo: s.imo, ship_type: s.ship_type,
            flag: s.flag, destination: s.destination, speed: s.speed, status: s.status,
        }));
    if (data.earthquakes?.length)
        ctx.earthquakes = summarize(data.earthquakes, 8, (e: any) => ({
            magnitude: e.mag || e.magnitude, place: e.place, depth: e.depth, time: e.time,
        }));
    if (data.satellites?.length)
        ctx.satellites = summarize(data.satellites, 6, (s: any) => ({
            name: s.name, id: s.id, type: s.type, altitude_km: s.altitude_km,
        }));
    if (data.cctv?.length)
        ctx.cctv_cameras = { count: data.cctv.length };
    if (data.cyber_threats?.length)
        ctx.cyber_threats = summarize(data.cyber_threats, 6, (c: any) => ({
            name: c.name, type: c.type, severity: c.severity, source: c.source,
        }));
    if (data.nmap_hosts?.length)
        ctx.nmap_hosts = summarize(data.nmap_hosts, 6, (h: any) => ({
            ip: h.ip, hostname: h.hostname, ports: h.ports, os: h.os,
        }));
    if (data.nuclei_vulns?.length)
        ctx.nuclei_vulns = summarize(data.nuclei_vulns, 6, (v: any) => ({
            name: v.name, severity: v.severity, host: v.host, template: v.template_id,
        }));
    if (data.snort_alerts?.length)
        ctx.snort_alerts = summarize(data.snort_alerts, 6, (a: any) => ({
            msg: a.msg, priority: a.priority, src: a.src_ip, dst: a.dst_ip,
        }));
    if (data.kismet_devices?.length)
        ctx.kismet_devices = summarize(data.kismet_devices, 6, (d: any) => ({
            name: d.name, mac: d.mac, type: d.type, signal: d.signal, channel: d.channel,
        }));

    // Summary of active layers
    if (activeLayers) {
        const activeLayerNames = Object.entries(activeLayers)
            .filter(([k, v]) => v === true && k !== 'cctvFilters')
            .map(([k]) => k);
        if (activeLayerNames.length) ctx._active_layers = activeLayerNames;
    }

    return Object.keys(ctx).length > 1 ? ctx : null; // >1 because _data_type always present
}

// Parse F.R.I.D.A.Y. response text for clickable entity references
function parseActionableText(text: string, data: any, onLocate?: (lat: number, lng: number) => void, onEntitySelect?: (e: any) => void): React.ReactNode[] {
    if (!text) return [];
    // Pattern: callsigns (AAL123, DAL54), ICAO hex (a1b2c3), IPs, coordinates
    const pattern = /\b([A-Z]{2,4}\d{1,5})\b|\b([0-9a-fA-F]{6})\b|\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b|\b(-?\d{1,3}\.\d{3,})[,\s]+(-?\d{1,3}\.\d{3,})\b/g;
    const parts: React.ReactNode[] = [];
    let lastIdx = 0;
    let match;
    while ((match = pattern.exec(text)) !== null) {
        if (match.index > lastIdx) parts.push(text.slice(lastIdx, match.index));
        const full = match[0];
        const callsign = match[1];
        const hexCode = match[2];
        const ip = match[3];
        const lat = match[4] ? parseFloat(match[4]) : null;
        const lng = match[5] ? parseFloat(match[5]) : null;

        let clickable = false;
        let clickFn: (() => void) | undefined;

        if (callsign && data) {
            const allFlights = [...(data.commercial_flights || []), ...(data.military_flights || []), ...(data.private_flights || []), ...(data.private_jets || []), ...(data.tracked_flights || [])];
            const f = allFlights.find((fl: any) => (fl.callsign || '').toUpperCase() === callsign);
            if (f) {
                clickable = true;
                clickFn = () => {
                    const fLat = f.lat; const fLng = f.lon || f.lng || f.longitude;
                    if (fLat && fLng) onLocate?.(fLat, fLng);
                    onEntitySelect?.({ type: 'flight', id: f.icao24 || callsign, name: callsign, extra: f });
                };
            }
        }
        if (lat !== null && lng !== null && Math.abs(lat) <= 90 && Math.abs(lng) <= 180) {
            clickable = true;
            clickFn = () => onLocate?.(lat, lng);
        }

        if (clickable) {
            parts.push(<span key={match.index} className="text-cyan-400 hover:text-cyan-300 cursor-pointer underline decoration-dotted" onClick={clickFn}>{full}</span>);
        } else {
            parts.push(full);
        }
        lastIdx = match.index + full.length;
    }
    if (lastIdx < text.length) parts.push(text.slice(lastIdx));
    return parts;
}

// Watchlist alert condition
interface WatchCondition { id: string; text: string; keywords: string[]; created: number; triggered: boolean; lastTriggered?: number; matchedItem?: string; }
const WATCH_TRIGGERS = ['alert me', 'watch for', 'notify me', 'warn me', 'monitor for', 'let me know'];

function FridayPanel({ selectedEntity, regionDossier, regionalFocus, regionalData, activeLayers, onOsintResult, onLocate, onEntitySelect, data }: { selectedEntity: { type: string; id: string | number; name?: string; callsign?: string; extra?: any } | null; regionDossier?: any; regionalFocus?: { active: boolean; name: string; countryCode: string; lat?: number; lng?: number } | null; regionalData?: any; activeLayers?: any; onOsintResult?: (result: any) => void; onLocate?: (lat: number, lng: number) => void; onEntitySelect?: (entity: any) => void; data?: any }) {
    const [question, setQuestion] = useState('');
    const [messages, setMessages] = useState<{role: 'user'|'assistant', content: string, meta?: any}[]>([]);
    const [loading, setLoading] = useState(false);
    const [minimized, setMinimized] = useState(false);
    const [autoSummary, setAutoSummary] = useState<any>(null);
    const [autoLoading, setAutoLoading] = useState(false);
    const prevEntityRef = useRef<string | null>(null);
    const [showLocalResults, setShowLocalResults] = useState(false);
    const chatEndRef = useRef<HTMLDivElement>(null);
    const [showWatchlist, setShowWatchlist] = useState(false);
    const [briefing, setBriefing] = useState<any>(null);
    const briefingDone = useRef(false);

    // Watchlist — persisted in localStorage
    const [watchlist, setWatchlist] = useState<WatchCondition[]>(() => {
        try { return JSON.parse(localStorage.getItem('friday-watchlist') || '[]'); } catch { return []; }
    });
    useEffect(() => { localStorage.setItem('friday-watchlist', JSON.stringify(watchlist)); }, [watchlist]);

    // Watchlist checker — run on data changes
    useEffect(() => {
        if (!data || watchlist.length === 0) return;
        const now = Date.now();
        const cooldown = 5 * 60 * 1000; // 5 min
        setWatchlist(prev => prev.map(w => {
            if (w.triggered && w.lastTriggered && now - w.lastTriggered < cooldown) return w;
            const searchPool = [
                ...(data.news || []).map((n: any) => n.title + ' ' + (n.description || '')),
                ...(data.social_media || []).map((s: any) => s.text || ''),
                ...(data.military_flights || []).map((f: any) => `${f.callsign} ${f.model} ${f.country || ''} ${f.operator || ''}`),
                ...(data.tracked_flights || []).map((f: any) => `${f.callsign} ${f.model} ${f.reason || ''}`),
                ...(data.cyber_threats || []).map((c: any) => `${c.name} ${c.type || ''}`),
                ...(data.snort_alerts || []).map((a: any) => a.msg || ''),
            ];
            const pool = searchPool.join(' ').toLowerCase();
            const matched = w.keywords.some(kw => pool.includes(kw.toLowerCase()));
            if (matched) {
                const matchedIn = searchPool.find(s => w.keywords.some(kw => s.toLowerCase().includes(kw.toLowerCase())));
                return { ...w, triggered: true, lastTriggered: now, matchedItem: matchedIn?.substring(0, 100) };
            }
            return w;
        }));
    }, [data]);

    const triggeredAlerts = watchlist.filter(w => w.triggered);

    // Auto-scroll chat
    useEffect(() => { chatEndRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages, loading]);

    // Auto-briefing — generate on first data load or regional focus change
    useEffect(() => {
        if (!data || briefingDone.current) return;
        const newsCount = data.news?.length || 0;
        const milCount = data.military_flights?.length || 0;
        const trackedCount = data.tracked_flights?.length || 0;
        const eqCount = data.earthquakes?.length || 0;
        const cyberCount = data.cyber_threats?.length || 0;
        const shipCount = data.ships?.length || 0;
        if (newsCount + milCount + trackedCount + eqCount === 0) return;
        briefingDone.current = true;

        const topNews = (data.news || []).slice(0, 3).map((n: any) => n.title);
        const notableEvents: string[] = [];
        if (milCount > 0) notableEvents.push(`${milCount} military aircraft tracked`);
        if (trackedCount > 0) notableEvents.push(`${trackedCount} watchlist flights active`);
        if (eqCount > 0) {
            const big = (data.earthquakes || []).filter((e: any) => (e.mag || e.magnitude || 0) >= 4.5);
            notableEvents.push(`${eqCount} seismic events${big.length ? ` (${big.length} M4.5+)` : ''}`);
        }
        if (cyberCount > 0) notableEvents.push(`${cyberCount} cyber threat indicators`);
        if (shipCount > 0) notableEvents.push(`${shipCount} vessels tracked`);

        setBriefing({
            timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
            topNews,
            notableEvents,
            region: regionalFocus?.active ? regionalFocus.name : 'Global',
        });
    }, [data, regionalFocus]);

    // Reset briefing on regional focus change
    useEffect(() => { briefingDone.current = false; setBriefing(null); }, [regionalFocus?.active, regionalFocus?.name]);

    // Local entity search
    const localMatches = useMemo(() => {
        if (!question || question.length < 2 || !data) return [];
        const q = question.toLowerCase();
        const matches: { label: string; sublabel: string; type: string; id: string | number; lat: number; lng: number }[] = [];
        const addFlights = (arr: any[], type: string) => {
            arr?.forEach((f: any) => {
                const cs = (f.callsign || '').toLowerCase();
                const icao = (f.icao24 || '').toLowerCase();
                const reg = (f.registration || '').toLowerCase();
                if (cs.includes(q) || icao.includes(q) || reg.includes(q)) {
                    matches.push({ label: f.callsign || f.icao24 || 'Unknown', sublabel: [f.model, f.airline, f.registration].filter(Boolean).join(' / '), type, id: f.icao24 || f.callsign, lat: f.lat, lng: f.lon || f.lng || f.longitude });
                }
            });
        };
        addFlights(data.commercial_flights, 'flight');
        addFlights(data.private_flights, 'private_flight');
        addFlights(data.private_jets, 'private_jet');
        addFlights(data.military_flights, 'military_flight');
        addFlights(data.tracked_flights, 'tracked_flight');
        data.ships?.forEach((s: any) => {
            const name = (s.name || s.shipname || '').toLowerCase();
            const mmsi = String(s.mmsi || '').toLowerCase();
            if (name.includes(q) || mmsi.includes(q)) {
                matches.push({ label: s.name || s.shipname || 'Unknown Vessel', sublabel: [s.ship_type, s.flag].filter(Boolean).join(' / '), type: 'ship', id: s.mmsi || s.imo, lat: s.lat, lng: s.lon || s.lng || s.longitude });
            }
        });
        return matches.slice(0, 8);
    }, [question, data]);

    // Reset chat and auto-analyze when entity changes
    useEffect(() => {
        const key = selectedEntity ? `${selectedEntity.type}-${selectedEntity.id}` : null;
        if (key !== prevEntityRef.current) {
            setMessages([]);
            setQuestion('');
            setAutoSummary(null);
            prevEntityRef.current = key;
            if (selectedEntity) {
                const entityContext: any = { type: selectedEntity.type, id: selectedEntity.id, name: selectedEntity.name || selectedEntity.callsign, ...(selectedEntity.extra || {}) };
                if (selectedEntity.type === 'region_dossier' && regionDossier) entityContext.region_dossier = regionDossier;
                setAutoLoading(true);
                fetch(`${API_BASE}/api/syd/analyze`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ scan_data: JSON.stringify(entityContext, null, 2), module: 'nmap' }) })
                    .then(r => r.ok ? r.json() : null)
                    .then(d => { if (d && prevEntityRef.current === key) setAutoSummary(d); })
                    .catch(() => {})
                    .finally(() => setAutoLoading(false));
            }
        }
    }, [selectedEntity]);

    const quickQueries = (() => {
        const t = selectedEntity?.type || '';
        if (['nmap_host', 'nuclei_vuln', 'snort_alert'].includes(t)) return ['Vulnerabilities?', 'Next steps', 'Risk assessment'];
        if (['flight', 'military_flight', 'private_flight', 'private_jet', 'tracked_flight'].includes(t)) return ['Flight analysis', 'Risk assessment', 'Anomaly detection'];
        if (t === 'ship') return ['Vessel risk profile', 'Route analysis', 'Sanctions check'];
        if (t === 'region_dossier') return ['Threat assessment', 'Geopolitical analysis', 'Key actors'];
        if (['military_base', 'nuclear_facility', 'embassy'].includes(t)) return ['Strategic significance', 'Threat assessment', 'Regional context'];
        if (t === 'earthquake' || t === 'eq') return ['Seismic analysis', 'Impact assessment'];
        if (t === 'gdelt' || t === 'news' || t === 'liveuamap') return ['Summarize event', 'Impact assessment', 'Related events'];
        return ['Analyze entity', 'Risk assessment', 'Next steps'];
    })();

    // Find local entity by query
    const findLocalEntity = useCallback((q: string): any | null => {
        if (!q || !data) return null;
        const term = q.toLowerCase().replace(/^(find|locate|where is|show|track)\s+/i, '').trim();
        if (term.length < 2) return null;
        const search = (arr: any[], type: string) => {
            if (!arr) return null;
            return (arr.find((f: any) => (f.callsign || '').toLowerCase() === term) || arr.find((f: any) => (f.icao24 || '').toLowerCase() === term) || arr.find((f: any) => (f.registration || '').toLowerCase() === term) || arr.find((f: any) => (f.callsign || '').toLowerCase().includes(term)))
                ? { ...(arr.find((f: any) => (f.callsign || '').toLowerCase() === term) || arr.find((f: any) => (f.icao24 || '').toLowerCase() === term) || arr.find((f: any) => (f.registration || '').toLowerCase() === term) || arr.find((f: any) => (f.callsign || '').toLowerCase().includes(term))), _type: type } : null;
        };
        const searchShip = (arr: any[]) => {
            if (!arr) return null;
            const m = arr.find((s: any) => (s.name || s.shipname || '').toLowerCase().includes(term) || String(s.mmsi || '').includes(term));
            return m ? { ...m, _type: 'ship' } : null;
        };
        return search(data.commercial_flights, 'flight') || search(data.military_flights, 'military_flight') || search(data.tracked_flights, 'tracked_flight') || search(data.private_flights, 'private_flight') || search(data.private_jets, 'private_jet') || searchShip(data.ships) || null;
    }, [data]);

    const askFriday = async (q: string) => {
        if (!q.trim()) return;
        setShowLocalResults(false);

        // Watchlist detection
        const qLower = q.toLowerCase();
        const isWatchRequest = WATCH_TRIGGERS.some(t => qLower.includes(t));
        if (isWatchRequest) {
            const condText = q.replace(/^.*?(alert me|watch for|notify me|warn me|monitor for|let me know)\s*(if|when|about)?\s*/i, '').trim();
            const keywords = condText.toLowerCase().split(/[\s,]+/).filter(w => w.length > 2);
            if (keywords.length > 0) {
                const newWatch: WatchCondition = { id: `w_${Date.now()}`, text: condText, keywords, created: Date.now(), triggered: false };
                setWatchlist(prev => [...prev, newWatch]);
                setMessages(prev => [...prev, { role: 'user', content: q }, { role: 'assistant', content: `Watchlist updated. I'll alert you when: "${condText}"\n\nMonitoring: news feeds, social media, military flights, tracked flights, cyber threats, and security alerts for keywords: ${keywords.join(', ')}`, meta: { mode: 'watchlist' } }]);
                setQuestion('');
                return;
            }
        }

        // Local entity match
        const localEntity = findLocalEntity(q);
        if (localEntity) {
            const lat = localEntity.lat; const lng = localEntity.lon || localEntity.lng || localEntity.longitude;
            if (lat && lng) onLocate?.(lat, lng);
            onEntitySelect?.({ type: localEntity._type, id: localEntity.icao24 || localEntity.mmsi || localEntity.imo || localEntity.callsign, name: localEntity.callsign || localEntity.name || localEntity.shipname, extra: localEntity });
        }

        setMessages(prev => [...prev, { role: 'user', content: q }]);
        setQuestion('');
        setLoading(true);
        try {
            const contextEntity = localEntity ? { type: localEntity._type, id: localEntity.icao24 || localEntity.mmsi || localEntity.callsign, name: localEntity.callsign || localEntity.name, ...localEntity } : selectedEntity;
            const entityContext: any = contextEntity ? { type: contextEntity.type || contextEntity._type, id: contextEntity.id || contextEntity.icao24 || contextEntity.mmsi, name: contextEntity.name || contextEntity.callsign, ...(contextEntity.extra || {}), ...(localEntity || {}) } : { type: 'general', id: 'none' };
            if (selectedEntity?.type === 'region_dossier' && regionDossier) entityContext.region_dossier = regionDossier;
            if (regionalFocus?.active) entityContext.regional_focus = { region_name: regionalFocus.name, country_code: regionalFocus.countryCode, lat: regionalFocus.lat, lng: regionalFocus.lng };
            const layerCtx = buildLayerContext(regionalData, activeLayers, !!regionalFocus?.active);
            if (layerCtx) entityContext.active_data = layerCtx;

            // Build history for follow-up context (last 8 messages)
            const historyForApi = messages.slice(-8).map(m => ({ role: m.role, content: m.content }));

            const res = await fetch(`${API_BASE}/api/syd/query`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ question: q, scan_data: JSON.stringify(entityContext, null, 2), module: 'nmap', history: historyForApi }),
            });
            if (res.ok) {
                const result = await res.json();
                setMessages(prev => [...prev, { role: 'assistant', content: result.answer || result.error || 'No response', meta: result }]);
                if (result.locations?.length > 0 && onOsintResult) {
                    onOsintResult({ query: result.query || q, locations: result.locations, answer: result.answer, mode: result.mode });
                }
            } else {
                setMessages(prev => [...prev, { role: 'assistant', content: `Error: HTTP ${res.status}`, meta: { error: true } }]);
            }
        } catch (e: any) {
            setMessages(prev => [...prev, { role: 'assistant', content: `Error: ${e.message || 'Failed to reach F.R.I.D.A.Y.'}`, meta: { error: true } }]);
        } finally {
            setLoading(false);
        }
    };

    const entityLabel = selectedEntity
        ? (selectedEntity.type === 'region_dossier' && regionDossier?.country?.name ? `Region: ${regionDossier.country.name}` : (selectedEntity.name || selectedEntity.callsign || `${selectedEntity.type}:${selectedEntity.id}`))
        : null;

    const modeBadge = (mode: string) => {
        const styles: Record<string, string> = { osint_research: 'text-cyan-400 border-cyan-800/40 bg-cyan-950/30', scan_analysis: 'text-green-400 border-green-800/40 bg-green-950/30', entity_analysis: 'text-amber-400 border-amber-800/40 bg-amber-950/30', watchlist: 'text-yellow-400 border-yellow-800/40 bg-yellow-950/30' };
        const labels: Record<string, string> = { osint_research: 'OSINT', scan_analysis: 'SCAN', entity_analysis: 'INTEL', watchlist: 'WATCH', general: 'GENERAL' };
        return <span className={`text-[7px] px-1.5 py-0.5 rounded-full border ${styles[mode] || 'text-purple-400 border-purple-800/40 bg-purple-950/30'}`}>{labels[mode] || 'GENERAL'}</span>;
    };

    return (
        <div className="bg-black/60 backdrop-blur-md border border-purple-800/50 rounded-xl font-mono shadow-[0_4px_30px_rgba(128,0,255,0.15)] pointer-events-auto overflow-hidden flex flex-col max-h-[500px]">
            <div className="px-3 py-2 border-b border-purple-500/20 bg-purple-950/30 cursor-pointer hover:bg-purple-900/30 transition-colors flex justify-between items-center flex-shrink-0" onClick={() => setMinimized(!minimized)}>
                <h2 className="text-[10px] tracking-[0.2em] font-bold text-purple-400 flex items-center gap-2">
                    <Brain size={12} />
                    F.R.I.D.A.Y.
                    {selectedEntity ? <span className="text-purple-600 font-normal tracking-normal text-[8px] max-w-[100px] truncate">— {entityLabel}</span>
                    : regionalFocus?.active ? <span className="text-amber-600 font-normal tracking-normal text-[8px] max-w-[100px] truncate">— {regionalFocus.name}</span> : null}
                    {triggeredAlerts.length > 0 && <span className="bg-red-500 text-white text-[7px] px-1.5 rounded-full animate-pulse">{triggeredAlerts.length}</span>}
                </h2>
                <div className="flex items-center gap-1.5">
                    {messages.length > 0 && <button className="text-gray-600 hover:text-red-400 text-[8px] transition-colors" onClick={(e) => { e.stopPropagation(); setMessages([]); }}>CLEAR</button>}
                    {watchlist.length > 0 && <button className="text-gray-600 hover:text-yellow-400 text-[8px] transition-colors" onClick={(e) => { e.stopPropagation(); setShowWatchlist(!showWatchlist); }}>WATCH({watchlist.length})</button>}
                    <button className="text-purple-500 hover:text-white transition-colors">{minimized ? <ChevronDown size={12} /> : <ChevronUp size={12} />}</button>
                </div>
            </div>

            <AnimatePresence>
                {!minimized && (
                    <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="flex flex-col min-h-0 flex-1">
                        {/* Triggered alerts */}
                        {triggeredAlerts.length > 0 && (
                            <div className="px-3 py-1.5 bg-red-950/30 border-b border-red-800/30 flex-shrink-0">
                                {triggeredAlerts.map(a => (
                                    <div key={a.id} className="flex items-center gap-2 text-[8px]">
                                        <AlertTriangle size={10} className="text-red-400 flex-shrink-0" />
                                        <span className="text-red-300 flex-1 truncate">ALERT: {a.text}</span>
                                        <span className="text-red-500/60 truncate max-w-[100px]">{a.matchedItem}</span>
                                        <button className="text-gray-600 hover:text-white" onClick={() => setWatchlist(prev => prev.map(w => w.id === a.id ? { ...w, triggered: false } : w))}>✕</button>
                                    </div>
                                ))}
                            </div>
                        )}

                        {/* Watchlist panel */}
                        {showWatchlist && (
                            <div className="px-3 py-2 bg-yellow-950/10 border-b border-yellow-800/20 flex-shrink-0 max-h-[120px] overflow-y-auto styled-scrollbar">
                                <div className="text-[8px] text-yellow-500 tracking-widest font-bold mb-1">ACTIVE WATCHES</div>
                                {watchlist.map(w => (
                                    <div key={w.id} className="flex items-center gap-2 text-[8px] py-0.5">
                                        <span className={`${w.triggered ? 'text-red-400' : 'text-gray-400'} flex-1 truncate`}>{w.text}</span>
                                        <button className="text-gray-600 hover:text-red-400" onClick={() => setWatchlist(prev => prev.filter(x => x.id !== w.id))}>DEL</button>
                                    </div>
                                ))}
                            </div>
                        )}

                        <div className="px-3 py-2 flex flex-col min-h-0 flex-1">
                            {/* Auto-briefing card */}
                            {briefing && messages.length === 0 && !selectedEntity && (
                                <div className="mb-2 p-2 bg-gradient-to-b from-purple-950/30 to-gray-900/60 border border-purple-800/30 rounded text-[8px]">
                                    <div className="flex items-center justify-between mb-1">
                                        <span className="text-purple-400 font-bold tracking-wider">SITUATION BRIEF — {briefing.region.toUpperCase()}</span>
                                        <span className="text-gray-600">{briefing.timestamp}</span>
                                    </div>
                                    {briefing.notableEvents.length > 0 && (
                                        <div className="flex flex-wrap gap-1.5 mb-1">
                                            {briefing.notableEvents.map((e: string, i: number) => (
                                                <span key={i} className="px-1.5 py-0.5 bg-gray-800/60 border border-gray-700/40 rounded text-gray-300">{e}</span>
                                            ))}
                                        </div>
                                    )}
                                    {briefing.topNews.length > 0 && (
                                        <div className="mt-1 pt-1 border-t border-gray-800/30">
                                            <span className="text-cyan-500 tracking-wider font-bold">TOP HEADLINES</span>
                                            {briefing.topNews.map((h: string, i: number) => <div key={i} className="text-gray-400 truncate mt-0.5">→ {h}</div>)}
                                        </div>
                                    )}
                                    <button className="mt-1 text-gray-600 hover:text-purple-400 text-[7px]" onClick={() => setBriefing(null)}>DISMISS</button>
                                </div>
                            )}

                            {/* Auto-summary for selected entity */}
                            {selectedEntity && autoLoading && (
                                <div className="mb-2 p-1.5 bg-purple-950/20 border border-purple-800/20 rounded text-[8px] text-purple-400 flex items-center gap-1.5 flex-shrink-0">
                                    <span className="animate-pulse">●</span> Scanning entity data...
                                </div>
                            )}
                            {selectedEntity && autoSummary && !autoLoading && (autoSummary.facts_text || autoSummary.next_steps) && messages.length === 0 && (
                                <div className="mb-2 p-2 bg-gray-900/60 border border-purple-800/20 rounded text-[8px] max-h-[100px] overflow-y-auto styled-scrollbar flex-shrink-0">
                                    {autoSummary.facts_text && <div><span className="text-purple-500 font-bold tracking-wider">QUICK SCAN</span><pre className="text-gray-400 whitespace-pre-wrap break-all mt-0.5 leading-relaxed">{autoSummary.facts_text}</pre></div>}
                                </div>
                            )}

                            {/* Chat thread */}
                            {messages.length > 0 && (
                                <div className="flex-1 min-h-0 max-h-[250px] overflow-y-auto styled-scrollbar mb-2 space-y-1.5">
                                    {messages.map((msg, i) => (
                                        <div key={i} className={`text-[9px] ${msg.role === 'user' ? 'text-right' : ''}`}>
                                            {msg.role === 'user' ? (
                                                <div className="inline-block bg-purple-950/40 border border-purple-800/30 rounded px-2 py-1 text-purple-200 max-w-[90%] text-left">{msg.content}</div>
                                            ) : (
                                                <div className="bg-gray-900/60 border border-gray-800/30 rounded px-2 py-1.5">
                                                    <div className="flex items-center gap-1.5 mb-0.5">
                                                        <span className="text-purple-500 font-bold text-[7px]">F.R.I.D.A.Y.</span>
                                                        {msg.meta?.mode && modeBadge(msg.meta.mode)}
                                                        {msg.meta?.validated === false && <span className="text-[7px] text-yellow-400">⚠</span>}
                                                    </div>
                                                    <div className="text-gray-300 whitespace-pre-wrap leading-relaxed">{parseActionableText(msg.content, data, onLocate, onEntitySelect)}</div>
                                                </div>
                                            )}
                                        </div>
                                    ))}
                                    {loading && <div className="text-[9px] text-purple-400 flex items-center gap-1.5 p-1"><span className="animate-pulse">●</span> F.R.I.D.A.Y. thinking...</div>}
                                    <div ref={chatEndRef} />
                                </div>
                            )}
                            {messages.length === 0 && loading && (
                                <div className="mb-2 p-2 bg-purple-950/20 border border-purple-800/30 rounded text-purple-400 text-[9px] flex items-center gap-2">
                                    <span className="animate-pulse">●</span> F.R.I.D.A.Y. PROCESSING...
                                </div>
                            )}

                            {/* Input */}
                            <div className="relative flex-shrink-0">
                                <div className="flex gap-1.5">
                                    <input type="text" value={question} onChange={e => { setQuestion(e.target.value); setShowLocalResults(true); }}
                                        onKeyDown={e => { if (e.key === 'Enter') { setShowLocalResults(false); askFriday(question); } }}
                                        onFocus={() => setShowLocalResults(true)} onBlur={() => setTimeout(() => setShowLocalResults(false), 200)}
                                        placeholder={selectedEntity ? "Ask about this target..." : regionalFocus?.active ? `Ask about ${regionalFocus.name}...` : "Search, ask, or run OSINT..."}
                                        className="flex-1 bg-gray-900/80 border border-purple-800/30 rounded px-2 py-1.5 text-[9px] text-purple-100 placeholder-gray-600 focus:outline-none focus:border-purple-500/50" />
                                    <button onClick={() => { setShowLocalResults(false); askFriday(question); }} disabled={loading || !question.trim()}
                                        className="flex items-center gap-1 px-2 py-1.5 rounded border text-[9px] tracking-wider font-bold transition-all cursor-pointer hover:brightness-125 disabled:opacity-40 bg-purple-950/40 border-purple-500/40 text-purple-400">
                                        <Send size={9} />{loading ? '...' : 'SEEK'}
                                    </button>
                                </div>
                                {showLocalResults && localMatches.length > 0 && !loading && (
                                    <div className="absolute left-0 right-0 bottom-full mb-1 bg-gray-950/95 border border-purple-800/40 rounded max-h-[150px] overflow-y-auto styled-scrollbar z-50">
                                        <div className="px-2 py-1 text-[7px] text-gray-600 tracking-widest border-b border-gray-800/40">LIVE MATCHES</div>
                                        {localMatches.map((m, i) => (
                                            <button key={`${m.type}-${m.id}-${i}`} className="w-full px-2 py-1 text-left hover:bg-purple-950/40 transition-colors flex items-center gap-2 border-b border-gray-900/40 last:border-0 cursor-pointer"
                                                onMouseDown={(e) => { e.preventDefault(); setShowLocalResults(false); setQuestion(''); if (m.lat && m.lng) onLocate?.(m.lat, m.lng); onEntitySelect?.({ type: m.type, id: m.id, name: m.label, extra: {} }); }}>
                                                <span className={`text-[8px] font-bold ${m.type.includes('military') ? 'text-red-400' : m.type === 'ship' ? 'text-blue-400' : m.type.includes('tracked') ? 'text-pink-400' : 'text-cyan-400'}`}>
                                                    {m.type === 'ship' ? '⚓' : '✈'} {m.label}
                                                </span>
                                                <span className="text-[7px] text-gray-500 truncate flex-1">{m.sublabel}</span>
                                            </button>
                                        ))}
                                    </div>
                                )}
                            </div>
                            <div className="flex gap-1 mt-1 flex-wrap flex-shrink-0">
                                {(selectedEntity ? quickQueries : regionalFocus?.active ? [`What's happening in ${regionalFocus.name}?`, 'Threat assessment', 'News summary'] : ['Threat overview', 'Network posture', 'CVE briefing']).map(q => (
                                    <button key={q} onClick={() => { setQuestion(q); askFriday(q); }} disabled={loading}
                                        className="px-1.5 py-0.5 bg-gray-800/50 border border-gray-700/40 rounded text-[8px] text-gray-500 hover:text-purple-400 hover:border-purple-700/40 transition-colors cursor-pointer disabled:opacity-40">{q}</button>
                                ))}
                            </div>
                        </div>
                    </motion.div>
                )}
            </AnimatePresence>
        </div>
    );
}

function OsintActions({ entity, extra }: { entity: { type: string; id: string | number; extra?: any }; extra: any }) {
    const [results, setResults] = useState<any>(null);
    const [loading, setLoading] = useState<string | null>(null);
    const [error, setError] = useState<string | null>(null);
    const cancelledRef = useRef(false);

    // Reset state when entity changes, cancel any running poll
    useEffect(() => {
        cancelledRef.current = false;
        setResults(null);
        setLoading(null);
        setError(null);
        return () => { cancelledRef.current = true; };
    }, [entity.id, entity.type]);

    // Extract actionable network targets from entity data
    const ipRe = /^\d+\.\d+\.\d+\.\d+$/;
    const ipPortRe = /^(\d+\.\d+\.\d+\.\d+):\d+$/; // "1.2.3.4:8080"
    const ips = new Set<string>();
    const domains = new Set<string>();
    const urls = new Set<string>();

    // IP extraction — check all fields that may contain raw IPs
    for (const key of ['ip', 'src_ip', 'dst_ip', 'host', 'target']) {
        const val = extra?.[key] || (entity as any)?.[key];
        if (val && typeof val === 'string' && ipRe.test(val)) ips.add(val);
    }
    // Domain/URL extraction
    for (const key of ['hostname', 'host', 'target', 'matched_at', 'url']) {
        const val = extra?.[key] || (entity as any)?.[key];
        if (!val || typeof val !== 'string') continue;
        if (val.startsWith('http')) {
            urls.add(val);
        } else {
            // Check for IP:port format (e.g. "192.168.1.1:161") → extract IP
            const ipPortMatch = val.match(ipPortRe);
            if (ipPortMatch) {
                ips.add(ipPortMatch[1]);
            } else if (val.includes('.') && !ipRe.test(val)) {
                // Only treat as domain if it's a real hostname, not IP-like
                domains.add(val);
            }
        }
    }

    // Only render if there are actual network targets we can scan
    if (ips.size === 0 && domains.size === 0 && urls.size === 0) return null;

    const runAction = async (tool: string, target: string, label: string) => {
        setLoading(label);
        setError(null);
        setResults(null);
        try {
            const res = await fetch(`${API_BASE}/api/osint/scan`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ tool, target }),
            });
            if (!res.ok) { setError(`HTTP ${res.status}`); return; }
            const data = await res.json();
            if (data.error) {
                setError(data.error);
            } else if (data.status === 'unavailable' || data.status === 'unknown_tool') {
                setError(data.status === 'unavailable' ? 'Tool not available on agent' : 'Unknown tool');
            } else if (data.job_id) {
                setResults({ status: 'running', job_id: data.job_id, tool });
                pollJob(data.job_id, tool);
            } else if (data.status === 'ok' && data.data) {
                setResults(data);
            } else {
                setResults(data);
            }
        } catch (e: any) {
            setError(e.message || 'Request failed');
        } finally {
            setLoading(null);
        }
    };

    const pollJob = async (jobId: string, tool: string) => {
        // Capture baseline counts so we detect NEW results, not pre-existing ones
        let baselineNmap = -1;
        let baselineNuclei = -1;
        try {
            const baseRes = await fetch(`${API_BASE}/api/live-data/osint`);
            if (baseRes.ok) {
                const bd = await baseRes.json();
                baselineNmap = bd.nmap_hosts?.length || 0;
                baselineNuclei = bd.nuclei_vulns?.length || 0;
            }
        } catch { /* use -1 as baseline (any count > 0 triggers) */ }

        // Poll for changes (scans typically finish in 10s-5min)
        for (let i = 0; i < 40; i++) {
            await new Promise(r => setTimeout(r, 3000));
            if (cancelledRef.current) return; // Stop polling if entity changed or unmounted
            try {
                const res = await fetch(`${API_BASE}/api/live-data/osint`);
                if (!res.ok) continue;
                const d = await res.json();
                if (cancelledRef.current) return;
                const nmapCount = d.nmap_hosts?.length || 0;
                const nucleiCount = d.nuclei_vulns?.length || 0;

                if (tool === 'nmap' && nmapCount !== baselineNmap) {
                    setResults({ status: 'complete', message: `${nmapCount} hosts discovered. Enable Network Hosts layer to view.` });
                    return;
                }
                if (tool === 'nuclei' && nucleiCount !== baselineNuclei) {
                    setResults({ status: 'complete', message: `${nucleiCount} findings. Enable Vulnerabilities layer to view.` });
                    return;
                }
                // AutoRecon / other async tools — poll job status directly
                if (tool === 'autorecon' || tool === 'spiderfoot') {
                    try {
                        const jobRes = await fetch(`${API_BASE}/api/osint/job/${encodeURIComponent(jobId)}`);
                        if (jobRes.ok) {
                            const jobData = await jobRes.json();
                            if (jobData.status === 'complete' && jobData.result?.data) {
                                setResults({ status: 'ok', data: jobData.result.data });
                                return;
                            }
                            if (jobData.status === 'complete') {
                                setResults({ status: 'complete', message: `${tool.toUpperCase()} complete — ${jobData.result?.services || 0} services, ${jobData.result?.files || 0} scan files.` });
                                return;
                            }
                            if (jobData.status === 'error') {
                                setError(jobData.error || 'Scan failed');
                                return;
                            }
                        }
                    } catch { /* continue polling */ }
                }
            } catch { /* continue polling */ }
        }
        if (!cancelledRef.current) {
            setResults({ status: 'timeout', message: 'Scan may still be running — enable OSINT layers to check.' });
        }
    };

    const ipList = [...ips];
    const domainList = [...domains];
    const urlList = [...urls];

    const btnClass = (color: string) =>
        `flex items-center gap-1.5 px-2.5 py-1.5 rounded border text-[9px] tracking-wider font-bold transition-all cursor-pointer hover:brightness-125 disabled:opacity-40 ${color}`;

    return (
        <div className="mt-3 pt-3 border-t border-gray-700/50">
            <div className="text-[8px] text-gray-500 tracking-widest mb-2 flex items-center gap-1">
                <Crosshair size={9} /> OSINT ACTIONS
            </div>
            <div className="flex flex-wrap gap-1.5">
                {ipList.map(ip => {
                    const isPrivate = _isPrivateIP(ip);
                    return (
                        <React.Fragment key={ip}>
                            {/* Nmap — works on both private and public IPs */}
                            <button
                                onClick={() => runAction('nmap', ip, `nmap-${ip}`)}
                                disabled={loading !== null}
                                className={btnClass('bg-green-950/40 border-green-500/40 text-green-400')}
                            >
                                <Search size={9} />
                                {loading === `nmap-${ip}` ? 'SCANNING...' : `NMAP ${ip}`}
                            </button>
                            {/* AutoRecon — deep scan with automatic service enumeration */}
                            <button
                                onClick={() => runAction('autorecon', ip, `autorecon-${ip}`)}
                                disabled={loading !== null}
                                className={btnClass('bg-amber-950/40 border-amber-500/40 text-amber-400')}
                            >
                                <Fingerprint size={9} />
                                {loading === `autorecon-${ip}` ? 'DEEP SCAN...' : 'AUTORECON'}
                            </button>
                            {/* Nuclei — only for public/routable IPs (web services) */}
                            {!isPrivate && (
                                <button
                                    onClick={() => runAction('nuclei', `http://${ip}`, `nuclei-${ip}`)}
                                    disabled={loading !== null}
                                    className={btnClass('bg-orange-950/40 border-orange-500/40 text-orange-400')}
                                >
                                    <Shield size={9} />
                                    {loading === `nuclei-${ip}` ? 'SCANNING...' : `VULN SCAN`}
                                </button>
                            )}
                        </React.Fragment>
                    );
                })}
                {urlList.map(url => {
                    // Extract host from URL to check if private
                    const urlHost = url.replace(/^https?:\/\//, '').split(/[/:]/)[0];
                    const urlIsPrivate = _isPrivateIP(urlHost);
                    // Skip URLs whose IP is already in the IP list (avoid duplicate actions)
                    if (ipRe.test(urlHost) && ips.has(urlHost)) return null;
                    return (
                        <React.Fragment key={url}>
                            <button
                                onClick={() => runAction('whatweb', url, `whatweb-${url}`)}
                                disabled={loading !== null}
                                className={btnClass('bg-blue-950/40 border-blue-500/40 text-blue-400')}
                            >
                                <Cpu size={9} />
                                {loading === `whatweb-${url}` ? 'DETECTING...' : 'TECH DETECT'}
                            </button>
                            {!urlIsPrivate && (
                                <button
                                    onClick={() => runAction('nuclei', url, `nuclei-url-${url}`)}
                                    disabled={loading !== null}
                                    className={btnClass('bg-orange-950/40 border-orange-500/40 text-orange-400')}
                                >
                                    <Shield size={9} />
                                    {loading === `nuclei-url-${url}` ? 'SCANNING...' : 'VULN SCAN'}
                                </button>
                            )}
                        </React.Fragment>
                    );
                })}
                {domainList.map(domain => (
                    <React.Fragment key={domain}>
                        <button
                            onClick={() => runAction('harvester', domain, `harvest-${domain}`)}
                            disabled={loading !== null}
                            className={btnClass('bg-purple-950/40 border-purple-500/40 text-purple-400')}
                        >
                            <Globe size={9} />
                            {loading === `harvest-${domain}` ? 'RECON...' : `OSINT ${domain}`}
                        </button>
                        <button
                            onClick={() => runAction('whatweb', `http://${domain}`, `whatweb-${domain}`)}
                            disabled={loading !== null}
                            className={btnClass('bg-blue-950/40 border-blue-500/40 text-blue-400')}
                        >
                            <Cpu size={9} />
                            {loading === `whatweb-${domain}` ? 'DETECTING...' : 'TECH DETECT'}
                        </button>
                        <button
                            onClick={() => runAction('spiderfoot', domain, `sf-${domain}`)}
                            disabled={loading !== null}
                            className={btnClass('bg-rose-950/40 border-rose-500/40 text-rose-400')}
                        >
                            <Search size={9} />
                            {loading === `sf-${domain}` ? 'DEEP RECON...' : 'SPIDERFOOT'}
                        </button>
                    </React.Fragment>
                ))}
                {/* SpiderFoot for standalone IPs (not already shown via domain buttons) */}
                {ipList.filter(ip => !domainList.includes(ip)).map(ip => (
                    <button
                        key={`sf-ip-${ip}`}
                        onClick={() => runAction('spiderfoot', ip, `sf-${ip}`)}
                        disabled={loading !== null}
                        className={btnClass('bg-rose-950/40 border-rose-500/40 text-rose-400')}
                    >
                        <Search size={9} />
                        {loading === `sf-${ip}` ? 'DEEP RECON...' : `SPIDERFOOT ${ip}`}
                    </button>
                ))}
            </div>

            {error && (
                <div className="mt-2 p-2 bg-red-950/30 border border-red-500/30 rounded text-red-400 text-[9px]">
                    ERROR: {error}
                </div>
            )}
            {results && (
                <div className="mt-2 p-2 bg-gray-900/60 border border-gray-700/50 rounded text-[9px] max-h-[250px] overflow-y-auto styled-scrollbar">
                    {results.status === 'running' && (
                        <div className="text-yellow-400 flex items-center gap-1">
                            <span className="animate-pulse">●</span> SCAN IN PROGRESS — {results.job_id}
                        </div>
                    )}
                    {results.status === 'complete' && (
                        <div className="text-green-400">{results.message}</div>
                    )}
                    {results.status === 'timeout' && (
                        <div className="text-yellow-400">{results.message}</div>
                    )}
                    {results.status === 'unavailable' && (
                        <div className="text-red-400">Tool not installed or agent unreachable.</div>
                    )}
                    {results.status === 'ok' && results.data && (() => {
                        const d = results.data;
                        // WhatWeb results — array of {target, plugins, http_status}
                        if (Array.isArray(d) && d.length > 0 && d[0]?.plugins) {
                            return (
                                <div className="flex flex-col gap-2">
                                    {d.map((entry: any, i: number) => (
                                        <div key={i}>
                                            <div className="text-blue-400 font-bold">{entry.target} — HTTP {entry.http_status}</div>
                                            <div className="flex flex-wrap gap-1 mt-1">
                                                {Object.entries(entry.plugins || {}).map(([name, info]: [string, any]) => {
                                                    const ver = info?.version?.[0];
                                                    return (
                                                        <span key={name} className="px-1.5 py-0.5 bg-blue-950/50 border border-blue-800/40 rounded text-blue-300">
                                                            {name}{ver ? ` ${ver}` : ''}
                                                        </span>
                                                    );
                                                })}
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            );
                        }
                        // SpiderFoot results — {target, findings: {emails, hostnames, ips, ...}, summary}
                        if (d.findings !== undefined && d.target !== undefined) {
                            const f = d.findings;
                            const summary = d.summary || {};
                            const totalFindings = Object.values(summary).reduce((a: number, b: any) => a + (b as number), 0);
                            const catColors: Record<string, string> = {
                                emails: 'text-purple-400', hostnames: 'text-cyan-400', ips: 'text-green-400',
                                urls: 'text-blue-400', technologies: 'text-yellow-400', dns_records: 'text-teal-400',
                                ports: 'text-orange-400', vulnerabilities: 'text-red-400', social_media: 'text-pink-400',
                                leaks: 'text-red-500', other: 'text-gray-400',
                            };
                            return (
                                <div className="flex flex-col gap-1.5">
                                    <div className="text-rose-400 font-bold text-[10px]">
                                        SPIDERFOOT — {d.target} — {totalFindings} findings ({d.total_events} events)
                                    </div>
                                    {Object.entries(f).filter(([, items]: [string, any]) => items.length > 0).map(([cat, items]: [string, any]) => (
                                        <div key={cat}>
                                            <span className={`font-bold uppercase ${catColors[cat] || 'text-gray-400'}`}>
                                                {cat.replace(/_/g, ' ')} ({items.length}):
                                            </span>
                                            <div className="ml-2 flex flex-col gap-0.5 mt-0.5">
                                                {items.slice(0, 15).map((item: any, i: number) => (
                                                    <div key={i} className="text-gray-300 flex items-start gap-1">
                                                        <span className="text-gray-600 select-none">›</span>
                                                        <span className="break-all">{item.data}</span>
                                                    </div>
                                                ))}
                                                {items.length > 15 && (
                                                    <div className="text-gray-500 ml-2">...and {items.length - 15} more</div>
                                                )}
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            );
                        }
                        // AutoRecon results — {target, services: [{port, protocol, scan_files, findings}], commands_run, nmap_output}
                        if (d.services !== undefined && d.commands_run !== undefined) {
                            return (
                                <div className="flex flex-col gap-1.5">
                                    <div className="text-amber-400 font-bold text-[10px]">
                                        AUTORECON — {d.target} — {d.services?.length || 0} services, {d.total_files || 0} scan files
                                    </div>
                                    {d.services?.map((svc: any, i: number) => (
                                        <div key={i} className="ml-1">
                                            <span className="text-amber-300 font-bold">{svc.protocol?.toUpperCase()}/{svc.port}</span>
                                            <span className="text-gray-500 ml-1">({svc.scan_files?.length || 0} scans)</span>
                                            {svc.findings?.length > 0 && (
                                                <div className="ml-2 mt-0.5 flex flex-col gap-0.5">
                                                    {svc.findings.slice(0, 10).map((f: string, j: number) => (
                                                        <div key={j} className="text-gray-300 flex items-start gap-1">
                                                            <span className="text-amber-600 select-none">›</span>
                                                            <span className="break-all">{f}</span>
                                                        </div>
                                                    ))}
                                                    {svc.findings.length > 10 && (
                                                        <div className="text-gray-500 ml-2">...and {svc.findings.length - 10} more</div>
                                                    )}
                                                </div>
                                            )}
                                        </div>
                                    ))}
                                    {d.nmap_output && (
                                        <div className="mt-1">
                                            <span className="text-green-400 font-bold">NMAP OUTPUT:</span>
                                            <pre className="text-gray-400 text-[8px] mt-0.5 whitespace-pre-wrap break-all max-h-[120px] overflow-y-auto">
                                                {d.nmap_output.slice(0, 2000)}
                                            </pre>
                                        </div>
                                    )}
                                    {d.commands_run?.length > 0 && (
                                        <div className="text-gray-600 text-[8px] mt-1">
                                            {d.commands_run.length} commands executed
                                        </div>
                                    )}
                                </div>
                            );
                        }
                        // Harvester results — {emails, hosts, ips}
                        if (d.emails !== undefined || d.hosts !== undefined || d.ips !== undefined) {
                            const emails = d.emails || [];
                            const hosts = d.hosts || [];
                            const ips = d.ips || [];
                            if (emails.length === 0 && hosts.length === 0 && ips.length === 0) {
                                return <div className="text-gray-400">No results found for this domain.</div>;
                            }
                            return (
                                <div className="flex flex-col gap-1.5">
                                    {emails.length > 0 && (
                                        <div>
                                            <span className="text-purple-400 font-bold">EMAILS ({emails.length}):</span>
                                            {emails.slice(0, 20).map((e: string, i: number) => (
                                                <div key={i} className="text-gray-300 ml-2">{e}</div>
                                            ))}
                                        </div>
                                    )}
                                    {hosts.length > 0 && (
                                        <div>
                                            <span className="text-green-400 font-bold">HOSTS ({hosts.length}):</span>
                                            {hosts.slice(0, 20).map((h: string, i: number) => (
                                                <div key={i} className="text-gray-300 ml-2">{h}</div>
                                            ))}
                                        </div>
                                    )}
                                    {ips.length > 0 && (
                                        <div>
                                            <span className="text-cyan-400 font-bold">IPs ({ips.length}):</span>
                                            {ips.slice(0, 20).map((ip: string, i: number) => (
                                                <div key={i} className="text-gray-300 ml-2">{ip}</div>
                                            ))}
                                        </div>
                                    )}
                                </div>
                            );
                        }
                        // Generic fallback
                        return (
                            <pre className="text-gray-300 whitespace-pre-wrap break-all">
                                {typeof d === 'string' ? d : JSON.stringify(d, null, 2).slice(0, 2000)}
                            </pre>
                        );
                    })()}
                    {results.status === 'submitted' && (
                        <div className="text-cyan-400">Scan submitted. Enable OSINT layers to view results.</div>
                    )}
                </div>
            )}
        </div>
    );
}

// Helper: find entity by stable ID (icao24/mmsi) instead of array index
function findFlight(arr: any[] | undefined, id: string | number): any {
    if (!arr) return undefined;
    return arr.find((f: any) => f.icao24 === id) ?? arr[id as number];
}
function findShip(arr: any[] | undefined, id: string | number): any {
    if (!arr) return undefined;
    return arr.find((s: any) => (s.mmsi && s.mmsi === id) || (s.imo && s.imo === id)) ?? arr[id as number];
}

function NewsFeedInner({ data, selectedEntity, regionDossier, regionDossierLoading, activeLayers, regionalFocus }: { data: any, selectedEntity?: { type: string, id: string | number, name?: string, callsign?: string, media_url?: string, extra?: any } | null, regionDossier?: any, regionDossierLoading?: boolean, activeLayers?: Record<string, any>, regionalFocus?: { active: boolean, name: string, countryCode: string } | null }) {
    const [isMinimized, setIsMinimized] = useState(false);
    const [socialMinimized, setSocialMinimized] = useState(false);
    const [expandedKeys, setExpandedKeys] = useState<Set<string>>(new Set());
    const itemRefs = useRef<(HTMLDivElement | null)[]>([]);

    // Intentionally omitting map click triggers for expanding
    // as we now show a contextual pop-up on the map directly.

    const toggleExpand = (key: string) => {
        setExpandedKeys(prev => {
            const next = new Set(prev);
            if (next.has(key)) next.delete(key);
            else next.add(key);
            return next;
        });
    }

    const news = data?.news || [];

    // Determine the selected flight's model for Wikipedia thumbnail lookup
    // (must call hook unconditionally — React rules of hooks)
    const selectedFlightModel = (() => {
        if (!selectedEntity) return undefined;
        const { type, id } = selectedEntity;
        let flight: any = null;
        if (type === 'flight') flight = findFlight(data?.commercial_flights, id);
        else if (type === 'private_flight') flight = findFlight(data?.private_flights, id);
        else if (type === 'private_jet') flight = findFlight(data?.private_jets, id);
        else if (type === 'military_flight') flight = findFlight(data?.military_flights, id);
        else if (type === 'tracked_flight') flight = findFlight(data?.tracked_flights, id);
        return flight?.model;
    })();
    const { imgUrl: aircraftImgUrl, wikiUrl: aircraftWikiUrl, loading: aircraftImgLoading } = useAircraftImage(selectedFlightModel);

    // OSINT Deep Search Results
    if (selectedEntity?.type === 'osint_search') {
        const r = selectedEntity.extra || {};
        const results = r.results || r.data?.results || {};
        const locations = r.locations || r.data?.locations || [];
        const queryType = r.type || r.data?.type || 'unknown';
        const summary = r.summary || r.data?.summary || '';
        const toolsRun = r.tools_run || r.data?.tools_run || [];
        const catColors: Record<string, string> = {
            sherlock: 'text-pink-400', h8mail: 'text-red-400', whois: 'text-cyan-400',
            dmitry: 'text-teal-400', harvester: 'text-purple-400', spiderfoot: 'text-rose-400',
            phone: 'text-green-400', general: 'text-amber-400',
            geolocation: 'text-emerald-400', nmap: 'text-green-400', shodan: 'text-red-300',
            subfinder: 'text-sky-400', dig: 'text-indigo-400', dnsrecon: 'text-violet-400',
            emailharvester: 'text-fuchsia-400', phone_lookup: 'text-lime-400',
            phoneinfoga: 'text-green-400', phonenumbers: 'text-emerald-400', numverify: 'text-lime-400',
            public_records: 'text-amber-400', maigret: 'text-pink-400', open_corporates: 'text-blue-300',
            voter_records: 'text-yellow-400', court_records: 'text-red-300', social_profiles: 'text-violet-400',
            holehe: 'text-orange-400', hibp: 'text-red-400',
        };
        const catBg: Record<string, string> = {
            sherlock: 'bg-pink-950/30 border-pink-800/40', h8mail: 'bg-red-950/30 border-red-800/40',
            whois: 'bg-cyan-950/30 border-cyan-800/40', dmitry: 'bg-teal-950/30 border-teal-800/40',
            harvester: 'bg-purple-950/30 border-purple-800/40', spiderfoot: 'bg-rose-950/30 border-rose-800/40',
            phone: 'bg-green-950/30 border-green-800/40', general: 'bg-amber-950/30 border-amber-800/40',
            geolocation: 'bg-emerald-950/30 border-emerald-800/40', nmap: 'bg-green-950/30 border-green-800/40',
            shodan: 'bg-red-950/30 border-red-800/40', subfinder: 'bg-sky-950/30 border-sky-800/40',
            dig: 'bg-indigo-950/30 border-indigo-800/40', dnsrecon: 'bg-violet-950/30 border-violet-800/40',
            emailharvester: 'bg-fuchsia-950/30 border-fuchsia-800/40', phone_lookup: 'bg-lime-950/30 border-lime-800/40',
            phoneinfoga: 'bg-green-950/30 border-green-800/40', phonenumbers: 'bg-emerald-950/30 border-emerald-800/40',
            numverify: 'bg-lime-950/30 border-lime-800/40',
            public_records: 'bg-amber-950/30 border-amber-800/40', maigret: 'bg-pink-950/30 border-pink-800/40',
            open_corporates: 'bg-blue-950/30 border-blue-800/40', voter_records: 'bg-yellow-950/30 border-yellow-800/40',
            court_records: 'bg-red-950/30 border-red-800/40', social_profiles: 'bg-violet-950/30 border-violet-800/40',
            holehe: 'bg-orange-950/30 border-orange-800/40', hibp: 'bg-red-950/30 border-red-800/40',
        };

        return (
            <motion.div
                initial={{ y: 50, opacity: 0 }}
                animate={{ y: 0, opacity: 1 }}
                transition={{ duration: 0.4 }}
                className="w-full bg-black/60 backdrop-blur-md border border-amber-800 rounded-xl flex flex-col z-10 font-mono shadow-[0_4px_30px_rgba(245,158,11,0.2)] pointer-events-auto overflow-hidden flex-shrink-0 max-h-[85vh]"
            >
                {/* Header */}
                <div className="p-4 border-b border-amber-900/50 bg-gradient-to-r from-amber-950/30 to-black/40">
                    <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                            <Fingerprint size={14} className="text-amber-400" />
                            <span className="text-[8px] text-amber-500 tracking-widest">OSINT DEEP SEARCH</span>
                        </div>
                        <div className="flex items-center gap-2">
                            <button
                                onClick={() => {
                                    const blob = new Blob([JSON.stringify(selectedEntity.extra, null, 2)], { type: 'application/json' });
                                    const url = URL.createObjectURL(blob);
                                    const a = document.createElement('a');
                                    a.href = url;
                                    a.download = `osint_${selectedEntity.id}_${Date.now()}.json`;
                                    a.click();
                                    URL.revokeObjectURL(url);
                                }}
                                className="px-2 py-1 rounded border border-amber-700/40 text-[7px] text-amber-500 hover:bg-amber-950/30 tracking-widest font-bold transition-all"
                                title="Export results as JSON"
                            >
                                <Download size={8} className="inline mr-1" />
                                EXPORT JSON
                            </button>
                            <span className="text-[7px] text-gray-600 tracking-wider uppercase">{queryType}</span>
                        </div>
                    </div>
                    <h2 className="text-xs tracking-widest font-bold text-amber-400 mt-1">
                        &quot;{selectedEntity.id}&quot;
                    </h2>
                    {summary && (
                        <p className="text-[9px] text-gray-400 mt-2 leading-relaxed">{summary}</p>
                    )}
                    {toolsRun.length > 0 && (
                        <div className="flex flex-wrap gap-1 mt-2">
                            {toolsRun.map((t: string) => (
                                <span key={t} className={`px-1.5 py-0.5 rounded text-[7px] tracking-wider border ${catBg[t] || 'bg-gray-900/30 border-gray-700/40'} ${catColors[t] || 'text-gray-400'}`}>
                                    {t.toUpperCase()}
                                </span>
                            ))}
                        </div>
                    )}
                </div>

                {/* Locations found */}
                {locations.length > 0 && (
                    <div className="px-4 py-2 border-b border-amber-900/30">
                        <div className="text-[8px] text-gray-500 tracking-widest mb-1">LOCATIONS ({locations.length})</div>
                        {locations.map((loc: any, i: number) => (
                            <div key={i} className="flex items-center gap-2 text-[9px] text-gray-300 py-0.5">
                                <Crosshair size={8} className="text-green-400" />
                                <span>{loc.label || 'Unknown'}</span>
                                <span className="text-gray-600">{loc.lat?.toFixed(3)}, {(loc.lon || loc.lng)?.toFixed(3)}</span>
                                <span className="text-[7px] text-gray-600 ml-auto">{loc.source}</span>
                            </div>
                        ))}
                    </div>
                )}

                {/* Results by tool */}
                <div className="flex-1 overflow-y-auto styled-scrollbar">
                    {Object.entries(results).map(([tool, toolData]: [string, any]) => {
                        if (!toolData || (typeof toolData === 'object' && Object.keys(toolData).length === 0)) return null;
                        // Skip empty results
                        if (toolData.error && !toolData.accounts_found?.length && !toolData.breaches?.length) {
                            return (
                                <div key={tool} className={`px-4 py-2 border-b border-gray-800/30 ${catBg[tool] || ''}`}>
                                    <div className={`text-[8px] tracking-widest font-bold ${catColors[tool] || 'text-gray-400'}`}>{tool.toUpperCase()}</div>
                                    <div className="text-[8px] text-gray-600 mt-0.5">{toolData.error || 'No results'}</div>
                                </div>
                            );
                        }

                        return (
                            <div key={tool} className={`px-4 py-3 border-b border-gray-800/30 ${catBg[tool] || ''}`}>
                                <div className={`text-[8px] tracking-widest font-bold mb-1.5 ${catColors[tool] || 'text-gray-400'}`}>
                                    {tool.toUpperCase()}
                                </div>

                                {/* Sherlock accounts */}
                                {tool === 'sherlock' && toolData.accounts_found && (
                                    <div className="flex flex-col gap-0.5">
                                        <div className="text-[8px] text-pink-300 mb-1">{toolData.total || toolData.accounts_found.length} accounts found</div>
                                        {toolData.accounts_found.slice(0, 30).map((acc: any, i: number) => (
                                            <a key={i} href={acc.url || '#'} target="_blank" rel="noopener noreferrer"
                                               className="text-[8px] text-gray-400 hover:text-pink-300 transition-colors truncate flex items-center gap-1">
                                                <span className="text-pink-600">›</span>
                                                <span className="text-gray-300 w-20 flex-shrink-0">{acc.site || acc.name}</span>
                                                <span className="text-gray-600 truncate">{acc.url}</span>
                                            </a>
                                        ))}
                                        {(toolData.accounts_found.length > 30) && (
                                            <div className="text-[7px] text-gray-600 mt-1">...and {toolData.accounts_found.length - 30} more</div>
                                        )}
                                    </div>
                                )}

                                {/* h8mail breaches */}
                                {tool === 'h8mail' && toolData.breaches && (
                                    <div className="flex flex-col gap-0.5">
                                        <div className="text-[8px] text-red-300 mb-1">{toolData.total || toolData.breaches.length} breach records</div>
                                        {toolData.breaches.slice(0, 20).map((b: any, i: number) => (
                                            <div key={i} className="text-[8px] text-gray-400 flex items-center gap-1">
                                                <span className="text-red-600">›</span>
                                                <span className="break-all">{typeof b === 'string' ? b : b.source || b.breach || JSON.stringify(b)}</span>
                                            </div>
                                        ))}
                                    </div>
                                )}

                                {/* Whois */}
                                {tool === 'whois' && (
                                    <div className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5">
                                        {Object.entries(toolData).filter(([k]) => k !== 'raw' && k !== 'error').map(([k, v]) => (
                                            <React.Fragment key={k}>
                                                <span className="text-[8px] text-cyan-600 uppercase">{k.replace(/_/g, ' ')}</span>
                                                <span className="text-[8px] text-gray-300 break-all">{String(v)}</span>
                                            </React.Fragment>
                                        ))}
                                    </div>
                                )}

                                {/* DMitry */}
                                {tool === 'dmitry' && (
                                    <div className="flex flex-col gap-1">
                                        {toolData.subdomains?.length > 0 && (
                                            <div>
                                                <span className="text-[8px] text-teal-400">SUBDOMAINS ({toolData.subdomains.length}):</span>
                                                {toolData.subdomains.slice(0, 15).map((s: string, i: number) => (
                                                    <div key={i} className="text-[8px] text-gray-400 ml-2">{s}</div>
                                                ))}
                                            </div>
                                        )}
                                        {toolData.emails?.length > 0 && (
                                            <div>
                                                <span className="text-[8px] text-teal-400">EMAILS ({toolData.emails.length}):</span>
                                                {toolData.emails.slice(0, 15).map((e: string, i: number) => (
                                                    <div key={i} className="text-[8px] text-gray-400 ml-2">{e}</div>
                                                ))}
                                            </div>
                                        )}
                                        {Object.entries(toolData).filter(([k]) => !['subdomains', 'emails', 'raw', 'error'].includes(k)).map(([k, v]) => (
                                            typeof v === 'string' || typeof v === 'number' ? (
                                                <div key={k} className="text-[8px]">
                                                    <span className="text-teal-600 uppercase">{k.replace(/_/g, ' ')}: </span>
                                                    <span className="text-gray-300">{String(v)}</span>
                                                </div>
                                            ) : null
                                        ))}
                                    </div>
                                )}

                                {/* Harvester */}
                                {tool === 'harvester' && (
                                    <div className="flex flex-col gap-1">
                                        {toolData.emails?.length > 0 && (
                                            <div>
                                                <span className="text-[8px] text-purple-400">EMAILS ({toolData.emails.length}):</span>
                                                {toolData.emails.slice(0, 15).map((e: string, i: number) => (
                                                    <div key={i} className="text-[8px] text-gray-400 ml-2">{e}</div>
                                                ))}
                                            </div>
                                        )}
                                        {toolData.hosts?.length > 0 && (
                                            <div>
                                                <span className="text-[8px] text-purple-400">HOSTS ({toolData.hosts.length}):</span>
                                                {toolData.hosts.slice(0, 15).map((h: string, i: number) => (
                                                    <div key={i} className="text-[8px] text-gray-400 ml-2">{h}</div>
                                                ))}
                                            </div>
                                        )}
                                        {toolData.ips?.length > 0 && (
                                            <div>
                                                <span className="text-[8px] text-purple-400">IPs ({toolData.ips.length}):</span>
                                                {toolData.ips.slice(0, 15).map((ip: string, i: number) => (
                                                    <div key={i} className="text-[8px] text-gray-400 ml-2">{ip}</div>
                                                ))}
                                            </div>
                                        )}
                                    </div>
                                )}

                                {/* SpiderFoot */}
                                {tool === 'spiderfoot' && toolData.findings && (
                                    <div className="flex flex-col gap-1">
                                        <div className="text-[8px] text-rose-300 mb-0.5">{toolData.total_events || 0} events processed</div>
                                        {Object.entries(toolData.findings).filter(([, items]: [string, any]) => items?.length > 0).map(([cat, items]: [string, any]) => (
                                            <div key={cat}>
                                                <span className="text-[8px] text-rose-400 uppercase">{cat.replace(/_/g, ' ')} ({items.length}):</span>
                                                {items.slice(0, 10).map((item: any, i: number) => (
                                                    <div key={i} className="text-[8px] text-gray-400 ml-2 break-all">{item.data || item}</div>
                                                ))}
                                            </div>
                                        ))}
                                    </div>
                                )}

                                {/* Geolocation */}
                                {tool === 'geolocation' && toolData.city && (
                                    <div className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5">
                                        {['ip', 'country', 'region', 'city', 'isp', 'org', 'asn'].map(k => (
                                            toolData[k] ? (
                                                <React.Fragment key={k}>
                                                    <span className="text-[8px] text-emerald-600 uppercase">{k}</span>
                                                    <span className="text-[8px] text-gray-300">{String(toolData[k])}</span>
                                                </React.Fragment>
                                            ) : null
                                        ))}
                                        {toolData.lat != null && (
                                            <React.Fragment>
                                                <span className="text-[8px] text-emerald-600">COORDS</span>
                                                <span className="text-[8px] text-gray-300">{toolData.lat}, {toolData.lon}</span>
                                            </React.Fragment>
                                        )}
                                    </div>
                                )}

                                {/* Nmap ports */}
                                {tool === 'nmap' && toolData.ports && (
                                    <div className="flex flex-col gap-0.5">
                                        {toolData.os && <div className="text-[8px] text-green-300 mb-1">OS: {toolData.os}</div>}
                                        <div className="text-[8px] text-green-300 mb-0.5">{toolData.total || toolData.ports.length} open ports</div>
                                        {toolData.ports.map((p: any, i: number) => (
                                            <div key={i} className="text-[8px] text-gray-400 flex gap-2">
                                                <span className="text-green-500 w-16 flex-shrink-0 font-bold">{p.port}</span>
                                                <span className="text-gray-500 w-10 flex-shrink-0">{p.state}</span>
                                                <span className="text-gray-300">{p.service}</span>
                                            </div>
                                        ))}
                                    </div>
                                )}

                                {/* Shodan */}
                                {tool === 'shodan' && !toolData.error && (
                                    <div className="flex flex-col gap-0.5">
                                        {toolData.ports && (
                                            <div className="text-[8px]">
                                                <span className="text-red-400">PORTS: </span>
                                                <span className="text-gray-300">{toolData.ports.join(', ')}</span>
                                            </div>
                                        )}
                                        {toolData.vulnerabilities && (
                                            <div className="text-[8px]">
                                                <span className="text-red-400">VULNS: </span>
                                                <span className="text-red-300">{toolData.vulnerabilities.join(', ')}</span>
                                            </div>
                                        )}
                                        {Object.entries(toolData).filter(([k]) => !['ports', 'vulnerabilities', 'raw_lines', 'error'].includes(k)).map(([k, v]) => (
                                            <div key={k} className="text-[8px]">
                                                <span className="text-red-600 uppercase">{k.replace(/_/g, ' ')}: </span>
                                                <span className="text-gray-300">{String(v)}</span>
                                            </div>
                                        ))}
                                    </div>
                                )}

                                {/* Subfinder */}
                                {tool === 'subfinder' && toolData.subdomains && (
                                    <div className="flex flex-col gap-0.5">
                                        <div className="text-[8px] text-sky-300 mb-0.5">{toolData.total || toolData.subdomains.length} subdomains</div>
                                        {toolData.subdomains.slice(0, 30).map((s: string, i: number) => (
                                            <div key={i} className="text-[8px] text-gray-400 ml-1">{s}</div>
                                        ))}
                                        {toolData.subdomains.length > 30 && (
                                            <div className="text-[7px] text-gray-600">...and {toolData.subdomains.length - 30} more</div>
                                        )}
                                    </div>
                                )}

                                {/* Dig DNS records */}
                                {tool === 'dig' && (
                                    <div className="flex flex-col gap-1">
                                        {Object.entries(toolData).filter(([k]) => k.endsWith('_records')).map(([k, records]: [string, any]) => (
                                            <div key={k}>
                                                <span className="text-[8px] text-indigo-400 font-bold uppercase">{k.replace('_records', '').toUpperCase()} ({records.length}):</span>
                                                {records.slice(0, 10).map((r: string, i: number) => (
                                                    <div key={i} className="text-[8px] text-gray-400 ml-2 break-all">{r}</div>
                                                ))}
                                            </div>
                                        ))}
                                    </div>
                                )}

                                {/* DNS Recon */}
                                {tool === 'dnsrecon' && toolData.records && (
                                    <div className="flex flex-col gap-0.5">
                                        <div className="text-[8px] text-violet-300 mb-0.5">{toolData.total || toolData.records.length} records</div>
                                        {toolData.records.slice(0, 20).map((r: any, i: number) => (
                                            <div key={i} className="text-[8px] text-gray-400 flex gap-2">
                                                {r.type && <span className="text-violet-500 w-10 flex-shrink-0">{r.type}</span>}
                                                <span className="text-gray-300 break-all">{r.name || r.raw || ''} {r.address || r.target || ''}</span>
                                            </div>
                                        ))}
                                    </div>
                                )}

                                {/* Email Harvester */}
                                {tool === 'emailharvester' && toolData.emails && (
                                    <div className="flex flex-col gap-0.5">
                                        <div className="text-[8px] text-fuchsia-300 mb-0.5">{toolData.total || toolData.emails.length} emails</div>
                                        {toolData.emails.slice(0, 20).map((e: string, i: number) => (
                                            <div key={i} className="text-[8px] text-gray-400 ml-1">{e}</div>
                                        ))}
                                    </div>
                                )}

                                {/* Phone lookup (legacy) */}
                                {tool === 'phone' && (
                                    <div className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5">
                                        {Object.entries(toolData).filter(([k]) => k !== 'error').map(([k, v]) => (
                                            <React.Fragment key={k}>
                                                <span className="text-[8px] text-green-600 uppercase">{k.replace(/_/g, ' ')}</span>
                                                <span className="text-[8px] text-gray-300 break-all">{String(v)}</span>
                                            </React.Fragment>
                                        ))}
                                    </div>
                                )}

                                {/* PhoneInfoga */}
                                {tool === 'phoneinfoga' && (
                                    <div className="space-y-2">
                                        {toolData.number && (
                                            <div className="text-[9px] text-green-300 font-bold">{toolData.number}</div>
                                        )}
                                        <div className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5">
                                            {['country', 'carrier', 'line_type', 'valid', 'possible',
                                              'local_format', 'international_format', 'country_code',
                                              'region', 'timezone'].map(k => toolData[k] ? (
                                                <React.Fragment key={k}>
                                                    <span className="text-[8px] text-green-600 uppercase">{k.replace(/_/g, ' ')}</span>
                                                    <span className="text-[8px] text-gray-300">{String(toolData[k])}</span>
                                                </React.Fragment>
                                            ) : null)}
                                        </div>
                                        {toolData.scans?.length > 0 && (
                                            <div className="space-y-1 mt-1">
                                                <div className="text-[7px] text-green-600 tracking-widest">SCANNER RESULTS ({toolData.scans.length})</div>
                                                {toolData.scans.map((s: any, i: number) => (
                                                    <div key={i} className="bg-green-950/20 border border-green-800/30 rounded p-1.5">
                                                        <div className="text-[7px] text-green-400 font-bold tracking-wider mb-0.5">{s.scanner?.toUpperCase()}</div>
                                                        <div className="grid grid-cols-[auto_1fr] gap-x-2 gap-y-0.5">
                                                            {Object.entries(s).filter(([k]) => k !== 'scanner').map(([k, v]) => (
                                                                <React.Fragment key={k}>
                                                                    <span className="text-[7px] text-green-700">{k.replace(/_/g, ' ')}</span>
                                                                    <span className="text-[7px] text-gray-400">{String(v)}</span>
                                                                </React.Fragment>
                                                            ))}
                                                        </div>
                                                    </div>
                                                ))}
                                            </div>
                                        )}
                                    </div>
                                )}

                                {/* phonenumbers library */}
                                {tool === 'phonenumbers' && (
                                    <div className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5">
                                        {['number', 'national_format', 'e164', 'valid', 'possible',
                                          'country_code', 'number_type', 'country', 'region_code',
                                          'carrier', 'timezones'].map(k => toolData[k] !== undefined ? (
                                            <React.Fragment key={k}>
                                                <span className="text-[8px] text-emerald-600 uppercase">{k.replace(/_/g, ' ')}</span>
                                                <span className="text-[8px] text-gray-300 break-all">
                                                    {Array.isArray(toolData[k]) ? toolData[k].join(', ') : String(toolData[k])}
                                                </span>
                                            </React.Fragment>
                                        ) : null)}
                                    </div>
                                )}

                                {/* numverify */}
                                {tool === 'numverify' && (
                                    <div className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5">
                                        {Object.entries(toolData).filter(([k]) => k !== 'error' && toolData[k]).map(([k, v]) => (
                                            <React.Fragment key={k}>
                                                <span className="text-[8px] text-lime-600 uppercase">{k.replace(/_/g, ' ')}</span>
                                                <span className="text-[8px] text-gray-300 break-all">{String(v)}</span>
                                            </React.Fragment>
                                        ))}
                                    </div>
                                )}

                                {/* Public records (person search) */}
                                {tool === 'public_records' && (
                                    <div className="space-y-2">
                                        {toolData.addresses?.length > 0 && (
                                            <div>
                                                <div className="text-[7px] text-amber-600 tracking-widest mb-1">ADDRESSES ({toolData.addresses.length})</div>
                                                {toolData.addresses.map((a: any, i: number) => (
                                                    <div key={i} className="text-[8px] text-gray-300 py-0.5 border-b border-gray-800/30">
                                                        {typeof a === 'string' ? a : `${a.address || ''}, ${a.city || ''}, ${a.state || ''} ${a.zip || ''}`}
                                                    </div>
                                                ))}
                                            </div>
                                        )}
                                        {toolData.phones?.length > 0 && (
                                            <div>
                                                <div className="text-[7px] text-amber-600 tracking-widest mb-1">PHONE NUMBERS ({toolData.phones.length})</div>
                                                {toolData.phones.map((p: string, i: number) => (
                                                    <div key={i} className="text-[8px] text-gray-300">{p}</div>
                                                ))}
                                            </div>
                                        )}
                                        {toolData.emails?.length > 0 && (
                                            <div>
                                                <div className="text-[7px] text-amber-600 tracking-widest mb-1">EMAILS ({toolData.emails.length})</div>
                                                {toolData.emails.map((e: string, i: number) => (
                                                    <div key={i} className="text-[8px] text-cyan-400">{e}</div>
                                                ))}
                                            </div>
                                        )}
                                        {toolData.relatives?.length > 0 && (
                                            <div>
                                                <div className="text-[7px] text-amber-600 tracking-widest mb-1">RELATIVES / ASSOCIATES</div>
                                                {toolData.relatives.map((r: string, i: number) => (
                                                    <div key={i} className="text-[8px] text-gray-300">{r}</div>
                                                ))}
                                            </div>
                                        )}
                                        {toolData.npi_records?.length > 0 && (
                                            <div>
                                                <div className="text-[7px] text-amber-600 tracking-widest mb-1">NPI RECORDS ({toolData.npi_records.length})</div>
                                                {toolData.npi_records.map((r: any, i: number) => (
                                                    <div key={i} className="bg-amber-950/20 border border-amber-800/30 rounded p-1.5 mb-1">
                                                        <div className="text-[8px] text-amber-300 font-bold">{r.name}</div>
                                                        {r.credential && <div className="text-[7px] text-gray-400">{r.credential}</div>}
                                                        {r.taxonomy && <div className="text-[7px] text-gray-500">{r.taxonomy}</div>}
                                                        {r.phone && <div className="text-[7px] text-green-400">Tel: {r.phone}</div>}
                                                        {r.addresses?.map((a: any, j: number) => (
                                                            <div key={j} className="text-[7px] text-gray-400 mt-0.5">{a.address}, {a.city}, {a.state} {a.zip}</div>
                                                        ))}
                                                    </div>
                                                ))}
                                            </div>
                                        )}
                                        {toolData.wikipedia && (
                                            <div>
                                                <div className="text-[7px] text-amber-600 tracking-widest mb-1">WIKIPEDIA</div>
                                                <div className="text-[8px] text-gray-300">{toolData.wikipedia.extract}</div>
                                            </div>
                                        )}
                                        {toolData.wikidata?.entities?.length > 0 && (
                                            <div>
                                                <div className="text-[7px] text-amber-600 tracking-widest mb-1">WIKIDATA</div>
                                                {toolData.wikidata.entities.map((e: any, i: number) => (
                                                    <div key={i} className="text-[8px] text-gray-400">{e.label} — {e.description}</div>
                                                ))}
                                            </div>
                                        )}
                                    </div>
                                )}

                                {/* Maigret (social accounts) */}
                                {tool === 'maigret' && (
                                    <div>
                                        {toolData.username_searched && (
                                            <div className="text-[7px] text-pink-600 tracking-wider mb-1">SEARCHED: @{toolData.username_searched}</div>
                                        )}
                                        <div className="text-[7px] text-gray-500 mb-1">{toolData.total || 0} ACCOUNTS FOUND</div>
                                        <div className="space-y-0.5 max-h-[200px] overflow-y-auto">
                                            {(toolData.accounts || []).slice(0, 50).map((a: any, i: number) => (
                                                <div key={i} className="flex items-center gap-2 text-[8px]">
                                                    <span className="text-pink-400 min-w-[80px]">{a.site}</span>
                                                    <a href={a.url} target="_blank" rel="noopener noreferrer" className="text-blue-400 hover:underline truncate">{a.url}</a>
                                                </div>
                                            ))}
                                            {(toolData.total || 0) > 50 && (
                                                <div className="text-[7px] text-gray-600 mt-1">... and {toolData.total - 50} more</div>
                                            )}
                                        </div>
                                    </div>
                                )}

                                {/* OpenCorporates */}
                                {tool === 'open_corporates' && (
                                    <div>
                                        <div className="text-[7px] text-gray-500 mb-1">{toolData.total || 0} CORPORATE OFFICER RECORDS</div>
                                        {(toolData.officers || []).map((o: any, i: number) => (
                                            <div key={i} className="bg-blue-950/20 border border-blue-800/30 rounded p-1.5 mb-1">
                                                <div className="text-[8px] text-blue-300 font-bold">{o.name}</div>
                                                <div className="text-[7px] text-gray-400">{o.position} at {o.company_name}</div>
                                                {o.jurisdiction && <div className="text-[7px] text-gray-500">Jurisdiction: {o.jurisdiction}</div>}
                                                {o.address && <div className="text-[7px] text-gray-500">{o.address}</div>}
                                                {o.start_date && <div className="text-[7px] text-gray-600">{o.start_date} → {o.end_date || 'present'}</div>}
                                            </div>
                                        ))}
                                    </div>
                                )}

                                {/* Court records */}
                                {tool === 'court_records' && (
                                    <div>
                                        <div className="text-[7px] text-gray-500 mb-1">{toolData.total || 0} COURT RECORDS</div>
                                        {(toolData.records || []).map((r: any, i: number) => (
                                            <div key={i} className="bg-red-950/20 border border-red-800/30 rounded p-1.5 mb-1">
                                                <div className="text-[8px] text-red-300 font-bold">{r.name}</div>
                                                {r.court && <div className="text-[7px] text-gray-400">Court: {r.court}</div>}
                                                {r.position && <div className="text-[7px] text-gray-400">Position: {r.position}</div>}
                                                {r.dob && <div className="text-[7px] text-gray-500">DOB: {r.dob}</div>}
                                            </div>
                                        ))}
                                    </div>
                                )}

                                {/* Social profiles */}
                                {tool === 'social_profiles' && (
                                    <div>
                                        <div className="text-[7px] text-violet-600 tracking-widest mb-1">SEARCH LINKS</div>
                                        <div className="space-y-0.5">
                                            {Object.entries(toolData.search_links || {}).map(([platform, url]) => (
                                                <div key={platform} className="flex items-center gap-2 text-[8px]">
                                                    <span className="text-violet-400 min-w-[70px] uppercase">{platform}</span>
                                                    <a href={url as string} target="_blank" rel="noopener noreferrer" className="text-blue-400 hover:underline truncate">{url as string}</a>
                                                </div>
                                            ))}
                                        </div>
                                        {toolData.username_variants?.length > 0 && (
                                            <div className="mt-2">
                                                <div className="text-[7px] text-violet-600 tracking-widest mb-1">USERNAME VARIANTS</div>
                                                <div className="flex flex-wrap gap-1">
                                                    {toolData.username_variants.map((u: string) => (
                                                        <span key={u} className="px-1.5 py-0.5 bg-violet-950/30 border border-violet-800/40 rounded text-[7px] text-violet-300">{u}</span>
                                                    ))}
                                                </div>
                                            </div>
                                        )}
                                    </div>
                                )}

                                {/* Voter records */}
                                {tool === 'voter_records' && toolData.note && (
                                    <div className="text-[8px] text-gray-400">{toolData.note}</div>
                                )}

                                {/* Have I Been Pwned */}
                                {tool === 'hibp' && (
                                    <div className="space-y-2">
                                        {toolData.note && (
                                            <div className="text-[8px] text-yellow-500">{toolData.note}</div>
                                        )}
                                        {toolData.total_breaches > 0 && (
                                            <div>
                                                <div className="text-[7px] text-red-500 tracking-widest mb-1 font-bold">
                                                    FOUND IN {toolData.total_breaches} BREACH{toolData.total_breaches !== 1 ? 'ES' : ''}
                                                </div>
                                                <div className="space-y-1">
                                                    {(toolData.breaches || []).map((b: any, i: number) => (
                                                        <div key={i} className="bg-red-950/20 border border-red-800/30 rounded p-1.5">
                                                            <div className="flex items-center justify-between">
                                                                <span className="text-[8px] text-red-300 font-bold">{b.name}</span>
                                                                <span className="text-[7px] text-gray-500">{b.breach_date}</span>
                                                            </div>
                                                            {b.domain && <div className="text-[7px] text-gray-500">{b.domain}</div>}
                                                            <div className="text-[7px] text-gray-600 mt-0.5">
                                                                {b.pwn_count?.toLocaleString()} accounts · {(b.data_classes || []).slice(0, 5).join(', ')}
                                                            </div>
                                                        </div>
                                                    ))}
                                                </div>
                                            </div>
                                        )}
                                        {toolData.total_breaches === 0 && !toolData.note && (
                                            <div className="text-[8px] text-green-400">No breaches found — clean record</div>
                                        )}
                                        {toolData.total_pastes > 0 && (
                                            <div>
                                                <div className="text-[7px] text-orange-500 tracking-widest mb-1">
                                                    {toolData.total_pastes} PASTE{toolData.total_pastes !== 1 ? 'S' : ''}
                                                </div>
                                                {(toolData.pastes || []).map((p: any, i: number) => (
                                                    <div key={i} className="text-[7px] text-gray-400">
                                                        {p.source}: {p.title || 'Untitled'} ({p.email_count} emails) — {p.date}
                                                    </div>
                                                ))}
                                            </div>
                                        )}
                                    </div>
                                )}

                                {/* Holehe */}
                                {tool === 'holehe' && (
                                    <div>
                                        <div className="text-[7px] text-gray-500 mb-1">REGISTERED ON {toolData.total_registered || toolData.total || 0} / {toolData.total_checked || '?'} SERVICES</div>
                                        <div className="flex flex-wrap gap-1">
                                            {(toolData.registered_on || []).map((s: string) => (
                                                <span key={s} className="px-1.5 py-0.5 bg-orange-950/30 border border-orange-800/40 rounded text-[7px] text-orange-300">{s}</span>
                                            ))}
                                        </div>
                                    </div>
                                )}

                                {/* Generic fallback for any tool not specifically handled */}
                                {!['sherlock', 'h8mail', 'whois', 'dmitry', 'harvester', 'spiderfoot',
                                   'geolocation', 'nmap', 'shodan', 'subfinder', 'dig', 'dnsrecon',
                                   'emailharvester', 'phone', 'phoneinfoga', 'phonenumbers', 'numverify',
                                   'public_records', 'maigret', 'open_corporates', 'court_records',
                                   'social_profiles', 'voter_records', 'holehe', 'hibp'].includes(tool) && (
                                    <pre className="text-[8px] text-gray-400 whitespace-pre-wrap break-all overflow-y-auto">
                                        {typeof toolData === 'string' ? toolData : JSON.stringify(toolData, null, 2).slice(0, 3000)}
                                    </pre>
                                )}
                            </div>
                        );
                    })}
                </div>

                {/* Cross-referenced discoveries */}
                {r.cross_references?.length > 0 && (
                    <div className="px-4 py-3 border-t border-amber-900/30">
                        <div className="text-[8px] text-amber-500 tracking-widest mb-2 font-bold">
                            CROSS-REFERENCED ({r.cross_references.length})
                        </div>
                        <div className="space-y-2">
                            {r.cross_references.map((xref: any, xi: number) => (
                                <div key={xi} className="bg-amber-950/20 border border-amber-800/30 rounded p-2">
                                    <div className="flex items-center gap-2 mb-1">
                                        <span className="text-[7px] px-1.5 py-0.5 rounded bg-amber-900/40 text-amber-400 tracking-wider">
                                            {xref.type?.toUpperCase()}
                                        </span>
                                        <span className="text-[9px] text-amber-300 font-bold font-mono">{xref.query}</span>
                                    </div>
                                    <div className="text-[8px] text-gray-400">
                                        Tools: {xref.tools_run?.join(', ')}
                                    </div>
                                    {/* Show key findings from cross-ref */}
                                    {Object.entries(xref.results || {}).map(([tool, data]: [string, any]) => {
                                        if (!data || data.error || data.skipped) return null;
                                        const highlights: string[] = [];
                                        if (data.total_breaches > 0) highlights.push(`${data.total_breaches} breaches`);
                                        if (data.registered_on?.length) highlights.push(`${data.registered_on.length} services`);
                                        if (data.accounts_found?.length) highlights.push(`${data.accounts_found.length} accounts`);
                                        if (data.valid !== undefined) highlights.push(data.valid ? 'valid' : 'invalid');
                                        if (data.carrier) highlights.push(data.carrier);
                                        if (data.country) highlights.push(data.country);
                                        if (!highlights.length) return null;
                                        return (
                                            <div key={tool} className="text-[7px] text-gray-500 mt-0.5">
                                                <span className="text-gray-400">{tool}:</span> {highlights.join(' · ')}
                                            </div>
                                        );
                                    })}
                                </div>
                            ))}
                        </div>
                    </div>
                )}

            </motion.div>
        );
    }

    // Region Dossier (right-click intelligence)
    if (selectedEntity?.type === 'region_dossier') {
        const d = regionDossier;
        return (
            <motion.div
                initial={{ y: 50, opacity: 0 }}
                animate={{ y: 0, opacity: 1 }}
                transition={{ duration: 0.4 }}
                className="w-full bg-black/60 backdrop-blur-md border border-emerald-800 rounded-xl flex flex-col z-10 font-mono shadow-[0_4px_30px_rgba(0,255,128,0.2)] pointer-events-auto overflow-hidden flex-shrink-0"
            >
                <div className="p-3 border-b border-emerald-500/30 bg-emerald-950/40 flex justify-between items-center">
                    <h2 className="text-xs tracking-widest font-bold text-emerald-400">REGION DOSSIER</h2>
                    <span className="text-[8px] text-gray-500">
                        {selectedEntity.extra?.lat != null && selectedEntity.extra?.lng != null ? `${Number(selectedEntity.extra.lat).toFixed(3)}, ${Number(selectedEntity.extra.lng).toFixed(3)}` : ''}
                    </span>
                </div>
                {regionDossierLoading ? (
                    <div className="p-6 flex items-center justify-center">
                        <span className="text-emerald-400 text-[10px] font-mono animate-pulse tracking-widest">COMPILING INTELLIGENCE...</span>
                    </div>
                ) : d && !d.error ? (
                    <div className="p-3 flex flex-col gap-1.5 max-h-[500px] overflow-y-auto styled-scrollbar text-[10px]">
                        {/* COUNTRY */}
                        <div className="text-[9px] text-emerald-500 tracking-widest font-bold border-b border-emerald-900/50 pb-1">COUNTRY LEVEL {d.country?.flag_emoji || ''}</div>
                        <div className="flex justify-between"><span className="text-gray-500">COUNTRY</span><span className="text-white font-bold">{d.country?.name}</span></div>
                        {d.country?.official_name && d.country.official_name !== d.country.name && (
                            <div className="flex justify-between"><span className="text-gray-500">OFFICIAL</span><span className="text-gray-300 text-right max-w-[180px]">{d.country.official_name}</span></div>
                        )}
                        <div className="flex justify-between"><span className="text-gray-500">LEADER</span><span className="text-emerald-400 font-bold">{d.country?.leader}</span></div>
                        <div className="flex justify-between"><span className="text-gray-500">GOVERNMENT</span><span className="text-white font-bold text-right max-w-[180px]">{d.country?.government_type}</span></div>
                        <div className="flex justify-between"><span className="text-gray-500">POPULATION</span><span className="text-white font-bold">{d.country?.population?.toLocaleString()}</span></div>
                        <div className="flex justify-between"><span className="text-gray-500">CAPITAL</span><span className="text-white font-bold">{d.country?.capital}</span></div>
                        <div className="flex justify-between"><span className="text-gray-500">LANGUAGES</span><span className="text-white text-right max-w-[180px]">{d.country?.languages?.join(', ')}</span></div>
                        {d.country?.currencies?.length > 0 && (
                            <div className="flex justify-between"><span className="text-gray-500">CURRENCY</span><span className="text-white text-right max-w-[180px]">{d.country.currencies.join(', ')}</span></div>
                        )}
                        <div className="flex justify-between"><span className="text-gray-500">REGION</span><span className="text-white">{d.country?.subregion || d.country?.region}</span></div>
                        {d.country?.area_km2 > 0 && (
                            <div className="flex justify-between"><span className="text-gray-500">AREA</span><span className="text-white">{d.country.area_km2.toLocaleString()} km²</span></div>
                        )}

                        {/* LOCAL */}
                        {(d.local?.name || d.local?.state) && (
                            <>
                                <div className="text-[9px] text-emerald-500 tracking-widest font-bold border-b border-emerald-900/50 pb-1 mt-2">LOCAL LEVEL</div>
                                {d.local.name && <div className="flex justify-between"><span className="text-gray-500">LOCALITY</span><span className="text-white font-bold">{d.local.name}</span></div>}
                                {d.local.state && <div className="flex justify-between"><span className="text-gray-500">STATE/PROVINCE</span><span className="text-white font-bold">{d.local.state}</span></div>}
                                {d.local.description && <div className="flex justify-between"><span className="text-gray-500">TYPE</span><span className="text-gray-300">{d.local.description}</span></div>}
                                {d.local.summary && (
                                    <div className="mt-1 p-2 bg-black/60 border border-emerald-800/50 rounded text-[9px] text-gray-300 leading-relaxed">
                                        <span className="text-emerald-400 font-bold">&gt;_ INTEL: </span>
                                        {d.local.summary.length > 500 ? d.local.summary.substring(0, 500) + '...' : d.local.summary}
                                    </div>
                                )}
                            </>
                        )}
                    </div>
                ) : d?.error ? (
                    <div className="p-4 text-gray-400 text-[10px]">{d.error}</div>
                ) : (
                    <div className="p-4 text-red-400 text-[10px]">INTEL UNAVAILABLE</div>
                )}
            </motion.div>
        );
    }

    if (selectedEntity?.type === 'tracked_flight') {
        const flight = findFlight(data?.tracked_flights, selectedEntity.id);
        if (flight) {
            const callsign = flight.callsign || "UNKNOWN";
            const alertColorMap: Record<string, string> = {
                'pink': 'text-pink-400', 'red': 'text-red-400',
                'darkblue': 'text-blue-400', 'white': 'text-white'
            };
            const alertBorderMap: Record<string, string> = {
                'pink': 'border-pink-500/30', 'red': 'border-red-500/30',
                'darkblue': 'border-blue-500/30', 'white': 'border-gray-500/30'
            };
            const alertBgMap: Record<string, string> = {
                'pink': 'bg-pink-950/40', 'red': 'bg-red-950/40',
                'darkblue': 'bg-blue-950/40', 'white': 'bg-gray-900/40'
            };
            const ac = flight.alert_color || 'white';
            const headerColor = alertColorMap[ac] || 'text-white';
            const borderColor = alertBorderMap[ac] || 'border-gray-500/30';
            const bgColor = alertBgMap[ac] || 'bg-gray-900/40';

            return (
                <motion.div
                    initial={{ y: 50, opacity: 0 }}
                    animate={{ y: 0, opacity: 1 }}
                    transition={{ duration: 0.4 }}
                    className={`w-full bg-black/60 backdrop-blur-md border ${ac === 'pink' ? 'border-pink-800' : ac === 'red' ? 'border-red-800' : ac === 'darkblue' ? 'border-blue-800' : 'border-gray-600'} rounded-xl flex flex-col z-10 font-mono shadow-[0_4px_30px_rgba(255,20,147,0.2)] pointer-events-auto overflow-hidden flex-shrink-0`}
                >
                    <div className={`p-3 border-b ${borderColor} ${bgColor} flex justify-between items-center`}>
                        <h2 className={`text-xs tracking-widest font-bold ${headerColor} flex items-center gap-2`}>
                            ⚠ TRACKED AIRCRAFT — {flight.alert_category || "ALERT"}
                        </h2>
                        <span className="text-[10px] text-gray-500 font-mono">TRK: {callsign}</span>
                    </div>

                    <div className="p-4 flex flex-col gap-3">
                        <div className="flex justify-between items-center border-b border-gray-800 pb-2">
                            <span className="text-gray-500 text-[10px]">OPERATOR</span>
                            {flight.alert_operator && flight.alert_operator !== "UNKNOWN" ? (
                                <a
                                    href={`https://en.wikipedia.org/wiki/${encodeURIComponent(flight.alert_operator.replace(/ /g, '_'))}`}
                                    target="_blank"
                                    rel="noreferrer"
                                    className={`text-xs font-bold underline ${headerColor} hover:opacity-80 transition-opacity`}
                                    title={`Search Wikipedia for ${flight.alert_operator}`}
                                >
                                    {flight.alert_operator}
                                </a>
                            ) : (
                                <span className={`text-xs font-bold ${headerColor}`}>UNKNOWN</span>
                            )}
                        </div>
                        {/* Owner/Operator Wikipedia photo */}
                        {flight.alert_operator && flight.alert_operator !== "UNKNOWN" && (
                            <div className="border-b border-gray-800 pb-2">
                                <WikiImage
                                    wikiUrl={`https://en.wikipedia.org/wiki/${encodeURIComponent(flight.alert_operator.replace(/ /g, '_'))}`}
                                    label={flight.alert_operator}
                                    maxH="max-h-36"
                                    accent={ac === 'pink' ? 'hover:border-pink-500/50' : ac === 'red' ? 'hover:border-red-500/50' : 'hover:border-cyan-500/50'}
                                />
                            </div>
                        )}
                        {/* Aircraft model Wikipedia photo */}
                        {aircraftImgUrl && (
                            <div className="border-b border-gray-800 pb-2">
                                <a href={aircraftWikiUrl || '#'} target="_blank" rel="noopener noreferrer" className="block">
                                    <img
                                        src={aircraftImgUrl}
                                        alt={AIRCRAFT_WIKI[flight.model] || flight.model}
                                        className={`w-full h-auto max-h-28 object-cover rounded border border-gray-700/50 ${ac === 'pink' ? 'hover:border-pink-500/50' : 'hover:border-cyan-500/50'} transition-colors`}
                                    />
                                </a>
                                {aircraftWikiUrl && (
                                    <a href={aircraftWikiUrl} target="_blank" rel="noopener noreferrer"
                                        className="text-[10px] text-cyan-400 hover:text-cyan-300 underline mt-1 inline-block">
                                        📖 {AIRCRAFT_WIKI[flight.model] || flight.model} — Wikipedia →
                                    </a>
                                )}
                            </div>
                        )}
                        <div className="flex justify-between items-center border-b border-gray-800 pb-2">
                            <span className="text-gray-500 text-[10px]">CATEGORY</span>
                            <span className={`text-xs font-bold ${headerColor}`}>{flight.alert_category || "N/A"}</span>
                        </div>
                        <div className="flex justify-between items-center border-b border-gray-800 pb-2">
                            <span className="text-gray-500 text-[10px]">AIRCRAFT</span>
                            <span className="text-white text-xs font-bold">{flight.alert_type || flight.model || "UNKNOWN"}</span>
                        </div>
                        <div className="flex justify-between items-center border-b border-gray-800 pb-2">
                            <span className="text-gray-500 text-[10px]">REGISTRATION</span>
                            <span className="text-white text-xs font-bold">{flight.registration || "N/A"}</span>
                        </div>
                        {flight.alert_tag1 && (
                            <div className="flex justify-between items-center border-b border-gray-800 pb-2">
                                <span className="text-gray-500 text-[10px]">INTEL TAG</span>
                                <span className={`text-xs font-bold ${headerColor}`}>{flight.alert_tag1}</span>
                            </div>
                        )}
                        {flight.alert_tag2 && (
                            <div className="flex justify-between items-center border-b border-gray-800 pb-2">
                                <span className="text-gray-500 text-[10px]">SECONDARY</span>
                                <span className="text-white text-xs font-bold">{flight.alert_tag2}</span>
                            </div>
                        )}
                        {flight.alert_tag3 && (
                            <div className="flex justify-between items-center border-b border-gray-800 pb-2">
                                <span className="text-gray-500 text-[10px]">DETAIL</span>
                                <span className="text-gray-400 text-xs">{flight.alert_tag3}</span>
                            </div>
                        )}
                        <div className="flex justify-between items-center border-b border-gray-800 pb-2">
                            <span className="text-gray-500 text-[10px]">ALTITUDE</span>
                            <span className="text-white text-xs font-bold">{(Math.round((flight.alt || 0) / 0.3048)).toLocaleString()} ft</span>
                        </div>
                        <div className="flex justify-between items-center border-b border-gray-800 pb-2">
                            <span className="text-gray-500 text-[10px]">GROUND SPEED</span>
                            <span className="text-white text-xs font-bold">{flight.speed_knots ? `${flight.speed_knots} kts` : 'N/A'}</span>
                        </div>
                        <div className="flex justify-between items-center border-b border-gray-800 pb-2">
                            <span className="text-gray-500 text-[10px]">HEADING</span>
                            <span className="text-white text-xs font-bold">{Math.round(flight.heading || 0)}°</span>
                        </div>
                        {flight.squawk && (
                            <div className="flex justify-between items-center border-b border-gray-800 pb-2">
                                <span className="text-gray-500 text-[10px]">SQUAWK</span>
                                <span className={`text-xs font-bold ${flight.squawk === '7700' ? 'text-red-400 animate-pulse' : flight.squawk === '7600' ? 'text-yellow-400' : 'text-white'}`}>{flight.squawk}{flight.squawk === '7700' ? ' ⚠ EMERGENCY' : flight.squawk === '7600' ? ' COMMS LOST' : ''}</span>
                            </div>
                        )}
                        {flight.alert_link && (
                            <div className="flex justify-between items-center border-b border-gray-800 pb-2">
                                <span className="text-gray-500 text-[10px]">REFERENCE</span>
                                <a href={flight.alert_link} target="_blank" rel="noreferrer" className={`text-xs font-bold underline ${headerColor} hover:opacity-80`}>
                                    View Intel Source
                                </a>
                            </div>
                        )}
                        {flight.icao24 && (
                            <div className="flex justify-between items-center border-b border-gray-800 pb-2">
                                <span className="text-gray-500 text-[10px]">FLIGHT RECORD</span>
                                <a href={`https://adsb.lol/?icao=${flight.icao24}`} target="_blank" rel="noreferrer" className={`${headerColor} hover:opacity-80 text-xs font-bold underline`}>
                                    View History Log
                                </a>
                            </div>
                        )}
                    </div>
                </motion.div>
            )
        }
    }

    if (selectedEntity?.type === 'flight' || selectedEntity?.type === 'military_flight' || selectedEntity?.type === 'private_flight' || selectedEntity?.type === 'private_jet') {
        const flightsList = selectedEntity.type === 'flight' ? data?.commercial_flights
            : selectedEntity.type === 'private_flight' ? data?.private_flights
                : selectedEntity.type === 'private_jet' ? data?.private_jets
                    : data?.military_flights;
        const flight = findFlight(flightsList, selectedEntity.id);

        if (flight) {
            const callsign = flight.callsign || "UNKNOWN";
            let airline = "UNKNOWN";

            if (selectedEntity.type === 'military_flight') {
                airline = "MILITARY ASSET";
            } else if (selectedEntity.type === 'private_jet') {
                airline = "PRIVATE JET";
            } else if (selectedEntity.type === 'private_flight') {
                airline = "PRIVATE / GA";
            } else if (flight.airline_code) {
                // Use the airline code resolved from adsb.lol routeset API
                const codeMap: Record<string, string> = {
                    "UAL": "UNITED AIRLINES", "DAL": "DELTA AIR LINES", "SWA": "SOUTHWEST AIRLINES",
                    "AAL": "AMERICAN AIRLINES", "BAW": "BRITISH AIRWAYS", "AFR": "AIR FRANCE",
                    "JBU": "JETBLUE AIRWAYS", "NKS": "SPIRIT AIRLINES", "THY": "TURKISH AIRLINES",
                    "UAE": "EMIRATES", "QFA": "QANTAS", "ACA": "AIR CANADA",
                    "FFT": "FRONTIER AIRLINES", "WJA": "WESTJET", "RPA": "REPUBLIC AIRWAYS",
                    "SKW": "SKYWEST AIRLINES", "ENY": "ENVOY AIR", "ASA": "ALASKA AIRLINES",
                    "HAL": "HAWAIIAN AIRLINES", "DLH": "LUFTHANSA", "KLM": "KLM",
                    "EZY": "EASYJET", "RYR": "RYANAIR", "SIA": "SINGAPORE AIRLINES",
                    "CPA": "CATHAY PACIFIC", "ANA": "ALL NIPPON AIRWAYS", "JAL": "JAPAN AIRLINES",
                    "QTR": "QATAR AIRWAYS", "ETD": "ETIHAD AIRWAYS", "SAS": "SAS SCANDINAVIAN"
                };
                airline = codeMap[flight.airline_code] || flight.airline_code;
            } else if (callsign !== "UNKNOWN") {
                airline = "COMMERCIAL FLIGHT";
            }

            return (
                <motion.div
                    initial={{ y: 50, opacity: 0 }}
                    animate={{ y: 0, opacity: 1 }}
                    transition={{ duration: 0.4 }}
                    className="w-full bg-black/60 backdrop-blur-md border border-cyan-800 rounded-xl flex flex-col z-10 font-mono shadow-[0_4px_30px_rgba(0,128,255,0.2)] pointer-events-auto overflow-hidden flex-shrink-0"
                >
                    <div className="p-3 border-b border-cyan-500/30 bg-cyan-950/40 flex justify-between items-center">
                        <h2 className={`text-xs tracking-widest font-bold ${selectedEntity.type === 'military_flight' ? 'text-red-400' : selectedEntity.type === 'private_flight' ? 'text-orange-400' : selectedEntity.type === 'private_jet' ? 'text-purple-400' : 'text-cyan-400'} flex items-center gap-2`}>
                            {selectedEntity.type === 'military_flight' ? "MILITARY BOGEY INTERCEPT" : selectedEntity.type === 'private_flight' ? "PRIVATE TRANSPONDER" : selectedEntity.type === 'private_jet' ? "PRIVATE JET TRANSPONDER" : "COMMERCIAL TRANSPONDER"}
                        </h2>
                        <span className="text-[10px] text-gray-500 font-mono">TRK: {callsign}</span>
                    </div>

                    <div className="p-4 flex flex-col gap-3">
                        <div className="flex justify-between items-center border-b border-gray-800 pb-2">
                            <span className="text-gray-500 text-[10px]">OPERATOR</span>
                            <span className="text-white text-xs font-bold">{airline}</span>
                        </div>
                        <div className="flex justify-between items-center border-b border-gray-800 pb-2">
                            <span className="text-gray-500 text-[10px]">REGISTRATION</span>
                            <span className="text-white text-xs font-bold">{flight.registration || "N/A"}</span>
                        </div>
                        <div className="flex justify-between items-center border-b border-gray-800 pb-2">
                            <span className="text-gray-500 text-[10px]">AIRCRAFT MODEL</span>
                            <span className="text-white text-xs font-bold">{flight.model || "UNKNOWN"}</span>
                        </div>
                        {/* Aircraft photo + Wikipedia link */}
                        {(aircraftImgUrl || aircraftImgLoading || aircraftWikiUrl) && (
                            <div className="border-b border-gray-800 pb-3">
                                {aircraftImgLoading && (
                                    <div className="w-full h-24 rounded bg-gray-800/60 animate-pulse" />
                                )}
                                {aircraftImgUrl && (
                                    <a href={aircraftWikiUrl || '#'} target="_blank" rel="noopener noreferrer" className="block">
                                        <img
                                            src={aircraftImgUrl}
                                            alt={AIRCRAFT_WIKI[flight.model] || flight.model}
                                            className="w-full h-auto max-h-32 object-cover rounded border border-gray-700/50 hover:border-cyan-500/50 transition-colors"
                                            style={{ imageRendering: 'auto' }}
                                        />
                                    </a>
                                )}
                                {aircraftWikiUrl && (
                                    <a href={aircraftWikiUrl} target="_blank" rel="noopener noreferrer"
                                        className="text-[10px] text-cyan-400 hover:text-cyan-300 underline mt-1 inline-block">
                                        📖 {AIRCRAFT_WIKI[flight.model] || flight.model} — Wikipedia →
                                    </a>
                                )}
                            </div>
                        )}
                        <div className="flex justify-between items-center border-b border-gray-800 pb-2">
                            <span className="text-gray-500 text-[10px]">ALTITUDE</span>
                            <span className="text-white text-xs font-bold">{(Math.round((flight.alt || 0) / 0.3048)).toLocaleString()} ft</span>
                        </div>
                        <div className="flex justify-between items-center border-b border-gray-800 pb-2">
                            <span className="text-gray-500 text-[10px]">GROUND SPEED</span>
                            <span className="text-white text-xs font-bold">{flight.speed_knots ? `${flight.speed_knots} kts` : 'N/A'}</span>
                        </div>
                        <div className="flex justify-between items-center border-b border-gray-800 pb-2">
                            <span className="text-gray-500 text-[10px]">HEADING</span>
                            <span className="text-white text-xs font-bold">{Math.round(flight.heading || 0)}°</span>
                        </div>
                        {flight.squawk && (
                            <div className="flex justify-between items-center border-b border-gray-800 pb-2">
                                <span className="text-gray-500 text-[10px]">SQUAWK</span>
                                <span className={`text-xs font-bold ${flight.squawk === '7700' ? 'text-red-400 animate-pulse' : flight.squawk === '7600' ? 'text-yellow-400' : 'text-white'}`}>{flight.squawk}{flight.squawk === '7700' ? ' ⚠ EMERGENCY' : flight.squawk === '7600' ? ' COMMS LOST' : ''}</span>
                            </div>
                        )}
                        <div className="flex justify-between items-center border-b border-gray-800 pb-2">
                            <span className="text-gray-500 text-[10px]">ROUTE</span>
                            <span className="text-cyan-400 text-xs font-bold">{flight.origin_name !== "UNKNOWN" ? `[${flight.origin_name}] → [${flight.dest_name}]` : "UNKNOWN"}</span>
                        </div>
                        {flight.icao24 && (
                            <div className="flex justify-between items-center border-b border-gray-800 pb-2">
                                <span className="text-gray-500 text-[10px]">FLIGHT RECORD</span>
                                <a href={`https://adsb.lol/?icao=${flight.icao24}`} target="_blank" rel="noreferrer" className="text-cyan-400 hover:text-cyan-300 text-xs font-bold underline">
                                    View History Log
                                </a>
                            </div>
                        )}
                    </div>
                </motion.div>
            )
        }
    }

    if (selectedEntity?.type === 'ship') {
        const ship = findShip(data?.ships, selectedEntity.id);
        if (ship) {
            const vesselTypeLabels: Record<string, string> = {
                'tanker': 'TANKER',
                'cargo': 'CARGO VESSEL',
                'passenger': 'PASSENGER / CRUISE',
                'yacht': 'PRIVATE YACHT',
                'military_vessel': 'MILITARY VESSEL',
                'carrier': 'AIRCRAFT CARRIER',
            };
            const typeLabel = vesselTypeLabels[ship.type] || ship.type?.toUpperCase() || 'VESSEL';

            const headerColorMap: Record<string, string> = {
                'tanker': 'text-red-400',
                'cargo': 'text-red-400',
                'passenger': 'text-white',
                'yacht': 'text-blue-400',
                'military_vessel': 'text-yellow-400',
                'carrier': 'text-orange-400',
            };
            const headerColor = headerColorMap[ship.type] || 'text-gray-400';

            const headerTitleMap: Record<string, string> = {
                'tanker': 'AIS TANKER INTERCEPT',
                'cargo': 'AIS CARGO INTERCEPT',
                'passenger': 'AIS PASSENGER VESSEL',
                'yacht': 'AIS YACHT SIGNAL',
                'military_vessel': 'AIS MILITARY VESSEL',
                'carrier': 'CARRIER STRIKE GROUP',
            };
            const headerTitle = headerTitleMap[ship.type] || 'AIS VESSEL SIGNAL';

            return (
                <motion.div
                    initial={{ y: 50, opacity: 0 }}
                    animate={{ y: 0, opacity: 1 }}
                    transition={{ duration: 0.4 }}
                    className="w-full bg-black/60 backdrop-blur-md border border-cyan-800 rounded-xl flex flex-col z-10 font-mono shadow-[0_4px_30px_rgba(0,128,255,0.2)] pointer-events-auto overflow-hidden flex-shrink-0"
                >
                    <div className="p-3 border-b border-cyan-500/30 bg-cyan-950/40 flex justify-between items-center">
                        <h2 className={`text-xs tracking-widest font-bold ${headerColor} flex items-center gap-2`}>
                            {headerTitle}
                        </h2>
                        <span className="text-[10px] text-gray-500 font-mono">MMSI: {ship.mmsi || 'N/A'}</span>
                    </div>

                    <div className="p-4 flex flex-col gap-3">
                        <div className="flex justify-between items-center border-b border-gray-800 pb-2">
                            <span className="text-gray-500 text-[10px]">VESSEL NAME</span>
                            <span className="text-white text-xs font-bold text-right ml-4">{ship.name || 'UNKNOWN'}</span>
                        </div>
                        <div className="flex justify-between items-center border-b border-gray-800 pb-2">
                            <span className="text-gray-500 text-[10px]">VESSEL TYPE</span>
                            <span className={`text-xs font-bold ${headerColor}`}>{typeLabel}</span>
                        </div>
                        <div className="flex justify-between items-center border-b border-gray-800 pb-2">
                            <span className="text-gray-500 text-[10px]">FLAG STATE</span>
                            <span className="text-white text-xs font-bold">{ship.country || 'UNKNOWN'}</span>
                        </div>
                        {ship.callsign && (
                            <div className="flex justify-between items-center border-b border-gray-800 pb-2">
                                <span className="text-gray-500 text-[10px]">CALLSIGN</span>
                                <span className="text-white text-xs font-bold">{ship.callsign}</span>
                            </div>
                        )}
                        {ship.imo > 0 && (
                            <div className="flex justify-between items-center border-b border-gray-800 pb-2">
                                <span className="text-gray-500 text-[10px]">IMO NUMBER</span>
                                <span className="text-white text-xs font-bold">{ship.imo}</span>
                            </div>
                        )}
                        <div className="flex justify-between items-center border-b border-gray-800 pb-2">
                            <span className="text-gray-500 text-[10px]">DESTINATION</span>
                            <span className={`text-xs font-bold ${ship.destination && ship.destination !== 'UNKNOWN' ? 'text-cyan-400' : 'text-orange-400'}`}>{ship.destination || 'UNKNOWN'}</span>
                        </div>
                        <div className="flex justify-between items-center border-b border-gray-800 pb-2">
                            <span className="text-gray-500 text-[10px]">SPEED (SOG)</span>
                            <span className="text-white text-xs font-bold">{ship.type === 'carrier' ? 'UNKNOWN' : `${ship.sog || 0} kts`}</span>
                        </div>
                        <div className="flex justify-between items-center border-b border-gray-800 pb-2">
                            <span className="text-gray-500 text-[10px]">COURSE (COG)</span>
                            <span className="text-white text-xs font-bold">{ship.type === 'carrier' ? 'UNKNOWN' : `${Math.round(ship.cog || 0)}°`}</span>
                        </div>
                        {ship.mmsi && (
                            <div className="flex justify-between items-center border-b border-gray-800 pb-2">
                                <span className="text-gray-500 text-[10px]">VESSEL RECORD</span>
                                <a href={`https://www.marinetraffic.com/en/ais/details/ships/mmsi:${ship.mmsi}`} target="_blank" rel="noreferrer" className="text-cyan-400 hover:text-cyan-300 text-xs font-bold underline">
                                    View on MarineTraffic
                                </a>
                            </div>
                        )}
                        {/* Ship/Carrier Wikipedia photo */}
                        {(ship.wiki || VESSEL_TYPE_WIKI[ship.type]) && (
                            <div className="border-t border-gray-800 pt-2">
                                <WikiImage
                                    wikiUrl={ship.wiki || VESSEL_TYPE_WIKI[ship.type]}
                                    label={ship.type === 'carrier' ? ship.name : typeLabel}
                                    maxH="max-h-32"
                                    accent={ship.type === 'carrier' ? 'hover:border-orange-500/50' : 'hover:border-cyan-500/50'}
                                />
                            </div>
                        )}
                    </div>
                </motion.div>
            )
        }
    }

    if (selectedEntity?.type === 'gdelt') {
        const gdeltItem = data?.gdelt?.[selectedEntity.id as number];
        if (gdeltItem && gdeltItem.properties) {
            const props = gdeltItem.properties;
            return (
                <motion.div
                    initial={{ y: 50, opacity: 0 }}
                    animate={{ y: 0, opacity: 1 }}
                    transition={{ duration: 0.4 }}
                    className="w-full bg-black/60 backdrop-blur-md border border-orange-800 rounded-xl flex flex-col z-10 font-mono shadow-[0_4px_30px_rgba(255,140,0,0.2)] pointer-events-auto overflow-hidden flex-shrink-0"
                >
                    <div className="p-3 border-b border-orange-500/30 bg-orange-950/40 flex justify-between items-center">
                        <h2 className="text-xs tracking-widest font-bold text-orange-400 flex items-center gap-2">
                            <AlertTriangle size={14} className="text-orange-400" /> MILITARY INCIDENT CLUSTER
                        </h2>
                        <span className="text-[10px] text-gray-500 font-mono">ID: {selectedEntity.id}</span>
                    </div>

                    <div className="p-4 flex flex-col gap-3">
                        <div className="flex justify-between items-center border-b border-gray-800 pb-2">
                            <span className="text-gray-500 text-[10px]">LOCATION</span>
                            <span className="text-white text-xs font-bold text-right ml-4">{props.name || 'UNKNOWN REGION'}</span>
                        </div>
                        <div className="flex justify-between items-center border-b border-gray-800 pb-2">
                            <span className="text-gray-500 text-[10px]">ARTICLE COUNT</span>
                            <span className="text-orange-400 text-xs font-bold">{props.count || 1}</span>
                        </div>
                        <div className="flex flex-col gap-2 mt-2">
                            <span className="text-gray-500 text-[10px]">LATEST REPORTS:</span>
                            <div
                                className="text-white text-xs whitespace-normal [&_a]:text-orange-400 [&_a]:underline hover:[&_a]:text-orange-300 [&_br]:mb-2"
                                dangerouslySetInnerHTML={{ __html: (props.html || 'No articles available.').replace(/<script[\s\S]*?<\/script>/gi, '').replace(/on\w+="[^"]*"/gi, '').replace(/on\w+='[^']*'/gi, '') }}
                            />
                        </div>
                    </div>
                </motion.div>
            )
        }
    }

    if (selectedEntity?.type === 'liveuamap') {
        const item = data?.liveuamap?.find((l: any) => String(l.id) === String(selectedEntity.id));
        if (item) {
            return (
                <motion.div
                    initial={{ y: 50, opacity: 0 }}
                    animate={{ y: 0, opacity: 1 }}
                    transition={{ duration: 0.4 }}
                    className="w-full bg-black/60 backdrop-blur-md border border-yellow-800 rounded-xl flex flex-col z-10 font-mono shadow-[0_4px_30px_rgba(255,255,0,0.2)] pointer-events-auto overflow-hidden flex-shrink-0"
                >
                    <div className="p-3 border-b border-yellow-500/30 bg-yellow-950/40 flex justify-between items-center">
                        <h2 className="text-xs tracking-widest font-bold text-yellow-400 flex items-center gap-2">
                            <AlertTriangle size={14} className="text-yellow-400" /> REGIONAL TACTICAL EVENT
                        </h2>
                        <span className="text-[10px] text-gray-500 font-mono">ID: {item.id}</span>
                    </div>

                    <div className="p-4 flex flex-col gap-3">
                        <div className="flex justify-between items-center border-b border-gray-800 pb-2">
                            <span className="text-gray-500 text-[10px]">REGION</span>
                            <span className="text-white text-xs font-bold text-right ml-4">{item.region || 'UNKNOWN'}</span>
                        </div>
                        <div className="flex flex-col gap-2 border-b border-gray-800 pb-2">
                            <span className="text-gray-500 text-[10px]">DESCRIPTION</span>
                            <span className="text-yellow-400 text-xs font-bold leading-tight">{item.title}</span>
                        </div>
                        <div className="flex justify-between items-center border-b border-gray-800 pb-2 mt-2">
                            <span className="text-gray-500 text-[10px]">REPORTED TIME</span>
                            <span className="text-white text-xs font-bold">{item.timestamp || 'UNKNOWN'}</span>
                        </div>
                        {item.link && (
                            <div className="flex justify-between items-center pb-2 mt-2">
                                <span className="text-gray-500 text-[10px]">SOURCE</span>
                                <a href={item.link} target="_blank" rel="noreferrer" className="text-yellow-400 hover:text-yellow-300 text-xs font-bold underline">
                                    View Liveuamap Report
                                </a>
                            </div>
                        )}
                    </div>
                </motion.div>
            )
        }
    }

    if (selectedEntity?.type === 'news') {
        const item = data?.news?.[selectedEntity.id as number];
        if (item) {
            return (
                <motion.div
                    initial={{ y: 50, opacity: 0 }}
                    animate={{ y: 0, opacity: 1 }}
                    transition={{ duration: 0.4 }}
                    className="w-full bg-black/60 backdrop-blur-md border border-red-800 rounded-xl flex flex-col z-10 font-mono shadow-[0_4px_30px_rgba(255,0,0,0.2)] pointer-events-auto overflow-hidden flex-shrink-0"
                >
                    <div className="p-3 border-b border-red-500/30 bg-red-950/40 flex justify-between items-center">
                        <h2 className="text-xs tracking-widest font-bold text-red-400 flex items-center gap-2">
                            <AlertTriangle size={14} className="text-red-400" /> THREAT INTERCEPT
                        </h2>
                        <span className="text-[10px] text-gray-500 font-mono">LVL: {item.risk_score}/10</span>
                    </div>

                    <div className="p-4 flex flex-col gap-3">
                        <div className="flex justify-between items-center border-b border-gray-800 pb-2">
                            <span className="text-gray-500 text-[10px]">SOURCE</span>
                            <span className="text-white text-xs font-bold text-right ml-4">{item.source || 'UNKNOWN'}</span>
                        </div>
                        <div className="flex flex-col gap-2 border-b border-gray-800 pb-2">
                            <span className="text-gray-500 text-[10px]">HEADLINE</span>
                            <span className="text-red-400 text-xs font-bold leading-tight">{item.title}</span>
                        </div>
                        {item.machine_assessment && (
                            <div className="mt-2 p-2 bg-black/60 border border-cyan-800/50 rounded-sm text-[9px] text-cyan-400 font-mono leading-tight relative overflow-hidden shadow-[inset_0_0_10px_rgba(0,255,255,0.05)]">
                                <div className="absolute top-0 left-0 w-[2px] h-full bg-cyan-500 animate-pulse"></div>
                                <span className="font-bold text-white">&gt;_ SYS.ANALYSIS: </span>
                                <span className="text-cyan-300 opacity-90">{item.machine_assessment}</span>
                            </div>
                        )}
                        {item.link && (
                            <div className="flex justify-between items-center pb-2 mt-2">
                                <span className="text-gray-500 text-[10px]">REFERENCE</span>
                                <a href={item.link} target="_blank" rel="noreferrer" className="text-red-400 hover:text-red-300 text-xs font-bold underline">
                                    View Source Article
                                </a>
                            </div>
                        )}
                    </div>
                </motion.div>
            )
        }
    }

    if (selectedEntity?.type === 'airport') {
        const apt = data?.airports?.find((a: any) => String(a.id) === String(selectedEntity.id));
        if (apt) {
            return (
                <motion.div
                    initial={{ y: 50, opacity: 0 }}
                    animate={{ y: 0, opacity: 1 }}
                    transition={{ duration: 0.4 }}
                    className="w-full bg-black/60 backdrop-blur-md border border-cyan-800 rounded-xl flex flex-col z-10 font-mono shadow-[0_4px_30px_rgba(0,128,255,0.2)] pointer-events-auto overflow-hidden flex-shrink-0"
                >
                    <div className="p-3 border-b border-cyan-500/30 bg-cyan-950/40 flex justify-between items-center">
                        <h2 className="text-xs tracking-widest font-bold text-cyan-400 flex items-center gap-2">
                            AERONAUTICAL HUB
                        </h2>
                        <span className="text-[10px] text-gray-500 font-mono">IATA: {apt.iata}</span>
                    </div>

                    <div className="p-4 flex flex-col gap-3">
                        <div className="flex justify-between items-center border-b border-gray-800 pb-2">
                            <span className="text-gray-500 text-[10px]">FACILITY NAME</span>
                            <span className="text-white text-[10px] font-bold text-right ml-4 break-words">{apt.name}</span>
                        </div>
                        <div className="flex justify-between items-center border-b border-gray-800 pb-2">
                            <span className="text-gray-500 text-[10px]">COORDINATES</span>
                            <span className="text-white text-xs font-bold">{apt.lat.toFixed(4)}, {apt.lng.toFixed(4)}</span>
                        </div>
                        <div className="flex justify-between items-center border-b border-gray-800 pb-2">
                            <span className="text-gray-500 text-[10px]">STATUS</span>
                            <span className="text-green-400 animate-pulse text-xs font-bold">OPERATIONAL</span>
                        </div>
                    </div>
                </motion.div>
            )
        }
    }

    if (selectedEntity?.type === 'cctv') {
        return (
            <motion.div
                initial={{ y: 50, opacity: 0 }}
                animate={{ y: 0, opacity: 1 }}
                transition={{ duration: 0.4 }}
                className="w-full bg-black/60 backdrop-blur-md border border-cyan-800 rounded-xl flex flex-col z-10 font-mono shadow-[0_4px_30px_rgba(0,128,255,0.2)] pointer-events-auto overflow-hidden flex-shrink-0"
            >
                <div className="p-3 border-b border-cyan-500/30 bg-cyan-950/40 flex justify-between items-center">
                    <h2 className="text-xs tracking-widest font-bold text-cyan-400 flex items-center gap-2">
                        <AlertTriangle size={14} className="text-red-400" /> {selectedEntity.extra?.last_updated
                            ? new Date(selectedEntity.extra.last_updated + 'Z').toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false, timeZoneName: 'short' }).toUpperCase() + ' — OPTIC INTERCEPT'
                            : 'OPTIC INTERCEPT'}
                    </h2>
                    <span className="text-[10px] text-gray-500 font-mono">ID: {selectedEntity.id}</span>
                </div>
                <div className="relative w-full h-48 bg-black flex items-center justify-center p-1">
                    {(() => {
                        const url = selectedEntity.media_url || '';
                        const mt = selectedEntity.extra?.media_type || (
                            url.includes('.mp4') || url.includes('.webm') ? 'video' :
                                url.includes('.m3u8') || url.includes('hls') ? 'hls' :
                                    url.includes('.mjpg') || url.includes('.mjpeg') || url.includes('mjpg') ? 'mjpeg' :
                                        url.includes('embed') || url.includes('maps/embed') ? 'embed' :
                                            url.includes('mapbox.com') ? 'satellite' : 'image'
                        );

                        if (mt === 'video') return (
                            <video
                                src={url}
                                autoPlay
                                loop
                                muted
                                playsInline
                                className="w-full h-full object-cover border border-cyan-900/50 rounded-sm filter contrast-125 saturate-50"
                            />
                        );
                        if (mt === 'hls') return (
                            <HlsVideo
                                src={url}
                                className="w-full h-full object-cover border border-cyan-900/50 rounded-sm filter contrast-125 saturate-50"
                            />
                        );
                        if (mt === 'embed') return (
                            <iframe
                                src={url}
                                allowFullScreen
                                loading="lazy"
                                className="w-full h-full object-cover border border-cyan-900/50 rounded-sm filter contrast-125 saturate-50"
                            />
                        );
                        if (mt === 'mjpeg') return (
                            <img
                                src={url}
                                alt="MJPEG Feed"
                                className="w-full h-full object-cover border border-cyan-900/50 rounded-sm filter contrast-125 saturate-50"
                                onError={(e) => {
                                    const target = e.target as HTMLImageElement;
                                    target.src = "https://via.placeholder.com/400x300.png?text=FEED+UNAVAILABLE";
                                }}
                            />
                        );
                        // satellite / image — standard img with referrer policy for external tiles
                        return (
                            <img
                                src={url}
                                alt="CCTV Feed"
                                className="w-full h-full object-cover border border-cyan-900/50 rounded-sm filter contrast-125 saturate-50"
                                onError={(e) => {
                                    const target = e.target as HTMLImageElement;
                                    target.src = "https://via.placeholder.com/400x300.png?text=NO+SIGNAL";
                                }}
                            />
                        );
                    })()}

                    {/* Retro UI Overlay for the camera feed */}
                    <div className="absolute top-2 left-2 text-[8px] text-cyan-500 bg-black/50 px-1 py-0.5 rounded">
                        REC // 00:00:00:00
                    </div>
                </div>
                <div className="p-3 bg-black/40 text-[9px] text-cyan-500/70 font-mono tracking-widest flex justify-between items-center">
                    <span>{selectedEntity.name?.toUpperCase() || 'UNKNOWN MOUNT'}</span>
                    <span className="text-red-500 text-right">
                        {selectedEntity.extra?.last_updated
                            ? new Date(selectedEntity.extra.last_updated + 'Z').toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false, timeZoneName: 'short' })
                            : ''}
                    </span>
                </div>
            </motion.div>
        );
    }

    // Generic entity info panel for Tier 1 + Tier 2 layers
    const genericEntityTypes = ['military_base', 'nuclear_facility', 'embassy', 'submarine_cable', 'cable_landing',
        'tfr', 'weather_alert', 'natural_event', 'firms_hotspot', 'power_outage', 'internet_outage', 'air_quality', 'radioactivity',
        'volcano', 'piracy', 'reservoir', 'cell_tower', 'border_crossing', 'cyber_threat', 'global_event', 'noaa_nwr', 'kiwisdr',
        'kismet_device', 'snort_alert', 'nmap_host', 'nuclei_vuln'];
    if (selectedEntity && genericEntityTypes.includes(selectedEntity.type)) {
        const e = selectedEntity.extra || {};
        const typeLabels: Record<string, { title: string; color: string; border: string }> = {
            military_base: { title: 'MILITARY INSTALLATION', color: 'text-green-400', border: 'border-green-800' },
            nuclear_facility: { title: 'NUCLEAR FACILITY', color: 'text-yellow-400', border: 'border-yellow-800' },
            embassy: { title: 'DIPLOMATIC FACILITY', color: 'text-amber-400', border: 'border-amber-800' },
            submarine_cable: { title: 'SUBMARINE CABLE', color: 'text-blue-400', border: 'border-blue-800' },
            cable_landing: { title: 'CABLE LANDING POINT', color: 'text-blue-400', border: 'border-blue-800' },
            tfr: { title: 'FLIGHT RESTRICTION (TFR)', color: 'text-red-400', border: 'border-red-800' },
            weather_alert: { title: 'WEATHER ALERT', color: 'text-orange-400', border: 'border-orange-800' },
            natural_event: { title: 'NATURAL EVENT', color: 'text-orange-400', border: 'border-orange-800' },
            firms_hotspot: { title: 'FIRE HOTSPOT (VIIRS)', color: 'text-orange-500', border: 'border-orange-800' },
            power_outage: { title: 'POWER OUTAGE', color: 'text-yellow-400', border: 'border-yellow-800' },
            internet_outage: { title: 'INTERNET OUTAGE', color: 'text-rose-400', border: 'border-rose-800' },
            air_quality: { title: 'AIR QUALITY ALERT', color: 'text-purple-400', border: 'border-purple-800' },
            radioactivity: { title: 'RADIATION MONITOR', color: 'text-green-400', border: 'border-green-800' },
            volcano: { title: 'VOLCANO', color: 'text-orange-500', border: 'border-orange-800' },
            piracy: { title: 'PIRACY / ASAM INCIDENT', color: 'text-red-500', border: 'border-red-800' },
            reservoir: { title: 'RESERVOIR / DAM', color: 'text-blue-400', border: 'border-blue-800' },
            cell_tower: { title: 'CELL TOWER', color: 'text-purple-400', border: 'border-purple-800' },
            border_crossing: { title: 'BORDER CROSSING', color: 'text-green-400', border: 'border-green-800' },
            cyber_threat: { title: e?.source === 'checkpoint' ? 'LIVE CYBER ATTACK' : 'CYBER THREAT', color: e?.source === 'checkpoint' ? 'text-red-400' : 'text-purple-400', border: e?.source === 'checkpoint' ? 'border-red-800' : 'border-purple-800' },
            global_event: { title: 'GLOBAL EVENT', color: 'text-red-400', border: 'border-red-800' },
            noaa_nwr: { title: 'NOAA WEATHER RADIO', color: 'text-orange-400', border: 'border-orange-800' },
            kiwisdr: { title: 'KIWISDR RECEIVER', color: 'text-teal-400', border: 'border-teal-800' },
            kismet_device: { title: 'WIRELESS DEVICE', color: 'text-cyan-400', border: 'border-cyan-800' },
            snort_alert: { title: 'IDS ALERT', color: 'text-red-400', border: 'border-red-800' },
            nmap_host: { title: 'NETWORK HOST', color: 'text-green-400', border: 'border-green-800' },
            nuclei_vuln: { title: 'VULNERABILITY', color: 'text-orange-400', border: 'border-orange-800' },
        };
        const tl = typeLabels[selectedEntity.type] || { title: 'ENTITY', color: 'text-cyan-400', border: 'border-cyan-800' };

        // Build field list based on entity type
        const fields: [string, string][] = [];
        if (e.name) fields.push(['NAME', e.name]);
        if (e.country) fields.push(['COUNTRY', e.country]);
        if (e.branch) fields.push(['BRANCH', e.branch]);
        if (e.base_type) fields.push(['TYPE', e.base_type]);
        if (e.status) fields.push(['STATUS', e.status]);
        if (e.reactor_type) fields.push(['REACTOR', e.reactor_type]);
        if (e.reactor_model) fields.push(['MODEL', e.reactor_model]);
        if (e.capacity_mw) fields.push(['CAPACITY', `${e.capacity_mw} MW`]);
        if (e.operational_from) fields.push(['OPERATIONAL SINCE', e.operational_from]);
        if (e.iaea_id) fields.push(['IAEA ID', e.iaea_id]);
        if (e.city) fields.push(['CITY', e.city]);
        if (e.emb_type) fields.push(['FACILITY TYPE', e.emb_type]);
        if (e.jurisdiction) fields.push(['JURISDICTION', e.jurisdiction]);
        if (e.address && e.address.length > 2) fields.push(['ADDRESS', e.address]);
        if (e.title) fields.push(['TITLE', e.title]);
        if (e.legal) fields.push(['RESTRICTION', e.legal]);
        if (e.state) fields.push(['STATE', e.state]);
        if (e.event) fields.push(['EVENT', e.event]);
        if (e.severity) fields.push(['SEVERITY', e.severity]);
        if (e.headline) fields.push(['HEADLINE', e.headline]);
        if (e.sender) fields.push(['SENDER', e.sender]);
        if (e.category) fields.push(['CATEGORY', e.category]);
        if (e.date) fields.push(['DATE', e.date]);
        if (e.confidence) fields.push(['CONFIDENCE', e.confidence]);
        if (e.frp) fields.push(['FIRE POWER', `${e.frp} MW`]);
        if (e.brightness) fields.push(['BRIGHTNESS', `${e.brightness} K`]);
        if (e.satellite) fields.push(['SATELLITE', e.satellite]);
        if (e.customers_out) fields.push(['CUSTOMERS OUT', Number(e.customers_out).toLocaleString()]);
        if (e.pct_out) fields.push(['% AFFECTED', `${e.pct_out}%`]);
        if (e.onset) fields.push(['ONSET', e.onset]);
        if (e.expires) fields.push(['EXPIRES', e.expires]);
        if (e.pm25) fields.push(['PM2.5 / AQI', String(e.pm25)]);
        if (e.level) fields.push(['LEVEL', e.level]);
        if (e.value) fields.push(['READING', `${e.value} ${e.unit || ''}`]);
        if (e.source) fields.push(['SOURCE', e.source]);
        if (e.notes) fields.push(['NOTES', e.notes]);
        if (e.elevation) fields.push(['ELEVATION', `${e.elevation} m`]);
        if (e.volcano_type) fields.push(['VOLCANO TYPE', e.volcano_type]);
        if (e.last_eruption) fields.push(['LAST ERUPTION', e.last_eruption]);
        if (e.region) fields.push(['REGION', e.region]);
        if (e.tectonic) fields.push(['TECTONIC SETTING', e.tectonic]);
        if (e.rock_type) fields.push(['ROCK TYPE', e.rock_type]);
        if (e.hostility) fields.push(['HOSTILITY', e.hostility]);
        if (e.victim) fields.push(['VICTIM', e.victim]);
        if (e.description) fields.push(['DESCRIPTION', e.description]);
        if (e.subregion) fields.push(['SUBREGION', e.subregion]);
        if (e.navarea) fields.push(['NAVAREA', e.navarea]);
        if (e.level_ft) fields.push(['WATER LEVEL', `${e.level_ft} ${e.unit || 'ft'}`]);
        if (e.radio) fields.push(['RADIO TYPE', e.radio]);
        if (e.mcc) fields.push(['MCC', e.mcc]);
        if (e.mnc) fields.push(['MNC', e.mnc]);
        if (e.range) fields.push(['RANGE', `${e.range} m`]);
        if (e.samples) fields.push(['SAMPLES', String(e.samples)]);
        if (e.updated) fields.push(['LAST UPDATE', e.updated]);
        if (e.event_type) fields.push(['EVENT TYPE', e.event_type]);
        if (e.delay !== undefined && e.delay > 0) fields.push(['WAIT TIME', `${e.delay} min`]);
        if (e.lanes_open) fields.push(['LANES OPEN', `${e.lanes_open} / ${e.max_lanes || '?'}`]);
        if (e.border) fields.push(['BORDER', e.border]);
        if (e.attack_name) fields.push(['ATTACK', e.attack_name]);
        if (e.attack_type) fields.push(['ATTACK TYPE', e.attack_type.toUpperCase()]);
        if (e.source_country) fields.push(['SOURCE', `${e.source_country}${e.source_state ? ' / ' + e.source_state : ''}`]);
        if (e.malware) fields.push(['MALWARE', e.malware]);
        if (e.ip) fields.push(['IP', e.ip]);
        if (e.as_name) fields.push(['AS NAME', e.as_name]);
        if (e.callsign) fields.push(['CALLSIGN', e.callsign]);
        if (e.freq) fields.push(['FREQUENCY', `${e.freq} MHz`]);
        if (e.location) fields.push(['LOCATION', e.location]);
        if (e.host) fields.push(['HOST', e.host]);
        if (e.port) fields.push(['PORT', String(e.port)]);
        if (e.freq_min && e.freq_max) fields.push(['FREQ RANGE', `${e.freq_min}–${e.freq_max} kHz`]);
        if (e.users !== undefined && e.channels) fields.push(['USERS', `${e.users} / ${e.channels} ch`]);
        if (e.antenna) fields.push(['ANTENNA', e.antenna]);
        if (e.url && !fields.some(f => f[0] === 'URL')) fields.push(['URL', e.url]);
        // OSINT fields
        if (e.mac) fields.push(['MAC', e.mac]);
        if (e.ssid) fields.push(['SSID', e.ssid]);
        if (e.signal_dbm) fields.push(['SIGNAL', `${e.signal_dbm} dBm`]);
        if (e.channel) fields.push(['CHANNEL', e.channel]);
        if (e.encryption) fields.push(['ENCRYPTION', e.encryption]);
        if (e.manufacturer) fields.push(['MANUFACTURER', e.manufacturer]);
        if (e.packets) fields.push(['PACKETS', String(e.packets)]);
        if (e.device_type) fields.push(['DEVICE TYPE', e.device_type]);
        if (e.signature_msg) fields.push(['SIGNATURE', e.signature_msg]);
        if (e.classification) fields.push(['CLASSIFICATION', e.classification]);
        if (e.src_ip) fields.push(['SRC IP', e.src_ip]);
        if (e.dst_ip) fields.push(['DST IP', e.dst_ip]);
        if (e.src_port) fields.push(['SRC PORT', String(e.src_port)]);
        if (e.dst_port) fields.push(['DST PORT', String(e.dst_port)]);
        if (e.protocol) fields.push(['PROTOCOL', e.protocol]);
        if (e.os_fingerprint) fields.push(['OS', e.os_fingerprint]);
        if (e.open_ports) fields.push(['OPEN PORTS', e.open_ports]);
        if (e.vendor) fields.push(['VENDOR', e.vendor]);
        if (e.hostname) fields.push(['HOSTNAME', e.hostname]);
        if (e.template_id) fields.push(['TEMPLATE', e.template_id]);
        if (e.vuln_severity) fields.push(['SEVERITY', e.vuln_severity.toUpperCase()]);
        if (e.matched_at) fields.push(['MATCHED AT', e.matched_at]);
        if (e.scan_time) fields.push(['SCAN TIME', e.scan_time]);
        if (e.target) fields.push(['TARGET', e.target]);

        return (
            <motion.div
                initial={{ y: 50, opacity: 0 }}
                animate={{ y: 0, opacity: 1 }}
                transition={{ duration: 0.4 }}
                className={`w-full bg-black/60 backdrop-blur-md border ${tl.border} rounded-xl flex flex-col z-10 font-mono shadow-[0_4px_30px_rgba(0,0,0,0.5)] pointer-events-auto overflow-hidden flex-shrink-0`}
            >
                <div className={`p-3 border-b ${tl.border} bg-black/40 flex justify-between items-center`}>
                    <h2 className={`text-xs tracking-widest font-bold ${tl.color}`}>
                        {tl.title}
                    </h2>
                    <span className="text-[10px] text-gray-500 font-mono">ID: {String(selectedEntity.id).slice(0, 20)}</span>
                </div>
                <div className="p-4 flex flex-col gap-2 max-h-[400px] overflow-y-auto styled-scrollbar">
                    {fields.map(([label, value]) => (
                        <div key={label} className="flex justify-between items-start border-b border-gray-800/50 pb-1.5">
                            <span className="text-gray-500 text-[10px] flex-shrink-0">{label}</span>
                            <span className="text-white text-[10px] font-bold text-right ml-4 break-words max-w-[65%]">{value}</span>
                        </div>
                    ))}
                    {fields.length === 0 && (
                        <div className="text-gray-500 text-[10px] text-center py-4">NO ADDITIONAL DATA</div>
                    )}
                    {selectedEntity.type === 'kiwisdr' && e.host && (
                        <a
                            href={`http://${e.host}:${e.port || 8073}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="mt-2 px-3 py-1.5 bg-teal-900/40 border border-teal-500/50 rounded text-teal-400 text-[10px] tracking-widest text-center hover:bg-teal-800/50 transition-colors"
                        >
                            LISTEN LIVE
                        </a>
                    )}
                    <OsintActions entity={selectedEntity} extra={e} />
                </div>
            </motion.div>
        );
    }

    return (<>
        <motion.div
            initial={{ y: 50, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            transition={{ duration: 0.8, delay: 0.2 }}
            className={`w-full bg-black/40 backdrop-blur-md border ${regionalFocus?.active ? 'border-amber-800' : 'border-gray-800'} rounded-xl flex flex-col z-10 font-mono shadow-[0_4px_30px_rgba(0,0,0,0.5)] pointer-events-auto overflow-hidden transition-all duration-300 ${isMinimized ? 'h-[50px] flex-shrink-0' : 'flex-1 min-h-0'}`}
        >
            <div
                className={`p-3 border-b ${regionalFocus?.active ? 'border-amber-500/20 bg-amber-950/20' : 'border-cyan-500/20 bg-cyan-950/20'} relative overflow-hidden cursor-pointer hover:bg-cyan-900/30 transition-colors`}
                onClick={() => setIsMinimized(!isMinimized)}
            >
                <div className="flex justify-between items-center relative z-10">
                    <h2 className={`text-xs tracking-widest font-bold flex items-center gap-2 ${regionalFocus?.active ? 'text-amber-400' : 'text-cyan-400'}`}>
                        <AlertTriangle size={14} />
                        {regionalFocus?.active
                            ? `REGIONAL THREAT INTERCEPT — ${regionalFocus.name?.toUpperCase() || 'REGION'}${regionalFocus.countryCode ? ` [${regionalFocus.countryCode}]` : ''}`
                            : 'GLOBAL THREAT INTERCEPT'
                        }
                    </h2>
                    <button className="text-cyan-500 hover:text-white transition-colors">
                        {isMinimized ? <ChevronDown size={14} /> : <ChevronUp size={14} />}
                    </button>
                </div>

                <AnimatePresence>
                    {!isMinimized && (
                        <motion.div
                            initial={{ height: 0, opacity: 0 }}
                            animate={{ height: "auto", opacity: 1 }}
                            exit={{ height: 0, opacity: 0 }}
                            className="text-[9px] text-cyan-500/80 mt-1 flex items-center justify-between font-bold relative z-10"
                        >
                            <span className={`px-1 border ${regionalFocus?.active ? 'border-amber-500/30 text-amber-500/80' : 'border-cyan-500/30'}`}>
                                {regionalFocus?.active ? 'SYS.STATUS: REGIONAL SCAN' : 'SYS.STATUS: MONITORING'}
                            </span>
                            <span className="flex items-center gap-1"><Clock size={10} /> {data?.last_updated ? formatTime(data.last_updated) : "SCANNING"}</span>
                        </motion.div>
                    )}
                </AnimatePresence>
            </div>

            <AnimatePresence>
                {!isMinimized && (
                    <motion.div
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        className="flex-1 overflow-y-auto p-3 flex flex-col gap-2 styled-scrollbar"
                    >
                        {news.map((item: any, idx: number) => {
                            let bgClass, titleClass, badgeClass;
                            if (item.risk_score >= 9) {
                                bgClass = "bg-red-950/20 border-red-500/30";
                                titleClass = "text-red-300 font-bold";
                                badgeClass = "bg-red-500/10 text-red-400 border-red-500/30";
                            } else if (item.risk_score >= 7) {
                                bgClass = "bg-orange-950/20 border-orange-500/30";
                                titleClass = "text-orange-300 font-bold";
                                badgeClass = "bg-orange-500/10 text-orange-400 border-orange-500/30";
                            } else if (item.risk_score >= 4) {
                                bgClass = "bg-yellow-950/20 border-yellow-500/30";
                                titleClass = "text-yellow-300 font-bold";
                                badgeClass = "bg-yellow-500/10 text-yellow-500 border-yellow-500/30";
                            } else {
                                bgClass = "bg-green-950/20 border-green-500/30";
                                titleClass = "text-green-300 font-medium";
                                badgeClass = "bg-green-500/10 text-green-400 border-green-500/30";
                            }
                            const itemKey = item.link || item.title || String(idx);
                            const isExpanded = expandedKeys.has(itemKey);

                            return (
                                <motion.div
                                    key={item.link || item.title || idx}
                                    ref={(el) => { itemRefs.current[idx] = el; }}
                                    initial={{ opacity: 0, x: -10 }}
                                    animate={{ opacity: 1, x: 0 }}
                                    transition={{ delay: 0.1 + (idx * 0.05) }}
                                    className={`p-2 rounded-sm border-l-[2px] border-r border-t border-b ${bgClass} flex flex-col gap-1 relative group shrink-0`}
                                >
                                    <div className="flex items-center justify-between text-[8px] text-gray-400 uppercase tracking-widest">
                                        <span className="font-bold flex items-center gap-1 text-cyan-600">
                                            &gt;_ {item.source}
                                        </span>
                                        <span>[{item.published ? formatTime(item.published) : ''}]</span>
                                    </div>

                                    <a href={item.link} target="_blank" rel="noreferrer" className={`text-[11px] ${titleClass} hover:text-white transition-colors leading-tight`}>
                                        {item.title}
                                    </a>

                                    {item.image_url && (
                                        <div className="mt-1 rounded overflow-hidden border border-gray-700/50 max-h-24">
                                            <img
                                                src={item.image_url}
                                                alt=""
                                                className="w-full h-24 object-cover opacity-80 hover:opacity-100 transition-opacity"
                                                loading="lazy"
                                                onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
                                            />
                                        </div>
                                    )}

                                    {item.machine_assessment && (
                                        <div className="mt-1 p-1.5 bg-black/60 border border-cyan-800/50 rounded-sm text-[8.5px] text-cyan-400 font-mono leading-tight relative overflow-hidden shadow-[inset_0_0_10px_rgba(0,255,255,0.05)]">
                                            <div className="absolute top-0 left-0 w-[2px] h-full bg-cyan-500 animate-pulse"></div>
                                            <span className="font-bold text-white">&gt;_ SYS.ANALYSIS: </span>
                                            <span className="text-cyan-300 opacity-90">{item.machine_assessment}</span>
                                        </div>
                                    )}

                                    <div className="flex justify-between items-end mt-1 relative z-10">
                                        <span className={`text-[8px] font-bold px-1 rounded-sm border ${badgeClass}`}>
                                            LVL: {item.risk_score}/10
                                        </span>
                                        <div className="flex items-center gap-2">
                                            {item.cluster_count > 1 && (
                                                <button onClick={() => toggleExpand(itemKey)} className="text-[8px] font-bold text-cyan-500 bg-cyan-950/50 hover:text-white hover:bg-cyan-900 border border-cyan-500/30 px-1.5 py-0.5 rounded-sm transition-colors cursor-pointer">
                                                    {isExpanded ? '[- COLLAPSE]' : `[+${item.cluster_count - 1} SOURCES]`}
                                                </button>
                                            )}
                                            {item.coords && (
                                                <span className="text-[8px] text-gray-500 font-mono tracking-tighter">
                                                    {item.coords[0].toFixed(2)}, {item.coords[1].toFixed(2)}
                                                </span>
                                            )}
                                        </div>
                                    </div>

                                    <AnimatePresence>
                                        {isExpanded && item.articles && item.articles.length > 1 && (
                                            <motion.div
                                                initial={{ height: 0, opacity: 0 }}
                                                animate={{ height: "auto", opacity: 1 }}
                                                exit={{ height: 0, opacity: 0 }}
                                                className="mt-2 pt-2 border-t border-cyan-500/20 flex flex-col gap-2 overflow-hidden"
                                            >
                                                {item.articles.slice(1).map((subItem: any, subIdx: number) => (
                                                    <div key={subItem.link || subItem.title || subIdx} className="flex flex-col gap-0.5 pl-2 border-l border-cyan-500/20">
                                                        <div className="flex items-center justify-between text-[7.5px] text-gray-500 uppercase font-bold">
                                                            <span>&gt;_ {subItem.source}</span>
                                                            <span className={
                                                                subItem.risk_score >= 9 ? 'text-red-400' :
                                                                    subItem.risk_score >= 7 ? 'text-orange-400' :
                                                                        subItem.risk_score >= 4 ? 'text-yellow-500' :
                                                                            'text-green-400'
                                                            }>LVL: {subItem.risk_score}/10</span>
                                                        </div>
                                                        <a href={subItem.link} target="_blank" rel="noreferrer" className="text-[10px] text-gray-400 hover:text-white transition-colors leading-tight">
                                                            {subItem.title}
                                                        </a>
                                                    </div>
                                                ))}
                                            </motion.div>
                                        )}
                                    </AnimatePresence>
                                </motion.div>
                            )
                        })}
                        {news.length === 0 && (
                            <div className={`text-[10px] tracking-widest font-bold text-center mt-6 animate-pulse ${regionalFocus?.active ? 'text-amber-500/50' : 'text-cyan-500/50'}`}>
                                {regionalFocus?.active
                                    ? `SCANNING REGIONAL FEEDS — ${regionalFocus.name?.toUpperCase() || 'REGION'}...`
                                    : 'INITIALIZING SECURE HANDSHAKE...'
                                }
                            </div>
                        )}
                    </motion.div>
                )}
            </AnimatePresence>


        </motion.div>

        {/* Social Media OSINT Feed — gated by layer toggle */}
        {activeLayers?.social_media !== false && data?.social_media?.length > 0 && (
            <motion.div
                initial={{ y: 50, opacity: 0 }}
                animate={{ y: 0, opacity: 1 }}
                transition={{ duration: 0.8, delay: 0.4 }}
                className={`w-full bg-black/40 backdrop-blur-md border ${regionalFocus?.active ? 'border-amber-800/50' : 'border-fuchsia-800/50'} rounded-xl flex flex-col z-10 font-mono shadow-[0_4px_30px_rgba(0,0,0,0.5)] pointer-events-auto overflow-hidden transition-all duration-300 ${socialMinimized ? 'h-[50px] flex-shrink-0' : 'flex-shrink-0 max-h-[350px]'}`}
            >
                <div
                    className="p-3 border-b border-fuchsia-500/20 bg-fuchsia-950/20 cursor-pointer hover:bg-fuchsia-900/30 transition-colors"
                    onClick={() => setSocialMinimized(!socialMinimized)}
                >
                    <div className="flex justify-between items-center">
                        <h2 className={`text-xs tracking-widest font-bold flex items-center gap-2 ${regionalFocus?.active ? 'text-amber-400' : 'text-fuchsia-400'}`}>
                            {regionalFocus?.active
                                ? `REGIONAL SOCIAL OSINT — ${regionalFocus.name?.toUpperCase() || 'REGION'}`
                                : 'SOCIAL MEDIA OSINT'
                            }
                        </h2>
                        <div className="flex items-center gap-2">
                            <span className={`text-[10px] font-bold ${regionalFocus?.active ? 'text-amber-500/60' : 'text-fuchsia-500/60'}`}>{data.social_media.length} POSTS</span>
                            <button className="text-fuchsia-500 hover:text-white transition-colors">
                                {socialMinimized ? <ChevronDown size={14} /> : <ChevronUp size={14} />}
                            </button>
                        </div>
                    </div>
                </div>
                <AnimatePresence>
                {!socialMinimized && (
                <motion.div
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    className="flex-1 overflow-y-auto p-2 flex flex-col gap-2 styled-scrollbar"
                >
                    {data.social_media.slice(0, 50).map((post: any, idx: number) => {
                        const platformColors: Record<string, string> = {
                            reddit: 'text-orange-400 border-orange-500/30 bg-orange-950/20',
                            bluesky: 'text-sky-400 border-sky-500/30 bg-sky-950/20',
                            flickr: 'text-pink-400 border-pink-500/30 bg-pink-950/20',
                            telegram: 'text-blue-400 border-blue-500/30 bg-blue-950/20',
                            youtube: 'text-red-400 border-red-500/30 bg-red-950/20',
                            mastodon: 'text-purple-400 border-purple-500/30 bg-purple-950/20',
                        };
                        const pClass = platformColors[post.platform] || 'text-gray-400 border-gray-500/30 bg-gray-950/20';
                        return (
                            <div key={post.id || idx} className={`p-2 rounded-sm border-l-2 border-r border-t border-b ${pClass} flex flex-col gap-1 shrink-0`}>
                                <div className="flex items-center justify-between text-[8px] uppercase tracking-widest">
                                    <span className="font-bold flex items-center gap-1">
                                        {post.platform === 'reddit' && '🔴'}
                                        {post.platform === 'bluesky' && '🦋'}
                                        {post.platform === 'flickr' && '📷'}
                                        {post.platform === 'telegram' && '✈️'}
                                        {post.platform === 'youtube' && '▶️'}
                                        {post.platform === 'mastodon' && '🐘'}
                                        {' '}{post.platform.toUpperCase()}
                                        {post.subreddit ? ` / ${post.subreddit}` : ''}
                                    </span>
                                    <div className="flex items-center gap-2">
                                        {post.score > 0 && <span className="text-yellow-500">⬆{post.score}</span>}
                                        {post.flair && <span className="text-gray-500">[{post.flair}]</span>}
                                    </div>
                                </div>
                                <a href={post.url} target="_blank" rel="noreferrer" className="text-[10px] text-white/90 hover:text-white transition-colors leading-tight font-bold">
                                    {post.title}
                                </a>
                                {post.media_url && post.media_type === 'image' && (
                                    <div className="mt-1 rounded overflow-hidden border border-gray-700">
                                        <img
                                            src={post.media_url}
                                            alt=""
                                            className="w-full h-32 object-cover opacity-90 hover:opacity-100 transition-opacity"
                                            loading="lazy"
                                            onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
                                        />
                                    </div>
                                )}
                                {post.media_url && post.media_type === 'video' && (
                                    <a href={post.url} target="_blank" rel="noreferrer" className="mt-1 relative block rounded overflow-hidden border border-gray-700">
                                        <img
                                            src={post.media_url}
                                            alt=""
                                            className="w-full h-32 object-cover opacity-80"
                                            loading="lazy"
                                            onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
                                        />
                                        <div className="absolute inset-0 flex items-center justify-center">
                                            <div className="w-10 h-10 bg-black/70 rounded-full flex items-center justify-center border border-white/30">
                                                <div className="w-0 h-0 border-l-[10px] border-l-white border-t-[6px] border-t-transparent border-b-[6px] border-b-transparent ml-1" />
                                            </div>
                                        </div>
                                    </a>
                                )}
                                <div className="flex items-center justify-between text-[8px] text-gray-500 mt-0.5">
                                    <span>@{post.author}</span>
                                    {post.comments > 0 && <span>💬 {post.comments}</span>}
                                </div>
                            </div>
                        );
                    })}
                </motion.div>
                )}
                </AnimatePresence>
            </motion.div>
        )}

        {/* Space Weather Panel */}
        {activeLayers?.space_weather !== false && data?.space_weather?.length > 0 && (
            <motion.div
                initial={{ y: 50, opacity: 0 }}
                animate={{ y: 0, opacity: 1 }}
                transition={{ duration: 0.8, delay: 0.5 }}
                className="w-full bg-black/40 backdrop-blur-md border border-amber-800/50 rounded-xl flex flex-col z-10 font-mono shadow-[0_4px_30px_rgba(0,0,0,0.5)] pointer-events-auto overflow-hidden flex-shrink-0"
            >
                <div className="p-3 border-b border-amber-500/20 bg-amber-950/20">
                    <h2 className="text-xs tracking-widest font-bold text-amber-400 flex items-center gap-2">
                        SPACE WEATHER
                        <span className="text-[10px] text-amber-500/60 font-bold ml-auto">{data.space_weather.length} EVENTS</span>
                    </h2>
                </div>
                <div className="p-2 flex flex-col gap-2 max-h-[250px] overflow-y-auto styled-scrollbar">
                    {(() => {
                        const kp = data.space_weather.find((e: any) => e.type === 'geomagnetic');
                        const wind = data.space_weather.find((e: any) => e.type === 'solar_wind');
                        const flares = data.space_weather.filter((e: any) => e.type === 'solar_flare');
                        const kpVal = kp?.kp || 0;
                        const kpColor = kpVal >= 7 ? 'text-red-400' : kpVal >= 5 ? 'text-orange-400' : kpVal >= 4 ? 'text-yellow-400' : 'text-green-400';
                        const windSpeed = parseFloat(wind?.speed_kms) || 0;
                        const windColor = windSpeed >= 700 ? 'text-red-400' : windSpeed >= 500 ? 'text-orange-400' : 'text-green-400';
                        return (
                            <>
                                {/* Status row */}
                                <div className="flex gap-2">
                                    {kp && (
                                        <div className="flex-1 p-2 rounded bg-amber-950/30 border border-amber-500/20">
                                            <div className="text-[8px] uppercase tracking-widest text-amber-500/60 mb-1">Geomagnetic</div>
                                            <div className={`text-lg font-bold ${kpColor}`}>Kp {kpVal}</div>
                                            <div className={`text-[9px] ${kpColor}`}>{kp.storm_level}</div>
                                        </div>
                                    )}
                                    {wind && (
                                        <div className="flex-1 p-2 rounded bg-amber-950/30 border border-amber-500/20">
                                            <div className="text-[8px] uppercase tracking-widest text-amber-500/60 mb-1">Solar Wind</div>
                                            <div className={`text-lg font-bold ${windColor}`}>{wind.speed_kms}</div>
                                            <div className="text-[9px] text-amber-500/60">km/s</div>
                                        </div>
                                    )}
                                </div>
                                {/* Flare list */}
                                {flares.length > 0 && (
                                    <div className="mt-1">
                                        <div className="text-[8px] uppercase tracking-widest text-amber-500/60 mb-1 px-1">Solar Flares</div>
                                        {flares.slice(-10).reverse().map((f: any) => {
                                            const cls = (f.class || '').charAt(0);
                                            const flareColor = cls === 'X' ? 'text-red-400 border-red-500/30' : cls === 'M' ? 'text-orange-400 border-orange-500/30' : cls === 'C' ? 'text-yellow-400 border-yellow-500/30' : 'text-gray-400 border-gray-500/30';
                                            return (
                                                <div key={f.id} className={`p-1.5 rounded-sm border-l-2 ${flareColor} mb-1 flex items-center justify-between`}>
                                                    <div className="flex items-center gap-2">
                                                        <span className={`text-xs font-bold ${flareColor.split(' ')[0]}`}>{f.class}</span>
                                                        <span className="text-[9px] text-gray-400">Region {f.region || '—'}</span>
                                                    </div>
                                                    <span className="text-[8px] text-gray-500">{f.peak ? new Date(f.peak).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : ''}</span>
                                                </div>
                                            );
                                        })}
                                    </div>
                                )}
                            </>
                        );
                    })()}
                </div>
            </motion.div>
        )}

        </>
    );
}

const NewsFeed = React.memo(NewsFeedInner);
export default NewsFeed;
export { FridayPanel };
