# unicorn_project/training/context_processors.py
from django.conf import settings
from .services.logos import get_current_logo
from .utils.user_roles import available_roles_for_user, resolve_active_role, user_has_role

def role_context(request):
    """
    Expose role flags & current role to templates.
    """
    user = getattr(request, "user", None)

    # Default role flags
    is_admin = False
    is_instructor = False
    is_engineer = False
    is_inspector = False

    if user and user.is_authenticated:
        is_admin = user_has_role(user, "admin")
        is_instructor = user_has_role(user, "instructor")
        is_engineer = user_has_role(user, "engineer")
        is_inspector = user_has_role(user, "inspector")

    active_role = None
    if user and user.is_authenticated:
        active_role = resolve_active_role(user, request.session)

    return {
        "is_admin": is_admin,
        "is_instructor": is_instructor,
        "is_engineer": is_engineer,
        "is_inspector": is_inspector,
        "current_role": active_role,
        "has_dual_roles": len(available_roles_for_user(user)) > 1 if user and user.is_authenticated else False,
    }

def globals(request):
    """
    Expose selected settings to all templates.
    """
    return {
        "GOOGLE_MAPS_API_KEY": getattr(settings, "GOOGLE_MAPS_API_KEY", ""),
        "ADMIN_INBOX_EMAIL": getattr(settings, "ADMIN_INBOX_EMAIL", ""),
        "OFFICE_PHONE": getattr(settings, "OFFICE_PHONE", ""),
        "APP_VERSION": getattr(settings, "APP_VERSION", ""),
        "REGISTER_SHOW_DATE": getattr(settings, "REGISTER_SHOW_DATE", settings.DEBUG),
    }

def logo_context(request):
    return {
        "current_logo": get_current_logo()
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


def two_factor_prompt(request):
    """Return whether to show the 2FA prompt to the user."""
    show_prompt = request.session.get("show_2fa_prompt", False)
    return {
        "show_two_factor_prompt": show_prompt,
        "show_2fa_prompt": show_prompt,
    }
