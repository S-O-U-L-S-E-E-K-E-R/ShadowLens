"""Kismet WiFi/BT device runner — HTTP API with SQLite fallback."""

import hashlib
import json
import logging
import math
import os
import sqlite3
import time

import httpx

from config import KISMET_API_URL, KISMET_API_KEY, KISMET_DB_PATH, HOST_LAT, HOST_LON
from runners.base import BaseToolRunner

logger = logging.getLogger(__name__)


class KismetRunner(BaseToolRunner):
    tool_name = "kismet"
    cache_ttl = 30

    async def get_devices(self) -> list[dict]:
        cache_key = self._cache_key("devices")
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        devices = await self._fetch_api()
        if not devices:
            devices = self._fetch_sqlite()

        self._set_cached(cache_key, devices)
        return devices

    async def _fetch_api(self) -> list[dict]:
        """Query Kismet REST API for active devices."""
        try:
            headers = {}
            if KISMET_API_KEY:
                headers["KISMET"] = KISMET_API_KEY

            async with httpx.AsyncClient(timeout=10) as client:
                # Get last-active devices (last 5 minutes)
                resp = await client.post(
                    f"{KISMET_API_URL}/devices/last-time/-300/devices.json",
                    headers=headers,
                    json={"fields": [
                        "kismet.device.base.macaddr",
                        "kismet.device.base.name",
                        "kismet.device.base.type",
                        "kismet.device.base.signal/kismet.common.signal.last_signal",
                        "kismet.device.base.channel",
                        "kismet.device.base.crypt",
                        "kismet.device.base.manuf",
                        "kismet.device.base.first_time",
                        "kismet.device.base.last_time",
                        "kismet.device.base.packets.total",
                        "kismet.device.base.location/kismet.common.location.last/kismet.common.location.geopoint",
                    ]},
                )
                if resp.status_code != 200:
                    logger.warning(f"Kismet API returned {resp.status_code}")
                    return []

                raw = resp.json()
                devices = []
                for d in raw:
                    loc = d.get("kismet.device.base.location", {})
                    last_loc = loc.get("kismet.common.location.last", {})
                    geopoint = last_loc.get("kismet.common.location.geopoint", [0, 0])

                    has_real_gps = (len(geopoint) > 1 and geopoint[1] != 0 and geopoint[0] != 0)
                    lat = geopoint[1] if has_real_gps else HOST_LAT
                    lon = geopoint[0] if has_real_gps else HOST_LON

                    signal_info = d.get("kismet.device.base.signal", {})
                    mac_addr = d.get("kismet.device.base.macaddr", "")

                    # Spread devices without real GPS in a small radius
                    if not has_real_gps and mac_addr:
                        seed = hashlib.md5(mac_addr.encode()).digest()
                        angle = (seed[0] / 255.0) * 2 * math.pi
                        radius = (seed[1] / 255.0) * 0.002
                        lat += radius * math.cos(angle)
                        lon += radius * math.sin(angle)

                    devices.append({
                        "mac": mac_addr,
                        "ssid": d.get("kismet.device.base.name", ""),
                        "device_type": d.get("kismet.device.base.type", "Wi-Fi"),
                        "signal_dbm": signal_info.get("kismet.common.signal.last_signal", 0) if isinstance(signal_info, dict) else 0,
                        "channel": str(d.get("kismet.device.base.channel", "")),
                        "encryption": d.get("kismet.device.base.crypt", ""),
                        "manufacturer": d.get("kismet.device.base.manuf", ""),
                        "first_seen": d.get("kismet.device.base.first_time", 0),
                        "last_seen": d.get("kismet.device.base.last_time", 0),
                        "packets": d.get("kismet.device.base.packets.total", 0) if isinstance(d.get("kismet.device.base.packets.total"), int) else 0,
                        "lat": lat,
                        "lon": lon,
                    })
                return devices
        except httpx.ConnectError:
            logger.debug("Kismet API not reachable, trying SQLite fallback")
            return []
        except Exception as e:
            logger.warning(f"Kismet API error: {e}")
            return []

    def _fetch_sqlite(self) -> list[dict]:
        """Fallback: read devices from Kismet SQLite database.

        Kismet uses multiple DB formats:
        - Modern: 'devices' table with full JSON blobs
        - Legacy/devicetracker: 'device_names' table with key/name pairs
        - Kismet log files (.kismet) are also SQLite with 'devices' table
        """
        # Try the configured DB first, then look for .kismet log files
        db_paths = [KISMET_DB_PATH]
        kismet_dir = os.path.dirname(KISMET_DB_PATH)
        if os.path.isdir(kismet_dir):
            for f in sorted(os.listdir(kismet_dir), reverse=True):
                if f.endswith(".kismet"):
                    db_paths.append(os.path.join(kismet_dir, f))

        for db_path in db_paths:
            if not os.path.isfile(db_path):
                continue
            conn = None
            try:
                conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
                conn.row_factory = sqlite3.Row
                cur = conn.cursor()

                # Check which tables exist
                cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = {row["name"] for row in cur.fetchall()}

                devices = []

                if "devices" in tables:
                    # Modern Kismet DB with full device JSON
                    cutoff = int(time.time()) - 600
                    try:
                        cur.execute("""
                            SELECT devmac, type, device
                            FROM devices
                            WHERE last_time > ?
                            ORDER BY last_time DESC
                            LIMIT 500
                        """, (cutoff,))
                    except Exception:
                        # Some versions don't have last_time column
                        cur.execute("SELECT devmac, type, device FROM devices LIMIT 500")

                    for row in cur.fetchall():
                        try:
                            dev = json.loads(row["device"]) if row["device"] else {}
                        except (json.JSONDecodeError, TypeError):
                            dev = {}

                        base = dev.get("kismet.device.base", dev)
                        loc = base.get("kismet.device.base.location", {})
                        last_loc = loc.get("kismet.common.location.last", {})
                        geopoint = last_loc.get("kismet.common.location.geopoint", [0, 0])

                        lat = geopoint[1] if len(geopoint) > 1 and geopoint[1] != 0 else HOST_LAT
                        lon = geopoint[0] if len(geopoint) > 0 and geopoint[0] != 0 else HOST_LON

                        devices.append({
                            "mac": row["devmac"] or "",
                            "ssid": base.get("kismet.device.base.name", ""),
                            "device_type": row["type"] or "Wi-Fi",
                            "signal_dbm": 0,
                            "channel": "",
                            "encryption": "",
                            "manufacturer": base.get("kismet.device.base.manuf", ""),
                            "first_seen": base.get("kismet.device.base.first_time", 0),
                            "last_seen": base.get("kismet.device.base.last_time", 0),
                            "packets": 0,
                            "lat": lat,
                            "lon": lon,
                        })

                elif "device_names" in tables:
                    # Legacy devicetracker format — key/name pairs only
                    cur.execute("SELECT key, name FROM device_names LIMIT 500")
                    for row in cur.fetchall():
                        devices.append({
                            "mac": row["key"] or "",
                            "ssid": row["name"] or "",
                            "device_type": "Wi-Fi",
                            "signal_dbm": 0,
                            "channel": "",
                            "encryption": "",
                            "manufacturer": "",
                            "first_seen": 0,
                            "last_seen": 0,
                            "packets": 0,
                            "lat": HOST_LAT,
                            "lon": HOST_LON,
                        })

                if devices:
                    return devices
            except Exception as e:
                logger.warning(f"Kismet SQLite error on {db_path}: {e}")
            finally:
                if conn:
                    conn.close()

        return []
