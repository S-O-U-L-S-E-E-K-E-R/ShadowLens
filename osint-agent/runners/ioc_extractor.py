"""IOC (Indicator of Compromise) extraction + Certificate transparency lookup.

Features:
  - Extract IPs, domains, emails, URLs, hashes from any text
  - crt.sh certificate transparency subdomain discovery
  - SSL certificate info retrieval
"""

import logging
import re
import socket
import ssl
from typing import Any

import httpx

from runners.base import BaseToolRunner

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# IOC regex patterns
# ---------------------------------------------------------------------------
IP_PATTERN = re.compile(
    r"\b(?:(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\b"
)
EMAIL_PATTERN = re.compile(
    r"\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b"
)
URL_PATTERN = re.compile(
    r"\bhttps?://[^\s<>'\"()]+", re.IGNORECASE
)
HASH_PATTERN = re.compile(
    r"\b(?:[a-fA-F0-9]{32}|[a-fA-F0-9]{40}|[a-fA-F0-9]{64})\b"
)
DOMAIN_PATTERN = re.compile(
    r"\b(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}\b"
)
# CVE pattern
CVE_PATTERN = re.compile(
    r"\bCVE-\d{4}-\d{4,}\b", re.IGNORECASE
)


def extract_iocs(text: str) -> dict:
    """Extract all IOCs from a block of text.

    Returns dict with keys: ips, domains, emails, urls, hashes, cves
    Each value is a deduplicated list.
    """
    if not text:
        return {"ips": [], "domains": [], "emails": [], "urls": [], "hashes": [], "cves": []}

    # Extract URLs first (strip trailing punctuation)
    urls = set()
    for m in URL_PATTERN.finditer(text):
        url = m.group(0).rstrip(".,;:!?)]}")
        urls.add(url)

    emails = set(EMAIL_PATTERN.findall(text))
    ips = set(IP_PATTERN.findall(text))
    hashes = {h.lower() for h in HASH_PATTERN.findall(text)}
    cves = {c.upper() for c in CVE_PATTERN.findall(text)}

    # Domains: exclude emails and URL hostnames (already captured)
    email_domains = {e.split("@")[1].lower() for e in emails}
    url_hosts = set()
    for u in urls:
        try:
            host = u.split("//", 1)[1].split("/", 1)[0].split(":")[0].lower()
            url_hosts.add(host)
        except IndexError:
            pass

    domains = set()
    for m in DOMAIN_PATTERN.finditer(text):
        d = m.group(0).lower().rstrip(".")
        if d not in email_domains and d not in url_hosts and len(d) > 4:
            domains.add(d)

    # Filter out private/loopback IPs
    public_ips = set()
    for ip in ips:
        octets = ip.split(".")
        first = int(octets[0])
        if first in (0, 10, 127, 169, 224, 240, 255):
            continue
        if first == 172 and 16 <= int(octets[1]) <= 31:
            continue
        if first == 192 and int(octets[1]) == 168:
            continue
        public_ips.add(ip)

    return {
        "ips": sorted(public_ips),
        "domains": sorted(domains),
        "emails": sorted(emails),
        "urls": sorted(urls),
        "hashes": sorted(hashes),
        "cves": sorted(cves),
        "total": len(public_ips) + len(domains) + len(emails) + len(urls) + len(hashes) + len(cves),
    }


class IocExtractorRunner(BaseToolRunner):
    tool_name = "ioc_extractor"
    cache_ttl = 600

    async def extract_from_text(self, text: str) -> dict:
        """Extract IOCs from arbitrary text."""
        return extract_iocs(text)

    async def cert_transparency(self, domain: str, limit: int = 200) -> dict:
        """Query crt.sh for subdomains via certificate transparency logs."""
        cache_key = self._cache_key("crt", domain)
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(
                    f"https://crt.sh/?q=%25.{domain}&output=json"
                )
                resp.raise_for_status()
                records = resp.json()

            subdomains = set()
            for record in records:
                cn = record.get("common_name", "").lower().strip()
                if cn and cn.endswith(f".{domain}") and not cn.startswith("*") and cn != domain:
                    subdomains.add(cn)
                # Also check name_value for SANs
                nv = record.get("name_value", "")
                for name in nv.split("\n"):
                    name = name.strip().lower()
                    if name and name.endswith(f".{domain}") and not name.startswith("*") and name != domain:
                        subdomains.add(name)

            sorted_subs = sorted(subdomains)[:limit]
            output = {
                "status": "ok",
                "domain": domain,
                "subdomains": sorted_subs,
                "total": len(sorted_subs),
                "source": "crt.sh",
            }
        except httpx.TimeoutException:
            output = {"status": "error", "error": "crt.sh timeout", "domain": domain, "subdomains": []}
        except Exception as e:
            output = {"status": "error", "error": str(e), "domain": domain, "subdomains": []}

        self._set_cached(cache_key, output)
        return output

    async def ssl_cert_info(self, domain: str) -> dict:
        """Retrieve SSL certificate details from a domain."""
        cache_key = self._cache_key("ssl", domain)
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        try:
            ctx = ssl.create_default_context()
            with ctx.wrap_socket(socket.socket(socket.AF_INET), server_hostname=domain) as sock:
                sock.settimeout(10)
                sock.connect((domain, 443))
                cert = sock.getpeercert()

            def extract_field(data, key):
                if not data:
                    return ""
                for item in data:
                    for k, v in item:
                        if k == key:
                            return v
                return ""

            subject = cert.get("subject", ())
            issuer = cert.get("issuer", ())
            sans = [entry[1] for entry in cert.get("subjectAltName", ()) if entry[0] == "DNS"]

            output = {
                "status": "ok",
                "domain": domain,
                "subject_cn": extract_field(subject, "commonName"),
                "subject_org": extract_field(subject, "organizationName"),
                "issuer_cn": extract_field(issuer, "commonName"),
                "issuer_org": extract_field(issuer, "organizationName"),
                "serial_number": cert.get("serialNumber", ""),
                "not_before": cert.get("notBefore", ""),
                "not_after": cert.get("notAfter", ""),
                "sans": sans,
                "san_count": len(sans),
            }
        except socket.timeout:
            output = {"status": "error", "error": "Connection timed out", "domain": domain}
        except socket.gaierror:
            output = {"status": "error", "error": "DNS resolution failed", "domain": domain}
        except ssl.SSLError as e:
            output = {"status": "error", "error": f"SSL error: {e}", "domain": domain}
        except ConnectionRefusedError:
            output = {"status": "error", "error": "Connection refused (port 443)", "domain": domain}
        except Exception as e:
            output = {"status": "error", "error": str(e), "domain": domain}

        self._set_cached(cache_key, output)
        return output
