from django import forms
from django.contrib.auth.models import User
from .models import Personnel
from .utils.user_roles import available_roles_for_user, role_choice_label

UPCOMING_REMINDER_DAY_CHOICES = [
    ("", "—"),
    ("1", "1 day before"),
    ("2", "2 days before"),
    ("3", "3 days before"),
    ("4", "4 days before"),
    ("5", "5 days before"),
    ("6", "6 days before"),
    ("7", "7 days before"),
    ("14", "14 days before"),
    ("21", "21 days before"),
]


def _coerce_reminder_days(value):
    if value in (None, ""):
        return None
    return int(value)


def _is_valid_hex_color(value: str) -> bool:
    if not value:
        return True
    if len(value) != 7 or not value.startswith("#"):
        return False
    return all(ch in "0123456789abcdefABCDEF" for ch in value[1:])


class UserProfileForm(forms.ModelForm):
    """Updates the built-in Django User model (name + email)."""

    class Meta:
        model = User
        fields = ["first_name", "last_name", "email"]
        widgets = {
            "first_name": forms.TextInput(attrs={"class": "form-control"}),
            "last_name": forms.TextInput(attrs={"class": "form-control"}),
            "email": forms.EmailInput(attrs={"class": "form-control"}),
        }


class PersonnelProfileForm(forms.ModelForm):
    """Updates the Personnel model fields (address, phone, bank)."""

    default_dashboard_role = forms.ChoiceField(
        required=False,
        choices=[],
        widget=forms.Select(attrs={"class": "form-select"}),
        label="Default dashboard",
        help_text="Choose which dashboard opens when you log in.",
    )

    class Meta:
        model = Personnel
        fields = [
            "address_line",
            "town",
            "postcode",
            "telephone",
            "dyslexia_mode",
            "night_mode",
            "pastel_background",
            "sidebar_theme",
            "sidebar_custom_color",
            "avatar_icon",
            "default_dashboard_role",
            "notify_new_bookings_telegram",
            "notify_booking_changes_telegram",
            "notify_reminders_telegram",
            "notify_upcoming_bookings_telegram",
            "notify_cover_requests_telegram",
            "notify_new_bookings_email",
            "notify_booking_changes_email",
            "notify_reminders_email",
            "notify_upcoming_bookings_email",
            "upcoming_reminder_days_1",
            "upcoming_reminder_days_2",
            "upcoming_reminder_days_3",
            "bank_sort_code",
            "bank_account_number",
            "name_on_account",
        ]
        widgets = {
            "address_line": forms.TextInput(attrs={"class": "form-control"}),
            "town": forms.TextInput(attrs={"class": "form-control"}),
            "postcode": forms.TextInput(attrs={"class": "form-control"}),
            "telephone": forms.TextInput(attrs={"class": "form-control"}),
            "dyslexia_mode": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "night_mode": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "pastel_background": forms.Select(attrs={"class": "form-select"}),
            "sidebar_theme": forms.RadioSelect(),
            "sidebar_custom_color": forms.HiddenInput(),
            "avatar_icon": forms.Select(attrs={"class": "form-select"}),
            "notify_new_bookings_telegram": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "notify_booking_changes_telegram": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "notify_reminders_telegram": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "notify_upcoming_bookings_telegram": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "notify_cover_requests_telegram": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "notify_new_bookings_email": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "notify_booking_changes_email": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "notify_reminders_email": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "notify_upcoming_bookings_email": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "upcoming_reminder_days_1": forms.Select(attrs={"class": "form-select form-select-sm"}),
            "upcoming_reminder_days_2": forms.Select(attrs={"class": "form-select form-select-sm"}),
            "upcoming_reminder_days_3": forms.Select(attrs={"class": "form-select form-select-sm"}),
            "bank_sort_code": forms.TextInput(attrs={"class": "form-control"}),
            "bank_account_number": forms.TextInput(attrs={"class": "form-control"}),
            "name_on_account": forms.TextInput(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        for field_name in (
            "upcoming_reminder_days_1",
            "upcoming_reminder_days_2",
            "upcoming_reminder_days_3",
        ):
            self.fields[field_name] = forms.TypedChoiceField(
                choices=UPCOMING_REMINDER_DAY_CHOICES,
                required=False,
                coerce=_coerce_reminder_days,
                empty_value=None,
                widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
                label="",
            )
            initial = getattr(self.instance, field_name, None)
            self.fields[field_name].initial = str(initial) if initial else ""
        roles = available_roles_for_user(user) if user else []
        if len(roles) <= 1:
            self.fields.pop("default_dashboard_role", None)
        else:
            self.fields["default_dashboard_role"].choices = [
                ("", "Automatic (Admin first, then Instructor, …)"),
                *[(role, role_choice_label(role)) for role in roles],
            ]

    def clean_default_dashboard_role(self):
        value = (self.cleaned_data.get("default_dashboard_role") or "").strip()
        if not value:
            return ""
        if self.user and value not in available_roles_for_user(self.user):
            raise forms.ValidationError("Choose a dashboard for one of your assigned roles.")
        return value

    def clean_sidebar_custom_color(self):
        value = (self.cleaned_data.get("sidebar_custom_color") or "").strip()
        if not value:
            return ""
        if not _is_valid_hex_color(value):
            raise forms.ValidationError("Enter a valid 6-digit hex colour.")
        return value.lower()

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("notify_upcoming_bookings_telegram") or cleaned.get("notify_upcoming_bookings_email"):
            days = [
                cleaned.get("upcoming_reminder_days_1"),
                cleaned.get("upcoming_reminder_days_2"),
                cleaned.get("upcoming_reminder_days_3"),
            ]
            chosen = [day for day in days if day]
            if not chosen:
                raise forms.ValidationError(
                    "Choose at least one reminder day for upcoming booking alerts."
                )
            if len(chosen) != len(set(chosen)):
                raise forms.ValidationError(
                    "Each upcoming booking reminder must use a different number of days."
                )
        return cleaned
