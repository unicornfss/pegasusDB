@echo off
setlocal
cd /d "%~dp0"
REM Activate venv (create if missing)
if not exist .venv (
  py -m venv .venv
)
call .\.venv\Scripts\activate.bat

REM Listen on LAN (0.0.0.0) so phones on the same Wi-Fi can connect
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\dev-local.ps1"
endlocal
