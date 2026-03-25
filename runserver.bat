@echo off
setlocal
cd /d "%~dp0"
REM Activate venv (create if missing)
if not exist .venv (
  py -m venv .venv
)
call .\.venv\Scripts\activate.bat

REM Start Django dev server
python manage.py runserver
endlocal
