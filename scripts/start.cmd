@echo off
REM IrsBot one-click start (Windows) - D2.1 / D2.4 / D3.1 / D3.2
REM   1.   create .env from .env.example if missing
REM   1.5  ensure SECRET_KEY + FIRST_SUPERUSER_PASSWORD are not the
REM        insecure default "changethis" (generate random + persist to .env)
REM   2.   check Docker
REM   3.   docker compose up -d --build
REM   4.   poll health-check, then open the browser
REM
REM NOTE: this file is intentionally ASCII-only. Windows cmd.exe reads .cmd
REM files with the ANSI code page, so any non-ASCII byte (including Chinese)
REM gets mangled and can break parsing. Keep messages in English.
setlocal enabledelayedexpansion
cd /d "%~dp0.."

echo.
echo   IrsBot start
echo   ============================================
echo.

REM ---- 1/5 .env ----
if not exist ".env" (
    if not exist ".env.example" (
        echo   [ERROR] Neither .env nor .env.example exists.
        exit /b 1
    )
    copy /y ".env.example" ".env" >nul
    echo   [1/5] .env created from .env.example
    echo         Review SECRET_KEY / DB password / LLM API keys before use.
) else (
    echo   [1/5] .env found
)

REM ---- 1.5/5 secrets (D3.1 / D3.2) ----
echo   [1.5/5] Checking secrets...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0bootstrap_env.ps1"
if errorlevel 1 (
    echo   [ERROR] bootstrap_env.ps1 failed.
    exit /b 1
)

REM ---- 2/5 Docker ----
docker version >nul 2>&1
if errorlevel 1 (
    echo   [ERROR] Docker not available. Start Docker Desktop first.
    exit /b 1
)
echo   [2/5] Docker OK

REM ---- 3/5 start ----
echo   [3/5] Building and starting containers (first run is slow)...
docker compose up -d --build
if errorlevel 1 (
    echo   [ERROR] docker compose up failed. See output above.
    exit /b 1
)

REM ---- 4/5 wait until healthy (max 3 min) ----
echo   [4/5] Waiting for backend...
set "READY=0"
for /L %%i in (1,1,60) do (
    curl.exe -s -f http://localhost:8000/api/v1/utils/health-check/ >nul 2>&1
    if not errorlevel 1 (
        set "READY=1"
        goto :ready
    )
    timeout /t 3 /nobreak >nul
)
:ready

if "!READY!"=="0" (
    echo.
    echo   [WARN] Timed out. Check logs: docker compose logs -f backend
    exit /b 1
)

set "SU="
for /f "usebackq tokens=1,* delims==" %%a in (`findstr /b "FIRST_SUPERUSER=" ".env"`) do set "SU=%%b"
set "SUPW="
for /f "usebackq tokens=1,* delims==" %%a in (`findstr /b "FIRST_SUPERUSER_PASSWORD=" ".env"`) do set "SUPW=%%b"

echo.
echo   Ready
echo   --------------------------------------------
echo   URL         : http://localhost:8000
echo   Account     : !SU!
echo   Password    : !SUPW!
echo   Logs        : docker compose logs -f backend
echo   Stop        : scripts\stop.cmd
echo   --------------------------------------------
echo.
echo   The admin password above is the one to use for your first login.
echo   It was randomly generated on first run and saved to .env; change it
echo   in the UI later if you like.
echo.

start "" http://localhost:8000

echo.
echo   Server is up. Press any key to close this window
echo   (containers keep running in Docker). Password is in .env.
pause >nul
endlocal
