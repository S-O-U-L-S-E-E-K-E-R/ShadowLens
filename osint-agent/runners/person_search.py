"""Person OSINT search — scrapes open-source public data for names, addresses,
phone numbers, emails, social accounts, and locations.  Uses multiple tools
and free public-records APIs in parallel."""

import asyncio
import json
import logging
import os
import re
import tempfile
import urllib.parse
import urllib.request
from typing import Any

from config import TOOL_PATHS
from runners.base import BaseToolRunner

logger = logging.getLogger(__name__)

_FAST_TIMEOUT = 60
_MED_TIMEOUT = 90
_SAFE_RE = re.compile(r'^[a-zA-Z0-9@._+\-:/\s\(\)\']+$')


def _sanitize(val: str) -> str:
    val = val.strip()
    if not val or len(val) > 200:
        raise ValueError("Invalid input")
    for bad in (";", "&", "|", "`", "$", "{", "}", "<", ">", "!", "\n"):
        if bad in val:
            raise ValueError(f"Disallowed character: {bad!r}")
    return val


class PersonSearchRunner(BaseToolRunner):
    """Full-spectrum person OSINT: name → addresses, phones, emails, socials, locations."""

    tool_name = "person_search"
    cache_ttl = 600

    async def search(self, name: str, extra_context: dict | None = None) -> dict:
        """Run all person-search tools in parallel for *name*.

        extra_context can include: city, state, email, username, age — to narrow results.
        """
        name = name.strip()
        if not name:
            return {"error": "Empty name", "tools_run": [], "results": {}, "locations": []}

        ctx = extra_context or {}
        safe_name = _sanitize(name)

        # Run all tools in parallel
        tasks = {
            "public_records": self._scrape_public_records(safe_name, ctx),
            "maigret": self._run_maigret(safe_name),
            "sherlock": self._run_sherlock(safe_name),
            "holehe": self._run_holehe_if_email(ctx.get("email", "")),
            "open_corporates": self._search_opencorporates(safe_name),
            "voter_records": self._search_voter_records(safe_name, ctx),
            "court_records": self._search_court_records(safe_name, ctx),
            "social_profiles": self._scrape_social_profiles(safe_name),
        }

        gathered = await asyncio.gather(*tasks.values(), return_exceptions=True)
        results = {}
        tools_run = []
        for key, res in zip(tasks.keys(), gathered):
            if isinstance(res, Exception):
                logger.warning(f"Person search {key} failed: {res}")
                results[key] = {"error": str(res)}
            elif res and not (isinstance(res, dict) and res.get("skipped")):
                results[key] = res
            tools_run.append(key)

        # Gather all locations from results and geocode them
        locations = self._extract_all_locations(results, safe_name)
        if locations:
            locations = await self.geocode_locations(locations)
            # Filter out locations that couldn't be geocoded
            locations = [l for l in locations if l.get("lat") and l.get("lon")]

        return {
            "query": name,
            "type": "person",
            "tools_run": tools_run,
            "results": results,
            "locations": locations,
            "summary": self._build_summary(name, results, locations),
        }

    # ------------------------------------------------------------------
    # Public records scraping (free open-source APIs)
    # ------------------------------------------------------------------

    async def _scrape_public_records(self, name: str, ctx: dict) -> dict:
        """Query multiple free people-search data sources."""
        results: dict[str, Any] = {"addresses": [], "phones": [], "emails": [],
                                    "relatives": [], "age": None, "aliases": []}

        # 1. Search via open public records APIs
        parts = name.split()
        first = parts[0] if parts else name
        last = parts[-1] if len(parts) > 1 else ""
        city = ctx.get("city", "")
        state = ctx.get("state", "")

        # Try multiple free people-lookup sources
        sources_tried = []

        # Source 1: npiregistry.cms.hhs.gov (if person is in healthcare)
        try:
            npi_data = await self._query_npi_registry(first, last, state)
            if npi_data.get("results"):
                results["npi_records"] = npi_data["results"]
                for rec in npi_data["results"]:
                    if rec.get("addresses"):
                        results["addresses"].extend(rec["addresses"])
                    if rec.get("phone"):
                        results["phones"].append(rec["phone"])
            sources_tried.append("npi_registry")
        except Exception as e:
            logger.debug(f"NPI registry error: {e}")

        # Source 2: OpenCNAM / caller ID (if we have a phone)
        # Source 3: Search via web scraping of public records sites
        try:
            web_results = await self._scrape_web_public(name, city, state)
            if web_results:
                for key in ("addresses", "phones", "emails", "relatives", "aliases"):
                    if web_results.get(key):
                        results[key].extend(web_results[key])
                if web_results.get("age"):
                    results["age"] = web_results["age"]
            sources_tried.append("web_public")
        except Exception as e:
            logger.debug(f"Web public records error: {e}")

        # Deduplicate
        for key in ("addresses", "phones", "emails", "relatives", "aliases"):
            if results[key]:
                seen = set()
                deduped = []
                for item in results[key]:
                    s = json.dumps(item, sort_keys=True) if isinstance(item, dict) else str(item)
                    if s not in seen:
                        seen.add(s)
                        deduped.append(item)
                results[key] = deduped

        results["sources_tried"] = sources_tried
        return results

    async def _query_npi_registry(self, first: str, last: str, state: str = "") -> dict:
        """Query NPI registry for healthcare professionals — free, no key needed."""
        params = {"version": "2.1", "first_name": first, "last_name": last, "limit": "5"}
        if state and len(state) == 2:
            params["state"] = state.upper()
        url = f"https://npiregistry.cms.hhs.gov/api/?{urllib.parse.urlencode(params)}"

        loop = asyncio.get_event_loop()
        req = urllib.request.Request(url, headers={"User-Agent": "osint-agent/1.0"})

        def _fetch():
            resp = urllib.request.urlopen(req, timeout=10)
            return json.loads(resp.read())

        data = await loop.run_in_executor(None, _fetch)
        records = []
        for r in data.get("results", [])[:5]:
            basic = r.get("basic", {})
            addrs = []
            for a in r.get("addresses", []):
                addr_str = f"{a.get('address_1', '')} {a.get('address_2', '')}, {a.get('city', '')}, {a.get('state', '')} {a.get('postal_code', '')}"
                addrs.append({
                    "address": addr_str.strip().strip(","),
                    "city": a.get("city", ""),
                    "state": a.get("state", ""),
                    "zip": a.get("postal_code", ""),
                })
            records.append({
                "name": f"{basic.get('first_name', '')} {basic.get('last_name', '')}".strip(),
                "credential": basic.get("credential", ""),
                "gender": basic.get("gender", ""),
                "npi": str(r.get("number", "")),
                "addresses": addrs,
                "phone": r.get("addresses", [{}])[0].get("telephone_number", "") if r.get("addresses") else "",
                "taxonomy": r.get("taxonomies", [{}])[0].get("desc", "") if r.get("taxonomies") else "",
            })
        return {"results": records}

    async def _scrape_web_public(self, name: str, city: str = "", state: str = "") -> dict:
        """Scrape public data using search-based approach."""
        results: dict[str, Any] = {"addresses": [], "phones": [], "emails": [],
                                    "relatives": [], "aliases": [], "age": None}

        # Use curl to query public people-search aggregators
        queries = [
            f'"{name}" address phone',
        ]
        if city:
            queries.append(f'"{name}" "{city}" address')
        if state:
            queries.append(f'"{name}" "{state}" address phone')

        # Search via a basic web lookup to find public info
        # We use the Wikipedia API to find notable persons
        try:
            wiki_data = await self._search_wikipedia(name)
            if wiki_data:
                results["wikipedia"] = wiki_data
        except Exception:
            pass

        # Search via Wikidata for structured person data
        try:
            wikidata = await self._search_wikidata(name)
            if wikidata:
                results["wikidata"] = wikidata
        except Exception:
            pass

        return results

    async def _search_wikipedia(self, name: str) -> dict | None:
        """Search Wikipedia for a person — free structured data."""
        loop = asyncio.get_event_loop()
        encoded = urllib.parse.quote(name)
        url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{encoded}"
        req = urllib.request.Request(url, headers={"User-Agent": "osint-agent/1.0"})

        def _fetch():
            try:
                resp = urllib.request.urlopen(req, timeout=8)
                return json.loads(resp.read())
            except Exception:
                return None

        data = await loop.run_in_executor(None, _fetch)
        if data and data.get("type") != "disambiguation" and data.get("extract"):
            return {
                "title": data.get("title", ""),
                "description": data.get("description", ""),
                "extract": data.get("extract", "")[:500],
                "coordinates": data.get("coordinates"),
            }
        return None

    async def _search_wikidata(self, name: str) -> dict | None:
        """Search Wikidata for structured person data (birth, death, location, occupation)."""
        loop = asyncio.get_event_loop()
        encoded = urllib.parse.quote(name)
        url = f"https://www.wikidata.org/w/api.php?action=wbsearchentities&search={encoded}&language=en&format=json&type=item&limit=3"
        req = urllib.request.Request(url, headers={"User-Agent": "osint-agent/1.0"})

        def _fetch():
            resp = urllib.request.urlopen(req, timeout=8)
            return json.loads(resp.read())

        data = await loop.run_in_executor(None, _fetch)
        results = []
        for entity in data.get("search", [])[:3]:
            results.append({
                "id": entity.get("id", ""),
                "label": entity.get("label", ""),
                "description": entity.get("description", ""),
                "url": entity.get("concepturi", ""),
            })
        return {"entities": results} if results else None

    # ------------------------------------------------------------------
    # Maigret (better Sherlock — checks 2500+ sites)
    # ------------------------------------------------------------------

    async def _run_maigret(self, name: str) -> dict:
        """Run maigret for comprehensive username search across 2500+ sites."""
        maigret_path = os.path.expanduser("~/.local/bin/maigret")
        if not os.path.isfile(maigret_path):
            maigret_path = "/usr/bin/maigret"
        if not os.path.isfile(maigret_path):
            return {"error": "maigret not installed", "accounts": []}

        username = name.replace(" ", "").lower()
        try:
            with tempfile.TemporaryDirectory(prefix="maigret_") as tmpdir:
                outfile = os.path.join(tmpdir, "results.json")
                cmd = [
                    maigret_path, username,
                    "--json", "notype",  # JSON output
                    "-o", outfile,
                    "--timeout", "15",
                    "--retries", "0",
                    "--no-color",
                    "--top-sites", "200",  # Top 200 sites for speed
                ]
                rc, stdout, stderr = await self.run_subprocess(cmd, timeout=_MED_TIMEOUT)

                accounts = []
                # Parse JSON output
                if os.path.isfile(outfile):
                    try:
                        with open(outfile) as f:
                            data = json.load(f)
                        if isinstance(data, dict):
                            for site, info in data.items():
                                if isinstance(info, dict) and info.get("status"):
                                    status = info["status"]
                                    if "Claimed" in str(status) or info.get("url_user"):
                                        accounts.append({
                                            "site": site,
                                            "url": info.get("url_user", ""),
                                            "status": str(status),
                                            "tags": info.get("tags", []),
                                        })
                        elif isinstance(data, list):
                            for item in data:
                                if isinstance(item, dict) and item.get("url_user"):
                                    accounts.append({
                                        "site": item.get("sitename", item.get("site", "")),
                                        "url": item.get("url_user", ""),
                                    })
                    except (json.JSONDecodeError, Exception) as e:
                        logger.debug(f"Maigret JSON parse error: {e}")

                # Fallback: parse stdout
                if not accounts and stdout:
                    for line in stdout.splitlines():
                        line = line.strip()
                        if "[+]" in line and "http" in line:
                            parts = line.split("[+]")[-1].strip()
                            if ": http" in parts:
                                idx = parts.index(": http")
                                site = parts[:idx].strip()
                                url = parts[idx + 2:].strip()
                                accounts.append({"site": site, "url": url})

                return {"accounts": accounts, "total": len(accounts), "username_searched": username}
        except Exception as exc:
            logger.warning(f"Maigret error: {exc}")
            return {"error": str(exc), "accounts": []}

    # ------------------------------------------------------------------
    # Sherlock (username search)
    # ------------------------------------------------------------------

    async def _run_sherlock(self, name: str) -> dict:
        """Run Sherlock for the name as a username."""
        sherlock_path = TOOL_PATHS.get("sherlock", "/usr/bin/sherlock")
        if not os.path.isfile(sherlock_path):
            return {"error": "sherlock not installed", "accounts": []}

        username = name.replace(" ", "").lower()
        try:
            with tempfile.TemporaryDirectory(prefix="sherlock_") as tmpdir:
                cmd = [
                    sherlock_path, username,
                    "--folderoutput", tmpdir,
                    "--csv",
                    "--print-found",
                    "--timeout", "15",
                    "--no-color",
                ]
                rc, stdout, stderr = await self.run_subprocess(cmd, timeout=_FAST_TIMEOUT)

                accounts = []
                csv_path = os.path.join(tmpdir, f"{username}.csv")
                if os.path.isfile(csv_path):
                    import csv
                    with open(csv_path) as f:
                        reader = csv.DictReader(f)
                        for row in reader:
                            url = row.get("url", row.get("URL", ""))
                            site = row.get("name", row.get("Name", ""))
                            if url:
                                accounts.append({"site": site, "url": url})

                if not accounts and stdout:
                    for line in stdout.splitlines():
                        if line.strip().startswith("[+]"):
                            content = line.strip()[4:].strip()
                            if ": http" in content:
                                idx = content.index(": http")
                                accounts.append({
                                    "site": content[:idx].strip(),
                                    "url": content[idx + 2:].strip()
                                })

                return {"accounts": accounts, "total": len(accounts), "username_searched": username}
        except Exception as exc:
            return {"error": str(exc), "accounts": []}

    # ------------------------------------------------------------------
    # Holehe (email → registered accounts)
    # ------------------------------------------------------------------

    async def _run_holehe_if_email(self, email: str) -> dict:
        """Run holehe to check what services an email is registered on."""
        if not email or "@" not in email:
            return {"skipped": True}

        holehe_path = os.path.expanduser("~/.local/bin/holehe")
        if not os.path.isfile(holehe_path):
            holehe_path = "/usr/bin/holehe"
        if not os.path.isfile(holehe_path):
            return {"error": "holehe not installed"}

        try:
            email = _sanitize(email)
            cmd = [holehe_path, email, "--no-color"]
            rc, stdout, stderr = await self.run_subprocess(cmd, timeout=_MED_TIMEOUT)

            registered = []
            not_registered = []
            for line in stdout.splitlines():
                line = line.strip()
                if "[+]" in line:
                    # Registered
                    site = line.split("[+]")[-1].strip().split()[0] if "[+]" in line else line
                    registered.append(site)
                elif "[-]" in line:
                    site = line.split("[-]")[-1].strip().split()[0] if "[-]" in line else line
                    not_registered.append(site)

            return {
                "email": email,
                "registered_on": registered,
                "total_registered": len(registered),
                "total_checked": len(registered) + len(not_registered),
            }
        except Exception as exc:
            return {"error": str(exc)}

    # ------------------------------------------------------------------
    # OpenCorporates (company/director search)
    # ------------------------------------------------------------------

    async def _search_opencorporates(self, name: str) -> dict:
        """Search OpenCorporates for corporate officer/director records."""
        loop = asyncio.get_event_loop()
        encoded = urllib.parse.quote(name)
        url = f"https://api.opencorporates.com/v0.4/officers/search?q={encoded}&per_page=5"
        req = urllib.request.Request(url, headers={"User-Agent": "osint-agent/1.0"})

        def _fetch():
            try:
                resp = urllib.request.urlopen(req, timeout=10)
                return json.loads(resp.read())
            except Exception:
                return None

        data = await loop.run_in_executor(None, _fetch)
        if not data:
            return {"officers": [], "total": 0}

        officers = []
        for o in data.get("results", {}).get("officers", [])[:10]:
            officer = o.get("officer", {})
            company = officer.get("company", {})
            officers.append({
                "name": officer.get("name", ""),
                "position": officer.get("position", ""),
                "company_name": company.get("name", ""),
                "company_number": company.get("company_number", ""),
                "jurisdiction": company.get("jurisdiction_code", ""),
                "start_date": officer.get("start_date", ""),
                "end_date": officer.get("end_date", ""),
                "address": officer.get("address", ""),
            })
        return {"officers": officers, "total": len(officers)}

    # ------------------------------------------------------------------
    # Voter records search (public in some US states)
    # ------------------------------------------------------------------

    async def _search_voter_records(self, name: str, ctx: dict) -> dict:
        """Search for voter registration data via public APIs where available."""
        # Voter records are publicly available in many US states
        # We use the Google Civic Information API (free, limited)
        parts = name.split()
        if len(parts) < 2:
            return {"note": "Need first and last name for voter lookup"}

        # For now, return a structured search suggestion with context
        return {
            "note": "Voter records vary by state. Use state-specific portals:",
            "search_name": name,
            "suggested_portals": [
                {"state": "FL", "url": "https://dos.myflorida.com/elections/data-statistics/voter-registration-statistics/"},
                {"state": "NC", "url": "https://vt.ncsbe.gov/RegLkup/"},
                {"state": "OH", "url": "https://voterlookup.ohiosos.gov/"},
                {"state": "TX", "url": "https://teamrv-mvp.sos.texas.gov/MVP/mvp.do"},
            ],
        }

    # ------------------------------------------------------------------
    # Court records (public)
    # ------------------------------------------------------------------

    async def _search_court_records(self, name: str, ctx: dict) -> dict:
        """Search public court records databases."""
        # PACER / RECAP (federal courts — public via CourtListener)
        loop = asyncio.get_event_loop()
        encoded = urllib.parse.quote(name)
        url = f"https://www.courtlistener.com/api/rest/v4/search/?q=%22{encoded}%22&type=people"
        req = urllib.request.Request(url, headers={"User-Agent": "osint-agent/1.0"})

        def _fetch():
            try:
                resp = urllib.request.urlopen(req, timeout=10)
                return json.loads(resp.read())
            except Exception:
                return None

        data = await loop.run_in_executor(None, _fetch)
        if not data:
            return {"records": [], "total": 0}

        records = []
        for r in data.get("results", [])[:10]:
            records.append({
                "name": r.get("name_full", r.get("name", "")),
                "court": r.get("court", ""),
                "dob": r.get("date_dob", ""),
                "political_affiliation": r.get("political_affiliation", ""),
                "position": r.get("name_suffix", ""),
                "school": r.get("school", ""),
                "url": r.get("absolute_url", ""),
            })
        return {"records": records, "total": len(records)}

    # ------------------------------------------------------------------
    # Social profiles aggregation
    # ------------------------------------------------------------------

    async def _scrape_social_profiles(self, name: str) -> dict:
        """Build social profile search links and check common platforms."""
        parts = name.lower().split()
        username_variants = [
            "".join(parts),           # johnsmith
            ".".join(parts),          # john.smith
            "_".join(parts),          # john_smith
        ]
        if len(parts) >= 2:
            username_variants.extend([
                parts[0][0] + parts[-1],   # jsmith
                parts[0] + parts[-1][0],   # johns
            ])

        platforms = {
            "linkedin": f"https://www.linkedin.com/search/results/people/?keywords={urllib.parse.quote(name)}",
            "facebook": f"https://www.facebook.com/search/people/?q={urllib.parse.quote(name)}",
            "twitter": f"https://twitter.com/search?q={urllib.parse.quote(name)}&f=user",
            "instagram": f"https://www.instagram.com/{username_variants[0]}/",
            "github": f"https://github.com/search?q={urllib.parse.quote(name)}&type=users",
            "reddit": f"https://www.reddit.com/search/?q={urllib.parse.quote(name)}&type=user",
        }

        return {
            "search_links": platforms,
            "username_variants": username_variants[:5],
            "note": "Direct profile links — verify manually",
        }

    # ------------------------------------------------------------------
    # Location extraction & geocoding
    # ------------------------------------------------------------------

    def _extract_all_locations(self, results: dict, name: str) -> list[dict]:
        """Extract and geocode all addresses found across all tools."""
        locations = []
        seen_addrs = set()

        # From public records
        pub = results.get("public_records", {})
        logger.info(f"Extracting locations: pub has {len(pub.get('addresses', []))} addresses, {len(pub.get('npi_records', []))} NPI records")
        for addr in pub.get("addresses", []):
            if isinstance(addr, dict):
                addr_str = addr.get("address", "")
                city = addr.get("city", "")
                state = addr.get("state", "")
                z = addr.get("zip", "")
                key = f"{addr_str}|{city}|{state}"
                if key not in seen_addrs and (city or state):
                    seen_addrs.add(key)
                    locations.append({
                        "lat": None, "lon": None,
                        "label": f"{name} — {addr_str}, {city}, {state} {z}".strip().rstrip(","),
                        "source": "public_records",
                        "address": addr_str,
                        "city": city,
                        "state": state,
                        "zip": z,
                        "needs_geocoding": True,
                    })

        # From NPI records
        for npi in pub.get("npi_records", []):
            for addr in npi.get("addresses", []):
                city = addr.get("city", "")
                state = addr.get("state", "")
                key = f"{addr.get('address', '')}|{city}|{state}"
                if key not in seen_addrs and (city or state):
                    seen_addrs.add(key)
                    locations.append({
                        "lat": None, "lon": None,
                        "label": f"{npi.get('name', name)} — {addr.get('address', '')}, {city}, {state}",
                        "source": "npi_registry",
                        "needs_geocoding": True,
                        "city": city,
                        "state": state,
                    })

        # From corporate records
        for off in results.get("open_corporates", {}).get("officers", []):
            addr = off.get("address", "")
            if addr and addr not in seen_addrs:
                seen_addrs.add(addr)
                locations.append({
                    "lat": None, "lon": None,
                    "label": f"{off.get('name', name)} — {off.get('position', '')} at {off.get('company_name', '')} — {addr}",
                    "source": "opencorporates",
                    "needs_geocoding": True,
                })

        return locations

    async def geocode_locations(self, locations: list[dict]) -> list[dict]:
        """Geocode locations that have addresses but no coordinates."""
        loop = asyncio.get_event_loop()
        logger.info(f"Geocoding {len(locations)} locations")
        for loc in locations:
            if loc.get("needs_geocoding") and not loc.get("lat"):
                # Build address query — use city+state only for best Nominatim results
                city = loc.get("city", "")
                state = loc.get("state", "")
                zipcode = loc.get("zip", "")[:5] if loc.get("zip") else ""
                street = loc.get("address", "").split(",")[0].strip() if loc.get("address") else ""
                # Clean double-spaces
                street = re.sub(r'\s{2,}', ' ', street).strip()
                if street and city and state:
                    query = f"{street}, {city}, {state} {zipcode}".strip()
                elif city and state:
                    query = f"{city}, {state}"
                else:
                    query = ""
                if not query:
                    query = loc.get("label", "").split("\u2014")[-1].strip() if "\u2014" in loc.get("label", "") else ""
                if not query:
                    logger.debug(f"No geocoding query for location: {loc}")
                    continue
                # Try multiple query variants: full address, simplified, city+state
                # Strip suite/unit/apt numbers that confuse Nominatim
                street_clean = re.sub(r'\s+(STE|SUITE|APT|UNIT|#)\s*\S*', '', street, flags=re.IGNORECASE).strip()
                queries_to_try = []
                if street_clean and city and state:
                    queries_to_try.append(f"{street_clean}, {city}, {state}")
                if city and state:
                    queries_to_try.append(f"{city}, {state}")

                try:
                    geocoded = False
                    for gq in queries_to_try:
                        encoded = urllib.parse.quote(gq)
                        geo_url = f"https://nominatim.openstreetmap.org/search?q={encoded}&format=json&limit=1&countrycodes=us"
                        geo_req = urllib.request.Request(geo_url, headers={"User-Agent": "osint-agent/1.0"})

                        def _fetch(_req=geo_req):
                            resp = urllib.request.urlopen(_req, timeout=10)
                            return json.loads(resp.read())

                        data = await loop.run_in_executor(None, _fetch)
                        if data and len(data) > 0:
                            loc["lat"] = float(data[0]["lat"])
                            loc["lon"] = float(data[0]["lon"])
                            loc["needs_geocoding"] = False
                            geocoded = True
                            logger.info(f"Geocoded '{gq}' → {loc['lat']}, {loc['lon']}")
                            break
                        await asyncio.sleep(1.1)

                    if not geocoded:
                        logger.warning(f"No geocoding results for '{query}'")
                except Exception as e:
                    logger.warning(f"Geocoding failed for '{query}': {e}")
                # Rate limit: nominatim requires 1 req/sec
                await asyncio.sleep(1.1)
        return locations

    def _build_summary(self, name: str, results: dict, locations: list) -> str:
        parts = [f"Person search for '{name}':"]

        pub = results.get("public_records", {})
        if pub.get("addresses"):
            parts.append(f"  Addresses: {len(pub['addresses'])} found")
        if pub.get("phones"):
            parts.append(f"  Phone numbers: {len(pub['phones'])} found")
        if pub.get("npi_records"):
            parts.append(f"  NPI records: {len(pub['npi_records'])} matches")

        maigret = results.get("maigret", {})
        if maigret.get("accounts"):
            parts.append(f"  Maigret: {len(maigret['accounts'])} social accounts")

        sherlock = results.get("sherlock", {})
        if sherlock.get("accounts"):
            parts.append(f"  Sherlock: {len(sherlock['accounts'])} accounts")

        corps = results.get("open_corporates", {})
        if corps.get("officers"):
            parts.append(f"  Corporate records: {len(corps['officers'])} officer matches")

        courts = results.get("court_records", {})
        if courts.get("records"):
            parts.append(f"  Court records: {len(courts['records'])} matches")

        if locations:
            parts.append(f"  Locations: {len(locations)} plotted on map")

        return "\n".join(parts)
