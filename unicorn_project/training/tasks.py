import os
import sys
from datetime import datetime, timezone as dtz

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from django.core.management import call_command
from django.conf import settings

# Single scheduler per Python process
_scheduler = None

def _get_test_interval_minutes() -> int:
    """
    If you want to run every N minutes (e.g. 2 for testing),
    set BOOKING_TEST_INTERVAL_MIN either in settings.py or env.
      settings.BOOKING_TEST_INTERVAL_MIN = 2
      # or env: BOOKING_TEST_INTERVAL_MIN=2
    Returns 0 if not set, which means use the 15-min cron schedule.
    """
    # settings first, env fallback
    val = getattr(settings, "BOOKING_TEST_INTERVAL_MIN", None)
    if val is None:
        val = os.environ.get("BOOKING_TEST_INTERVAL_MIN")
    try:
        return int(val) if val else 0
    except (TypeError, ValueError):
        return 0


def start():
    """
    Start APScheduler once per process.
    - Always adds a 'kickoff' run to fire immediately on startup/wake.
    - Then schedules either:
        * every 2 minutes (or N minutes) if BOOKING_TEST_INTERVAL_MIN > 0
        * or the regular cron: minute="0,15,30,45"
    """
    global _scheduler
    if _scheduler is not None:
        # Already started in this process
        print(f"[APScheduler] Already running in PID {os.getpid()}; skipping re-start.")
        return

    # Build the scheduler (UTC is fine; your command uses timezone.localtime())
    scheduler = BackgroundScheduler(
        timezone="UTC",
        job_defaults={"coalesce": True, "misfire_grace_time": 3600},
    )

    # Decide schedule: test interval vs cron
    test_every = _get_test_interval_minutes()
    if test_every > 0:
        schedule_desc = f"every {test_every} minutes (interval)"
        # interval schedule
        scheduler.add_job(
            lambda: call_command("update_booking_statuses"),
            trigger="interval",
            minutes=test_every,
            id="update_booking_statuses_interval",
            replace_existing=True,
        )
    else:
        schedule_desc = "every 15 minutes at 00,15,30,45 (cron)"
        # 15-min cron
        scheduler.add_job(
            lambda: call_command("update_booking_statuses"),
            CronTrigger(minute="0,15,30,45"),
            id="update_booking_statuses_cron",
            replace_existing=True,
        )

    # Kickoff: run once immediately at startup/wake
    scheduler.add_job(
        lambda: call_command("update_booking_statuses"),
        next_run_time=datetime.now(dtz.utc),
        id="update_booking_statuses_kick",
        replace_existing=True,
    )

    scheduler.start()
    _scheduler = scheduler

    # Helpful log lines
    print(
        f"APScheduler started in PID {os.getpid()}: kickoff + {schedule_desc}."
    )
