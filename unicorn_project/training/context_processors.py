# unicorn_project/training/context_processors.py
from django.conf import settings
from .services.logos import get_current_logo_info
from .utils.user_roles import (
    ADMIN_BOOKING_URL_NAMES,
    get_user_roles,
    resolve_active_role,
    sync_active_role_from_path,
)

def role_context(request):
    """
    Expose role flags & current role to templates.
    """
    user = getattr(request, "user", None)

    is_admin = False
    is_instructor = False
    is_engineer = False
    is_inspector = False
    has_dual_roles = False
    active_role = None

    if user and user.is_authenticated:
        roles = get_user_roles(user)
        is_admin = user.is_superuser or "admin" in roles
        is_instructor = "instructor" in roles
        is_engineer = "engineer" in roles
        is_inspector = "inspector" in roles
        has_dual_roles = sum((is_admin, is_instructor, is_engineer, is_inspector)) > 1
        sync_active_role_from_path(request)
        active_role = resolve_active_role(user, request.session)

    url_name = getattr(getattr(request, "resolver_match", None), "url_name", "") or ""

    return {
        "is_admin": is_admin,
        "is_instructor": is_instructor,
        "is_engineer": is_engineer,
        "is_inspector": is_inspector,
        "current_role": active_role,
        "has_dual_roles": has_dual_roles,
        "nav_admin_bookings_active": url_name in ADMIN_BOOKING_URL_NAMES,
    }

def globals(request):
    """
    Expose selected settings to all templates.
    """
    poll_seconds = getattr(settings, "INBOX_NOTIFY_POLL_SECONDS", 60)
    return {
        "GOOGLE_MAPS_API_KEY": getattr(settings, "GOOGLE_MAPS_API_KEY", ""),
        "ADMIN_INBOX_EMAIL": getattr(settings, "ADMIN_INBOX_EMAIL", ""),
        "OFFICE_PHONE": getattr(settings, "OFFICE_PHONE", ""),
        "APP_VERSION": getattr(settings, "APP_VERSION", ""),
        "DEBUG": bool(settings.DEBUG),
        "REGISTER_SHOW_DATE": getattr(settings, "REGISTER_SHOW_DATE", settings.DEBUG),
        "INBOX_NOTIFY_POLL_MS": max(15, int(poll_seconds)) * 1000,
    }

def logo_context(request):
    info = get_current_logo_info()
    return {
        "current_logo": info["file"],
        "current_logo_label": info.get("label") or "",
    }

from .models import Personnel

def user_display_name(request):
    user = request.user
    name = ""

    if user.is_authenticated:
        # Prefer Personnel record, if exists
        person = getattr(user, "personnel", None)
        if person and person.name:
            name = person.name
        else:
            # fallback to User first/last name or username
            name = user.get_full_name() or user.username

    return {"display_name": name}


def release_notes_prompt(request):
    """Return whether to show the what's-new modal after login."""
    from .release_notes import RELEASE_NOTES_FEATURES, RELEASE_NOTES_TITLE

    show_prompt = bool(
        getattr(request, "user", None)
        and request.user.is_authenticated
        and request.session.get("show_release_notes", False)
    )
    return {
        "show_release_notes": show_prompt,
        "release_notes_title": RELEASE_NOTES_TITLE,
        "release_notes_features": RELEASE_NOTES_FEATURES,
    }


def two_factor_prompt(request):
    """Return whether to show the 2FA prompt to the user."""
    show_prompt = request.session.get("show_2fa_prompt", False)
    return {
        "show_two_factor_prompt": show_prompt,
        "show_2fa_prompt": show_prompt,
    }


def course_swap_badges(request):
    """Legacy — cover swap counts now live in the unified inbox."""
    return {
        "course_swap_menu_badge_count": 0,
        "course_swap_incoming_count": 0,
        "course_swap_outcome_count": 0,
    }


def inbox_badges(request):
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {
            "inbox_unread_count": 0,
            "staff_inbox_unread_count": 0,
            "admin_inbox_unread_count": 0,
        }

    personnel = getattr(user, "personnel", None)
    if not personnel:
        return {
            "inbox_unread_count": 0,
            "staff_inbox_unread_count": 0,
            "admin_inbox_unread_count": 0,
        }

    from .services.staff_inbox import unread_inbox_counts

    counts = unread_inbox_counts(personnel)
    return {
        "inbox_unread_count": counts["total"],
        "staff_inbox_unread_count": counts["staff"],
        "admin_inbox_unread_count": counts["admin"],
    }
