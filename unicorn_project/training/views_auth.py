from django.contrib import messages
from django.contrib.auth.views import PasswordChangeView
from django.urls import reverse_lazy

class ForcePasswordChangeView(PasswordChangeView):
    """
    Runs the normal password change, then clears staff_profile.must_change_password
    so users can proceed past the gate.
    """
    success_url = reverse_lazy('password_change_done')

    def form_valid(self, form):
        response = super().form_valid(form)
        prof = getattr(self.request.user, 'staff_profile', None)
        if prof and getattr(prof, 'must_change_password', False):
            prof.must_change_password = False
            prof.save(update_fields=['must_change_password'])
        messages.success(self.request, "Password changed successfully.")
        return response
