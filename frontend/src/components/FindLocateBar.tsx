"use client";

import { useState, useMemo, useRef, useEffect, useCallback } from "react";
import { Search, Crosshair, Plane, Shield, Star, Ship, X, Database, Loader, User, Mail, Globe, Phone, Monitor, Fingerprint, Clock } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { trackedOperators } from '../lib/trackedData';
import { API_BASE } from "@/lib/api";

interface FindLocateBarProps {
    data: any;
    onLocate: (lat: number, lng: number, entityId: string, entityType: string) => void;
    onFilter?: (filterType: string, filterValue: string) => void;
    onOsintResult?: (result: any) => void;
}

interface SearchResult {
    id: string;
    label: string;
    sublabel: string;
    category: string;
    categoryColor: string;
    lat: number;
    lng: number;
    entityType: string;
}

interface HistoryEntry {
    query: string;
    type: string;
    timestamp: string;
    tools_run: string[];
    summary: string;
}

function relativeTime(iso: string): string {
    const diff = Date.now() - new Date(iso).getTime();
    const sec = Math.floor(diff / 1000);
    if (sec < 60) return `${sec}s ago`;
    const min = Math.floor(sec / 60);
    if (min < 60) return `${min}m ago`;
    const hr = Math.floor(min / 60);
    if (hr < 24) return `${hr}h ago`;
    const days = Math.floor(hr / 24);
    return `${days}d ago`;
}

const TYPE_BADGE_COLORS: Record<string, string> = {
    email: "bg-purple-950/60 text-purple-400 border-purple-500/30",
    username: "bg-pink-950/60 text-pink-400 border-pink-500/30",
    ip: "bg-cyan-950/60 text-cyan-400 border-cyan-500/30",
    domain: "bg-blue-950/60 text-blue-400 border-blue-500/30",
    phone: "bg-green-950/60 text-green-400 border-green-500/30",
    name: "bg-amber-950/60 text-amber-400 border-amber-500/30",
};

// Detect what type of OSINT query this is
function detectQueryType(q: string): { type: string; icon: any; label: string; color: string } | null {
    const trimmed = q.trim();
    if (!trimmed || trimmed.length < 2) return null;

    // Email
    if (/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(trimmed)) {
        return { type: 'email', icon: Mail, label: 'EMAIL OSINT', color: 'text-purple-400' };
    }
    // IP address (must come before phone — IPs look like phone digits)
    if (/^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}(\/\d{1,2})?$/.test(trimmed)) {
        return { type: 'ip', icon: Monitor, label: 'IP INTEL', color: 'text-cyan-400' };
    }
    // Phone number (digits, +, -, spaces, parens, at least 7 digits — but NOT dots-only like IPs)
    if (/^[\d\s\-\+\(\)\.]{7,}$/.test(trimmed) && (trimmed.match(/\d/g) || []).length >= 7 && !/^\d+(\.\d+){2,}$/.test(trimmed)) {
        return { type: 'phone', icon: Phone, label: 'PHONE LOOKUP', color: 'text-green-400' };
    }
    // Username (starts with @ or single word with no spaces, no dots)
    if (/^@[\w\-\.]{2,}$/.test(trimmed) || (/^[\w\-]{3,30}$/.test(trimmed) && !trimmed.includes('.'))) {
        return { type: 'username', icon: User, label: 'USERNAME HUNT', color: 'text-pink-400' };
    }
    // Domain (has dots, looks like hostname, no spaces)
    if (/^[a-zA-Z0-9]([a-zA-Z0-9\-]*[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]*[a-zA-Z0-9])?)+$/.test(trimmed)) {
        return { type: 'domain', icon: Globe, label: 'DOMAIN RECON', color: 'text-blue-400' };
    }
    // Name / general search (has spaces or just text)
    if (trimmed.length >= 3) {
        return { type: 'name', icon: Fingerprint, label: 'DEEP OSINT', color: 'text-amber-400' };
    }

    return null;
}

export default function FindLocateBar({ data, onLocate, onFilter, onOsintResult }: FindLocateBarProps) {
    const [query, setQuery] = useState("");
    const [isOpen, setIsOpen] = useState(false);
    const [osintLoading, setOsintLoading] = useState(false);
    const [osintError, setOsintError] = useState<string | null>(null);
    const [searchHistory, setSearchHistory] = useState<HistoryEntry[]>([]);
    const historyCache = useRef<{ data: HistoryEntry[]; ts: number } | null>(null);
    const inputRef = useRef<HTMLInputElement>(null);
    const containerRef = useRef<HTMLDivElement>(null);
    const abortRef = useRef<AbortController | null>(null);

    const fetchHistory = useCallback(async () => {
        // Use cached data if less than 60s old
        if (historyCache.current && Date.now() - historyCache.current.ts < 60_000) {
            setSearchHistory(historyCache.current.data);
            return;
        }
        try {
            const res = await fetch(`${API_BASE}/api/osint/search/history`);
            if (res.ok) {
                const data: HistoryEntry[] = await res.json();
                const sorted = Array.isArray(data) ? data.slice().reverse() : [];
                setSearchHistory(sorted);
                historyCache.current = { data: sorted, ts: Date.now() };
            }
        } catch {
            // silent — history is best-effort
        }
    }, []);

    // Close dropdown when clicking outside
    useEffect(() => {
        const handler = (e: MouseEvent) => {
            if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
                setIsOpen(false);
            }
        };
        document.addEventListener("mousedown", handler);
        return () => document.removeEventListener("mousedown", handler);
    }, []);

    // Build searchable index from all data
    const allEntities = useMemo(() => {
        const results: SearchResult[] = [];

        // Commercial flights
        for (const f of data?.commercial_flights || []) {
            const uid = f.icao24 || f.registration || f.callsign || '';
            results.push({
                id: `flight-${uid}`,
                label: f.callsign || uid,
                sublabel: `${f.model || 'Unknown'} · ${f.airline_code || 'Commercial'}`,
                category: "COMMERCIAL",
                categoryColor: "text-cyan-400",
                lat: f.lat,
                lng: f.lng,
                entityType: "flight",
            });
        }

        // Private flights
        for (const f of [...(data?.private_flights || []), ...(data?.private_jets || [])]) {
            const uid = f.icao24 || f.registration || f.callsign || '';
            const type = f.type === 'private_jet' ? 'private_jet' : 'private_flight';
            results.push({
                id: `${type === 'private_jet' ? 'private-jet' : 'private-flight'}-${uid}`,
                label: f.callsign || f.registration || uid,
                sublabel: `${f.model || 'Unknown'} · Private`,
                category: "PRIVATE",
                categoryColor: "text-orange-400",
                lat: f.lat,
                lng: f.lng,
                entityType: type,
            });
        }

        // Military flights
        for (const f of data?.military_flights || []) {
            const uid = f.icao24 || f.registration || f.callsign || '';
            results.push({
                id: `mil-flight-${uid}`,
                label: f.callsign || uid,
                sublabel: `${f.model || 'Unknown'} · ${f.military_type || 'Military'}`,
                category: "MILITARY",
                categoryColor: "text-yellow-400",
                lat: f.lat,
                lng: f.lng,
                entityType: "military_flight",
            });
        }

        // Tracked flights
        for (const f of data?.tracked_flights || []) {
            const uid = f.icao24 || f.registration || f.callsign || '';
            const operator = f.alert_operator || 'Unknown Operator';
            const category = f.alert_category || 'Tracked';
            const type = f.alert_type || f.model || 'Unknown';
            results.push({
                id: `tracked-${uid}`,
                label: operator,
                sublabel: `${category} · ${type} (${f.registration || uid})`,
                category: "TRACKED",
                categoryColor: "text-pink-400",
                lat: f.lat,
                lng: f.lng,
                entityType: "tracked_flight",
            });
        }

        // Ships
        for (const s of data?.ships || []) {
            results.push({
                id: `ship-${s.mmsi || s.name || ''}`,
                label: s.name || "UNKNOWN",
                sublabel: `${s.type || 'Vessel'} · ${s.destination || 'Unknown dest'}`,
                category: "MARITIME",
                categoryColor: "text-blue-400",
                lat: s.lat,
                lng: s.lng,
                entityType: "ship",
            });
        }

        // Database Records - Tracked Operators
        for (const op of trackedOperators) {
            results.push({
                id: `tracked-db-${op}`,
                label: op,
                sublabel: `Database Record · Operator`,
                category: "DATABASE",
                categoryColor: "text-purple-400",
                lat: 0,
                lng: 0,
                entityType: "database_operator",
            });
        }

        return results;
    }, [data]);

    // Filter results based on query
    const filtered = useMemo(() => {
        if (!query.trim()) return [];
        const q = query.toLowerCase();
        return allEntities
            .filter(e => {
                const searchable = `${e.label} ${e.sublabel} ${e.id}`.toLowerCase();
                return searchable.includes(q);
            })
            .slice(0, 12);
    }, [query, allEntities]);

    const queryType = useMemo(() => detectQueryType(query), [query]);

    const handleSelect = (result: SearchResult) => {
        if (result.entityType === "database_operator") {
            if (onFilter) onFilter("tracked_owner", result.label);
        } else {
            onLocate(result.lat, result.lng, result.id, result.entityType);
        }
        setQuery("");
        setIsOpen(false);
    };

    const runOsintSearchFor = useCallback(async (searchQuery: string) => {
        const trimmed = searchQuery.trim();
        if (!trimmed || trimmed.length < 2) return;
        if (osintLoading) return;

        // Cancel any previous search
        if (abortRef.current) abortRef.current.abort();
        abortRef.current = new AbortController();

        setOsintLoading(true);
        setOsintError(null);
        setIsOpen(false);

        try {
            const res = await fetch(`${API_BASE}/api/osint/search`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ query: trimmed }),
                signal: abortRef.current.signal,
            });

            if (!res.ok) {
                setOsintError(`HTTP ${res.status}`);
                return;
            }

            const result = await res.json();

            if (result.status === 'unavailable') {
                setOsintError('OSINT agent unreachable');
                return;
            }

            if (result.error) {
                setOsintError(result.error);
                return;
            }

            // Invalidate history cache so next focus re-fetches
            historyCache.current = null;

            // Pass results to parent
            if (onOsintResult) {
                onOsintResult(result);
            }
        } catch (e: any) {
            if (e.name !== 'AbortError') {
                setOsintError(e.message || 'Search failed');
            }
        } finally {
            setOsintLoading(false);
        }
    }, [osintLoading, onOsintResult]);

    const runOsintSearch = useCallback(() => {
        runOsintSearchFor(query);
    }, [query, runOsintSearchFor]);

    // Enter key triggers OSINT search if no local results match
    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            if (filtered.length > 0 && !queryType) {
                // Select first local result
                handleSelect(filtered[0]);
            } else {
                // Run OSINT search
                runOsintSearch();
            }
        }
    };

    const categoryIcons: Record<string, React.ReactNode> = {
        COMMERCIAL: <Plane size={10} className="text-cyan-400" />,
        PRIVATE: <Plane size={10} className="text-orange-400" />,
        MILITARY: <Shield size={10} className="text-yellow-400" />,
        TRACKED: <Star size={10} className="text-pink-400" />,
        MARITIME: <Ship size={10} className="text-blue-400" />,
        DATABASE: <Database size={10} className="text-purple-400" />,
    };

    const QueryTypeIcon = queryType?.icon || Search;

    return (
        <div ref={containerRef} className="relative w-full pointer-events-auto">
            <div className={`flex items-center gap-2 bg-black/40 backdrop-blur-md border rounded-lg px-3 py-2 transition-colors ${
                osintLoading ? 'border-amber-500/60 shadow-[0_0_15px_rgba(245,158,11,0.15)]' :
                osintError ? 'border-red-500/40' :
                'border-gray-800 focus-within:border-cyan-500/40'
            }`}>
                {osintLoading ? (
                    <Loader size={12} className="text-amber-400 animate-spin flex-shrink-0" />
                ) : (
                    <Search size={12} className="text-gray-500 flex-shrink-0" />
                )}
                <input
                    ref={inputRef}
                    type="text"
                    value={query}
                    placeholder="Search assets or OSINT anything..."
                    className="flex-1 bg-transparent text-[10px] text-gray-300 font-mono tracking-wider outline-none placeholder:text-gray-600"
                    onChange={(e) => {
                        setQuery(e.target.value);
                        setIsOpen(true);
                        setOsintError(null);
                    }}
                    onFocus={() => { setIsOpen(true); fetchHistory(); }}
                    onKeyDown={handleKeyDown}
                    disabled={osintLoading}
                />
                {query && !osintLoading && (
                    <button onClick={() => { setQuery(""); setIsOpen(false); setOsintError(null); }} className="text-gray-600 hover:text-white transition-colors">
                        <X size={10} />
                    </button>
                )}
                {/* OSINT search trigger button */}
                {queryType && !osintLoading && (
                    <button
                        onClick={runOsintSearch}
                        className={`flex items-center gap-1 px-2 py-0.5 rounded border text-[7px] tracking-widest font-bold transition-all hover:brightness-125 ${
                            queryType.type === 'email' ? 'bg-purple-950/40 border-purple-500/40 text-purple-400' :
                            queryType.type === 'username' ? 'bg-pink-950/40 border-pink-500/40 text-pink-400' :
                            queryType.type === 'ip' ? 'bg-cyan-950/40 border-cyan-500/40 text-cyan-400' :
                            queryType.type === 'domain' ? 'bg-blue-950/40 border-blue-500/40 text-blue-400' :
                            queryType.type === 'phone' ? 'bg-green-950/40 border-green-500/40 text-green-400' :
                            'bg-amber-950/40 border-amber-500/40 text-amber-400'
                        }`}
                        title={`Run ${queryType.label}`}
                    >
                        <QueryTypeIcon size={8} />
                        {queryType.label}
                    </button>
                )}
                {!queryType && <Crosshair size={12} className="text-gray-600 flex-shrink-0" />}
            </div>

            {/* Error display */}
            {osintError && (
                <div className="mt-1 px-3 py-1.5 bg-red-950/30 border border-red-500/30 rounded text-red-400 text-[8px] font-mono tracking-wider">
                    OSINT ERROR: {osintError}
                </div>
            )}

            {/* Loading indicator */}
            {osintLoading && (
                <div className="mt-1 px-3 py-2 bg-amber-950/20 border border-amber-500/30 rounded text-[8px] font-mono tracking-wider">
                    <div className="flex items-center gap-2 text-amber-400">
                        <Loader size={9} className="animate-spin" />
                        <span>RUNNING OSINT TOOLS ON &quot;{query}&quot;...</span>
                    </div>
                    <div className="text-amber-600 mt-1 text-[7px]">
                        Sherlock · PhoneInfoga · Nmap · Whois · theHarvester · h8mail — this may take 30-60s
                    </div>
                </div>
            )}

            <AnimatePresence>
                {isOpen && !osintLoading && (filtered.length > 0 || queryType) && (
                    <motion.div
                        initial={{ opacity: 0, y: -4 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -4 }}
                        className="absolute top-full left-0 right-0 mt-1 bg-black/90 backdrop-blur-md border border-gray-800 rounded-lg overflow-hidden z-50 shadow-[0_8px_30px_rgba(0,0,0,0.6)]"
                    >
                        <div className="max-h-[300px] overflow-y-auto styled-scrollbar">
                            {/* OSINT search option — always first when query type is detected */}
                            {queryType && (
                                <button
                                    onClick={runOsintSearch}
                                    className="w-full flex items-center gap-3 px-3 py-2.5 hover:bg-amber-950/30 transition-colors text-left border-b border-gray-800/50 group"
                                >
                                    <div className={`flex-shrink-0 w-5 h-5 flex items-center justify-center rounded bg-gray-900 border border-amber-800/50 group-hover:border-amber-500/50`}>
                                        <QueryTypeIcon size={10} className={queryType.color} />
                                    </div>
                                    <div className="flex-1 min-w-0">
                                        <div className="text-[10px] text-gray-200 font-mono tracking-wide">
                                            Deep search &quot;{query}&quot;
                                        </div>
                                        <div className="text-[8px] text-gray-500 font-mono">
                                            {queryType.type === 'email' ? 'HIBP · h8mail · holehe · theHarvester · breach search' :
                                             queryType.type === 'username' ? 'Sherlock · SpiderFoot · social media hunt' :
                                             queryType.type === 'ip' ? 'Whois · Nmap · SpiderFoot · threat intel' :
                                             queryType.type === 'domain' ? 'Whois · DMitry · theHarvester · SpiderFoot' :
                                             queryType.type === 'phone' ? 'PhoneInfoga · phonenumbers · numverify · carrier · geolocation' :
                                             'Maigret · Sherlock · public records · corporate · court records · social'}
                                        </div>
                                    </div>
                                    <span className={`text-[7px] font-bold tracking-widest ${queryType.color} flex-shrink-0`}>
                                        {queryType.label}
                                    </span>
                                </button>
                            )}
                            {/* Local asset matches */}
                            {filtered.map((r, idx) => (
                                <button
                                    key={`${r.id}-${idx}`}
                                    onClick={() => handleSelect(r)}
                                    className="w-full flex items-center gap-3 px-3 py-2 hover:bg-cyan-950/30 transition-colors text-left border-b border-gray-800/50 last:border-0 group"
                                >
                                    <div className="flex-shrink-0 w-5 h-5 flex items-center justify-center rounded bg-gray-900 border border-gray-800 group-hover:border-cyan-800">
                                        {categoryIcons[r.category]}
                                    </div>
                                    <div className="flex-1 min-w-0">
                                        <div className="text-[10px] text-gray-200 font-mono tracking-wide truncate">{r.label}</div>
                                        <div className="text-[8px] text-gray-500 font-mono truncate">{r.sublabel}</div>
                                    </div>
                                    <span className={`text-[7px] font-bold tracking-widest ${r.categoryColor} flex-shrink-0`}>
                                        {r.category}
                                    </span>
                                </button>
                            ))}
                        </div>
                        <div className="px-3 py-1.5 border-t border-gray-800 bg-black/50 text-[8px] text-gray-600 font-mono tracking-widest flex justify-between">
                            <span>{filtered.length} LOCAL MATCH{filtered.length !== 1 ? 'ES' : ''}</span>
                            <span>{queryType ? '↵ ENTER = OSINT SEARCH' : '↵ ENTER = LOCATE'}</span>
                        </div>
                    </motion.div>
                )}
                {isOpen && !osintLoading && query.trim() && filtered.length === 0 && !queryType && (
                    <motion.div
                        initial={{ opacity: 0, y: -4 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -4 }}
                        className="absolute top-full left-0 right-0 mt-1 bg-black/90 backdrop-blur-md border border-gray-800 rounded-lg z-50 p-4 text-center"
                    >
                        <div className="text-[9px] text-gray-600 font-mono tracking-widest">NO MATCHING ASSETS — TYPE MORE TO ENABLE OSINT SEARCH</div>
                    </motion.div>
                )}
                {/* Search history — shown when input is focused and empty */}
                {isOpen && !osintLoading && !query.trim() && searchHistory.length > 0 && (
                    <motion.div
                        initial={{ opacity: 0, y: -4 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -4 }}
                        className="absolute top-full left-0 right-0 mt-1 bg-black/90 backdrop-blur-md border border-gray-800 rounded-lg overflow-hidden z-50 shadow-[0_8px_30px_rgba(0,0,0,0.6)]"
                    >
                        <div className="px-3 py-1.5 border-b border-gray-800 bg-black/50 text-[8px] text-gray-500 font-mono tracking-widest flex items-center gap-1.5">
                            <Clock size={8} />
                            RECENT SEARCHES
                        </div>
                        <div className="max-h-[260px] overflow-y-auto styled-scrollbar">
                            {searchHistory.slice(0, 15).map((h, idx) => (
                                <button
                                    key={`hist-${idx}`}
                                    onClick={() => {
                                        setQuery(h.query);
                                        runOsintSearchFor(h.query);
                                    }}
                                    className="w-full flex items-center gap-3 px-3 py-2 hover:bg-cyan-950/20 transition-colors text-left border-b border-gray-800/30 last:border-0 group"
                                >
                                    <div className="flex-shrink-0 w-5 h-5 flex items-center justify-center rounded bg-gray-900 border border-gray-800 group-hover:border-gray-700">
                                        <Clock size={9} className="text-gray-600" />
                                    </div>
                                    <div className="flex-1 min-w-0">
                                        <div className="text-[10px] text-gray-300 font-mono tracking-wide truncate">
                                            {h.query}
                                        </div>
                                        <div className="text-[7px] text-gray-600 font-mono truncate mt-0.5">
                                            {h.tools_run?.slice(0, 4).join(" · ") || "—"}
                                        </div>
                                    </div>
                                    <div className="flex items-center gap-2 flex-shrink-0">
                                        <span className={`text-[7px] font-bold tracking-widest px-1.5 py-0.5 rounded border ${TYPE_BADGE_COLORS[h.type] || "bg-gray-900 text-gray-500 border-gray-700"}`}>
                                            {h.type?.toUpperCase() || "?"}
                                        </span>
                                        <span className="text-[7px] text-gray-600 font-mono w-12 text-right">
                                            {relativeTime(h.timestamp)}
                                        </span>
                                    </div>
                                </button>
                            ))}
                        </div>
                    </motion.div>
                )}
            </AnimatePresence>
        </div>
    );
}
