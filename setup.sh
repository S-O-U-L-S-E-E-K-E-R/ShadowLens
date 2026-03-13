#!/bin/bash
# ShadowLens — One-time setup script
# Installs all dependencies: Docker containers, OSINT agent venv, and security tools.
# Run once after cloning. Re-run to install any missing tools.
#
# Usage: chmod +x setup.sh && ./setup.sh

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

ok()   { echo -e "  ${GREEN}[+]${NC} $1"; }
warn() { echo -e "  ${YELLOW}[!]${NC} $1"; }
fail() { echo -e "  ${RED}[-]${NC} $1"; }
info() { echo -e "  ${CYAN}[*]${NC} $1"; }

MISSING=0
INSTALLED=0
SKIPPED=0

# ---------------------------------------------------------------------------
# Helper: check if a command exists
# ---------------------------------------------------------------------------
has() { command -v "$1" &>/dev/null; }

# ---------------------------------------------------------------------------
# Helper: install via apt if not present
# ---------------------------------------------------------------------------
apt_install() {
    local cmd="$1"
    local pkg="${2:-$1}"
    if has "$cmd"; then
        ok "$cmd already installed"
        return
    fi
    info "Installing $pkg..."
    if sudo apt-get install -y -qq "$pkg" &>/dev/null; then
        ok "$cmd installed"
        ((INSTALLED++))
    else
        fail "$cmd failed to install (apt: $pkg)"
        ((MISSING++))
    fi
}

# ---------------------------------------------------------------------------
# Helper: install via pip (into osint-agent venv) if not present
# ---------------------------------------------------------------------------
pip_install() {
    local cmd="$1"
    local pkg="${2:-$1}"
    if "$VENV_PIP" show "$pkg" &>/dev/null || has "$cmd"; then
        ok "$cmd already installed"
        return
    fi
    info "Installing $pkg (pip)..."
    if "$VENV_PIP" install -q "$pkg" &>/dev/null; then
        ok "$cmd installed (pip)"
        ((INSTALLED++))
    else
        fail "$cmd failed to install (pip: $pkg)"
        ((MISSING++))
    fi
}

# ---------------------------------------------------------------------------
# Helper: install Go tool if not present
# ---------------------------------------------------------------------------
go_install() {
    local cmd="$1"
    local pkg="$2"
    if has "$cmd"; then
        ok "$cmd already installed"
        return
    fi
    if ! has go; then
        warn "$cmd skipped (Go not installed)"
        ((SKIPPED++))
        return
    fi
    info "Installing $cmd (go install)..."
    if go install "$pkg" &>/dev/null; then
        ok "$cmd installed"
        ((INSTALLED++))
    else
        fail "$cmd failed to install (go: $pkg)"
        ((MISSING++))
    fi
}

echo ""
echo "==========================================="
echo "  S H A D O W L E N S   —   S E T U P"
echo "==========================================="
echo ""

# ---------------------------------------------------------------------------
# 1. Check core prerequisites
# ---------------------------------------------------------------------------
echo "[1/5] Checking prerequisites..."

if ! has docker; then
    fail "Docker not found. Install from https://docs.docker.com/engine/install/"
    exit 1
fi
ok "Docker found"

if ! has python3; then
    fail "Python 3 not found. Install python3.10+ first."
    exit 1
fi
ok "Python 3 found ($(python3 --version 2>&1 | awk '{print $2}'))"

if ! has node; then
    warn "Node.js not found (only needed for dev mode, not Docker)"
else
    ok "Node.js found ($(node --version))"
fi

if ! has go; then
    warn "Go not found — nuclei, subfinder, httpx won't auto-install (install manually or apt)"
else
    ok "Go found ($(go version | awk '{print $3}'))"
fi

# ---------------------------------------------------------------------------
# 2. Create .env if missing
# ---------------------------------------------------------------------------
echo ""
echo "[2/5] Environment setup..."

if [ ! -f "$SCRIPT_DIR/.env" ]; then
    cp "$SCRIPT_DIR/.env.example" "$SCRIPT_DIR/.env"
    warn "Created .env from template — edit it with your API keys"
    warn "At minimum, set AIS_API_KEY for maritime tracking"
else
    ok ".env already exists"
fi

# ---------------------------------------------------------------------------
# 3. Set up OSINT agent Python venv
# ---------------------------------------------------------------------------
echo ""
echo "[3/5] OSINT agent Python environment..."

VENV_DIR="$SCRIPT_DIR/osint-agent/venv"
VENV_PIP="$VENV_DIR/bin/pip"
VENV_PYTHON="$VENV_DIR/bin/python"

if [ ! -d "$VENV_DIR" ]; then
    info "Creating Python venv..."
    python3 -m venv "$VENV_DIR"
    ok "venv created"
else
    ok "venv already exists"
fi

info "Installing Python requirements..."
"$VENV_PIP" install -q --upgrade pip &>/dev/null
"$VENV_PIP" install -q -r "$SCRIPT_DIR/osint-agent/requirements.txt" &>/dev/null
ok "Python requirements installed"

# ---------------------------------------------------------------------------
# 4. Install OSINT tools
# ---------------------------------------------------------------------------
echo ""
echo "[4/5] Installing OSINT tools..."
echo ""

# Update apt cache once
info "Updating package lists..."
sudo apt-get update -qq &>/dev/null 2>&1 || warn "apt update failed (continuing anyway)"

# --- APT packages ---
apt_install nmap
apt_install whatweb
apt_install whois
apt_install dmitry
apt_install dig dnsutils
apt_install dnsrecon
apt_install kismet
apt_install snort

# --- theHarvester (pip) ---
pip_install theHarvester theharvester

# --- sherlock (pip) ---
pip_install sherlock sherlock-project

# --- h8mail (pip) ---
pip_install h8mail

# --- maigret (pip) ---
pip_install maigret

# --- holehe (pip) ---
pip_install holehe

# --- autorecon (pip) ---
pip_install autorecon

# --- shodan CLI (pip) ---
pip_install shodan

# --- Go tools ---
go_install nuclei github.com/projectdiscovery/nuclei/v3/cmd/nuclei@latest
go_install subfinder github.com/projectdiscovery/subfinder/v2/cmd/subfinder@latest

# --- phoneinfoga (check for prebuilt or go) ---
if has phoneinfoga; then
    ok "phoneinfoga already installed"
elif has go; then
    info "Installing phoneinfoga (go)..."
    go install github.com/sundowndev/phoneinfoga/v2@latest &>/dev/null && ok "phoneinfoga installed" || { fail "phoneinfoga failed"; ((MISSING++)); }
else
    warn "phoneinfoga skipped (needs Go or manual install)"
    ((SKIPPED++))
fi

# --- SpiderFoot (pip into venv) ---
if "$VENV_PIP" show spiderfoot &>/dev/null || has spiderfoot; then
    ok "spiderfoot already installed"
else
    info "Installing spiderfoot (pip)..."
    "$VENV_PIP" install -q spiderfoot &>/dev/null && ok "spiderfoot installed" || { fail "spiderfoot failed"; ((MISSING++)); }
fi

# ---------------------------------------------------------------------------
# 5. Build Docker images
# ---------------------------------------------------------------------------
echo ""
echo "[5/5] Building Docker images..."

cd "$SCRIPT_DIR"
if sudo docker compose build --quiet 2>/dev/null; then
    ok "Docker images built"
else
    fail "Docker build failed — check Dockerfiles"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "==========================================="
echo "  SETUP COMPLETE"
echo "==========================================="
echo ""
echo -e "  ${GREEN}Installed:${NC} $INSTALLED"
echo -e "  ${YELLOW}Skipped:${NC}   $SKIPPED"
echo -e "  ${RED}Failed:${NC}    $MISSING"
echo ""
echo "  Next steps:"
echo "    1. Edit .env with your API keys (AIS_API_KEY required)"
echo "    2. Run ./start.sh to launch everything"
echo ""

# Show tool availability
echo "  Tool status:"
for tool in nmap nuclei whatweb whois dmitry dig dnsrecon subfinder kismet snort; do
    if has "$tool"; then
        echo -e "    ${GREEN}+${NC} $tool"
    else
        echo -e "    ${RED}-${NC} $tool (not found)"
    fi
done
for tool in theHarvester sherlock h8mail maigret holehe autorecon shodan spiderfoot phoneinfoga; do
    if has "$tool" || [ -f "$VENV_DIR/bin/$tool" ]; then
        echo -e "    ${GREEN}+${NC} $tool"
    else
        echo -e "    ${RED}-${NC} $tool (not found)"
    fi
done
echo ""
