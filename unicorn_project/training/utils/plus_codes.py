from urllib.parse import quote

from openlocationcode import openlocationcode as olc

# 11 characters ≈ 3 m × 3 m — similar precision to a what3words square.
_PLUS_CODE_LENGTH = 11


def coordinates_to_plus_code(lat, lng):
    """Return a Google Plus Code for the given coordinates, or '' on failure."""
    try:
        lat = float(lat)
        lng = float(lng)
    except (TypeError, ValueError):
        return ""
    return olc.encode(lat, lng, _PLUS_CODE_LENGTH)


def plus_code_url(code):
    code = (code or "").strip()
    if not code:
        return ""
    return f"https://plus.codes/{quote(code, safe='+')}"


def plus_code_maps_url(code):
    code = (code or "").strip()
    if not code:
        return ""
    return f"https://www.google.com/maps/search/?api=1&query={quote(code)}"
