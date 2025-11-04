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
    val = getattr(settings, "BOOKING_TEST_INTERVAL_MIN", None)
    if val is None:
        val = os.environ.get("BOOKING_TEST_INTERVAL_MIN")
    try:
        return int(val) if val else 0
    except (TypeError, ValueError):
        return 0

def _get_anon_test_interval_minutes() -> int:
    """
    If you want the accident anonymiser to run every N minutes (test mode),
    set ACCIDENT_ANON_TEST_MIN in settings.py or env.
      settings.ACCIDENT_ANON_TEST_MIN = 1
      # or env: ACCIDENT_ANON_TEST_MIN=1
    Returns 0 if not set, which means use the nightly cron schedule.
    """
    val = getattr(settings, "ACCIDENT_ANON_TEST_MIN", None)
    if val is None:
        val = os.environ.get("ACCIDENT_ANON_TEST_MIN")
    try:
        return int(val) if val else 0
    except (TypeError, ValueError):
        return 0

# ---- Job wrappers with logging ----
def run_update_booking_statuses():
    print("[Scheduler] Running update_booking_statuses...")
    try:
        call_command("update_booking_statuses")
        print("[Scheduler] Finished update_booking_statuses.")
    except Exception as e:
        print(f"[Scheduler] update_booking_statuses FAILED: {e}")

def run_anonymiser():
    print("[Scheduler] Running anonymisation job...")
    try:
        call_command("anonymise_accident_reports")
        print("[Scheduler] Finished anonymisation job.")
    except Exception as e:
        print(f"[Scheduler] anonymisation job FAILED: {e}")

def start():
    """
    Start APScheduler once per process.
    - Adds a 'kickoff' run for update_booking_statuses immediately on startup/wake.
    - Schedules:
        * update_booking_statuses: every N minutes (if BOOKING_TEST_INTERVAL_MIN > 0) OR cron 00,15,30,45
        * anonymise_accident_reports: every N minutes (if ACCIDENT_ANON_TEST_MIN > 0) OR nightly at 00:05 UTC
    """
    global _scheduler
    if _scheduler is not None:
        # Already started in this process
        print(f"[APScheduler] Already running in PID {os.getpid()}; skipping re-start.")
        return

    # Build the scheduler (UTC is fine; commands can localize timestamps as needed)
    scheduler = BackgroundScheduler(
        timezone="UTC",
        job_defaults={"coalesce": True, "misfire_grace_time": 3600},
    )

    # ---- update_booking_statuses schedule ----
    test_every = _get_test_interval_minutes()
    if test_every > 0:
        bookings_desc = f"bookings every {test_every} min (interval)"
        scheduler.add_job(
            run_update_booking_statuses,
            trigger="interval",
            minutes=test_every,
            id="update_booking_statuses_interval",
            replace_existing=True,
        )
    else:
        bookings_desc = "bookings every 15 min @ 00,15,30,45 (cron)"
        scheduler.add_job(
            run_update_booking_statuses,
            CronTrigger(minute="0,15,30,45"),
            id="update_booking_statuses_cron",
            replace_existing=True,
        )

    # Kickoff: run update_booking_statuses once immediately at startup/wake
    scheduler.add_job(
        run_update_booking_statuses,
        next_run_time=datetime.now(dtz.utc),
        id="update_booking_statuses_kick",
        replace_existing=True,
    )

    # ---- anonymise_accident_reports schedule ----
    anon_test_every = _get_anon_test_interval_minutes()
    if anon_test_every > 0:
        anon_desc = f"anonymiser every {anon_test_every} min (interval)"
        scheduler.add_job(
            run_anonymiser,
            trigger="interval",
            minutes=anon_test_every,
            id="anonymise_accident_reports_interval",
            replace_existing=True,
        )
    else:
        anon_desc = "anonymiser nightly @ 00:05 UTC (cron)"
        scheduler.add_job(
            run_anonymiser,
            CronTrigger(hour="0", minute="5"),
            id="anonymise_accident_reports_nightly",
            replace_existing=True,
        )

    # Start scheduler
    scheduler.start()
    _scheduler = scheduler

    # Helpful log lines
    print(f"[APScheduler] Started in PID {os.getpid()}: {bookings_desc}; {anon_desc}.")
