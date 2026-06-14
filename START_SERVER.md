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
3. Start the Django development server on **all network interfaces** (`0.0.0.0:8000`)

When it starts, the terminal prints URLs you can open — including a **http://192.168…** address for your phone.

Then open on this PC:

**http://127.0.0.1:8000/**

To stop the server, press **Ctrl+C** in that terminal window.

---

## View on your phone or tablet (same Wi-Fi)

1. Run `.\runserver.bat` on your PC as usual.
2. Note the **http://192.168.x.x:8000** URL printed in the terminal (your PC’s LAN address).
3. On your phone, connect to the **same Wi-Fi** and open that URL in the browser.

**Login and forms** work from the phone — in debug mode the app automatically trusts your LAN address for CSRF.

**If the page never loads:**

- Confirm PC and phone are on the same network (not mobile data).
- Windows may block inbound connections — when prompted, allow **Python** on private networks, or add a firewall rule for TCP port **8000**.
- Some guest/hotel Wi-Fi blocks device-to-device traffic; try a home network or phone hotspot from the PC.

**Telegram QR / links on phone:** those use `SITE_URL` from `.env`. For local mobile testing, temporarily set:

```
SITE_URL=http://192.168.x.x:8000
```

(use your PC’s LAN IP from the terminal). Change it back to `http://127.0.0.1:8000` when testing only on the PC.

Optional override if auto-detection is wrong:

```
DEV_SITE_URL=http://192.168.x.x:8000
```

---

## Manual start

If you prefer to run the commands yourself:

```powershell
cd "C:\Users\jonsk\OneDrive\Unicorn\Database 2025\UnicornPegasus\pegasusDB"
.\.venv\Scripts\Activate.ps1
python manage.py runserver 0.0.0.0:8000
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

Run **two** terminals:

1. Django (as usual): `.\runserver.bat`
2. Telegram polling: `.\telegram_poll.bat`

Local dev uses **polling** (not webhooks). `telegram_poll.bat` clears any webhook on the dev bot when it starts.

**If you see “another process is polling” (HTTP 409):** Windows often leaves old `python.exe` running after Ctrl+C. Run:

```
.\telegram_poll_stop.bat
.\telegram_poll.bat
```

Only **one** `telegram_poll.bat` terminal should be open at a time.

Then on **Profile**, scan the QR code to link Telegram.

---

## Telegram bot (Render production)

Production uses a **webhook on the existing web service** — no separate worker, no extra monthly cost.

Set on the **web** service:

| Variable | Value |
|----------|--------|
| `TELEGRAM_BOT_TOKEN` | Production bot token from @BotFather |
| `TELEGRAM_BOT_USERNAME` | `Unicornfsscombot` (no `@`) |
| `TELEGRAM_WEBHOOK_SECRET` | Long random string (Render can generate) |
| `SITE_URL` | `https://unicorn.adminforge.co.uk` |

Each deploy runs `python manage.py telegram_set_webhook` to register:

`https://unicorn.adminforge.co.uk/telegram/webhook/<secret>/`

**After first deploy**, if linking fails, run in **Render Shell** on the web service:

```
python manage.py telegram_set_webhook
```

Use a **dev bot** locally and the **production bot** on Render. Same Telegram user account on your phone is fine.

After installing dependencies:

```powershell
pip install -r requirements.txt
python manage.py migrate
```
