from django.conf import settings
from django.core.mail import send_mail


def send_initial_password_email(personnel, temp_password):
    """
    Sends the initial temporary password to the user.

    In production:
        → goes to the real user

    In development (DEBUG=True):
        → ALWAYS goes to DEV_CATCH_ALL_EMAIL
        → subject is prefixed with intended email address
    """

    intended_email = personnel.email

    #----- DEV MODE (DEBUG=True) -----
    if settings.DEBUG and getattr(settings, "DEV_CATCH_ALL_EMAIL", None):
        to_email = settings.DEV_CATCH_ALL_EMAIL
        subject_prefix = f"[INTENDED: {intended_email}] "
    else:
        #----- PRODUCTION -----
        to_email = personnel.email
        subject_prefix = ""

    subject = subject_prefix + "Your new account password"

    message = (
        f"Hello {personnel.name},\n\n"
        f"Your temporary password is:\n\n"
        f"{temp_password}\n\n"
        "You will be required to change this immediately after logging in.\n"
        "If you did not request this or expected something else, please contact support.\n\n"
        "Regards,\n"
        "Unicorn Admin System"
    )

    send_mail(
        subject,
        message,
        settings.DEFAULT_FROM_EMAIL,
        [to_email],
    )
