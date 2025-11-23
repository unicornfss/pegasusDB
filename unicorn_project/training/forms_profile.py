from django import forms
from django.contrib.auth.models import User
from .models import Personnel


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
            "bank_sort_code",
            "bank_account_number",
            "name_on_account",
        ]
        widgets = {
            "address_line": forms.TextInput(attrs={"class": "form-control"}),
            "town": forms.TextInput(attrs={"class": "form-control"}),
            "postcode": forms.TextInput(attrs={"class": "form-control"}),
            "telephone": forms.TextInput(attrs={"class": "form-control"}),
            "bank_sort_code": forms.TextInput(attrs={"class": "form-control"}),
            "bank_account_number": forms.TextInput(attrs={"class": "form-control"}),
            "name_on_account": forms.TextInput(attrs={"class": "form-control"}),
        }
