from django.shortcuts import redirect
from django.urls import reverse

EXEMPT_PREFIXES = (
    '/accounts/login',
    '/accounts/logout',
    '/accounts/password_change',
    '/accounts/password_change/done',
    '/accounts/password_reset',
    '/accounts/reset',
    '/static/',
    '/admin/',           # allow Django admin to render
)

class MustChangePasswordMiddleware:
    """
    If a logged-in user has staff_profile.must_change_password=True,
    redirect them to the password-change page until they change it.
    Exempts auth, admin and static routes to avoid loops.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # skip for anonymous or already on exempt paths
        if request.user.is_authenticated:
            path = request.path.rstrip('/')
            if not any(path.startswith(p) for p in EXEMPT_PREFIXES):
                prof = getattr(request.user, 'staff_profile', None)
                if prof and getattr(prof, 'must_change_password', False):
                    return redirect('password_change')  # named url from auth.urls
        return self.get_response(request)
