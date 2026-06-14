import logging
from urllib.parse import urlencode

import requests
from django.conf import settings

from .booking_details import _location_lines

logger = logging.getLogger(__name__)


def _maps_api_key() -> str:
    return (getattr(settings, "GOOGLE_MAPS_API_KEY", "") or "").strip()


def _postcode_or_address(*parts) -> str:
    bits = [p.strip() for p in parts if p and str(p).strip()]
    return ", ".join(bits)


def origin_for_instructor(instructor) -> str:
    if not instructor:
        return ""
    postcode = (getattr(instructor, "postcode", "") or "").strip()
    if postcode:
        return postcode
    return _postcode_or_address(
        getattr(instructor, "address_line", ""),
        getattr(instructor, "town", ""),
    )


def destination_for_booking(booking) -> str:
    lat = booking.effective_precise_lat()
    lng = booking.effective_precise_lng()
    if lat is not None and lng is not None:
        return f"{lat},{lng}"

    loc = booking.training_location
    if not loc:
        return ""
    postcode = (loc.postcode or "").strip()
    if postcode:
        return postcode
    lines = _location_lines(loc)
    return ", ".join(lines)


def fetch_driving_duration_seconds(origin: str, destination: str) -> int | None:
    origin = (origin or "").strip()
    destination = (destination or "").strip()
    api_key = _maps_api_key()
    if not origin or not destination or not api_key:
        return None

    params = urlencode({
        "origins": origin,
        "destinations": destination,
        "mode": "driving",
        "key": api_key,
    })
    url = f"https://maps.googleapis.com/maps/api/distancematrix/json?{params}"

    try:
        response = requests.get(url, timeout=8)
        response.raise_for_status()
        payload = response.json()
    except Exception:
        logger.exception("Google Distance Matrix request failed")
        return None

    if payload.get("status") != "OK":
        logger.warning("Distance Matrix status=%s", payload.get("status"))
        return None

    rows = payload.get("rows") or []
    if not rows:
        return None
    elements = rows[0].get("elements") or []
    if not elements:
        return None
    element = elements[0]
    if element.get("status") != "OK":
        logger.warning("Distance Matrix element status=%s", element.get("status"))
        return None

    duration = element.get("duration") or {}
    value = duration.get("value")
    try:
        seconds = int(value)
    except (TypeError, ValueError):
        return None
    return seconds if seconds > 0 else None


def update_booking_travel_duration(booking, *, save=True) -> int | None:
    """Refresh one-way driving time from instructor home to venue."""
    booking = (
        booking.__class__.objects.select_related("instructor", "training_location")
        .filter(pk=booking.pk)
        .first()
    )
    if not booking:
        return None

    origin = origin_for_instructor(booking.instructor)
    destination = destination_for_booking(booking)
    seconds = fetch_driving_duration_seconds(origin, destination)
    if save:
        booking.travel_duration_seconds = seconds
        booking.save(update_fields=["travel_duration_seconds"])
    return seconds


def travel_duration_seconds_for_booking(booking) -> int | None:
    if booking.travel_duration_seconds:
        return int(booking.travel_duration_seconds)
    return update_booking_travel_duration(booking, save=True)
