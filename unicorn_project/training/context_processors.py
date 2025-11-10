# unicorn_project/training/context_processors.py
from django.conf import settings
from .services.logos import get_current_logo

def role_context(request):
    """
    Expose role flags & current role to templates.
    """
    user = getattr(request, "user", None)
    is_admin = False
    is_instructor = False

    if user and user.is_authenticated:
        # superuser counts as admin
        is_admin = user.is_superuser or user.groups.filter(name__iexact="admin").exists()
        is_instructor = user.groups.filter(name__iexact="instructor").exists()

    # Optional: an active role stored in session (not strictly required)
    active_role = request.session.get("active_role")
    if active_role not in {"admin", "instructor", None}:
        active_role = None
    if not active_role:
        active_role = "admin" if is_admin else ("instructor" if is_instructor else None)

    return {
        "is_admin": is_admin,
        "is_instructor": is_instructor,
        "current_role": active_role,
        "has_dual_roles": is_admin and is_instructor,
    }

def globals(request):
    """
    Expose selected settings to all templates.
    """
    return {
        "GOOGLE_MAPS_API_KEY": getattr(settings, "GOOGLE_MAPS_API_KEY", ""),
    }

def logo_context(request):
    return {
        "current_logo": get_current_logo()
    }