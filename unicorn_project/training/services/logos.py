import json
import calendar
import datetime as dt
from pathlib import Path
from django.conf import settings

# Try to import the override model, but don’t crash if migrations aren’t ready
try:
    from ..models import LogoOverride
except Exception:  # ImportError, AppRegistryNotReady, etc.
    LogoOverride = None

SCHEDULE_PATH = Path(settings.BASE_DIR) / "config" / "logo_schedule.json"


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


# ----------------------------
#  MAIN SCHEDULE PICKER
# ----------------------------

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
            start = e - dt.timedelta(days=rule.get("days_before", 3))
            end = e + dt.timedelta(days=rule.get("days_after", 3))
            if start <= today <= end:
                return rule["file"]

    return spec.get("default", "logo.png")


# ----------------------------
#  MAIN ENTRY POINT
# ----------------------------

def get_current_logo(today: dt.date | None = None) -> str:
    today = today or dt.date.today()

    # 1) Admin override wins if available and active
    if LogoOverride is not None:
        try:
            override = next((o for o in LogoOverride.objects.all() if o.is_active_now()), None)
            if override:
                return override.file_name
        except Exception:
            # DB not ready during migrations/collectstatic etc.
            pass

    # 2) Scheduled rules
    try:
        with open(SCHEDULE_PATH, "r", encoding="utf-8") as f:
            spec = json.load(f)
        return _pick_from_schedule(today, spec)
    except FileNotFoundError:
        return "logo.png"
