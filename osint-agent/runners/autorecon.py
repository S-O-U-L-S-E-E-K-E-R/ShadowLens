"""AutoRecon runner — deep reconnaissance with automatic service enumeration."""

import asyncio
import glob
import logging
import os
import time

from config import TOOL_PATHS, RESULTS_DIR, HOST_LAT, HOST_LON
from runners.base import BaseToolRunner, create_job, update_job

logger = logging.getLogger(__name__)

# AutoRecon timeout: it runs many sub-scans, allow up to 20 minutes
AUTORECON_TIMEOUT = 1200


class AutoReconRunner(BaseToolRunner):
    tool_name = "autorecon"
    cache_ttl = 1800  # 30 minutes — results are expensive to produce

    async def start_scan(self, target: str, ports: str = "") -> dict:
        """Start an async AutoRecon scan. Returns job info."""
        ar_path = TOOL_PATHS.get("autorecon", "autorecon")
        if not os.path.isfile(ar_path):
            return {"error": "autorecon not installed", "status": "unavailable"}

        job_id = create_job("autorecon", target)
        output_dir = os.path.join(RESULTS_DIR, f"autorecon-{job_id}")
        os.makedirs(output_dir, exist_ok=True)

        cmd = [
            ar_path, target,
            "-o", output_dir,
            "--single-target",
            "--only-scans-dir",
            "--heartbeat", "0",
            "--disable-keyboard-control",
        ]
        if ports:
            cmd.extend(["-p", ports])

        asyncio.create_task(self._run_scan(job_id, cmd, output_dir, target))
        return {"job_id": job_id, "status": "started", "target": target}

    async def _run_scan(self, job_id: str, cmd: list[str], output_dir: str, target: str):
        """Execute autorecon and parse results directory."""
        update_job(job_id, status="running")
        try:
            returncode, stdout, stderr = await self.run_subprocess(
                cmd, timeout=AUTORECON_TIMEOUT
            )

            # AutoRecon may return non-zero but still produce useful results
            results = self._parse_results_dir(output_dir, target)

            if not results["services"] and returncode != 0:
                update_job(job_id, status="error", error=stderr[:500])
                return

            result_file = self.save_result(f"autorecon-{job_id}.json", results)
            self._last_results = results
            update_job(
                job_id,
                status="complete",
                result={
                    "services": len(results["services"]),
                    "files": results["total_files"],
                    "file": result_file,
                    "data": results,
                },
            )
        except Exception as e:
            update_job(job_id, status="error", error=str(e))

    def _parse_results_dir(self, output_dir: str, target: str) -> dict:
        """Parse AutoRecon's output directory structure into structured results.

        AutoRecon outputs:
          output_dir/scans/
            _commands.log          — all commands run
            _full_tcp_nmap.txt     — full nmap results
            tcp80/                 — per-port service scans
              tcp_80_http_*.txt
            ...
        """
        results = {
            "target": target,
            "scan_time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "services": [],
            "commands_run": [],
            "total_files": 0,
            "lat": HOST_LAT,
            "lon": HOST_LON,
        }

        scans_dir = output_dir
        # AutoRecon may nest under target IP or scans/
        for candidate in [
            os.path.join(output_dir, "scans"),
            os.path.join(output_dir, target, "scans"),
            output_dir,
        ]:
            if os.path.isdir(candidate):
                scans_dir = candidate
                break

        # Parse _commands.log
        commands_log = os.path.join(scans_dir, "_commands.log")
        if os.path.isfile(commands_log):
            try:
                with open(commands_log, "r", errors="replace") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#"):
                            results["commands_run"].append(line)
            except Exception:
                pass

        # Collect all scan output files
        all_files = []
        for root, dirs, files in os.walk(scans_dir):
            for fname in files:
                fpath = os.path.join(root, fname)
                all_files.append(fpath)

        results["total_files"] = len(all_files)

        # Group by service (port directories like tcp80/, tcp443/, udp53/)
        service_files: dict[str, list[str]] = {}
        for fpath in all_files:
            rel = os.path.relpath(fpath, scans_dir)
            parts = rel.split(os.sep)
            if len(parts) >= 2:
                svc_dir = parts[0]  # e.g. "tcp80"
                service_files.setdefault(svc_dir, []).append(fpath)
            else:
                service_files.setdefault("_global", []).append(fpath)

        # Parse each service's results
        for svc_name, files in sorted(service_files.items()):
            if svc_name == "_global":
                continue

            # Extract port from directory name (e.g. "tcp80" -> 80)
            port = 0
            protocol = "tcp"
            for ch_idx, ch in enumerate(svc_name):
                if ch.isdigit():
                    try:
                        port = int(svc_name[ch_idx:])
                        protocol = svc_name[:ch_idx]
                    except ValueError:
                        pass
                    break

            service_result = {
                "port": port,
                "protocol": protocol,
                "scan_files": [],
                "findings": [],
            }

            for fpath in files:
                fname = os.path.basename(fpath)
                file_info = {"name": fname, "size": 0, "preview": ""}

                try:
                    file_info["size"] = os.path.getsize(fpath)
                    # Read first 2000 chars as preview
                    with open(fpath, "r", errors="replace") as f:
                        content = f.read(2000)
                    file_info["preview"] = content

                    # Extract key findings from common scan types
                    findings = self._extract_findings(fname, content)
                    if findings:
                        service_result["findings"].extend(findings)
                except Exception:
                    pass

                service_result["scan_files"].append(file_info)

            results["services"].append(service_result)

        # Also parse global nmap results if present
        for nmap_file in glob.glob(os.path.join(scans_dir, "*nmap*")):
            try:
                with open(nmap_file, "r", errors="replace") as f:
                    content = f.read(3000)
                if content.strip():
                    results.setdefault("nmap_output", "")
                    results["nmap_output"] += content[:3000] + "\n"
            except Exception:
                pass

        return results

    def _extract_findings(self, filename: str, content: str) -> list[str]:
        """Extract notable findings from scan output."""
        findings = []
        lower = content.lower()

        # HTTP directory/file discovery (gobuster, feroxbuster, dirsearch)
        if any(kw in filename.lower() for kw in ["gobuster", "feroxbuster", "dirsearch", "dirb", "ffuf"]):
            for line in content.split("\n"):
                line = line.strip()
                # Lines with status codes 200, 301, 302, 403
                if any(f" {code} " in line or f"[{code}]" in line or f"(Status: {code})" in line
                       for code in ["200", "301", "302", "403"]):
                    if len(line) < 200:
                        findings.append(line)

        # Nikto findings
        elif "nikto" in filename.lower():
            for line in content.split("\n"):
                if line.strip().startswith("+"):
                    findings.append(line.strip()[:200])

        # SMB/enum4linux
        elif "enum4linux" in filename.lower():
            for line in content.split("\n"):
                for kw in ["share", "user", "password", "domain", "workgroup"]:
                    if kw in line.lower() and len(line.strip()) < 200:
                        findings.append(line.strip())
                        break

        # Vulnerability indicators
        if "vulnerab" in lower or "exploit" in lower or "cve-" in lower:
            for line in content.split("\n"):
                ll = line.lower()
                if "cve-" in ll or "vulnerab" in ll or "exploit" in ll:
                    if len(line.strip()) < 200:
                        findings.append(line.strip())

        # Limit findings per file
        return findings[:20]

    async def get_results(self) -> dict:
        """Return last scan results."""
        return getattr(self, "_last_results", {})
