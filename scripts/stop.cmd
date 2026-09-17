@echo off
REM IrsBot one-click stop (Windows) - D2.3
REM   Default: `docker compose down` keeps the data volume.
REM   Add -v to also DELETE the database volume (destructive).
setlocal
cd /d "%~dp0.."

echo.
echo   Stopping IrsBot ...
docker compose down

echo.
echo   Stopped. The app-db-data volume is preserved, so your data
echo   remains for the next start.
echo   To wipe everything (DANGEROUS): docker compose down -v
echo.

endlocal
