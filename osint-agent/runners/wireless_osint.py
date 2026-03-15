"""Wireless OSINT runner — Wigle WiFi/Bluetooth discovery, wpa-sec credential
leak detection, and device type classification.

Sources:
  - Wigle.net: Global wardriving database (WiFi + Bluetooth)
  - wpa-sec.stanev.org: Leaked WiFi credentials (k-Anonymity)
  - Device classification heuristics
"""

import json
import logging
import os
from hashlib import sha1
from typing import Any

import httpx

from runners.base import BaseToolRunner

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Device classification heuristics
# ---------------------------------------------------------------------------
_DEVICE_RULES = [
    ("car", ["CAR", "FORD", "TOYOTA", "BMW", "TESLA", "SYNC", "MAZDA", "HONDA",
             "UCONNECT", "HYUNDAI", "LEXUS", "NISSAN", "CHEVY", "AUDI", "BENZ",
             "VOLKSWAGEN", "KIA", "SUBARU", "JEEP", "DODGE", "CHRYSLER"]),
    ("tv", ["TV", "BRAVIA", "VIZIO", "SAMSUNG TV", "LG TV", "ROKU", "FIRE TV",
            "SMARTVIEW", "KDL-", "CHROMECAST", "APPLE TV"]),
    ("headphone", ["HEADPHONE", "EARBUD", "BOSE", "AIRPOD", "JBL", "SENNHEISER",
                   "BEATS", "SONY WH-", "SONY WF-", "BUDS", "EARPHONE"]),
    ("dashcam", ["DASHCAM", "DASH CAM", "DVR", "70MAI", "VIOFO", "GARMIN DASH",
                 "NEXTBASE", "BLACKVUE"]),
    ("camera", ["CAM", "SURVEILLANCE", "SECURITY", "NEST", "RING", "ARLO",
                "HIKVISION", "DAHUA", "REOLINK", "WYZE", "BLINK", "EUFY"]),
    ("iot", ["WATCH", "FITBIT", "GARMIN", "WHOOP", "THERMOSTAT", "NEST",
             "ECHO", "ALEXA", "GOOGLE HOME", "SMART", "IOT"]),
    ("printer", ["PRINTER", "EPSON", "CANON", "HP-", "BROTHER"]),
    ("drone", ["DRONE", "DJI", "MAVIC", "PHANTOM", "SKYDIO"]),
]


def classify_device(name: str, original_type: str = "router") -> str:
    """Classify a wireless device by its broadcast name."""
    if not name:
        return original_type
    upper = name.upper()
    for device_type, keywords in _DEVICE_RULES:
        if any(k in upper for k in keywords):
            return device_type
    return original_type


# ---------------------------------------------------------------------------
# wpa-sec leaked credential check (k-Anonymity)
# ---------------------------------------------------------------------------
def check_leaked_credentials(devices: list[dict]) -> list[dict]:
    """Check WiFi devices against wpa-sec for leaked credentials.

    Uses k-Anonymity: sends only 4-char hash prefixes, compares suffixes locally.
    No plaintext data or full hashes leave the machine.
    """
    if not devices:
        return devices

    # Build hash map for routers with BSSID+SSID
    clids: set[str] = set()
    for d in devices:
        if d.get("device_type") not in ("router", "Wi-Fi", "wifi") or not d.get("bssid") or not d.get("ssid"):
            continue
        bssid = d["bssid"].replace(":", "").replace("-", "").lower()
        if len(bssid) != 12 or not all(c in "0123456789abcdef" for c in bssid):
            continue
        ssid_hex = d["ssid"].encode("utf-8").hex()
        d["_hash"] = sha1(f"{bssid}{ssid_hex}".encode("ascii")).hexdigest()
        clids.add(d["_hash"][:4])

    if not clids:
        return devices

    # Query wpa-sec k-Anonymity endpoint
    try:
        resp = httpx.post(
            "https://wpa-sec.stanev.org/bmacssid",
            content=json.dumps(list(clids)),
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        if resp.status_code == 200:
            leaked_data = resp.json()
            for d in devices:
                h = d.pop("_hash", None)
                if not h:
                    continue
                suffixes = leaked_data.get(h[:4])
                if suffixes:
                    for s in suffixes:
                        if h.endswith(s):
                            d["leaked"] = True
                            break
    except Exception as e:
        logger.warning(f"wpa-sec k-query failed: {e}")
        # Clean up _hash fields
        for d in devices:
            d.pop("_hash", None)

    return devices


class WirelessOsintRunner(BaseToolRunner):
    tool_name = "wireless_osint"
    cache_ttl = 300  # 5 min cache

    def _get_wigle_auth(self) -> tuple[str, str] | None:
        name = os.environ.get("WIGLE_API_NAME", "")
        token = os.environ.get("WIGLE_API_TOKEN", "")
        if name and token:
            return (name, token)
        return None

    async def search_wifi(self, lat: float, lon: float, radius: float = 0.01, max_results: int = 500) -> dict:
        """Search Wigle for WiFi networks near coordinates with pagination.

        Args:
            lat, lon: Center coordinates
            radius: Search radius in degrees (~0.01 = ~1.1km)
            max_results: Max devices to fetch (paginated in batches of 100)
        """
        cache_key = self._cache_key("wifi", f"{lat:.4f}", f"{lon:.4f}")
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        auth = self._get_wigle_auth()
        if not auth:
            return {"status": "error", "error": "Wigle API credentials not configured (WIGLE_API_NAME + WIGLE_API_TOKEN)", "devices": []}

        devices = []
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                first = 0
                while len(devices) < max_results:
                    resp = await client.get(
                        "https://api.wigle.net/api/v2/network/search",
                        params={
                            "latrange1": lat - radius,
                            "latrange2": lat + radius,
                            "longrange1": lon - radius,
                            "longrange2": lon + radius,
                            "resultsPerPage": 100,
                            "first": first,
                        },
                        auth=auth,
                    )
                    if resp.status_code != 200:
                        logger.warning(f"Wigle WiFi search returned {resp.status_code}")
                        break
                    results = resp.json().get("results", [])
                    if not results:
                        break
                    for net in results:
                        name = net.get("ssid", "")
                        devices.append({
                            "lat": net.get("trilat"),
                            "lon": net.get("trilong"),
                            "ssid": name,
                            "bssid": net.get("netid", ""),
                            "vendor": net.get("vendor", ""),
                            "signal_dbm": net.get("level", 0),
                            "channel": str(net.get("channel", "")),
                            "encryption": net.get("encryption", ""),
                            "last_seen": net.get("lastupdt", ""),
                            "device_type": classify_device(name, "router"),
                        })
                    first += len(results)
                    if len(results) < 100:
                        break  # No more pages
                # Check for leaked credentials
                devices = check_leaked_credentials(devices)
        except Exception as e:
            logger.warning(f"Wigle WiFi search failed: {e}")

        output = {
            "status": "ok",
            "mode": "wifi",
            "total": len(devices),
            "leaked_count": sum(1 for d in devices if d.get("leaked")),
            "devices": devices,
        }
        self._set_cached(cache_key, output)
        return output

    async def search_bluetooth(self, lat: float, lon: float, radius: float = 0.01, max_results: int = 500) -> dict:
        """Search Wigle for Bluetooth devices near coordinates with pagination."""
        cache_key = self._cache_key("bt", f"{lat:.4f}", f"{lon:.4f}")
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        auth = self._get_wigle_auth()
        if not auth:
            return {"status": "error", "error": "Wigle API credentials not configured", "devices": []}

        devices = []
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                first = 0
                while len(devices) < max_results:
                    resp = await client.get(
                        "https://api.wigle.net/api/v2/bluetooth/search",
                        params={
                            "latrange1": lat - radius,
                            "latrange2": lat + radius,
                            "longrange1": lon - radius,
                            "longrange2": lon + radius,
                            "resultsPerPage": 100,
                            "first": first,
                        },
                        auth=auth,
                    )
                    if resp.status_code != 200:
                        logger.warning(f"Wigle BT search returned {resp.status_code}")
                        break
                    results = resp.json().get("results", [])
                    if not results:
                        break
                    for dev in results:
                        name = dev.get("name") or dev.get("netid", "")
                        classified = classify_device(name, "bluetooth")
                        devices.append({
                            "lat": dev.get("trilat"),
                            "lon": dev.get("trilong"),
                            "ssid": name,
                            "bssid": dev.get("netid", ""),
                            "vendor": dev.get("type") or classified.replace("_", " ").title(),
                            "signal_dbm": dev.get("level", 0),
                            "last_seen": dev.get("lastupdt", ""),
                            "device_type": classified,
                        })
                    first += len(results)
                    if len(results) < 100:
                        break
        except Exception as e:
            logger.warning(f"Wigle BT search failed: {e}")

        output = {
            "status": "ok",
            "mode": "bluetooth",
            "total": len(devices),
            "devices": devices,
        }
        self._set_cached(cache_key, output)
        return output

    async def search_nearby(self, lat: float, lon: float, mode: str = "all", radius: float = 0.01) -> dict:
        """Combined search — WiFi + Bluetooth + credential leak check."""
        if mode == "wifi":
            return await self.search_wifi(lat, lon, radius)
        elif mode == "bluetooth":
            return await self.search_bluetooth(lat, lon, radius)

        # mode == "all": run both in parallel
        import asyncio
        wifi_result, bt_result = await asyncio.gather(
            self.search_wifi(lat, lon, radius),
            self.search_bluetooth(lat, lon, radius),
        )

        all_devices = wifi_result.get("devices", []) + bt_result.get("devices", [])
        return {
            "status": "ok",
            "mode": "all",
            "total": len(all_devices),
            "wifi_count": wifi_result.get("total", 0),
            "bluetooth_count": bt_result.get("total", 0),
            "leaked_count": wifi_result.get("leaked_count", 0),
            "devices": all_devices,
        }

    async def search_ssid(self, ssid: str) -> dict:
        """Search Wigle for a specific SSID globally."""
        auth = self._get_wigle_auth()
        if not auth:
            return {"status": "error", "error": "Wigle API credentials not configured", "devices": []}

        devices = []
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    "https://api.wigle.net/api/v2/network/search",
                    params={"ssid": ssid},
                    auth=auth,
                )
                if resp.status_code == 200:
                    for net in resp.json().get("results", []):
                        devices.append({
                            "lat": net.get("trilat"),
                            "lon": net.get("trilong"),
                            "ssid": net.get("ssid", ""),
                            "bssid": net.get("netid", ""),
                            "vendor": net.get("vendor", ""),
                            "signal_dbm": net.get("level", 0),
                            "last_seen": net.get("lastupdt", ""),
                            "device_type": classify_device(net.get("ssid", ""), "router"),
                        })
                    devices = check_leaked_credentials(devices)
        except Exception as e:
            logger.warning(f"Wigle SSID search failed: {e}")

        return {"status": "ok", "query": ssid, "total": len(devices), "devices": devices}

    async def search_bssid(self, bssid: str) -> dict:
        """Search Wigle for a specific BSSID (MAC address)."""
        auth = self._get_wigle_auth()
        if not auth:
            return {"status": "error", "error": "Wigle API credentials not configured", "devices": []}

        devices = []
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    "https://api.wigle.net/api/v2/network/search",
                    params={"netid": bssid},
                    auth=auth,
                )
                if resp.status_code == 200:
                    for net in resp.json().get("results", []):
                        devices.append({
                            "lat": net.get("trilat"),
                            "lon": net.get("trilong"),
                            "ssid": net.get("ssid", ""),
                            "bssid": net.get("netid", ""),
                            "vendor": net.get("vendor", ""),
                            "signal_dbm": net.get("level", 0),
                            "last_seen": net.get("lastupdt", ""),
                            "device_type": classify_device(net.get("ssid", ""), "router"),
                        })
                    devices = check_leaked_credentials(devices)
        except Exception as e:
            logger.warning(f"Wigle BSSID search failed: {e}")

        return {"status": "ok", "query": bssid, "total": len(devices), "devices": devices}
