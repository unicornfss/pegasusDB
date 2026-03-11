from django.contrib import messages
from django.contrib.auth.views import PasswordChangeView
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse, reverse_lazy
from django.utils.crypto import get_random_string
import pyotp

from django.contrib import messages
from django.contrib.auth.views import PasswordChangeView
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse, reverse_lazy
from django.utils.crypto import get_random_string
from django.contrib.auth import authenticate, login
from django.contrib.auth.forms import AuthenticationForm
import pyotp

from unicorn_project.training.models import Personnel
from unicorn_project.training.utils.passwords import send_initial_password_email


def _queue_two_factor_prompt(request, user):
    personnel = getattr(user, "personnel", None)
    request.session["show_2fa_prompt"] = bool(personnel and not personnel.totp_secret)


def custom_login(request):
    """Custom login view that handles 2FA."""
    if request.user.is_authenticated:
        return HttpResponseRedirect(reverse("home"))
    
    if request.method == "POST":
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            personnel = getattr(user, 'personnel', None)
            
            if personnel and personnel.totp_secret:
                # Store user in session for 2FA verification
                request.session['2fa_user_id'] = user.id
                return HttpResponseRedirect(reverse("two_factor_auth"))
            else:
                # No 2FA, login normally
                login(request, user)
                _queue_two_factor_prompt(request, user)
                return HttpResponseRedirect(reverse("post_login"))
    else:
        form = AuthenticationForm(request)
    
    return render(request, "registration/login.html", {"form": form})


def two_factor_auth(request):
    """Verify 2FA code during login."""
    user_id = request.session.get('2fa_user_id')
    if not user_id:
        return HttpResponseRedirect(reverse("login"))
    
    try:
        from django.contrib.auth import get_user_model
        User = get_user_model()
        user = User.objects.get(id=user_id)
        personnel = user.personnel
    except (User.DoesNotExist, Personnel.DoesNotExist):
        del request.session['2fa_user_id']
        return HttpResponseRedirect(reverse("login"))
    
    if request.method == "POST":
        code = request.POST.get("code", "").strip()
        totp = pyotp.TOTP(personnel.totp_secret)
        
        if totp.verify(code):
            login(request, user)
            del request.session['2fa_user_id']
            _queue_two_factor_prompt(request, user)
            return HttpResponseRedirect(reverse("post_login"))
        else:
            messages.error(request, "Invalid 2FA code.")
    
    return render(request, "two_factor/auth.html")


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
    """Enable 2FA for the current user."""
    if not request.user.is_authenticated:
        return HttpResponseRedirect(reverse("login"))
    
    personnel = getattr(request.user, 'personnel', None)
    if not personnel:
        messages.error(request, "Profile not found.")
        return HttpResponseRedirect(reverse("home"))
    
    if personnel.totp_secret:
        messages.info(request, "2FA is already enabled.")
        return HttpResponseRedirect(reverse("user_profile"))
    
    if request.method == "POST":
        secret = pyotp.random_base32()
        personnel.totp_secret = secret
        personnel.save(update_fields=['totp_secret'])
        
        totp = pyotp.TOTP(secret)
        provisioning_uri = totp.provisioning_uri(name=personnel.email, issuer_name="Unicorn Pegasus")
        
        return render(request, "two_factor/setup.html", {
            'secret': secret,
            'provisioning_uri': provisioning_uri,
        })
    
    return render(request, "two_factor/setup_confirm.html")


def two_factor_verify(request):
    """Verify 2FA code during setup."""
    if not request.user.is_authenticated:
        return HttpResponseRedirect(reverse("login"))
    
    personnel = getattr(request.user, 'personnel', None)
    if not personnel or not personnel.totp_secret:
        messages.error(request, "2FA not set up.")
        return HttpResponseRedirect(reverse("user_profile"))
    
    if request.method == "POST":
        code = request.POST.get("code", "").strip()
        totp = pyotp.TOTP(personnel.totp_secret)
        
        if totp.verify(code):
            messages.success(request, "2FA has been enabled successfully.")
            return HttpResponseRedirect(reverse("user_profile"))
        else:
            messages.error(request, "Invalid code. Please try again.")
    
    return render(request, "two_factor/verify.html")


def two_factor_disable(request):
    """Disable 2FA for the current user."""
    if not request.user.is_authenticated:
        return HttpResponseRedirect(reverse("login"))
    
    personnel = getattr(request.user, 'personnel', None)
    if not personnel:
        messages.error(request, "Profile not found.")
        return HttpResponseRedirect(reverse("home"))
    
    if not personnel.totp_secret:
        messages.info(request, "2FA is not enabled.")
        return HttpResponseRedirect(reverse("user_profile"))
    
    if request.method == "POST":
        code = request.POST.get("code", "").strip()
        totp = pyotp.TOTP(personnel.totp_secret)
        
        if totp.verify(code):
            personnel.totp_secret = None
            personnel.save(update_fields=['totp_secret'])
            messages.success(request, "2FA has been disabled.")
            return HttpResponseRedirect(reverse("user_profile"))
        else:
            messages.error(request, "Invalid code. Please try again.")
    
    return render(request, "two_factor/disable.html")
