"""Threat intelligence runners — free, no-auth APIs for IP/URL/hash enrichment.

Sources:
  - Shodan InternetDB: Free IP lookup (ports, vulns, hostnames, CPEs)
  - URLhaus (abuse.ch): Malware URL database
  - ThreatFox (abuse.ch): IOC database (IPs, domains, hashes)
  - MalwareBazaar (abuse.ch): Malware hash lookups
  - Tor exit node check
"""

import json
import logging
from typing import Any

import httpx

from runners.base import BaseToolRunner

logger = logging.getLogger(__name__)

# Tor exit node list — cached in memory
_tor_exit_nodes: set = set()
_tor_last_fetch: float = 0


class ThreatIntelRunner(BaseToolRunner):
    tool_name = "threat_intel"
    cache_ttl = 600  # 10 min cache

    async def internetdb_lookup(self, ip: str) -> dict:
        """Free Shodan InternetDB — ports, vulns, hostnames, CPEs for any IP.

        No API key required. Returns open ports, known vulnerabilities,
        hostnames, and CPE identifiers.
        """
        cache_key = self._cache_key("internetdb", ip)
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"https://internetdb.shodan.io/{ip}")
                if resp.status_code == 200:
                    data = resp.json()
                    output = {
                        "status": "ok",
                        "ip": ip,
                        "ports": data.get("ports", []),
                        "hostnames": data.get("hostnames", []),
                        "vulns": data.get("vulns", []),
                        "cpes": data.get("cpes", []),
                        "tags": data.get("tags", []),
                        "port_count": len(data.get("ports", [])),
                        "vuln_count": len(data.get("vulns", [])),
                        "source": "shodan_internetdb",
                    }
                elif resp.status_code == 404:
                    output = {"status": "ok", "ip": ip, "ports": [], "hostnames": [],
                              "vulns": [], "cpes": [], "tags": [], "port_count": 0,
                              "vuln_count": 0, "source": "shodan_internetdb"}
                else:
                    output = {"status": "error", "error": f"HTTP {resp.status_code}", "ip": ip}
        except Exception as e:
            logger.warning(f"InternetDB lookup failed: {e}")
            output = {"status": "error", "error": str(e), "ip": ip}

        self._set_cached(cache_key, output)
        return output

    async def urlhaus_lookup(self, url: str) -> dict:
        """Check if a URL is in the URLhaus malware database."""
        cache_key = self._cache_key("urlhaus", url)
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    "https://urlhaus-api.abuse.ch/v1/url/",
                    data={"url": url},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    output = {
                        "status": "ok",
                        "url": url,
                        "threat": data.get("threat", ""),
                        "url_status": data.get("url_status", ""),
                        "tags": data.get("tags") or [],
                        "payloads": len(data.get("payloads") or []),
                        "date_added": data.get("date_added", ""),
                        "reporter": data.get("reporter", ""),
                        "found": data.get("query_status") != "no_results",
                        "source": "urlhaus",
                    }
                else:
                    output = {"status": "error", "error": f"HTTP {resp.status_code}", "url": url}
        except Exception as e:
            logger.warning(f"URLhaus lookup failed: {e}")
            output = {"status": "error", "error": str(e), "url": url}

        self._set_cached(cache_key, output)
        return output

    async def threatfox_search(self, query: str, query_type: str = "search_ioc") -> dict:
        """Search ThreatFox IOC database (IPs, domains, hashes).

        query_type: search_ioc, search_hash, search_tag
        """
        cache_key = self._cache_key("threatfox", query)
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    "https://threatfox-api.abuse.ch/api/v1/",
                    json={"query": query_type, "search_term": query},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    iocs = data.get("data") or []
                    output = {
                        "status": "ok",
                        "query": query,
                        "total": len(iocs) if isinstance(iocs, list) else 0,
                        "iocs": iocs[:20] if isinstance(iocs, list) else [],
                        "found": data.get("query_status") != "no_result",
                        "source": "threatfox",
                    }
                else:
                    output = {"status": "error", "error": f"HTTP {resp.status_code}", "query": query}
        except Exception as e:
            logger.warning(f"ThreatFox search failed: {e}")
            output = {"status": "error", "error": str(e), "query": query}

        self._set_cached(cache_key, output)
        return output

    async def malwarebazaar_hash(self, hash_value: str) -> dict:
        """Lookup a hash in MalwareBazaar malware sample database."""
        cache_key = self._cache_key("bazaar", hash_value)
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    "https://mb-api.abuse.ch/api/v1/",
                    data={"query": "get_info", "hash": hash_value},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    samples = data.get("data") or []
                    if isinstance(samples, list) and samples:
                        sample = samples[0]
                        output = {
                            "status": "ok",
                            "hash": hash_value,
                            "found": True,
                            "file_type": sample.get("file_type", ""),
                            "file_size": sample.get("file_size", 0),
                            "signature": sample.get("signature", ""),
                            "tags": sample.get("tags") or [],
                            "first_seen": sample.get("first_seen", ""),
                            "last_seen": sample.get("last_seen", ""),
                            "intelligence": sample.get("intelligence", {}),
                            "source": "malwarebazaar",
                        }
                    else:
                        output = {"status": "ok", "hash": hash_value, "found": False,
                                  "source": "malwarebazaar"}
                else:
                    output = {"status": "error", "error": f"HTTP {resp.status_code}"}
        except Exception as e:
            logger.warning(f"MalwareBazaar lookup failed: {e}")
            output = {"status": "error", "error": str(e)}

        self._set_cached(cache_key, output)
        return output

    async def check_tor_exit(self, ip: str) -> dict:
        """Check if an IP is a known Tor exit node."""
        global _tor_exit_nodes, _tor_last_fetch
        import time

        # Refresh Tor list every 30 minutes
        if time.time() - _tor_last_fetch > 1800 or not _tor_exit_nodes:
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.get("https://check.torproject.org/torbulkexitlist")
                    if resp.status_code == 200:
                        _tor_exit_nodes = {line.strip() for line in resp.text.splitlines() if line.strip() and not line.startswith("#")}
                        _tor_last_fetch = time.time()
                        logger.info(f"Tor exit list refreshed: {len(_tor_exit_nodes)} nodes")
            except Exception as e:
                logger.warning(f"Tor exit list fetch failed: {e}")

        is_tor = ip in _tor_exit_nodes
        return {
            "status": "ok",
            "ip": ip,
            "is_tor_exit": is_tor,
            "tor_nodes_count": len(_tor_exit_nodes),
            "source": "torproject",
        }

    async def enrich_ip(self, ip: str) -> dict:
        """Full IP enrichment — InternetDB + ThreatFox + Tor check in parallel."""
        import asyncio
        internetdb, threatfox, tor = await asyncio.gather(
            self.internetdb_lookup(ip),
            self.threatfox_search(ip),
            self.check_tor_exit(ip),
        )
        return {
            "status": "ok",
            "ip": ip,
            "internetdb": internetdb,
            "threatfox": threatfox,
            "tor": tor,
            "summary": {
                "ports": internetdb.get("port_count", 0),
                "vulns": internetdb.get("vuln_count", 0),
                "hostnames": internetdb.get("hostnames", []),
                "is_tor": tor.get("is_tor_exit", False),
                "threat_iocs": threatfox.get("total", 0),
            },
        }
