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

class MustChangePasswordMiddleware:
    ALLOWED_PATHS = (
        "/accounts/login/",
        "/accounts/logout/",
        "/accounts/password_change/",
        "/accounts/password_change/done/",
        "/accounts/password_reset/",
        "/accounts/password_reset/done/",
        "/static/",
        "/favicon.ico",
        "/post-login/",
        # DO NOT include "/" here — causes match-all bug
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user

        # Not logged in
        if not user.is_authenticated:
            return self.get_response(request)

        # Allow true homepage explicitly
        if request.path == "/":
            return self.get_response(request)

        # Use CORRECT related_name → user.personnel
        profile = getattr(user, "personnel", None)

        if not profile:
            return self.get_response(request)

        if not profile.must_change_password:
            return self.get_response(request)

        path = request.path

        # Do NOT redirect on allowed pages
        for allowed in self.ALLOWED_PATHS:
            if path.startswith(allowed):
                return self.get_response(request)

        # Avoid redirect loop
        if path == reverse("password_change"):
            return self.get_response(request)

        messages.warning(request, "You must change your password before continuing.")
        return redirect("password_change")

class AdminGateMiddleware(MiddlewareMixin):
    """
    Hard block for anything under /app/admin/ unless the user is an admin.
    This is *in addition* to per-view decorators (defense in depth).
    """
    def process_request(self, request):
        path = request.path or "/"

        # -------------------------------------------
        # FIRST: allow safe pages (prevents loops!)
        # -------------------------------------------
        for p in SAFE_ADMIN_WHITELIST:
            if path.startswith(p):
                return None

        # -------------------------------------------
        # THIRD: admin-area restriction
        # -------------------------------------------
        if any(path.startswith(prefix) for prefix in ADMIN_PREFIXES):
            if not _is_admin(getattr(request, "user", None)):
                messages.error(request, "You don't have access to the admin area.")
                return redirect("home")

        return None

