# unicorn_project/training/context_processors.py
from django.conf import settings
from .services.logos import get_current_logo

# unicorn_project/training/context_processors.py
from django.conf import settings
from .services.logos import get_current_logo

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
        # Admin = superuser or in "admin" group
        is_admin = user.is_superuser or user.groups.filter(name__iexact="admin").exists()

        # Instructor role
        is_instructor = user.groups.filter(name__iexact="instructor").exists()

        # New roles
        is_engineer = user.groups.filter(name__iexact="engineer").exists()
        is_inspector = user.groups.filter(name__iexact="inspector").exists()

    # Active role handling
    active_role = request.session.get("active_role")
    if active_role not in {"admin", "instructor", "engineer", "inspector", None}:
        active_role = None

    if not active_role:
        if is_admin:
            active_role = "admin"
        elif is_instructor:
            active_role = "instructor"
        elif is_engineer:
            active_role = "engineer"
        elif is_inspector:
            active_role = "inspector"

    return {
        "is_admin": is_admin,
        "is_instructor": is_instructor,
        "is_engineer": is_engineer,
        "is_inspector": is_inspector,
        "current_role": active_role,
        "has_dual_roles": sum([is_admin, is_instructor, is_engineer, is_inspector]) > 1,
    }

def globals(request):
    """
    Expose selected settings to all templates.
    """
    return {
        "GOOGLE_MAPS_API_KEY": getattr(settings, "GOOGLE_MAPS_API_KEY", ""),
        "ADMIN_INBOX_EMAIL": getattr(settings, "ADMIN_INBOX_EMAIL", ""),
        "OFFICE_PHONE": getattr(settings, "OFFICE_PHONE", ""),
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
