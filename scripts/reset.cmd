@echo off
REM IrsBot clean reset (Windows) - D4.1
REM   Remove ALL containers + data volumes (db + milvus), then one-click start.
REM   WARNING: this deletes every conversation / knowledge base / config stored
REM   in the Docker volumes. Use it only to start from a truly clean state.
setlocal enabledelayedexpansion
cd /d "%~dp0.."

echo.
echo   IrsBot clean reset
echo   ============================================
echo   WARNING: this removes ALL data (db + milvus
echo   volumes) and rebuilds from scratch.
echo.

docker version >nul 2>&1
if errorlevel 1 (
    echo   [ERROR] Docker not available. Start Docker Desktop first.
    exit /b 1
)

echo   Stopping and removing containers + volumes...
docker compose down -v
if errorlevel 1 (
    echo   [ERROR] docker compose down -v failed.
    exit /b 1
)

echo   Starting clean one-click setup...
call "%~dp0start.cmd"
endlocal
