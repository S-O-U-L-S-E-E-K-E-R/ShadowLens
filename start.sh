#!/bin/bash
echo "======================================================="
echo "   S H A D O W  L E N S   —   Startup                  "
echo "======================================================="
echo ""

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# ── Docker Services (Frontend + Backend) ──
echo "[*] Starting Docker containers (frontend + backend)..."
cd "$SCRIPT_DIR"
sudo docker compose up -d
echo "[✓] Frontend:  http://localhost:3000"
echo "[✓] Backend:   http://localhost:8001"

# ── OSINT Agent + F.R.I.D.A.Y. ──
echo ""
echo "[*] Starting OSINT Agent + F.R.I.D.A.Y. engine..."
cd "$SCRIPT_DIR/osint-agent"

if [ ! -d "venv" ]; then
    echo "[!] OSINT Agent venv not found. Run setup first."
    echo "    python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt"
    exit 1
fi

# Kill any existing osint-agent
pkill -f "uvicorn.*main:app.*8002" 2>/dev/null
sleep 1

source venv/bin/activate
nohup python -m uvicorn main:app --host 0.0.0.0 --port 8002 --reload > /tmp/osint-agent.log 2>&1 &
AGENT_PID=$!
echo "[✓] OSINT Agent: http://localhost:8002 (PID: $AGENT_PID)"

# Wait for F.R.I.D.A.Y. to come online
echo "[*] Waiting for F.R.I.D.A.Y. engine to initialize..."
for i in $(seq 1 60); do
    sleep 5
    STATUS=$(curl -s --max-time 3 http://localhost:8002/syd/status 2>/dev/null)
    READY=$(echo "$STATUS" | python3 -c "import json,sys; print(json.load(sys.stdin).get('ready',''))" 2>/dev/null)
    if [ "$READY" = "True" ]; then
        echo "[✓] F.R.I.D.A.Y. is online and ready!"
        GPU=$(echo "$STATUS" | python3 -c "import json,sys; print('GPU' if json.load(sys.stdin).get('llm_loaded') else 'CPU')" 2>/dev/null)
        echo "    Mode: $GPU | LLM loaded | All modules active"
        break
    fi
    echo "    ...loading ($i/60)"
done

echo ""
echo "======================================================="
echo "  S H A D O W  L E N S   —   ALL SYSTEMS ONLINE        "
echo "                                                        "
echo "  Dashboard:     http://localhost:3000                   "
echo "  Backend API:   http://localhost:8001                   "
echo "  OSINT Agent:   http://localhost:8002                   "
echo "  F.R.I.D.A.Y.:  Ready for analysis                     "
echo "                                                        "
echo "  Logs: tail -f /tmp/osint-agent.log                    "
echo "  Stop: docker compose down && pkill -f 'uvicorn.*8002' "
echo "======================================================="
