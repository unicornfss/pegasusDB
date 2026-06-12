@echo off
setlocal
cd /d "%~dp0"

echo Stopping any orphan telegram_poll processes...
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name = 'python.exe'\" | Where-Object { $_.CommandLine -match 'manage.py telegram_poll' -and $_.CommandLine -match 'pegasusDB' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"

if exist .telegram_poll.lock del /f .telegram_poll.lock

ping 127.0.0.1 -n 3 >nul
echo Done. You can now run telegram_poll.bat once.

endlocal
