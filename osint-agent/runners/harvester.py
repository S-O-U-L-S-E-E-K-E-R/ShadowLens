"""theHarvester wrapper for email/subdomain/IP discovery."""

import json
import logging
import os
import tempfile

from config import TOOL_PATHS, SCAN_TIMEOUT
from runners.base import BaseToolRunner

logger = logging.getLogger(__name__)


class HarvesterRunner(BaseToolRunner):
    tool_name = "theharvester"
    cache_ttl = 600

    # Allowed source engines for theHarvester -b flag
    _VALID_SOURCES = {
        "all", "anubis", "baidu", "bevigil", "binaryedge", "bing", "bingapi",
        "bufferoverun", "brave", "censys", "certspotter", "criminalip", "crtsh",
        "dnsdumpster", "duckduckgo", "fullhunt", "github-code", "hackertarget",
        "hunter", "hunterhow", "intelx", "netlas", "onyphe", "otx", "pentesttools",
        "projectdiscovery", "rapiddns", "rocketreach", "securityTrails", "shodan",
        "sitedossier", "subdomaincenter", "subdomainfinderc99", "threatminer",
        "tomba", "urlscan", "virustotal", "yahoo", "zoomeye",
    }

    async def run(self, domain: str, sources: str = "all") -> dict:
        """Run theHarvester for a target domain."""
        # Validate domain — only allow valid hostname characters
        if not domain or not all(c.isalnum() or c in "-._" for c in domain):
            return {"status": "denied", "data": {}, "error": "Invalid domain"}

        # Validate sources
        for src in sources.split(","):
            if src.strip() and src.strip() not in self._VALID_SOURCES:
                return {"status": "denied", "data": {}, "error": f"Invalid source: {src.strip()}"}

        cache_key = self._cache_key(domain, sources)
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        harvester_path = TOOL_PATHS.get("theharvester", "theHarvester")
        if not os.path.isfile(harvester_path):
            return {"status": "unavailable", "data": {}}

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            cmd = [harvester_path, "-d", domain, "-b", sources, "-f", tmp_path]
            returncode, stdout, stderr = await self.run_subprocess(cmd, timeout=SCAN_TIMEOUT)

            if returncode not in (0, None):
                logger.warning(f"theHarvester exited with code {returncode}: {stderr[:200]}")

            result = {"emails": [], "hosts": [], "ips": []}
            json_path = tmp_path + ".json" if not os.path.isfile(tmp_path) else tmp_path
            if os.path.isfile(json_path):
                with open(json_path) as f:
                    data = json.load(f)
                result["emails"] = data.get("emails", [])
                result["hosts"] = data.get("hosts", [])
                result["ips"] = data.get("ips", [])

            self._set_cached(cache_key, {"status": "ok", "data": result})
            return {"status": "ok", "data": result}
        except Exception as e:
            logger.warning(f"theHarvester error: {e}")
            return {"status": "error", "data": {}, "error": str(e)}
        finally:
            for p in [tmp_path, tmp_path + ".json", tmp_path + ".xml"]:
                if os.path.isfile(p):
                    os.unlink(p)
