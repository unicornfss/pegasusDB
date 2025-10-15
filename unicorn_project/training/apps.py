from django.apps import AppConfig
import os

class TrainingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "unicorn_project.training"

    def ready(self):
        # Optional kill-switch via env or settings
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
