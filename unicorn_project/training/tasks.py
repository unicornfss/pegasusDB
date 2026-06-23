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

def run_purge_dummy_bookings():
    print("[Scheduler] Running dummy booking purge...")
    try:
        call_command("purge_dummy_bookings", verbosity=0)
        print("[Scheduler] Finished dummy booking purge.")
    except Exception as e:
        print(f"[Scheduler] dummy booking purge FAILED: {e}")

def run_departure_reminders():
    print("[Scheduler] Running departure reminders...")
    try:
        call_command("send_departure_reminders", verbosity=0)
        print("[Scheduler] Finished departure reminders.")
    except Exception as e:
        print(f"[Scheduler] departure reminders FAILED: {e}")

def run_upcoming_booking_reminders():
    print("[Scheduler] Running upcoming booking reminders...")
    try:
        call_command("send_upcoming_booking_reminders", verbosity=0)
        print("[Scheduler] Finished upcoming booking reminders.")
    except Exception as e:
        print(f"[Scheduler] upcoming booking reminders FAILED: {e}")

def start():
    """
    Start APScheduler once per process (local dev only when BOOKING_SCHEDULER_ENABLED).
    Schedules background management commands on a timer — no immediate kickoff on start.
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

    if test_every > 0:
        dummy_desc = f"dummy purge every {test_every} min (interval)"
        scheduler.add_job(
            run_purge_dummy_bookings,
            trigger="interval",
            minutes=test_every,
            id="purge_dummy_bookings_interval",
            replace_existing=True,
        )
        departure_desc = f"departure reminders every {test_every} min (interval)"
        scheduler.add_job(
            run_departure_reminders,
            trigger="interval",
            minutes=test_every,
            id="send_departure_reminders_interval",
            replace_existing=True,
        )
        upcoming_desc = f"upcoming reminders every {test_every} min (interval)"
        scheduler.add_job(
            run_upcoming_booking_reminders,
            trigger="interval",
            minutes=test_every,
            id="send_upcoming_booking_reminders_interval",
            replace_existing=True,
        )
    else:
        dummy_desc = "dummy purge every 15 min @ 00,15,30,45 (cron)"
        scheduler.add_job(
            run_purge_dummy_bookings,
            CronTrigger(minute="0,15,30,45"),
            id="purge_dummy_bookings_cron",
            replace_existing=True,
        )
        departure_desc = "departure reminders every 5 min (cron)"
        scheduler.add_job(
            run_departure_reminders,
            CronTrigger(minute="*/5"),
            id="send_departure_reminders_cron",
            replace_existing=True,
        )
        upcoming_desc = "upcoming reminders every 5 min (cron)"
        scheduler.add_job(
            run_upcoming_booking_reminders,
            CronTrigger(minute="*/5"),
            id="send_upcoming_booking_reminders_cron",
            replace_existing=True,
        )

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

    # No immediate kickoff — avoids blocking web requests on deploy/wake
    scheduler.start()
    _scheduler = scheduler

    print(f"[APScheduler] Started in PID {os.getpid()}: {bookings_desc}; {dummy_desc}; {departure_desc}; {upcoming_desc}; {anon_desc}.")
