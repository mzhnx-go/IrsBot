@echo off
REM IrsBot one-shot backup (read-only; never deletes data).
setlocal
pushd "%~dp0.."
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0backup.ps1"
popd
pause >nul
endlocal
