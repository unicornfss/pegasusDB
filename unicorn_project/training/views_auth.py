from django.contrib.auth import authenticate, login
from django.contrib.auth.forms import AuthenticationForm
from django.contrib import messages
from django.contrib.auth.views import PasswordChangeView
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse, reverse_lazy
from django.utils.crypto import get_random_string

from unicorn_project.training.models import Personnel
from unicorn_project.training.utils.passwords import send_initial_password_email


def _queue_two_factor_prompt(request, user):
    request.session["show_2fa_prompt"] = False


def custom_login(request):
    """Custom login view without 2FA enforcement."""
    if request.user.is_authenticated:
        return HttpResponseRedirect(reverse("home"))
    
    if request.method == "POST":
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            request.session.pop('2fa_user_id', None)
            login(request, user)
            _queue_two_factor_prompt(request, user)
            return HttpResponseRedirect(reverse("post_login"))
    else:
        form = AuthenticationForm(request)
    
    return render(request, "registration/login.html", {"form": form})


def two_factor_auth(request):
    """Complete legacy 2FA logins without requiring a code."""
    user_id = request.session.get('2fa_user_id')
    if not user_id:
        return HttpResponseRedirect(reverse("login"))
    
    try:
        from django.contrib.auth import get_user_model
        User = get_user_model()
        user = User.objects.get(id=user_id)
        personnel = user.personnel
    except (User.DoesNotExist, Personnel.DoesNotExist):
        request.session.pop('2fa_user_id', None)
        return HttpResponseRedirect(reverse("login"))

    login(request, user)
    request.session.pop('2fa_user_id', None)
    _queue_two_factor_prompt(request, user)
    messages.warning(request, "Two-factor authentication is currently disabled. You have been signed in without a code.")
    return HttpResponseRedirect(reverse("post_login"))


class ForcePasswordChangeView(PasswordChangeView):
    """
    Runs the normal password change, then clears staff_profile.must_change_password
    so users can proceed past the gate.
    """
    success_url = reverse_lazy('password_change_done')

    def form_valid(self, form):
        response = super().form_valid(form)
        prof = getattr(self.request.user, 'personnel', None)
        if prof and getattr(prof, 'must_change_password', False):
            prof.must_change_password = False
            prof.save(update_fields=['must_change_password'])
        messages.success(self.request, "Password changed successfully.")
        return response


def forgot_password(request):
    """Generate and email a new temporary password.

    Response is always generic so we don't leak whether an email exists.
    """
    if request.method == "POST":
        email = (request.POST.get("email") or "").strip()

        if email:
            prof = Personnel.objects.filter(email__iexact=email).select_related("user").first()
            if prof and prof.user:
                temp_password = get_random_string(12)

                prof.user.set_password(temp_password)
                prof.user.is_active = True
                prof.user.save(update_fields=["password", "is_active"])

                prof.must_change_password = True
                prof.save(update_fields=["must_change_password"])

                send_initial_password_email(prof, temp_password)

        messages.success(
            request,
            "If an account exists for that email address, a new temporary password has been sent."
        )
        return HttpResponseRedirect(reverse("login"))

    return render(request, "registration/forgot_password.html")


def two_factor_setup(request):
    """Legacy 2FA setup route kept as a redirect while 2FA is disabled."""
    if not request.user.is_authenticated:
        return HttpResponseRedirect(reverse("login"))

    messages.info(request, "Two-factor authentication is currently disabled.")
    return HttpResponseRedirect(reverse("user_profile"))


def two_factor_verify(request):
    """Legacy 2FA verification route kept as a redirect while 2FA is disabled."""
    if not request.user.is_authenticated:
        return HttpResponseRedirect(reverse("login"))

    messages.info(request, "Two-factor authentication is currently disabled.")
    return HttpResponseRedirect(reverse("user_profile"))


def two_factor_disable(request):
    """Legacy 2FA disable route kept as a redirect while 2FA is disabled."""
    if not request.user.is_authenticated:
        return HttpResponseRedirect(reverse("login"))

    messages.info(request, "Two-factor authentication is currently disabled.")
    return HttpResponseRedirect(reverse("user_profile"))
