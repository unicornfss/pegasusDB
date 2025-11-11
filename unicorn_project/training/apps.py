# unicorn_project/training/apps.py
from django.apps import AppConfig
import os

class TrainingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "unicorn_project.training"

    def ready(self):
        """
        Always wire up Django signals. Optionally start the booking scheduler.
        """
        # ✅ Always connect signal handlers (even if scheduler is disabled)
        try:
            from . import signals  # noqa: F401  # import registers receivers
        except Exception as e:
            # Avoid crashing the app if there's a typo during development
            print(f"Failed to import training.signals: {e}")

        # 🔧 Start APScheduler only if enabled
        from django.conf import settings
        if os.environ.get("BOOKING_SCHEDULER_ENABLED", "true").lower() != "true":
            return
        if getattr(settings, "BOOKING_SCHEDULER_ENABLED", True) is False:
            return

        try:
            from . import tasks
            tasks.start()  # idempotent per process
        except Exception as e:
            print(f"APScheduler failed to start: {e}")
