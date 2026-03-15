"use client";

import React, { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Plane, AlertTriangle, Activity, Satellite, Cctv, ChevronDown, ChevronUp, Ship, Eye, Anchor, Settings, Sun, BookOpen, Radio, ShieldAlert, CloudLightning, Flame, Zap, Wifi, Wind, Radiation, Thermometer, Globe, Shield, Atom, Cable, Building2, Mountain, Skull, Car, Bug, Waves, Signal, Siren, MessageSquare, Monitor, Radar } from "lucide-react";

const CCTV_FILTER_GROUPS: Record<string, string[]> = {
    "TDOT SmartWay": ["TDOT SmartWay"],
    "Clarksville/Ft Campbell": ["Clarksville TN", "KYTC Fort Campbell"],
    "NewsChannel 5": ["NewsChannel 5 Skynet"],
    "WSMV": ["WSMV Channel 4"],
    "Caltrans": ["Caltrans"],
    "FL511": ["FL511"],
    "NYC DOT": ["NYC DOT"],
    "Austin TxDOT": ["Austin TxDOT"],
    "TfL London": ["TfL"],
    "Singapore LTA": ["Singapore LTA"],
    "NPS / Parks": ["NPS Great Smokies", "ResortCams"],
    "LA DOTD 511": ["LA DOTD 511"],
    "LA Weather Cams": ["LA Weather Cam"],
    "Community / Tourist": ["Community Webcam", "Tourist Webcam"],
};

export function agencyMatchesFilter(agency: string, enabledFilters: Record<string, boolean>): boolean {
    for (const [filterName, prefixes] of Object.entries(CCTV_FILTER_GROUPS)) {
        if (prefixes.some(p => agency.startsWith(p))) {
            return enabledFilters[filterName] !== false;
        }
    }
    return true; // show unknown agencies by default
}

const WorldviewLeftPanel = React.memo(function WorldviewLeftPanel({ data, activeLayers, setActiveLayers, onSettingsClick, onLegendClick }: { data: any; activeLayers: any; setActiveLayers: any; onSettingsClick?: () => void; onLegendClick?: () => void }) {
    const [isMinimized, setIsMinimized] = useState(false);
    const [cctvExpanded, setCctvExpanded] = useState(false);

    // Compute ship category counts
    const importantShipCount = data?.ships?.filter((s: any) => ['carrier', 'military_vessel', 'tanker', 'cargo'].includes(s.type))?.length || 0;
    const passengerShipCount = data?.ships?.filter((s: any) => s.type === 'passenger')?.length || 0;
    const civilianShipCount = data?.ships?.filter((s: any) => !['carrier', 'military_vessel', 'tanker', 'cargo', 'passenger'].includes(s.type))?.length || 0;

    const layers = [
        { id: "flights", name: "Commercial Flights", source: "adsb.lol", count: data?.commercial_flights?.length || 0, icon: Plane },
        { id: "private", name: "Private Flights", source: "adsb.lol", count: data?.private_flights?.length || 0, icon: Plane },
        { id: "jets", name: "Private Jets", source: "adsb.lol", count: data?.private_jets?.length || 0, icon: Plane },
        { id: "military", name: "Military Flights", source: "adsb.lol", count: data?.military_flights?.length || 0, icon: AlertTriangle },
        { id: "tracked", name: "Tracked Aircraft", source: "Plane-Alert DB", count: data?.tracked_flights?.length || 0, icon: Eye },
        { id: "earthquakes", name: "Earthquakes (24h)", source: "USGS", count: data?.earthquakes?.length || 0, icon: Activity },
        { id: "satellites", name: "Satellites", source: "CelesTrak SGP4", count: data?.satellites?.length || 0, icon: Satellite },
        { id: "ships_important", name: "Carriers / Mil / Cargo", source: "AIS Stream", count: importantShipCount, icon: Ship },
        { id: "ships_civilian", name: "Civilian Vessels", source: "AIS Stream", count: civilianShipCount, icon: Anchor },
        { id: "ships_passenger", name: "Cruise / Passenger", source: "AIS Stream", count: passengerShipCount, icon: Anchor },
        { id: "ukraine_frontline", name: "Ukraine Frontline", source: "DeepStateMap", count: data?.frontlines ? 1 : 0, icon: AlertTriangle },
        { id: "global_incidents", name: "Global Incidents", source: "GDELT+LiveUAMap", count: (data?.gdelt?.length || 0) + (data?.liveuamap?.length || 0), icon: Activity },
        { id: "cctv", name: "CCTV Mesh", source: "CCTV Mesh + Street View", count: data?.cctv?.length || 0, icon: Cctv },
        { id: "gps_jamming", name: "GPS Jamming", source: "ADS-B NACp", count: data?.gps_jamming?.length || 0, icon: Radio },
        { id: "tfrs", name: "Flight Restrictions (TFR)", source: "FAA GeoServer", count: data?.tfrs?.length || 0, icon: ShieldAlert },
        { id: "weather_alerts", name: "Weather Alerts", source: "NWS", count: data?.weather_alerts?.length || 0, icon: CloudLightning },
        { id: "natural_events", name: "Natural Events", source: "NASA EONET", count: data?.natural_events?.length || 0, icon: Flame },
        { id: "firms_hotspots", name: "Fire Hotspots", source: "NASA FIRMS VIIRS", count: data?.firms_hotspots?.length || 0, icon: Thermometer },
        { id: "power_outages", name: "Power Outages", source: "PowerOutage.us", count: data?.power_outages?.length || 0, icon: Zap },
        { id: "internet_outages", name: "Internet Outages", source: "Cloudflare+IODA+NWS", count: data?.internet_outages?.length || 0, icon: Wifi },
        { id: "air_quality", name: "Air Quality (PM2.5)", source: "OpenAQ", count: data?.air_quality?.length || 0, icon: Wind },
        { id: "space_weather", name: "Space Weather", source: "NOAA SWPC", count: data?.space_weather?.length || 0, icon: Globe },
        { id: "radioactivity", name: "Radiation Monitor", source: "EPA RadNet + EURDEP", count: data?.radioactivity?.length || 0, icon: Radiation },
        { id: "military_bases", name: "Military Bases", source: "DoD + Vine Dataset", count: data?.military_bases?.length || 0, icon: Shield },
        { id: "nuclear_facilities", name: "Nuclear Facilities", source: "IAEA GeoNuclearData", count: data?.nuclear_facilities?.length || 0, icon: Atom },
        { id: "submarine_cables", name: "Submarine Cables", source: "TeleGeography", count: (data?.submarine_cables?.length || 0) + (data?.cable_landing_points?.length || 0), icon: Cable },
        { id: "embassies", name: "Embassies", source: "Wikidata", count: data?.embassies?.length || 0, icon: Building2 },
        { id: "volcanoes", name: "Volcanoes", source: "Smithsonian GVP", count: data?.volcanoes?.length || 0, icon: Mountain },
        { id: "piracy", name: "Piracy / ASAM", source: "NGA ASAM", count: data?.piracy_incidents?.length || 0, icon: Skull },
        { id: "border_crossings", name: "Border Crossings", source: "US CBP", count: data?.border_crossings?.length || 0, icon: Car },
        { id: "cyber_threats", name: "Cyber Threats", source: "abuse.ch", count: data?.cyber_threats?.length || 0, icon: Bug },
        { id: "reservoirs", name: "Reservoirs / Dams", source: "USGS Water", count: data?.reservoirs?.length || 0, icon: Waves },
        { id: "cell_towers", name: "Cell Towers", source: "OpenCelliD", count: data?.cell_towers?.length || 0, icon: Signal },
        { id: "global_events", name: "Global Events", source: "GDACS+ReliefWeb+WHO+FEMA", count: data?.global_events?.length || 0, icon: Siren },
        { id: "social_media", name: "Social Media OSINT", source: "Reddit+Telegram+Mastodon+YouTube+Flickr", count: data?.social_media?.length || 0, icon: MessageSquare },
        { id: "noaa_nwr", name: "NOAA Weather Radio", source: "NWS NWR Network", count: data?.noaa_nwr?.length || 0, icon: Radio },
        { id: "kiwisdr_nodes", name: "KiwiSDR Nodes", source: "KiwiSDR Directory", count: data?.kiwisdr_nodes?.length || 0, icon: Signal },
        { id: "day_night", name: "Day / Night Cycle", source: "Solar Calc", count: null, icon: Sun },
        // OSINT / Local
        { id: "kismet_devices", name: "WiFi/BT Devices", source: "Kismet", count: data?.kismet_devices?.length || 0, icon: Wifi },
        { id: "snort_alerts", name: "IDS Alerts", source: "Snort", count: data?.snort_alerts?.length || 0, icon: ShieldAlert },
        { id: "nmap_hosts", name: "Network Hosts", source: "Nmap", count: data?.nmap_hosts?.length || 0, icon: Monitor },
        { id: "nuclei_vulns", name: "Vulnerabilities", source: "Nuclei", count: data?.nuclei_vulns?.length || 0, icon: Bug },
    ];

    const shipIcon = <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M2 21c.6.5 1.2 1 2.5 1 2.5 0 2.5-2 5-2 1.3 0 1.9.5 2.5 1 .6.5 1.2 1 2.5 1 2.5 0 2.5-2 5-2 1.3 0 1.9.5 2.5 1" /><path d="M19.38 20A11.6 11.6 0 0 0 21 14l-9-4-9 4c0 2.9.94 5.34 2.81 7.76" /><path d="M19 13V7a2 2 0 0 0-2-2H7a2 2 0 0 0-2 2v6" /></svg>;

    return (
        <motion.div
            initial={{ opacity: 0, x: -50 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 1 }}
            className="w-full flex-1 min-h-0 flex flex-col pointer-events-none"
        >
            {/* Header */}
            <div className="mb-6 pointer-events-auto">
                <div className="text-[10px] text-gray-400 font-mono tracking-widest mb-1">TOP SECRET // SI-TK // NOFORN</div>
                <div className="text-[10px] text-gray-500 font-mono tracking-widest mb-4">KH11-4094 OPS-4168</div>
                <div className="flex items-center gap-3">
                    <h1 className="text-2xl font-bold tracking-[0.2em] text-cyan-50">FLIR</h1>
                    {onSettingsClick && (
                        <button
                            onClick={onSettingsClick}
                            className="w-7 h-7 rounded-lg border border-gray-700 hover:border-cyan-500/50 flex items-center justify-center text-gray-500 hover:text-cyan-400 transition-all hover:bg-cyan-950/20 group"
                            title="System Settings"
                        >
                            <Settings size={14} className="group-hover:rotate-90 transition-transform duration-300" />
                        </button>
                    )}
                    {onLegendClick && (
                        <button
                            onClick={onLegendClick}
                            className="h-7 px-2 rounded-lg border border-gray-700 hover:border-cyan-500/50 flex items-center justify-center gap-1 text-gray-500 hover:text-cyan-400 transition-all hover:bg-cyan-950/20"
                            title="Map Legend / Icon Key"
                        >
                            <BookOpen size={12} />
                            <span className="text-[8px] font-mono tracking-widest font-bold">KEY</span>
                        </button>
                    )}
                </div>
            </div>

            {/* Data Layers Box */}
            <div className="bg-black/40 backdrop-blur-md border border-gray-800 rounded-xl pointer-events-auto shadow-[0_4px_30px_rgba(0,0,0,0.5)] flex flex-col relative overflow-hidden max-h-full">

                {/* Header / Toggle */}
                <div
                    className="flex justify-between items-center p-4 cursor-pointer hover:bg-gray-900/50 transition-colors border-b border-gray-800/50"
                >
                    <span className="text-[10px] text-gray-500 font-mono tracking-widest" onClick={() => setIsMinimized(!isMinimized)}>DATA LAYERS</span>
                    <div className="flex items-center gap-3">
                        {(() => {
                            const anyOn = layers.some(l => activeLayers[l.id as keyof typeof activeLayers]);
                            return (
                                <div
                                    onClick={(e) => {
                                        e.stopPropagation();
                                        const updated: any = {};
                                        for (const l of layers) updated[l.id] = !anyOn;
                                        setActiveLayers((prev: any) => ({ ...prev, ...updated }));
                                    }}
                                    className={`text-[9px] font-mono tracking-wider px-2 py-0.5 rounded-full border cursor-pointer transition-all ${anyOn
                                        ? 'border-cyan-500/50 text-cyan-400 bg-cyan-950/30 shadow-[0_0_10px_rgba(34,211,238,0.2)]'
                                        : 'border-gray-800 text-gray-600 bg-transparent'
                                    }`}
                                >
                                    {anyOn ? 'ON' : 'OFF'}
                                </div>
                            );
                        })()}
                        <button className="text-gray-500 hover:text-white transition-colors" onClick={() => setIsMinimized(!isMinimized)}>
                            {isMinimized ? <ChevronDown size={14} /> : <ChevronUp size={14} />}
                        </button>
                    </div>
                </div>

                <AnimatePresence>
                    {!isMinimized && (
                        <motion.div
                            initial={{ height: 0, opacity: 0 }}
                            animate={{ height: "auto", opacity: 1 }}
                            exit={{ height: 0, opacity: 0 }}
                            className="overflow-y-auto styled-scrollbar"
                        >
                            <div className="flex flex-col gap-6 p-4 pt-2 pb-6">
                                {layers.map((layer, idx) => {
                                    const Icon = layer.icon;
                                    const active = activeLayers[layer.id as keyof typeof activeLayers] || false;
                                    const isCctv = layer.id === 'cctv';

                                    return (
                                        <div key={layer.id} className="flex flex-col">
                                            <div
                                                className="flex items-start justify-between group cursor-pointer"
                                                onClick={() => setActiveLayers((prev: any) => ({ ...prev, [layer.id]: !active }))}
                                            >
                                                <div className="flex gap-3">
                                                    <div className={`mt-1 ${active ? 'text-cyan-400' : 'text-gray-600 group-hover:text-gray-400'} transition-colors`}>
                                                        {(['ships_important', 'ships_civilian', 'ships_passenger'].includes(layer.id)) ? shipIcon : <Icon size={16} strokeWidth={1.5} />}
                                                    </div>
                                                    <div className="flex flex-col">
                                                        <span className={`text-sm font-medium ${active ? 'text-white' : 'text-gray-400'} tracking-wide`}>{layer.name}</span>
                                                        <span className="text-[9px] text-gray-600 font-mono tracking-wider mt-0.5">{layer.source} · {active ? 'LIVE' : 'OFF'}</span>
                                                    </div>
                                                </div>
                                                <div className="flex items-center gap-3">
                                                    {active && layer.count > 0 && (
                                                        <span className="text-[10px] text-gray-300 font-mono">{layer.count.toLocaleString()}</span>
                                                    )}
                                                    {isCctv && active && (
                                                        <button
                                                            onClick={(e) => { e.stopPropagation(); setCctvExpanded(!cctvExpanded); }}
                                                            className="text-gray-500 hover:text-cyan-400 transition-colors mr-1"
                                                            title="Filter feeds"
                                                        >
                                                            {cctvExpanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                                                        </button>
                                                    )}
                                                    <div className={`text-[9px] font-mono tracking-wider px-2 py-0.5 rounded-full border ${active
                                                        ? 'border-cyan-500/50 text-cyan-400 bg-cyan-950/30 shadow-[0_0_10px_rgba(34,211,238,0.2)]'
                                                        : 'border-gray-800 text-gray-600 bg-transparent'
                                                        }`}>
                                                        {active ? 'ON' : 'OFF'}
                                                    </div>
                                                </div>
                                            </div>

                                            {/* CCTV Feed Filter Dropdown */}
                                            {isCctv && active && cctvExpanded && (
                                                <motion.div
                                                    initial={{ height: 0, opacity: 0 }}
                                                    animate={{ height: "auto", opacity: 1 }}
                                                    exit={{ height: 0, opacity: 0 }}
                                                    className="ml-8 mt-3 flex flex-col gap-1.5 border-l border-cyan-900/30 pl-3"
                                                >
                                                    <div className="flex items-center justify-between mb-1">
                                                        <span className="text-[8px] text-gray-500 font-mono tracking-widest">FEED SOURCES</span>
                                                        <button
                                                            onClick={(e) => {
                                                                e.stopPropagation();
                                                                const filters = activeLayers.cctvFilters || {};
                                                                const allOn = Object.values(filters).every(Boolean);
                                                                const toggled: Record<string, boolean> = {};
                                                                for (const k of Object.keys(filters)) toggled[k] = !allOn;
                                                                setActiveLayers((prev: any) => ({ ...prev, cctvFilters: toggled }));
                                                            }}
                                                            className="text-[8px] text-gray-500 hover:text-cyan-400 font-mono tracking-wider transition-colors"
                                                        >
                                                            {Object.values(activeLayers.cctvFilters || {}).every(Boolean) ? 'NONE' : 'ALL'}
                                                        </button>
                                                    </div>
                                                    {Object.entries(activeLayers.cctvFilters || {}).map(([filterName, enabled]) => {
                                                        const isOn = enabled as boolean;
                                                        // Count cameras matching this filter
                                                        const count = (data?.cctv || []).filter((c: any) => {
                                                            const agency = c.source_agency || '';
                                                            const prefixes = CCTV_FILTER_GROUPS[filterName] || [];
                                                            return prefixes.some((p: string) => agency.startsWith(p));
                                                        }).length;

                                                        return (
                                                            <div
                                                                key={filterName}
                                                                className="flex items-center justify-between cursor-pointer group/f py-0.5"
                                                                onClick={(e) => {
                                                                    e.stopPropagation();
                                                                    setActiveLayers((prev: any) => ({
                                                                        ...prev,
                                                                        cctvFilters: { ...prev.cctvFilters, [filterName]: !isOn }
                                                                    }));
                                                                }}
                                                            >
                                                                <div className="flex items-center gap-2">
                                                                    <div className={`w-2 h-2 rounded-full border ${isOn
                                                                        ? 'border-green-500 bg-green-500 shadow-[0_0_6px_rgba(34,197,94,0.4)]'
                                                                        : 'border-gray-700 bg-transparent'
                                                                    }`} />
                                                                    <span className={`text-[10px] font-mono tracking-wide ${isOn ? 'text-gray-300' : 'text-gray-600'}`}>
                                                                        {filterName}
                                                                    </span>
                                                                </div>
                                                                <span className={`text-[9px] font-mono ${isOn ? 'text-gray-500' : 'text-gray-700'}`}>
                                                                    {count.toLocaleString()}
                                                                </span>
                                                            </div>
                                                        );
                                                    })}
                                                </motion.div>
                                            )}
                                        </div>
                                    )
                                })}
                            </div>
                        </motion.div>
                    )}
                </AnimatePresence>
            </div>
        </motion.div>
    );
});

export default WorldviewLeftPanel;
