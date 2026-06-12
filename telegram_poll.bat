@echo off

setlocal

cd /d "%~dp0"

if not exist .venv (

  py -m venv .venv

)

call .\.venv\Scripts\activate.bat

python manage.py telegram_poll

endlocal

