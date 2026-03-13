"""Nmap scanner runner with async job queue and RFC1918 whitelist."""

import asyncio
import hashlib
import ipaddress
import json
import logging
import math
import os
import time
import xml.etree.ElementTree as ET

from config import TOOL_PATHS, NMAP_ALLOWED_RANGES, HOST_LAT, HOST_LON, SCAN_TIMEOUT, RESULTS_DIR
from runners.base import BaseToolRunner, create_job, update_job

logger = logging.getLogger(__name__)


class NmapRunner(BaseToolRunner):
    tool_name = "nmap"
    cache_ttl = 900  # 15 minutes

    def __init__(self):
        super().__init__()
        self._last_results: list[dict] = []

    def _is_target_allowed(self, target: str) -> bool:
        """Allow RFC1918 ranges and single public IPs. Block broad public ranges."""
        try:
            net = ipaddress.ip_network(target, strict=False)
            # Always allow private ranges
            if any(net.subnet_of(ipaddress.ip_network(allowed, strict=False))
                   for allowed in NMAP_ALLOWED_RANGES):
                return True
            # Allow single public IPs or /32s (not wide sweeps)
            if net.prefixlen >= 32:
                return True
            return False
        except ValueError:
            # Hostname — allow single hosts
            return "." in target and "/" not in target

    async def get_results(self) -> list[dict]:
        """Return cached/last scan results."""
        return self._last_results

    async def start_scan(self, target: str, scan_type: str = "quick") -> dict:
        """Start an async nmap scan. Returns job info."""
        nmap_path = TOOL_PATHS.get("nmap", "nmap")
        if not os.path.isfile(nmap_path):
            return {"error": "nmap not installed", "status": "unavailable"}

        if not self._is_target_allowed(target):
            return {"error": f"Target {target} not in allowed ranges (RFC1918 only)", "status": "denied"}

        job_id = create_job("nmap", target)

        # Build scan command — all use XML output for structured parsing
        if scan_type == "quick":
            # Fast: service detection on top 100 ports
            cmd = [nmap_path, "-sV", "-sC", "--top-ports", "100", "-T4", "--open", "-oX", "-", target]
        elif scan_type == "service":
            # Medium: service + OS detection, top 1000 ports, default scripts
            cmd = [nmap_path, "-sV", "-O", "-sC", "--top-ports", "1000", "-T4", "--open", "-oX", "-", target]
        else:
            # Full: all 65535 ports, OS, services, scripts, traceroute
            cmd = [nmap_path, "-sS", "-sV", "-O", "-sC", "--traceroute", "-p-", "-T4", "--open", "-oX", "-", target]

        asyncio.create_task(self._run_scan(job_id, cmd))
        return {"job_id": job_id, "status": "started", "target": target}

    async def _run_scan(self, job_id: str, cmd: list[str]):
        """Execute nmap scan and parse results."""
        update_job(job_id, status="running")
        try:
            returncode, stdout, stderr = await self.run_subprocess(cmd, timeout=SCAN_TIMEOUT)
            if returncode != 0:
                update_job(job_id, status="error", error=stderr[:500])
                return

            hosts = self._parse_xml(stdout)
            self._last_results = hosts
            result_file = self.save_result(f"nmap-{job_id}.json", hosts)
            update_job(job_id, status="complete", result={"hosts": len(hosts), "file": result_file})
        except Exception as e:
            update_job(job_id, status="error", error=str(e))

    def _parse_xml(self, xml_str: str) -> list[dict]:
        """Parse nmap XML output into host dicts."""
        hosts = []
        try:
            root = ET.fromstring(xml_str)
            for host_el in root.findall("host"):
                state_el = host_el.find("status")
                if state_el is not None and state_el.get("state") != "up":
                    continue

                ip = ""
                mac = ""
                vendor = ""
                hostname = ""
                for addr in host_el.findall("address"):
                    if addr.get("addrtype") == "ipv4":
                        ip = addr.get("addr", "")
                    elif addr.get("addrtype") == "mac":
                        mac = addr.get("addr", "")
                        vendor = addr.get("vendor", "")

                hostnames_el = host_el.find("hostnames")
                if hostnames_el is not None:
                    hn = hostnames_el.find("hostname")
                    if hn is not None:
                        hostname = hn.get("name", "")

                os_fingerprint = ""
                os_el = host_el.find("os")
                if os_el is not None:
                    osmatch = os_el.find("osmatch")
                    if osmatch is not None:
                        os_fingerprint = osmatch.get("name", "")

                open_ports = []
                services = []
                ports_el = host_el.find("ports")
                if ports_el is not None:
                    for port_el in ports_el.findall("port"):
                        port_state = port_el.find("state")
                        if port_state is not None and port_state.get("state") == "open":
                            portid = port_el.get("portid", "")
                            protocol = port_el.get("protocol", "tcp")
                            open_ports.append(f"{portid}/{protocol}")
                            svc = port_el.find("service")
                            if svc is not None:
                                services.append({
                                    "port": int(portid) if portid.isdigit() else 0,
                                    "protocol": protocol,
                                    "name": svc.get("name", ""),
                                    "product": svc.get("product", ""),
                                    "version": svc.get("version", ""),
                                })

                # Spread LAN hosts in a small radius (~200m) around host
                # location so they don't stack into a single dot on the map.
                # Uses deterministic hash so each device always lands in the
                # same spot across scans.
                seed = hashlib.md5((ip + mac).encode()).digest()
                angle = (seed[0] / 255.0) * 2 * math.pi
                radius = (seed[1] / 255.0) * 0.002  # ~200m in degrees
                lat_offset = radius * math.cos(angle)
                lon_offset = radius * math.sin(angle)

                hosts.append({
                    "ip": ip,
                    "hostname": hostname,
                    "os_fingerprint": os_fingerprint,
                    "mac": mac,
                    "vendor": vendor,
                    "open_ports": open_ports,
                    "services": services,
                    "state": "up",
                    "scan_time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "lat": HOST_LAT + lat_offset,
                    "lon": HOST_LON + lon_offset,
                })
        except ET.ParseError as e:
            logger.warning(f"Nmap XML parse error: {e}")
        return hosts
