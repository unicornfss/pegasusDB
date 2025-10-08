# Unicorn Training — fresh Django starter

**Two UIs**: custom Admin app (`/app/admin/`) and Instructor app (`/app/instructor/`). Superusers only may access Django admin (`/admin/`). Dynamic location dropdown on booking form via `/api/locations/`.

## Quick start (Windows PowerShell)
```
cd "/mnt/data/unicorn-django"
py -m venv .venv
. .venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python manage.py makemigrations training
python manage.py migrate
python manage.py loaddata unicorn_project/training/fixtures.json
python manage.py createsuperuser
python manage.py runserver
```
Open: http://127.0.0.1:8000/

### Roles
Create groups `admin` and `instructor` in Django admin, then add users to them. Link an `Instructor` row to a user to show their bookings.
