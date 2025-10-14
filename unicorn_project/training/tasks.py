from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime, timezone as dtz
from django.core.management import call_command

_scheduler = None

def start():
    global _scheduler
    if _scheduler:
        return

    # coalesce=True = if the scheduler was briefly paused, run only once
    # misfire_grace_time gives us a window to still run late jobs (not helpful across full restarts,
    # but harmless to keep)
    s = BackgroundScheduler(
        timezone="UTC",
        job_defaults={"coalesce": True, "misfire_grace_time": 3600},
    )

    # 1) schedule the regular every-15-min run
    s.add_job(
        lambda: call_command("update_booking_statuses"),
        CronTrigger(minute="0,15,30,45"),
        id="update_booking_statuses_cron",
        replace_existing=True,
    )

    # 2) run ONCE immediately on startup (so waking from sleep does an instant catch-up)
    s.add_job(
        lambda: call_command("update_booking_statuses"),
        next_run_time=datetime.now(dtz.utc),
        id="update_booking_statuses_kick",
        replace_existing=True,
    )

    s.start()
    _scheduler = s
    print("APScheduler started: kickoff + every 15 minutes (00,15,30,45).")
