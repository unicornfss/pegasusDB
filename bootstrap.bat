@echo off
setlocal

REM create venv if missing
if not exist .venv (
  py -m venv .venv
)
call .\.venv\Scripts\activate.bat

python -m pip install --upgrade pip
pip install -r requirements.txt

python manage.py makemigrations unicorn_project.training
python manage.py migrate

REM Load fixtures only if empty
python -c "import os; os.environ.setdefault('DJANGO_SETTINGS_MODULE','unicorn_project.settings'); import django; django.setup(); from unicorn_project.training.models import Booking; from django.core.management import call_command; import sys; \
import pathlib; \
print('Checking fixtures...'); \
0 if Booking.objects.exists() else call_command('loaddata', 'unicorn_project/training/fixtures.json')"

echo.
echo Launching server at http://127.0.0.1:8000/
python manage.py runserver

endlocal
