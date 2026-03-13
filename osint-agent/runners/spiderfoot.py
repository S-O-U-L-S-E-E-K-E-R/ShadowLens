"""SpiderFoot runner — CLI-based OSINT scans + web API proxy (port 5001)."""

import json
import logging
import re

import httpx

from config import SPIDERFOOT_URL, TOOL_PATHS
from runners.base import BaseToolRunner, create_job, update_job

logger = logging.getLogger(__name__)

# Allowed use cases for CLI scans
_VALID_USE_CASES = {"all", "footprint", "investigate", "passive"}

# Validate targets — only domains, IPs, emails, hostnames
_TARGET_RE = re.compile(
    r'^('
    r'[a-zA-Z0-9]([a-zA-Z0-9\-]*[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]*[a-zA-Z0-9])?)*\.[a-zA-Z]{2,}'  # domain
    r'|'
    r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}'  # IPv4
    r'|'
    r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}'  # email
    r')$'
)


class SpiderFootRunner(BaseToolRunner):
    tool_name = "spiderfoot"
    cache_ttl = 600  # 10 min cache for results

    async def get_scans(self) -> list[dict]:
        """List all SpiderFoot scans from web UI API."""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"{SPIDERFOOT_URL}/scanlist")
                if resp.status_code == 200:
                    return resp.json()
        except Exception as e:
            logger.debug(f"SpiderFoot web UI not reachable: {e}")
        return []

    async def get_scan_results(self, scan_id: str) -> dict:
        """Get results for a specific scan from web UI API."""
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(f"{SPIDERFOOT_URL}/scaneventresults", params={"id": scan_id})
                if resp.status_code == 200:
                    return {"status": "ok", "data": resp.json()}
        except Exception as e:
            logger.debug(f"SpiderFoot scan results error: {e}")
        return {"status": "unavailable", "data": []}

    async def run_scan(self, target: str, use_case: str = "passive") -> dict:
        """Run a SpiderFoot CLI scan against a target.

        Returns structured results: emails, hostnames, IPs, technologies, etc.
        Uses passive mode by default (no active probing) for safety.
        """
        # Validate target
        if not _TARGET_RE.match(target):
            return {"status": "error", "error": "Invalid target format. Use domain, IP, or email."}

        if use_case not in _VALID_USE_CASES:
            use_case = "passive"

        # Check if spiderfoot binary exists
        sf_path = TOOL_PATHS.get("spiderfoot", "spiderfoot")

        # Create async job
        job_id = create_job("spiderfoot", target)
        update_job(job_id, status="running")

        # Build CLI command — JSON output, passive use case
        cmd = [
            sf_path,
            "-s", target,
            "-u", use_case,
            "-o", "json",
            "-q",  # quiet mode (no banner)
            "-max-threads", "5",
        ]

        logger.info(f"SpiderFoot scan started: {target} (use_case={use_case}, job={job_id})")

        # Run with extended timeout — passive scans can take 2-5 minutes
        returncode, stdout, stderr = await self.run_subprocess(cmd, timeout=300)

        if returncode != 0 and returncode != -1:
            logger.warning(f"SpiderFoot exited with code {returncode}: {stderr[:500]}")

        if returncode == -2:
            update_job(job_id, status="error", error="SpiderFoot not installed")
            return {"status": "unavailable", "error": "SpiderFoot binary not found", "job_id": job_id}

        if returncode == -1:
            update_job(job_id, status="error", error="Timeout")
            return {"status": "error", "error": "Scan timed out after 5 minutes", "job_id": job_id}

        # Parse JSON output
        results = self._parse_output(stdout, target)
        update_job(job_id, status="complete", result=results)

        # Cache results
        cache_key = self._cache_key(target, use_case)
        self._set_cached(cache_key, results)

        # Save to disk
        self.save_result(f"spiderfoot_{target.replace('.', '_')}.json", results)

        logger.info(f"SpiderFoot scan complete: {target} — {sum(len(v) for v in results.get('findings', {}).values())} findings")
        return {"status": "ok", "data": results, "job_id": job_id}

    def _parse_output(self, stdout: str, target: str) -> dict:
        """Parse SpiderFoot JSON output into categorized findings."""
        findings = {
            "emails": [],
            "hostnames": [],
            "ips": [],
            "urls": [],
            "technologies": [],
            "dns_records": [],
            "ports": [],
            "vulnerabilities": [],
            "social_media": [],
            "leaks": [],
            "other": [],
        }
        raw_events = []

        # SpiderFoot JSON output is one JSON object per line
        for line in stdout.strip().split('\n'):
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
                raw_events.append(event)
            except json.JSONDecodeError:
                continue

        # Categorize events by type
        for event in raw_events:
            etype = event.get("type", "")
            data = event.get("data", "")
            source = event.get("source", "")

            if not data or not etype:
                continue

            entry = {"type": etype, "data": str(data)[:500], "source": source}

            if "EMAIL" in etype:
                findings["emails"].append(entry)
            elif etype in ("INTERNET_NAME", "DOMAIN_NAME", "AFFILIATE_INTERNET_NAME", "CO_HOSTED_SITE"):
                findings["hostnames"].append(entry)
            elif etype in ("IP_ADDRESS", "IPV6_ADDRESS", "AFFILIATE_IPADDR"):
                findings["ips"].append(entry)
            elif "URL" in etype or "WEB" in etype:
                findings["urls"].append(entry)
            elif etype in ("WEBSERVER_TECHNOLOGY", "WEBSERVER_BANNER", "SOFTWARE_USED"):
                findings["technologies"].append(entry)
            elif "DNS" in etype or etype in ("A_RECORD", "AAAA_RECORD", "MX_RECORD", "NS_RECORD", "TXT_RECORD"):
                findings["dns_records"].append(entry)
            elif "PORT" in etype or "TCP" in etype or "UDP" in etype:
                findings["ports"].append(entry)
            elif "VULNERABILITY" in etype or "CVE" in etype:
                findings["vulnerabilities"].append(entry)
            elif "SOCIAL" in etype or "ACCOUNT" in etype:
                findings["social_media"].append(entry)
            elif "LEAK" in etype or "BREACH" in etype or "DARKNET" in etype:
                findings["leaks"].append(entry)
            else:
                findings["other"].append(entry)

        # Deduplicate by data value within each category
        for cat in findings:
            seen = set()
            deduped = []
            for item in findings[cat]:
                if item["data"] not in seen:
                    seen.add(item["data"])
                    deduped.append(item)
            findings[cat] = deduped

        return {
            "target": target,
            "total_events": len(raw_events),
            "findings": findings,
            "summary": {cat: len(items) for cat, items in findings.items() if items},
        }

    async def get_cached_results(self, target: str, use_case: str = "passive") -> dict | None:
        """Return cached results if available."""
        cache_key = self._cache_key(target, use_case)
        return self._get_cached(cache_key)
