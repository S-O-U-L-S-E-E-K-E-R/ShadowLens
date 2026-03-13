"""Snort3 IDS alert log parser.

Snort3 alert_json format:
  { "timestamp": "03/11-20:24:56.995355", "pkt_num": 2, "proto": "TCP",
    "pkt_gen": "raw", "pkt_len": 83, "dir": "S2C",
    "src_ap": "151.101.54.217:443", "dst_ap": "192.168.1.26:34622",
    "rule": "129:8:1", "action": "allow" }
"""

import hashlib
import json
import logging
import math
import os
import re
import time

from config import SNORT_LOG_DIR, SNORT_ALERT_FILE, HOST_LAT, HOST_LON
from runners.base import BaseToolRunner

logger = logging.getLogger(__name__)

# Load sid-msg.map for rule descriptions
_SID_MSG_MAP: dict[int, str] = {}
_SID_MAP_PATH = os.environ.get("SNORT_SID_MAP", "/etc/snort/sid-msg.map")
if os.path.isfile(_SID_MAP_PATH):
    try:
        with open(_SID_MAP_PATH) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split(" || ", 1)
                if len(parts) >= 2:
                    try:
                        _SID_MSG_MAP[int(parts[0].strip())] = parts[1].strip()
                    except ValueError:
                        continue
        logger.info(f"Loaded {len(_SID_MSG_MAP)} Snort rule descriptions")
    except Exception as e:
        logger.warning(f"Failed to load sid-msg.map: {e}")

# Builtin decoder/inspector rule descriptions (GID:SID)
_BUILTIN_MSGS: dict[str, str] = {
    "116:6": "Ethernet truncated header",
    "116:45": "TCP timestamp option",
    "116:46": "TCP timestamp option length",
    "116:97": "IP fragment overlap",
    "116:151": "Ethernet header length",
    "116:275": "Ethernet header anomaly",
    "116:432": "IP decoder anomaly",
    "116:444": "IP multicast anomaly",
    "112:1": "ARP decoder event",
    "119:2": "HTTP inspect — invalid header",
    "119:19": "HTTP inspect — chunk encoding",
    "119:31": "HTTP inspect — long header",
    "119:228": "HTTP inspect — anomalous response",
    "120:3": "HTTP client body extraction",
    "122:1": "Portscan detected",
    "122:2": "Portscan decoy detected",
    "122:3": "Portscan distributed",
    "122:4": "Portscan sweep detected",
    "122:15": "Portscan — filtered scan",
    "122:17": "Portscan — ICMP sweep",
    "123:8": "FTP bounce attempt",
    "124:1": "SMTP data overflow",
    "128:1": "SSH protocol mismatch",
    "129:2": "SSL invalid client hello",
    "129:5": "SSL v2 session detected",
    "129:8": "SSL invalid server hello",
    "129:12": "SSL v3 abort handshake",
    "129:14": "SSL heartbeat",
    "129:15": "SSL handshake anomaly",
    "133:1": "DNS overflow attempt",
    "137:2": "DNS inspector event",
    "1:402": "ICMP destination unreachable",
    "1:408": "ICMP echo reply",
}

# GIDs/rules that are decoder/inspector noise — not real security events.
# These fire on normal traffic (jumbo frames, TLS 1.3, ARP, multicast, ICMP unreachable).
_NOISE_GIDS: set[int] = {112, 116}  # ARP decoder, protocol decoder
_NOISE_RULES: set[str] = {
    "129:8",   # SSL invalid server hello — TLS 1.3 negotiation
    "129:15",  # SSL handshake anomaly — TLS 1.3 handshake
    "1:402",   # ICMP destination unreachable — normal ICMP
    "1:408",   # ICMP echo reply — normal ping
}

# RFC1918 check
_PRIVATE_NETS = [
    (0x0A000000, 0xFF000000),  # 10.0.0.0/8
    (0xAC100000, 0xFFF00000),  # 172.16.0.0/12
    (0xC0A80000, 0xFFFF0000),  # 192.168.0.0/16
]

def _is_private(ip: str) -> bool:
    try:
        parts = ip.split(".")
        if len(parts) != 4:
            return True
        val = (int(parts[0]) << 24) | (int(parts[1]) << 16) | (int(parts[2]) << 8) | int(parts[3])
        return any((val & mask) == net for net, mask in _PRIVATE_NETS)
    except Exception:
        return True


def _geolocate_ip(ip: str) -> tuple[float | None, float | None]:
    """Return lat/lon for an IP. Private IPs get host location, public IPs get
    a deterministic spread around host coords (real geolocation would need an
    external API call which is too slow for bulk alerts)."""
    if _is_private(ip):
        return HOST_LAT, HOST_LON
    # Deterministic offset for public IPs based on IP hash
    seed = hashlib.md5(ip.encode()).digest()
    angle = (seed[0] / 255.0) * 2 * math.pi
    radius = 0.003 + (seed[1] / 255.0) * 0.01  # ~300m to 1.4km
    return HOST_LAT + radius * math.cos(angle), HOST_LON + radius * math.sin(angle)


class SnortRunner(BaseToolRunner):
    tool_name = "snort"
    cache_ttl = 30

    async def get_alerts(self, limit: int = 200) -> list[dict]:
        cache_key = self._cache_key("alerts", str(limit))
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        alerts = self._parse_snort3_json(limit) or self._parse_text_alerts(limit)
        self._set_cached(cache_key, alerts)
        return alerts

    def _get_rule_msg(self, rule: str) -> str:
        """Look up rule description from GID:SID:REV string."""
        parts = rule.split(":")
        if len(parts) >= 2:
            gid = int(parts[0]) if parts[0].isdigit() else 0
            gid_sid = f"{parts[0]}:{parts[1]}"
            sid = int(parts[1]) if parts[1].isdigit() else 0

            # Check builtin map first (covers all GIDs)
            if gid_sid in _BUILTIN_MSGS:
                return _BUILTIN_MSGS[gid_sid]

            # sid-msg.map is ONLY for GID=1 community rules.
            # Using it for other GIDs maps wrong descriptions (e.g.
            # GID:119 SID:228 → HTTP inspector, NOT "TFN DDoS" from GID:1 SID:228)
            if gid == 1 and sid in _SID_MSG_MAP:
                return _SID_MSG_MAP[sid]

            return f"Rule {rule}"
        return rule

    def _parse_src_dst(self, ap: str) -> tuple[str, int]:
        """Parse 'IP:port' or ':0' format from Snort3 src_ap/dst_ap."""
        if not ap or ap == ":0":
            return "", 0
        # Handle IPv4:port  (e.g. "192.168.1.26:443")
        m = re.match(r'^([\d.]+):(\d+)$', ap)
        if m:
            return m.group(1), int(m.group(2))
        # Handle IPv6:port  (e.g. "2607:6bc0::10:443" — last segment is port)
        # Snort3 appends ":port" to IPv6 addresses in src_ap/dst_ap
        if ':' in ap and not ap.startswith(':'):
            # Strip trailing :port from IPv6 address
            last_colon = ap.rfind(':')
            possible_port = ap[last_colon + 1:]
            if possible_port.isdigit():
                ipv6 = ap[:last_colon]
                return ipv6, int(possible_port)
        return ap, 0

    def _parse_snort3_json(self, limit: int) -> list[dict]:
        """Parse Snort3 alert_json output."""
        path = os.path.join(SNORT_LOG_DIR, SNORT_ALERT_FILE)
        if not os.path.isfile(path):
            return []

        try:
            alerts = []
            with open(path, "r") as f:
                lines = f.readlines()

            # Deduplicate by rule — keep latest occurrence of each rule+src+dst combo
            seen_rules: dict[str, dict] = {}

            for line in reversed(lines[-limit * 3:]):
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue

                rule = obj.get("rule", "")
                if not rule:
                    continue

                parts = rule.split(":")
                gid = int(parts[0]) if parts[0].isdigit() else 0
                sid = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
                gid_sid = f"{gid}:{sid}"

                # Filter out decoder/inspector noise — these fire on normal
                # traffic and are not security events
                if gid in _NOISE_GIDS or gid_sid in _NOISE_RULES:
                    continue

                src_ip, src_port = self._parse_src_dst(obj.get("src_ap", ""))
                dst_ip, dst_port = self._parse_src_dst(obj.get("dst_ap", ""))
                msg = self._get_rule_msg(rule)
                proto = obj.get("proto", "")
                direction = obj.get("dir", "")

                # Use the external IP for geolocation (the interesting one)
                geo_ip = src_ip
                if _is_private(src_ip) and not _is_private(dst_ip):
                    geo_ip = dst_ip
                elif not src_ip:
                    geo_ip = dst_ip

                lat, lon = _geolocate_ip(geo_ip) if geo_ip else (HOST_LAT, HOST_LON)

                # Dedup key — same rule + same endpoints = same alert
                dedup_key = f"{rule}|{src_ip}|{dst_ip}"
                if dedup_key in seen_rules:
                    continue
                seen_rules[dedup_key] = True

                # Priority: GID=1 community rules are more significant
                # Portscan (122) gets priority 2, other inspectors get 3
                if gid == 1:
                    priority = 1  # Community rule match — real detection
                elif gid == 122:
                    priority = 2  # Portscan — notable
                else:
                    priority = 3  # Inspector event

                alerts.append({
                    "id": f"snort-{gid}-{sid}-{len(alerts)}",
                    "timestamp": obj.get("timestamp", ""),
                    "signature_id": sid,
                    "signature_msg": msg,
                    "classification": f"GID:{gid}" if gid > 1 else "",
                    "priority": priority,
                    "src_ip": src_ip,
                    "dst_ip": dst_ip,
                    "src_port": src_port,
                    "dst_port": dst_port,
                    "protocol": proto,
                    "direction": direction,
                    "action": obj.get("action", ""),
                    "pkt_len": obj.get("pkt_len", 0),
                    "lat": lat,
                    "lon": lon,
                })

                if len(alerts) >= limit:
                    break

            return alerts
        except PermissionError:
            logger.warning(f"Permission denied reading {path} — run agent as root or add user to 'adm' group")
            return []
        except Exception as e:
            logger.warning(f"Snort3 JSON parse error: {e}")
            return []

    def _parse_text_alerts(self, limit: int) -> list[dict]:
        """Parse Snort3 alert_fast.txt format."""
        path = os.path.join(SNORT_LOG_DIR, "alert_fast.txt")
        if not os.path.isfile(path):
            return []

        try:
            alerts = []
            with open(path, "r") as f:
                lines = f.readlines()

            for line in reversed(lines[-limit * 2:]):
                line = line.strip()
                if not line:
                    continue
                # Format: timestamp [**] [gid:sid:rev] msg [**] ... {proto} src -> dst
                m = re.match(
                    r'^([\d/\-:.]+)\s+\[\*\*\]\s+\[(\d+):(\d+):\d+\]\s+"?([^"]*)"?\s+\[\*\*\].*\{(\w+)\}\s+([\d.]+):?(\d*)\s*->\s*([\d.]+):?(\d*)',
                    line
                )
                if m:
                    ts, gid, sid, msg, proto = m.group(1), int(m.group(2)), int(m.group(3)), m.group(4), m.group(5)
                    gid_sid = f"{gid}:{sid}"

                    # Filter noise
                    if gid in _NOISE_GIDS or gid_sid in _NOISE_RULES:
                        continue

                    src_ip, src_port = m.group(6), int(m.group(7)) if m.group(7) else 0
                    dst_ip, dst_port = m.group(8), int(m.group(9)) if m.group(9) else 0

                    geo_ip = dst_ip if _is_private(src_ip) and not _is_private(dst_ip) else src_ip
                    lat, lon = _geolocate_ip(geo_ip)

                    alerts.append({
                        "id": f"snort-{gid}-{sid}-{len(alerts)}",
                        "timestamp": ts,
                        "signature_id": sid,
                        "signature_msg": msg.strip(),
                        "classification": f"GID:{gid}" if gid > 1 else "",
                        "priority": 2 if gid == 1 else 3,
                        "src_ip": src_ip,
                        "dst_ip": dst_ip,
                        "src_port": src_port,
                        "dst_port": dst_port,
                        "protocol": proto,
                        "lat": lat,
                        "lon": lon,
                    })
                    if len(alerts) >= limit:
                        break

            return alerts
        except PermissionError:
            logger.warning(f"Permission denied reading {path}")
            return []
        except Exception as e:
            logger.warning(f"Snort text parse error: {e}")
            return []
