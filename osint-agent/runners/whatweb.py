"""WhatWeb technology detection runner."""

import json
import logging
import os

from config import TOOL_PATHS, TOOL_TIMEOUT
from runners.base import BaseToolRunner

logger = logging.getLogger(__name__)


class WhatWebRunner(BaseToolRunner):
    tool_name = "whatweb"
    cache_ttl = 600

    async def analyze(self, target: str) -> dict:
        """Run WhatWeb against a target URL."""
        cache_key = self._cache_key(target)
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        whatweb_path = TOOL_PATHS.get("whatweb", "whatweb")
        if not os.path.isfile(whatweb_path):
            return {"status": "unavailable", "data": []}

        cmd = [whatweb_path, "--log-json=-", "-q", target]
        returncode, stdout, stderr = await self.run_subprocess(cmd, timeout=TOOL_TIMEOUT)

        if returncode not in (0, None):
            logger.warning(f"WhatWeb exited with code {returncode}: {stderr[:200]}")
            if not stdout.strip():
                return {"status": "error", "data": [], "error": f"WhatWeb failed: {stderr[:200]}"}

        results = []
        for line in stdout.strip().split("\n"):
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
                results.append(obj)
            except json.JSONDecodeError as e:
                logger.debug(f"WhatWeb JSON parse error: {e}")
                continue

        result = {"status": "ok", "data": results}
        self._set_cached(cache_key, result)
        return result
