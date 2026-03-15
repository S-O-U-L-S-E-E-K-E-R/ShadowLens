"""Comprehensive OSINT deep search runner — auto-detects input type and runs
the appropriate combination of tools (Sherlock, h8mail, whois, theHarvester,
SpiderFoot, dmitry, subfinder, dnsrecon, dig, nmap, shodan, emailharvester,
ip-api geolocation) to gather intelligence on a target."""

import asyncio
import csv as csv_mod
import json
import logging
import os
import re
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from config import TOOL_PATHS, TOOL_TIMEOUT
from runners.base import BaseToolRunner
from runners.harvester import HarvesterRunner
from runners.spiderfoot import SpiderFootRunner
from runners.person_search import PersonSearchRunner
from runners.user_scanner import UserScannerRunner

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Input-type detection patterns
# ---------------------------------------------------------------------------
_EMAIL_RE = re.compile(
    r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$'
)
_IPV4_RE = re.compile(
    r'^(\d{1,3}\.){3}\d{1,3}$'
)
_PHONE_RE = re.compile(
    r'^[\+]?[\d\s\-\(\)]{7,20}$'
)
_DOMAIN_RE = re.compile(
    r'^[a-zA-Z0-9]([a-zA-Z0-9\-]*[a-zA-Z0-9])?'
    r'(\.[a-zA-Z0-9]([a-zA-Z0-9\-]*[a-zA-Z0-9])?)*'
    r'\.[a-zA-Z]{2,}$'
)
_USERNAME_RE = re.compile(
    r'^@?[a-zA-Z0-9_\-]{1,64}$'
)

# Characters permitted in subprocess arguments (strict allowlist).
_SAFE_CHARS_RE = re.compile(r'^[a-zA-Z0-9@._+\-:/\s\(\)]+$')

# Slow-tool timeout (whois, dmitry, spiderfoot)
_SLOW_TIMEOUT = 120
# Fast-tool timeout (sherlock, h8mail)
_FAST_TIMEOUT = 60


def _sanitize(value: str) -> str:
    """Sanitize a value for safe subprocess usage.

    Raises ValueError if the input contains unexpected characters that could
    be used for command injection.
    """
    value = value.strip()
    if not value:
        raise ValueError("Empty input")
    if len(value) > 256:
        raise ValueError("Input too long (max 256 chars)")
    if not _SAFE_CHARS_RE.match(value):
        raise ValueError(f"Input contains disallowed characters: {value!r}")
    # Block obvious shell metacharacters even if regex above should catch them
    for bad in (";", "&", "|", "`", "$", "{", "}", "<", ">", "!", "\n", "\r"):
        if bad in value:
            raise ValueError(f"Input contains shell metacharacter: {bad!r}")
    return value


class DeepSearchRunner(BaseToolRunner):
    """Unified OSINT search runner.

    Accepts any query string, auto-detects its type (email, username, phone,
    IP, domain, or general name) and dispatches the right set of tools.
    """

    tool_name = "deep_search"
    cache_ttl = 600  # 10-minute result cache

    def __init__(self):
        super().__init__()
        self._harvester = HarvesterRunner()
        self._spiderfoot = SpiderFootRunner()
        self._person_search = PersonSearchRunner()
        self._user_scanner = UserScannerRunner()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def search(self, query: str) -> dict:
        """Run a comprehensive OSINT search for *query*.

        Returns a unified result dict regardless of query type.
        """
        query = query.strip()
        if not query:
            return self._empty_result(query, "unknown", error="Empty query")

        # Check cache
        cache_key = self._cache_key(query)
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        query_type = await self._detect_type(query)

        try:
            sanitized = _sanitize(query.lstrip("@"))
        except ValueError as exc:
            return self._empty_result(query, query_type, error=str(exc))

        tools_run: list[str] = []
        results: dict[str, Any] = {}
        locations: list[dict] = []

        # Dispatch based on detected type
        if query_type == "email":
            results, tools_run, locations = await self._search_email(sanitized)
        elif query_type == "username":
            username = query.lstrip("@")
            results, tools_run = await self._search_username(username)
        elif query_type == "phone":
            results, tools_run, locations = await self._search_phone(sanitized)
        elif query_type == "ip":
            results, tools_run, locations = await self._search_ip(sanitized)
        elif query_type == "domain":
            results, tools_run, locations = await self._search_domain(sanitized)
        else:  # name / general
            results, tools_run, locations = await self._search_name(sanitized)

        # Cross-reference: scan results for new leads and auto-run them
        cross_refs = await self._cross_reference(query, query_type, results)

        summary = self._build_summary(query, query_type, results)

        output = {
            "query": query,
            "type": query_type,
            "tools_run": tools_run,
            "results": results,
            "locations": locations,
            "summary": summary,
            "cross_references": cross_refs,
        }

        self._set_cached(cache_key, output)
        self.save_result(f"deep_search_{re.sub(r'[^a-zA-Z0-9]', '_', query)[:60]}.json", output)
        return output

    # ------------------------------------------------------------------
    # Type detection
    # ------------------------------------------------------------------

    async def _detect_type(self, query: str) -> str:
        """Classify *query* into one of: email, username, phone, ip, domain, name."""
        q = query.strip()

        if _EMAIL_RE.match(q):
            return "email"

        if _IPV4_RE.match(q):
            # Validate each octet is 0-255
            parts = q.split(".")
            if all(0 <= int(p) <= 255 for p in parts):
                return "ip"

        if _PHONE_RE.match(q) and sum(c.isdigit() for c in q) >= 7:
            return "phone"

        if q.startswith("@"):
            return "username"

        if _DOMAIN_RE.match(q):
            return "domain"

        # If it looks like a plain username (no spaces, short, alphanumeric)
        if _USERNAME_RE.match(q) and " " not in q and "." not in q:
            return "username"

        return "name"

    # ------------------------------------------------------------------
    # Per-type search orchestrators
    # ------------------------------------------------------------------

    async def _search_email(self, email: str) -> tuple[dict, list[str], list[dict]]:
        domain = email.split("@", 1)[1] if "@" in email else email
        # Run all email OSINT tools in parallel
        h8, harvester, emailhv, hibp, holehe, uscan, hudson = await asyncio.gather(
            self._run_h8mail(email),
            self._run_harvester(domain),
            self._run_emailharvester(domain),
            self._run_hibp(email),
            self._run_holehe(email),
            self._run_user_scanner_email(email),
            self._run_hudson_rock(email, is_email=True),
        )
        results = {"hibp": hibp, "h8mail": h8, "holehe": holehe,
                   "harvester": harvester, "emailharvester": emailhv,
                   "user_scanner": uscan, "hudson_rock": hudson}
        tools_run = ["hibp", "h8mail", "holehe", "harvester", "emailharvester",
                     "user_scanner", "hudson_rock"]
        # Geolocate the email domain's server
        locations: list[dict] = []
        try:
            geo = await self._run_ip_geolocation(domain)
            if geo.get("lat") and geo.get("lon"):
                locations.append({
                    "lat": geo["lat"], "lon": geo["lon"],
                    "label": f"{domain} mail server — {geo.get('city', '')}, {geo.get('country', '')}",
                    "source": "ip-api",
                })
        except Exception:
            pass
        return results, tools_run, locations

    async def _search_username(self, username: str) -> tuple[dict, list[str]]:
        sherlock, uscan, hudson = await asyncio.gather(
            self._run_sherlock(username),
            self._run_user_scanner_username(username),
            self._run_hudson_rock(username, is_email=False),
        )
        return {"sherlock": sherlock, "user_scanner": uscan, "hudson_rock": hudson}, \
               ["sherlock", "user_scanner", "hudson_rock"]

    async def _search_phone(self, phone: str) -> tuple[dict, list[str], list[dict]]:
        """Phone number lookup via PhoneInfoga + phonenumbers + numverify."""
        # Run all phone tools in parallel
        phoneinfoga_task = self._run_phoneinfoga(phone)
        phonenumbers_task = self._run_phonenumbers(phone)
        numverify_task = self._run_numverify(phone)
        phoneinfoga_res, phonenumbers_res, numverify_res = await asyncio.gather(
            phoneinfoga_task, phonenumbers_task, numverify_task
        )
        results = {
            "phoneinfoga": phoneinfoga_res,
            "phonenumbers": phonenumbers_res,
            "numverify": numverify_res,
        }
        tools_run = ["phoneinfoga", "phonenumbers", "numverify"]
        # Extract location from numverify or phonenumbers region data
        locations: list[dict] = []
        loc_query = numverify_res.get("location") or phonenumbers_res.get("country") or ""
        if loc_query:
            try:
                geo = await self._geocode_string(loc_query)
                if geo:
                    locations.append({
                        "lat": geo["lat"], "lon": geo["lon"],
                        "label": f"Phone region: {loc_query}",
                        "source": "phonenumbers",
                    })
            except Exception:
                pass
        return results, tools_run, locations

    @staticmethod
    def _is_private_ip(ip: str) -> bool:
        """Check if an IP is RFC1918 private or link-local."""
        parts = ip.split(".")
        if len(parts) != 4:
            return False
        try:
            a, b = int(parts[0]), int(parts[1])
        except ValueError:
            return False
        return (a == 10 or (a == 172 and 16 <= b <= 31) or
                (a == 192 and b == 168) or a == 127 or a == 169 and b == 254)

    async def _search_ip(self, ip: str) -> tuple[dict, list[str], list[dict]]:
        from config import HOST_LAT, HOST_LON

        # Private/local IPs — use host location, only run nmap
        if self._is_private_ip(ip):
            nmap_res = await self._run_nmap_quick(ip)
            locations = []
            if HOST_LAT and HOST_LON:
                locations.append({
                    "lat": HOST_LAT, "lon": HOST_LON,
                    "label": f"{ip} — Local Network",
                    "source": "host-gps",
                })
            results = {"nmap": nmap_res, "geolocation": {"note": "Private IP — using host location"},
                       "whois": {"note": "RFC1918 private address"}, "shodan": {}}
            return results, ["nmap"], locations

        # Public IP — run whois + nmap + ip geolocation + shodan in parallel
        whois_res, geo, nmap_res, shodan_res = await asyncio.gather(
            self._run_whois(ip), self._run_ip_geolocation(ip),
            self._run_nmap_quick(ip), self._run_shodan(ip),
        )
        locations = []
        if geo.get("lat") and geo.get("lon"):
            locations.append({
                "lat": geo["lat"], "lon": geo["lon"],
                "label": f"{ip} — {geo.get('city', '')}, {geo.get('country', '')}",
                "source": "ip-api",
            })
        results = {"whois": whois_res, "geolocation": geo, "nmap": nmap_res, "shodan": shodan_res}
        tools_run = ["whois", "geolocation", "nmap", "shodan"]
        return results, tools_run, locations

    async def _search_domain(self, domain: str) -> tuple[dict, list[str], list[dict]]:
        # Run whois + harvester + dmitry + subfinder + dig + dnsrecon in parallel
        whois_task = self._run_whois(domain)
        harvester_task = self._run_harvester(domain)
        dmitry_task = self._run_dmitry(domain)
        subfinder_task = self._run_subfinder(domain)
        dig_task = self._run_dig(domain)
        dnsrecon_task = self._run_dnsrecon(domain)
        whois_res, harvester, dmitry, subfinder, dig_res, dnsrecon = await asyncio.gather(
            whois_task, harvester_task, dmitry_task,
            subfinder_task, dig_task, dnsrecon_task,
        )
        locations = self._extract_locations_from_whois(whois_res, "whois")
        # Try to geolocate the domain's A record
        if dig_res.get("a_records"):
            first_ip = dig_res["a_records"][0]
            geo = await self._run_ip_geolocation(first_ip)
            if geo.get("lat") and geo.get("lon"):
                locations = [{
                    "lat": geo["lat"], "lon": geo["lon"],
                    "label": f"{domain} ({first_ip}) — {geo.get('city', '')}, {geo.get('country', '')}",
                    "source": "ip-api",
                }]
        results = {
            "whois": whois_res, "harvester": harvester, "dmitry": dmitry,
            "subfinder": subfinder, "dig": dig_res, "dnsrecon": dnsrecon,
        }
        tools_run = ["whois", "harvester", "dmitry", "subfinder", "dig", "dnsrecon"]
        return results, tools_run, locations

    async def _search_name(self, name: str) -> tuple[dict, list[str], list[dict]]:
        # Run full person search pipeline — public records, maigret, sherlock,
        # corporate records, court records, social profiles — all in parallel
        person_result = await self._person_search.search(name)
        results = person_result.get("results", {})
        tools_run = person_result.get("tools_run", [])
        locations = person_result.get("locations", [])
        return results, tools_run, locations

    # ------------------------------------------------------------------
    # Individual tool runners
    # ------------------------------------------------------------------

    async def _run_sherlock(self, username: str) -> dict:
        """Run Sherlock username enumeration and parse JSON output."""
        try:
            username = _sanitize(username)
        except ValueError as exc:
            return {"error": str(exc), "accounts_found": [], "total": 0}

        sherlock_path = TOOL_PATHS.get("sherlock", "/usr/bin/sherlock")
        if not os.path.isfile(sherlock_path):
            return {"error": "sherlock not installed", "accounts_found": [], "total": 0}

        # Use a temp dir for CSV output
        with tempfile.TemporaryDirectory(prefix="sherlock_") as tmpdir:
            try:
                cmd = [
                    sherlock_path, username,
                    "--folderoutput", tmpdir,
                    "--csv",
                    "--print-found",
                    "--timeout", "20",
                    "--no-color",
                ]
                returncode, stdout, stderr = await self.run_subprocess(cmd, timeout=_FAST_TIMEOUT)

                accounts: list[dict] = []

                # Parse CSV output file (sherlock creates username.csv)
                csv_path = os.path.join(tmpdir, f"{username}.csv")
                if os.path.isfile(csv_path):
                    try:
                        import csv as csv_mod
                        with open(csv_path) as f:
                            reader = csv_mod.DictReader(f)
                            for row in reader:
                                url = row.get("url", row.get("URL", ""))
                                site = row.get("name", row.get("Name", row.get("site", "")))
                                if url:
                                    accounts.append({"site": site, "url": url})
                    except Exception:
                        pass

                # Fallback: parse stdout for "[+]" lines
                # Format: "[+] SiteName: https://url..."
                if not accounts and stdout:
                    for line in stdout.splitlines():
                        line = line.strip()
                        if not line.startswith("[+]"):
                            continue
                        content = line[4:].strip()
                        if ": http" in content:
                            idx = content.index(": http")
                            site = content[:idx].strip()
                            url = content[idx + 2:].strip()
                            accounts.append({"site": site, "url": url})
                        elif ": " in content:
                            parts = content.split(": ", 1)
                            accounts.append({"site": parts[0].strip(), "url": parts[1].strip()})

                return {
                    "accounts_found": accounts,
                    "total": len(accounts),
                }
            except Exception as exc:
                logger.warning(f"Sherlock error for {username}: {exc}")
                return {"error": str(exc), "accounts_found": [], "total": 0}

    async def _run_h8mail(self, email: str) -> dict:
        """Run h8mail email breach lookup and parse stdout."""
        try:
            email = _sanitize(email)
        except ValueError as exc:
            return {"error": str(exc), "breaches": [], "total": 0}

        h8mail_path = "/usr/bin/h8mail"
        if not os.path.isfile(h8mail_path):
            return {"error": "h8mail not installed", "breaches": [], "total": 0}

        try:
            cmd = [h8mail_path, "-t", email]
            returncode, stdout, stderr = await self.run_subprocess(cmd, timeout=_FAST_TIMEOUT)

            breaches: list[dict] = []

            if stdout:
                current_source = ""
                for line in stdout.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    # h8mail outputs breach sources with headers and indented results
                    if line.startswith("[") and "]" in line:
                        # Extract source tag like [breach-parse], [hunter.io], etc.
                        tag_end = line.index("]")
                        current_source = line[1:tag_end]
                        remainder = line[tag_end + 1:].strip()
                        if remainder:
                            breaches.append({
                                "source": current_source,
                                "data": remainder,
                            })
                    elif ":" in line and current_source:
                        breaches.append({
                            "source": current_source,
                            "data": line,
                        })

            return {
                "breaches": breaches,
                "total": len(breaches),
            }
        except Exception as exc:
            logger.warning(f"h8mail error for {email}: {exc}")
            return {"error": str(exc), "breaches": [], "total": 0}

    async def _run_hibp(self, email: str) -> dict:
        """Query Have I Been Pwned API for breach data on an email address."""
        hibp_key = os.environ.get("HIBP_API_KEY", "")
        if not hibp_key:
            return {"note": "Set HIBP_API_KEY env for breach lookups via haveibeenpwned.com",
                    "breaches": [], "pastes": []}
        try:
            email = _sanitize(email)
            # Breached accounts
            url = f"https://haveibeenpwned.com/api/v3/breachedaccount/{urllib.parse.quote(email)}?truncateResponse=false"
            req = urllib.request.Request(url, headers={
                "User-Agent": "osint-agent/1.0",
                "hibp-api-key": hibp_key,
            })
            breaches = []
            try:
                resp = urllib.request.urlopen(req, timeout=10)
                data = json.loads(resp.read())
                for b in data:
                    breaches.append({
                        "name": b.get("Name", ""),
                        "domain": b.get("Domain", ""),
                        "breach_date": b.get("BreachDate", ""),
                        "pwn_count": b.get("PwnCount", 0),
                        "data_classes": b.get("DataClasses", []),
                        "is_verified": b.get("IsVerified", False),
                        "is_sensitive": b.get("IsSensitive", False),
                        "description": b.get("Description", "")[:200],
                    })
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    pass  # No breaches found — good news
                elif e.code == 401:
                    return {"error": "Invalid HIBP API key", "breaches": [], "pastes": []}
                elif e.code == 429:
                    return {"error": "HIBP rate limit exceeded", "breaches": [], "pastes": []}
                else:
                    return {"error": f"HIBP API error: {e.code}", "breaches": [], "pastes": []}

            # Paste accounts
            pastes = []
            try:
                paste_url = f"https://haveibeenpwned.com/api/v3/pasteaccount/{urllib.parse.quote(email)}"
                paste_req = urllib.request.Request(paste_url, headers={
                    "User-Agent": "osint-agent/1.0",
                    "hibp-api-key": hibp_key,
                })
                paste_resp = urllib.request.urlopen(paste_req, timeout=10)
                paste_data = json.loads(paste_resp.read())
                for p in paste_data[:20]:
                    pastes.append({
                        "source": p.get("Source", ""),
                        "title": p.get("Title", ""),
                        "date": p.get("Date", ""),
                        "email_count": p.get("EmailCount", 0),
                    })
            except urllib.error.HTTPError:
                pass  # 404 = no pastes, others = skip

            return {
                "breaches": breaches,
                "total_breaches": len(breaches),
                "pastes": pastes,
                "total_pastes": len(pastes),
            }
        except Exception as exc:
            logger.warning(f"HIBP error for {email}: {exc}")
            return {"error": str(exc), "breaches": [], "pastes": []}

    async def _run_holehe(self, email: str) -> dict:
        """Run holehe to check what services an email is registered on."""
        holehe_path = os.path.expanduser("~/.local/bin/holehe")
        if not os.path.isfile(holehe_path):
            holehe_path = "/usr/bin/holehe"
        if not os.path.isfile(holehe_path):
            return {"error": "holehe not installed", "registered_on": []}
        try:
            email = _sanitize(email)
            cmd = [holehe_path, email, "--no-color"]
            rc, stdout, stderr = await self.run_subprocess(cmd, timeout=90)
            registered = []
            for line in stdout.splitlines():
                line = line.strip()
                if "[+]" in line:
                    site = line.split("[+]")[-1].strip().split()[0]
                    if site:
                        registered.append(site)
            return {"registered_on": registered, "total": len(registered)}
        except Exception as exc:
            return {"error": str(exc), "registered_on": []}

    async def _run_user_scanner_email(self, email: str) -> dict:
        """Run user-scanner email registration scan (107 platforms)."""
        try:
            return await self._user_scanner.scan_email(email)
        except Exception as e:
            logger.warning(f"user-scanner email scan failed: {e}")
            return {"error": str(e)}

    async def _run_user_scanner_username(self, username: str) -> dict:
        """Run user-scanner username availability scan (91 platforms)."""
        try:
            return await self._user_scanner.scan_username(username)
        except Exception as e:
            logger.warning(f"user-scanner username scan failed: {e}")
            return {"error": str(e)}

    async def _run_hudson_rock(self, target: str, is_email: bool = False) -> dict:
        """Run Hudson Rock infostealer lookup."""
        try:
            return await self._user_scanner.hudson_rock_lookup(target, is_email)
        except Exception as e:
            logger.warning(f"Hudson Rock lookup failed: {e}")
            return {"error": str(e)}

    async def _run_whois(self, target: str) -> dict:
        """Run whois lookup and parse the output into structured fields."""
        try:
            target = _sanitize(target)
        except ValueError as exc:
            return {"error": str(exc)}

        whois_path = "/usr/bin/whois"
        if not os.path.isfile(whois_path):
            return {"error": "whois not installed"}

        try:
            cmd = [whois_path, target]
            returncode, stdout, stderr = await self.run_subprocess(cmd, timeout=_SLOW_TIMEOUT)

            if returncode not in (0, 1, 2) and not stdout:
                return {"error": f"whois failed (code {returncode}): {stderr[:200]}"}

            # Parse well-known whois fields
            parsed: dict[str, str] = {}
            field_map = {
                "registrar": ("Registrar:", "registrar"),
                "created": ("Creation Date:", "created"),
                "updated": ("Updated Date:", "updated"),
                "expires": ("Registry Expiry Date:", "Expiration Date:", "expires"),
                "name_servers": ("Name Server:", "nserver"),
                "registrant_org": ("Registrant Organization:", "org-name", "OrgName:"),
                "registrant_country": ("Registrant Country:", "Country:"),
                "registrant_city": ("Registrant City:", "City:"),
                "registrant_state": ("Registrant State/Province:", "State:"),
                "status": ("Domain Status:", "status"),
                "netname": ("NetName:", "netname"),
                "netrange": ("NetRange:", "inetnum"),
                "cidr": ("CIDR:",),
                "org_name": ("OrgName:", "org-name"),
                "description": ("descr:",),
            }

            name_servers: list[str] = []

            for line in stdout.splitlines():
                line_stripped = line.strip()
                if not line_stripped or line_stripped.startswith("%") or line_stripped.startswith("#"):
                    continue

                for field_key, markers in field_map.items():
                    for marker in markers:
                        if line_stripped.lower().startswith(marker.lower()):
                            value = line_stripped[len(marker):].strip()
                            if field_key == "name_servers":
                                name_servers.append(value.lower())
                            elif field_key not in parsed:
                                parsed[field_key] = value
                            break

            if name_servers:
                parsed["name_servers"] = ", ".join(sorted(set(name_servers)))

            parsed["raw_length"] = str(len(stdout))
            return parsed

        except Exception as exc:
            logger.warning(f"whois error for {target}: {exc}")
            return {"error": str(exc)}

    async def _run_dmitry(self, target: str) -> dict:
        """Run dmitry deep info gathering and parse output."""
        try:
            target = _sanitize(target)
        except ValueError as exc:
            return {"error": str(exc), "subdomains": [], "emails": []}

        dmitry_path = "/usr/bin/dmitry"
        if not os.path.isfile(dmitry_path):
            return {"error": "dmitry not installed", "subdomains": [], "emails": []}

        try:
            # -w whois, -i arin, -n netcraft, -s subdomains, -e emails, -p port scan
            cmd = [dmitry_path, "-winsep", target]
            returncode, stdout, stderr = await self.run_subprocess(cmd, timeout=_SLOW_TIMEOUT)

            subdomains: list[str] = []
            emails: list[str] = []
            ports: list[str] = []

            section = ""
            for line in stdout.splitlines():
                line_stripped = line.strip()

                # Section headers
                if "Searching for possible subdomain" in line:
                    section = "subdomains"
                    continue
                elif "Searching for possible email" in line:
                    section = "emails"
                    continue
                elif "Scanning TCP ports" in line or "PortScan" in line:
                    section = "ports"
                    continue

                if not line_stripped or line_stripped.startswith("-"):
                    continue

                if section == "subdomains" and line_stripped and "Found" not in line_stripped:
                    # Lines like "subdomain.example.com"
                    candidate = line_stripped.split()[0] if line_stripped.split() else ""
                    if candidate and "." in candidate:
                        subdomains.append(candidate)
                elif section == "emails" and "@" in line_stripped:
                    # Extract email from line
                    for word in line_stripped.split():
                        if "@" in word and "." in word:
                            emails.append(word.strip())
                elif section == "ports" and ("open" in line_stripped.lower() or "/tcp" in line_stripped):
                    ports.append(line_stripped)

            return {
                "subdomains": list(set(subdomains)),
                "emails": list(set(emails)),
                "ports": ports,
            }
        except Exception as exc:
            logger.warning(f"dmitry error for {target}: {exc}")
            return {"error": str(exc), "subdomains": [], "emails": []}

    async def _run_harvester(self, target: str) -> dict:
        """Delegate to the existing HarvesterRunner."""
        try:
            result = await self._harvester.run(target)
            data = result.get("data", {})
            return {
                "emails": data.get("emails", []),
                "hosts": data.get("hosts", []),
                "ips": data.get("ips", []),
            }
        except Exception as exc:
            logger.warning(f"theHarvester error for {target}: {exc}")
            return {"error": str(exc), "emails": [], "hosts": [], "ips": []}

    async def _run_spiderfoot(self, target: str) -> dict:
        """Delegate to the existing SpiderFootRunner (passive mode)."""
        try:
            result = await self._spiderfoot.run_scan(target, use_case="passive")
            if result.get("status") == "ok":
                data = result.get("data", {})
                findings = data.get("findings", {})
                return {
                    "emails": [e["data"] for e in findings.get("emails", [])],
                    "hostnames": [h["data"] for h in findings.get("hostnames", [])],
                    "ips": [i["data"] for i in findings.get("ips", [])],
                    "technologies": [t["data"] for t in findings.get("technologies", [])],
                    "social_media": [s["data"] for s in findings.get("social_media", [])],
                    "leaks": [l["data"] for l in findings.get("leaks", [])],
                    "total_events": data.get("total_events", 0),
                }
            return {"error": result.get("error", "SpiderFoot scan failed")}
        except Exception as exc:
            logger.warning(f"SpiderFoot error for {target}: {exc}")
            return {"error": str(exc)}

    async def _run_subfinder(self, domain: str) -> dict:
        """Run subfinder for fast subdomain enumeration."""
        subfinder_path = TOOL_PATHS.get("subfinder", "/usr/bin/subfinder")
        if not os.path.isfile(subfinder_path):
            return {"error": "subfinder not installed", "subdomains": []}
        try:
            domain = _sanitize(domain)
            cmd = [subfinder_path, "-d", domain, "-silent", "-timeout", "30"]
            rc, stdout, stderr = await self.run_subprocess(cmd, timeout=_FAST_TIMEOUT)
            subs = [line.strip() for line in stdout.splitlines() if line.strip() and "." in line.strip()]
            return {"subdomains": sorted(set(subs)), "total": len(set(subs))}
        except Exception as exc:
            return {"error": str(exc), "subdomains": []}

    async def _run_dig(self, domain: str) -> dict:
        """Run dig for DNS record lookup."""
        dig_path = "/usr/bin/dig"
        if not os.path.isfile(dig_path):
            return {"error": "dig not installed"}
        try:
            domain = _sanitize(domain)
            # Run A, MX, NS, TXT lookups in parallel
            tasks = []
            for rtype in ["A", "AAAA", "MX", "NS", "TXT", "CNAME", "SOA"]:
                tasks.append(self.run_subprocess([dig_path, domain, rtype, "+short"], timeout=15))
            results_raw = await asyncio.gather(*tasks)
            rtypes = ["A", "AAAA", "MX", "NS", "TXT", "CNAME", "SOA"]
            parsed = {}
            for rtype, (rc, stdout, stderr) in zip(rtypes, results_raw):
                records = [l.strip() for l in stdout.splitlines() if l.strip()]
                if records:
                    parsed[f"{rtype.lower()}_records"] = records
            return parsed
        except Exception as exc:
            return {"error": str(exc)}

    async def _run_dnsrecon(self, domain: str) -> dict:
        """Run dnsrecon for comprehensive DNS enumeration."""
        dnsrecon_path = "/usr/bin/dnsrecon"
        if not os.path.isfile(dnsrecon_path):
            return {"error": "dnsrecon not installed", "records": []}
        try:
            domain = _sanitize(domain)
            cmd = [dnsrecon_path, "-d", domain, "-t", "std", "--json", "/dev/stdout"]
            rc, stdout, stderr = await self.run_subprocess(cmd, timeout=_SLOW_TIMEOUT)
            records = []
            try:
                data = json.loads(stdout)
                if isinstance(data, list):
                    records = [{"type": r.get("type", ""), "name": r.get("name", ""),
                               "address": r.get("address", ""), "target": r.get("target", "")}
                              for r in data if isinstance(r, dict)]
            except json.JSONDecodeError:
                # Parse text output
                for line in stdout.splitlines():
                    line = line.strip()
                    if line and "[*]" in line:
                        records.append({"raw": line.replace("[*]", "").strip()})
            return {"records": records[:50], "total": len(records)}
        except Exception as exc:
            return {"error": str(exc), "records": []}

    async def _run_emailharvester(self, domain: str) -> dict:
        """Run emailharvester for email discovery."""
        eh_path = "/usr/bin/emailharvester"
        if not os.path.isfile(eh_path):
            return {"error": "emailharvester not installed", "emails": []}
        try:
            domain = _sanitize(domain)
            cmd = [eh_path, "-d", domain]
            rc, stdout, stderr = await self.run_subprocess(cmd, timeout=_FAST_TIMEOUT)
            emails = []
            for line in stdout.splitlines():
                line = line.strip()
                if "@" in line and "." in line:
                    # Extract email-like patterns
                    for word in re.findall(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}', line):
                        emails.append(word)
            return {"emails": sorted(set(emails)), "total": len(set(emails))}
        except Exception as exc:
            return {"error": str(exc), "emails": []}

    async def _run_ip_geolocation(self, ip: str) -> dict:
        """Geolocate an IP address using ip-api.com (free, no key)."""
        try:
            ip = _sanitize(ip)
            url = f"http://ip-api.com/json/{ip}?fields=status,country,regionName,city,lat,lon,isp,org,as,query"
            req = urllib.request.Request(url, headers={"User-Agent": "osint-agent/1.0"})
            resp = urllib.request.urlopen(req, timeout=8)
            data = json.loads(resp.read())
            if data.get("status") == "success":
                return {
                    "ip": data.get("query", ip),
                    "country": data.get("country", ""),
                    "region": data.get("regionName", ""),
                    "city": data.get("city", ""),
                    "lat": data.get("lat"),
                    "lon": data.get("lon"),
                    "isp": data.get("isp", ""),
                    "org": data.get("org", ""),
                    "asn": data.get("as", ""),
                }
            return {"error": "Geolocation failed", "ip": ip}
        except Exception as exc:
            return {"error": str(exc), "ip": ip}

    async def _run_nmap_quick(self, ip: str) -> dict:
        """Nmap scan — service detection, OS fingerprint, scripts, top 1000 ports."""
        nmap_path = TOOL_PATHS.get("nmap", "/usr/bin/nmap")
        if not os.path.isfile(nmap_path):
            return {"error": "nmap not installed", "ports": []}
        try:
            ip = _sanitize(ip)
            # -sV: service/version detection
            # -sC: default scripts (banner, ssl-cert, http-title, etc.)
            # --top-ports 1000: scan top 1000 ports
            # -T4: aggressive timing
            # --open: only show open ports
            # -oX -: XML output for structured parsing
            # Use sudo for SYN scan + OS detection if available
            import shutil
            has_sudo = shutil.which("sudo") is not None
            # Two-phase scan: fast port discovery, then version detect open ports
            if has_sudo:
                # Phase 1: fast SYN scan to find open ports
                cmd1 = ["sudo", nmap_path, "-sS", "--top-ports", "200",
                        "-T5", "--open", "-oG", "-", ip]
            else:
                cmd1 = [nmap_path, "-sT", "--top-ports", "200",
                        "-T5", "--open", "-oG", "-", ip]
            rc1, stdout1, _ = await self.run_subprocess(cmd1, timeout=30)
            # Parse grepable output for open ports
            open_ports = []
            for line in stdout1.splitlines():
                if "Ports:" in line:
                    import re as _re
                    open_ports = _re.findall(r'(\d+)/open', line)
            if not open_ports:
                # No open ports found — return fast with just OS guess
                return {"ports": [], "os": "", "total": 0}
            # Phase 2: version + OS detect only on the open ports found
            port_spec = ",".join(open_ports)
            if has_sudo:
                cmd = ["sudo", nmap_path, "-sS", "-sV", "-O",
                       "--version-intensity", "2",
                       "-p", port_spec, "-T4", "--open",
                       "--host-timeout", "60s", "-oX", "-", ip]
            else:
                cmd = [nmap_path, "-sT", "-sV",
                       "--version-intensity", "2",
                       "-p", port_spec, "-T4", "--open",
                       "--host-timeout", "60s", "-oX", "-", ip]
            rc, stdout, stderr = await self.run_subprocess(cmd, timeout=_SLOW_TIMEOUT)

            # Try XML parsing first for richer data
            import xml.etree.ElementTree as ET
            try:
                root = ET.fromstring(stdout)
                return self._parse_nmap_xml(root)
            except ET.ParseError:
                pass

            # Fallback: parse text output
            return self._parse_nmap_text(stdout)
        except Exception as exc:
            return {"error": str(exc), "ports": []}

    def _parse_nmap_xml(self, root) -> dict:
        """Parse nmap XML into structured results."""
        import xml.etree.ElementTree as ET
        result: dict[str, Any] = {"ports": [], "os": "", "hostname": "",
                                   "mac": "", "vendor": "", "scripts": [],
                                   "total": 0}
        for host_el in root.findall("host"):
            state_el = host_el.find("status")
            if state_el is not None and state_el.get("state") != "up":
                continue

            # Addresses
            for addr in host_el.findall("address"):
                if addr.get("addrtype") == "mac":
                    result["mac"] = addr.get("addr", "")
                    result["vendor"] = addr.get("vendor", "")

            # Hostname
            hostnames_el = host_el.find("hostnames")
            if hostnames_el is not None:
                hn = hostnames_el.find("hostname")
                if hn is not None:
                    result["hostname"] = hn.get("name", "")

            # OS
            os_el = host_el.find("os")
            if os_el is not None:
                osmatch = os_el.find("osmatch")
                if osmatch is not None:
                    result["os"] = osmatch.get("name", "")
                    accuracy = osmatch.get("accuracy", "")
                    if accuracy:
                        result["os"] += f" ({accuracy}% confidence)"

            # Ports + services + scripts
            ports_el = host_el.find("ports")
            if ports_el is not None:
                for port_el in ports_el.findall("port"):
                    port_state = port_el.find("state")
                    if port_state is None or port_state.get("state") != "open":
                        continue
                    portid = port_el.get("portid", "")
                    protocol = port_el.get("protocol", "tcp")
                    svc = port_el.find("service")
                    port_info: dict[str, Any] = {
                        "port": f"{portid}/{protocol}",
                        "state": "open",
                        "service": svc.get("name", "") if svc is not None else "",
                        "product": svc.get("product", "") if svc is not None else "",
                        "version": svc.get("version", "") if svc is not None else "",
                        "extra": svc.get("extrainfo", "") if svc is not None else "",
                    }
                    # Collect script output for this port
                    port_scripts = []
                    for script_el in port_el.findall("script"):
                        script_id = script_el.get("id", "")
                        script_out = script_el.get("output", "").strip()
                        if script_out:
                            port_scripts.append({"id": script_id, "output": script_out[:500]})
                    if port_scripts:
                        port_info["scripts"] = port_scripts
                    result["ports"].append(port_info)

            # Host scripts (e.g., smb-os-discovery, http-server-header)
            hostscript = host_el.find("hostscript")
            if hostscript is not None:
                for script_el in hostscript.findall("script"):
                    script_id = script_el.get("id", "")
                    script_out = script_el.get("output", "").strip()
                    if script_out:
                        result["scripts"].append({"id": script_id, "output": script_out[:500]})

        result["total"] = len(result["ports"])
        return result

    def _parse_nmap_text(self, stdout: str) -> dict:
        """Fallback text parser for nmap output."""
        ports = []
        for line in stdout.splitlines():
            line = line.strip()
            if "/tcp" in line or "/udp" in line:
                parts = line.split()
                if len(parts) >= 3:
                    ports.append({
                        "port": parts[0], "state": parts[1],
                        "service": " ".join(parts[2:]),
                    })
        os_info = ""
        for line in stdout.splitlines():
            if "OS details:" in line or "Running:" in line:
                os_info = line.split(":", 1)[1].strip()
                break
        return {"ports": ports, "os": os_info, "total": len(ports)}

    async def _run_shodan(self, ip: str) -> dict:
        """Query Shodan CLI for IP intelligence (requires API key in env)."""
        shodan_path = "/usr/bin/shodan"
        if not os.path.isfile(shodan_path):
            return {"error": "shodan CLI not installed"}
        try:
            ip = _sanitize(ip)
            cmd = [shodan_path, "host", ip]
            rc, stdout, stderr = await self.run_subprocess(cmd, timeout=30)
            if rc != 0 or "Error" in stdout[:100]:
                return {"error": stdout.strip()[:200] or stderr.strip()[:200] or "Shodan lookup failed"}
            # Parse shodan host output
            parsed: dict[str, Any] = {"raw_lines": []}
            ports_found = []
            vulns = []
            for line in stdout.splitlines():
                line = line.strip()
                if not line:
                    continue
                if line.startswith("Ports:"):
                    ports_found = [p.strip() for p in line.split(":", 1)[1].split(",")]
                elif line.startswith("Vulnerabilities:"):
                    vulns = [v.strip() for v in line.split(":", 1)[1].split(",")]
                elif ":" in line:
                    key, val = line.split(":", 1)
                    parsed[key.strip().lower().replace(" ", "_")] = val.strip()
                else:
                    parsed["raw_lines"].append(line)
            if ports_found:
                parsed["ports"] = ports_found
            if vulns:
                parsed["vulnerabilities"] = vulns
            if not parsed.get("raw_lines"):
                del parsed["raw_lines"]
            return parsed
        except Exception as exc:
            return {"error": str(exc)}

    async def _run_phoneinfoga(self, phone: str) -> dict:
        """Run PhoneInfoga scanner for comprehensive phone intel."""
        phoneinfoga_path = TOOL_PATHS.get("phoneinfoga", "/usr/local/bin/phoneinfoga")
        if not os.path.isfile(phoneinfoga_path):
            return {"error": "phoneinfoga not installed", "scans": []}
        try:
            clean = re.sub(r'[^\d+]', '', phone)
            if not clean.startswith("+"):
                # Default to US if no country code
                if len(clean) == 10:
                    clean = "+1" + clean
                elif len(clean) == 11 and clean.startswith("1"):
                    clean = "+" + clean
                else:
                    clean = "+" + clean
            cmd = [phoneinfoga_path, "scan", "-n", clean]
            rc, stdout, stderr = await self.run_subprocess(cmd, timeout=_FAST_TIMEOUT)

            result: dict[str, Any] = {"number": clean, "scans": []}

            if stdout:
                current_scanner = ""
                scanner_data: dict[str, Any] = {}
                for line in stdout.splitlines():
                    line = line.strip()
                    if not line:
                        if current_scanner and scanner_data:
                            result["scans"].append({"scanner": current_scanner, **scanner_data})
                            scanner_data = {}
                        continue

                    # Scanner headers like "Running scanner: local"
                    if "Running scanner" in line or "Scanner:" in line:
                        if current_scanner and scanner_data:
                            result["scans"].append({"scanner": current_scanner, **scanner_data})
                        current_scanner = line.split(":")[-1].strip().strip('"')
                        scanner_data = {}
                        continue

                    # Key-value pairs
                    if ":" in line:
                        key, val = line.split(":", 1)
                        key = key.strip().lower().replace(" ", "_")
                        val = val.strip()
                        if val and val != "N/A":
                            scanner_data[key] = val
                            # Also capture top-level fields
                            if key in ("country", "carrier", "line_type", "valid",
                                       "possible", "local_format", "international_format",
                                       "country_code", "region", "timezone"):
                                result[key] = val

                # Flush last scanner
                if current_scanner and scanner_data:
                    result["scans"].append({"scanner": current_scanner, **scanner_data})

            result["total_scans"] = len(result["scans"])
            return result
        except Exception as exc:
            logger.warning(f"PhoneInfoga error for {phone}: {exc}")
            return {"error": str(exc), "scans": []}

    async def _run_phonenumbers(self, phone: str) -> dict:
        """Use python-phonenumbers library for number validation and carrier lookup."""
        try:
            import phonenumbers
            from phonenumbers import carrier, geocoder, timezone as tz_mod

            clean = re.sub(r'[^\d+]', '', phone)
            if not clean.startswith("+"):
                if len(clean) == 10:
                    clean = "+1" + clean
                elif len(clean) == 11 and clean.startswith("1"):
                    clean = "+" + clean

            parsed = phonenumbers.parse(clean, None)
            result: dict[str, Any] = {
                "number": phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.INTERNATIONAL),
                "national_format": phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.NATIONAL),
                "e164": phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164),
                "valid": phonenumbers.is_valid_number(parsed),
                "possible": phonenumbers.is_possible_number(parsed),
                "country_code": parsed.country_code,
                "number_type": self._phone_type_name(phonenumbers.number_type(parsed)),
            }

            # Country / region
            country = geocoder.description_for_number(parsed, "en")
            if country:
                result["country"] = country

            region_code = phonenumbers.region_code_for_number(parsed)
            if region_code:
                result["region_code"] = region_code

            # Carrier
            carrier_name = carrier.name_for_number(parsed, "en")
            if carrier_name:
                result["carrier"] = carrier_name

            # Timezone
            timezones = tz_mod.time_zones_for_number(parsed)
            if timezones:
                result["timezones"] = list(timezones)

            return result
        except Exception as exc:
            logger.warning(f"phonenumbers error for {phone}: {exc}")
            return {"error": str(exc)}

    @staticmethod
    def _phone_type_name(ptype: int) -> str:
        """Convert phonenumbers type int to human-readable string."""
        type_map = {
            0: "FIXED_LINE", 1: "MOBILE", 2: "FIXED_LINE_OR_MOBILE",
            3: "TOLL_FREE", 4: "PREMIUM_RATE", 5: "SHARED_COST",
            6: "VOIP", 7: "PERSONAL_NUMBER", 8: "PAGER",
            9: "UAN", 10: "VOICEMAIL", 99: "UNKNOWN",
        }
        return type_map.get(ptype, "UNKNOWN")

    async def _run_numverify(self, phone: str) -> dict:
        """Query numverify.com API for phone validation (requires NUMVERIFY_API_KEY env)."""
        numverify_key = os.environ.get("NUMVERIFY_API_KEY", "")
        if not numverify_key:
            return {"note": "Set NUMVERIFY_API_KEY env for carrier/line-type lookup via numverify.com"}
        try:
            clean = re.sub(r'[^\d+]', '', phone).lstrip("+")
            url = f"http://apilayer.net/api/validate?access_key={numverify_key}&number={clean}"
            req = urllib.request.Request(url, headers={"User-Agent": "osint-agent/1.0"})
            resp = urllib.request.urlopen(req, timeout=10)
            data = json.loads(resp.read())

            if data.get("valid") is not None:
                return {
                    "valid": data.get("valid", False),
                    "number": data.get("international_format", clean),
                    "country": data.get("country_name", ""),
                    "country_code": data.get("country_code", ""),
                    "carrier": data.get("carrier", ""),
                    "line_type": data.get("line_type", ""),
                    "location": data.get("location", ""),
                }
            return {"error": data.get("error", {}).get("info", "Validation failed")}
        except Exception as exc:
            logger.debug(f"numverify error for {phone}: {exc}")
            return {"error": str(exc)}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Cross-referencing — scan results for new leads and auto-run them
    # ------------------------------------------------------------------

    # Patterns for extracting entities from result text
    _XREF_EMAIL_RE = re.compile(
        r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    )
    _XREF_PHONE_RE = re.compile(
        r'(?<!\d)(?:\+?\d[\d\s\-\(\)]{6,18}\d)(?!\d)'
    )
    _XREF_IP_RE = re.compile(
        r'(?<!\d)(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})(?!\d)'
    )
    _XREF_DOMAIN_RE = re.compile(
        r'(?<![a-zA-Z0-9@._-])([a-zA-Z0-9](?:[a-zA-Z0-9-]*[a-zA-Z0-9])?'
        r'(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]*[a-zA-Z0-9])?)*'
        r'\.[a-zA-Z]{2,})(?![a-zA-Z0-9._-])'
    )

    async def _cross_reference(self, query: str, query_type: str,
                                results: dict) -> list[dict]:
        """Scan *results* for emails, phones, IPs, and domains that differ
        from the original *query* and auto-run them through relevant tools.

        Returns a list of cross-reference dicts:
            [{"query": <str>, "type": <str>, "results": <dict>}, ...]

        At most 3 cross-references are executed to avoid timeouts.
        """
        # Flatten all result values into a single text blob for scanning
        text_blob = json.dumps(results, default=str)

        # Normalise original query for dedup
        original_lower = query.strip().lower()

        found: list[tuple[str, str]] = []  # (value, entity_type)

        # --- Emails ---
        for m in self._XREF_EMAIL_RE.finditer(text_blob):
            email = m.group(0).lower()
            if email != original_lower and email not in {v for v, _ in found}:
                found.append((email, "email"))

        # --- Phones (7+ digits) ---
        for m in self._XREF_PHONE_RE.finditer(text_blob):
            raw = m.group(0).strip()
            digits = re.sub(r'\D', '', raw)
            if len(digits) >= 7 and raw != original_lower and digits not in {re.sub(r'\D', '', v) for v, _ in found}:
                found.append((raw, "phone"))

        # --- IPs ---
        for m in self._XREF_IP_RE.finditer(text_blob):
            ip = m.group(1)
            parts = ip.split(".")
            if all(0 <= int(p) <= 255 for p in parts):
                if ip != original_lower and ip not in {v for v, _ in found}:
                    # Skip common non-routable / version-looking IPs
                    if not ip.startswith("0.") and not ip.startswith("127."):
                        found.append((ip, "ip"))

        # --- Domains ---
        for m in self._XREF_DOMAIN_RE.finditer(text_blob):
            domain = m.group(1).lower()
            # Skip if it's an email domain we already captured, or the original query
            if domain == original_lower:
                continue
            # Skip common non-interesting TLDs / short fragments
            if domain in {v for v, _ in found}:
                continue
            # Skip if it looks like a version string (e.g. "2.0.0")
            if all(part.isdigit() for part in domain.split(".")):
                continue
            found.append((domain, "domain"))

        if not found:
            return []

        # Limit to 3 cross-refs
        found = found[:3]

        async def _run_one(value: str, etype: str) -> dict:
            """Run a single cross-reference lookup."""
            try:
                sanitized = _sanitize(value.lstrip("@"))
            except ValueError:
                return {"query": value, "type": etype, "results": {"error": "invalid input"}}

            xref_results: dict[str, Any] = {}
            if etype == "email":
                hibp = await self._run_hibp(sanitized)
                holehe = await self._run_holehe(sanitized)
                xref_results = {"hibp": hibp, "holehe": holehe}
            elif etype == "phone":
                phoneinfoga = await self._run_phoneinfoga(sanitized)
                xref_results = {"phoneinfoga": phoneinfoga}
            elif etype == "ip":
                geo = await self._run_ip_geolocation(sanitized)
                xref_results = {"geolocation": geo}
            elif etype == "domain":
                whois = await self._run_whois(sanitized)
                dig = await self._run_dig(sanitized)
                xref_results = {"whois": whois, "dig": dig}

            return {"query": value, "type": etype, "results": xref_results}

        # Run all cross-refs in parallel
        xref_tasks = [_run_one(v, t) for v, t in found]
        cross_refs = await asyncio.gather(*xref_tasks, return_exceptions=True)

        # Filter out exceptions
        output: list[dict] = []
        for cr in cross_refs:
            if isinstance(cr, dict):
                output.append(cr)
            elif isinstance(cr, Exception):
                logger.warning(f"Cross-reference error: {cr}")

        return output

    @staticmethod
    def _extract_locations_from_whois(whois_data: dict, source: str) -> list[dict]:
        """Try to extract geo hints from whois data.  Whois itself doesn't
        carry coordinates, but city/state/country can be used for rough
        geocoding downstream.  We return a placeholder entry that the UI
        layer can enrich via a geocoding API."""
        locations: list[dict] = []
        city = whois_data.get("registrant_city", "")
        state = whois_data.get("registrant_state", "")
        country = whois_data.get("registrant_country", "")
        if city or country:
            label_parts = [p for p in (city, state, country) if p]
            locations.append({
                "lat": None,
                "lon": None,
                "label": ", ".join(label_parts),
                "source": source,
                "needs_geocoding": True,
            })
        return locations

    @staticmethod
    def _empty_result(query: str, query_type: str, error: str = "") -> dict:
        return {
            "query": query,
            "type": query_type,
            "tools_run": [],
            "results": {},
            "locations": [],
            "summary": error or "No results",
        }

    async def _geocode_string(self, location_str: str) -> dict | None:
        """Geocode a freeform location string via Nominatim."""
        import urllib.parse, urllib.request
        try:
            encoded = urllib.parse.quote(location_str)
            url = f"https://nominatim.openstreetmap.org/search?q={encoded}&format=json&limit=1"
            req = urllib.request.Request(url, headers={"User-Agent": "osint-agent/1.0"})
            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(None, lambda: json.loads(urllib.request.urlopen(req, timeout=10).read()))
            if data and len(data) > 0:
                return {"lat": float(data[0]["lat"]), "lon": float(data[0]["lon"])}
        except Exception:
            pass
        return None

    @staticmethod
    def _build_summary(query: str, query_type: str, results: dict) -> str:
        """Build a human-readable summary of findings."""
        parts = [f"Deep search for {query_type} '{query}':"]

        for tool, data in results.items():
            if isinstance(data, dict):
                if "error" in data and not any(
                    k for k in data if k != "error" and data.get(k)
                ):
                    parts.append(f"  {tool}: error - {data['error']}")
                    continue

                highlights = []
                if "total" in data:
                    highlights.append(f"{data['total']} results")
                if "accounts_found" in data and data["accounts_found"]:
                    highlights.append(f"{len(data['accounts_found'])} accounts")
                if "breaches" in data and data["breaches"]:
                    highlights.append(f"{len(data['breaches'])} breach entries")
                if "emails" in data and data["emails"]:
                    highlights.append(f"{len(data['emails'])} emails")
                if "hosts" in data and data["hosts"]:
                    highlights.append(f"{len(data['hosts'])} hosts")
                if "subdomains" in data and data["subdomains"]:
                    highlights.append(f"{len(data['subdomains'])} subdomains")
                if "ips" in data and data["ips"]:
                    highlights.append(f"{len(data['ips'])} IPs")
                if "registrar" in data:
                    highlights.append(f"registrar={data['registrar']}")
                if "total_events" in data:
                    highlights.append(f"{data['total_events']} SpiderFoot events")
                if "ports" in data and isinstance(data["ports"], list) and data["ports"]:
                    highlights.append(f"{len(data['ports'])} open ports")
                if "records" in data and isinstance(data["records"], list) and data["records"]:
                    highlights.append(f"{len(data['records'])} DNS records")
                if "vulnerabilities" in data and isinstance(data["vulnerabilities"], list):
                    highlights.append(f"{len(data['vulnerabilities'])} vulns")
                if "city" in data and data.get("city"):
                    highlights.append(f"loc={data['city']}, {data.get('country', '')}")
                if "isp" in data and data.get("isp"):
                    highlights.append(f"ISP={data['isp']}")
                if "a_records" in data:
                    highlights.append(f"{len(data['a_records'])} A records")
                if "total_found" in data:
                    highlights.append(f"{data['total_found']}/{data.get('total_checked', '?')} accounts found")
                if "infections_found" in data:
                    count = data["infections_found"]
                    highlights.append(f"{count} infostealer infection{'s' if count != 1 else ''}")

                if highlights:
                    parts.append(f"  {tool}: {', '.join(highlights)}")
                else:
                    parts.append(f"  {tool}: completed (no notable findings)")

        return "\n".join(parts)
