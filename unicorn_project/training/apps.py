import os
from django.apps import AppConfig

class TrainingConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'unicorn_project.training'
    label = 'training'

    def ready(self):
        """
        Start the APScheduler exactly once under runserver.
        """
        # Under runserver, Django launches a reloader parent + child.
        # Only start in the reloader CHILD (RUN_MAIN == 'true').
        if os.environ.get("RUN_MAIN") != "true":
            return

        # Start the scheduler
        try:
            from . import tasks
            tasks.start()
        except Exception as e:
            # Avoid crashing the server if scheduler setup fails
            print(f"APScheduler failed to start: {e}")
