"""Google OSINT — unauthenticated Google intelligence gathering.

Features:
  - Email registration check (is email on Google?)
  - BSSID geolocation (WiFi MAC → coordinates via Google Geolocation API)
  - Digital Asset Links (website ↔ Android app associations)

No Google account/authentication required.
"""

import json
import logging
from typing import Any

import httpx

from runners.base import BaseToolRunner

logger = logging.getLogger(__name__)

# Google Geolocation API key (public, embedded in Google Maps JS samples)
_GEOLOCATION_API_KEY = "AIzaSyB41DRUbKWJHPxaFjMAwdrzWzbVKartNGg"


class GoogleOsintRunner(BaseToolRunner):
    tool_name = "google_osint"
    cache_ttl = 600

    async def check_google_email(self, email: str) -> dict:
        """Check if an email address is registered on Google (Gmail, Workspace, etc.).

        Uses the gxlu endpoint — no authentication needed.
        Returns True if the email has a Google account.
        """
        cache_key = self._cache_key("email", email)
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        try:
            async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
                resp = await client.get(
                    "https://mail.google.com/mail/gxlu",
                    params={"email": email},
                )
                registered = "Set-Cookie" in resp.headers
                output = {
                    "status": "ok",
                    "email": email,
                    "google_registered": registered,
                    "source": "google_gxlu",
                }
        except Exception as e:
            logger.warning(f"Google email check failed: {e}")
            output = {"status": "error", "error": str(e), "email": email}

        self._set_cached(cache_key, output)
        return output

    async def geolocate_bssid(self, bssid: str) -> dict:
        """Geolocate a WiFi access point by its BSSID (MAC address).

        Uses Google's Geolocation API with a public API key.
        Returns lat/lon/accuracy or error.
        """
        cache_key = self._cache_key("bssid", bssid)
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        try:
            payload = {
                "considerIp": False,
                "wifiAccessPoints": [
                    {"macAddress": "00:25:9c:cf:1c:ad"},  # Reference AP
                    {"macAddress": bssid},
                ],
            }
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"https://www.googleapis.com/geolocation/v1/geolocate?key={_GEOLOCATION_API_KEY}",
                    json=payload,
                    headers={
                        "Content-Type": "application/json",
                        "Referer": "https://geo-devrel-javascript-samples.web.app",
                        "Origin": "https://geo-devrel-javascript-samples.web.app",
                    },
                )
                data = resp.json()

                if "error" in data:
                    output = {
                        "status": "error",
                        "error": data["error"].get("message", "Unknown error"),
                        "bssid": bssid,
                    }
                else:
                    location = data.get("location", {})
                    output = {
                        "status": "ok",
                        "bssid": bssid,
                        "lat": location.get("lat"),
                        "lon": location.get("lng"),
                        "accuracy_meters": data.get("accuracy"),
                        "source": "google_geolocation",
                    }
        except Exception as e:
            logger.warning(f"Google BSSID geolocation failed: {e}")
            output = {"status": "error", "error": str(e), "bssid": bssid}

        self._set_cached(cache_key, output)
        return output

    async def digital_asset_links(self, website: str = "", android_package: str = "") -> dict:
        """Query Google Digital Asset Links to find web ↔ Android app associations.

        - Provide website (e.g. "https://example.com") to find linked Android apps
        - Provide android_package (e.g. "com.example.app") to find linked websites
        - No authentication required.
        """
        if not website and not android_package:
            return {"status": "error", "error": "Provide either website or android_package"}

        cache_key = self._cache_key("dal", website or android_package)
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        try:
            params = {}
            if website:
                if not website.startswith("http"):
                    website = f"https://{website}"
                params["source.web.site"] = website
            elif android_package:
                params["source.androidApp.packageName"] = android_package
                params["source.androidApp.certificate.sha256Fingerprint"] = ""

            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    "https://digitalassetlinks.googleapis.com/v1/statements:list",
                    params=params,
                )
                data = resp.json()

                if "error" in data:
                    output = {
                        "status": "error",
                        "error": data["error"].get("message", "Unknown"),
                        "query": website or android_package,
                    }
                else:
                    statements = data.get("statements", [])
                    links = []
                    for stmt in statements:
                        target = stmt.get("target", {})
                        link = {"relation": stmt.get("relation", "")}
                        if "androidApp" in target:
                            app = target["androidApp"]
                            link["type"] = "android_app"
                            link["package"] = app.get("packageName", "")
                            cert = app.get("certificate", {})
                            link["cert_sha256"] = cert.get("sha256Fingerprint", "")
                        elif "web" in target:
                            link["type"] = "website"
                            link["site"] = target["web"].get("site", "")
                        links.append(link)

                    output = {
                        "status": "ok",
                        "query": website or android_package,
                        "query_type": "website" if website else "android_package",
                        "total": len(links),
                        "links": links,
                        "source": "google_digital_asset_links",
                    }
        except Exception as e:
            logger.warning(f"Digital Asset Links query failed: {e}")
            output = {"status": "error", "error": str(e), "query": website or android_package}

        self._set_cached(cache_key, output)
        return output
