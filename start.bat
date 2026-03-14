@echo off
title ShadowLens - Global Threat Intercept

echo ===================================================
echo     S H A D O W L E N S   --   STARTUP
echo ===================================================
echo.

:: ── Docker Services (Frontend + Backend) ──
echo [*] Starting Docker containers (frontend + backend)...
docker compose up -d
echo [+] Frontend:  http://localhost:3000
echo [+] Backend:   http://localhost:8001

:: ── OSINT Agent + F.R.I.D.A.Y. ──
echo.
echo [*] Starting OSINT Agent + F.R.I.D.A.Y. engine...
cd osint-agent

if not exist "venv\" (
    echo [!] OSINT Agent venv not found. Creating...
    python -m venv venv
    call venv\Scripts\activate.bat
    pip install -r requirements.txt
) else (
    call venv\Scripts\activate.bat
)

start /B "" python -m uvicorn main:app --host 0.0.0.0 --port 8002
echo [+] OSINT Agent: http://localhost:8002

cd ..

echo.
echo ===================================================
echo   S H A D O W L E N S   --   ALL SYSTEMS ONLINE
echo.
echo   Dashboard:     http://localhost:3000
echo   Backend API:   http://localhost:8001
echo   OSINT Agent:   http://localhost:8002
echo   F.R.I.D.A.Y.:  Initializing in background...
echo.
echo   Stop: docker compose down
echo ===================================================
pause
