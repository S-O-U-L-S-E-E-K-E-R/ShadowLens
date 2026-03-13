"""Base tool runner with subprocess execution, caching, and rate limiting."""

import asyncio
import hashlib
import json
import logging
import os
import subprocess
import time
from typing import Any, Optional

from config import RESULTS_DIR, TOOL_TIMEOUT

logger = logging.getLogger(__name__)

# Per-tool semaphores: 1 concurrent execution per tool
_tool_locks: dict[str, asyncio.Semaphore] = {}


def _get_lock(tool_name: str) -> asyncio.Semaphore:
    if tool_name not in _tool_locks:
        _tool_locks[tool_name] = asyncio.Semaphore(1)
    return _tool_locks[tool_name]


class BaseToolRunner:
    """Base class for all tool runners with caching and rate limiting."""

    tool_name: str = "base"
    cache_ttl: int = 300  # seconds

    def __init__(self):
        self._cache: dict[str, tuple[float, Any]] = {}

    def _cache_key(self, *args: str) -> str:
        raw = f"{self.tool_name}:{'|'.join(str(a) for a in args)}"
        return hashlib.md5(raw.encode()).hexdigest()

    def _get_cached(self, key: str) -> Optional[Any]:
        if key in self._cache:
            ts, data = self._cache[key]
            if time.time() - ts < self.cache_ttl:
                return data
            del self._cache[key]
        return None

    def _set_cached(self, key: str, data: Any):
        self._cache[key] = (time.time(), data)

    async def run_subprocess(self, cmd: list[str], timeout: int = TOOL_TIMEOUT) -> tuple[int, str, str]:
        """Run a subprocess with timeout. Returns (returncode, stdout, stderr)."""
        sem = _get_lock(self.tool_name)
        async with sem:
            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
                return proc.returncode or 0, stdout.decode(errors="replace"), stderr.decode(errors="replace")
            except asyncio.TimeoutError:
                try:
                    proc.kill()
                except Exception:
                    pass
                return -1, "", f"Timeout after {timeout}s"
            except FileNotFoundError:
                return -2, "", f"Tool binary not found: {cmd[0]}"
            except Exception as e:
                return -3, "", str(e)

    def save_result(self, filename: str, data: Any) -> str:
        """Save result to the shared results directory."""
        path = os.path.join(RESULTS_DIR, filename)
        with open(path, "w") as f:
            json.dump(data, f, default=str)
        return path


# Job tracking for async scans
_jobs: dict[str, dict] = {}
_job_counter = 0
_MAX_JOBS = 200
_JOB_TTL = 3600  # prune completed jobs older than 1 hour


def _prune_jobs():
    """Remove completed/errored jobs older than _JOB_TTL to prevent unbounded growth."""
    if len(_jobs) <= _MAX_JOBS:
        return
    now = time.time()
    to_delete = [
        jid for jid, j in _jobs.items()
        if j["status"] in ("complete", "error") and now - j["created"] > _JOB_TTL
    ]
    for jid in to_delete:
        del _jobs[jid]


def create_job(tool: str, target: str) -> str:
    global _job_counter
    _prune_jobs()
    _job_counter += 1
    job_id = f"{tool}-{_job_counter}-{int(time.time())}"
    _jobs[job_id] = {
        "id": job_id,
        "tool": tool,
        "target": target,
        "status": "queued",
        "created": time.time(),
        "result": None,
        "error": None,
    }
    return job_id


def update_job(job_id: str, **kwargs):
    if job_id in _jobs:
        _jobs[job_id].update(kwargs)


def get_job(job_id: str) -> Optional[dict]:
    return _jobs.get(job_id)


def list_jobs() -> list[dict]:
    return list(_jobs.values())
