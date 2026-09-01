"""
Public business portal — magic-link login, course list, released certificates.
"""
from __future__ import annotations

from django.contrib import messages
from django.db.models import Min
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from .forms import BusinessPortalContactForm, BusinessPortalLoginForm
from .models import Booking, Business
from .utils.business_portal import (
    add_portal_email,
    businesses_for_portal_email,
    consume_login_token,
    create_login_token,
    email_can_access_business,
    normalise_email,
)
from .utils.certificates import build_certificates_pdf_for_booking, _unique_delegates_for_booking
from .utils.emailing import send_pdf_to_booking_contacts
from .utils.site_url import public_site_url

SESSION_EMAIL = "business_portal_email"

ACTIVE_STATUSES = ("scheduled", "in_progress", "awaiting_closure")
COMPLETED_STATUSES = ("completed",)


def _clear_session(request) -> None:
    request.session.pop(SESSION_EMAIL, None)


def _session_email(request) -> str:
    return normalise_email(request.session.get(SESSION_EMAIL))


def _require_email(request):
    email = _session_email(request)
    if not email:
        return None
    return email


def _format_time(t) -> str:
    if not t:
        return ""
    return t.strftime("%H:%M")


def _format_date_range(booking: Booking) -> str:
    days = sorted(
        booking.days.all(),
        key=lambda d: (d.date, d.start_time or d.end_time or d.date),
    )
    dates = [d.date for d in days]
    if not dates:
        d = booking.course_date
        return d.strftime("%d %b %Y") if d else "—"
    if len(dates) == 1:
        return dates[0].strftime("%d %b %Y")
    return f"{dates[0].strftime('%d %b %Y')} – {dates[-1].strftime('%d %b %Y')}"


def _times_display(booking: Booking) -> str:
    """Compact start–finish for list cards (shared window, or first day if mixed)."""
    days = sorted(booking.days.all(), key=lambda d: (d.date, d.start_time or d.end_time or d.date))
    if not days:
        st = _format_time(booking.start_time)
        return f"{st} –" if st else ""

    windows = []
    for d in days:
        st = _format_time(d.start_time) or _format_time(booking.start_time)
        et = _format_time(d.end_time)
        if st or et:
            windows.append((st, et))

    if not windows:
        st = _format_time(booking.start_time)
        return f"{st} –" if st else ""

    unique = set(windows)
    st, et = windows[0]
    if len(unique) == 1:
        if st and et:
            return f"{st} – {et}"
        if st:
            return f"From {st}"
        if et:
            return f"Until {et}"
        return ""
    # Mixed day times — show first day and note variation
    if st and et:
        return f"{st} – {et} (varies by day)"
    if st:
        return f"From {st} (varies by day)"
    return "Times vary by day"


def _day_schedule(booking: Booking) -> list[dict]:
    days = sorted(booking.days.all(), key=lambda d: (d.date, d.start_time or d.end_time or d.date))
    rows = []
    for d in days:
        st = d.start_time or booking.start_time
        et = d.end_time
        rows.append({
            "date": d.date,
            "start_time": st,
            "end_time": et,
            "start_display": _format_time(st) or "—",
            "end_display": _format_time(et) or "—",
        })
    if not rows and booking.course_date:
        st = booking.start_time
        rows.append({
            "date": booking.course_date,
            "start_time": st,
            "end_time": None,
            "start_display": _format_time(st) or "—",
            "end_display": "—",
        })
    return rows


def _bookings_for_business(business: Business):
    return (
        Booking.objects.filter(business=business)
        .exclude(status="cancelled")
        .select_related("course_type", "instructor", "training_location")
        .prefetch_related("days")
        .annotate(first_day=Min("days__date"))
        .order_by("-first_day", "-course_date", "-created_at")
    )


def _send_magic_link(email: str, request) -> None:
    from django.conf import settings
    from django.template.loader import render_to_string

    token = create_login_token(email)
    path = reverse("business_portal_consume", args=[token])
    base = public_site_url() or request.build_absolute_uri("/").rstrip("/")
    link = f"{base}{path}"

    subject = "Business portal login — Unicorn Training"
    disclaimer_html = ""
    if getattr(settings, "DEBUG", False):
        disclaimer_html = (
            "⚠️ <b>DEV / TEST</b><br>"
            "<i>Sent from a development environment. "
            f"Intended recipient: {email}</i>"
        )

    html = render_to_string(
        "training/emails/business_portal_login.html",
        {
            "heading": "Business portal login",
            "login_url": link,
            "disclaimer_html": disclaimer_html,
        },
    )
    send_pdf_to_booking_contacts(
        subject=subject,
        body=html,
        to=[email],
        html=True,
    )


@require_http_methods(["GET", "POST"])
def business_portal_login(request):
    email = _session_email(request)
    if email and businesses_for_portal_email(email).exists():
        return redirect("business_portal_home")

    form = BusinessPortalLoginForm(request.POST or None)
    sent = False

    if request.method == "POST" and form.is_valid():
        addr = normalise_email(form.cleaned_data["email"])
        matches = businesses_for_portal_email(addr)
        # Always show the same success copy (do not reveal whether the email is known)
        sent = True
        if matches.exists():
            try:
                _send_magic_link(addr, request)
            except Exception:
                # Still show success to the user; log via messages for admins in DEBUG only
                messages.error(
                    request,
                    "We could not send the login email just now. Please try again shortly.",
                )
                sent = False

    return render(request, "public/business_portal_login.html", {
        "form": form,
        "sent": sent,
    })


@require_http_methods(["GET"])
def business_portal_consume(request, token: str):
    email = consume_login_token(token)
    if not email or not businesses_for_portal_email(email).exists():
        messages.error(request, "That login link is invalid or has expired. Please request a new one.")
        return redirect("business_portal_login")

    request.session[SESSION_EMAIL] = email
    request.session.modified = True
    messages.success(request, "You are signed in.")
    return redirect("business_portal_home")


@require_http_methods(["GET", "POST"])
def business_portal_logout(request):
    _clear_session(request)
    return redirect("business_portal_login")


@require_http_methods(["GET"])
def business_portal_home(request):
    email = _require_email(request)
    if not email:
        return redirect("business_portal_login")

    businesses = list(businesses_for_portal_email(email))
    if not businesses:
        _clear_session(request)
        messages.error(request, "Your email is no longer authorised. Please contact your training provider.")
        return redirect("business_portal_login")

    if len(businesses) == 1:
        return redirect("business_portal_business", pk=businesses[0].pk)

    return render(request, "public/business_portal_pick.html", {
        "email": email,
        "businesses": businesses,
    })


@require_http_methods(["GET"])
def business_portal_business(request, pk):
    from .services.booking_status import auto_update_booking_statuses

    email = _require_email(request)
    if not email:
        return redirect("business_portal_login")

    auto_update_booking_statuses()

    business = get_object_or_404(Business, pk=pk)
    if not email_can_access_business(email, business):
        messages.error(request, "You do not have access to that business.")
        return redirect("business_portal_home")

    bookings = list(_bookings_for_business(business))
    for b in bookings:
        b.dates_display = _format_date_range(b)
        b.times_display = _times_display(b)
        b.certs_available = bool(b.certificates_released)
        b.is_completed = (b.status or "") == "completed"
        b.is_upcoming = (b.status or "") in ACTIVE_STATUSES

    upcoming = [b for b in bookings if b.is_upcoming]
    completed = [b for b in bookings if b.is_completed]
    other = [b for b in bookings if not b.is_upcoming and not b.is_completed]

    multi = businesses_for_portal_email(email).count() > 1

    return render(request, "public/business_portal_home.html", {
        "email": email,
        "business": business,
        "upcoming": upcoming,
        "completed": completed,
        "other": other,
        "show_business_switcher": multi,
    })


@require_http_methods(["GET", "POST"])
def business_portal_booking(request, pk):
    from .services.booking_status import auto_update_booking_statuses

    email = _require_email(request)
    if not email:
        return redirect("business_portal_login")

    auto_update_booking_statuses()

    booking = get_object_or_404(
        Booking.objects.select_related("business", "course_type", "instructor", "training_location")
        .prefetch_related("days"),
        pk=pk,
    )
    if not email_can_access_business(email, booking.business):
        messages.error(request, "You do not have access to that course.")
        return redirect("business_portal_home")

    can_edit_contact = (booking.status or "") == "scheduled"
    contact_form = None

    if can_edit_contact:
        if request.method == "POST":
            contact_form = BusinessPortalContactForm(request.POST, instance=booking)
            if contact_form.is_valid():
                updated = contact_form.save()
                if updated.email:
                    add_portal_email(updated.business, updated.email)
                messages.success(request, "Contact details updated.")
                return redirect("business_portal_booking", pk=booking.pk)
            messages.error(request, "Please correct the errors below.")
        else:
            contact_form = BusinessPortalContactForm(instance=booking)

    cert_delegates = []
    if booking.certificates_released:
        cert_delegates = _unique_delegates_for_booking(booking)

    return render(request, "public/business_portal_booking.html", {
        "email": email,
        "business": booking.business,
        "booking": booking,
        "dates_display": _format_date_range(booking),
        "day_schedule": _day_schedule(booking),
        "certificates_released": booking.certificates_released,
        "cert_delegates": cert_delegates,
        "can_edit_contact": can_edit_contact,
        "contact_form": contact_form,
    })


@require_http_methods(["GET"])
def business_portal_certificates_pdf(request, pk):
    email = _require_email(request)
    if not email:
        return redirect("business_portal_login")

    booking = get_object_or_404(
        Booking.objects.select_related("business", "course_type", "instructor"),
        pk=pk,
    )
    if not email_can_access_business(email, booking.business):
        messages.error(request, "You do not have access to that course.")
        return redirect("business_portal_home")
    if not booking.certificates_released:
        messages.error(request, "Certificates for this course are not released yet.")
        return redirect("business_portal_booking", pk=booking.pk)

    result = build_certificates_pdf_for_booking(booking)
    if not result:
        messages.error(request, "No certificates are available for this course yet.")
        return redirect("business_portal_booking", pk=booking.pk)

    filename, pdf_bytes = result
    resp = HttpResponse(pdf_bytes, content_type="application/pdf")
    resp["Content-Disposition"] = f'inline; filename="{filename}"'
    return resp
