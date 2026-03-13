"""Nuclei vulnerability scanner runner with async job queue."""

import asyncio
import json
import logging
import os
import time

from config import TOOL_PATHS, SCAN_TIMEOUT, HOST_LAT, HOST_LON
from runners.base import BaseToolRunner, create_job, update_job

logger = logging.getLogger(__name__)


class NucleiRunner(BaseToolRunner):
    tool_name = "nuclei"
    cache_ttl = 900

    def __init__(self):
        super().__init__()
        self._last_results: list[dict] = []

    async def get_results(self) -> list[dict]:
        return self._last_results

    async def start_scan(self, target: str, templates: str = "") -> dict:
        """Start an async nuclei scan."""
        nuclei_path = TOOL_PATHS.get("nuclei", "nuclei")
        if not os.path.isfile(nuclei_path):
            return {"error": "nuclei not installed", "status": "unavailable"}

        # Validate templates param — only allow alphanumeric, hyphens, slashes, commas
        if templates and not all(c.isalnum() or c in "-_/,." for c in templates):
            return {"error": "Invalid template name", "status": "denied"}

        job_id = create_job("nuclei", target)

        cmd = [nuclei_path, "-u", target, "-jsonl", "-silent"]
        if templates:
            cmd.extend(["-t", templates])

        asyncio.create_task(self._run_scan(job_id, cmd))
        return {"job_id": job_id, "status": "started", "target": target}

    async def _run_scan(self, job_id: str, cmd: list[str]):
        update_job(job_id, status="running")
        try:
            returncode, stdout, stderr = await self.run_subprocess(cmd, timeout=SCAN_TIMEOUT)
            if returncode not in (0, None) and not stdout.strip():
                update_job(job_id, status="error", error=stderr[:500])
                return
            vulns = self._parse_jsonl(stdout)
            self._last_results = vulns
            result_file = self.save_result(f"nuclei-{job_id}.json", vulns)
            update_job(job_id, status="complete", result={"vulns": len(vulns), "file": result_file})
        except Exception as e:
            update_job(job_id, status="error", error=str(e))

    def _parse_jsonl(self, output: str) -> list[dict]:
        vulns = []
        for line in output.strip().split("\n"):
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
                vulns.append({
                    "id": f"nuclei-{obj.get('template-id', '')}-{len(vulns)}",
                    "template_id": obj.get("template-id", ""),
                    "vuln_name": obj.get("info", {}).get("name", obj.get("template-id", "")),
                    "vuln_severity": obj.get("info", {}).get("severity", "info"),
                    "target": obj.get("host", obj.get("matched-at", "")),
                    "matched_at": obj.get("matched-at", ""),
                    "description": obj.get("info", {}).get("description", ""),
                    "scan_time": obj.get("timestamp", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())),
                    "lat": HOST_LAT,
                    "lon": HOST_LON,
                })
            except json.JSONDecodeError as e:
                logger.debug(f"Nuclei JSON parse error: {e}")
                continue
        return vulns
