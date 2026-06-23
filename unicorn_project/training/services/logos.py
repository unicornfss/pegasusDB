import json
import calendar
import datetime as dt
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings
from django.contrib.staticfiles import finders

# Try to import the override model, but don’t crash if migrations aren’t ready
try:
    from ..models import LogoOverride
except Exception:  # ImportError, AppRegistryNotReady, etc.
    LogoOverride = None

SCHEDULE_PATH = Path(settings.BASE_DIR) / "config" / "logo_schedule.json"
LOGO_IMG_DIR = (
    Path(settings.BASE_DIR) / "unicorn_project" / "training" / "static" / "training" / "img"
)
_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}


@dataclass(frozen=True)
class LogoCatalogEntry:
    file: str
    is_default: bool
    is_current: bool
    on_disk: bool
    rules: list[dict]


def _logo_img_directories() -> list[Path]:
    """Directories that may contain sidebar/header logo images."""
    candidates = [
        LOGO_IMG_DIR,
        Path(settings.BASE_DIR) / "staticfiles" / "training" / "img",
    ]
    for static_dir in getattr(settings, "STATICFILES_DIRS", []):
        candidates.append(Path(static_dir) / "training" / "img")
    static_root = getattr(settings, "STATIC_ROOT", None)
    if static_root:
        candidates.append(Path(static_root) / "training" / "img")

    directories: list[Path] = []
    seen: set[str] = set()
    for path in candidates:
        key = str(path.resolve()).lower() if path.exists() else str(path).lower()
        if path.is_dir() and key not in seen:
            directories.append(path)
            seen.add(key)
    return directories


def _is_logo_image_name(name: str) -> bool:
    lower = name.lower()
    return lower.startswith("logo") and Path(lower).suffix in _IMAGE_SUFFIXES


def logo_file_exists(file_name: str) -> bool:
    if finders.find(f"training/img/{file_name}"):
        return True
    return any((directory / file_name).is_file() for directory in _logo_img_directories())


def available_logo_filenames() -> list[str]:
    names: set[str] = set()
    for directory in _logo_img_directories():
        for path in directory.iterdir():
            if path.is_file() and _is_logo_image_name(path.name):
                names.add(path.name)

    spec = load_schedule_spec()
    for rule in spec.get("rules", []):
        file_name = (rule.get("file") or "").strip()
        if file_name and logo_file_exists(file_name):
            names.add(file_name)
    default_file = (spec.get("default") or "logo.png").strip()
    if default_file:
        names.add(default_file)

    return sorted(names) or ["logo.png"]


_SCHEDULE_CACHE: dict | None = None
_SCHEDULE_MTIME: float | None = None


def load_schedule_spec() -> dict:
    global _SCHEDULE_CACHE, _SCHEDULE_MTIME
    try:
        mtime = SCHEDULE_PATH.stat().st_mtime
    except OSError:
        return {"rules": [], "default": "logo.png"}

    if _SCHEDULE_CACHE is not None and _SCHEDULE_MTIME == mtime:
        return _SCHEDULE_CACHE

    try:
        with open(SCHEDULE_PATH, "r", encoding="utf-8") as f:
            _SCHEDULE_CACHE = json.load(f)
            _SCHEDULE_MTIME = mtime
            return _SCHEDULE_CACHE
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {"rules": [], "default": "logo.png"}


def save_schedule_spec(spec: dict) -> None:
    global _SCHEDULE_CACHE, _SCHEDULE_MTIME
    SCHEDULE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(SCHEDULE_PATH, "w", encoding="utf-8") as f:
        json.dump(spec, f, indent=2)
        f.write("\n")
    _SCHEDULE_CACHE = spec
    try:
        _SCHEDULE_MTIME = SCHEDULE_PATH.stat().st_mtime
    except OSError:
        _SCHEDULE_MTIME = None


# ----------------------------
#  DATE HELPERS
# ----------------------------

def easter_sunday(year: int) -> dt.date:
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return dt.date(year, month, day)


def last_weekday_of_month(year, month, weekday):  # 0=Mon..6=Sun; Sat=5
    import calendar as cal
    c = cal.Calendar()
    dates = [d for d in c.itermonthdates(year, month) if d.month == month and d.weekday() == weekday]
    return dates[-1]


def _apply_window(anchor, rule):
    """Apply optional start_offset_days and end_offset_days from JSON."""
    start = anchor + dt.timedelta(days=int(rule.get("start_offset_days", 0)))
    end = anchor + dt.timedelta(days=int(rule.get("end_offset_days", 0)))
    if end < start:
        start, end = end, start
    return start, end


def _month_day_label(value: str) -> str:
    month, day = map(int, value.split("-"))
    return dt.date(2000, month, day).strftime("%d %B").lstrip("0")


_WEEKDAYS = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)


def describe_schedule_rule(rule: dict) -> str:
    """Human-readable summary of a logo schedule rule."""
    rule_type = rule.get("type", "")
    window_note = ""
    start_off = int(rule.get("start_offset_days", 0))
    end_off = int(rule.get("end_offset_days", 0))
    if start_off or end_off:
        window_note = f" (window: {start_off:+d} to {end_off:+d} days)"

    if rule_type == "single":
        return f"Each year on {_month_day_label(rule['date'])}{window_note}"

    if rule_type == "range":
        return (
            f"Each year from {_month_day_label(rule['start'])} "
            f"to {_month_day_label(rule['end'])}"
        )

    if rule_type == "range_yearwrap":
        return (
            f"Each year from {_month_day_label(rule['start'])} "
            f"through {_month_day_label(rule['end'])} (crosses New Year)"
        )

    if rule_type == "range_absolute":
        return (
            f"Each year from {_month_day_label(rule['start_abs'])} "
            f"to {_month_day_label(rule['end_abs'])}"
        )

    if rule_type == "weekday_in_month":
        month_name = dt.date(2000, int(rule["month"]), 1).strftime("%B")
        weekday = _WEEKDAYS[int(rule["weekday"])]
        occurrence = rule.get("occurrence", "last")
        return f"{occurrence.title()} {weekday} in {month_name}{window_note}"

    if rule_type == "easter_range":
        before = int(rule.get("days_before", 6))
        after = int(rule.get("days_after", 6))
        return f"From {before} day{'s' if before != 1 else ''} before Easter Sunday to {after} day{'s' if after != 1 else ''} after"

    return f"Rule type: {rule_type or 'unknown'}"


def build_logo_catalog(spec: dict, *, current_logo: str | None = None) -> list[LogoCatalogEntry]:
    """Group schedule rules by logo file for display."""
    default_file = spec.get("default", "logo.png")
    rules_by_file: dict[str, list[dict]] = {}
    for rule in spec.get("rules", []):
        file_name = (rule.get("file") or "").strip()
        if not file_name:
            continue
        rules_by_file.setdefault(file_name, []).append(
            {
                "name": rule.get("name") or "Scheduled rule",
                "summary": describe_schedule_rule(rule),
            }
        )

    catalog_files: list[str] = []
    seen: set[str] = set()
    for file_name in available_logo_filenames():
        seen.add(file_name)
        catalog_files.append(file_name)
    for file_name in sorted(rules_by_file):
        if file_name not in seen:
            catalog_files.append(file_name)
            seen.add(file_name)
    if default_file and default_file not in seen:
        catalog_files.append(default_file)

    catalog: list[LogoCatalogEntry] = []
    for file_name in catalog_files:
        catalog.append(
            LogoCatalogEntry(
                file=file_name,
                is_default=file_name == default_file,
                is_current=bool(current_logo and file_name == current_logo),
                on_disk=logo_file_exists(file_name),
                rules=rules_by_file.get(file_name, []),
            )
        )
    catalog.sort(
        key=lambda item: (
            0 if item.is_default else 1,
            0 if item.rules else 1,
            item.file.lower(),
        )
    )
    return catalog


def _pick_from_schedule(today: dt.date, spec: dict) -> str:
    for rule in spec.get("rules", []):
        t = rule["type"]

        # Single date (optionally with window)
        if t == "single":
            m, d = map(int, rule["date"].split("-"))
            anchor = dt.date(today.year, m, d)
            start, end = _apply_window(anchor, rule)
            if start <= today <= end:
                return rule["file"]

        # Simple month-day range
        elif t == "range":
            sm, sd = map(int, rule["start"].split("-"))
            em, ed = map(int, rule["end"].split("-"))
            if (today.month, today.day) >= (sm, sd) and (today.month, today.day) <= (em, ed):
                return rule["file"]

        # Range that crosses New Year (e.g. Dec 31–Jan 2)
        elif t == "range_yearwrap":
            sm, sd = map(int, rule["start"].split("-"))
            em, ed = map(int, rule["end"].split("-"))
            after_start = (today.month, today.day) >= (sm, sd)
            before_end = (today.month, today.day) <= (em, ed)
            if after_start or before_end:
                return rule["file"]

        # Dynamic rule: weekday occurrence in month (e.g. last Saturday in June)
        elif t == "weekday_in_month":
            if today.month == int(rule["month"]):
                wd = int(rule["weekday"])  # 0=Mon..6=Sun; 5=Saturday
                occ = rule.get("occurrence", "last")

                if occ == "last":
                    anchor = last_weekday_of_month(today.year, today.month, wd)
                else:
                    anchor = None  # Extend later for nth weekday if needed

                start, end = _apply_window(anchor, rule)

                if start <= today <= end:
                    return rule["file"]

        # Fixed absolute date range
        elif t == "range_absolute":
            sm, sd = map(int, rule["start_abs"].split("-"))
            em, ed = map(int, rule["end_abs"].split("-"))
            if (today.month, today.day) >= (sm, sd) and (today.month, today.day) <= (em, ed):
                return rule["file"]

        # Easter-relative range
        elif t == "easter_range":
            e = easter_sunday(today.year)
            start = e - dt.timedelta(days=rule.get("days_before", 6))
            end = e + dt.timedelta(days=rule.get("days_after", 6))
            if start <= today <= end:
                return rule["file"]

    return spec.get("default", "logo.png")


# ----------------------------
#  MAIN ENTRY POINT
# ----------------------------

def get_current_logo(today: dt.date | None = None) -> str:
    today = today or dt.date.today()

    if LogoOverride is not None:
        try:
            from django.db.models import Q
            from django.utils import timezone

            now = timezone.now()
            override = (
                LogoOverride.objects.filter(active=True)
                .filter(Q(starts_at__isnull=True) | Q(starts_at__lte=now))
                .filter(Q(ends_at__isnull=True) | Q(ends_at__gte=now))
                .order_by("priority", "-id")
                .values_list("file_name", flat=True)
                .first()
            )
            if override:
                return override
        except Exception:
            pass

    try:
        spec = load_schedule_spec()
        return _pick_from_schedule(today, spec)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return "logo.png"
