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

## Telegram bot (local dev)

Use a **separate test bot** from production (create a second bot via @BotFather).

Add these to your `.env` — **token and username must be from the same bot**:

```
TELEGRAM_BOT_TOKEN=your_dev_bot_token_from_BotFather
TELEGRAM_BOT_USERNAME=your_dev_bot_username_without_at
SITE_URL=http://127.0.0.1:8000
```

Do **not** use the production bot token/username locally while testing live linking.

Run **two** terminals:

1. Django (as usual): `.\runserver.bat`
2. Telegram polling: `.\telegram_poll.bat`

**Stop `telegram_poll.bat`** whenever you test QR linking on the live site — only one process may poll a bot token at a time, and local `.env` uses a different `DJANGO_SECRET_KEY` than Render.

Then on **Profile**, scan the QR code to link Telegram. Enable notification toggles and save.

---

## Telegram bot (Render production)

1. Set on **both** the **web** service and **unicorn-telegram-bot** worker:
   - `TELEGRAM_BOT_TOKEN` — production bot token from @BotFather
   - `TELEGRAM_BOT_USERNAME` — production bot username (no `@`)
   - `SITE_URL=https://unicorn.adminforge.co.uk`
2. Worker must share `DJANGO_SECRET_KEY` with web (see `render.yaml` `fromService`).
3. Ensure the **unicorn-telegram-bot** worker is running (`python manage.py telegram_poll`).
4. Link tokens are signed with `DJANGO_SECRET_KEY` (no shared cache required).

**Same Telegram user account** on your phone is fine for dev and prod. **Same bot token** in dev and prod is not — use two bots, or stop local polling when using live.

After installing dependencies:

```powershell
pip install -r requirements.txt
python manage.py migrate
```
