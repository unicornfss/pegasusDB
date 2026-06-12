import atexit
import logging
import os
import sys
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from unicorn_project.training.utils.telegram_bot import run_polling

logger = logging.getLogger(__name__)

_MUTEX_NAME = "UnicornPegasusDBTelegramPoll"
_mutex_handle = None


def _lock_path() -> Path:
    return Path(settings.BASE_DIR) / ".telegram_poll.lock"


def _acquire_single_instance() -> None:
    global _mutex_handle

    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.windll.kernel32
        kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
        kernel32.CreateMutexW.restype = wintypes.HANDLE
        kernel32.GetLastError.restype = wintypes.DWORD

        _mutex_handle = kernel32.CreateMutexW(None, True, _MUTEX_NAME)
        if kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
            raise CommandError(
                "telegram_poll is already running in another terminal.\n"
                "Run .\\telegram_poll_stop.bat first, then .\\telegram_poll.bat again."
            )
        return

    path = _lock_path()
    if path.exists():
        try:
            existing = int(path.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            existing = 0
        if existing and existing != os.getpid():
            try:
                os.kill(existing, 0)
                raise CommandError(
                    f"telegram_poll is already running (PID {existing}). "
                    "Close the other terminal first."
                )
            except OSError:
                path.unlink(missing_ok=True)

    path.write_text(str(os.getpid()), encoding="utf-8")

    def _release() -> None:
        try:
            if path.exists() and path.read_text(encoding="utf-8").strip() == str(os.getpid()):
                path.unlink(missing_ok=True)
        except OSError:
            pass

    atexit.register(_release)


class Command(BaseCommand):
    help = "Poll Telegram for bot commands (local development)."

    def handle(self, *args, **options):
        logging.basicConfig(level=logging.INFO)
        _acquire_single_instance()
        run_polling()
