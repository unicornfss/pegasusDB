@echo off
setlocal

if not exist .venv (
  py -m venv .venv
)

call .\.venv\Scripts\activate.bat

python manage.py global_test %*

endlocal