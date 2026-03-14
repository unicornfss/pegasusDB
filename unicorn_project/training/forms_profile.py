from django import forms
from django.contrib.auth.models import User
from .models import Personnel


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
            "bank_sort_code": forms.TextInput(attrs={"class": "form-control"}),
            "bank_account_number": forms.TextInput(attrs={"class": "form-control"}),
            "name_on_account": forms.TextInput(attrs={"class": "form-control"}),
        }

    def clean_sidebar_custom_color(self):
        value = (self.cleaned_data.get("sidebar_custom_color") or "").strip()
        if not value:
            return ""
        if not _is_valid_hex_color(value):
            raise forms.ValidationError("Enter a valid 6-digit hex colour.")
        return value.lower()
