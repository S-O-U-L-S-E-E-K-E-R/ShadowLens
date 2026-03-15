"""F.R.I.D.A.Y. Analysis Engine — powered by Claude Code.

Provides LLM-powered analysis for ALL ShadowLens data layers:
  - Security scans (Nmap, BloodHound, Volatility) with 3-stage anti-hallucination
  - General entity analysis (flights, ships, bases, threats, weather, etc.)
  - Free-form OSINT research with tool access
  - General knowledge queries
"""

import json
import logging
import os
import re
import pickle
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Base directory for engine data (relative to this file)
_ENGINE_DIR = Path(__file__).parent
_MODELS_DIR = _ENGINE_DIR / "models"
_RAG_DATA_DIR = _ENGINE_DIR / "rag_data"

# Entity types that are security scan data (use 3-stage pipeline)
SCAN_ENTITY_TYPES = {'nmap_host', 'nuclei_vuln', 'snort_alert', 'kismet_device'}

# OSINT trigger keywords — if the question contains these, enable tools
OSINT_KEYWORDS = [
    'scan ', 'run nmap', 'run nuclei', 'enumerate', 'recon ', 'reconnaissance',
    'osint ', 'search for', 'look up', 'lookup', 'investigate ', 'find info', 'find ',
    'whois ', 'dns lookup', 'subdomain', 'harvest', 'sherlock',
    'deep search', 'research ', 'dig into', 'footprint',
    'find phone', 'find address', 'find email', 'find location',
    'phone number', 'track ', 'trace ', 'geolocate', 'geolocation',
    'who owns', 'who is ', 'what is the ip', 'port scan',
    'vulnerability scan', 'check if ', 'is this ip', 'reverse lookup',
    'email lookup', 'username lookup', 'domain lookup', 'ip lookup',
    'scan email', 'check email', 'email accounts', 'find accounts',
    'find all accounts', 'accounts for', 'check username', 'scan username',
    'username accounts', 'registered accounts', 'account lookup',
    'what sites', 'what platforms', 'where is registered',
    'hudson rock', 'infostealer', 'breach check', 'credential leak',
    'compromised credentials', 'what accounts',
    'telegram', 'telegram channel', 'scrape telegram', 'monitor telegram',
    'certificate transparency', 'cert transparency', 'crt.sh', 'ssl cert',
    'extract ioc', 'find ioc', 'indicators of compromise',
    'subdomains for', 'find subdomains',
]

# Location/mapping keywords — questions that need geocoding + map plotting
LOCATE_KEYWORDS = [
    'plot ', 'plot on', 'locate ', 'map ', 'show on map', 'show me ',
    'where is ', 'fly to ', 'go to ', 'zoom to ',
    'on the map', 'location of', 'place a marker', 'place marker',
    'mark ', 'mark the', 'pin ', 'pin the', 'pinpoint',
    'find the location', 'find location', 'put a pin', 'drop a pin',
    'show location', 'mark location', 'marker at', 'marker on',
    'mark on map', 'pin on map', 'find on map', 'find it on',
]

# Wireless device discovery keywords — triggers Wigle WiFi/BT search
WIRELESS_KEYWORDS = [
    'wifi near', 'wifi device', 'wifi network', 'wireless device', 'wireless network',
    'bluetooth device', 'bluetooth near', 'bt device', 'find wifi', 'find bluetooth',
    'find wireless', 'show wifi', 'show bluetooth', 'scan wifi', 'scan bluetooth',
    'wigle', 'wardriving', 'wireless scan', 'wifi scan', 'bt scan',
    'leaked wifi', 'leaked credential', 'wifi password', 'wpa-sec',
    'ssid ', 'bssid ', 'find ssid', 'find bssid',
]

# Camera/webcam discovery keywords — triggers nearby webcam search
CAMERA_KEYWORDS = [
    'find camera', 'find cctv', 'find webcam', 'camera feed', 'cctv feed',
    'webcam feed', 'show camera', 'show cctv', 'show webcam', 'camera at',
    'cameras near', 'cameras in', 'cctv near', 'webcam near', 'webcams near',
    'webcams in', 'live cam', 'live camera', 'surveillance camera',
    'pull up camera', 'pull up cctv', 'get camera', 'get cctv',
    'camera footage', 'video feed', 'find feed', 'find stream',
]

# Pattern for US street addresses (e.g. "1087 Reynolds Bridge Rd, Benton TN 37042")
ADDRESS_PATTERN = re.compile(
    r'\b\d+\s+[\w\s]+(?:st|street|rd|road|ave|avenue|blvd|boulevard|dr|drive|ln|lane|ct|court|way|pl|place|cir|circle|hwy|highway|pkwy|parkway)\b',
    re.IGNORECASE,
)

# Service synonym mapping for hallucination validation
SERVICE_SYNONYMS = {
    'smb': ['smb', 'microsoft-ds', 'netbios-ssn', 'cifs', 'smb2'],
    'rdp': ['rdp', 'ms-wbt-server', 'terminal services', 'terminal-services'],
    'dns': ['dns', 'domain'],
    'http': ['http', 'www', 'http-alt', 'https', 'ssl/http', 'http-proxy'],
    'https': ['https', 'ssl/http', 'http-ssl'],
    'ssh': ['ssh', 'openssh'],
    'ftp': ['ftp', 'ftps', 'ftp-data'],
    'telnet': ['telnet'],
    'smtp': ['smtp', 'smtps', 'submission'],
    'ldap': ['ldap', 'ldaps', 'ssl/ldap'],
    'vnc': ['vnc', 'vnc-http'],
    'mysql': ['mysql', 'mariadb'],
    'postgresql': ['postgresql', 'postgres'],
    'rpc': ['rpc', 'msrpc', 'rpcbind', 'ncacn_http'],
    'kerberos': ['kerberos', 'kerberos-sec', 'kpasswd5'],
}


class FridayEngine:
    """Core F.R.I.D.A.Y. analysis engine — uses Claude Code CLI or Ollama as the LLM backend."""

    def __init__(self):
        self.llm = None
        self.embed_model = None
        self.faiss_indexes: dict = {}
        self.chunks: dict = {}
        self.fact_extractors: dict = {}
        self.ready = False
        self._loading = False
        self._lock = threading.Lock()
        self._claude_path: Optional[str] = None
        self._ollama_available: bool = False

    @property
    def model_path(self) -> Path:
        return _MODELS_DIR / "Qwen2.5-14B-Instruct-Q5_K_M.gguf"

    @property
    def model_available(self) -> bool:
        return self._claude_path is not None

    @property
    def _llm_provider(self) -> str:
        """Current LLM provider — 'claude' or 'ollama'."""
        return os.environ.get("LLM_PROVIDER", "claude")

    def status(self) -> dict:
        modules = {}
        for mod in ['nmap', 'bloodhound', 'volatility']:
            modules[mod] = {
                'faiss_loaded': mod in self.faiss_indexes,
                'extractor_loaded': mod in self.fact_extractors,
                'chunks': len(self.chunks.get(mod, [])),
            }
        provider = self._llm_provider
        return {
            'ready': self.ready,
            'loading': self._loading,
            'model_available': self.model_available or self._ollama_available,
            'model_path': self._claude_path or 'claude (not found)' if provider == 'claude' else os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"),
            'llm_loaded': self.llm is not None,
            'llm_backend': provider,
            'ollama_available': self._ollama_available,
            'ollama_model': os.environ.get("OLLAMA_MODEL", "llama3"),
            'embed_model_loaded': self.embed_model is not None,
            'modules': modules,
        }

    def initialize(self, background: bool = True):
        if self._loading or self.ready:
            return
        if background:
            threading.Thread(target=self._load, daemon=True, name="friday-init").start()
        else:
            self._load()

    def _load(self):
        with self._lock:
            if self.ready or self._loading:
                return
            self._loading = True

        try:
            logger.info("F.R.I.D.A.Y.: Loading embedding model...")
            self._load_embedding_model()

            logger.info("F.R.I.D.A.Y.: Loading FAISS indexes...")
            self._load_faiss_indexes()

            logger.info("F.R.I.D.A.Y.: Loading fact extractors...")
            self._load_fact_extractors()

            logger.info("F.R.I.D.A.Y.: Verifying LLM backends...")
            self._load_llm()
            self._probe_ollama()

            provider = self._llm_provider
            self.ready = True
            logger.info(f"F.R.I.D.A.Y.: Engine ready. Active backend: {provider}. Claude={'ok' if self._claude_path else 'N/A'}, Ollama={'ok' if self._ollama_available else 'N/A'}.")
        except Exception as e:
            logger.error(f"F.R.I.D.A.Y.: Initialization failed: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self._loading = False

    def _load_embedding_model(self):
        import warnings
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore")
            from sentence_transformers import SentenceTransformer
            self.embed_model = SentenceTransformer("all-MiniLM-L6-v2")
            self.embed_model.eval()

    def _load_faiss_indexes(self):
        import faiss
        index_map = {
            'nmap': 'customer_syd_Nmap',
            'bloodhound': 'customer_syd_bloodhound_knowledge_BloodHound',
            'volatility': 'customer_syd_volatility_knowledge_Volatility3',
        }
        for module, prefix in index_map.items():
            faiss_path = _RAG_DATA_DIR / f"{prefix}.faiss"
            pkl_path = _RAG_DATA_DIR / f"{prefix}.pkl"
            if faiss_path.exists() and pkl_path.exists():
                self.faiss_indexes[module] = faiss.read_index(str(faiss_path))
                with open(pkl_path, 'rb') as f:
                    self.chunks[module] = pickle.load(f)
                logger.info(f"F.R.I.D.A.Y.: Loaded {module} index ({len(self.chunks[module])} chunks)")

    def _load_fact_extractors(self):
        import sys
        engine_dir = str(_ENGINE_DIR)
        if engine_dir not in sys.path:
            sys.path.insert(0, engine_dir)
        try:
            from nmap_fact_extractor import NmapFactExtractor
            self.fact_extractors['nmap'] = NmapFactExtractor()
        except Exception as e:
            logger.warning(f"F.R.I.D.A.Y.: Could not load Nmap extractor: {e}")
        try:
            from bloodhound_fact_extractor import BloodHoundFactExtractor
            self.fact_extractors['bloodhound'] = BloodHoundFactExtractor()
        except Exception as e:
            logger.warning(f"F.R.I.D.A.Y.: Could not load BloodHound extractor: {e}")
        try:
            from volatility_fact_extractor import VolatilityFactExtractor
            self.fact_extractors['volatility'] = VolatilityFactExtractor()
        except Exception as e:
            logger.warning(f"F.R.I.D.A.Y.: Could not load Volatility extractor: {e}")

    def _load_llm(self):
        claude_path = shutil.which("claude")
        if not claude_path:
            for p in [
                os.path.expanduser("~/.local/bin/claude"),
                "/usr/local/bin/claude",
                "/usr/bin/claude",
            ]:
                if os.path.isfile(p) and os.access(p, os.X_OK):
                    claude_path = p
                    break
        if not claude_path:
            logger.warning("F.R.I.D.A.Y.: Claude Code CLI not found — Claude backend unavailable.")
            return
        try:
            result = subprocess.run(
                [claude_path, "--version"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                version = result.stdout.strip()
                logger.info(f"F.R.I.D.A.Y.: Claude Code CLI verified — {version}")
                self._claude_path = claude_path
                self.llm = "claude"
            else:
                logger.warning(f"F.R.I.D.A.Y.: Claude CLI check failed: {result.stderr}")
        except subprocess.TimeoutExpired:
            logger.warning("F.R.I.D.A.Y.: Claude CLI timed out during version check")

    def _probe_ollama(self):
        """Check if Ollama is reachable."""
        import urllib.request
        ollama_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
        try:
            req = urllib.request.Request(f"{ollama_url}/api/tags", headers={"User-Agent": "ShadowLens/1.0"})
            resp = urllib.request.urlopen(req, timeout=5)
            if resp.status == 200:
                self._ollama_available = True
                logger.info(f"F.R.I.D.A.Y.: Ollama reachable at {ollama_url}")
            else:
                logger.warning(f"F.R.I.D.A.Y.: Ollama returned status {resp.status}")
        except Exception as e:
            logger.debug(f"F.R.I.D.A.Y.: Ollama not reachable at {ollama_url}: {e}")

    # ------------------------------------------------------------------
    # Claude CLI interface
    # ------------------------------------------------------------------

    def _call_claude(self, prompt: str, use_tools: bool = False, timeout: int = 120) -> str:
        """Call Claude Code CLI and return the response.

        Args:
            prompt: Full prompt text
            use_tools: If True, allow Claude to use Bash, Read, WebSearch, HexStrike MCP etc.
                       If False, text-only response (faster).
            timeout: Max seconds to wait
        """
        cmd = [
            self._claude_path,
            "-p", prompt,
            "--output-format", "text",
        ]

        if use_tools:
            # Load HexStrike MCP server for advanced security tooling
            hexstrike_config = Path(__file__).parent / "hexstrike_mcp.json"
            if hexstrike_config.exists():
                cmd.extend(["--mcp-config", str(hexstrike_config)])

            # Allow research tools + all HexStrike MCP tools
            cmd.extend([
                "--allowedTools",
                "Bash(grep:*) Bash(curl:*) Bash(nmap:*) Bash(whois:*) "
                "Bash(dig:*) Bash(host:*) Bash(nuclei:*) Bash(whatweb:*) "
                "Bash(sherlock:*) Bash(theHarvester:*) Bash(subfinder:*) "
                "Bash(dnsrecon:*) Bash(shodan:*) Bash(holehe:*) Bash(maigret:*) "
                "Bash(dmitry:*) Bash(emailharvester:*) Bash(phoneinfoga:*) "
                "Read WebSearch WebFetch Grep Glob "
                "mcp__hexstrike-ai__*",
                "--max-turns", "15",
                "--dangerously-skip-permissions",
            ])
        else:
            cmd.extend(["--tools", ""])

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                env={**os.environ},
            )
            if result.returncode == 0:
                return result.stdout.strip()
            else:
                logger.error(f"F.R.I.D.A.Y.: Claude CLI error (rc={result.returncode}): {result.stderr[:500]}")
                return "[F.R.I.D.A.Y. Error] Claude returned an error. Please try again."
        except subprocess.TimeoutExpired:
            logger.error(f"F.R.I.D.A.Y.: Claude CLI timed out ({timeout}s)")
            return "[F.R.I.D.A.Y. Error] Analysis timed out. Try a more specific question."
        except Exception as e:
            logger.error(f"F.R.I.D.A.Y.: Claude CLI exception: {e}")
            return f"[F.R.I.D.A.Y. Error] Failed to reach Claude: {e}"

    def _call_ollama(self, prompt: str, timeout: int = 120) -> str:
        """Call Ollama chat API and return the response.

        Uses /api/chat with a strict system prompt to reduce hallucination.
        The user prompt is expected to contain all entity data inline.
        """
        import urllib.request
        ollama_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
        model = os.environ.get("OLLAMA_MODEL", "llama3")

        system_msg = (
            "You are F.R.I.D.A.Y., an intelligence analysis AI. "
            "CRITICAL RULES:\n"
            "1. ONLY use data explicitly provided in the user message. NEVER invent, guess, or hallucinate any values.\n"
            "2. If a field is not in the provided data, say 'not available' — do NOT make up a value.\n"
            "3. Quote exact values from the data (callsigns, registrations, coordinates, speeds, altitudes).\n"
            "4. If the data says the aircraft is a Boeing 767, do NOT say it is an Airbus. Use EXACT data.\n"
            "5. Keep your analysis concise and grounded in the provided facts."
        )

        try:
            payload = json.dumps({
                "model": model,
                "messages": [
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": prompt},
                ],
                "stream": False,
                "options": {"num_predict": 2048, "temperature": 0.3},
            }).encode()
            req = urllib.request.Request(
                f"{ollama_url}/api/chat",
                data=payload,
                headers={"Content-Type": "application/json", "User-Agent": "ShadowLens/1.0"},
                method="POST",
            )
            resp = urllib.request.urlopen(req, timeout=timeout)
            data = json.loads(resp.read())
            msg = data.get("message", {})
            return msg.get("content", "").strip() if isinstance(msg, dict) else ""
        except Exception as e:
            logger.error(f"F.R.I.D.A.Y.: Ollama error: {e}")
            return f"[F.R.I.D.A.Y. Error] Ollama request failed: {e}"

    def _call_llm(self, prompt: str, use_tools: bool = False, timeout: int = 120) -> str:
        """Route to the active LLM provider."""
        provider = self._llm_provider
        if provider == "ollama" and self._ollama_available:
            # Ollama doesn't support tool use — fall back to Claude for OSINT tool calls
            if use_tools and self._claude_path:
                return self._call_claude(prompt, use_tools=True, timeout=timeout)
            return self._call_ollama(prompt, timeout=timeout)
        if self._claude_path:
            return self._call_claude(prompt, use_tools=use_tools, timeout=timeout)
        if self._ollama_available:
            return self._call_ollama(prompt, timeout=timeout)
        return "[F.R.I.D.A.Y. Error] No LLM backend available. Configure Claude Code CLI or Ollama."

    def _needs_osint(self, question: str) -> bool:
        """Detect if the question requires OSINT tools or web research."""
        q = question.lower()
        return any(kw in q for kw in OSINT_KEYWORDS)

    def _needs_locate(self, question: str) -> bool:
        """Detect if the question is a location/mapping request."""
        q = question.lower()
        # Check keywords
        if any(kw in q for kw in LOCATE_KEYWORDS):
            return True
        # Check for street address in the question
        if ADDRESS_PATTERN.search(question):
            return True
        # Check for "city, ST" or "city, ST ZIP" pattern
        if re.search(r'\b[A-Z][a-z]+,?\s+[A-Z]{2}\b(?:\s+\d{5})?', question):
            return True
        return False

    def _needs_wireless(self, question: str) -> bool:
        """Detect if the question is a wireless device discovery request."""
        q = question.lower()
        return any(kw in q for kw in WIRELESS_KEYWORDS)

    def _needs_camera(self, question: str) -> bool:
        """Detect if the question is a camera/webcam discovery request."""
        q = question.lower()
        return any(kw in q for kw in CAMERA_KEYWORDS)

    def _search_webcams(self, lat: float, lon: float, radius_km: int = 50, limit: int = 10) -> list:
        """Search for webcams near coordinates using Windy Webcams API v3."""
        import urllib.request
        api_key = os.environ.get("WINDY_WEBCAMS_API_KEY", "")
        if not api_key:
            return []
        try:
            url = (
                f"https://api.windy.com/webcams/api/v3/webcams"
                f"?nearby={lat},{lon},{radius_km}"
                f"&include=images,location,player,urls"
                f"&limit={limit}&lang=en"
            )
            req = urllib.request.Request(url, headers={
                "X-WINDY-API-KEY": api_key,
                "User-Agent": "ShadowLens/1.0",
            })
            resp = urllib.request.urlopen(req, timeout=10)
            data = json.loads(resp.read())
            webcams = data.get("webcams", [])
            results = []
            for cam in webcams:
                loc = cam.get("location", {})
                player = cam.get("player", {})
                images = cam.get("images", {})
                current_img = images.get("current", {})
                embed_url = player.get("day", "")
                thumbnail = current_img.get("icon", "") or current_img.get("small", "")
                results.append({
                    "lat": loc.get("latitude"),
                    "lon": loc.get("longitude"),
                    "label": cam.get("title", "Webcam"),
                    "source": "windy_webcam",
                    "webcam_id": cam.get("webcamId"),
                    "city": loc.get("city", ""),
                    "country": loc.get("country", ""),
                    "embed_url": embed_url,
                    "thumbnail": thumbnail,
                    "media_url": embed_url,
                    "media_type": "embed",
                    "status": cam.get("status", ""),
                })
            return results
        except Exception as e:
            logger.warning(f"Windy webcam search failed: {e}")
            return []

    def _detect_entity_type(self, context_data: str) -> Optional[str]:
        """Parse context JSON and return the entity type, or None."""
        try:
            data = json.loads(context_data)
            return data.get('type')
        except (json.JSONDecodeError, AttributeError):
            return None

    def _is_scan_entity(self, entity_type: Optional[str]) -> bool:
        """Check if entity type is a security scan that needs the 3-stage pipeline."""
        return entity_type in SCAN_ENTITY_TYPES

    def _has_raw_scan_data(self, context: str) -> bool:
        """Check if the context contains actual raw scan output (not just JSON metadata).
        Raw nmap output has 'PORT' headers, BloodHound has specific JSON keys, etc."""
        # Nmap raw output markers
        if 'PORT' in context and 'STATE' in context and 'SERVICE' in context:
            return True
        if 'Nmap scan report' in context:
            return True
        # BloodHound markers
        if '"BloodHound"' in context or '"attack_paths"' in context:
            return True
        # Volatility markers
        if 'Volatility' in context and ('PID' in context or 'Offset' in context):
            return True
        return False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract_facts(self, scan_data: str, module: str = "nmap") -> dict:
        """Stage A: Deterministic fact extraction from scan output."""
        extractor = self.fact_extractors.get(module)
        if not extractor:
            return {"error": f"No extractor for module '{module}'"}
        if module == 'bloodhound':
            try:
                json_data = json.loads(scan_data)
            except json.JSONDecodeError:
                return {"error": "Invalid JSON for BloodHound analysis"}
            return extractor.extract_facts(json_data)
        else:
            return extractor.extract_facts(scan_data)

    def facts_to_text(self, facts: dict, module: str = "nmap") -> str:
        """Convert extracted facts to human-readable text."""
        extractor = self.fact_extractors.get(module)
        if not extractor:
            return str(facts)
        return extractor.facts_to_text(facts)

    def _format_history(self, history: list) -> str:
        """Format conversation history for inclusion in prompts."""
        if not history:
            return ""
        # Take last 8 messages max to avoid prompt bloat
        recent = history[-8:]
        lines = ["CONVERSATION HISTORY:"]
        for msg in recent:
            role = msg.get('role', 'user').upper()
            content = msg.get('content', '')
            # Truncate long messages in history
            if len(content) > 500:
                content = content[:500] + "..."
            label = "User" if role == "USER" else "F.R.I.D.A.Y."
            lines.append(f"{label}: {content}")
        lines.append("")
        return "\n".join(lines)

    def chat(self, question: str, context: str = "", history: list = None) -> dict:
        """General-purpose F.R.I.D.A.Y. chat — handles ANY question with optional entity context.

        This is the main entry point. It auto-detects:
          - Security scan data → 3-stage RAG pipeline with validation
          - Entity context (flights, ships, etc.) → Claude analysis with context
          - OSINT requests → Claude with tool access
          - General questions → Claude direct answer

        Args:
            question: User's question
            context: JSON string of entity data, scan data, or empty for general queries
            history: List of prior messages [{role: 'user'|'assistant', content: str}]

        Returns:
            { 'answer': str, 'mode': str, 'validated': bool, 'issues': list, 'facts_summary': str }
        """
        if not self.ready:
            return {"error": "F.R.I.D.A.Y. engine not ready. Still loading.", "ready": False}
        if not self.llm and not self._ollama_available:
            return {"error": "No LLM backend available. Configure Claude Code CLI or Ollama.", "ready": True}

        entity_type = self._detect_entity_type(context)
        needs_osint = self._needs_osint(question)
        needs_locate = self._needs_locate(question)
        needs_camera = self._needs_camera(question)
        needs_wireless = self._needs_wireless(question)
        hist = history or []

        # Route 0a: Fast-path for cert/subdomain/IOC queries (no LLM needed)
        fast_result = self._try_fast_osint(question)
        if fast_result:
            return fast_result

        # Route 0b: Wireless device discovery — Wigle WiFi/BT search
        if needs_wireless:
            return self._handle_wireless_query(question, context, hist)

        # Route 0c: Camera/webcam discovery — find live feeds near a location
        if needs_camera:
            return self._handle_camera_query(question, context, hist)

        # Route 1: OSINT request — enable tools (highest priority, user is asking for action)
        if needs_osint:
            return self._handle_osint_query(question, context, hist)

        # Route 2: Location/mapping request — geocode and plot on map
        if needs_locate:
            return self._handle_locate_query(question, context, hist)

        # Route 3: Security scan data with raw scan output — full 3-stage pipeline
        # Only use if we detect actual scan output (not just entity JSON metadata)
        if self._is_scan_entity(entity_type) and self._has_raw_scan_data(context):
            return self._handle_scan_query(question, context, entity_type)

        # Route 4: Any entity context (including scan entities without raw data) — Claude analysis
        if context and entity_type and entity_type not in ('general', 'none'):
            return self._handle_entity_query(question, context, entity_type, hist)

        # Route 5: General question — Claude direct (pass context for live data awareness)
        return self._handle_general_query(question, context, hist)

    def _handle_scan_query(self, question: str, scan_data: str, entity_type: str) -> dict:
        """3-stage pipeline for security scan entities."""
        # Map entity type to module
        module = 'nmap'  # default
        if entity_type == 'bloodhound_data':
            module = 'bloodhound'

        facts = self.extract_facts(scan_data, module)
        if "error" in facts:
            # Fall back to direct Claude analysis if extractor fails
            return self._handle_entity_query(question, scan_data, entity_type)

        facts_text = self.facts_to_text(facts, module)
        context_text = self._rag_retrieve(question, module)
        system_prompt = self._build_scan_prompt(module, facts_text, context_text)
        user_message = f"Question: {question}\n\nAnswer based on the facts above:"

        answer = self._call_llm(f"{system_prompt}\n\n---\n\n{user_message}")

        validation = self._validate(answer, facts, module)
        if not validation['valid']:
            blocked = "[BLOCKED - HALLUCINATION DETECTED]\n\nF.R.I.D.A.Y. mentioned data not in the scan:\n"
            for issue in validation['issues']:
                blocked += f"  - {issue}\n"
            blocked += f"\nOriginal answer: {answer[:300]}..."
            answer = blocked

        # Extract any IP/location references from scan analysis
        locations = self._extract_locations_from_answer(answer, question)

        result = {
            'answer': answer,
            'mode': 'scan_analysis',
            'validated': validation['valid'],
            'issues': validation['issues'],
            'facts_summary': facts_text[:500],
            'module': module,
        }
        if locations:
            result['locations'] = locations
        return result

    def _handle_entity_query(self, question: str, context: str, entity_type: str, history: list = None) -> dict:
        """Analyze any entity type — flights, ships, bases, threats, weather, etc."""
        # Extract entity identity from context for focused analysis
        entity_name = ""
        try:
            ctx_data = json.loads(context)
            entity_name = ctx_data.get('name') or ctx_data.get('callsign') or ctx_data.get('id') or ''
        except (json.JSONDecodeError, AttributeError):
            pass

        prompt = (
            "You are F.R.I.D.A.Y., an advanced intelligence analysis AI embedded in ShadowLens — "
            "a real-time global situational awareness platform.\n\n"
            "You have deep expertise in: OSINT, SIGINT, GEOINT, cybersecurity, aviation (ADS-B), "
            "maritime (AIS), military intelligence, threat analysis, and geopolitical assessment.\n\n"
            f"THE USER HAS SELECTED A SPECIFIC ENTITY: {entity_name} (type: {entity_type})\n"
            "YOUR PRIMARY TASK: Analyze THIS SPECIFIC ENTITY in detail. Do NOT give a general overview "
            "of all flights/ships/assets. Focus your entire analysis on the selected target.\n\n"
            "The JSON below contains:\n"
            "- Top-level fields (type, id, name, callsign, etc.) = THE SELECTED ENTITY — this is your primary focus\n"
            "- 'active_data' field (if present) = background situational awareness from other live feeds. "
            "Only reference this for regional context or if the user asks about the broader picture.\n\n"
            "ENTITY & CONTEXT DATA:\n"
            f"```json\n{context}\n```\n\n"
            "INSTRUCTIONS:\n"
            f"- Focus on {entity_name or 'the selected entity'} — analyze it specifically and thoroughly\n"
            "- Use ALL entity fields: coordinates, IDs, callsigns, registration, altitude, speed, route, flags, metadata\n"
            "- For aircraft: identify the operator from callsign/registration, analyze the route (origin->destination), "
            "aircraft type capabilities, altitude/speed profile, any unusual patterns\n"
            "- For vessels: flag state risk, route patterns, AIS anomalies, vessel type, sanctions exposure\n"
            "- For facilities: strategic significance, regional context, threat landscape\n"
            "- For cyber threats: TTPs, attribution indicators, IOCs, mitigation\n"
            "- Only reference live news/social/GDELT feeds from active_data if they're directly relevant to this entity\n"
            "- Provide intelligence-grade analysis: what is it, why it matters, what to watch\n"
            "- Be concise but thorough. Do NOT pad with generic recommendations.\n"
        )

        # If user wants a location plotted, hint the LLM to output LOCATION: tags
        if self._needs_locate(question):
            prompt += (
                "\nIMPORTANT: If your answer references a specific geographic location, "
                "include a line in this exact format:\nLOCATION: <place name or address>\n"
                "This allows the platform to plot it on the map.\n"
            )

        prompt += (
            f"\n{self._format_history(history)}"
            f"---\n\nCurrent question: {question}"
        )
        answer = self._call_llm(prompt)

        # Extract any locations from the answer + entity context for map plotting
        locations = self._extract_locations_from_answer(answer, question)
        # Also try to get coordinates from the entity data itself
        if not locations:
            try:
                ctx = json.loads(context)
                lat = ctx.get('lat') or ctx.get('latitude')
                lon = ctx.get('lon') or ctx.get('lng') or ctx.get('longitude')
                if lat is not None and lon is not None:
                    name = ctx.get('name') or ctx.get('callsign') or ctx.get('id') or entity_type
                    locations.append({"lat": float(lat), "lon": float(lon), "label": str(name), "source": "entity"})
            except (json.JSONDecodeError, ValueError, TypeError):
                pass

        result = {
            'answer': answer,
            'mode': 'entity_analysis',
            'validated': True,
            'issues': [],
            'facts_summary': f"Entity type: {entity_type}",
        }
        if locations:
            result['locations'] = locations
        return result

    def _geocode_location(self, location_text: str) -> dict | None:
        """Geocode a place name / address using OpenStreetMap Nominatim. Returns {lat, lon, label, source} or None."""
        import urllib.request
        import urllib.parse
        try:
            q = urllib.parse.quote(location_text)
            url = f"https://nominatim.openstreetmap.org/search?q={q}&format=json&limit=1"
            req = urllib.request.Request(url, headers={"User-Agent": "ShadowLens/1.0"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read())
                if data and len(data) > 0:
                    lat = float(data[0]["lat"])
                    lon = float(data[0]["lon"])
                    display = data[0].get("display_name", location_text)
                    return {"lat": lat, "lon": lon, "label": display, "source": "geocode"}
        except Exception:
            pass
        return None

    def _geolocate_ip(self, ip: str) -> dict | None:
        """Geolocate an IP address using ip-api.com. Returns {lat, lon, label, source} or None."""
        import urllib.request
        try:
            url = f"http://ip-api.com/json/{ip}?fields=status,country,regionName,city,lat,lon,isp"
            req = urllib.request.Request(url, headers={"User-Agent": "ShadowLens/1.0"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read())
                if data.get("status") == "success" and data.get("lat"):
                    city = data.get("city", "")
                    region = data.get("regionName", "")
                    country = data.get("country", "")
                    label = f"{ip} — {', '.join(filter(None, [city, region, country]))}"
                    return {"lat": data["lat"], "lon": data["lon"], "label": label, "source": "ip-api"}
        except Exception:
            pass
        return None

    def _extract_locations_from_answer(self, answer: str, question: str) -> list:
        """Extract geolocatable data (IPs, coordinates) from F.R.I.D.A.Y.'s OSINT response."""
        locations = []
        seen = set()

        # Extract IPs mentioned in the answer (skip private/loopback)
        ip_pattern = re.compile(r'\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b')
        for match in ip_pattern.finditer(answer):
            ip = match.group(1)
            if ip in seen:
                continue
            # Skip loopback, link-local, and common non-routable
            octets = ip.split('.')
            first = int(octets[0])
            if first in (0, 127, 169, 224, 225, 226, 227, 228, 229, 230, 231, 232, 233, 234, 235, 236, 237, 238, 239, 240, 255):
                continue
            # Skip RFC1918 private ranges
            if first == 10 or (first == 172 and 16 <= int(octets[1]) <= 31) or (first == 192 and int(octets[1]) == 168):
                continue
            seen.add(ip)
            loc = self._geolocate_ip(ip)
            if loc:
                locations.append(loc)

        # Also try to geolocate the query target itself if it looks like an IP
        q_stripped = question.strip()
        ip_match = ip_pattern.match(q_stripped.split()[-1] if q_stripped else "")
        if ip_match and ip_match.group(1) not in seen:
            loc = self._geolocate_ip(ip_match.group(1))
            if loc:
                locations.append(loc)

        # Extract explicit coordinates — multiple formats:
        # "lat: 25.75, lon: 55.25" / "latitude: 25.75, longitude: 55.25"
        coord_pattern = re.compile(r'(?:lat(?:itude)?)[:\s]+(-?\d+\.?\d*)[,\s]+(?:lon(?:gitude)?|lng)[:\s]+(-?\d+\.?\d*)', re.IGNORECASE)
        for m in coord_pattern.finditer(answer):
            lat, lon = float(m.group(1)), float(m.group(2))
            if -90 <= lat <= 90 and -180 <= lon <= 180:
                locations.append({"lat": lat, "lon": lon, "label": f"Coordinates ({lat:.4f}, {lon:.4f})", "source": "extracted"})

        # "25.75°N, 55.25°E" / "25.75° N, 55.25° E" / "25.75N 55.25E"
        deg_pattern = re.compile(r'(-?\d+\.?\d*)\s*°?\s*([NSns])\s*[,\s]+\s*(-?\d+\.?\d*)\s*°?\s*([EWew])')
        for m in deg_pattern.finditer(answer):
            lat = float(m.group(1)) * (-1 if m.group(2).upper() == 'S' else 1)
            lon = float(m.group(3)) * (-1 if m.group(4).upper() == 'W' else 1)
            if -90 <= lat <= 90 and -180 <= lon <= 180:
                key = f"{lat:.4f},{lon:.4f}"
                if key not in seen:
                    seen.add(key)
                    locations.append({"lat": lat, "lon": lon, "label": f"Coordinates ({lat:.4f}, {lon:.4f})", "source": "extracted"})

        # Bare coordinate pairs: (25.75, 55.25) or 25.75, 55.25
        bare_coord = re.compile(r'(?<!\d)(-?\d{1,3}\.\d{2,6})\s*[,\s]\s*(-?\d{1,3}\.\d{2,6})(?!\d)')
        for m in bare_coord.finditer(answer):
            lat, lon = float(m.group(1)), float(m.group(2))
            if -90 <= lat <= 90 and -180 <= lon <= 180 and not (lat == 0 and lon == 0):
                key = f"{lat:.4f},{lon:.4f}"
                if key not in seen:
                    seen.add(key)
                    locations.append({"lat": lat, "lon": lon, "label": f"Coordinates ({lat:.4f}, {lon:.4f})", "source": "extracted"})

        # Extract LOCATION: tags (structured output from the prompt)
        loc_pattern = re.compile(r'LOCATION:\s*(.+?)(?:\n|$)', re.IGNORECASE)
        geocoded_texts = set()
        for m in loc_pattern.finditer(answer):
            raw_loc = m.group(1).strip().rstrip('.').strip('*').strip()

            # First: try to extract coordinates directly from the LOCATION line
            # Handles: "Persian Gulf, 25.811, 54.833" or "Kharg Island (26.2, 50.3)"
            loc_has_coords = False
            for cp in [deg_pattern, bare_coord]:
                for cm in cp.finditer(raw_loc):
                    if cp == deg_pattern:
                        clat = float(cm.group(1)) * (-1 if cm.group(2).upper() == 'S' else 1)
                        clon = float(cm.group(3)) * (-1 if cm.group(4).upper() == 'W' else 1)
                    else:
                        clat, clon = float(cm.group(1)), float(cm.group(2))
                    if -90 <= clat <= 90 and -180 <= clon <= 180 and not (clat == 0 and clon == 0):
                        key = f"{clat:.4f},{clon:.4f}"
                        if key not in seen:
                            seen.add(key)
                            # Use the place name part as the label
                            label = re.sub(r'[\d.,°NSEW\s]+$', '', raw_loc).strip(' ,') or f"({clat:.4f}, {clon:.4f})"
                            locations.append({"lat": clat, "lon": clon, "label": label, "source": "extracted"})
                            loc_has_coords = True

            # If no coords found in the LOCATION line, clean it up and geocode the place name
            if not loc_has_coords:
                loc_text = raw_loc
                loc_text = re.sub(r'\(.*?\)', '', loc_text).strip()
                loc_text = re.sub(r'approximately\s*', '', loc_text, flags=re.IGNORECASE).strip()
                loc_text = re.sub(r'\d+\.?\d*°?\s*[NSEW],?\s*\d+\.?\d*°?\s*[NSEW]', '', loc_text).strip()
                loc_text = re.sub(r'-?\d+\.?\d*\s*,\s*-?\d+\.?\d*', '', loc_text).strip()  # remove bare coords
                loc_text = loc_text.strip(' ,')
                if loc_text and loc_text not in geocoded_texts and len(loc_text) > 3:
                    geocoded_texts.add(loc_text)
                    loc = self._geocode_location(loc_text)
                    if loc:
                        locations.append(loc)

        # If no locations found yet, try to extract US city/state patterns from the text
        if not locations:
            city_state = re.compile(r'\b([A-Z][a-z]+(?:\s[A-Z][a-z]+)*),\s*([A-Z]{2})\b')
            for m in city_state.finditer(answer):
                loc_text = f"{m.group(1)}, {m.group(2)}"
                if loc_text not in geocoded_texts:
                    geocoded_texts.add(loc_text)
                    loc = self._geocode_location(loc_text)
                    if loc:
                        locations.append(loc)
                    if len(locations) >= 3:
                        break

        return locations[:20]  # Cap at 20 to avoid huge payloads

    def _try_fast_osint(self, question: str) -> dict | None:
        """Fast-path for queries that can be answered without the LLM.

        Handles: subdomain discovery, cert info, IOC extraction.
        Returns None if the query doesn't match a fast-path.
        """
        import concurrent.futures
        import asyncio
        from runners.ioc_extractor import IocExtractorRunner

        q = question.lower()
        runner = IocExtractorRunner()

        # Subdomain / cert transparency queries
        if any(kw in q for kw in ['subdomain', 'crt.sh', 'cert transparency', 'certificate transparency']):
            # Extract domain from question
            domain = self._extract_domain_from_question(q)
            if domain:
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    result = pool.submit(lambda: asyncio.run(runner.cert_transparency(domain))).result()
                subs = result.get("subdomains", [])
                if subs:
                    sub_list = "\n".join([f"- `{s}`" for s in subs])
                    answer = f"Found **{len(subs)} subdomain(s)** for `{domain}` via certificate transparency (crt.sh):\n\n{sub_list}"
                else:
                    answer = f"No subdomains found for `{domain}` via crt.sh."
                return {"answer": answer, "mode": "fast_osint", "query": question, "validated": True, "issues": [], "facts_summary": f"{len(subs)} subdomains for {domain}"}

        # SSL cert info queries
        if any(kw in q for kw in ['ssl cert', 'certificate info', 'cert info', 'tls cert']):
            domain = self._extract_domain_from_question(q)
            if domain:
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    result = pool.submit(lambda: asyncio.run(runner.ssl_cert_info(domain))).result()
                if result.get("status") == "ok":
                    sans = result.get("sans", [])
                    answer = (
                        f"**SSL Certificate for `{domain}`**\n\n"
                        f"| Field | Value |\n|---|---|\n"
                        f"| Subject | {result.get('subject_cn', 'N/A')} |\n"
                        f"| Issuer | {result.get('issuer_cn', '')} ({result.get('issuer_org', '')}) |\n"
                        f"| Valid From | {result.get('not_before', 'N/A')} |\n"
                        f"| Valid Until | {result.get('not_after', 'N/A')} |\n"
                        f"| Serial | {result.get('serial_number', 'N/A')} |\n"
                        f"| SANs | {len(sans)} entries |\n"
                    )
                    if sans:
                        answer += f"\n**Subject Alternative Names:**\n" + "\n".join([f"- `{s}`" for s in sans[:20]])
                else:
                    answer = f"Could not retrieve SSL certificate for `{domain}`: {result.get('error', 'unknown error')}"
                return {"answer": answer, "mode": "fast_osint", "query": question, "validated": True, "issues": [], "facts_summary": f"SSL cert for {domain}"}

        # IOC extraction from pasted text
        if any(kw in q for kw in ['extract ioc', 'find ioc', 'indicators of compromise', 'parse ioc']):
            # The IOC text is the question itself (user pastes text)
            from runners.ioc_extractor import extract_iocs
            result = extract_iocs(question)
            if result.get("total", 0) > 0:
                parts = []
                for key, label in [("ips", "IPs"), ("domains", "Domains"), ("emails", "Emails"),
                                    ("urls", "URLs"), ("hashes", "Hashes"), ("cves", "CVEs")]:
                    items = result.get(key, [])
                    if items:
                        parts.append(f"**{label} ({len(items)}):**\n" + "\n".join([f"- `{i}`" for i in items[:15]]))
                answer = f"Extracted **{result['total']} IOC(s)**:\n\n" + "\n\n".join(parts)
            else:
                answer = "No IOCs found in the provided text."
            return {"answer": answer, "mode": "fast_osint", "query": question, "validated": True, "issues": [], "facts_summary": f"{result.get('total', 0)} IOCs extracted"}

        # Quick email scan — fast checks only, offer deep search after
        import re as _re
        email_in_q = _re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', question)
        if email_in_q and any(kw in q for kw in ['find ', 'search ', 'scan ', 'check ', 'lookup ', 'look up']):
            email = email_in_q.group(0)
            import urllib.request
            parts = [f"**Quick Scan for `{email}`:**\n"]
            tools_run = []

            # Google check (fast — single HTTP request)
            try:
                resp = urllib.request.urlopen(
                    f"http://localhost:8002/google/email-check/{email}", timeout=10)
                gcheck = json.loads(resp.read())
                reg = gcheck.get("google_registered", False)
                parts.append(f"- Google: **{'Registered' if reg else 'Not registered'}**")
                tools_run.append("google_check")
            except Exception:
                parts.append("- Google: check failed")

            # Hudson Rock (fast — single HTTP request)
            try:
                payload = json.dumps({"target": email, "is_email": True}).encode()
                req = urllib.request.Request(
                    "http://localhost:8002/user-scanner/hudson-rock",
                    data=payload, headers={"Content-Type": "application/json"}, method="POST")
                resp = urllib.request.urlopen(req, timeout=15)
                hudson = json.loads(resp.read())
                infections = hudson.get("infections_found", 0)
                if infections:
                    parts.append(f"- **INFOSTEALER: {infections} infection(s) detected!**")
                    for s in hudson.get("stealers", [])[:3]:
                        parts.append(f"  - {s.get('stealer_family', '?')} — {s.get('date_compromised', '?')[:10]} — {s.get('operating_system', '?')}")
                else:
                    parts.append("- Hudson Rock: No infostealer infections")
                tools_run.append("hudson_rock")
            except Exception:
                parts.append("- Hudson Rock: check failed")

            # HIBP breach check (fast — single HTTP request)
            try:
                req = urllib.request.Request(
                    f"https://haveibeenpwned.com/api/v2/breachedaccount/{email}",
                    headers={"User-Agent": "ShadowLens/1.0"})
                resp = urllib.request.urlopen(req, timeout=10)
                breaches = json.loads(resp.read())
                if breaches:
                    breach_names = [b.get("Name", "?") for b in breaches[:10]]
                    parts.append(f"- HIBP: **{len(breaches)} breach(es)** — {', '.join(breach_names)}")
                tools_run.append("hibp")
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    parts.append("- HIBP: No breaches found")
                    tools_run.append("hibp")
                elif e.code == 401:
                    parts.append("- HIBP: API key required for full results")
            except Exception:
                pass

            parts.append(f"\n*Quick scan complete ({len(tools_run)} checks). Say **\"deep scan {email}\"** for full 107-platform account discovery + credential analysis.*")
            return {"answer": "\n".join(parts), "mode": "fast_osint", "query": question, "validated": True, "issues": [], "facts_summary": f"Quick scan: {email}"}

        # Deep scan — full 107-platform scan (user explicitly asked for deep)
        if any(kw in q for kw in ['deep scan', 'deep search', 'full scan']) and email_in_q:
            email = email_in_q.group(0)
            import urllib.request
            try:
                payload = json.dumps({"query": email}).encode()
                req = urllib.request.Request(
                    "http://localhost:8002/search",
                    data=payload, headers={"Content-Type": "application/json"}, method="POST")
                resp = urllib.request.urlopen(req, timeout=300)
                result = json.loads(resp.read())
                summary = result.get("summary", "No results")
                results_data = result.get("results", {})
                parts = [f"**Deep OSINT Scan for `{email}`:**\n"]
                uscan = results_data.get("user_scanner", {})
                if uscan.get("total_found"):
                    parts.append(f"- Accounts found: **{uscan['total_found']}** across {uscan.get('total_checked', '?')} platforms")
                    for cat, items in uscan.get("by_category", {}).items():
                        sites = ", ".join([i.get("site_name", "?") for i in items[:5]])
                        parts.append(f"  - {cat}: {sites}")
                hudson = results_data.get("hudson_rock", {})
                if hudson.get("infections_found"):
                    parts.append(f"- **INFOSTEALER: {hudson['infections_found']} infection(s)**")
                holehe = results_data.get("holehe", {})
                if holehe.get("registered_on"):
                    parts.append(f"- holehe: {', '.join(holehe['registered_on'][:10])}")
                gcheck = results_data.get("google_check", {})
                if gcheck.get("google_registered") is not None:
                    parts.append(f"- Google: {'Registered' if gcheck['google_registered'] else 'Not registered'}")
                if len(parts) == 1:
                    parts.append("- No significant findings")
                parts.append(f"\n*{len(result.get('tools_run', []))} tools executed*")
                return {"answer": "\n".join(parts), "mode": "fast_osint", "query": question, "validated": True, "issues": [], "facts_summary": summary, "locations": result.get("locations", [])}
            except Exception as e:
                return {"answer": f"Deep scan failed: {e}", "mode": "fast_osint", "query": question, "validated": True, "issues": [], "facts_summary": ""}

        # IP threat enrichment — InternetDB + ThreatFox + Tor
        ip_match = _re.search(r'\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b', question)
        if ip_match and any(kw in q for kw in ['threat', 'vuln', 'ports', 'tor check', 'internetdb', 'enrich ip', 'check ip', 'scan ip']):
            ip = ip_match.group(1)
            import urllib.request
            try:
                resp = urllib.request.urlopen(f"http://localhost:8002/threat/ip/{ip}", timeout=15)
                result = json.loads(resp.read())
                idb = result.get("internetdb", {})
                tfox = result.get("threatfox", {})
                tor = result.get("tor", {})
                summary = result.get("summary", {})
                parts = [f"**Threat Intel for `{ip}`:**\n"]
                parts.append(f"- **Open Ports ({summary.get('ports', 0)}):** {', '.join(str(p) for p in idb.get('ports', [])[:20]) or 'none'}")
                if summary.get("vulns"):
                    parts.append(f"- **Vulnerabilities ({summary['vulns']}):** {', '.join(idb.get('vulns', [])[:10])}")
                if summary.get("hostnames"):
                    parts.append(f"- **Hostnames:** {', '.join(summary['hostnames'][:5])}")
                parts.append(f"- **Tor Exit Node:** {'YES' if summary.get('is_tor') else 'No'}")
                if summary.get("threat_iocs"):
                    parts.append(f"- **ThreatFox IOCs:** {summary['threat_iocs']} matching indicators")
                if idb.get("cpes"):
                    parts.append(f"- **CPEs:** {', '.join(idb['cpes'][:5])}")
                if idb.get("tags"):
                    parts.append(f"- **Tags:** {', '.join(idb['tags'])}")
                return {"answer": "\n".join(parts), "mode": "fast_osint", "query": question, "validated": True, "issues": [], "facts_summary": f"IP: {ip} — {summary.get('ports',0)} ports, {summary.get('vulns',0)} vulns"}
            except Exception as e:
                pass  # Fall through to normal routing

        # Google email check
        if any(kw in q for kw in ['is this email on google', 'google email check', 'gmail check', 'check google']):
            import re
            email_match = re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', question)
            if email_match:
                from runners.google_osint import GoogleOsintRunner
                runner = GoogleOsintRunner()
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    result = pool.submit(lambda: asyncio.run(runner.check_google_email(email_match.group(0)))).result()
                registered = result.get("google_registered", False)
                email = email_match.group(0)
                answer = f"**Google Account Check for `{email}`:** {'Registered on Google' if registered else 'Not registered on Google'}"
                return {"answer": answer, "mode": "fast_osint", "query": question, "validated": True, "issues": [], "facts_summary": f"{email}: {'Google registered' if registered else 'not on Google'}"}

        # BSSID geolocation
        if any(kw in q for kw in ['geolocate bssid', 'bssid location', 'locate bssid', 'wifi mac', 'mac address location']):
            import re
            mac_match = re.search(r'([0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2}', question)
            if mac_match:
                from runners.google_osint import GoogleOsintRunner
                runner = GoogleOsintRunner()
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    result = pool.submit(lambda: asyncio.run(runner.geolocate_bssid(mac_match.group(0)))).result()
                if result.get("status") == "ok" and result.get("lat"):
                    answer = f"**WiFi AP Geolocation for `{mac_match.group(0)}`:**\n\n- Latitude: {result['lat']}\n- Longitude: {result['lon']}\n- Accuracy: {result.get('accuracy_meters', '?')}m"
                    locations = [{"lat": result["lat"], "lon": result["lon"], "label": f"WiFi AP {mac_match.group(0)}", "source": "google_geolocation"}]
                    return {"answer": answer, "mode": "fast_osint", "query": question, "validated": True, "issues": [], "facts_summary": f"BSSID located", "locations": locations}
                else:
                    answer = f"**BSSID `{mac_match.group(0)}`:** Not found in Google's geolocation database."
                    return {"answer": answer, "mode": "fast_osint", "query": question, "validated": True, "issues": [], "facts_summary": "BSSID not found"}

        # Digital Asset Links
        if any(kw in q for kw in ['asset links', 'linked apps', 'android app for', 'what apps', 'app association']):
            domain = self._extract_domain_from_question(q)
            if domain:
                from runners.google_osint import GoogleOsintRunner
                runner = GoogleOsintRunner()
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    result = pool.submit(lambda: asyncio.run(runner.digital_asset_links(website=f"https://{domain}"))).result()
                links = result.get("links", [])
                if links:
                    app_links = [l for l in links if l.get("type") == "android_app"]
                    web_links = [l for l in links if l.get("type") == "website"]
                    parts = []
                    if app_links:
                        parts.append(f"**Android Apps ({len(app_links)}):**\n" + "\n".join([f"- `{l.get('package', '?')}`" for l in app_links[:15]]))
                    if web_links:
                        parts.append(f"**Linked Websites ({len(web_links)}):**\n" + "\n".join([f"- {l.get('site', '?')}" for l in web_links[:10]]))
                    answer = f"**Digital Asset Links for `{domain}`** — {len(links)} association(s):\n\n" + "\n\n".join(parts)
                else:
                    answer = f"No Digital Asset Links found for `{domain}`."
                return {"answer": answer, "mode": "fast_osint", "query": question, "validated": True, "issues": [], "facts_summary": f"{len(links)} asset links for {domain}"}

        return None

    def _extract_domain_from_question(self, question: str) -> str | None:
        """Extract a domain name from a natural language question."""
        import re
        # Try to find a domain pattern in the question
        domain_re = re.compile(r'\b([a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)*\.[a-zA-Z]{2,})\b')
        for m in domain_re.finditer(question):
            d = m.group(1).lower()
            # Skip common words that look like domains
            if d in ('crt.sh', 'wpa-sec.stanev.org'):
                continue
            if '.' in d and len(d) > 4:
                return d
        return None

    def _handle_wireless_query(self, question: str, context: str, history: list = None) -> dict:
        """Handle wireless device discovery — Wigle WiFi/Bluetooth search."""
        import asyncio
        from runners.wireless_osint import WirelessOsintRunner

        q_lower = question.lower()

        # Detect mode
        mode = "all"
        if any(kw in q_lower for kw in ["bluetooth", "bt device", "bt scan"]):
            mode = "bluetooth"
        elif any(kw in q_lower for kw in ["wifi", "wireless network", "ssid", "router"]):
            mode = "wifi"

        # Check for SSID/BSSID specific search
        import re
        ssid_match = re.search(r'ssid\s+["\']?([^"\']+)["\']?', q_lower)
        bssid_match = re.search(r'bssid\s+([0-9a-f:]{17})', q_lower, re.IGNORECASE)
        mac_match = re.search(r'([0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2}', question)

        runner = WirelessOsintRunner()

        if bssid_match or mac_match:
            bssid = (bssid_match or mac_match).group(0)
            result = asyncio.get_event_loop().run_in_executor(None, lambda: asyncio.run(runner.search_bssid(bssid)))
            # Can't nest event loops — use thread
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                result = pool.submit(lambda: asyncio.run(runner.search_bssid(bssid))).result()
            devices = result.get("devices", [])
            answer = f"Found **{len(devices)} result(s)** for BSSID `{bssid}`."
            if devices:
                answer += "\n\n" + "\n".join([f"- **{d.get('ssid', 'Unknown')}** ({d.get('vendor', '')}) at ({d.get('lat', 0):.4f}, {d.get('lon', 0):.4f})" for d in devices[:10]])
            locations = [{"lat": d["lat"], "lon": d["lon"], "label": d.get("ssid") or d.get("bssid", "Device"), "source": "wigle"} for d in devices if d.get("lat")]
            return {"answer": answer, "mode": "wireless_search", "query": question, "validated": True, "issues": [], "facts_summary": f"BSSID search: {bssid}", "locations": locations}

        if ssid_match:
            ssid = ssid_match.group(1).strip()
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                result = pool.submit(lambda: asyncio.run(runner.search_ssid(ssid))).result()
            devices = result.get("devices", [])
            answer = f"Found **{len(devices)} network(s)** matching SSID `{ssid}`."
            if devices:
                leaked = [d for d in devices if d.get("leaked")]
                if leaked:
                    answer += f"\n\n**WARNING: {len(leaked)} network(s) have leaked credentials (wpa-sec).**"
                answer += "\n\n" + "\n".join([f"- **{d.get('ssid')}** ({d.get('vendor', '')}) at ({d.get('lat', 0):.4f}, {d.get('lon', 0):.4f}){' — LEAKED' if d.get('leaked') else ''}" for d in devices[:15]])
            locations = [{"lat": d["lat"], "lon": d["lon"], "label": f"{'⚠ ' if d.get('leaked') else ''}{d.get('ssid', 'WiFi')}", "source": "wigle"} for d in devices if d.get("lat")]
            return {"answer": answer, "mode": "wireless_search", "query": question, "validated": True, "issues": [], "facts_summary": f"SSID search: {ssid}", "locations": locations}

        # Location-based search — extract coordinates
        lat, lon = None, None
        try:
            ctx = json.loads(context) if context else {}
            lat = ctx.get("lat") or ctx.get("latitude")
            lon = ctx.get("lon") or ctx.get("lng") or ctx.get("longitude")
            if lat and lon:
                lat, lon = float(lat), float(lon)
        except (json.JSONDecodeError, ValueError, TypeError):
            pass

        if not lat or not lon:
            # Try to geocode from the question
            location_text = q_lower
            for kw in WIRELESS_KEYWORDS:
                location_text = location_text.replace(kw, " ")
            noise = {"find", "show", "get", "scan", "search", "near", "around", "at", "in", "the", "a", "for", "devices", "networks"}
            words = [w for w in location_text.split() if w not in noise and not re.match(r"^\d+$", w)]
            location_text = " ".join(words).strip()
            if location_text:
                geo = self._geocode_location(location_text)
                if geo:
                    lat, lon = geo["lat"], geo["lon"]

        if not lat or not lon:
            return {"answer": "I couldn't determine the location. Try specifying a city or coordinates.", "mode": "wireless_search", "validated": True, "issues": [], "facts_summary": ""}

        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            result = pool.submit(lambda: asyncio.run(runner.search_nearby(lat, lon, mode, radius=0.01))).result()

        devices = result.get("devices", [])
        leaked_count = result.get("leaked_count", 0)

        if devices:
            by_type = {}
            for d in devices:
                t = d.get("device_type", "unknown")
                by_type.setdefault(t, []).append(d)

            type_summary = ", ".join([f"{len(v)} {k}" for k, v in sorted(by_type.items(), key=lambda x: -len(x[1]))])
            answer = f"Found **{len(devices)} wireless device(s)** near ({lat:.4f}, {lon:.4f}):\n\n"
            answer += f"**Breakdown:** {type_summary}\n"
            if leaked_count:
                answer += f"\n**⚠ {leaked_count} WiFi network(s) have leaked credentials (wpa-sec)**\n"
            answer += "\n**Top devices:**\n"
            for d in devices[:15]:
                leaked_flag = " — **LEAKED**" if d.get("leaked") else ""
                answer += f"- [{d.get('device_type', '?')}] **{d.get('ssid') or d.get('bssid', 'Unknown')}** ({d.get('vendor', '')}){leaked_flag}\n"
        else:
            answer = f"No wireless devices found near ({lat:.4f}, {lon:.4f}) via Wigle. The area may not have wardriving coverage."

        locations = [{"lat": d["lat"], "lon": d["lon"], "label": f"{'⚠ ' if d.get('leaked') else ''}{d.get('ssid') or d.get('bssid', 'Device')}", "source": "wigle"} for d in devices if d.get("lat")]

        return {
            "answer": answer,
            "mode": "wireless_search",
            "query": question,
            "validated": True,
            "issues": [],
            "facts_summary": f"Wireless search: {len(devices)} devices, {leaked_count} leaked",
            "locations": locations,
        }

    def _handle_camera_query(self, question: str, context: str, history: list = None) -> dict:
        """Handle camera/webcam discovery — find live feeds near a location."""
        # Parse requested count from the question (e.g. "find 5 cameras", "show me 10 webcams")
        count_match = re.search(r'\b(\d+)\s*(?:camera|webcam|cctv|feed|stream)', question.lower())
        if not count_match:
            count_match = re.search(r'(?:find|show|get|pull up)\s+(\d+)', question.lower())
        requested_limit = int(count_match.group(1)) if count_match else 50  # default: return all available up to 50

        # Extract location from the question by stripping camera-related words
        location_text = question.lower()
        # Sort keywords longest-first so longer phrases match before substrings
        sorted_kws = sorted(CAMERA_KEYWORDS, key=len, reverse=True)
        for kw in sorted_kws:
            location_text = location_text.replace(kw, ' ')
        # Strip all noise words that aren't part of place names
        noise = {'find', 'show', 'get', 'pull', 'up', 'me', 'feeds', 'feed', 'streams',
                 'stream', 'footage', 'cameras', 'camera', 'cctv', 'webcam', 'webcams',
                 'live', 'video', 'at', 'in', 'near', 'around', 'for', 'the', 'a', 'an',
                 'some', 'any', 'from', 'to', 'on', 'with'}
        words = location_text.split()
        # Remove noise words and standalone numbers/single chars
        cleaned = [w for w in words if w not in noise and not re.match(r'^(\d+|[a-z])$', w)]
        # Keep "of" only if it connects place name parts (e.g. "Strait of Hormuz")
        # Re-insert "of" between non-noise words
        final_words = []
        for i, w in enumerate(words):
            if w == 'of' and final_words and i + 1 < len(words) and words[i + 1] not in noise:
                final_words.append(w)
            elif w in cleaned:
                final_words.append(w)
        location_text = ' '.join(final_words).strip()
        location_text = re.sub(r'\s+', ' ', location_text).strip()

        # Try to get coords from entity context first
        lat, lon = None, None
        try:
            ctx = json.loads(context) if context else {}
            lat = ctx.get('lat') or ctx.get('latitude')
            lon = ctx.get('lon') or ctx.get('lng') or ctx.get('longitude')
            if lat and lon:
                lat, lon = float(lat), float(lon)
        except (json.JSONDecodeError, ValueError, TypeError):
            pass

        # If no coords from context, geocode the location text
        if not lat or not lon:
            if location_text:
                geo = self._geocode_location(location_text)
                if geo:
                    lat, lon = geo['lat'], geo['lon']

        if not lat or not lon:
            return {
                'answer': f"I couldn't determine the location for \"{location_text}\". Try specifying a city or address.",
                'mode': 'camera_search',
                'validated': True,
                'issues': [],
                'facts_summary': '',
            }

        # Search for webcams
        webcams = self._search_webcams(lat, lon, radius_km=250, limit=min(requested_limit, 50))

        # Also check existing CCTV feeds in the platform data
        existing_note = ""
        try:
            from services.data_fetcher import get_latest_data
            d = get_latest_data()
            nearby_cctv = []
            for c in d.get('cctv', []):
                clat = c.get('lat') or c.get('latitude')
                clng = c.get('lon') or c.get('lng')
                if clat and clng:
                    try:
                        dist = abs(float(clat) - lat) + abs(float(clng) - lon)
                        if dist < 1.0:  # roughly within ~100km
                            nearby_cctv.append(c)
                    except (ValueError, TypeError):
                        pass
            if nearby_cctv:
                existing_note = f"\n\nNote: {len(nearby_cctv)} existing CCTV feeds from the platform database are also near this location (visible on the CCTV layer)."
        except Exception:
            pass

        if webcams:
            cam_list = "\n".join([
                f"- **{c['label']}** ({c.get('city', '')}, {c.get('country', '')}) — [View feed]({c.get('embed_url', '')})"
                for c in webcams
            ])
            answer = (
                f"Found **{len(webcams)} live webcam(s)** near {location_text or f'{lat:.3f}, {lon:.3f}'}:\n\n"
                f"{cam_list}\n\n"
                f"Click any marker on the map to view the live feed."
                f"{existing_note}"
            )
            # Return webcams as locations with media data for map pins
            locations = []
            for c in webcams:
                locations.append({
                    "lat": c["lat"],
                    "lon": c["lon"],
                    "label": c["label"],
                    "source": "windy_webcam",
                    "media_url": c.get("embed_url", ""),
                    "media_type": "embed",
                    "thumbnail": c.get("thumbnail", ""),
                    "webcam_id": c.get("webcam_id"),
                })
        else:
            answer = (
                f"No public webcams found near {location_text or f'{lat:.3f}, {lon:.3f}'} "
                f"within 250km. Try a larger city or a different area."
                f"{existing_note}"
            )
            locations = [{"lat": lat, "lon": lon, "label": location_text or "Search area", "source": "geocode"}]

        return {
            'answer': answer,
            'mode': 'camera_search',
            'query': question,
            'validated': True,
            'issues': [],
            'facts_summary': f"Webcams near {location_text}",
            'locations': locations,
        }

    def _handle_osint_query(self, question: str, context: str, history: list = None) -> dict:
        """Handle OSINT requests — Claude with tool access for active research."""
        context_block = ""
        if context:
            entity_type = self._detect_entity_type(context)
            if entity_type and entity_type != 'general':
                context_block = f"\nCONTEXT (selected entity from ShadowLens):\n```json\n{context}\n```\n"

        prompt = (
            "You are F.R.I.D.A.Y., an OSINT and cybersecurity research AI.\n\n"
            "You have access to TWO tool systems:\n\n"
            "1. LOCAL CLI TOOLS (via Bash):\n"
            "  - nmap, nuclei, whatweb, theHarvester, sherlock, subfinder\n"
            "  - dnsrecon, whois, dig, host, shodan, holehe, maigret, dmitry, phoneinfoga\n\n"
            "2. HEXSTRIKE AI SECURITY PLATFORM (via MCP tools — prefixed mcp__hexstrike-ai__):\n"
            "  HexStrike provides 100+ advanced security tools. Key capabilities:\n"
            "  RECONNAISSANCE: nmap_scan, nmap_advanced_scan, rustscan_fast_scan, masscan_high_speed,\n"
            "    subfinder_scan, amass_scan, dnsenum_scan, fierce_scan, autorecon_comprehensive\n"
            "  WEB SCANNING: nikto_scan, gobuster_scan, dirb_scan, dirsearch_scan, feroxbuster_scan,\n"
            "    ffuf_scan, wfuzz_scan, nuclei_scan, dalfox_xss_scan, sqlmap_scan, xsser_scan\n"
            "  VULNERABILITY: ai_vulnerability_assessment, jaeles_vulnerability_scan, dotdotpwn_scan,\n"
            "    generate_exploit_from_cve, monitor_cve_feeds\n"
            "  OSINT/RECON: ai_reconnaissance_workflow, bugbounty_reconnaissance_workflow,\n"
            "    bugbounty_osint_gathering, paramspider_discovery, katana_crawl, hakrawler_crawl,\n"
            "    httpx_probe, waybackurls_discovery, gau_discovery\n"
            "  API TESTING: api_fuzzer, api_schema_analyzer, comprehensive_api_audit, graphql_scanner,\n"
            "    jwt_analyzer, arjun_parameter_discovery\n"
            "  EXPLOITATION: metasploit_run, hydra_attack, hashcat_crack, john_crack,\n"
            "    msfvenom_generate, responder_credential_harvest\n"
            "  BINARY/FORENSICS: ghidra_analysis, radare2_analyze, binwalk_analyze, volatility3_analyze,\n"
            "    gdb_analyze, checksec_analyze, ropgadget_search, pwntools_exploit\n"
            "  CLOUD/CONTAINER: trivy_scan, docker_bench_security_scan, kube_hunter_scan,\n"
            "    prowler_scan, scout_suite_assessment, checkov_iac_scan\n"
            "  AI-POWERED: ai_generate_attack_suite, ai_generate_payload, ai_test_payload,\n"
            "    intelligent_smart_scan, select_optimal_tools_ai, detect_technologies_ai,\n"
            "    analyze_target_intelligence, create_attack_chain_ai\n"
            "  WAF/DETECTION: wafw00f_scan, http_repeater, http_intruder, burpsuite_alternative_scan\n"
            "  SMB/AD: enum4linux_scan, enum4linux_ng_advanced, smbmap_scan, netexec_scan,\n"
            "    nbtscan_netbios, rpcclient_enumeration\n\n"
            "  PREFER HexStrike tools over local CLI when available — they are more capable,\n"
            "  have better output parsing, and support AI-enhanced analysis.\n\n"
            "You can also use WebSearch and WebFetch for research.\n\n"
            "RULES:\n"
            "- Only scan targets the user has authorized\n"
            "- Present findings clearly with actionable intelligence\n"
            "- If a tool isn't available, suggest alternatives\n"
            "- When you discover any IP addresses, domains, physical addresses, or geographic locations, "
            "mention them clearly in your response so they can be plotted on the map\n"
            "- For physical locations, always include a line formatted as: LOCATION: <city, state, country>\n"
            "  or LOCATION: <full address> — this enables automatic map plotting\n"
            "- You can include multiple LOCATION: lines for multiple places\n"
            f"{context_block}\n"
            f"{self._format_history(history)}"
            f"---\n\nUser request: {question}"
        )
        answer = self._call_llm(prompt, use_tools=True, timeout=600)

        # Extract geolocatable data from the response for map plotting
        locations = self._extract_locations_from_answer(answer, question)

        return {
            'answer': answer,
            'mode': 'osint_research',
            'validated': True,
            'issues': [],
            'facts_summary': 'OSINT research with tool access',
            'locations': locations,
            'query': question,
        }

    def _handle_locate_query(self, question: str, context: str = "", history: list = None) -> dict:
        """Handle location/mapping requests — geocode addresses, coordinates, places and return map-plottable locations."""
        locations = []

        # Try to extract addresses from the question directly
        # Full address with ZIP: "1087 Reynolds Bridge Rd, Benton TN 37042"
        addr_match = ADDRESS_PATTERN.search(question)
        # Also grab everything after the address-like start (city, state, zip)
        full_loc = question
        # Strip command words to get the location text
        for prefix in ['find ', 'locate ', 'plot ', 'map ', 'show ', 'go to ', 'fly to ', 'zoom to ', 'where is ', 'show me ']:
            if full_loc.lower().startswith(prefix):
                full_loc = full_loc[len(prefix):]
                break
        # Strip trailing instructions
        for suffix in [' on the map', ' on map', ' and plot', ' and show']:
            idx = full_loc.lower().find(suffix)
            if idx > 0:
                full_loc = full_loc[:idx]
        full_loc = full_loc.strip().rstrip('.')

        if full_loc:
            loc = self._geocode_location(full_loc)
            if loc:
                locations.append(loc)

        # If geocoding the full text failed, try the address pattern match
        if not locations and addr_match:
            loc = self._geocode_location(addr_match.group(0))
            if loc:
                locations.append(loc)

        # Build a response
        if locations:
            loc = locations[0]
            answer = (
                f"Located: **{loc['label']}**\n\n"
                f"Coordinates: {loc['lat']:.6f}, {loc['lon']:.6f}\n\n"
                f"LOCATION: {loc['label']}\n\n"
                f"Plotted on the map."
            )
        else:
            # Fall back to Claude for help identifying the location
            prompt = (
                "You are F.R.I.D.A.Y., an AI assistant. The user wants to find a location and plot it on a map.\n\n"
                "Identify the exact location from the user's query and respond with:\n"
                "1. The full address or place name\n"
                "2. A LOCATION: line with the place (e.g. LOCATION: 1087 Reynolds Bridge Rd, Benton, TN 37042)\n"
                "3. Any relevant context about the location\n\n"
                f"{self._format_history(history)}"
                f"---\n\nUser request: {question}"
            )
            answer = self._call_llm(prompt)
            # Try to extract locations from the LLM's response
            loc_pattern = re.compile(r'LOCATION:\s*(.+?)(?:\n|$)', re.IGNORECASE)
            for m in loc_pattern.finditer(answer):
                loc_text = m.group(1).strip().rstrip('.')
                if loc_text and len(loc_text) > 3:
                    loc = self._geocode_location(loc_text)
                    if loc:
                        locations.append(loc)

        return {
            'answer': answer,
            'mode': 'locate',
            'validated': True,
            'issues': [],
            'facts_summary': '',
            'locations': locations,
            'query': question,
        }

    def _handle_general_query(self, question: str, context: str = "", history: list = None) -> dict:
        """Handle general questions — may include live data context."""
        context_block = ""
        if context:
            context_block = (
                "\nIMPORTANT: The data below is LIVE, REAL-TIME data from the platform's active feeds. "
                "This includes live news headlines, social media posts, flight tracking, ship tracking, "
                "GDELT events, and other intelligence feeds collected RIGHT NOW. "
                "Fields like 'live_news_feed', 'live_social_feed', 'gdelt_global_events' contain current data — "
                "reference them directly when answering questions about current events or what's happening.\n\n"
                f"LIVE PLATFORM DATA:\n```json\n{context}\n```\n\n"
            )

        # If the question mentions a location/place, instruct the LLM to output a LOCATION: tag
        location_hint = ""
        if self._needs_locate(question):
            location_hint = (
                "\n\nIMPORTANT: If your answer references a specific geographic location, "
                "include a line in this exact format:\nLOCATION: <place name or address>\n"
                "This allows the platform to plot it on the map.\n"
            )

        prompt = (
            "You are F.R.I.D.A.Y., an advanced AI assistant embedded in ShadowLens — "
            "a real-time global intelligence and cybersecurity platform.\n\n"
            "You have expertise in: cybersecurity, penetration testing, OSINT, threat intelligence, "
            "network security, aviation tracking, maritime monitoring, geopolitical analysis, "
            "and military intelligence.\n\n"
            f"{context_block}"
            "Answer the user's question directly and concisely. Use your full knowledge "
            "and reference any live data provided above when relevant.\n\n"
            f"{location_hint}"
            f"{self._format_history(history)}"
            f"---\n\nCurrent question: {question}"
        )
        answer = self._call_llm(prompt)

        # Extract locations from the answer for map plotting
        locations = self._extract_locations_from_answer(answer, question)

        result = {
            'answer': answer,
            'mode': 'general',
            'validated': True,
            'issues': [],
            'facts_summary': '',
        }
        if locations:
            result['locations'] = locations
        return result

    def query(self, question: str, scan_data: str, module: str = "nmap") -> dict:
        """Legacy compatibility — routes through chat()."""
        return self.chat(question, scan_data)

    def analyze_nmap_results(self, nmap_xml: str) -> dict:
        """Quick analysis of Nmap results — facts + next steps, no LLM needed."""
        facts = self.extract_facts(nmap_xml, 'nmap')
        if "error" in facts:
            return facts

        facts_text = self.facts_to_text(facts, 'nmap')
        recommendations = []
        try:
            from nmap_advice import parse_nmap_text, plan_next_steps
            services = parse_nmap_text(nmap_xml)
            steps = plan_next_steps(services)
            for step in steps[:10]:
                recommendations.append({
                    'priority': step.priority if hasattr(step, 'priority') else 3,
                    'tool': step.tool if hasattr(step, 'tool') else '',
                    'command': step.command if hasattr(step, 'command') else '',
                    'description': step.description if hasattr(step, 'description') else str(step),
                    'reason': step.reason if hasattr(step, 'reason') else '',
                })
        except Exception as e:
            logger.debug(f"F.R.I.D.A.Y.: nmap_advice failed: {e}")

        return {
            'facts': facts,
            'facts_text': facts_text,
            'recommendations': recommendations,
            'host_count': len(facts.get('hosts', [])),
            'total_open_ports': sum(
                len(h.get('open_ports', [])) for h in facts.get('hosts', [])
            ),
        }

    def analyze_entity(self, context: str) -> dict:
        """Quick entity summary — used for auto-analyze on entity select."""
        entity_type = self._detect_entity_type(context)

        # For scan entities, use the deterministic pipeline
        if self._is_scan_entity(entity_type):
            return self.analyze_nmap_results(context)

        # For other entities, return formatted context as the summary
        try:
            data = json.loads(context)
            # Build a human-readable summary from entity fields
            lines = []
            entity_name = data.get('name') or data.get('callsign') or data.get('id', 'Unknown')
            etype = data.get('type', 'unknown')
            lines.append(f"Entity: {entity_name}")
            lines.append(f"Type: {etype}")

            # Include all meaningful fields
            skip_keys = {'type', 'id', 'name', 'callsign', 'extra'}
            for key, val in data.items():
                if key in skip_keys or val is None or val == '':
                    continue
                # Format key nicely
                label = key.replace('_', ' ').title()
                if isinstance(val, dict):
                    val = json.dumps(val, indent=2)
                lines.append(f"{label}: {val}")

            facts_text = "\n".join(lines)
            return {
                'facts_text': facts_text,
                'entity_type': etype,
                'entity_name': str(entity_name),
            }
        except (json.JSONDecodeError, AttributeError):
            return {'facts_text': context[:500]}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _rag_retrieve(self, question: str, module: str, k: int = 3) -> str:
        import faiss as faiss_lib
        import numpy as np
        if module not in self.faiss_indexes or not self.embed_model:
            return ""
        query_vec = self.embed_model.encode([question]).astype('float32')
        faiss_lib.normalize_L2(query_vec)
        distances, indices = self.faiss_indexes[module].search(query_vec, k)
        contexts = []
        chunks = self.chunks.get(module, [])
        for idx in indices[0]:
            if 0 <= idx < len(chunks):
                chunk = chunks[idx]
                text = chunk.get('content', str(chunk))
                contexts.append(text)
        return "\n\n".join(contexts)

    def _build_scan_prompt(self, module: str, facts_text: str, context_text: str) -> str:
        module_instructions = {
            'nmap': (
                "You are F.R.I.D.A.Y., an expert penetration testing analyst analyzing Nmap scan results.\n\n"
                "ANSWERING STRATEGY (3-Tier Approach):\n\n"
                "1. SPECIFIC SCAN DATA (Facts-First - NEVER Invent):\n"
                "   - For IPs, port numbers, versions, services: Use ONLY the facts below\n"
                "   - NEVER invent or guess IP addresses, port numbers, version strings\n"
                "   - If not in facts, say 'Not present in the facts'\n\n"
                "2. INFERENCE FROM EVIDENCE (Connect the Dots):\n"
                "   - OS Detection: 'Ubuntu' in banners = Linux, 'Microsoft' = Windows\n"
                "   - Service Synonyms: microsoft-ds = SMB, ms-wbt-server = RDP, domain = DNS\n"
                "   - Use phrases like: 'Based on the banners...' or 'The evidence suggests...'\n\n"
                "3. GENERAL SECURITY KNOWLEDGE (Explain Concepts):\n"
                "   - Definitions, standard practices, risk assessment\n"
                "   - Use phrases like: 'In penetration testing...' or 'Generally...'\n"
            ),
            'bloodhound': (
                "You are F.R.I.D.A.Y., an expert Active Directory penetration testing analyst.\n\n"
                "ANSWERING STRATEGY:\n"
                "1. Use ONLY the extracted facts for specific data (users, groups, ACLs)\n"
                "2. Identify attack paths and privilege escalation opportunities\n"
                "3. Provide actionable next steps for exploitation\n"
                "4. NEVER invent usernames, SIDs, or group memberships\n"
            ),
            'volatility': (
                "You are F.R.I.D.A.Y., an expert memory forensics analyst.\n\n"
                "ANSWERING STRATEGY:\n"
                "1. Use ONLY the extracted facts for specific data (PIDs, processes, IPs)\n"
                "2. Identify suspicious processes, injected code, and malware indicators\n"
                "3. Provide forensic analysis and attribution\n"
                "4. NEVER invent PIDs, process names, or IP addresses\n"
            ),
        }
        instruction = module_instructions.get(module, module_instructions['nmap'])
        return (
            f"{instruction}\n"
            f"FACTS FROM THIS SCAN:\n{facts_text}\n\n"
            f"KNOWLEDGE BASE (for general concepts):\n{context_text}\n\n"
            f"RESPONSE FORMAT:\n"
            f"- Start with facts from the scan\n"
            f"- Add inferences based on evidence\n"
            f"- Include general knowledge if helpful\n"
            f"- Always distinguish: Facts vs Inference vs General knowledge\n"
            f"- Be concise and actionable"
        )

    def _validate(self, answer: str, facts: dict, module: str) -> dict:
        if module == 'nmap':
            return self._validate_nmap(answer, facts)
        return {'valid': True, 'issues': []}

    def _validate_nmap(self, answer: str, facts: dict) -> dict:
        issues = []
        mentioned_ports = set(re.findall(r'\b(\d{1,5})/(?:tcp|udp)\b', answer))
        mentioned_ports.update(re.findall(r'\bport\s+(\d{1,5})\b', answer.lower()))
        valid_ports = set()
        for host in facts.get('hosts', []):
            for port_info in host.get('open_ports', []):
                valid_ports.add(str(port_info.get('port', '')))
            for port_info in host.get('filtered_ports', []):
                valid_ports.add(str(port_info.get('port', '')))
        invented_ports = mentioned_ports - valid_ports
        if invented_ports:
            issues.append(f"Invented ports: {', '.join(invented_ports)}")

        valid_services = set()
        for host in facts.get('hosts', []):
            for port_info in host.get('open_ports', []):
                valid_services.add(port_info.get('service', '').lower())
                if port_info.get('version_info'):
                    valid_services.add(port_info['version_info'].lower())
        for service in ['ftp', 'telnet', 'smtp', 'smb', 'rdp', 'vnc', 'mysql', 'postgresql']:
            if service in answer.lower():
                synonyms = SERVICE_SYNONYMS.get(service, [service])
                found = any(syn in ' '.join(valid_services) for syn in synonyms)
                if not found:
                    issues.append(f"Mentioned '{service}' not in scan")

        mentioned_ips = set(re.findall(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', answer))
        valid_ips = set(facts.get('targets', []))
        advisory_ips = {'127.0.0.1', '0.0.0.0', '255.255.255.0', '255.255.255.255',
                        '10.0.0.0', '172.16.0.0', '192.168.0.0', '8.8.8.8', '8.8.4.4'}
        invented_ips = mentioned_ips - valid_ips - advisory_ips
        if invented_ips:
            issues.append(f"Invented IPs: {', '.join(invented_ips)}")
        return {'valid': len(issues) == 0, 'issues': issues}


# Singleton instance
_engine: Optional[FridayEngine] = None
_engine_lock = threading.Lock()


def get_engine() -> FridayEngine:
    global _engine
    if _engine is None:
        with _engine_lock:
            if _engine is None:
                _engine = FridayEngine()
    return _engine
