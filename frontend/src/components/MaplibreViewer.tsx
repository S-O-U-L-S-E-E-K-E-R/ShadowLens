"use client";

import { API_BASE } from "@/lib/api";
import React, { useMemo, useState, useEffect, useCallback, useRef } from "react";
import Map, { Source, Layer, MapRef, ViewState, Popup, Marker } from "react-map-gl/maplibre";
import "maplibre-gl/dist/maplibre-gl.css";
import { computeNightPolygon } from "@/utils/solarTerminator";
import ScaleBar from "@/components/ScaleBar";
import maplibregl from "maplibre-gl";
import { AlertTriangle } from "lucide-react";
import WikiImage from "@/components/WikiImage";

const svgPlaneCyan = `data:image/svg+xml;utf8,${encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="cyan" stroke="black"><path d="M21 16v-2l-8-5V3.5c0-.83-.67-1.5-1.5-1.5S10 2.67 10 3.5V9l-8 5v2l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-5.5l8 2.5z" /></svg>`)}`;
const svgPlaneYellow = `data:image/svg+xml;utf8,${encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="yellow" stroke="black"><path d="M21 16v-2l-8-5V3.5c0-.83-.67-1.5-1.5-1.5S10 2.67 10 3.5V9l-8 5v2l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-5.5l8 2.5z" /></svg>`)}`;
const svgPlaneOrange = `data:image/svg+xml;utf8,${encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="#FF8C00" stroke="black"><path d="M21 16v-2l-8-5V3.5c0-.83-.67-1.5-1.5-1.5S10 2.67 10 3.5V9l-8 5v2l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-5.5l8 2.5z" /></svg>`)}`;
const svgPlanePurple = `data:image/svg+xml;utf8,${encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="#9B59B6" stroke="black"><path d="M21 16v-2l-8-5V3.5c0-.83-.67-1.5-1.5-1.5S10 2.67 10 3.5V9l-8 5v2l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-5.5l8 2.5z" /></svg>`)}`;
const svgFighter = `data:image/svg+xml;utf8,${encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="yellow" stroke="black"><path d="M12 2L14 8L18 10L14 16L15 22L12 20L9 22L10 16L6 10L10 8L12 2Z"/></svg>`)}`;
const svgHeli = `data:image/svg+xml;utf8,${encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="yellow" stroke="black"><path d="M10 6L10 14L8 16L8 18L10 17L12 22L14 17L16 18L16 16L14 14L14 6C14 4 13 2 12 2C11 2 10 4 10 6Z"/><circle cx="12" cy="12" r="8" fill="none" stroke="black" stroke-dasharray="2 2" stroke-width="1"/></svg>`)}`;
const svgHeliCyan = `data:image/svg+xml;utf8,${encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="cyan" stroke="black"><path d="M10 6L10 14L8 16L8 18L10 17L12 22L14 17L16 18L16 16L14 14L14 6C14 4 13 2 12 2C11 2 10 4 10 6Z"/><circle cx="12" cy="12" r="8" fill="none" stroke="cyan" stroke-dasharray="2 2" stroke-width="1"/></svg>`)}`;
const svgHeliOrange = `data:image/svg+xml;utf8,${encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="#FF8C00" stroke="black"><path d="M10 6L10 14L8 16L8 18L10 17L12 22L14 17L16 18L16 16L14 14L14 6C14 4 13 2 12 2C11 2 10 4 10 6Z"/><circle cx="12" cy="12" r="8" fill="none" stroke="#FF8C00" stroke-dasharray="2 2" stroke-width="1"/></svg>`)}`;
const svgHeliPurple = `data:image/svg+xml;utf8,${encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="#9B59B6" stroke="black"><path d="M10 6L10 14L8 16L8 18L10 17L12 22L14 17L16 18L16 16L14 14L14 6C14 4 13 2 12 2C11 2 10 4 10 6Z"/><circle cx="12" cy="12" r="8" fill="none" stroke="#9B59B6" stroke-dasharray="2 2" stroke-width="1"/></svg>`)}`;
const svgTanker = `data:image/svg+xml;utf8,${encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="yellow" stroke="black"><path d="M21 16v-2l-8-5V3.5c0-.83-.67-1.5-1.5-1.5S10 2.67 10 3.5V9l-8 5v2l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-5.5l8 2.5z" /><line x1="12" y1="20" x2="12" y2="24" stroke="yellow" stroke-width="2" /></svg>`)}`;
const svgRecon = `data:image/svg+xml;utf8,${encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="yellow" stroke="black"><path d="M21 16v-2l-8-5V3.5c0-.83-.67-1.5-1.5-1.5S10 2.67 10 3.5V9l-8 5v2l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-5.5l8 2.5z" /><ellipse cx="12" cy="11" rx="5" ry="3" fill="none" stroke="red" stroke-width="1.5"/></svg>`)}`;
const svgPlanePink = `data:image/svg+xml;utf8,${encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="#FF1493" stroke="black"><path d="M21 16v-2l-8-5V3.5c0-.83-.67-1.5-1.5-1.5S10 2.67 10 3.5V9l-8 5v2l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-5.5l8 2.5z" /></svg>`)}`;
const svgPlaneAlertRed = `data:image/svg+xml;utf8,${encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="#FF2020" stroke="black"><path d="M21 16v-2l-8-5V3.5c0-.83-.67-1.5-1.5-1.5S10 2.67 10 3.5V9l-8 5v2l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-5.5l8 2.5z" /></svg>`)}`;
const svgPlaneDarkBlue = `data:image/svg+xml;utf8,${encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="#1A3A8A" stroke="#4A80D0"><path d="M21 16v-2l-8-5V3.5c0-.83-.67-1.5-1.5-1.5S10 2.67 10 3.5V9l-8 5v2l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-5.5l8 2.5z" /></svg>`)}`;
const svgPlaneWhiteAlert = `data:image/svg+xml;utf8,${encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="white" stroke="#ff0000" stroke-width="2"><path d="M21 16v-2l-8-5V3.5c0-.83-.67-1.5-1.5-1.5S10 2.67 10 3.5V9l-8 5v2l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-5.5l8 2.5z" /></svg>`)}`;
const svgHeliPink = `data:image/svg+xml;utf8,${encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="#ff66b2" stroke="black"><path d="M10 6L10 14L8 16L8 18L10 17L12 22L14 17L16 18L16 16L14 14L14 6C14 4 13 2 12 2C11 2 10 4 10 6Z"/><circle cx="12" cy="12" r="8" fill="none" stroke="#ff66b2" stroke-dasharray="2 2" stroke-width="1"/></svg>`)}`;
const svgHeliAlertRed = `data:image/svg+xml;utf8,${encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="#ff0000" stroke="black"><path d="M10 6L10 14L8 16L8 18L10 17L12 22L14 17L16 18L16 16L14 14L14 6C14 4 13 2 12 2C11 2 10 4 10 6Z"/><circle cx="12" cy="12" r="8" fill="none" stroke="#ff0000" stroke-dasharray="2 2" stroke-width="1"/></svg>`)}`;
const svgHeliDarkBlue = `data:image/svg+xml;utf8,${encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="#000080" stroke="#4A80D0"><path d="M10 6L10 14L8 16L8 18L10 17L12 22L14 17L16 18L16 16L14 14L14 6C14 4 13 2 12 2C11 2 10 4 10 6Z"/><circle cx="12" cy="12" r="8" fill="none" stroke="#4A80D0" stroke-dasharray="2 2" stroke-width="1"/></svg>`)}`;
const svgHeliWhiteAlert = `data:image/svg+xml;utf8,${encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="white" stroke="#ff0000"><path d="M10 6L10 14L8 16L8 18L10 17L12 22L14 17L16 18L16 16L14 14L14 6C14 4 13 2 12 2C11 2 10 4 10 6Z"/><circle cx="12" cy="12" r="8" fill="none" stroke="#ff0000" stroke-dasharray="2 2" stroke-width="1"/></svg>`)}`;
const svgPlaneBlack = `data:image/svg+xml;utf8,${encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="#222" stroke="#444"><path d="M21 16v-2l-8-5V3.5c0-.83-.67-1.5-1.5-1.5S10 2.67 10 3.5V9l-8 5v2l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-5.5l8 2.5z" /></svg>`)}`;
const svgHeliBlack = `data:image/svg+xml;utf8,${encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="#222" stroke="#444"><path d="M10 6L10 14L8 16L8 18L10 17L12 22L14 17L16 18L16 16L14 14L14 6C14 4 13 2 12 2C11 2 10 4 10 6Z"/><circle cx="12" cy="12" r="8" fill="none" stroke="#444" stroke-dasharray="2 2" stroke-width="1"/></svg>`)}`;
const svgDrone = `data:image/svg+xml;utf8,${encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="orange" stroke="black"><path d="M12 2L15 8H9L12 2Z" /><rect x="8" y="8" width="8" height="2" /><path d="M4 10L10 14H14L20 10V12L14 16H10L4 12V10Z" /><circle cx="12" cy="14" r="2" fill="red"/></svg>`)}`;
const svgShipGray = `data:image/svg+xml;utf8,${encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" width="12" height="24" viewBox="0 0 24 24" fill="none"><path d="M6 20 L6 8 L12 2 L18 8 L18 20 C18 22 6 22 6 20 Z" fill="gray" stroke="#000" stroke-width="1"/><polygon points="12,6 16,16 8,16" fill="#fff" stroke="#000" stroke-width="1"/></svg>`)}`;
const svgShipRed = `data:image/svg+xml;utf8,${encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" width="16" height="32" viewBox="0 0 24 24" fill="none"><path d="M6 22 L6 6 L12 2 L18 6 L18 22 Z" fill="#ff2222" stroke="#000" stroke-width="1"/><rect x="8" y="15" width="8" height="4" fill="#880000" stroke="#000" stroke-width="1"/><rect x="8" y="7" width="8" height="6" fill="#444" stroke="#000" stroke-width="1"/></svg>`)}`;
const svgShipYellow = `data:image/svg+xml;utf8,${encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" width="14" height="34" viewBox="0 0 24 24" fill="none"><path d="M7 22 L7 6 L12 1 L17 6 L17 22 Z" fill="yellow" stroke="#000" stroke-width="1"/><rect x="9" y="8" width="6" height="8" fill="#555" stroke="#000" stroke-width="1"/><circle cx="12" cy="18" r="1.5" fill="#000"/><line x1="12" y1="18" x2="12" y2="24" stroke="#000" stroke-width="1.5"/></svg>`)}`;
const svgShipBlue = `data:image/svg+xml;utf8,${encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" width="16" height="32" viewBox="0 0 24 24" fill="none"><path d="M6 22 L6 6 L12 2 L18 6 L18 22 Z" fill="#3b82f6" stroke="#000" stroke-width="1"/></svg>`)}`;
const svgShipWhite = `data:image/svg+xml;utf8,${encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" width="18" height="36" viewBox="0 0 24 24" fill="none"><path d="M5 21 L5 8 L12 2 L19 8 L19 21 C19 23 5 23 5 21 Z" fill="white" stroke="#000" stroke-width="1"/><rect x="7" y="10" width="10" height="8" fill="#90cdf4" stroke="#000" stroke-width="1"/><circle cx="12" cy="14" r="2" fill="yellow" stroke="#000"/></svg>`)}`;
const svgCarrier = `data:image/svg+xml;utf8,${encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="orange" stroke="black"><polygon points="3,21 21,21 20,4 16,4 16,3 12,3 12,4 4,4" /><rect x="15" y="6" width="3" height="10" /></svg>`)}`;
const svgCctv = `data:image/svg+xml;utf8,${encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="cyan" stroke-width="2"><path d="M16.75 12h3.632a1 1 0 0 1 .894 1.447l-2.034 4.069a1 1 0 0 1-.894.553H5.652a1 1 0 0 1-.894-.553L2.724 13.447A1 1 0 0 1 3.618 12h3.632M14 12V8a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v4a4 4 0 1 0 8 0Z" /></svg>`)}`;
const svgWarning = `data:image/svg+xml;utf8,${encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="yellow" stroke="black"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z" /><path d="M12 9v4" /><path d="M12 17h.01" /></svg>`)}`;
const svgThreat = `data:image/svg+xml;utf8,${encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="#ffff00" stroke="#ff0000" stroke-width="2"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z" /><path d="M12 9v4" /><path d="M12 17h.01" /></svg>`)}`;
const svgTriangleYellow = `data:image/svg+xml;utf8,${encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="#ffaa00" stroke="#000" stroke-width="1"><path d="M1 21h22L12 2 1 21z"/></svg>`)}`;
const svgTriangleRed = `data:image/svg+xml;utf8,${encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="#ff0000" stroke="#fff" stroke-width="1"><path d="M1 21h22L12 2 1 21z"/></svg>`)}`;

// --- Aircraft type-specific SVG paths (top-down silhouettes) ---
// Airliner: wide swept wings with engine pods, narrow fuselage
const AIRLINER_PATH = "M12 2C11.2 2 10.5 2.8 10.5 3.5V8.5L3 13V15L10.5 12.5V18L8 19.5V21L12 19.5L16 21V19.5L13.5 18V12.5L21 15V13L13.5 8.5V3.5C13.5 2.8 12.8 2 12 2Z M5.5 13.5L3.5 14.5 M18.5 13.5L20.5 14.5";
// Turboprop: straight high wings, shorter body
const TURBOPROP_PATH = "M12 3C11.3 3 10.8 3.5 10.8 4V9L3 12V13.5L10.8 11.5V18.5L9 19.5V21L12 20L15 21V19.5L13.2 18.5V11.5L21 13.5V12L13.2 9V4C13.2 3.5 12.7 3 12 3Z";
// Bizjet: sleek, small swept wings, T-tail
const BIZJET_PATH = "M12 1.5C11.4 1.5 11 2 11 2.8V9L5 12.5V14L11 12V18.5L8.5 20V21.5L12 20.5L15.5 21.5V20L13 18.5V12L19 14V12.5L13 9V2.8C13 2 12.6 1.5 12 1.5Z";

function makeAircraftSvg(type: 'airliner' | 'turboprop' | 'bizjet' | 'generic', fill: string, stroke = 'black', size = 20) {
    const paths: Record<string, string> = { airliner: AIRLINER_PATH, turboprop: TURBOPROP_PATH, bizjet: BIZJET_PATH, generic: "M21 16v-2l-8-5V3.5c0-.83-.67-1.5-1.5-1.5S10 2.67 10 3.5V9l-8 5v2l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-5.5l8 2.5z" };
    const p = paths[type] || paths.generic;
    // Airliner gets engine pod circles
    const extras = type === 'airliner' ? `<circle cx="7" cy="12.5" r="1.2" fill="${fill}" stroke="${stroke}" stroke-width="0.5"/><circle cx="17" cy="12.5" r="1.2" fill="${fill}" stroke="${stroke}" stroke-width="0.5"/>` : '';
    return `data:image/svg+xml;utf8,${encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 24 24" fill="${fill}" stroke="${stroke}"><path d="${p}"/>${extras}</svg>`)}`;
}

// Pre-built aircraft SVGs by type & color
const svgAirlinerCyan = makeAircraftSvg('airliner', 'cyan');
const svgAirlinerOrange = makeAircraftSvg('airliner', '#FF8C00');
const svgAirlinerPurple = makeAircraftSvg('airliner', '#9B59B6');
const svgAirlinerYellow = makeAircraftSvg('airliner', 'yellow');
const svgAirlinerPink = makeAircraftSvg('airliner', '#FF1493', 'black', 22);
const svgAirlinerRed = makeAircraftSvg('airliner', '#FF2020', 'black', 22);
const svgAirlinerDarkBlue = makeAircraftSvg('airliner', '#1A3A8A', '#4A80D0', 22);
const svgAirlinerWhite = makeAircraftSvg('airliner', 'white', '#ff0000', 22);

const svgTurbopropCyan = makeAircraftSvg('turboprop', 'cyan');
const svgTurbopropOrange = makeAircraftSvg('turboprop', '#FF8C00');
const svgTurbopropPurple = makeAircraftSvg('turboprop', '#9B59B6');
const svgTurbopropYellow = makeAircraftSvg('turboprop', 'yellow');
const svgTurbopropPink = makeAircraftSvg('turboprop', '#FF1493', 'black', 22);
const svgTurbopropRed = makeAircraftSvg('turboprop', '#FF2020', 'black', 22);
const svgTurbopropDarkBlue = makeAircraftSvg('turboprop', '#1A3A8A', '#4A80D0', 22);
const svgTurbopropWhite = makeAircraftSvg('turboprop', 'white', '#ff0000', 22);

const svgBizjetCyan = makeAircraftSvg('bizjet', 'cyan');
const svgBizjetOrange = makeAircraftSvg('bizjet', '#FF8C00');
const svgBizjetPurple = makeAircraftSvg('bizjet', '#9B59B6');
const svgBizjetYellow = makeAircraftSvg('bizjet', 'yellow');
const svgBizjetPink = makeAircraftSvg('bizjet', '#FF1493', 'black', 22);
const svgBizjetRed = makeAircraftSvg('bizjet', '#FF2020', 'black', 22);
const svgBizjetDarkBlue = makeAircraftSvg('bizjet', '#1A3A8A', '#4A80D0', 22);
const svgBizjetWhite = makeAircraftSvg('bizjet', 'white', '#ff0000', 22);

// Grey variants for grounded/parked aircraft (altitude 0)
const svgAirlinerGrey = makeAircraftSvg('airliner', '#555', '#333');
const svgTurbopropGrey = makeAircraftSvg('turboprop', '#555', '#333');
const svgBizjetGrey = makeAircraftSvg('bizjet', '#555', '#333');
const svgHeliGrey = `data:image/svg+xml;utf8,${encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="#555" stroke="#333"><path d="M10 6L10 14L8 16L8 18L10 17L12 22L14 17L16 18L16 16L14 14L14 6C14 4 13 2 12 2C11 2 10 4 10 6Z"/><circle cx="12" cy="12" r="8" fill="none" stroke="#555" stroke-dasharray="2 2" stroke-width="1"/></svg>`)}`;

// Grey icon map for grounded aircraft
const GROUNDED_ICON_MAP: Record<string, string> = { heli: 'svgHeliGrey', turboprop: 'svgTurbopropGrey', bizjet: 'svgBizjetGrey', airliner: 'svgAirlinerGrey' };

// ICAO type code -> aircraft shape classification
const HELI_TYPES = new Set(['R22', 'R44', 'R66', 'B06', 'B05', 'B47G', 'B105', 'B212', 'B222', 'B230', 'B407', 'B412', 'B429', 'B430', 'B505', 'BK17', 'S55', 'S58', 'S61', 'S64', 'S70', 'S76', 'S92', 'A109', 'A119', 'A139', 'A169', 'A189', 'AW09', 'EC20', 'EC25', 'EC30', 'EC35', 'EC45', 'EC55', 'EC75', 'H125', 'H130', 'H135', 'H145', 'H155', 'H160', 'H175', 'H215', 'H225', 'AS32', 'AS35', 'AS50', 'AS55', 'AS65', 'MD52', 'MD60', 'MDHI', 'MD90', 'NOTR', 'HUEY', 'GAMA', 'CABR', 'EXE', 'R300', 'R480', 'LAMA', 'ALLI', 'PUMA', 'NH90', 'CH47', 'UH1', 'UH60', 'AH64', 'MI8', 'MI24', 'MI26', 'MI28', 'KA52', 'K32', 'LYNX', 'WILD', 'MRLX', 'A149', 'A119']);
const TURBOPROP_TYPES = new Set(['AT43', 'AT45', 'AT72', 'AT73', 'AT75', 'AT76', 'B190', 'B350', 'BE20', 'BE30', 'BE40', 'BE9L', 'BE99', 'C130', 'C160', 'C208', 'C212', 'C295', 'CN35', 'D228', 'D328', 'DHC2', 'DHC3', 'DHC4', 'DHC5', 'DHC6', 'DHC7', 'DHC8', 'DO28', 'DH8A', 'DH8B', 'DH8C', 'DH8D', 'E110', 'E120', 'F27', 'F406', 'F50', 'G159', 'G73T', 'J328', 'JS31', 'JS32', 'JS41', 'L188', 'MA60', 'M28', 'N262', 'P68', 'P180', 'PA31', 'PA42', 'PC12', 'PC21', 'PC24', 'S2', 'S340', 'SF34', 'SF50', 'SW4', 'TRIS', 'TBM7', 'TBM8', 'TBM9', 'C30J', 'C5M', 'AN12', 'AN24', 'AN26', 'AN30', 'AN32', 'IL18', 'L410', 'Y12', 'BALL', 'AEST', 'AC68', 'AC80', 'AC90', 'AC95', 'AC11', 'C172', 'C182', 'C206', 'C210', 'C310', 'C337', 'C402', 'C414', 'C421', 'C425', 'C441', 'M20P', 'M20T', 'PA28', 'PA32', 'PA34', 'PA44', 'PA46', 'PA60', 'P28A', 'P28B', 'P28R', 'P32R', 'P46T', 'SR20', 'SR22', 'DA40', 'DA42', 'DA62', 'RV10', 'BE33', 'BE35', 'BE36', 'BE55', 'BE58', 'DR40', 'TB20', 'AA5']);
const BIZJET_TYPES = new Set(['ASTR', 'C25A', 'C25B', 'C25C', 'C25M', 'C500', 'C501', 'C510', 'C525', 'C526', 'C550', 'C551', 'C560', 'C56X', 'C650', 'C680', 'C700', 'C750', 'CL30', 'CL35', 'CL60', 'CONI', 'CRJX', 'E35L', 'E45X', 'E50P', 'E55P', 'F2TH', 'F900', 'FA10', 'FA20', 'FA50', 'FA7X', 'FA8X', 'G100', 'G150', 'G200', 'G280', 'GA5C', 'GA6C', 'GALX', 'GL5T', 'GL7T', 'GLEX', 'GLF2', 'GLF3', 'GLF4', 'GLF5', 'GLF6', 'H25A', 'H25B', 'H25C', 'HA4T', 'HDJT', 'LJ23', 'LJ24', 'LJ25', 'LJ28', 'LJ31', 'LJ35', 'LJ40', 'LJ45', 'LJ55', 'LJ60', 'LJ70', 'LJ75', 'MU30', 'PC24', 'PRM1', 'SBR1', 'SBR2', 'WW24', 'BE40', 'BLCF']);

function classifyAircraft(model: string, category?: string): 'heli' | 'turboprop' | 'bizjet' | 'airliner' {
    const m = (model || '').toUpperCase();
    if (category === 'heli' || HELI_TYPES.has(m)) return 'heli';
    if (BIZJET_TYPES.has(m)) return 'bizjet';
    if (TURBOPROP_TYPES.has(m)) return 'turboprop';
    return 'airliner';
}

// --- Smooth position interpolation helpers ---
// Given heading (degrees) and speed (knots), compute new lat/lng after dt seconds
function interpolatePosition(lat: number, lng: number, headingDeg: number, speedKnots: number, dtSeconds: number, maxDist = 0, maxDt = 65): [number, number] {
    if (!speedKnots || speedKnots <= 0 || dtSeconds <= 0) return [lat, lng];
    // Cap interpolation time to prevent runaway drift when data is stale
    const clampedDt = Math.min(dtSeconds, maxDt);
    // 1 knot = 1 nautical mile/hour = 1852 m/h
    const speedMps = speedKnots * 0.5144; // meters per second
    const dist = maxDist > 0 ? Math.min(speedMps * clampedDt, maxDist) : speedMps * clampedDt;
    const R = 6371000; // Earth radius in meters
    const headingRad = (headingDeg * Math.PI) / 180;
    const latRad = (lat * Math.PI) / 180;
    const lngRad = (lng * Math.PI) / 180;
    const newLatRad = Math.asin(
        Math.sin(latRad) * Math.cos(dist / R) +
        Math.cos(latRad) * Math.sin(dist / R) * Math.cos(headingRad)
    );
    const newLngRad = lngRad + Math.atan2(
        Math.sin(headingRad) * Math.sin(dist / R) * Math.cos(latRad),
        Math.cos(dist / R) - Math.sin(latRad) * Math.sin(newLatRad)
    );
    return [(newLatRad * 180) / Math.PI, (newLngRad * 180) / Math.PI];
}

const darkStyle = {
    version: 8,
    glyphs: "https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf",
    sources: {
        'carto-dark': {
            type: 'raster',
            tiles: [
                "https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}@2x.png",
                "https://b.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}@2x.png",
                "https://c.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}@2x.png",
                "https://d.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}@2x.png"
            ],
            tileSize: 256
        }
    },
    layers: [
        {
            id: 'carto-dark-layer',
            type: 'raster',
            source: 'carto-dark',
            minzoom: 0,
            maxzoom: 22
        }
    ]
};

// Satellite icon SVG builder — module-level constant (no re-creation per render)
const makeSatSvg = (color: string) => {
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24">
        <rect x="9" y="9" width="6" height="6" rx="1" fill="${color}" stroke="#0a0e1a" stroke-width="0.5"/>
        <rect x="1" y="10" width="7" height="4" rx="1" fill="${color}" opacity="0.7" stroke="#0a0e1a" stroke-width="0.3"/>
        <rect x="16" y="10" width="7" height="4" rx="1" fill="${color}" opacity="0.7" stroke="#0a0e1a" stroke-width="0.3"/>
        <line x1="8" y1="12" x2="1" y2="12" stroke="${color}" stroke-width="0.8"/>
        <line x1="16" y1="12" x2="23" y2="12" stroke="${color}" stroke-width="0.8"/>
        <circle cx="12" cy="12" r="1.5" fill="#fff" opacity="0.8"/>
    </svg>`;
    return 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg);
};
const MISSION_COLORS: Record<string, string> = {
    'military_recon': '#ff3333', 'military_sar': '#ff3333',
    'sar': '#00e5ff', 'sigint': '#ffffff',
    'navigation': '#4488ff', 'early_warning': '#ff00ff',
    'commercial_imaging': '#44ff44', 'space_station': '#ffdd00'
};
const MISSION_ICON_MAP: Record<string, string> = {
    'military_recon': 'sat-mil', 'military_sar': 'sat-mil',
    'sar': 'sat-sar', 'sigint': 'sat-sigint',
    'navigation': 'sat-nav', 'early_warning': 'sat-ew',
    'commercial_imaging': 'sat-com', 'space_station': 'sat-station'
};

// --- Entity Popup Card: floating info card shown on map at click location ---
const EntityPopupCard = ({ type, props }: { type: string; props: Record<string, any> }) => {
    const isFlight = type?.includes('flight') || type === 'military_air' || type === 'heli' || type === 'uav';
    const isShip = type === 'ship';
    const isEarthquake = type === 'earthquake' || type === 'eq';
    const isOsint = type === 'osint' || type === 'recon' || type === 'subdomain';

    const accentColor = isFlight ? 'text-cyan-400' :
        isShip ? 'text-blue-400' :
        isEarthquake ? 'text-red-400' :
        isOsint ? 'text-green-400' :
        (type === 'military_air' || type === 'military') ? 'text-red-400' :
        'text-gray-300';

    const borderColor = isFlight ? 'border-cyan-700/60' :
        isShip ? 'border-blue-700/60' :
        isEarthquake ? 'border-red-700/60' :
        isOsint ? 'border-green-700/60' :
        'border-gray-700/60';

    if (isFlight) {
        return (
            <div className={`bg-gray-950/95 border ${borderColor} rounded px-2 py-1.5 font-mono min-w-[180px] max-w-[260px]`}>
                <div className={`${accentColor} font-bold text-[11px] tracking-wide truncate`}>{props.callsign || props.name || 'UNKNOWN'}</div>
                {(props.model || props.airline) && (
                    <div className="text-gray-400 text-[9px] truncate">{[props.model, props.airline].filter(Boolean).join(' / ')}</div>
                )}
                <div className="flex gap-3 mt-0.5">
                    {props.alt != null && <span className="text-[9px] text-gray-500">ALT <span className="text-green-400">{Number(props.alt).toLocaleString()}ft</span></span>}
                    {props.speed != null && <span className="text-[9px] text-gray-500">SPD <span className="text-cyan-300">{props.speed}kn</span></span>}
                </div>
                {(props.registration || props.icao24) && (
                    <div className="text-[9px] text-gray-500 mt-0.5 truncate">
                        {props.registration && <span>REG {props.registration} </span>}
                        {props.icao24 && <span>ICAO {props.icao24}</span>}
                    </div>
                )}
            </div>
        );
    }

    if (isShip) {
        return (
            <div className={`bg-gray-950/95 border ${borderColor} rounded px-2 py-1.5 font-mono min-w-[180px] max-w-[260px]`}>
                <div className={`${accentColor} font-bold text-[11px] tracking-wide truncate`}>{props.name || props.shipname || 'UNKNOWN VESSEL'}</div>
                {(props.ship_type || props.flag) && (
                    <div className="text-gray-400 text-[9px] truncate">{[props.ship_type, props.flag].filter(Boolean).join(' / ')}</div>
                )}
                {props.destination && <div className="text-[9px] text-gray-500 mt-0.5">DEST <span className="text-blue-300">{props.destination}</span></div>}
                <div className="flex gap-3 mt-0.5">
                    {props.mmsi && <span className="text-[9px] text-gray-500">MMSI <span className="text-white">{props.mmsi}</span></span>}
                    {props.speed != null && <span className="text-[9px] text-gray-500">SPD <span className="text-blue-300">{props.speed}kn</span></span>}
                </div>
            </div>
        );
    }

    if (isEarthquake) {
        return (
            <div className={`bg-gray-950/95 border ${borderColor} rounded px-2 py-1.5 font-mono min-w-[180px] max-w-[260px]`}>
                <div className="flex items-center gap-2">
                    <span className={`${accentColor} font-bold text-[12px]`}>M{props.mag || props.magnitude || '?'}</span>
                    <span className="text-gray-400 text-[9px] truncate flex-1">{props.place || props.location || 'Unknown location'}</span>
                </div>
                <div className="flex gap-3 mt-0.5">
                    {props.depth != null && <span className="text-[9px] text-gray-500">DEPTH <span className="text-orange-400">{props.depth}km</span></span>}
                    {props.time && <span className="text-[9px] text-gray-500 truncate">{new Date(props.time).toLocaleString()}</span>}
                </div>
            </div>
        );
    }

    if (isOsint) {
        return (
            <div className={`bg-gray-950/95 border ${borderColor} rounded px-2 py-1.5 font-mono min-w-[180px] max-w-[260px]`}>
                <div className={`${accentColor} font-bold text-[11px] tracking-wide truncate`}>{props.target || props.name || 'OSINT Result'}</div>
                {props.tool && <div className="text-gray-400 text-[9px]">VIA <span className="text-green-300">{props.tool}</span></div>}
                {props.finding && <div className="text-[9px] text-gray-400 mt-0.5 truncate">{props.finding}</div>}
            </div>
        );
    }

    // Generic fallback
    return (
        <div className={`bg-gray-950/95 border ${borderColor} rounded px-2 py-1.5 font-mono min-w-[180px] max-w-[260px]`}>
            <div className={`${accentColor} font-bold text-[11px] tracking-wide truncate`}>{props.name || props.title || props.callsign || props.id || 'Entity'}</div>
            <div className="inline-block bg-gray-800 text-gray-400 text-[8px] px-1 rounded mt-0.5">{type}</div>
            {props.description && <div className="text-[9px] text-gray-400 mt-0.5 truncate">{props.description}</div>}
            {props.country && <div className="text-[9px] text-gray-500 mt-0.5">{props.country}</div>}
        </div>
    );
};

// Helper: find entity by stable ID (icao24/mmsi) instead of array index
function findFlight(arr: any[] | undefined, id: string | number): any {
    if (!arr) return undefined;
    return arr.find((f: any) => f.icao24 === id) ?? arr[id as number];
}
function findShip(arr: any[] | undefined, id: string | number): any {
    if (!arr) return undefined;
    return arr.find((s: any) => (s.mmsi && s.mmsi === id) || (s.imo && s.imo === id)) ?? arr[id as number];
}

const MaplibreViewer = ({ data, activeLayers, onEntityClick, flyToLocation, selectedEntity, onMouseCoords, onRightClick, onMiddleClick, regionDossier, regionDossierLoading, onViewStateChange, measureMode, onMeasureClick, measurePoints, regionalFocus, pinnedLocations, onClearPins, onRemovePin }: any) => {
    const mapRef = useRef<MapRef>(null);

    const [viewState, setViewState] = useState<ViewState>({
        longitude: 0,
        latitude: 20,
        zoom: 2,
        bearing: 0,
        pitch: 0,
        padding: { top: 0, bottom: 0, left: 0, right: 0 }
    });

    // Viewport bounds for culling off-screen features [west, south, east, north]
    // Buffer extends bounds by ~20% so features near edges don't pop in/out
    const [mapBounds, setMapBounds] = useState<[number, number, number, number]>([-180, -90, 180, 90]);
    const boundsTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

    const updateBounds = useCallback(() => {
        const map = mapRef.current?.getMap();
        if (!map) return;
        const b = map.getBounds();
        const latRange = b.getNorth() - b.getSouth();
        const lngRange = b.getEast() - b.getWest();
        const buf = 0.2; // 20% buffer
        setMapBounds([
            b.getWest() - lngRange * buf,
            b.getSouth() - latRange * buf,
            b.getEast() + lngRange * buf,
            b.getNorth() + latRange * buf
        ]);
    }, []);

    // Fast bounds check — used by all GeoJSON builders and Marker loops
    const inView = useCallback((lat: number, lng: number) =>
        lng >= mapBounds[0] && lng <= mapBounds[2] && lat >= mapBounds[1] && lat <= mapBounds[3],
        [mapBounds]
    );

    const [dynamicRoute, setDynamicRoute] = useState<any>(null);
    const prevCallsign = useRef<string | null>(null);
    const [shipClusters, setShipClusters] = useState<any[]>([]);
    const [eqClusters, setEqClusters] = useState<any[]>([]);

    // --- Smooth interpolation: tick counter triggers GeoJSON recalc every second ---
    const [interpTick, setInterpTick] = useState(0);
    const dataTimestamp = useRef<number>(Date.now());

    // Track when flight/ship/satellite data actually changes (new fetch arrived)
    useEffect(() => {
        dataTimestamp.current = Date.now();
    }, [data?.commercial_flights, data?.ships, data?.satellites]);

    // Tick every 2s between data refreshes to animate positions
    // Satellites move ~7km/s so need frequent updates for smooth motion
    useEffect(() => {
        const timer = setInterval(() => setInterpTick(t => t + 1), 2000);
        return () => clearInterval(timer);
    }, []);

    // --- Solar Terminator: recompute the night polygon every 60 seconds ---
    const [nightGeoJSON, setNightGeoJSON] = useState<any>(() => computeNightPolygon());

    // Entity popup card state — floating info card on the map at click location
    const [entityPopup, setEntityPopup] = useState<{
        lat: number;
        lng: number;
        type: string;
        props: Record<string, any>;
    } | null>(null);
    useEffect(() => {
        const timer = setInterval(() => setNightGeoJSON(computeNightPolygon()), 60000);
        return () => clearInterval(timer);
    }, []);

    useEffect(() => {
        let isMounted = true;

        let callsign = null;
        if (selectedEntity && data) {
            let entity = null;
            if (selectedEntity.type === 'flight') entity = findFlight(data?.commercial_flights, selectedEntity.id);
            else if (selectedEntity.type === 'private_flight') entity = findFlight(data?.private_flights, selectedEntity.id);
            else if (selectedEntity.type === 'military_flight') entity = findFlight(data?.military_flights, selectedEntity.id);
            else if (selectedEntity.type === 'private_jet') entity = findFlight(data?.private_jets, selectedEntity.id);

            if (entity && entity.callsign) {
                callsign = entity.callsign;
            }
        }

        if (callsign && callsign !== prevCallsign.current) {
            prevCallsign.current = callsign;
            fetch(`${API_BASE}/api/route/${callsign}`)
                .then(res => res.json())
                .then(routeData => {
                    if (isMounted) setDynamicRoute(routeData);
                })
                .catch(() => {
                    if (isMounted) setDynamicRoute(null);
                });
        } else if (!callsign) {
            prevCallsign.current = null;
            if (isMounted) setDynamicRoute(null);
        }

        return () => { isMounted = false; };
    }, [selectedEntity, data]);

    useEffect(() => {
        if (flyToLocation && mapRef.current) {
            mapRef.current.flyTo({
                center: [flyToLocation.lng, flyToLocation.lat],
                zoom: 8,
                duration: 1500
            });
        }
    }, [flyToLocation]);

    const earthquakesGeoJSON = useMemo(() => {
        if (!activeLayers.earthquakes || !data?.earthquakes) return null;
        return {
            type: 'FeatureCollection',
            features: data.earthquakes.map((eq: any, i: number) => {
                if (eq.lat == null || eq.lng == null) return null;
                return {
                    type: 'Feature',
                    properties: {
                        id: i,
                        type: 'earthquake',
                        name: `[M${eq.mag}]\n${eq.place || 'Unknown Location'}`,
                        title: eq.title
                    },
                    geometry: { type: 'Point', coordinates: [eq.lng, eq.lat] }
                };
            }).filter(Boolean)
        };
    }, [activeLayers.earthquakes, data?.earthquakes]);

    // GPS Jamming zones — 1°×1° grid squares colored by severity
    const jammingGeoJSON = useMemo(() => {
        if (!activeLayers.gps_jamming || !data?.gps_jamming?.length) return null;
        return {
            type: 'FeatureCollection' as const,
            features: data.gps_jamming.map((zone: any, i: number) => {
                const halfDeg = 0.5;
                const lat = zone.lat;
                const lng = zone.lng;
                return {
                    type: 'Feature' as const,
                    properties: {
                        id: i,
                        severity: zone.severity,
                        ratio: zone.ratio,
                        degraded: zone.degraded,
                        total: zone.total,
                        opacity: zone.severity === 'high' ? 0.45 : zone.severity === 'medium' ? 0.3 : 0.18
                    },
                    geometry: {
                        type: 'Polygon' as const,
                        coordinates: [[
                            [lng - halfDeg, lat - halfDeg],
                            [lng + halfDeg, lat - halfDeg],
                            [lng + halfDeg, lat + halfDeg],
                            [lng - halfDeg, lat + halfDeg],
                            [lng - halfDeg, lat - halfDeg]
                        ]]
                    }
                };
            })
        };
    }, [activeLayers.gps_jamming, data?.gps_jamming]);

    // FAA TFRs — red/orange polygons showing flight restrictions
    const tfrGeoJSON = useMemo(() => {
        if (!activeLayers.tfrs || !data?.tfrs?.length) return null;
        return {
            type: 'FeatureCollection' as const,
            features: data.tfrs.filter((t: any) => t.geometry).map((t: any) => ({
                type: 'Feature' as const,
                properties: {
                    id: t.id,
                    type: 'tfr',
                    title: t.title || '',
                    legal: t.type || 'TFR',
                    state: t.state || '',
                },
                geometry: t.geometry
            }))
        };
    }, [activeLayers.tfrs, data?.tfrs]);

    // NWS Weather Alerts — yellow/red polygons
    const weatherAlertGeoJSON = useMemo(() => {
        if (!activeLayers.weather_alerts || !data?.weather_alerts?.length) return null;
        return {
            type: 'FeatureCollection' as const,
            features: data.weather_alerts.filter((a: any) => a.geometry).map((a: any) => ({
                type: 'Feature' as const,
                properties: {
                    id: a.id,
                    type: 'weather_alert',
                    event: a.event || '',
                    severity: a.severity || '',
                    headline: a.headline || '',
                    sender: a.sender || '',
                },
                geometry: a.geometry
            }))
        };
    }, [activeLayers.weather_alerts, data?.weather_alerts]);

    // NASA EONET natural events — fire/volcano/storm markers
    const naturalEventGeoJSON = useMemo(() => {
        if (!activeLayers.natural_events || !data?.natural_events?.length) return null;
        return {
            type: 'FeatureCollection' as const,
            features: data.natural_events.filter((e: any) => e.lat != null && e.lon != null).map((e: any) => ({
                type: 'Feature' as const,
                properties: {
                    id: e.id,
                    type: 'natural_event',
                    title: e.title || '',
                    category: e.category || '',
                    category_id: e.category_id || '',
                    date: e.date || '',
                },
                geometry: { type: 'Point' as const, coordinates: [e.lon, e.lat] }
            }))
        };
    }, [activeLayers.natural_events, data?.natural_events]);

    // NASA FIRMS fire hotspots — orange/red heat dots
    const firmsGeoJSON = useMemo(() => {
        if (!activeLayers.firms_hotspots || !data?.firms_hotspots?.length) return null;
        return {
            type: 'FeatureCollection' as const,
            features: data.firms_hotspots.filter((h: any) => h.lat != null && h.lon != null).map((h: any) => ({
                type: 'Feature' as const,
                properties: {
                    id: `firms-${h.lat}-${h.lon}`,
                    type: 'firms_hotspot',
                    name: `Fire ${h.confidence} confidence`,
                    confidence: h.confidence || '',
                    frp: h.frp || 0,
                    brightness: h.brightness || 0,
                    satellite: h.satellite || '',
                    date: h.date || '',
                },
                geometry: { type: 'Point' as const, coordinates: [h.lon, h.lat] }
            }))
        };
    }, [activeLayers.firms_hotspots, data?.firms_hotspots]);

    // Power outages — yellow/red scaled circles
    const powerOutageGeoJSON = useMemo(() => {
        if (!activeLayers.power_outages || !data?.power_outages?.length) return null;
        return {
            type: 'FeatureCollection' as const,
            features: data.power_outages.filter((o: any) => o.lat && o.lon).map((o: any) => ({
                type: 'Feature' as const,
                properties: {
                    id: o.id || '',
                    type: 'power_outage',
                    name: o.headline || `${o.event || o.county || ''} — ${o.state || ''}`,
                    customers_out: o.customers_out || 0,
                    pct_out: o.pct_out || 0,
                    severity: o.severity || '',
                    event: o.event || '',
                },
                geometry: o.geometry || { type: 'Point' as const, coordinates: [o.lon, o.lat] }
            }))
        };
    }, [activeLayers.power_outages, data?.power_outages]);

    // Internet outages — red/orange pulsing circles by severity
    const internetOutageGeoJSON = useMemo(() => {
        if (!activeLayers.internet_outages || !data?.internet_outages?.length) return null;
        return {
            type: 'FeatureCollection' as const,
            features: data.internet_outages.filter((o: any) => o.lat && o.lon).map((o: any) => ({
                type: 'Feature' as const,
                properties: {
                    id: o.id || '',
                    type: 'internet_outage',
                    name: o.description || `Internet outage — ${o.country || ''}`,
                    country: o.country || '',
                    event_type: o.event_type || '',
                    severity: o.severity || '',
                    source: o.source || '',
                    start: o.start || '',
                    end: o.end || '',
                    scope: o.scope || '',
                    description: o.description || '',
                },
                geometry: o.geometry || { type: 'Point' as const, coordinates: [o.lon, o.lat] }
            }))
        };
    }, [activeLayers.internet_outages, data?.internet_outages]);

    // Air quality — colored circles by pollution level
    const aqiGeoJSON = useMemo(() => {
        if (!activeLayers.air_quality || !data?.air_quality?.length) return null;
        return {
            type: 'FeatureCollection' as const,
            features: data.air_quality.filter((s: any) => s.lat != null && s.lon != null).map((s: any) => ({
                type: 'Feature' as const,
                properties: {
                    id: s.id || '',
                    type: 'air_quality',
                    name: `${s.name} — PM2.5: ${s.pm25}`,
                    pm25: s.pm25 || 0,
                    level: s.level || '',
                    city: s.city || '',
                    country: s.country || '',
                },
                geometry: { type: 'Point' as const, coordinates: [s.lon, s.lat] }
            }))
        };
    }, [activeLayers.air_quality, data?.air_quality]);

    // Radioactivity monitoring stations — green/yellow/red
    const radioactivityGeoJSON = useMemo(() => {
        if (!activeLayers.radioactivity || !data?.radioactivity?.length) return null;
        return {
            type: 'FeatureCollection' as const,
            features: data.radioactivity.filter((s: any) => s.lat && s.lon).map((s: any) => ({
                type: 'Feature' as const,
                properties: {
                    id: s.id || '',
                    type: 'radioactivity',
                    name: `${s.name} — ${s.value} ${s.unit}`,
                    value: s.value || 0,
                    unit: s.unit || '',
                    source: s.source || '',
                    country: s.country || '',
                },
                geometry: { type: 'Point' as const, coordinates: [s.lon, s.lat] }
            }))
        };
    }, [activeLayers.radioactivity, data?.radioactivity]);

    // Military bases — shield icons
    const milBasesGeoJSON = useMemo(() => {
        if (!activeLayers.military_bases || !data?.military_bases?.length) return null;
        return {
            type: 'FeatureCollection' as const,
            features: data.military_bases.filter((b: any) => b.lat && b.lon).map((b: any) => ({
                type: 'Feature' as const,
                properties: {
                    id: b.id,
                    type: 'military_base',
                    name: b.name || '',
                    country: b.country || '',
                    branch: b.branch || '',
                    base_type: b.base_type || '',
                    notes: b.notes || '',
                },
                geometry: { type: 'Point' as const, coordinates: [b.lon, b.lat] }
            }))
        };
    }, [activeLayers.military_bases, data?.military_bases]);

    // Nuclear facilities — radiation warning circles
    const nuclearGeoJSON = useMemo(() => {
        if (!activeLayers.nuclear_facilities || !data?.nuclear_facilities?.length) return null;
        return {
            type: 'FeatureCollection' as const,
            features: data.nuclear_facilities.filter((f: any) => f.lat && f.lon).map((f: any) => ({
                type: 'Feature' as const,
                properties: {
                    id: f.id,
                    type: 'nuclear_facility',
                    name: f.name || '',
                    country: f.country || '',
                    status: f.status || '',
                    reactor_type: f.reactor_type || '',
                    reactor_model: f.reactor_model || '',
                    capacity_mw: f.capacity_mw || '',
                    operational_from: f.operational_from || '',
                    iaea_id: f.iaea_id || '',
                },
                geometry: { type: 'Point' as const, coordinates: [f.lon, f.lat] }
            }))
        };
    }, [activeLayers.nuclear_facilities, data?.nuclear_facilities]);

    // Submarine cables — line geometries
    const cableGeoJSON = useMemo(() => {
        if (!activeLayers.submarine_cables || !data?.submarine_cables?.length) return null;
        return {
            type: 'FeatureCollection' as const,
            features: data.submarine_cables.filter((c: any) => c.geometry).map((c: any) => ({
                type: 'Feature' as const,
                properties: {
                    id: c.id,
                    type: 'submarine_cable',
                    name: c.name || '',
                    color: c.color || '#3b82f6',
                },
                geometry: c.geometry
            }))
        };
    }, [activeLayers.submarine_cables, data?.submarine_cables]);

    // Cable landing points
    const cableLandingGeoJSON = useMemo(() => {
        if (!activeLayers.submarine_cables || !data?.cable_landing_points?.length) return null;
        return {
            type: 'FeatureCollection' as const,
            features: data.cable_landing_points.filter((lp: any) => lp.lat && lp.lon).map((lp: any) => ({
                type: 'Feature' as const,
                properties: {
                    id: lp.id,
                    type: 'cable_landing',
                    name: lp.name || '',
                },
                geometry: { type: 'Point' as const, coordinates: [lp.lon, lp.lat] }
            }))
        };
    }, [activeLayers.submarine_cables, data?.cable_landing_points]);

    // Embassies — diplomatic facility markers
    const embassyGeoJSON = useMemo(() => {
        if (!activeLayers.embassies || !data?.embassies?.length) return null;
        return {
            type: 'FeatureCollection' as const,
            features: data.embassies.filter((e: any) => e.lat && e.lon && inView(e.lat, e.lon)).map((e: any) => ({
                type: 'Feature' as const,
                properties: {
                    id: e.id,
                    type: 'embassy',
                    name: e.name || '',
                    country: e.country || '',
                    city: e.city || '',
                    emb_type: e.type || '',
                    jurisdiction: e.jurisdiction || '',
                    address: e.address || '',
                },
                geometry: { type: 'Point' as const, coordinates: [e.lon, e.lat] }
            }))
        };
    }, [activeLayers.embassies, data?.embassies, mapBounds]);

    // Volcanoes — red/orange triangles
    const volcanoGeoJSON = useMemo(() => {
        if (!activeLayers.volcanoes || !data?.volcanoes?.length) return null;
        return {
            type: 'FeatureCollection' as const,
            features: data.volcanoes.filter((v: any) => v.lat && v.lon).map((v: any) => ({
                type: 'Feature' as const,
                properties: {
                    id: v.id, type: 'volcano', name: v.name || '',
                    country: v.country || '', elevation: v.elevation || 0,
                    volcano_type: v.type || '', last_eruption: v.last_eruption || '',
                    region: v.region || '', tectonic: v.tectonic || '', rock_type: v.rock_type || '',
                },
                geometry: { type: 'Point' as const, coordinates: [v.lon, v.lat] }
            }))
        };
    }, [activeLayers.volcanoes, data?.volcanoes]);

    // Piracy incidents — skull markers
    const piracyGeoJSON = useMemo(() => {
        if (!activeLayers.piracy || !data?.piracy_incidents?.length) return null;
        return {
            type: 'FeatureCollection' as const,
            features: data.piracy_incidents.filter((p: any) => p.lat && p.lon).map((p: any) => ({
                type: 'Feature' as const,
                properties: {
                    id: p.id, type: 'piracy', name: p.reference || '',
                    date: p.date || '', hostility: p.hostility || '',
                    victim: p.victim || '', description: p.description || '',
                    subregion: p.subregion || '', navarea: p.navarea || '',
                },
                geometry: { type: 'Point' as const, coordinates: [p.lon, p.lat] }
            }))
        };
    }, [activeLayers.piracy, data?.piracy_incidents]);

    // Reservoirs — blue circles sized by water level
    const reservoirGeoJSON = useMemo(() => {
        if (!activeLayers.reservoirs || !data?.reservoirs?.length) return null;
        return {
            type: 'FeatureCollection' as const,
            features: data.reservoirs.filter((r: any) => r.lat && r.lon).map((r: any) => ({
                type: 'Feature' as const,
                properties: {
                    id: r.id, type: 'reservoir', name: r.name || '',
                    state: r.state || '', level_ft: r.level_ft || 0,
                    unit: r.unit || 'ft', updated: r.updated || '',
                },
                geometry: { type: 'Point' as const, coordinates: [r.lon, r.lat] }
            }))
        };
    }, [activeLayers.reservoirs, data?.reservoirs]);

    // Cell towers — clustered signal markers
    const cellTowerGeoJSON = useMemo(() => {
        if (!activeLayers.cell_towers || !data?.cell_towers?.length) return null;
        return {
            type: 'FeatureCollection' as const,
            features: data.cell_towers.filter((t: any) => t.lat && t.lon).map((t: any) => ({
                type: 'Feature' as const,
                properties: {
                    id: t.id, type: 'cell_tower', name: `${t.radio || 'Cell'} Tower`,
                    radio: t.radio || '', mcc: t.mcc || '', mnc: t.mnc || '',
                    range: t.range || 0, samples: t.samples || 0, region: t.region || '',
                },
                geometry: { type: 'Point' as const, coordinates: [t.lon, t.lat] }
            }))
        };
    }, [activeLayers.cell_towers, data?.cell_towers]);

    // Border Crossings — US CBP port of entry wait times
    const borderCrossingGeoJSON = useMemo(() => {
        if (!activeLayers.border_crossings || !data?.border_crossings?.length) return null;
        return {
            type: 'FeatureCollection' as const,
            features: data.border_crossings.filter((b: any) => b.lat && b.lon).map((b: any) => ({
                type: 'Feature' as const,
                properties: {
                    id: b.id, type: 'border_crossing', name: b.name || '',
                    border: b.border || '', status: b.status || '',
                    delay: b.delay_minutes || 0, lanes_open: b.lanes_open || 0,
                    max_lanes: b.max_lanes || 0, update_time: b.update_time || '',
                },
                geometry: { type: 'Point' as const, coordinates: [b.lon, b.lat] }
            }))
        };
    }, [activeLayers.border_crossings, data?.border_crossings]);

    // Cyber Threats — abuse.ch botnet C2 / IOC + Check Point live attacks
    const cyberThreatGeoJSON = useMemo(() => {
        if (!activeLayers.cyber_threats || !data?.cyber_threats?.length) return null;
        return {
            type: 'FeatureCollection' as const,
            features: data.cyber_threats.filter((c: any) => c.lat && c.lon).map((c: any) => ({
                type: 'Feature' as const,
                properties: {
                    id: c.id, type: 'cyber_threat', name: c.attack_name || c.ip || '',
                    ip: c.ip || '',
                    malware: c.malware || '', country: c.country || '',
                    as_name: c.as_name || '', port: c.port || '',
                    status: c.status || '', first_seen: c.first_seen || '',
                    attack_name: c.attack_name || '',
                    attack_type: c.type || '',
                    source: c.source || '',
                    source_country: c.source_country || '',
                    // live = Check Point real-time, other = Feodo/ThreatFox
                    isLive: c.source === 'checkpoint' ? 1 : 0,
                },
                geometry: { type: 'Point' as const, coordinates: [c.lon, c.lat] }
            }))
        };
    }, [activeLayers.cyber_threats, data?.cyber_threats]);

    // Check Point attack arcs — lines from source to destination
    const cyberAttackArcsGeoJSON = useMemo(() => {
        if (!activeLayers.cyber_threats || !data?.cyber_threats?.length) return null;
        const liveAttacks = data.cyber_threats.filter((c: any) =>
            c.source === 'checkpoint' && c.src_lat && c.src_lon && c.lat && c.lon
        );
        if (!liveAttacks.length) return null;
        // Take last 100 for performance
        const recent = liveAttacks.slice(-100);
        return {
            type: 'FeatureCollection' as const,
            features: recent.map((c: any) => ({
                type: 'Feature' as const,
                properties: {
                    attack_type: c.type || 'exploit',
                },
                geometry: {
                    type: 'LineString' as const,
                    coordinates: [[c.src_lon, c.src_lat], [c.lon, c.lat]]
                }
            }))
        };
    }, [activeLayers.cyber_threats, data?.cyber_threats]);

    // Global Events — multi-source incidents (GDACS, ReliefWeb, WHO, FEMA, etc.)
    const globalEventsGeoJSON = useMemo(() => {
        if (!activeLayers.global_events || !data?.global_events?.length) return null;
        return {
            type: 'FeatureCollection' as const,
            features: data.global_events.filter((e: any) => e.lat && e.lon).map((e: any) => ({
                type: 'Feature' as const,
                properties: {
                    id: e.id, type: 'global_event', name: e.title || '',
                    event_type: e.event_type || '', severity: e.severity || '',
                    country: e.country || '', date: e.date || '',
                    source: e.source || '', url: e.url || '',
                    description: e.description || '',
                    media_url: e.media_url || '', media_type: e.media_type || '',
                },
                geometry: { type: 'Point' as const, coordinates: [e.lon, e.lat] }
            }))
        };
    }, [activeLayers.global_events, data?.global_events]);

    // NOAA Weather Radio stations
    const noaaNwrGeoJSON = useMemo(() => {
        if (!activeLayers.noaa_nwr || !data?.noaa_nwr?.length) return null;
        return {
            type: 'FeatureCollection' as const,
            features: data.noaa_nwr.filter((s: any) => s.lat && s.lon).map((s: any) => ({
                type: 'Feature' as const,
                properties: {
                    id: s.callsign || s.id, type: 'noaa_nwr',
                    name: s.name || s.callsign || '',
                    callsign: s.callsign || '', freq: s.frequency || '',
                    state: s.state || '', location: s.location || '',
                    status: s.status || '',
                },
                geometry: { type: 'Point' as const, coordinates: [s.lon, s.lat] }
            }))
        };
    }, [activeLayers.noaa_nwr, data?.noaa_nwr]);

    // KiwiSDR receiver nodes
    const kiwisdrGeoJSON = useMemo(() => {
        if (!activeLayers.kiwisdr_nodes || !data?.kiwisdr_nodes?.length) return null;
        return {
            type: 'FeatureCollection' as const,
            features: data.kiwisdr_nodes.filter((n: any) => n.lat && n.lon).map((n: any) => ({
                type: 'Feature' as const,
                properties: {
                    id: n.host || n.id, type: 'kiwisdr',
                    name: n.name || n.host || '',
                    host: n.host || '', port: n.port || 8073,
                    freq_min: n.freq_min_khz || 0, freq_max: n.freq_max_khz || 30000,
                    users: n.users || 0, channels: n.num_ch || n.channels || 8,
                    antenna: n.antenna || '',
                },
                geometry: { type: 'Point' as const, coordinates: [n.lon, n.lat] }
            }))
        };
    }, [activeLayers.kiwisdr_nodes, data?.kiwisdr_nodes]);

    // OSINT: Kismet WiFi/BT devices — cyan circles
    const kismetGeoJSON = useMemo(() => {
        if (!activeLayers.kismet_devices || !data?.kismet_devices?.length) return null;
        return {
            type: 'FeatureCollection' as const,
            features: data.kismet_devices.filter((d: any) => d.lat && d.lon).map((d: any) => ({
                type: 'Feature' as const,
                properties: {
                    id: d.mac || d.id, type: 'kismet_device',
                    name: d.ssid || d.mac || '',
                    mac: d.mac || '', ssid: d.ssid || '',
                    device_type: d.device_type || '',
                    signal_dbm: d.signal_dbm || 0,
                    channel: d.channel || '',
                    encryption: d.encryption || '',
                    manufacturer: d.manufacturer || '',
                    packets: d.packets || 0,
                },
                geometry: { type: 'Point' as const, coordinates: [d.lon, d.lat] }
            }))
        };
    }, [activeLayers.kismet_devices, data?.kismet_devices]);

    // OSINT: Snort IDS alerts — red circles (geolocated external IPs)
    const snortGeoJSON = useMemo(() => {
        if (!activeLayers.snort_alerts || !data?.snort_alerts?.length) return null;
        return {
            type: 'FeatureCollection' as const,
            features: data.snort_alerts.filter((a: any) => a.lat && a.lon).map((a: any) => ({
                type: 'Feature' as const,
                properties: {
                    id: a.id, type: 'snort_alert',
                    name: a.signature_msg || '',
                    signature_msg: a.signature_msg || '',
                    classification: a.classification || '',
                    priority: a.priority || 3,
                    src_ip: a.src_ip || '', dst_ip: a.dst_ip || '',
                    src_port: a.src_port || 0, dst_port: a.dst_port || 0,
                    protocol: a.protocol || '',
                    timestamp: a.timestamp || '',
                },
                geometry: { type: 'Point' as const, coordinates: [a.lon, a.lat] }
            }))
        };
    }, [activeLayers.snort_alerts, data?.snort_alerts]);

    // OSINT: Nmap network hosts — green circles at host location
    const nmapGeoJSON = useMemo(() => {
        if (!activeLayers.nmap_hosts || !data?.nmap_hosts?.length) return null;
        return {
            type: 'FeatureCollection' as const,
            features: data.nmap_hosts.filter((h: any) => h.lat && h.lon).map((h: any) => ({
                type: 'Feature' as const,
                properties: {
                    id: h.ip || h.id, type: 'nmap_host',
                    name: h.hostname || h.ip || '',
                    ip: h.ip || '', hostname: h.hostname || '',
                    os_fingerprint: h.os_fingerprint || '',
                    mac: h.mac || '', vendor: h.vendor || '',
                    open_ports: (h.open_ports || []).join(', '),
                    state: h.state || 'up',
                    scan_time: h.scan_time || '',
                },
                geometry: { type: 'Point' as const, coordinates: [h.lon, h.lat] }
            }))
        };
    }, [activeLayers.nmap_hosts, data?.nmap_hosts]);

    // OSINT: Nuclei vulnerabilities — orange circles, color by severity
    const nucleiGeoJSON = useMemo(() => {
        if (!activeLayers.nuclei_vulns || !data?.nuclei_vulns?.length) return null;
        return {
            type: 'FeatureCollection' as const,
            features: data.nuclei_vulns.filter((v: any) => v.lat && v.lon).map((v: any) => ({
                type: 'Feature' as const,
                properties: {
                    id: v.id, type: 'nuclei_vuln',
                    name: v.vuln_name || v.template_id || '',
                    template_id: v.template_id || '',
                    vuln_severity: v.vuln_severity || 'info',
                    target: v.target || '',
                    matched_at: v.matched_at || '',
                    description: v.description || '',
                    scan_time: v.scan_time || '',
                },
                geometry: { type: 'Point' as const, coordinates: [v.lon, v.lat] }
            }))
        };
    }, [activeLayers.nuclei_vulns, data?.nuclei_vulns]);

    // CCTV cameras — clustered green dots with source filtering
    const cctvGeoJSON = useMemo(() => {
        if (!activeLayers.cctv || !data?.cctv?.length) return null;
        const filters = activeLayers.cctvFilters || {};
        return {
            type: 'FeatureCollection' as const,
            features: data.cctv.filter((c: any) => {
                if (c.lat == null || c.lon == null || !inView(c.lat, c.lon)) return false;
                const agency = c.source_agency || '';
                // Check against filter groups
                const groups: Record<string, string[]> = {
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
                for (const [filterName, prefixes] of Object.entries(groups)) {
                    if (prefixes.some(p => agency.startsWith(p))) {
                        return filters[filterName] !== false;
                    }
                }
                return true;
            }).map((c: any, i: number) => ({
                type: 'Feature' as const,
                properties: {
                    id: c.id || i,
                    type: 'cctv',
                    name: c.direction_facing || 'Camera',
                    source_agency: c.source_agency || 'Unknown',
                    media_url: c.media_url || '',
                    media_type: c.media_type || 'image'
                },
                geometry: { type: 'Point' as const, coordinates: [c.lon, c.lat] }
            }))
        };
    }, [activeLayers.cctv, activeLayers.cctvFilters, data?.cctv, inView]);

    // Load Images into the Map Style once loaded
    const onMapLoad = useCallback((e: any) => {
        const map = e.target;

        // Track which images are still loading so we can retry on styleimagemissing
        const pendingImages: Record<string, string> = {};

        const loadImg = (id: string, url: string) => {
            if (!map.hasImage(id)) {
                pendingImages[id] = url;
                const img = new Image();
                img.crossOrigin = "anonymous";
                img.src = url;
                img.onload = () => {
                    if (!map.hasImage(id)) map.addImage(id, img);
                    delete pendingImages[id];
                };
            }
        };

        // Suppress "image not found" warnings — retry when the async load finishes
        map.on('styleimagemissing', (ev: any) => {
            const id = ev.id;
            const url = pendingImages[id];
            if (url) {
                const img = new Image();
                img.crossOrigin = "anonymous";
                img.src = url;
                img.onload = () => {
                    if (!map.hasImage(id)) map.addImage(id, img);
                    delete pendingImages[id];
                };
            }
        });

        // Legacy generic plane icons (still used as fallbacks)
        loadImg('svgPlaneCyan', svgPlaneCyan);
        loadImg('svgPlaneYellow', svgPlaneYellow);
        loadImg('svgPlaneOrange', svgPlaneOrange);
        loadImg('svgPlanePurple', svgPlanePurple);
        loadImg('svgPlanePink', svgPlanePink);
        loadImg('svgPlaneAlertRed', svgPlaneAlertRed);
        loadImg('svgPlaneDarkBlue', svgPlaneDarkBlue);
        loadImg('svgPlaneWhiteAlert', svgPlaneWhiteAlert);
        loadImg('svgPlaneBlack', svgPlaneBlack);
        // Heli icons
        loadImg('svgHeli', svgHeli);
        loadImg('svgHeliCyan', svgHeliCyan);
        loadImg('svgHeliOrange', svgHeliOrange);
        loadImg('svgHeliPurple', svgHeliPurple);
        loadImg('svgHeliPink', svgHeliPink);
        loadImg('svgHeliAlertRed', svgHeliAlertRed);
        loadImg('svgHeliDarkBlue', svgHeliDarkBlue);
        loadImg('svgHeliWhiteAlert', svgHeliWhiteAlert);
        loadImg('svgHeliBlack', svgHeliBlack);
        // Military special
        loadImg('svgFighter', svgFighter);
        loadImg('svgTanker', svgTanker);
        loadImg('svgRecon', svgRecon);
        // Airliner icons (swept wings + engine pods)
        loadImg('svgAirlinerCyan', svgAirlinerCyan);
        loadImg('svgAirlinerOrange', svgAirlinerOrange);
        loadImg('svgAirlinerPurple', svgAirlinerPurple);
        loadImg('svgAirlinerYellow', svgAirlinerYellow);
        loadImg('svgAirlinerPink', svgAirlinerPink);
        loadImg('svgAirlinerRed', svgAirlinerRed);
        loadImg('svgAirlinerDarkBlue', svgAirlinerDarkBlue);
        loadImg('svgAirlinerWhite', svgAirlinerWhite);
        // Turboprop icons (straight wings)
        loadImg('svgTurbopropCyan', svgTurbopropCyan);
        loadImg('svgTurbopropOrange', svgTurbopropOrange);
        loadImg('svgTurbopropPurple', svgTurbopropPurple);
        loadImg('svgTurbopropYellow', svgTurbopropYellow);
        loadImg('svgTurbopropPink', svgTurbopropPink);
        loadImg('svgTurbopropRed', svgTurbopropRed);
        loadImg('svgTurbopropDarkBlue', svgTurbopropDarkBlue);
        loadImg('svgTurbopropWhite', svgTurbopropWhite);
        // Bizjet icons (sleek, T-tail)
        loadImg('svgBizjetCyan', svgBizjetCyan);
        loadImg('svgBizjetOrange', svgBizjetOrange);
        loadImg('svgBizjetPurple', svgBizjetPurple);
        loadImg('svgBizjetYellow', svgBizjetYellow);
        loadImg('svgBizjetPink', svgBizjetPink);
        loadImg('svgBizjetRed', svgBizjetRed);
        loadImg('svgBizjetDarkBlue', svgBizjetDarkBlue);
        loadImg('svgBizjetWhite', svgBizjetWhite);
        // Grey grounded icons
        loadImg('svgAirlinerGrey', svgAirlinerGrey);
        loadImg('svgTurbopropGrey', svgTurbopropGrey);
        loadImg('svgBizjetGrey', svgBizjetGrey);
        loadImg('svgHeliGrey', svgHeliGrey);
        loadImg('svgDrone', svgDrone);
        loadImg('svgShipGray', svgShipGray);
        loadImg('svgShipRed', svgShipRed);
        loadImg('svgShipYellow', svgShipYellow);
        loadImg('svgShipBlue', svgShipBlue);
        loadImg('svgShipWhite', svgShipWhite);
        loadImg('svgCarrier', svgCarrier);
        loadImg('svgCctv', svgCctv);
        loadImg('svgWarning', svgWarning);
        loadImg('icon-threat', svgThreat);
        loadImg('icon-liveua-yellow', svgTriangleYellow);
        loadImg('icon-liveua-red', svgTriangleRed);

        // Satellite mission-type icons
        loadImg('sat-mil', makeSatSvg('#ff3333'));
        loadImg('sat-sar', makeSatSvg('#00e5ff'));
        loadImg('sat-sigint', makeSatSvg('#ffffff'));
        loadImg('sat-nav', makeSatSvg('#4488ff'));
        loadImg('sat-ew', makeSatSvg('#ff00ff'));
        loadImg('sat-com', makeSatSvg('#44ff44'));
        loadImg('sat-station', makeSatSvg('#ffdd00'));
        loadImg('sat-gen', makeSatSvg('#aaaaaa'));
    }, []);

    // Build a set of tracked icao24s to exclude from other flight layers
    const trackedIcaoSet = useMemo(() => {
        const s = new Set<string>();
        if (data?.tracked_flights) {
            for (const t of data.tracked_flights) {
                if (t.icao24) s.add(t.icao24.toLowerCase());
            }
        }
        return s;
    }, [data?.tracked_flights]);

    // Elapsed seconds since last data refresh (used for position interpolation)
    // interpTick dependency forces recalculation every 1s tick
    const dtSeconds = useMemo(() => {
        void interpTick; // use the tick to trigger recalc
        return (Date.now() - dataTimestamp.current) / 1000;
    }, [interpTick]);

    // Helper: interpolate a flight's position if airborne and has speed+heading
    const interpFlight = (f: any): [number, number] => {
        // Fast path: skip trig for stationary/grounded/no-speed aircraft
        if (!f.speed_knots || f.speed_knots <= 0 || dtSeconds <= 0) return [f.lng, f.lat];
        if (f.alt != null && f.alt <= 100) return [f.lng, f.lat];
        // Only interpolate if enough time has passed to matter (>1s)
        if (dtSeconds < 1) return [f.lng, f.lat];
        const heading = f.true_track || f.heading || 0;
        const [newLat, newLng] = interpolatePosition(f.lat, f.lng, heading, f.speed_knots, dtSeconds);
        return [newLng, newLat];
    };

    // Helper: interpolate a ship's position using SOG + heading
    const interpShip = (s: any): [number, number] => {
        if (typeof s.sog !== 'number' || !s.sog || s.sog <= 0 || dtSeconds <= 0) return [s.lng, s.lat];
        const heading = (typeof s.cog === 'number' ? s.cog : 0) || s.heading || 0;
        const [newLat, newLng] = interpolatePosition(s.lat, s.lng, heading, s.sog, dtSeconds);
        return [newLng, newLat];
    };

    // Helper: interpolate a satellite's position between API updates
    // Satellites have deterministic orbits so linear interpolation over 60s is accurate
    // maxDt=65 allows full interval coverage (60s update + 5s buffer)
    const interpSat = (s: any): [number, number] => {
        if (!s.speed_knots || s.speed_knots <= 0 || dtSeconds < 1) return [s.lng, s.lat];
        const [newLat, newLng] = interpolatePosition(s.lat, s.lng, s.heading || 0, s.speed_knots, dtSeconds, 0, 65);
        return [newLng, newLat];
    };

    // Satellite GeoJSON with interpolated positions
    const satellitesGeoJSON = useMemo(() => {
        if (!activeLayers.satellites || !data?.satellites?.length) return null;
        return {
            type: 'FeatureCollection' as const,
            features: data.satellites.filter((s: any) => s.lat != null && s.lng != null && inView(s.lat, s.lng)).map((s: any, i: number) => ({
                type: 'Feature' as const,
                properties: {
                    id: s.id || i,
                    type: 'satellite',
                    name: s.name,
                    mission: s.mission || 'general',
                    sat_type: s.sat_type || 'Satellite',
                    country: s.country || '',
                    alt_km: s.alt_km || 0,
                    wiki: s.wiki || '',
                    color: MISSION_COLORS[s.mission] || '#aaaaaa',
                    iconId: MISSION_ICON_MAP[s.mission] || 'sat-gen'
                },
                geometry: { type: 'Point' as const, coordinates: interpSat(s) }
            }))
        };
    }, [activeLayers.satellites, data?.satellites, dtSeconds, inView]);


    // Create GeoJSON collections dynamically (this runs ultra fast in pure JS)
    const commFlightsGeoJSON = useMemo(() => {
        if (!activeLayers.flights || !data?.commercial_flights) return null;
        const colorMap: Record<string, string> = { heli: 'svgHeliCyan', turboprop: 'svgTurbopropCyan', bizjet: 'svgBizjetCyan', airliner: 'svgAirlinerCyan' };
        return {
            type: 'FeatureCollection',
            features: data.commercial_flights.map((f: any, i: number) => {
                if (f.lat == null || f.lng == null) return null;
                if (!inView(f.lat, f.lng)) return null;
                if (f.icao24 && trackedIcaoSet.has(f.icao24.toLowerCase())) return null;
                const acType = classifyAircraft(f.model, f.aircraft_category);
                const grounded = f.alt != null && f.alt <= 100;
                const [iLng, iLat] = interpFlight(f);
                return {
                    type: 'Feature',
                    properties: { id: f.icao24 || `flight_${i}`, type: 'flight', callsign: f.callsign || f.icao24, rotation: f.true_track || f.heading || 0, iconId: grounded ? GROUNDED_ICON_MAP[acType] : colorMap[acType] },
                    geometry: { type: 'Point', coordinates: [iLng, iLat] }
                };
            }).filter(Boolean)
        };
    }, [activeLayers.flights, data?.commercial_flights, trackedIcaoSet, dtSeconds, inView]);

    const privFlightsGeoJSON = useMemo(() => {
        if (!activeLayers.private || !data?.private_flights) return null;
        const colorMap: Record<string, string> = { heli: 'svgHeliOrange', turboprop: 'svgTurbopropOrange', bizjet: 'svgBizjetOrange', airliner: 'svgAirlinerOrange' };
        return {
            type: 'FeatureCollection',
            features: data.private_flights.map((f: any, i: number) => {
                if (f.lat == null || f.lng == null) return null;
                if (!inView(f.lat, f.lng)) return null;
                if (f.icao24 && trackedIcaoSet.has(f.icao24.toLowerCase())) return null;
                const acType = classifyAircraft(f.model, f.aircraft_category);
                const grounded = f.alt != null && f.alt <= 100;
                const [iLng, iLat] = interpFlight(f);
                return {
                    type: 'Feature',
                    properties: { id: f.icao24 || `priv_${i}`, type: 'private_flight', callsign: f.callsign || f.icao24, rotation: f.true_track || f.heading || 0, iconId: grounded ? GROUNDED_ICON_MAP[acType] : colorMap[acType] },
                    geometry: { type: 'Point', coordinates: [iLng, iLat] }
                };
            }).filter(Boolean)
        };
    }, [activeLayers.private, data?.private_flights, trackedIcaoSet, dtSeconds, inView]);

    const privJetsGeoJSON = useMemo(() => {
        if (!activeLayers.jets || !data?.private_jets) return null;
        const colorMap: Record<string, string> = { heli: 'svgHeliPurple', turboprop: 'svgTurbopropPurple', bizjet: 'svgBizjetPurple', airliner: 'svgAirlinerPurple' };
        return {
            type: 'FeatureCollection',
            features: data.private_jets.map((f: any, i: number) => {
                if (f.lat == null || f.lng == null) return null;
                if (!inView(f.lat, f.lng)) return null;
                if (f.icao24 && trackedIcaoSet.has(f.icao24.toLowerCase())) return null;
                const acType = classifyAircraft(f.model, f.aircraft_category);
                const grounded = f.alt != null && f.alt <= 100;
                const [iLng, iLat] = interpFlight(f);
                return {
                    type: 'Feature',
                    properties: { id: f.icao24 || `jet_${i}`, type: 'private_jet', callsign: f.callsign || f.icao24, rotation: f.true_track || f.heading || 0, iconId: grounded ? GROUNDED_ICON_MAP[acType] : colorMap[acType] },
                    geometry: { type: 'Point', coordinates: [iLng, iLat] }
                };
            }).filter(Boolean)
        };
    }, [activeLayers.jets, data?.private_jets, trackedIcaoSet, dtSeconds, inView]);

    const milFlightsGeoJSON = useMemo(() => {
        if (!activeLayers.military || !data?.military_flights) return null;

        // Special military types keep their unique icons
        const milSpecialMap: any = { 'fighter': 'svgFighter', 'tanker': 'svgTanker', 'recon': 'svgRecon' };
        // Fallback by aircraft shape for cargo/default
        const milColorMap: Record<string, string> = { heli: 'svgHeli', turboprop: 'svgTurbopropYellow', bizjet: 'svgBizjetYellow', airliner: 'svgAirlinerYellow' };

        return {
            type: 'FeatureCollection',
            features: data.military_flights.map((f: any, i: number) => {
                if (f.lat == null || f.lng == null) return null;
                if (!inView(f.lat, f.lng)) return null;
                if (f.icao24 && trackedIcaoSet.has(f.icao24.toLowerCase())) return null;
                const milType = f.military_type || 'default';
                const grounded = f.alt != null && f.alt <= 100;
                let iconId = milSpecialMap[milType];
                if (!iconId) {
                    const acType = classifyAircraft(f.model, f.aircraft_category);
                    iconId = grounded ? GROUNDED_ICON_MAP[acType] : milColorMap[acType];
                } else if (grounded) {
                    const acType = classifyAircraft(f.model, f.aircraft_category);
                    iconId = GROUNDED_ICON_MAP[acType];
                }
                const [iLng, iLat] = interpFlight(f);
                return {
                    type: 'Feature',
                    properties: { id: f.icao24 || `mil_${i}`, type: 'military_flight', callsign: f.callsign || f.icao24, rotation: f.true_track || f.heading || 0, iconId },
                    geometry: { type: 'Point', coordinates: [iLng, iLat] }
                };
            }).filter(Boolean)
        };
    }, [activeLayers.military, data?.military_flights, trackedIcaoSet, dtSeconds, inView]);

    const shipsGeoJSON = useMemo(() => {
        if (!(activeLayers.ships_important || activeLayers.ships_civilian || activeLayers.ships_passenger) || !data?.ships) return null;

        return {
            type: 'FeatureCollection',
            features: data.ships.map((s: any, i: number) => {
                if (s.lat == null || s.lng == null) return null;
                if (!inView(s.lat, s.lng)) return null;

                const isImportant = s.type === 'carrier' || s.type === 'military_vessel' || s.type === 'tanker' || s.type === 'cargo';
                const isPassenger = s.type === 'passenger';

                // Carriers are now handled by a dedicated unclustered source
                if (s.type === 'carrier') return null;

                if (isImportant && activeLayers?.ships_important === false) return null;
                if (isPassenger && activeLayers?.ships_passenger === false) return null;
                if (!isImportant && !isPassenger && activeLayers?.ships_civilian === false) return null;

                let iconId = 'svgShipBlue';
                if (s.type === 'carrier') {
                    iconId = 'svgCarrier';
                } else if (s.type === 'tanker' || s.type === 'cargo') {
                    iconId = 'svgShipRed';
                } else if (s.type === 'yacht' || s.type === 'passenger') {
                    iconId = 'svgShipWhite';
                } else if (s.type === 'military_vessel') {
                    iconId = 'svgShipYellow';
                }

                const [iLng, iLat] = interpShip(s);
                return {
                    type: 'Feature',
                    properties: { id: s.mmsi || s.imo || `ship_${i}`, type: 'ship', name: s.name, rotation: s.heading || 0, iconId },
                    geometry: { type: 'Point', coordinates: [iLng, iLat] }
                };
            }).filter(Boolean)
        };
    }, [activeLayers.ships_important, activeLayers.ships_civilian, activeLayers.ships_passenger, data?.ships, inView]);

    // Extract ship cluster positions from the map source for HTML labels
    const shipClusterHandlerRef = useRef<(() => void) | null>(null);
    useEffect(() => {
        const map = mapRef.current?.getMap();
        if (!map || !shipsGeoJSON) { setShipClusters([]); return; }

        // Remove previous handler if it exists
        if (shipClusterHandlerRef.current) {
            map.off('moveend', shipClusterHandlerRef.current);
            map.off('sourcedata', shipClusterHandlerRef.current);
        }

        const update = () => {
            try {
                const features = map.querySourceFeatures('ships');
                const clusters = features
                    .filter((f: any) => f.properties?.cluster)
                    .map((f: any) => ({
                        lng: (f.geometry as any).coordinates[0],
                        lat: (f.geometry as any).coordinates[1],
                        count: f.properties.point_count_abbreviated || f.properties.point_count,
                        id: f.properties.cluster_id
                    }));
                const seen = new Set();
                const unique = clusters.filter((c: any) => { if (seen.has(c.id)) return false; seen.add(c.id); return true; });
                setShipClusters(unique);
            } catch { setShipClusters([]); }
        };
        shipClusterHandlerRef.current = update;

        map.on('moveend', update);
        map.on('sourcedata', update);
        setTimeout(update, 500);

        return () => { map.off('moveend', update); map.off('sourcedata', update); };
    }, [shipsGeoJSON]);

    // Extract earthquake cluster positions from the map source for HTML labels
    const eqClusterHandlerRef = useRef<(() => void) | null>(null);
    useEffect(() => {
        const map = mapRef.current?.getMap();
        if (!map || !earthquakesGeoJSON) { setEqClusters([]); return; }

        if (eqClusterHandlerRef.current) {
            map.off('moveend', eqClusterHandlerRef.current);
            map.off('sourcedata', eqClusterHandlerRef.current);
        }

        const update = () => {
            try {
                const features = map.querySourceFeatures('earthquakes');
                const clusters = features
                    .filter((f: any) => f.properties?.cluster)
                    .map((f: any) => ({
                        lng: (f.geometry as any).coordinates[0],
                        lat: (f.geometry as any).coordinates[1],
                        count: f.properties.point_count_abbreviated || f.properties.point_count,
                        id: f.properties.cluster_id
                    }));
                const seen = new Set();
                const unique = clusters.filter((c: any) => { if (seen.has(c.id)) return false; seen.add(c.id); return true; });
                setEqClusters(unique);
            } catch { setEqClusters([]); }
        };
        eqClusterHandlerRef.current = update;

        map.on('moveend', update);
        map.on('sourcedata', update);
        setTimeout(update, 500);

        return () => { map.off('moveend', update); map.off('sourcedata', update); };
    }, [earthquakesGeoJSON]);

    const carriersGeoJSON = useMemo(() => {
        if (!activeLayers.ships_important || !data?.ships) return null;
        return {
            type: 'FeatureCollection',
            features: data.ships.map((s: any, i: number) => {
                if (s.type !== 'carrier' || s.lat == null || s.lng == null) return null;
                const [iLng, iLat] = interpShip(s);
                return {
                    type: 'Feature',
                    properties: { id: s.mmsi || s.imo || `carrier_${i}`, type: 'ship', name: s.name, rotation: s.heading || 0, iconId: 'svgCarrier' },
                    geometry: { type: 'Point', coordinates: [iLng, iLat] }
                };
            }).filter(Boolean)
        };
    }, [activeLayers.ships_important, data?.ships]);

    const activeRouteGeoJSON = useMemo(() => {
        if (!selectedEntity || !data) return null;

        let entity = null;
        if (selectedEntity.type === 'flight') entity = findFlight(data?.commercial_flights, selectedEntity.id);
        else if (selectedEntity.type === 'private_flight') entity = findFlight(data?.private_flights, selectedEntity.id);
        else if (selectedEntity.type === 'military_flight') entity = findFlight(data?.military_flights, selectedEntity.id);
        else if (selectedEntity.type === 'private_jet') entity = findFlight(data?.private_jets, selectedEntity.id);
        else if (selectedEntity.type === 'ship') entity = findShip(data?.ships, selectedEntity.id);

        if (!entity) return null;

        const currentLoc = [entity.lng, entity.lat];
        let originLoc = entity.origin_loc; // [lng, lat]
        let destLoc = entity.dest_loc; // [lng, lat]

        if (dynamicRoute && dynamicRoute.orig_loc && dynamicRoute.dest_loc) {
            originLoc = dynamicRoute.orig_loc;
            destLoc = dynamicRoute.dest_loc;
        }

        const features = [];
        if (originLoc) {
            features.push({
                type: 'Feature',
                properties: { type: 'route-origin' },
                geometry: { type: 'LineString', coordinates: [currentLoc, originLoc] }
            });
        }
        if (destLoc) {
            features.push({
                type: 'Feature',
                properties: { type: 'route-dest' },
                geometry: { type: 'LineString', coordinates: [currentLoc, destLoc] }
            });
        }

        if (features.length === 0) return null;
        return { type: 'FeatureCollection', features };
    }, [selectedEntity, data, dynamicRoute]);

    // Trail history GeoJSON: shows where an aircraft has been (from backend trail data)
    const trailGeoJSON = useMemo(() => {
        if (!selectedEntity || !data) return null;

        let entity = null;
        if (selectedEntity.type === 'flight') entity = findFlight(data?.commercial_flights, selectedEntity.id);
        else if (selectedEntity.type === 'private_flight') entity = findFlight(data?.private_flights, selectedEntity.id);
        else if (selectedEntity.type === 'military_flight') entity = findFlight(data?.military_flights, selectedEntity.id);
        else if (selectedEntity.type === 'private_jet') entity = findFlight(data?.private_jets, selectedEntity.id);
        else if (selectedEntity.type === 'tracked_flight') entity = findFlight(data?.tracked_flights, selectedEntity.id);

        if (!entity || !entity.trail || entity.trail.length < 2) return null;

        // trail points are [lat, lng, alt, timestamp] — convert to [lng, lat] for GeoJSON
        const coords = entity.trail.map((p: number[]) => [p[1], p[0]]);
        // Append current position as the final point
        if (entity.lat != null && entity.lng != null) {
            coords.push([entity.lng, entity.lat]);
        }

        return {
            type: 'FeatureCollection',
            features: [{
                type: 'Feature',
                properties: { type: 'trail' },
                geometry: { type: 'LineString', coordinates: coords }
            }]
        };
    }, [selectedEntity, data]);

    const spreadAlerts = useMemo(() => {
        if (!data?.news) return [];

        // 1. Prepare items with screen-space coordinates (Mercator approx)
        // We use a relative pixel projection based on zoom to detect visual collisions.
        const pixelsPerDeg = 256 * Math.pow(2, viewState.zoom) / 360;

        // Use original array mapping to preserve correct indices for the popup/selection logic
        // Estimate each box's rendered height based on its content.
        // CSS: padding 5px top/bottom, title maxWidth 160px at 9px font (~18 chars/line),
        // header "!! ALERT LVL X !!" = 14px, title lines * 13px each, footer 12px if present
        const estimateBoxH = (n: any) => {
            const titleLen = (n.title || '').length;
            const titleLines = Math.max(1, Math.ceil(titleLen / 20)); // ~20 chars per line at 9px in 160px
            const hasFooter = (n.cluster_count || 1) > 1;
            return 10 + 14 + (titleLines * 13) + (hasFooter ? 14 : 0) + 10; // padding + header + title + footer + padding
        };

        let items = data.news
            .map((n: any, idx: number) => ({ ...n, originalIdx: idx }))
            .filter((n: any) => n.coords)
            .map((n: any) => ({
                ...n,
                x: n.coords[1] * pixelsPerDeg,
                y: -n.coords[0] * pixelsPerDeg,
                offsetX: 0,
                offsetY: 0,
                boxH: estimateBoxH(n),
            }));

        // Box width is consistent (minWidth 120 + padding, titles up to 160px + 16px padding)
        const BOX_W = 180;
        const GAP = 6; // Minimum gap between boxes
        const MAX_OFFSET = 350;

        // 2. Grid-based Collision Resolution (O(n) per iteration instead of O(n²))
        const CELL_W = BOX_W + GAP;
        const CELL_H = 100; // Approximate max box height + gap
        const maxIter = 30;
        for (let iter = 0; iter < maxIter; iter++) {
            let moved = false;
            // Build spatial grid
            const grid: Record<string, number[]> = {};
            for (let i = 0; i < items.length; i++) {
                const cx = Math.floor((items[i].x + items[i].offsetX) / CELL_W);
                const cy = Math.floor((items[i].y + items[i].offsetY) / CELL_H);
                const key = `${cx},${cy}`;
                (grid[key] ??= []).push(i);
            }
            // Check collisions only within same/adjacent cells
            const checked = new Set<string>();
            for (const key in grid) {
                const [cx, cy] = key.split(',').map(Number);
                for (let dx = -1; dx <= 1; dx++) {
                    for (let dy = -1; dy <= 1; dy++) {
                        const nk = `${cx + dx},${cy + dy}`;
                        if (!grid[nk]) continue;
                        const pairKey = cx + dx < cx || (cx + dx === cx && cy + dy < cy) ? `${nk}|${key}` : `${key}|${nk}`;
                        if (key !== nk && checked.has(pairKey)) continue;
                        checked.add(pairKey);
                        const cellA = grid[key];
                        const cellB = key === nk ? cellA : grid[nk];
                        for (const i of cellA) {
                            const startJ = key === nk ? cellA.indexOf(i) + 1 : 0;
                            for (let jIdx = startJ; jIdx < cellB.length; jIdx++) {
                                const j = cellB[jIdx];
                                if (i === j) continue;
                                const a = items[i], b = items[j];
                                const adx = Math.abs((a.x + a.offsetX) - (b.x + b.offsetX));
                                const ady = Math.abs((a.y + a.offsetY) - (b.y + b.offsetY));
                                const minDistX = BOX_W + GAP;
                                const minDistY = (a.boxH + b.boxH) / 2 + GAP;
                                if (adx < minDistX && ady < minDistY) {
                                    moved = true;
                                    const overlapX = minDistX - adx;
                                    const overlapY = minDistY - ady;
                                    if (overlapY < overlapX) {
                                        const push = (overlapY / 2) + 1;
                                        if ((a.y + a.offsetY) <= (b.y + b.offsetY)) { a.offsetY -= push; b.offsetY += push; }
                                        else { a.offsetY += push; b.offsetY -= push; }
                                    } else {
                                        const push = (overlapX / 2) + 1;
                                        if ((a.x + a.offsetX) <= (b.x + b.offsetX)) { a.offsetX -= push; b.offsetX += push; }
                                        else { a.offsetX += push; b.offsetX -= push; }
                                    }
                                }
                            }
                        }
                    }
                }
            }
            if (!moved) break;
        }

        // Clamp offsets so boxes stay near their origin
        for (const item of items) {
            item.offsetX = Math.max(-MAX_OFFSET, Math.min(MAX_OFFSET, item.offsetX));
            item.offsetY = Math.max(-MAX_OFFSET, Math.min(MAX_OFFSET, item.offsetY));
        }

        return items.map((item: any) => ({
            ...item,
            showLine: Math.abs(item.offsetX) > 5 || Math.abs(item.offsetY) > 5
        }));
    }, [data?.news, Math.round(viewState.zoom)]);

    const trackedFlightsGeoJSON = useMemo(() => {
        if (!activeLayers.tracked || !data?.tracked_flights) return null;

        // Tracked icon maps by aircraft shape and alert color
        const trackedIconMap: Record<string, Record<string, string>> = {
            heli: { pink: 'svgHeliPink', red: 'svgHeliAlertRed', darkblue: 'svgHeliDarkBlue', white: 'svgHeliWhiteAlert' },
            airliner: { pink: 'svgAirlinerPink', red: 'svgAirlinerRed', darkblue: 'svgAirlinerDarkBlue', white: 'svgAirlinerWhite' },
            turboprop: { pink: 'svgTurbopropPink', red: 'svgTurbopropRed', darkblue: 'svgTurbopropDarkBlue', white: 'svgTurbopropWhite' },
            bizjet: { pink: 'svgBizjetPink', red: 'svgBizjetRed', darkblue: 'svgBizjetDarkBlue', white: 'svgBizjetWhite' },
        };

        return {
            type: 'FeatureCollection',
            features: data.tracked_flights.map((f: any, i: number) => {
                if (f.lat == null || f.lng == null) return null;

                const alertColor = f.alert_color || 'white';
                const acType = classifyAircraft(f.model, f.aircraft_category);
                const grounded = f.alt != null && f.alt <= 100;
                const iconId = grounded ? GROUNDED_ICON_MAP[acType] : (trackedIconMap[acType]?.[alertColor] || trackedIconMap.airliner[alertColor] || 'svgAirlinerWhite');

                const displayName = f.alert_operator || f.operator || f.owner || f.name || f.callsign || f.icao24 || "UNKNOWN";

                const [iLng, iLat] = interpFlight(f);
                return {
                    type: 'Feature',
                    properties: { id: f.icao24 || `tracked_${i}`, type: 'tracked_flight', callsign: String(displayName), rotation: f.true_track || f.heading || 0, iconId },
                    geometry: { type: 'Point', coordinates: [iLng, iLat] }
                };
            }).filter(Boolean)
        };
    }, [activeLayers.tracked, data?.tracked_flights, dtSeconds]);

    const uavGeoJSON = useMemo(() => {
        if (!activeLayers.military || !data?.uavs) return null;
        return {
            type: 'FeatureCollection',
            features: data.uavs.map((uav: any, i: number) => {
                if (uav.lat == null || uav.lng == null || !inView(uav.lat, uav.lng)) return null;
                return {
                    type: 'Feature',
                    properties: {
                        id: uav.id || i,
                        type: 'uav',
                        callsign: uav.callsign,
                        rotation: uav.heading || 0,
                        iconId: 'svgDrone',
                        name: uav.aircraft_model || uav.callsign,
                        country: uav.country || '',
                        uav_type: uav.uav_type || '',
                        alt: uav.alt || 0,
                        range_km: uav.range_km || 0,
                        wiki: uav.wiki || '',
                        speed_knots: uav.speed_knots || 0
                    },
                    geometry: { type: 'Point', coordinates: [uav.lng, uav.lat] }
                };
            }).filter(Boolean)
        };
    }, [activeLayers.military, data?.uavs, inView]);

    // UAV operational range circle — only for the selected UAV
    const uavRangeGeoJSON = useMemo(() => {
        if (!activeLayers.military || !data?.uavs || selectedEntity?.type !== 'uav') return null;
        const uav = data.uavs.find((u: any) => u.id === selectedEntity.id);
        if (!uav?.center || !uav?.range_km) return null;
        const R = 6371;
        const rangeDeg = uav.range_km / R * (180 / Math.PI);
        const centerLat = uav.center[0];
        const centerLng = uav.center[1];
        const coords: number[][] = [];
        for (let i = 0; i <= 64; i++) {
            const angle = (i / 64) * 2 * Math.PI;
            const lat = centerLat + rangeDeg * Math.sin(angle);
            const lng = centerLng + rangeDeg * Math.cos(angle) / Math.cos(centerLat * Math.PI / 180);
            coords.push([lng, lat]);
        }
        return {
            type: 'FeatureCollection' as const,
            features: [{
                type: 'Feature' as const,
                properties: { name: uav.callsign, range_km: uav.range_km },
                geometry: { type: 'Polygon' as const, coordinates: [coords] }
            }]
        };
    }, [activeLayers.military, data?.uavs, selectedEntity]);

    const gdeltGeoJSON = useMemo(() => {
        if (!activeLayers.global_incidents || !data?.gdelt) return null;
        return {
            type: 'FeatureCollection',
            features: data.gdelt.map((g: any, i: number) => {
                if (!g.geometry || !g.geometry.coordinates) return null;
                const [gLng, gLat] = g.geometry.coordinates;
                if (!inView(gLat, gLng)) return null;
                return {
                    type: 'Feature',
                    properties: { id: i, type: 'gdelt', title: g.title },
                    geometry: g.geometry
                };
            }).filter(Boolean)
        };
    }, [activeLayers.global_incidents, data?.gdelt, inView]);

    const liveuaGeoJSON = useMemo(() => {
        if (!activeLayers.global_incidents || !data?.liveuamap) return null;
        return {
            type: 'FeatureCollection',
            features: data.liveuamap.map((incident: any, i: number) => {
                if (incident.lat == null || incident.lng == null || !inView(incident.lat, incident.lng)) return null;
                const isViolent = /bomb|missil|strike|attack|kill|destroy|fire|shoot|expl|raid/i.test(incident.title || "");
                return {
                    type: 'Feature',
                    properties: { id: incident.id, type: 'liveuamap', title: incident.title, iconId: isViolent ? 'icon-liveua-red' : 'icon-liveua-yellow' },
                    geometry: { type: 'Point', coordinates: [incident.lng, incident.lat] }
                };
            }).filter(Boolean)
        };
    }, [activeLayers.global_incidents, data?.liveuamap, inView]);

    const frontlineGeoJSON = useMemo(() => {
        if (!activeLayers.ukraine_frontline || !data?.frontlines) return null;
        return data.frontlines; // Frontlines is already a fully formed GeoJSON FeatureCollection
    }, [activeLayers.ukraine_frontline, data?.frontlines]);

    // OSINT search result locations (points)
    const osintLocationsGeoJSON = useMemo(() => {
        if (selectedEntity?.type !== 'osint_search') return null;
        const locs = selectedEntity.extra?.locations || [];
        const validLocs = locs.filter((l: any) => l.lat && (l.lon || l.lng));
        if (!validLocs.length) return null;

        return {
            type: 'FeatureCollection' as const,
            features: validLocs.map((l: any, i: number) => ({
                type: 'Feature' as const,
                properties: {
                    label: l.label || `Location ${i + 1}`,
                    source: l.source || 'osint',
                    index: i,
                },
                geometry: {
                    type: 'Point' as const,
                    coordinates: [l.lon || l.lng, l.lat],
                },
            })),
        };
    }, [selectedEntity]);

    // OSINT search result connecting lines
    const osintLinesGeoJSON = useMemo(() => {
        if (selectedEntity?.type !== 'osint_search') return null;
        const locs = selectedEntity.extra?.locations || [];
        const validLocs = locs.filter((l: any) => l.lat && (l.lon || l.lng));
        if (validLocs.length < 2) return null;

        return {
            type: 'Feature' as const,
            properties: {},
            geometry: {
                type: 'LineString' as const,
                coordinates: validLocs.map((l: any) => [l.lon || l.lng, l.lat]),
            },
        };
    }, [selectedEntity]);

    const activeInteractiveLayerIds = [
        commFlightsGeoJSON && 'commercial-flights-layer',
        privFlightsGeoJSON && 'private-flights-layer',
        privJetsGeoJSON && 'private-jets-layer',
        milFlightsGeoJSON && 'military-flights-layer',
        shipsGeoJSON && 'ships-clusters-layer',
        shipsGeoJSON && 'ships-layer',
        carriersGeoJSON && 'carriers-layer',
        trackedFlightsGeoJSON && 'tracked-flights-layer',
        uavGeoJSON && 'uav-layer',
        gdeltGeoJSON && 'gdelt-layer',
        liveuaGeoJSON && 'liveuamap-layer',
        frontlineGeoJSON && 'ukraine-frontline-layer',
        earthquakesGeoJSON && 'earthquakes-layer',
        satellitesGeoJSON && 'satellites-layer',
        cctvGeoJSON && 'cctv-layer',
        tfrGeoJSON && 'tfr-fill',
        weatherAlertGeoJSON && 'weather-alert-fill',
        naturalEventGeoJSON && 'natural-events-layer',
        firmsGeoJSON && 'firms-layer',
        powerOutageGeoJSON && 'power-outage-fill',
        powerOutageGeoJSON && 'power-outage-layer',
        internetOutageGeoJSON && 'internet-outage-fill',
        internetOutageGeoJSON && 'internet-outage-layer',
        aqiGeoJSON && 'aqi-layer',
        radioactivityGeoJSON && 'radioactivity-layer',
        milBasesGeoJSON && 'mil-base-layer',
        nuclearGeoJSON && 'nuclear-layer',
        cableGeoJSON && 'cable-lines',
        cableLandingGeoJSON && 'cable-landing-layer',
        embassyGeoJSON && 'embassy-layer',
        volcanoGeoJSON && 'volcano-layer',
        piracyGeoJSON && 'piracy-layer',
        reservoirGeoJSON && 'reservoir-layer',
        cellTowerGeoJSON && 'cell-tower-layer',
        borderCrossingGeoJSON && 'border-crossing-layer',
        cyberThreatGeoJSON && 'cyber-threat-layer',
        globalEventsGeoJSON && 'global-events-layer',
        noaaNwrGeoJSON && 'noaa-nwr-layer',
        kiwisdrGeoJSON && 'kiwisdr-layer',
        kismetGeoJSON && 'kismet-layer',
        snortGeoJSON && 'snort-layer',
        nmapGeoJSON && 'nmap-layer',
        nucleiGeoJSON && 'nuclei-layer',
        osintLocationsGeoJSON && 'osint-locations-circle',
    ].filter(Boolean) as string[];


    const handleMouseMove = useCallback((evt: any) => {
        if (onMouseCoords) onMouseCoords({ lat: evt.lngLat.lat, lng: evt.lngLat.lng });
    }, [onMouseCoords]);

    // Middle mouse button (scroll wheel click) → regional focus
    // Use a ref to hold the latest callback so the listener doesn't need re-attaching
    const middleClickRef = useRef(onMiddleClick);
    middleClickRef.current = onMiddleClick;

    useEffect(() => {
        // Attach after a short delay to ensure map canvas is ready
        const timer = setTimeout(() => {
            const map = mapRef.current?.getMap();
            if (!map) return;
            const container = map.getContainer();

            // Use 'auxclick' — fires on middle/right click release, not consumed by MapLibre drag
            const handler = (e: MouseEvent) => {
                if (e.button === 1 && middleClickRef.current) { // button 1 = middle/scroll wheel
                    e.preventDefault();
                    e.stopPropagation();
                    const canvas = map.getCanvas();
                    const rect = canvas.getBoundingClientRect();
                    const point = map.unproject([e.clientX - rect.left, e.clientY - rect.top]);
                    middleClickRef.current({ lat: point.lat, lng: point.lng });
                }
            };
            container.addEventListener('auxclick', handler);
            (container as any).__middleClickHandler = handler;
        }, 1000);

        return () => {
            clearTimeout(timer);
            const map = mapRef.current?.getMap();
            if (map) {
                const container = map.getContainer();
                const h = (container as any).__middleClickHandler;
                if (h) container.removeEventListener('auxclick', h);
            }
        };
    }, []); // attach once

    const opacityFilter: any = selectedEntity
        ? ['case', ['all', ['==', ['get', 'type'], selectedEntity.type], ['==', ['get', 'id'], selectedEntity.id]], 1.0, 0.0]
        : 1.0;

    return (
        <div className={`relative h-full w-full z-0 isolate ${selectedEntity && ['region_dossier', 'gdelt', 'liveuamap', 'news'].includes(selectedEntity.type) ? 'map-focus-active' : ''}`}>
            <Map
                ref={mapRef}
                reuseMaps
                maxTileCacheSize={200}
                fadeDuration={0}
                initialViewState={viewState}
                onMove={evt => {
                    setViewState(evt.viewState);
                    onViewStateChange?.({ zoom: evt.viewState.zoom, latitude: evt.viewState.latitude });
                    // Debounce bounds update to avoid thrashing during drag
                    if (boundsTimerRef.current) clearTimeout(boundsTimerRef.current);
                    boundsTimerRef.current = setTimeout(updateBounds, 300);
                }}
                onMouseMove={handleMouseMove}
                onContextMenu={(evt) => {
                    evt.preventDefault();
                    onRightClick?.({ lat: evt.lngLat.lat, lng: evt.lngLat.lng });
                }}
                mapStyle={darkStyle as any}
                mapLib={maplibregl}
                onLoad={onMapLoad}
                onIdle={updateBounds}
                interactiveLayerIds={activeInteractiveLayerIds}
                onClick={(e) => {
                    // Measurement mode: place waypoints instead of selecting entities
                    if (measureMode && onMeasureClick) {
                        onMeasureClick({ lat: e.lngLat.lat, lng: e.lngLat.lng });
                        return;
                    }
                    if (e.features && e.features.length > 0) {
                        const feature = e.features[0];
                        const props = feature.properties || {};

                        // Cluster click → zoom in instead of selecting
                        if (props.cluster_id != null || props.point_count != null) {
                            const map = mapRef.current?.getMap();
                            if (map && feature.geometry?.type === 'Point') {
                                const [lng, lat] = (feature.geometry as any).coordinates;
                                map.flyTo({ center: [lng, lat], zoom: (map.getZoom() || 2) + 2, duration: 500 });
                            }
                            return;
                        }

                        // Click same entity → deselect; click different → select new
                        if (selectedEntity && selectedEntity.type === props.type && selectedEntity.id === props.id) {
                            onEntityClick?.(null);
                            setEntityPopup(null);
                        } else {
                            // Set entity popup card at click location
                            const clickLng = e.lngLat.lng;
                            const clickLat = e.lngLat.lat;
                            setEntityPopup({
                                lat: clickLat,
                                lng: clickLng,
                                type: props.type || 'unknown',
                                props: { ...props }
                            });
                            onEntityClick?.({
                                id: props.id,
                                type: props.type,
                                name: props.name,
                                media_url: props.media_url,
                                extra: props
                            });
                        }
                    } else {
                        // Clicked empty map → deselect
                        if (selectedEntity) onEntityClick?.(null);
                        setEntityPopup(null);
                    }
                }}
            >
                {/* SOLAR TERMINATOR — night overlay */}
                {activeLayers.day_night && nightGeoJSON && (
                    <Source id="night-overlay" type="geojson" data={nightGeoJSON as any}>
                        <Layer
                            id="night-overlay-layer"
                            type="fill"
                            paint={{
                                'fill-color': '#0a0e1a',
                                'fill-opacity': 0.35,
                            }}
                        />
                    </Source>
                )}

                {/* NOAA Weather Radar — NEXRAD composite via Iowa State Mesonet */}
                {activeLayers.weather_alerts && (
                    <Source
                        id="weather-radar"
                        type="raster"
                        tiles={[`https://mesonet.agron.iastate.edu/cache/tile.py/1.0.0/nexrad-n0q-900913/{z}/{x}/{y}.png?_=${Math.floor(Date.now() / 300000)}`]}
                        tileSize={256}
                    >
                        <Layer
                            id="weather-radar-layer"
                            type="raster"
                            paint={{
                                'raster-opacity': 0.55,
                                'raster-fade-duration': 300,
                            }}
                        />
                    </Source>
                )}

                {commFlightsGeoJSON && (
                    <Source id="commercial-flights" type="geojson" data={commFlightsGeoJSON as any}>
                        <Layer
                            id="commercial-flights-layer"
                            type="symbol"
                            layout={{
                                'icon-image': ['get', 'iconId'],
                                'icon-size': 0.8,
                                'icon-allow-overlap': true,
                                'icon-rotate': ['get', 'rotation'],
                                'icon-rotation-alignment': 'map'
                            }}
                            paint={{ 'icon-opacity': opacityFilter }}
                        />
                    </Source>
                )}

                {privFlightsGeoJSON && (
                    <Source id="private-flights" type="geojson" data={privFlightsGeoJSON as any}>
                        <Layer
                            id="private-flights-layer"
                            type="symbol"
                            layout={{
                                'icon-image': ['get', 'iconId'],
                                'icon-size': 0.8,
                                'icon-allow-overlap': true,
                                'icon-rotate': ['get', 'rotation'],
                                'icon-rotation-alignment': 'map'
                            }}
                            paint={{ 'icon-opacity': opacityFilter }}
                        />
                    </Source>
                )}

                {privJetsGeoJSON && (
                    <Source id="private-jets" type="geojson" data={privJetsGeoJSON as any}>
                        <Layer
                            id="private-jets-layer"
                            type="symbol"
                            layout={{
                                'icon-image': ['get', 'iconId'],
                                'icon-size': 0.8,
                                'icon-allow-overlap': true,
                                'icon-rotate': ['get', 'rotation'],
                                'icon-rotation-alignment': 'map'
                            }}
                            paint={{ 'icon-opacity': opacityFilter }}
                        />
                    </Source>
                )}

                {milFlightsGeoJSON && (
                    <Source id="military-flights" type="geojson" data={milFlightsGeoJSON as any}>
                        <Layer
                            id="military-flights-layer"
                            type="symbol"
                            layout={{
                                'icon-image': ['get', 'iconId'],
                                'icon-size': 0.8,
                                'icon-allow-overlap': true,
                                'icon-rotate': ['get', 'rotation'],
                                'icon-rotation-alignment': 'map'
                            }}
                            paint={{ 'icon-opacity': opacityFilter }}
                        />
                    </Source>
                )}

                {shipsGeoJSON && (
                    <Source
                        id="ships"
                        type="geojson"
                        data={shipsGeoJSON as any}
                        cluster={true}
                        clusterMaxZoom={8}
                        clusterRadius={40}
                    >
                        {/* Clustered circles */}
                        <Layer
                            id="ships-clusters-layer"
                            type="circle"
                            filter={['has', 'point_count']}
                            paint={{
                                'circle-opacity': opacityFilter,
                                'circle-stroke-opacity': opacityFilter,
                                'circle-color': 'rgba(30, 64, 175, 0.85)',
                                'circle-radius': [
                                    'step',
                                    ['get', 'point_count'],
                                    12,
                                    10, 15,
                                    100, 20,
                                    1000, 25,
                                    5000, 30
                                ],
                                'circle-stroke-width': 2,
                                'circle-stroke-color': 'rgba(59, 130, 246, 1.0)'
                            }}
                        />

                        {/* Cluster count - rendered via HTML markers below */}
                        <Layer
                            id="ships-cluster-count-layer"
                            type="circle"
                            filter={['has', 'point_count']}
                            paint={{ 'circle-radius': 0, 'circle-opacity': 0 }}
                        />

                        {/* Unclustered individual ships (Cargo, Tankers, etc.) */}
                        <Layer
                            id="ships-layer"
                            type="symbol"
                            minzoom={4}
                            filter={['!', ['has', 'point_count']]}
                            layout={{
                                'icon-image': ['get', 'iconId'],
                                'icon-size': 0.8,
                                'icon-allow-overlap': true,
                                'icon-rotate': ['get', 'rotation'],
                                'icon-rotation-alignment': 'map'
                            }}
                            paint={{
                                'icon-opacity': opacityFilter
                            }}
                        />
                    </Source>
                )}

                {carriersGeoJSON && (
                    <Source id="carriers" type="geojson" data={carriersGeoJSON as any}>
                        <Layer
                            id="carriers-layer"
                            type="symbol"
                            layout={{
                                'icon-image': 'svgCarrier',
                                'icon-size': 0.8,
                                'icon-allow-overlap': true,
                                'icon-rotate': ['get', 'rotation'],
                                'icon-rotation-alignment': 'map'
                            }}
                            paint={{ 'icon-opacity': opacityFilter }}
                        />
                    </Source>
                )}


                {activeRouteGeoJSON && (
                    <Source id="active-route" type="geojson" data={activeRouteGeoJSON as any}>
                        <Layer
                            id="active-route-layer"
                            type="line"
                            paint={{
                                'line-color': [
                                    'match',
                                    ['get', 'type'],
                                    'route-origin', '#38bdf8', // light blue
                                    'route-dest', '#fcd34d', // yellow
                                    '#ffffff'
                                ],
                                'line-width': 2,
                                'line-dasharray': [2, 2],
                                'line-opacity': 0.8
                            }}
                        />
                    </Source>
                )}

                {/* Flight trail history (where the aircraft has been) */}
                {trailGeoJSON && (
                    <Source id="flight-trail" type="geojson" data={trailGeoJSON as any}>
                        <Layer
                            id="flight-trail-layer"
                            type="line"
                            paint={{
                                'line-color': '#22d3ee',
                                'line-width': 2,
                                'line-opacity': 0.6,
                            }}
                        />
                    </Source>
                )}

                {trackedFlightsGeoJSON && (
                    <Source id="tracked-flights" type="geojson" data={trackedFlightsGeoJSON as any}>
                        <Layer
                            id="tracked-flights-layer"
                            type="symbol"
                            layout={{
                                'icon-image': ['get', 'iconId'],
                                'icon-size': 0.8,
                                'icon-allow-overlap': true,
                                'icon-rotate': ['get', 'rotation'],
                                'icon-rotation-alignment': 'map'
                            }}
                            paint={{ 'icon-opacity': opacityFilter }}
                        />
                    </Source>
                )}

                {uavGeoJSON && (
                    <Source id="uavs" type="geojson" data={uavGeoJSON as any}>
                        <Layer
                            id="uav-layer"
                            type="symbol"
                            layout={{
                                'icon-image': ['get', 'iconId'],
                                'icon-size': 0.8,
                                'icon-allow-overlap': true,
                                'icon-rotate': ['get', 'rotation'],
                                'icon-rotation-alignment': 'map'
                            }}
                            paint={{ 'icon-opacity': opacityFilter }}
                        />
                    </Source>
                )}

                {/* UAV Operational Range Circles */}
                {uavRangeGeoJSON && (
                    <Source id="uav-ranges" type="geojson" data={uavRangeGeoJSON as any}>
                        <Layer
                            id="uav-range-fill"
                            type="fill"
                            paint={{
                                'fill-color': '#ff4444',
                                'fill-opacity': 0.04
                            }}
                        />
                        <Layer
                            id="uav-range-border"
                            type="line"
                            paint={{
                                'line-color': '#ff4444',
                                'line-width': 1,
                                'line-opacity': 0.3,
                                'line-dasharray': [4, 4]
                            }}
                        />
                    </Source>
                )}

                {gdeltGeoJSON && (
                    <Source id="gdelt" type="geojson" data={gdeltGeoJSON as any}>
                        <Layer
                            id="gdelt-layer"
                            type="circle"
                            minzoom={4}
                            paint={{
                                'circle-radius': 5,
                                'circle-color': '#ff8c00',
                                'circle-stroke-color': '#ff0000',
                                'circle-stroke-width': 1,
                                'circle-opacity': 0.7
                            }}
                        />
                    </Source>
                )}

                {liveuaGeoJSON && (
                    <Source id="liveuamap" type="geojson" data={liveuaGeoJSON as any}>
                        <Layer
                            id="liveuamap-layer"
                            type="symbol"
                            minzoom={4}
                            layout={{
                                'icon-image': ['get', 'iconId'],
                                'icon-size': 0.8,
                                'icon-allow-overlap': true,
                            }}
                        />
                    </Source>
                )}

                {/* HTML labels for ship cluster counts (hidden when any entity popup is active) */}
                {shipsGeoJSON && !selectedEntity && shipClusters.map((c: any) => (
                    <Marker key={`sc-${c.id}`} longitude={c.lng} latitude={c.lat} anchor="center" style={{ zIndex: 1 }}>
                        <div style={{ color: '#fff', fontSize: '11px', fontFamily: 'monospace', fontWeight: 'bold', textShadow: '0 0 3px #000, 0 0 3px #000', pointerEvents: 'none', textAlign: 'center' }}>
                            {c.count}
                        </div>
                    </Marker>
                ))}

                {/* HTML labels for tracked flights (pink names, grey when grounded) */}
                {trackedFlightsGeoJSON && !selectedEntity && data?.tracked_flights?.map((f: any, i: number) => {
                    if (f.lat == null || f.lng == null) return null;
                    if (!inView(f.lat, f.lng)) return null;
                    const displayName = f.alert_operator || f.operator || f.owner || f.name || f.callsign || f.icao24 || "UNKNOWN";
                    const grounded = f.alt != null && f.alt <= 100;
                    const [iLng, iLat] = interpFlight(f);
                    return (
                        <Marker key={`tf-label-${i}`} longitude={iLng} latitude={iLat} anchor="top" offset={[0, 10]} style={{ zIndex: 2 }}>
                            <div style={{ color: grounded ? '#888' : '#ff1493', fontSize: '10px', fontFamily: 'monospace', fontWeight: 'bold', textShadow: '0 0 3px #000, 0 0 3px #000, 1px 1px 2px #000', whiteSpace: 'nowrap', pointerEvents: 'none' }}>
                                {String(displayName)}
                            </div>
                        </Marker>
                    );
                })}

                {/* HTML labels for carriers (orange names) */}
                {carriersGeoJSON && !selectedEntity && data?.ships?.map((s: any, i: number) => {
                    if (s.type !== 'carrier' || s.lat == null || s.lng == null) return null;
                    if (!inView(s.lat, s.lng)) return null;
                    const [iLng, iLat] = interpShip(s);
                    return (
                        <Marker key={`carrier-label-${i}`} longitude={iLng} latitude={iLat} anchor="top" offset={[0, 12]} style={{ zIndex: 2 }}>
                            <div style={{ color: '#ffaa00', fontSize: '11px', fontFamily: 'monospace', fontWeight: 'bold', textShadow: '0 0 3px #000, 0 0 3px #000, 1px 1px 2px #000', whiteSpace: 'nowrap', pointerEvents: 'none' }}>
                                [[{s.name}]]
                            </div>
                        </Marker>
                    );
                })}

                {/* HTML labels for earthquake cluster counts (hidden when any entity popup is active) */}
                {earthquakesGeoJSON && !selectedEntity && eqClusters.map((c: any) => (
                    <Marker key={`eqc-${c.id}`} longitude={c.lng} latitude={c.lat} anchor="center" style={{ zIndex: 1 }}>
                        <div style={{ color: '#fff', fontSize: '11px', fontFamily: 'monospace', fontWeight: 'bold', textShadow: '0 0 3px #000, 0 0 3px #000', pointerEvents: 'none', textAlign: 'center' }}>
                            {c.count}
                        </div>
                    </Marker>
                ))}

                {/* HTML labels for UAVs (orange names) */}
                {uavGeoJSON && !selectedEntity && data?.uavs?.map((uav: any, i: number) => {
                    if (uav.lat == null || uav.lng == null) return null;
                    if (!inView(uav.lat, uav.lng)) return null;
                    const name = uav.aircraft_model ? `[UAV: ${uav.aircraft_model}]` : `[UAV: ${uav.callsign}]`;
                    return (
                        <Marker key={`uav-label-${i}`} longitude={uav.lng} latitude={uav.lat} anchor="top" offset={[0, 10]} style={{ zIndex: 2 }}>
                            <div style={{ color: '#ff8c00', fontSize: '10px', fontFamily: 'monospace', fontWeight: 'bold', textShadow: '0 0 3px #000, 0 0 3px #000, 1px 1px 2px #000', whiteSpace: 'nowrap', pointerEvents: 'none' }}>
                                {name}
                            </div>
                        </Marker>
                    );
                })}

                {/* HTML labels for earthquakes (yellow) - only show when zoomed in (~2000 miles = zoom ~5) */}
                {earthquakesGeoJSON && !selectedEntity && viewState.zoom >= 5 && data?.earthquakes?.map((eq: any, i: number) => {
                    if (eq.lat == null || eq.lng == null) return null;
                    if (!inView(eq.lat, eq.lng)) return null;
                    return (
                        <Marker key={`eq-label-${i}`} longitude={eq.lng} latitude={eq.lat} anchor="top" offset={[0, 14]} style={{ zIndex: 1 }}>
                            <div style={{ color: '#ffcc00', fontSize: '10px', fontFamily: 'monospace', fontWeight: 'bold', textShadow: '0 0 3px #000, 0 0 3px #000, 1px 1px 2px #000', whiteSpace: 'nowrap', pointerEvents: 'none' }}>
                                [M{eq.mag}] {eq.place || ''}
                            </div>
                        </Marker>
                    );
                })}

                {/* Maplibre HTML Custom Markers for high-importance Threat Overlays (highest z-index) */}
                {activeLayers.global_incidents && spreadAlerts.map((n: any) => {
                    const idx = n.originalIdx;
                    const count = n.cluster_count || 1;
                    const score = n.risk_score || 0;

                    let riskColor = '#22c55e'; // Green (1-3)
                    if (score >= 9) riskColor = '#ef4444'; // Red (9-10)
                    else if (score >= 7) riskColor = '#f97316'; // Orange (7-8)
                    else if (score >= 4) riskColor = '#eab308'; // Yellow (4-6)
                    else if (score >= 1) riskColor = '#3b82f6'; // Blue (1-3)

                    // Hide alerts when any entity is selected (focus mode)
                    // For news: only show the selected alert. For all others: hide all alerts.
                    let isVisible = viewState.zoom >= 1;
                    if (selectedEntity) {
                        if (selectedEntity.type === 'news') {
                            if (selectedEntity.id !== idx) isVisible = false;
                        } else {
                            isVisible = false;
                        }
                    }

                    return (
                        <Marker
                            key={`threat-${idx}`}
                            longitude={n.coords[1]}
                            latitude={n.coords[0]}
                            anchor="center"
                            offset={[n.offsetX, n.offsetY]}
                            style={{ zIndex: 50 + score }}
                            onClick={(e) => {
                                e.originalEvent.stopPropagation();
                                onEntityClick?.({ id: idx, type: 'news' });
                            }}
                        >
                            <div className="relative group/alert">
                                {/* Connector Line for scattered markers (Speech Bubble Line) */}
                                {n.showLine && isVisible && (
                                    <svg className="absolute pointer-events-none" style={{ left: '50%', top: '50%', width: 1, height: 1, overflow: 'visible', zIndex: -1 }}>
                                        <line x1={0} y1={0} x2={-n.offsetX} y2={-n.offsetY} stroke={riskColor} strokeWidth="1.5" strokeDasharray="3,3" className="opacity-80" />
                                        <circle cx={-n.offsetX} cy={-n.offsetY} r="2" fill={riskColor} />
                                    </svg>
                                )}

                                <div
                                    className="cursor-pointer transition-all duration-300 relative"
                                    style={{
                                        opacity: isVisible ? 1.0 : 0.0,
                                        pointerEvents: isVisible ? 'auto' : 'none',
                                        backgroundColor: 'rgba(5, 5, 5, 0.95)',
                                        border: `1.5px solid ${riskColor}`,
                                        borderRadius: '4px',
                                        padding: '5px 8px',
                                        color: riskColor,
                                        fontFamily: 'monospace',
                                        fontSize: '9px',
                                        fontWeight: 'bold',
                                        textAlign: 'center',
                                        boxShadow: `0 0 12px ${riskColor}60`,
                                        zIndex: 10,
                                        lineHeight: '1.2',
                                        minWidth: '120px'
                                    }}
                                >
                                    {/* Bubble Tail / Triangle */}
                                    {n.showLine && isVisible && (
                                        <div
                                            className="absolute"
                                            style={{
                                                width: 0,
                                                height: 0,
                                                borderLeft: '6px solid transparent',
                                                borderRight: '6px solid transparent',
                                                // If above origin, point down. If below, point up.
                                                borderTop: n.offsetY < 0 ? `6px solid ${riskColor}` : 'none',
                                                borderBottom: n.offsetY > 0 ? `6px solid ${riskColor}` : 'none',
                                                left: '50%',
                                                [n.offsetY < 0 ? 'bottom' : 'top']: '-6px',
                                                transform: 'translateX(-50%)'
                                            }}
                                        />
                                    )}

                                    <div className="absolute inset-0 border border-current rounded opacity-50 animate-pulse" style={{ color: riskColor, zIndex: -1 }}></div>
                                    <div style={{ fontSize: '10px', letterSpacing: '0.5px' }}>!! ALERT LVL {score} !!</div>
                                    <div style={{ color: '#fff', fontSize: '9px', marginTop: '2px', maxWidth: '160px', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                                        {n.title}
                                    </div>
                                    {count > 1 && (
                                        <div style={{ color: riskColor, opacity: 0.8, fontSize: '8px', marginTop: '2px' }}>
                                            [+{count - 1} ACTIVE THREATS IN AREA]
                                        </div>
                                    )}
                                </div>
                            </div>
                        </Marker>
                    );
                })}

                {frontlineGeoJSON && (
                    <Source id="frontlines" type="geojson" data={frontlineGeoJSON as any}>
                        <Layer
                            id="ukraine-frontline-layer"
                            type="fill"
                            paint={{
                                'fill-color': '#ff0000',
                                'fill-opacity': 0.3,
                                'fill-outline-color': '#ff5500'
                            }}
                        />
                    </Source>
                )}

                {earthquakesGeoJSON && (
                    <Source
                        id="earthquakes"
                        type="geojson"
                        data={earthquakesGeoJSON as any}
                        cluster={true}
                        clusterMaxZoom={10}
                        clusterRadius={60}
                    >
                        {/* Earthquake cluster circles */}
                        <Layer
                            id="eq-clusters-layer"
                            type="circle"
                            filter={['has', 'point_count']}
                            paint={{
                                'circle-color': 'rgba(255, 170, 0, 0.85)',
                                'circle-radius': [
                                    'step',
                                    ['get', 'point_count'],
                                    12,
                                    5, 16,
                                    10, 20,
                                    20, 24
                                ],
                                'circle-stroke-width': 2,
                                'circle-stroke-color': 'rgba(255, 200, 0, 1.0)'
                            }}
                        />
                        {/* Individual (unclustered) earthquake icons */}
                        <Layer
                            id="earthquakes-layer"
                            type="symbol"
                            filter={['!', ['has', 'point_count']]}
                            layout={{
                                'icon-image': 'icon-threat',
                                'icon-size': 0.5,
                                'icon-allow-overlap': true
                            }}
                            paint={{ 'icon-opacity': 1.0 }}
                        />
                    </Source>
                )}

                {/* GPS Jamming Zones — red translucent grid squares */}
                {jammingGeoJSON && (
                    <Source id="gps-jamming" type="geojson" data={jammingGeoJSON as any}>
                        <Layer
                            id="gps-jamming-fill"
                            type="fill"
                            paint={{
                                'fill-color': '#ff0040',
                                'fill-opacity': ['get', 'opacity']
                            }}
                        />
                        <Layer
                            id="gps-jamming-outline"
                            type="line"
                            paint={{
                                'line-color': '#ff0040',
                                'line-width': 1.5,
                                'line-opacity': 0.6
                            }}
                        />
                        <Layer
                            id="gps-jamming-label"
                            type="symbol"
                            layout={{
                                'text-field': ['concat', 'GPS JAM ', ['to-string', ['round', ['*', 100, ['get', 'ratio']]]], '%'],
                                'text-size': [
                                    'interpolate', ['linear'], ['zoom'],
                                    2, 8,
                                    5, 10,
                                    8, 12
                                ],
                                'text-allow-overlap': false,
                                'text-ignore-placement': false
                            }}
                            paint={{
                                'text-color': '#ff4060',
                                'text-halo-color': '#000000',
                                'text-halo-width': 1.5
                            }}
                        />
                    </Source>
                )}

                {/* FAA TFRs — red polygons showing flight restrictions */}
                {tfrGeoJSON && (
                    <Source id="tfrs" type="geojson" data={tfrGeoJSON as any}>
                        <Layer
                            id="tfr-fill"
                            type="fill"
                            paint={{
                                'fill-color': '#ff2020',
                                'fill-opacity': 0.15,
                            }}
                        />
                        <Layer
                            id="tfr-outline"
                            type="line"
                            paint={{
                                'line-color': '#ff4040',
                                'line-width': 2,
                                'line-dasharray': [4, 2],
                                'line-opacity': 0.8,
                            }}
                        />
                        <Layer
                            id="tfr-label"
                            type="symbol"
                            layout={{
                                'text-field': ['get', 'legal'],
                                'text-size': 10,
                                'text-allow-overlap': false,
                            }}
                            paint={{
                                'text-color': '#ff6060',
                                'text-halo-color': '#000000',
                                'text-halo-width': 1.5,
                            }}
                        />
                    </Source>
                )}

                {/* NWS Weather Alerts — amber/red polygons */}
                {weatherAlertGeoJSON && (
                    <Source id="weather-alerts" type="geojson" data={weatherAlertGeoJSON as any}>
                        <Layer
                            id="weather-alert-fill"
                            type="fill"
                            paint={{
                                'fill-color': [
                                    'match', ['get', 'severity'],
                                    'Extreme', '#ff0000',
                                    'Severe', '#ff4500',
                                    '#ffaa00'
                                ],
                                'fill-opacity': 0.12,
                            }}
                        />
                        <Layer
                            id="weather-alert-outline"
                            type="line"
                            paint={{
                                'line-color': [
                                    'match', ['get', 'severity'],
                                    'Extreme', '#ff0000',
                                    'Severe', '#ff6600',
                                    '#ffcc00'
                                ],
                                'line-width': 1.5,
                                'line-opacity': 0.7,
                            }}
                        />
                        <Layer
                            id="weather-alert-label"
                            type="symbol"
                            layout={{
                                'text-field': ['get', 'event'],
                                'text-size': 9,
                                'text-allow-overlap': false,
                            }}
                            paint={{
                                'text-color': '#ffcc00',
                                'text-halo-color': '#000000',
                                'text-halo-width': 1.5,
                            }}
                        />
                    </Source>
                )}

                {/* NASA EONET Natural Events — colored circles */}
                {naturalEventGeoJSON && (
                    <Source id="natural-events" type="geojson" data={naturalEventGeoJSON as any}>
                        <Layer
                            id="natural-events-layer"
                            type="circle"
                            paint={{
                                'circle-color': [
                                    'match', ['get', 'category_id'],
                                    'wildfires', '#ff4500',
                                    'volcanoes', '#ff0000',
                                    'severeStorms', '#9400d3',
                                    'floods', '#1e90ff',
                                    'seaLakeIce', '#00ced1',
                                    '#ffaa00'
                                ],
                                'circle-radius': [
                                    'interpolate', ['linear'], ['zoom'],
                                    1, 4,
                                    5, 7,
                                    10, 10
                                ],
                                'circle-opacity': 0.85,
                                'circle-stroke-width': 2,
                                'circle-stroke-color': '#000000',
                            }}
                        />
                        <Layer
                            id="natural-events-label"
                            type="symbol"
                            layout={{
                                'text-field': ['get', 'title'],
                                'text-size': 9,
                                'text-offset': [0, 1.5],
                                'text-allow-overlap': false,
                            }}
                            paint={{
                                'text-color': '#ffffff',
                                'text-halo-color': '#000000',
                                'text-halo-width': 1.5,
                            }}
                        />
                    </Source>
                )}

                {/* NASA FIRMS Fire Hotspots — clustered orange/red heat dots */}
                {firmsGeoJSON && (
                    <Source id="firms" type="geojson" data={firmsGeoJSON as any} cluster={true} clusterRadius={40} clusterMaxZoom={10}>
                        <Layer
                            id="firms-clusters"
                            type="circle"
                            filter={['has', 'point_count']}
                            paint={{
                                'circle-color': '#ff4500',
                                'circle-radius': [
                                    'step', ['get', 'point_count'],
                                    10, 50,
                                    16, 500,
                                    22, 5000,
                                    28
                                ],
                                'circle-opacity': 0.75,
                                'circle-stroke-width': 2,
                                'circle-stroke-color': '#ff0000'
                            }}
                        />
                        <Layer
                            id="firms-cluster-count"
                            type="symbol"
                            filter={['has', 'point_count']}
                            layout={{
                                'text-field': '{point_count_abbreviated}',
                                'text-size': 10,
                                'text-allow-overlap': true
                            }}
                            paint={{
                                'text-color': '#ffffff',
                                'text-halo-color': '#000000',
                                'text-halo-width': 1
                            }}
                        />
                        <Layer
                            id="firms-layer"
                            type="circle"
                            filter={['!', ['has', 'point_count']]}
                            paint={{
                                'circle-color': [
                                    'interpolate', ['linear'], ['get', 'frp'],
                                    0, '#ff8c00',
                                    50, '#ff4500',
                                    200, '#ff0000'
                                ],
                                'circle-radius': [
                                    'interpolate', ['linear'], ['zoom'],
                                    1, 2,
                                    6, 4,
                                    12, 7
                                ],
                                'circle-opacity': 0.8,
                                'circle-stroke-width': 1,
                                'circle-stroke-color': '#cc0000'
                            }}
                        />
                    </Source>
                )}

                {/* Power Outages — severity-colored polygons (NWS severe weather) and circles */}
                {powerOutageGeoJSON && (
                    <Source id="power-outages" type="geojson" data={powerOutageGeoJSON as any}>
                        {/* Polygon fill for NWS alert zones */}
                        <Layer
                            id="power-outage-fill"
                            type="fill"
                            filter={['any', ['==', ['geometry-type'], 'Polygon'], ['==', ['geometry-type'], 'MultiPolygon']]}
                            paint={{
                                'fill-color': [
                                    'match', ['get', 'severity'],
                                    'Extreme', '#ff0000',
                                    'Severe', '#ff6600',
                                    'Moderate', '#ffcc00',
                                    '#ffcc00'
                                ],
                                'fill-opacity': 0.25,
                            }}
                        />
                        <Layer
                            id="power-outage-outline"
                            type="line"
                            filter={['any', ['==', ['geometry-type'], 'Polygon'], ['==', ['geometry-type'], 'MultiPolygon']]}
                            paint={{
                                'line-color': [
                                    'match', ['get', 'severity'],
                                    'Extreme', '#ff0000',
                                    'Severe', '#ff6600',
                                    'Moderate', '#ffcc00',
                                    '#ffcc00'
                                ],
                                'line-width': 1.5,
                                'line-opacity': 0.7,
                            }}
                        />
                        {/* Circle fallback for point-based outages */}
                        <Layer
                            id="power-outage-layer"
                            type="circle"
                            filter={['==', ['geometry-type'], 'Point']}
                            paint={{
                                'circle-color': [
                                    'match', ['get', 'severity'],
                                    'Extreme', '#ff0000',
                                    'Severe', '#ff6600',
                                    'Major', '#ff6600',
                                    'Moderate', '#ffcc00',
                                    '#ffcc00'
                                ],
                                'circle-radius': [
                                    'interpolate', ['linear'], ['get', 'customers_out'],
                                    100, 6, 10000, 14, 100000, 24
                                ],
                                'circle-opacity': 0.7,
                                'circle-stroke-width': 2,
                                'circle-stroke-color': '#000'
                            }}
                        />
                        <Layer
                            id="power-outage-label"
                            type="symbol"
                            minzoom={5}
                            layout={{
                                'text-field': ['get', 'event'],
                                'text-size': 9,
                                'text-offset': [0, 1.5],
                                'text-allow-overlap': false,
                                'text-max-width': 12,
                            }}
                            paint={{
                                'text-color': '#ffcc00',
                                'text-halo-color': '#000',
                                'text-halo-width': 1.5,
                            }}
                        />
                    </Source>
                )}

                {/* Internet Outages — red/orange indicators */}
                {internetOutageGeoJSON && (
                    <Source id="internet-outages" type="geojson" data={internetOutageGeoJSON as any}>
                        {/* Polygon fill for weather-related geometry */}
                        <Layer
                            id="internet-outage-fill"
                            type="fill"
                            filter={['any', ['==', ['geometry-type'], 'Polygon'], ['==', ['geometry-type'], 'MultiPolygon']]}
                            paint={{
                                'fill-color': '#e11d48',
                                'fill-opacity': 0.2,
                            }}
                        />
                        <Layer
                            id="internet-outage-outline"
                            type="line"
                            filter={['any', ['==', ['geometry-type'], 'Polygon'], ['==', ['geometry-type'], 'MultiPolygon']]}
                            paint={{
                                'line-color': '#e11d48',
                                'line-width': 1.5,
                                'line-opacity': 0.6,
                            }}
                        />
                        <Layer
                            id="internet-outage-layer"
                            type="circle"
                            filter={['==', ['geometry-type'], 'Point']}
                            paint={{
                                'circle-color': [
                                    'match', ['get', 'event_type'],
                                    'bgp', '#e11d48',
                                    'active_probing', '#f97316',
                                    'asn', '#dc2626',
                                    'weather-related', '#f59e0b',
                                    '#e11d48'
                                ],
                                'circle-radius': 10,
                                'circle-opacity': 0.7,
                                'circle-stroke-width': 2,
                                'circle-stroke-color': '#000',
                            }}
                        />
                        <Layer
                            id="internet-outage-label"
                            type="symbol"
                            minzoom={3}
                            layout={{
                                'text-field': ['get', 'country'],
                                'text-size': 10,
                                'text-offset': [0, 1.5],
                                'text-allow-overlap': false,
                                'text-max-width': 12,
                            }}
                            paint={{
                                'text-color': '#fb7185',
                                'text-halo-color': '#000',
                                'text-halo-width': 1.5,
                            }}
                        />
                    </Source>
                )}

                {/* Air Quality — colored circles by PM2.5 level */}
                {aqiGeoJSON && (
                    <Source id="air-quality" type="geojson" data={aqiGeoJSON as any}>
                        <Layer
                            id="aqi-layer"
                            type="circle"
                            paint={{
                                'circle-color': [
                                    'match', ['get', 'level'],
                                    'Hazardous', '#7e0023',
                                    'Very Unhealthy', '#8f3f97',
                                    'Unhealthy', '#ff0000',
                                    'Unhealthy for Sensitive', '#ff7e00',
                                    '#ffcc00'
                                ],
                                'circle-radius': [
                                    'interpolate', ['linear'], ['get', 'pm25'],
                                    25, 5,
                                    100, 10,
                                    300, 18
                                ],
                                'circle-opacity': 0.7,
                                'circle-stroke-width': 1.5,
                                'circle-stroke-color': '#000000'
                            }}
                        />
                        <Layer
                            id="aqi-label"
                            type="symbol"
                            layout={{
                                'text-field': ['concat', 'PM2.5: ', ['to-string', ['round', ['get', 'pm25']]]],
                                'text-size': 9,
                                'text-offset': [0, 1.5],
                                'text-allow-overlap': false,
                            }}
                            paint={{
                                'text-color': '#ffaa00',
                                'text-halo-color': '#000000',
                                'text-halo-width': 1.5,
                            }}
                        />
                    </Source>
                )}

                {/* Radioactivity Monitoring — green/yellow/red circles */}
                {radioactivityGeoJSON && (
                    <Source id="radioactivity" type="geojson" data={radioactivityGeoJSON as any}>
                        <Layer
                            id="radioactivity-layer"
                            type="circle"
                            paint={{
                                'circle-color': [
                                    'interpolate', ['linear'], ['get', 'value'],
                                    0, '#22c55e',
                                    100, '#ffcc00',
                                    500, '#ff4500',
                                    1000, '#ff0000'
                                ],
                                'circle-radius': [
                                    'interpolate', ['linear'], ['zoom'],
                                    1, 3,
                                    6, 5,
                                    10, 8
                                ],
                                'circle-opacity': 0.7,
                                'circle-stroke-width': 1,
                                'circle-stroke-color': '#000000'
                            }}
                        />
                        <Layer
                            id="radioactivity-label"
                            type="symbol"
                            layout={{
                                'text-field': ['get', 'name'],
                                'text-size': 8,
                                'text-offset': [0, 1.5],
                                'text-allow-overlap': false,
                            }}
                            paint={{
                                'text-color': '#88ff88',
                                'text-halo-color': '#000000',
                                'text-halo-width': 1.5,
                            }}
                        />
                    </Source>
                )}

                {/* Military Bases — clustered olive/green markers */}
                {milBasesGeoJSON && (
                    <Source id="military-bases" type="geojson" data={milBasesGeoJSON as any} cluster={true} clusterRadius={40} clusterMaxZoom={8}>
                        <Layer
                            id="mil-base-clusters"
                            type="circle"
                            filter={['has', 'point_count']}
                            paint={{
                                'circle-color': '#556b2f',
                                'circle-radius': ['step', ['get', 'point_count'], 12, 10, 16, 50, 22],
                                'circle-opacity': 0.8,
                                'circle-stroke-width': 2,
                                'circle-stroke-color': '#2d3a1a'
                            }}
                        />
                        <Layer
                            id="mil-base-cluster-count"
                            type="symbol"
                            filter={['has', 'point_count']}
                            layout={{ 'text-field': '{point_count_abbreviated}', 'text-size': 10, 'text-allow-overlap': true }}
                            paint={{ 'text-color': '#ffffff', 'text-halo-color': '#000', 'text-halo-width': 1 }}
                        />
                        <Layer
                            id="mil-base-layer"
                            type="circle"
                            filter={['!', ['has', 'point_count']]}
                            paint={{
                                'circle-color': '#556b2f',
                                'circle-radius': ['interpolate', ['linear'], ['zoom'], 1, 3, 6, 5, 12, 8],
                                'circle-opacity': 0.85,
                                'circle-stroke-width': 2,
                                'circle-stroke-color': '#2d3a1a'
                            }}
                        />
                        <Layer
                            id="mil-base-label"
                            type="symbol"
                            filter={['!', ['has', 'point_count']]}
                            minzoom={8}
                            layout={{ 'text-field': ['get', 'name'], 'text-size': 9, 'text-offset': [0, 1.5], 'text-allow-overlap': false }}
                            paint={{ 'text-color': '#9acd32', 'text-halo-color': '#000', 'text-halo-width': 1.5 }}
                        />
                    </Source>
                )}

                {/* Nuclear Facilities — yellow/red radiation markers */}
                {nuclearGeoJSON && (
                    <Source id="nuclear-facilities" type="geojson" data={nuclearGeoJSON as any}>
                        <Layer
                            id="nuclear-layer"
                            type="circle"
                            paint={{
                                'circle-color': [
                                    'match', ['get', 'status'],
                                    'Operational', '#ffcc00',
                                    'Under Construction', '#ff8800',
                                    'Shutdown', '#666666',
                                    'Decommissioned', '#444444',
                                    '#ffcc00'
                                ],
                                'circle-radius': ['interpolate', ['linear'], ['zoom'], 1, 4, 6, 7, 12, 12],
                                'circle-opacity': 0.85,
                                'circle-stroke-width': 2,
                                'circle-stroke-color': '#ff4500'
                            }}
                        />
                        <Layer
                            id="nuclear-label"
                            type="symbol"
                            minzoom={6}
                            layout={{ 'text-field': ['get', 'name'], 'text-size': 9, 'text-offset': [0, 1.5], 'text-allow-overlap': false }}
                            paint={{ 'text-color': '#ffcc00', 'text-halo-color': '#000', 'text-halo-width': 1.5 }}
                        />
                    </Source>
                )}

                {/* Submarine Cables — line geometries */}
                {cableGeoJSON && (
                    <Source id="submarine-cables" type="geojson" data={cableGeoJSON as any}>
                        <Layer
                            id="cable-lines"
                            type="line"
                            paint={{
                                'line-color': ['get', 'color'],
                                'line-width': ['interpolate', ['linear'], ['zoom'], 1, 0.5, 4, 1, 8, 2],
                                'line-opacity': 0.6,
                            }}
                        />
                        <Layer
                            id="cable-label"
                            type="symbol"
                            minzoom={5}
                            layout={{
                                'symbol-placement': 'line',
                                'text-field': ['get', 'name'],
                                'text-size': 9,
                                'text-allow-overlap': false,
                            }}
                            paint={{ 'text-color': '#60a5fa', 'text-halo-color': '#000', 'text-halo-width': 1.5 }}
                        />
                    </Source>
                )}

                {/* Cable Landing Points — small blue dots */}
                {cableLandingGeoJSON && (
                    <Source id="cable-landings" type="geojson" data={cableLandingGeoJSON as any}>
                        <Layer
                            id="cable-landing-layer"
                            type="circle"
                            paint={{
                                'circle-color': '#3b82f6',
                                'circle-radius': ['interpolate', ['linear'], ['zoom'], 1, 2, 6, 4, 12, 6],
                                'circle-opacity': 0.8,
                                'circle-stroke-width': 1,
                                'circle-stroke-color': '#1e3a5f'
                            }}
                        />
                    </Source>
                )}

                {/* Embassies — clustered gold markers */}
                {embassyGeoJSON && (
                    <Source id="embassies" type="geojson" data={embassyGeoJSON as any} cluster={true} clusterRadius={40} clusterMaxZoom={10}>
                        <Layer
                            id="embassy-clusters"
                            type="circle"
                            filter={['has', 'point_count']}
                            paint={{
                                'circle-color': '#b8860b',
                                'circle-radius': ['step', ['get', 'point_count'], 10, 10, 14, 50, 20],
                                'circle-opacity': 0.8,
                                'circle-stroke-width': 2,
                                'circle-stroke-color': '#8b6914'
                            }}
                        />
                        <Layer
                            id="embassy-cluster-count"
                            type="symbol"
                            filter={['has', 'point_count']}
                            layout={{ 'text-field': '{point_count_abbreviated}', 'text-size': 10, 'text-allow-overlap': true }}
                            paint={{ 'text-color': '#fff', 'text-halo-color': '#000', 'text-halo-width': 1 }}
                        />
                        <Layer
                            id="embassy-layer"
                            type="circle"
                            filter={['!', ['has', 'point_count']]}
                            paint={{
                                'circle-color': '#daa520',
                                'circle-radius': ['interpolate', ['linear'], ['zoom'], 1, 2, 8, 4, 14, 7],
                                'circle-opacity': 0.85,
                                'circle-stroke-width': 1.5,
                                'circle-stroke-color': '#8b6914'
                            }}
                        />
                        <Layer
                            id="embassy-label"
                            type="symbol"
                            filter={['!', ['has', 'point_count']]}
                            minzoom={10}
                            layout={{ 'text-field': ['get', 'name'], 'text-size': 9, 'text-offset': [0, 1.3], 'text-allow-overlap': false }}
                            paint={{ 'text-color': '#daa520', 'text-halo-color': '#000', 'text-halo-width': 1.5 }}
                        />
                    </Source>
                )}

                {/* Volcanoes — red/orange circles */}
                {volcanoGeoJSON && (
                    <Source id="volcanoes" type="geojson" data={volcanoGeoJSON as any}>
                        <Layer
                            id="volcano-layer"
                            type="circle"
                            paint={{
                                'circle-color': '#ff4500',
                                'circle-radius': ['interpolate', ['linear'], ['zoom'], 1, 4, 6, 7, 12, 11],
                                'circle-opacity': 0.85,
                                'circle-stroke-width': 2,
                                'circle-stroke-color': '#8b0000'
                            }}
                        />
                        <Layer
                            id="volcano-label"
                            type="symbol"
                            minzoom={5}
                            layout={{ 'text-field': ['get', 'name'], 'text-size': 9, 'text-offset': [0, 1.5], 'text-allow-overlap': false }}
                            paint={{ 'text-color': '#ff6347', 'text-halo-color': '#000', 'text-halo-width': 1.5 }}
                        />
                    </Source>
                )}

                {/* Piracy / ASAM incidents — red skulls / clustered */}
                {piracyGeoJSON && (
                    <Source id="piracy" type="geojson" data={piracyGeoJSON as any} cluster={true} clusterRadius={50} clusterMaxZoom={8}>
                        <Layer
                            id="piracy-clusters"
                            type="circle"
                            filter={['has', 'point_count']}
                            paint={{
                                'circle-color': '#dc2626',
                                'circle-radius': ['step', ['get', 'point_count'], 12, 10, 16, 50, 22],
                                'circle-opacity': 0.8,
                                'circle-stroke-width': 2,
                                'circle-stroke-color': '#7f1d1d'
                            }}
                        />
                        <Layer
                            id="piracy-cluster-count"
                            type="symbol"
                            filter={['has', 'point_count']}
                            layout={{ 'text-field': '{point_count_abbreviated}', 'text-size': 10, 'text-allow-overlap': true }}
                            paint={{ 'text-color': '#fff', 'text-halo-color': '#000', 'text-halo-width': 1 }}
                        />
                        <Layer
                            id="piracy-layer"
                            type="circle"
                            filter={['!', ['has', 'point_count']]}
                            paint={{
                                'circle-color': '#dc2626',
                                'circle-radius': ['interpolate', ['linear'], ['zoom'], 1, 3, 6, 5, 12, 8],
                                'circle-opacity': 0.85,
                                'circle-stroke-width': 1.5,
                                'circle-stroke-color': '#7f1d1d'
                            }}
                        />
                    </Source>
                )}

                {/* Reservoirs / Dams — blue circles */}
                {reservoirGeoJSON && (
                    <Source id="reservoirs" type="geojson" data={reservoirGeoJSON as any}>
                        <Layer
                            id="reservoir-layer"
                            type="circle"
                            paint={{
                                'circle-color': '#3b82f6',
                                'circle-radius': ['interpolate', ['linear'], ['zoom'], 1, 3, 8, 5, 14, 8],
                                'circle-opacity': 0.7,
                                'circle-stroke-width': 1.5,
                                'circle-stroke-color': '#1e3a5f'
                            }}
                        />
                        <Layer
                            id="reservoir-label"
                            type="symbol"
                            minzoom={8}
                            layout={{ 'text-field': ['concat', ['get', 'name'], '\n', ['to-string', ['get', 'level_ft']], ' ft'], 'text-size': 9, 'text-offset': [0, 1.5], 'text-allow-overlap': false }}
                            paint={{ 'text-color': '#60a5fa', 'text-halo-color': '#000', 'text-halo-width': 1.5 }}
                        />
                    </Source>
                )}

                {/* Cell Towers — magenta/purple signal dots */}
                {cellTowerGeoJSON && (
                    <Source id="cell-towers" type="geojson" data={cellTowerGeoJSON as any} cluster={true} clusterRadius={40} clusterMaxZoom={10}>
                        <Layer
                            id="cell-tower-clusters"
                            type="circle"
                            filter={['has', 'point_count']}
                            paint={{
                                'circle-color': '#a855f7',
                                'circle-radius': ['step', ['get', 'point_count'], 10, 20, 14, 100, 20],
                                'circle-opacity': 0.75,
                                'circle-stroke-width': 2,
                                'circle-stroke-color': '#6b21a8'
                            }}
                        />
                        <Layer
                            id="cell-tower-cluster-count"
                            type="symbol"
                            filter={['has', 'point_count']}
                            layout={{ 'text-field': '{point_count_abbreviated}', 'text-size': 10, 'text-allow-overlap': true }}
                            paint={{ 'text-color': '#fff', 'text-halo-color': '#000', 'text-halo-width': 1 }}
                        />
                        <Layer
                            id="cell-tower-layer"
                            type="circle"
                            filter={['!', ['has', 'point_count']]}
                            paint={{
                                'circle-color': [
                                    'match', ['get', 'radio'],
                                    'LTE', '#a855f7',
                                    'NR', '#ec4899',
                                    'UMTS', '#8b5cf6',
                                    'GSM', '#6366f1',
                                    '#a855f7'
                                ],
                                'circle-radius': ['interpolate', ['linear'], ['zoom'], 6, 3, 12, 5, 16, 8],
                                'circle-opacity': 0.8,
                                'circle-stroke-width': 1,
                                'circle-stroke-color': '#4c1d95'
                            }}
                        />
                        <Layer
                            id="cell-tower-label"
                            type="symbol"
                            filter={['!', ['has', 'point_count']]}
                            minzoom={12}
                            layout={{ 'text-field': ['get', 'radio'], 'text-size': 8, 'text-offset': [0, 1.2], 'text-allow-overlap': false }}
                            paint={{ 'text-color': '#c084fc', 'text-halo-color': '#000', 'text-halo-width': 1 }}
                        />
                    </Source>
                )}

                {/* Global Events — multi-source incidents (GDACS, WHO, ReliefWeb, FEMA etc) */}
                {globalEventsGeoJSON && (
                    <Source id="global-events" type="geojson" data={globalEventsGeoJSON as any} cluster={true} clusterRadius={50} clusterMaxZoom={8}>
                        <Layer
                            id="global-events-clusters"
                            type="circle"
                            filter={['has', 'point_count']}
                            paint={{
                                'circle-color': '#ef4444',
                                'circle-radius': ['step', ['get', 'point_count'], 12, 10, 16, 50, 22],
                                'circle-opacity': 0.8,
                                'circle-stroke-width': 2,
                                'circle-stroke-color': '#991b1b'
                            }}
                        />
                        <Layer
                            id="global-events-cluster-count"
                            type="symbol"
                            filter={['has', 'point_count']}
                            layout={{ 'text-field': '{point_count_abbreviated}', 'text-size': 10, 'text-allow-overlap': true }}
                            paint={{ 'text-color': '#fff', 'text-halo-color': '#000', 'text-halo-width': 1 }}
                        />
                        <Layer
                            id="global-events-layer"
                            type="circle"
                            filter={['!', ['has', 'point_count']]}
                            paint={{
                                'circle-color': [
                                    'match', ['get', 'source'],
                                    'GDACS', '#ef4444',
                                    'ReliefWeb', '#f97316',
                                    'WHO', '#eab308',
                                    'RSOE-EDIS', '#f43f5e',
                                    'GIM', '#dc2626',
                                    'Amnesty', '#a855f7',
                                    'UNOSAT', '#3b82f6',
                                    'FEMA', '#f59e0b',
                                    'EMSC', '#22c55e',
                                    'SPC/NOAA', '#06b6d4',
                                    '#ef4444'
                                ],
                                'circle-radius': ['interpolate', ['linear'], ['zoom'], 2, 5, 6, 7, 10, 10],
                                'circle-opacity': 0.85,
                                'circle-stroke-width': 2,
                                'circle-stroke-color': '#000'
                            }}
                        />
                        <Layer
                            id="global-events-label"
                            type="symbol"
                            filter={['!', ['has', 'point_count']]}
                            minzoom={5}
                            layout={{
                                'text-field': ['get', 'name'],
                                'text-size': 9, 'text-offset': [0, 1.5],
                                'text-allow-overlap': false,
                                'text-max-width': 12
                            }}
                            paint={{ 'text-color': '#fca5a5', 'text-halo-color': '#000', 'text-halo-width': 1 }}
                        />
                    </Source>
                )}

                {/* Border Crossings — US CBP wait times */}
                {borderCrossingGeoJSON && (
                    <Source id="border-crossings" type="geojson" data={borderCrossingGeoJSON as any}>
                        <Layer
                            id="border-crossing-layer"
                            type="circle"
                            paint={{
                                'circle-color': [
                                    'step', ['get', 'delay'],
                                    '#22c55e',  // 0 min = green
                                    15, '#eab308', // 15+ min = yellow
                                    30, '#f97316', // 30+ min = orange
                                    60, '#ef4444', // 60+ min = red
                                ],
                                'circle-radius': ['interpolate', ['linear'], ['zoom'], 3, 4, 6, 6, 10, 10],
                                'circle-opacity': 0.9,
                                'circle-stroke-width': 2,
                                'circle-stroke-color': '#000'
                            }}
                        />
                        <Layer
                            id="border-crossing-label"
                            type="symbol"
                            minzoom={5}
                            layout={{
                                'text-field': ['concat', ['get', 'name'], '\n', ['get', 'delay'], ' min'],
                                'text-size': 8, 'text-offset': [0, 1.5],
                                'text-allow-overlap': false,
                                'text-max-width': 10
                            }}
                            paint={{ 'text-color': '#86efac', 'text-halo-color': '#000', 'text-halo-width': 1 }}
                        />
                    </Source>
                )}

                {/* Cyber Threats — abuse.ch botnet C2 / IOCs */}
                {/* Cyber Attack Arcs — Check Point live attack lines (source → dest) */}
                {cyberAttackArcsGeoJSON && (
                    <Source id="cyber-attack-arcs" type="geojson" data={cyberAttackArcsGeoJSON as any}>
                        <Layer
                            id="cyber-attack-arc-layer"
                            type="line"
                            paint={{
                                'line-color': [
                                    'match', ['get', 'attack_type'],
                                    'exploit', '#ef4444',
                                    'malware', '#a855f7',
                                    'phishing', '#f59e0b',
                                    '#ef4444'
                                ],
                                'line-width': 1,
                                'line-opacity': 0.35,
                            }}
                        />
                    </Source>
                )}
                {cyberThreatGeoJSON && (
                    <Source id="cyber-threats" type="geojson" data={cyberThreatGeoJSON as any} cluster={true} clusterRadius={40} clusterMaxZoom={6}>
                        <Layer
                            id="cyber-threat-clusters"
                            type="circle"
                            filter={['has', 'point_count']}
                            paint={{
                                'circle-color': '#a855f7',
                                'circle-radius': ['step', ['get', 'point_count'], 10, 10, 14, 50, 18],
                                'circle-opacity': 0.75,
                                'circle-stroke-width': 2,
                                'circle-stroke-color': '#581c87'
                            }}
                        />
                        <Layer
                            id="cyber-threat-cluster-count"
                            type="symbol"
                            filter={['has', 'point_count']}
                            layout={{ 'text-field': '{point_count_abbreviated}', 'text-size': 9, 'text-allow-overlap': true }}
                            paint={{ 'text-color': '#fff', 'text-halo-color': '#000', 'text-halo-width': 1 }}
                        />
                        <Layer
                            id="cyber-threat-layer"
                            type="circle"
                            filter={['!', ['has', 'point_count']]}
                            paint={{
                                'circle-color': [
                                    'case',
                                    ['==', ['get', 'isLive'], 1],
                                    ['match', ['get', 'attack_type'],
                                        'exploit', '#ef4444',
                                        'malware', '#a855f7',
                                        'phishing', '#f59e0b',
                                        '#ef4444'
                                    ],
                                    '#a855f7'
                                ],
                                'circle-radius': [
                                    'case',
                                    ['==', ['get', 'isLive'], 1],
                                    ['interpolate', ['linear'], ['zoom'], 2, 3, 6, 5, 10, 8],
                                    ['interpolate', ['linear'], ['zoom'], 2, 3, 6, 5, 10, 7]
                                ],
                                'circle-opacity': [
                                    'case',
                                    ['==', ['get', 'isLive'], 1], 0.9,
                                    0.7
                                ],
                                'circle-stroke-width': 1.5,
                                'circle-stroke-color': '#000'
                            }}
                        />
                        <Layer
                            id="cyber-threat-label"
                            type="symbol"
                            filter={['!', ['has', 'point_count']]}
                            minzoom={6}
                            layout={{
                                'text-field': ['coalesce', ['get', 'attack_name'], ['get', 'malware']],
                                'text-size': 8, 'text-offset': [0, 1.4],
                                'text-allow-overlap': false,
                                'text-max-width': 12
                            }}
                            paint={{ 'text-color': '#d8b4fe', 'text-halo-color': '#000', 'text-halo-width': 1 }}
                        />
                    </Source>
                )}

                {/* NOAA Weather Radio Stations — orange broadcast towers */}
                {noaaNwrGeoJSON && (
                    <Source id="noaa-nwr" type="geojson" data={noaaNwrGeoJSON as any} cluster={true} clusterRadius={40} clusterMaxZoom={8}>
                        <Layer
                            id="noaa-nwr-clusters"
                            type="circle"
                            filter={['has', 'point_count']}
                            paint={{
                                'circle-color': '#f97316',
                                'circle-radius': ['step', ['get', 'point_count'], 10, 10, 14, 50, 18],
                                'circle-opacity': 0.8,
                                'circle-stroke-width': 2,
                                'circle-stroke-color': '#7c2d12'
                            }}
                        />
                        <Layer
                            id="noaa-nwr-cluster-count"
                            type="symbol"
                            filter={['has', 'point_count']}
                            layout={{ 'text-field': '{point_count_abbreviated}', 'text-size': 9, 'text-allow-overlap': true }}
                            paint={{ 'text-color': '#fff', 'text-halo-color': '#000', 'text-halo-width': 1 }}
                        />
                        <Layer
                            id="noaa-nwr-layer"
                            type="circle"
                            filter={['!', ['has', 'point_count']]}
                            paint={{
                                'circle-color': [
                                    'match', ['get', 'status'],
                                    'On Air', '#f97316',
                                    'Off Air', '#6b7280',
                                    '#f97316'
                                ],
                                'circle-radius': ['interpolate', ['linear'], ['zoom'], 2, 3, 6, 5, 10, 8],
                                'circle-opacity': 0.85,
                                'circle-stroke-width': 1.5,
                                'circle-stroke-color': '#000'
                            }}
                        />
                        <Layer
                            id="noaa-nwr-label"
                            type="symbol"
                            filter={['!', ['has', 'point_count']]}
                            minzoom={7}
                            layout={{
                                'text-field': ['concat', ['get', 'callsign'], ' ', ['get', 'freq']],
                                'text-size': 8, 'text-offset': [0, 1.4],
                                'text-allow-overlap': false,
                                'text-max-width': 10
                            }}
                            paint={{ 'text-color': '#fdba74', 'text-halo-color': '#000', 'text-halo-width': 1 }}
                        />
                    </Source>
                )}

                {/* KiwiSDR Receiver Nodes — teal radio receivers */}
                {kiwisdrGeoJSON && (
                    <Source id="kiwisdr" type="geojson" data={kiwisdrGeoJSON as any} cluster={true} clusterRadius={40} clusterMaxZoom={8}>
                        <Layer
                            id="kiwisdr-clusters"
                            type="circle"
                            filter={['has', 'point_count']}
                            paint={{
                                'circle-color': '#14b8a6',
                                'circle-radius': ['step', ['get', 'point_count'], 10, 10, 14, 50, 18],
                                'circle-opacity': 0.8,
                                'circle-stroke-width': 2,
                                'circle-stroke-color': '#134e4a'
                            }}
                        />
                        <Layer
                            id="kiwisdr-cluster-count"
                            type="symbol"
                            filter={['has', 'point_count']}
                            layout={{ 'text-field': '{point_count_abbreviated}', 'text-size': 9, 'text-allow-overlap': true }}
                            paint={{ 'text-color': '#fff', 'text-halo-color': '#000', 'text-halo-width': 1 }}
                        />
                        <Layer
                            id="kiwisdr-layer"
                            type="circle"
                            filter={['!', ['has', 'point_count']]}
                            paint={{
                                'circle-color': '#14b8a6',
                                'circle-radius': ['interpolate', ['linear'], ['zoom'], 2, 3, 6, 5, 10, 8],
                                'circle-opacity': 0.85,
                                'circle-stroke-width': 1.5,
                                'circle-stroke-color': '#000'
                            }}
                        />
                        <Layer
                            id="kiwisdr-label"
                            type="symbol"
                            filter={['!', ['has', 'point_count']]}
                            minzoom={6}
                            layout={{
                                'text-field': ['get', 'name'],
                                'text-size': 8, 'text-offset': [0, 1.4],
                                'text-allow-overlap': false,
                                'text-max-width': 10
                            }}
                            paint={{ 'text-color': '#5eead4', 'text-halo-color': '#000', 'text-halo-width': 1 }}
                        />
                    </Source>
                )}

                {/* OSINT: Kismet WiFi/BT Devices — cyan clustered circles */}
                {kismetGeoJSON && (
                    <Source id="kismet" type="geojson" data={kismetGeoJSON as any} cluster={true} clusterRadius={40} clusterMaxZoom={10}>
                        <Layer
                            id="kismet-clusters"
                            type="circle"
                            filter={['has', 'point_count']}
                            paint={{
                                'circle-color': '#22d3ee',
                                'circle-radius': ['step', ['get', 'point_count'], 12, 10, 16, 50, 22],
                                'circle-opacity': 0.8,
                                'circle-stroke-width': 2,
                                'circle-stroke-color': '#0e7490'
                            }}
                        />
                        <Layer
                            id="kismet-cluster-count"
                            type="symbol"
                            filter={['has', 'point_count']}
                            layout={{ 'text-field': '{point_count_abbreviated}', 'text-size': 10, 'text-allow-overlap': true }}
                            paint={{ 'text-color': '#fff', 'text-halo-color': '#000', 'text-halo-width': 1 }}
                        />
                        <Layer
                            id="kismet-layer"
                            type="circle"
                            filter={['!', ['has', 'point_count']]}
                            paint={{
                                'circle-color': '#22d3ee',
                                'circle-radius': ['interpolate', ['linear'], ['zoom'], 2, 3, 8, 5, 14, 8],
                                'circle-opacity': 0.85,
                                'circle-stroke-width': 1.5,
                                'circle-stroke-color': '#000'
                            }}
                        />
                        <Layer
                            id="kismet-label"
                            type="symbol"
                            filter={['!', ['has', 'point_count']]}
                            minzoom={10}
                            layout={{
                                'text-field': ['coalesce', ['get', 'ssid'], ['get', 'mac']],
                                'text-size': 8, 'text-offset': [0, 1.4],
                                'text-allow-overlap': false,
                                'text-max-width': 10
                            }}
                            paint={{ 'text-color': '#67e8f9', 'text-halo-color': '#000', 'text-halo-width': 1 }}
                        />
                    </Source>
                )}

                {/* OSINT: Snort IDS Alerts — red pulsing circles */}
                {snortGeoJSON && (
                    <Source id="snort" type="geojson" data={snortGeoJSON as any}>
                        <Layer
                            id="snort-layer"
                            type="circle"
                            paint={{
                                'circle-color': '#ef4444',
                                'circle-radius': ['interpolate', ['linear'], ['zoom'], 2, 4, 8, 7, 14, 10],
                                'circle-opacity': 0.8,
                                'circle-stroke-width': 2,
                                'circle-stroke-color': '#991b1b'
                            }}
                        />
                        <Layer
                            id="snort-label"
                            type="symbol"
                            minzoom={6}
                            layout={{
                                'text-field': ['get', 'signature_msg'],
                                'text-size': 8, 'text-offset': [0, 1.5],
                                'text-allow-overlap': false,
                                'text-max-width': 12
                            }}
                            paint={{ 'text-color': '#fca5a5', 'text-halo-color': '#000', 'text-halo-width': 1 }}
                        />
                    </Source>
                )}

                {/* OSINT: Nmap Network Hosts — green circles */}
                {nmapGeoJSON && (
                    <Source id="nmap" type="geojson" data={nmapGeoJSON as any} cluster={true} clusterRadius={30} clusterMaxZoom={12}>
                        <Layer
                            id="nmap-clusters"
                            type="circle"
                            filter={['has', 'point_count']}
                            paint={{
                                'circle-color': '#4ade80',
                                'circle-radius': ['step', ['get', 'point_count'], 10, 5, 14, 20, 18],
                                'circle-opacity': 0.75,
                                'circle-stroke-width': 2,
                                'circle-stroke-color': '#166534'
                            }}
                        />
                        <Layer
                            id="nmap-cluster-count"
                            type="symbol"
                            filter={['has', 'point_count']}
                            layout={{ 'text-field': '{point_count_abbreviated}', 'text-size': 9, 'text-allow-overlap': true }}
                            paint={{ 'text-color': '#fff', 'text-halo-color': '#000', 'text-halo-width': 1 }}
                        />
                        <Layer
                            id="nmap-layer"
                            type="circle"
                            filter={['!', ['has', 'point_count']]}
                            paint={{
                                'circle-color': '#4ade80',
                                'circle-radius': ['interpolate', ['linear'], ['zoom'], 2, 3, 8, 5, 14, 7],
                                'circle-opacity': 0.8,
                                'circle-stroke-width': 1.5,
                                'circle-stroke-color': '#000'
                            }}
                        />
                        <Layer
                            id="nmap-label"
                            type="symbol"
                            filter={['!', ['has', 'point_count']]}
                            minzoom={8}
                            layout={{
                                'text-field': ['coalesce', ['get', 'hostname'], ['get', 'ip']],
                                'text-size': 8, 'text-offset': [0, 1.4],
                                'text-allow-overlap': false,
                                'text-max-width': 10
                            }}
                            paint={{ 'text-color': '#86efac', 'text-halo-color': '#000', 'text-halo-width': 1 }}
                        />
                    </Source>
                )}

                {/* OSINT: Nuclei Vulnerabilities — orange circles, severity-colored */}
                {nucleiGeoJSON && (
                    <Source id="nuclei" type="geojson" data={nucleiGeoJSON as any}>
                        <Layer
                            id="nuclei-layer"
                            type="circle"
                            paint={{
                                'circle-color': [
                                    'match', ['get', 'vuln_severity'],
                                    'critical', '#ef4444',
                                    'high', '#f97316',
                                    'medium', '#eab308',
                                    'low', '#22d3ee',
                                    '#9ca3af'  // info / default
                                ],
                                'circle-radius': [
                                    'match', ['get', 'vuln_severity'],
                                    'critical', 10,
                                    'high', 8,
                                    'medium', 6,
                                    'low', 5,
                                    4  // info
                                ],
                                'circle-opacity': 0.85,
                                'circle-stroke-width': 2,
                                'circle-stroke-color': '#000'
                            }}
                        />
                        <Layer
                            id="nuclei-label"
                            type="symbol"
                            minzoom={6}
                            layout={{
                                'text-field': ['concat', ['get', 'vuln_severity'], ' — ', ['get', 'name']],
                                'text-size': 8, 'text-offset': [0, 1.5],
                                'text-allow-overlap': false,
                                'text-max-width': 14
                            }}
                            paint={{ 'text-color': '#fdba74', 'text-halo-color': '#000', 'text-halo-width': 1 }}
                        />
                    </Source>
                )}

                {/* CCTV Cameras — clustered green dots */}
                {cctvGeoJSON && (
                    <Source id="cctv" type="geojson" data={cctvGeoJSON as any} cluster={true} clusterRadius={50} clusterMaxZoom={14}>
                        {/* Cluster circles — green, sized by count */}
                        <Layer
                            id="cctv-clusters"
                            type="circle"
                            filter={['has', 'point_count']}
                            paint={{
                                'circle-color': '#22c55e',
                                'circle-radius': [
                                    'step', ['get', 'point_count'],
                                    14, 10,
                                    18, 50,
                                    24, 200,
                                    30
                                ],
                                'circle-opacity': 0.8,
                                'circle-stroke-width': 2,
                                'circle-stroke-color': '#16a34a'
                            }}
                        />
                        {/* Cluster count labels */}
                        <Layer
                            id="cctv-cluster-count"
                            type="symbol"
                            filter={['has', 'point_count']}
                            layout={{
                                'text-field': '{point_count_abbreviated}',
                                'text-size': 12,
                                'text-allow-overlap': true
                            }}
                            paint={{
                                'text-color': '#ffffff',
                                'text-halo-color': '#000000',
                                'text-halo-width': 1
                            }}
                        />
                        {/* Individual camera dots */}
                        <Layer
                            id="cctv-layer"
                            type="circle"
                            filter={['!', ['has', 'point_count']]}
                            paint={{
                                'circle-color': '#22c55e',
                                'circle-radius': [
                                    'interpolate', ['linear'], ['zoom'],
                                    2, 2,
                                    8, 4,
                                    14, 6
                                ],
                                'circle-opacity': 0.9,
                                'circle-stroke-width': 1,
                                'circle-stroke-color': '#16a34a'
                            }}
                        />
                    </Source>
                )}

                {/* Satellite positions — mission-type icons */}
                {satellitesGeoJSON && (
                    <Source id="satellites" type="geojson" data={satellitesGeoJSON as any}>
                        <Layer
                            id="satellites-layer"
                            type="symbol"
                            layout={{
                                'icon-image': ['get', 'iconId'],
                                'icon-size': [
                                    'interpolate', ['linear'], ['zoom'],
                                    0, 0.4,
                                    3, 0.5,
                                    6, 0.7,
                                    10, 1.0
                                ],
                                'icon-allow-overlap': true,
                            }}
                        />
                    </Source>
                )}

                {/* Satellite click popup */}
                {selectedEntity?.type === 'satellite' && (() => {
                    const sat = data?.satellites?.find((s: any) => s.id === selectedEntity.id);
                    if (!sat) return null;
                    const missionLabels: Record<string, string> = {
                        military_recon: '🔴 MILITARY RECON', military_sar: '🔴 MILITARY SAR',
                        sar: '🔷 SAR IMAGING', sigint: '🟠 SIGINT / ELINT',
                        navigation: '🔵 NAVIGATION', early_warning: '🟣 EARLY WARNING',
                        commercial_imaging: '🟢 COMMERCIAL IMAGING', space_station: '🏠 SPACE STATION',
                        communication: '📡 COMMUNICATION'
                    };
                    return (
                        <Popup
                            longitude={sat.lng} latitude={sat.lat}
                            closeButton={false} closeOnClick={false}
                            onClose={() => onEntityClick?.(null)}
                            anchor="bottom" offset={12}
                        >
                            <div style={{
                                background: 'rgba(10,14,26,0.95)', border: '1px solid rgba(0,200,255,0.3)',
                                borderRadius: 6, padding: '10px 14px', color: '#e0e6f0',
                                fontFamily: 'monospace', fontSize: 11, minWidth: 220, maxWidth: 320
                            }}>
                                <div style={{ color: '#00c8ff', fontWeight: 700, fontSize: 13, marginBottom: 6, letterSpacing: 1 }}>
                                    🛰️ {sat.name}
                                </div>
                                <div style={{ color: '#8899aa', marginBottom: 4 }}>
                                    NORAD ID: <span style={{ color: '#fff' }}>{sat.id}</span>
                                </div>
                                {sat.sat_type && (
                                    <div style={{ marginBottom: 4 }}>
                                        Type: <span style={{ color: '#ffcc00' }}>{sat.sat_type}</span>
                                    </div>
                                )}
                                {sat.country && (
                                    <div style={{ marginBottom: 4 }}>
                                        Country: <span style={{ color: '#fff' }}>{sat.country}</span>
                                    </div>
                                )}
                                {sat.mission && (
                                    <div style={{ marginBottom: 4, fontWeight: 600 }}>
                                        {missionLabels[sat.mission] || `⚪ ${sat.mission.toUpperCase()}`}
                                    </div>
                                )}
                                <div style={{ marginBottom: 4 }}>
                                    Altitude: <span style={{ color: '#44ff88' }}>{sat.alt_km?.toLocaleString()} km</span>
                                </div>
                                {sat.wiki && (
                                    <div className="mt-2 border-t border-gray-700/50 pt-2">
                                        <WikiImage wikiUrl={sat.wiki} label={sat.sat_type || sat.name} maxH="max-h-28" accent="hover:border-cyan-500/50" />
                                    </div>
                                )}
                            </div>
                        </Popup>
                    );
                })()}

                {/* UAV click popup */}
                {selectedEntity?.type === 'uav' && (() => {
                    const uav = data?.uavs?.find((u: any) => u.id === selectedEntity.id);
                    if (!uav) return null;
                    return (
                        <Popup
                            longitude={uav.lng} latitude={uav.lat}
                            closeButton={false} closeOnClick={false}
                            onClose={() => onEntityClick?.(null)}
                            anchor="bottom" offset={12}
                        >
                            <div style={{
                                background: 'rgba(10,14,26,0.95)', border: '1px solid rgba(255,68,68,0.4)',
                                borderRadius: 6, padding: '10px 14px', color: '#e0e6f0',
                                fontFamily: 'monospace', fontSize: 11, minWidth: 220, maxWidth: 320
                            }}>
                                <div style={{ color: '#ff4444', fontWeight: 700, fontSize: 13, marginBottom: 6, letterSpacing: 1 }}>
                                    ✈️ {uav.callsign}
                                </div>
                                {uav.uav_type && (
                                    <div style={{ marginBottom: 4 }}>
                                        Type: <span style={{ color: '#ffcc00' }}>{uav.uav_type}</span>
                                    </div>
                                )}
                                {uav.country && (
                                    <div style={{ marginBottom: 4 }}>
                                        Country: <span style={{ color: '#fff' }}>{uav.country}</span>
                                    </div>
                                )}
                                <div style={{ marginBottom: 4 }}>
                                    Altitude: <span style={{ color: '#44ff88' }}>{uav.alt?.toLocaleString()} m</span>
                                </div>
                                {uav.speed_knots > 0 && (
                                    <div style={{ marginBottom: 4 }}>
                                        Speed: <span style={{ color: '#00e5ff' }}>{uav.speed_knots} kn</span>
                                    </div>
                                )}
                                {uav.range_km > 0 && (
                                    <div style={{ marginBottom: 4 }}>
                                        Operational Range: <span style={{ color: '#ff8844' }}>{uav.range_km?.toLocaleString()} km</span>
                                    </div>
                                )}
                                {uav.wiki && (
                                    <div className="mt-2 border-t border-gray-700/50 pt-2">
                                        <WikiImage wikiUrl={uav.wiki} label={uav.callsign} maxH="max-h-28" accent="hover:border-red-500/50" />
                                    </div>
                                )}
                            </div>
                        </Popup>
                    );
                })()}
                {
                    selectedEntity?.type === 'gdelt' && data?.gdelt?.[selectedEntity.id as number] && (
                        <Popup
                            longitude={data.gdelt[selectedEntity.id as number].geometry.coordinates[0]}
                            latitude={data.gdelt[selectedEntity.id as number].geometry.coordinates[1]}
                            closeButton={false}
                            closeOnClick={false}
                            onClose={() => onEntityClick?.(null)}
                            anchor="bottom"
                            offset={15}
                        >
                            <div className="bg-black/90 backdrop-blur-md border border-orange-800 rounded-lg flex flex-col z-[100] font-mono shadow-[0_4px_30px_rgba(255,140,0,0.4)] pointer-events-auto overflow-hidden w-[300px]">
                                <div className="p-2 border-b border-orange-500/30 bg-orange-950/40 flex justify-between items-center">
                                    <h2 className="text-[10px] tracking-widest font-bold text-orange-400 flex items-center gap-1">
                                        <AlertTriangle size={12} className="text-orange-400" /> NEWS ON THE GROUND
                                    </h2>
                                    <button onClick={() => onEntityClick?.(null)} className="text-gray-400 hover:text-white">✕</button>
                                </div>
                                <div className="p-3 flex flex-col gap-2">
                                    <div className="flex justify-between items-center border-b border-gray-800 pb-1">
                                        <span className="text-gray-500 text-[9px]">LOCATION</span>
                                        <span className="text-white text-[10px] font-bold text-right ml-2 break-words max-w-[150px]">{data.gdelt[selectedEntity.id as number].properties?.name || 'UNKNOWN REGION'}</span>
                                    </div>
                                    <div className="flex flex-col gap-1 mt-1">
                                        <span className="text-gray-500 text-[9px]">LATEST REPORTS: ({data.gdelt[selectedEntity.id as number].properties?.count || 1})</span>
                                        <div className="flex flex-col gap-2 max-h-[200px] overflow-y-auto styled-scrollbar mt-1">
                                            {(() => {
                                                const urls: string[] = data.gdelt[selectedEntity.id as number].properties?._urls_list || [];
                                                const headlines: string[] = data.gdelt[selectedEntity.id as number].properties?._headlines_list || [];
                                                if (urls.length === 0) return <span className="text-gray-500 text-[9px]">No articles available.</span>;
                                                return urls.map((url: string, idx: number) => (
                                                    <a
                                                        key={idx}
                                                        href={url}
                                                        target="_blank"
                                                        rel="noopener noreferrer"
                                                        onClick={(e) => e.stopPropagation()}
                                                        className="text-orange-400 text-[9px] underline hover:text-orange-300 block py-1 border-b border-gray-800/50 last:border-0 cursor-pointer"
                                                        style={{ pointerEvents: 'all' }}
                                                    >
                                                        {headlines[idx] || url}
                                                    </a>
                                                ));
                                            })()}
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </Popup>
                    )
                }

                {
                    selectedEntity?.type === 'liveuamap' && data?.liveuamap?.find((l: any) => String(l.id) === String(selectedEntity.id)) && (() => {
                        const item = data.liveuamap.find((l: any) => String(l.id) === String(selectedEntity.id));
                        return (
                            <Popup
                                longitude={item.lng}
                                latitude={item.lat}
                                closeButton={false}
                                closeOnClick={false}
                                onClose={() => onEntityClick?.(null)}
                                anchor="bottom"
                                offset={15}
                            >
                                <div className="bg-black/90 backdrop-blur-md border border-yellow-800 rounded-lg flex flex-col z-[100] font-mono shadow-[0_4px_30px_rgba(255,255,0,0.3)] pointer-events-auto overflow-hidden w-[280px]">
                                    <div className="p-2 border-b border-yellow-500/30 bg-yellow-950/40 flex justify-between items-center">
                                        <h2 className="text-[10px] tracking-widest font-bold text-yellow-400 flex items-center gap-1">
                                            <AlertTriangle size={12} className="text-yellow-400" /> REGIONAL TACTICAL EVENT
                                        </h2>
                                        <button onClick={() => onEntityClick?.(null)} className="text-gray-400 hover:text-white">✕</button>
                                    </div>
                                    <div className="p-3 flex flex-col gap-2">
                                        <div className="flex flex-col gap-1 border-b border-gray-800 pb-1">
                                            <span className="text-yellow-400 text-[10px] font-bold leading-tight">{item.title}</span>
                                        </div>
                                        <div className="flex justify-between items-center border-b border-gray-800 pb-1 mt-1">
                                            <span className="text-gray-500 text-[9px]">TIME</span>
                                            <span className="text-white text-[9px] font-bold">{item.timestamp || 'UNKNOWN'}</span>
                                        </div>
                                        {item.link && (
                                            <div className="flex justify-between items-center mt-1">
                                                <a href={item.link} target="_blank" rel="noreferrer" className="text-yellow-400 hover:text-yellow-300 text-[9px] font-bold underline">
                                                    View Source Report
                                                </a>
                                            </div>
                                        )}
                                    </div>
                                </div>
                            </Popup>
                        );
                    })()
                }

                {
                    selectedEntity?.type === 'news' && data?.news?.[selectedEntity.id as number] && (() => {
                        const item = data.news[selectedEntity.id as number];
                        let threatColor = "text-yellow-400";
                        let borderColor = "border-yellow-800";
                        let bgHeaderColor = "bg-yellow-950/40";
                        let shadowColor = "rgba(255,255,0,0.3)";
                        if (item.risk_score >= 8) {
                            threatColor = "text-red-400";
                            borderColor = "border-red-800";
                            bgHeaderColor = "bg-red-950/40";
                            shadowColor = "rgba(255,0,0,0.3)";
                        } else if (item.risk_score <= 4) {
                            threatColor = "text-green-400";
                            borderColor = "border-green-800";
                            bgHeaderColor = "bg-green-950/40";
                            shadowColor = "rgba(0,255,0,0.3)";
                        }

                        if (!item || !item.coords) return null;

                        return (
                            <Popup
                                longitude={item.coords[1]}
                                latitude={item.coords[0]}
                                closeButton={false}
                                closeOnClick={false}
                                onClose={() => onEntityClick?.(null)}
                                anchor="bottom"
                                offset={25}
                            >
                                <div className={`bg-black/90 backdrop-blur-md border ${borderColor} rounded-lg flex flex-col z-[100] font-mono shadow-[0_4px_30px_${shadowColor}] pointer-events-auto overflow-hidden w-[280px]`}>
                                    <div className={`p-2 border-b ${borderColor}/50 ${bgHeaderColor} flex justify-between items-center`}>
                                        <h2 className={`text-[10px] tracking-widest font-bold ${threatColor} flex items-center gap-1`}>
                                            <AlertTriangle size={12} className={threatColor} /> THREAT INTERCEPT
                                        </h2>
                                        <div className="flex items-center gap-2">
                                            <span className={`text-[10px] ${threatColor} font-mono font-bold animate-pulse`}>LVL: {item.risk_score}/10</span>
                                            <button onClick={() => onEntityClick?.(null)} className="text-gray-400 hover:text-white">✕</button>
                                        </div>
                                    </div>
                                    <div className="p-3 flex flex-col gap-2">
                                        <div className="flex flex-col gap-1 border-b border-gray-800 pb-1">
                                            <span className={`text-[10px] font-bold leading-tight ${threatColor}`}>{item.title}</span>
                                        </div>
                                        <div className="flex justify-between items-center border-b border-gray-800 pb-1 mt-1">
                                            <span className="text-gray-500 text-[9px]">SOURCE</span>
                                            <span className="text-white text-[9px] font-bold text-right ml-2">{item.source || 'UNKNOWN'}</span>
                                        </div>
                                        {item.machine_assessment && (
                                            <div className="mt-1 p-2 bg-black/60 border border-cyan-800/50 rounded-sm text-[8px] text-cyan-400 font-mono leading-tight relative overflow-hidden shadow-[inset_0_0_10px_rgba(0,255,255,0.05)]">
                                                <div className="absolute top-0 left-0 w-[2px] h-full bg-cyan-500 animate-pulse"></div>
                                                <span className="font-bold text-white">&gt;_ SYS.ANALYSIS: </span>
                                                <span className="text-cyan-300 opacity-90">{item.machine_assessment}</span>
                                            </div>
                                        )}
                                        {item.link && (
                                            <div className="flex justify-between items-center mt-1">
                                                <a href={item.link} target="_blank" rel="noreferrer" className={`${threatColor} hover:text-red-300 text-[9px] font-bold underline`}>
                                                    View Details
                                                </a>
                                            </div>
                                        )}
                                    </div>
                                </div>
                            </Popup>
                        );
                    })()
                }

                {/* ENTITY POPUP CARD — floating info card at click location */}
                {entityPopup && (
                    <Popup
                        latitude={entityPopup.lat}
                        longitude={entityPopup.lng}
                        closeOnClick={false}
                        onClose={() => setEntityPopup(null)}
                        anchor="bottom"
                        className="entity-popup-card"
                        maxWidth="280px"
                        closeButton={false}
                        offset={14}
                    >
                        <EntityPopupCard type={entityPopup.type} props={entityPopup.props} />
                    </Popup>
                )}

                {/* REGION DOSSIER — location pin on map (full intel shown in right panel) */}
                {selectedEntity?.type === 'region_dossier' && selectedEntity.extra && (
                    <Marker
                        longitude={selectedEntity.extra.lng}
                        latitude={selectedEntity.extra.lat}
                        anchor="bottom"
                        style={{ zIndex: 10 }}
                    >
                        <div className="flex flex-col items-center pointer-events-none">
                            {/* Pulsing ring */}
                            <div className="w-8 h-8 rounded-full border-2 border-emerald-500 animate-ping absolute opacity-30" />
                            {/* Pin dot */}
                            <div className="w-4 h-4 rounded-full bg-emerald-500 border-2 border-emerald-300 shadow-[0_0_15px_rgba(16,185,129,0.6)]" />
                            {/* Label */}
                            <div className="mt-2 bg-black/80 border border-emerald-800 rounded px-2 py-1 text-[9px] font-mono text-emerald-400 tracking-widest whitespace-nowrap shadow-[0_0_10px_rgba(16,185,129,0.3)]">
                                {regionDossierLoading ? 'COMPILING...' : '▶ INTEL TARGET'}
                            </div>
                        </div>
                    </Marker>
                )}

                {/* PINNED LOCATIONS — from F.R.I.D.A.Y. OSINT/locate results */}
                {pinnedLocations && pinnedLocations.length > 0 && pinnedLocations.map((pin: any, idx: number) => (
                    <Marker key={pin.id || `pin-${idx}`} longitude={pin.lng} latitude={pin.lat} anchor="bottom" style={{ zIndex: 9 }}>
                        <div className="flex flex-col items-center cursor-pointer group relative">
                            {/* Pulse ring */}
                            <div className="w-6 h-6 rounded-full border-2 border-red-500 animate-ping absolute opacity-25" />
                            {/* Pin icon */}
                            <svg width="20" height="28" viewBox="0 0 20 28" className="drop-shadow-[0_0_8px_rgba(239,68,68,0.7)]" onClick={() => onEntityClick?.({ type: 'pinned_location', id: pin.id, extra: pin })}>
                                <path d="M10 0C4.5 0 0 4.5 0 10c0 7.5 10 18 10 18s10-10.5 10-18C20 4.5 15.5 0 10 0z" fill="#ef4444" stroke="#fca5a5" strokeWidth="1"/>
                                <circle cx="10" cy="10" r="4" fill="#fca5a5"/>
                            </svg>
                            {/* Remove button — appears on hover */}
                            <div
                                className="absolute -top-2 -right-2 w-4 h-4 rounded-full bg-black border border-red-500 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity hover:bg-red-900 z-10"
                                title="Remove pin"
                                onClick={(e) => { e.stopPropagation(); onRemovePin?.(pin.id); }}
                            >
                                <span className="text-red-400 text-[8px] font-bold leading-none">✕</span>
                            </div>
                            {/* Label */}
                            <div className="mt-1 bg-black/85 border border-red-800/60 rounded px-1.5 py-0.5 text-[8px] font-mono text-red-400 tracking-wider whitespace-nowrap max-w-[180px] truncate shadow-[0_0_10px_rgba(239,68,68,0.3)]">
                                {pin.label || `Pin ${idx + 1}`}
                            </div>
                        </div>
                    </Marker>
                ))}

                {/* Clear pins button (top-right of map when pins exist) */}
                {pinnedLocations && pinnedLocations.length > 0 && (
                    <div className="absolute top-3 right-3 z-[300]">
                        <button
                            onClick={onClearPins}
                            className="bg-black/80 border border-red-800/50 rounded px-2 py-1 text-[9px] font-mono text-red-400 tracking-widest hover:bg-red-900/30 hover:border-red-600 transition-all cursor-pointer"
                        >
                            CLEAR {pinnedLocations.length} PIN{pinnedLocations.length > 1 ? 'S' : ''}
                        </button>
                    </div>
                )}

                {/* MEASUREMENT LINES */}
                {measurePoints && measurePoints.length >= 2 && (
                    <Source id="measure-lines" type="geojson" data={{
                        type: 'FeatureCollection',
                        features: [{
                            type: 'Feature',
                            properties: {},
                            geometry: {
                                type: 'LineString',
                                coordinates: measurePoints.map((p: any) => [p.lng, p.lat])
                            }
                        }]
                    } as any}>
                        <Layer
                            id="measure-lines-layer"
                            type="line"
                            paint={{
                                'line-color': '#00ffff',
                                'line-width': 2,
                                'line-dasharray': [4, 3],
                                'line-opacity': 0.8,
                            }}
                        />
                    </Source>
                )}

                {/* OSINT Search Result Locations */}
                {osintLocationsGeoJSON && (
                    <Source id="osint-locations" type="geojson" data={osintLocationsGeoJSON}>
                        {/* Outer glow */}
                        <Layer
                            id="osint-locations-glow"
                            type="circle"
                            paint={{
                                'circle-radius': 14,
                                'circle-color': '#f59e0b',
                                'circle-opacity': 0.15,
                                'circle-blur': 1,
                            }}
                        />
                        {/* Inner circle */}
                        <Layer
                            id="osint-locations-circle"
                            type="circle"
                            paint={{
                                'circle-radius': 6,
                                'circle-color': '#f59e0b',
                                'circle-stroke-width': 2,
                                'circle-stroke-color': '#ffffff',
                            }}
                        />
                        {/* Labels */}
                        <Layer
                            id="osint-locations-label"
                            type="symbol"
                            layout={{
                                'text-field': ['get', 'label'],
                                'text-size': 10,
                                'text-offset': [0, 1.5],
                                'text-anchor': 'top',
                                'text-max-width': 15,
                            }}
                            paint={{
                                'text-color': '#fbbf24',
                                'text-halo-color': '#000000',
                                'text-halo-width': 1.5,
                            }}
                        />
                    </Source>
                )}

                {/* Connecting lines between OSINT locations */}
                {osintLinesGeoJSON && (
                    <Source id="osint-lines" type="geojson" data={osintLinesGeoJSON}>
                        <Layer
                            id="osint-lines-layer"
                            type="line"
                            paint={{
                                'line-color': '#f59e0b',
                                'line-width': 1.5,
                                'line-dasharray': [4, 4],
                                'line-opacity': 0.6,
                            }}
                        />
                    </Source>
                )}

                {/* Regional Focus Center Marker */}
                {regionalFocus?.active && (
                    <Marker longitude={regionalFocus.lng} latitude={regionalFocus.lat} anchor="center">
                        <div className="flex flex-col items-center pointer-events-none">
                            <div className="w-10 h-10 rounded-full border-2 border-amber-400/50 animate-ping absolute opacity-20" />
                            <div className="w-3 h-3 rounded-full bg-amber-500 border border-amber-300 shadow-[0_0_20px_rgba(245,158,11,0.6)]" />
                            <div className="mt-1 px-2 py-0.5 bg-black/80 border border-amber-500/40 rounded text-[8px] font-mono text-amber-400 tracking-wider whitespace-nowrap">
                                REGIONAL FOCUS
                            </div>
                        </div>
                    </Marker>
                )}

                {/* MEASUREMENT WAYPOINTS */}
                {measurePoints && measurePoints.map((pt: any, idx: number) => (
                    <Marker key={`measure-${idx}`} longitude={pt.lng} latitude={pt.lat} anchor="center">
                        <div className="flex flex-col items-center pointer-events-none">
                            <div className="w-6 h-6 rounded-full border-2 border-cyan-400 animate-ping absolute opacity-20" />
                            <div className="w-4 h-4 rounded-full bg-cyan-500 border-2 border-cyan-300 shadow-[0_0_12px_rgba(0,255,255,0.6)] flex items-center justify-center">
                                <span className="text-[7px] font-mono font-bold text-black">{idx + 1}</span>
                            </div>
                        </div>
                    </Marker>
                ))}

            </Map>
        </div>
    );
}

import dynamic from "next/dynamic";

export default dynamic(() => Promise.resolve(MaplibreViewer), {
    ssr: false
});
