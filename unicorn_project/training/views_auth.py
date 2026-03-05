from django.contrib import messages
from django.contrib.auth.views import PasswordChangeView
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse, reverse_lazy
from django.utils.crypto import get_random_string

from unicorn_project.training.models import Personnel
from unicorn_project.training.utils.passwords import send_initial_password_email

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
