# Starting the server (local development)

Project folder:

```
C:\Users\jonsk\OneDrive\Unicorn\Database 2025\UnicornPegasus\pegasusDB
```

## Quick start (recommended)

Open **PowerShell** or **Command Prompt**, go to the project folder, then run:

```bat
.\runserver.bat
```

That script will:

1. Create `.venv` if it does not exist yet
2. Activate the virtual environment
3. Start the Django development server

Then open:

**http://127.0.0.1:8000/**

To stop the server, press **Ctrl+C** in that terminal window.

---

## Manual start

If you prefer to run the commands yourself:

```powershell
cd "C:\Users\jonsk\OneDrive\Unicorn\Database 2025\UnicornPegasus\pegasusDB"
.\.venv\Scripts\Activate.ps1
python manage.py runserver
```

If the virtual environment does not exist yet:

```powershell
cd "C:\Users\jonsk\OneDrive\Unicorn\Database 2025\UnicornPegasus\pegasusDB"
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

---

## First-time setup

For a fresh machine or first checkout, you can use:

```bat
.\bootstrap.bat
```

That installs dependencies, runs migrations, loads fixtures if the database is empty, and then starts the server.

You will also need a `.env` file in the project root with your local settings (database, email, API keys, etc.).

---

## Useful checks

Run the global health check:

```bat
.\global_test.bat
```

Or:

```powershell
python manage.py global_test
```

---

## Notes

- The dev server auto-reloads when you change Python code. If something still looks stale, stop the server with **Ctrl+C** and start it again.
- After database model changes, run:

```powershell
python manage.py migrate
```

- Django admin (superusers only): **http://127.0.0.1:8000/admin/**
- Main app login: **http://127.0.0.1:8000/**

---

## Telegram bot (local dev, `telegram_bot` branch)

Add these to your `.env` (enter the token yourself — do not paste it in chat):

```
TELEGRAM_BOT_TOKEN=your_bot_token_from_BotFather
TELEGRAM_BOT_USERNAME=your_bot_username_without_at
SITE_URL=http://127.0.0.1:8000
```

Run **two** terminals:

1. Django (as usual): `.\runserver.bat`
2. Telegram polling: `.\telegram_poll.bat`

Then on **Profile**, scan the QR code to link Telegram. Enable notification toggles and save.

On local dev (`DEBUG=True`), instructors are notified for **all** bookings including practice/dummy ones. Each Telegram message adds a line to the booking notes.

After installing dependencies:

```powershell
pip install -r requirements.txt
python manage.py migrate
```
