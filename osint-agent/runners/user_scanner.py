"""User Scanner runner — wraps user-scanner library for email/username OSINT
and Hudson Rock infostealer intelligence.

Email scan: checks 107 platforms for account registration
Username scan: checks 91 platforms for account existence
Hudson Rock: queries infostealer breach database
"""

import asyncio
import logging
from typing import Any

import httpx

from runners.base import BaseToolRunner

logger = logging.getLogger(__name__)


def _import_engine():
    """Lazy import to avoid failure if user-scanner not installed."""
    from user_scanner.core.engine import check_all, check_category
    return check_all, check_category


class UserScannerRunner(BaseToolRunner):
    tool_name = "user_scanner"
    cache_ttl = 600  # 10 min cache

    async def scan_email(self, email: str) -> dict:
        """Scan email across 107 platforms for registrations."""
        cache_key = self._cache_key("email", email)
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        try:
            check_all, _ = _import_engine()
            results = await check_all(email, is_email=True)
            output = self._format_results(results, email, "email")
        except Exception as e:
            logger.error(f"User scanner email scan failed: {e}")
            output = {"status": "error", "error": str(e), "target": email, "scan_type": "email"}

        self._set_cached(cache_key, output)
        self.save_result(f"user_scanner_email_{email.replace('@', '_at_')}.json", output)
        return output

    async def scan_username(self, username: str) -> dict:
        """Scan username across 91 platforms for account existence."""
        cache_key = self._cache_key("username", username)
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        try:
            check_all, _ = _import_engine()
            results = await check_all(username, is_email=False)
            output = self._format_results(results, username, "username")
        except Exception as e:
            logger.error(f"User scanner username scan failed: {e}")
            output = {"status": "error", "error": str(e), "target": username, "scan_type": "username"}

        self._set_cached(cache_key, output)
        self.save_result(f"user_scanner_username_{username}.json", output)
        return output

    async def hudson_rock_lookup(self, target: str, is_email: bool = False) -> dict:
        """Query Hudson Rock infostealer API (non-interactive, no prompt)."""
        cache_key = self._cache_key("hudson", target)
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        base_url = "https://cavalier.hudsonrock.com/api/json/v2/osint-tools/"
        endpoint = "search-by-email" if is_email else "search-by-username"
        param = "email" if is_email else "username"
        url = f"{base_url}{endpoint}?{param}={target}"

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url)
                if response.status_code == 200:
                    data = response.json()
                    stealers = data.get("stealers", [])
                    output = {
                        "status": "ok",
                        "target": target,
                        "type": param,
                        "infections_found": len(stealers),
                        "stealers": stealers,
                        "attribution": "Data provided by Hudson Rock (https://www.hudsonrock.com)",
                    }
                elif response.status_code == 404:
                    output = {"status": "ok", "target": target, "type": param,
                              "infections_found": 0, "stealers": []}
                else:
                    output = {"status": "error", "error": f"HTTP {response.status_code}"}
        except Exception as e:
            logger.warning(f"Hudson Rock lookup failed: {e}")
            output = {"status": "error", "error": str(e)}

        self._set_cached(cache_key, output)
        return output

    def _format_results(self, results: list, target: str, scan_type: str) -> dict:
        """Convert list of Result objects to a serializable summary dict."""
        all_results = []
        for r in results:
            try:
                all_results.append(r.as_dict())
            except Exception:
                pass

        found = [r for r in all_results if r.get("status") in ("Registered", "Found", "Taken")]
        not_found = [r for r in all_results if r.get("status") in ("Not Registered", "Not Found", "Available")]
        errors = [r for r in all_results if r.get("status") == "Error"]

        # Group found results by category
        by_category = {}
        for r in found:
            cat = r.get("category", "Unknown")
            by_category.setdefault(cat, []).append(r)

        return {
            "status": "ok",
            "target": target,
            "scan_type": scan_type,
            "total_checked": len(all_results),
            "total_found": len(found),
            "total_not_found": len(not_found),
            "total_errors": len(errors),
            "found": found,
            "by_category": by_category,
        }
