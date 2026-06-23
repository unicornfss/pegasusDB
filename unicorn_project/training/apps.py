# unicorn_project/training/apps.py
import os
import sys

from django.apps import AppConfig


def _running_under_app_server() -> bool:
    """True only for long-running web processes (runserver / gunicorn)."""
    joined = " ".join(sys.argv)
    if "telegram_poll" in joined:
        return False
    if "runserver" in joined or "gunicorn" in joined:
        return True
    if "manage.py" in joined:
        return False
    return False


class TrainingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "unicorn_project.training"

    def ready(self):
        """
        Always wire up Django signals. Optionally start the booking scheduler.
        """
        try:
            from . import signals  # noqa: F401  # import registers receivers
        except Exception as e:
            print(f"Failed to import training.signals: {e}")

        if not _running_under_app_server():
            return

        from django.conf import settings

        if not getattr(settings, "BOOKING_SCHEDULER_ENABLED", False):
            return

        # Django runserver autoreloader starts two processes; only run in the worker.
        if "runserver" in " ".join(sys.argv) and os.environ.get("RUN_MAIN") != "true":
            return

        try:
            from . import tasks

            tasks.start()  # idempotent per process
        except Exception as e:
            print(f"APScheduler failed to start: {e}")
