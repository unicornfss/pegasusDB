# unicorn_project/training/middleware.py
from django.shortcuts import redirect
from django.contrib import messages
from django.urls import reverse
from django.utils.deprecation import MiddlewareMixin

ADMIN_PREFIXES = (
    "/app/admin/",   # your custom admin area
)

SAFE_ADMIN_WHITELIST = (
    # allow login/logout/password pages, static, etc.
    "/accounts/login/",
    "/accounts/logout/",
    "/accounts/password_change/",
    "/accounts/password_change/done/",
    "/accounts/password_reset/",
    "/accounts/password_reset/done/",
    "/accounts/reset/",
    "/static/",
    "/favicon.ico",
)

def _is_admin(user):
    return user.is_authenticated and (
        user.is_superuser
        or user.is_staff
        or user.groups.filter(name__iexact="admin").exists()
    )

class MustChangePasswordMiddleware(MiddlewareMixin):
    """
    (You already had this — keep as-is.)
    Blocks any page except the change-password screen if the user
    is flagged to change password.
    """
    def process_request(self, request):
        user = getattr(request, "user", None)
        # Only act for logged-in users
        if not (user and user.is_authenticated):
            return None

        must_change = getattr(user, "profile", None)
        must_change = getattr(must_change, "must_change_password", False)
        if not must_change:
            return None

        path = request.path or "/"
        # let them access only the force-change page and auth endpoints
        if path.startswith("/accounts/password_change/") or path.startswith("/accounts/login/") or path.startswith("/accounts/logout/"):
            return None

        messages.warning(request, "You must change your password before continuing.")
        return redirect("password_change")  # django.contrib.auth.views.PasswordChangeView

class AdminGateMiddleware(MiddlewareMixin):
    """
    Hard block for anything under /app/admin/ unless the user is an admin.
    This is *in addition* to per-view decorators (defense in depth).
    """
    def process_request(self, request):
        path = request.path or "/"

        # Fast pass: ignore clearly safe paths
        for p in SAFE_ADMIN_WHITELIST:
            if path.startswith(p):
                return None

        # Only check our custom admin area patterns
        if any(path.startswith(prefix) for prefix in ADMIN_PREFIXES):
            if not _is_admin(getattr(request, "user", None)):
                messages.error(request, "You don't have access to the admin area.")
                return redirect("home")

        return None
