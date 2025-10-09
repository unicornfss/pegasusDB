from django import forms
from django.contrib.auth.models import User 
from django.db.models import Q
from .models import (
    Business,
    CourseType,
    Instructor,
    TrainingLocation,
    Booking,
    BookingDay,
    Attendance,
)

class AttendanceForm(forms.ModelForm):
    class Meta:
        model=Attendance
        fields=['delegate_name','delegate_email','result','notes']

class BookingForm(forms.ModelForm):
    class Meta:
        model = Booking
        fields = ['business','training_location','course_type','instructor',
                  'course_date','start_time','course_fee','instructor_fee','course_reference']

class BusinessForm(forms.ModelForm):
    address_line = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            "id": "id_address_line",
            "type": "text",
            "inputmode": "text",
            "autocomplete": "off",
            # critically: NO pattern attribute here
        })
    )
    class Meta:
        model = Business
        fields = ["name", "address_line", "town", "postcode", "contact_name", "telephone", "email"]


class CourseTypeForm(forms.ModelForm):
    class Meta:
        model = CourseType
        fields = ['name','code','duration_days','default_course_fee','default_instructor_fee','has_written_exam','has_online_exam']


class InstructorForm(forms.ModelForm):
    """
    Admin form for creating/updating instructors with a 'user' selector that:
      - lists only non-superuser accounts that are NOT already assigned to another instructor
      - but allows keeping the currently assigned user when editing
    Also blocks assigning a superuser or a user already linked elsewhere.
    """
    user = forms.ModelChoiceField(
        queryset=User.objects.none(),
        required=False,
        help_text="Optional login for this instructor. Only unassigned (non-superuser) users are listed."
    )

    class Meta:
        model = Instructor
        fields = [
            'name', 'address_line', 'town', 'postcode',
            'telephone', 'email',
            'bank_sort_code', 'bank_account_number', 'name_on_account',
            'user'
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'address_line': forms.TextInput(attrs={'class': 'form-control', 'id': 'id_address_line'}),
            'town': forms.TextInput(attrs={'class': 'form-control', 'id': 'id_town'}),
            'postcode': forms.TextInput(attrs={'class': 'form-control', 'id': 'id_postcode'}),
            'telephone': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'bank_sort_code': forms.TextInput(attrs={'class': 'form-control'}),
            'bank_account_number': forms.TextInput(attrs={'class': 'form-control'}),
            'name_on_account': forms.TextInput(attrs={'class': 'form-control'}),
            'user': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Base: only non-superusers
        base_qs = User.objects.filter(is_superuser=False)

        if self.instance and self.instance.pk and self.instance.user_id:
            # Allow currently linked user OR any user not linked to any instructor
            qs = base_qs.filter(
                Q(instructor__isnull=True) | Q(pk=self.instance.user_id)
            )
        else:
            # New instructor: only users not linked to any instructor
            qs = base_qs.filter(instructor__isnull=True)

        self.fields['user'].queryset = qs.order_by('username')

    def clean_user(self):
        user = self.cleaned_data.get('user')
        if not user:
            return user

        if user.is_superuser:
            raise forms.ValidationError("You cannot assign a superuser account.")

        # Ensure uniqueness of user→instructor mapping
        existing = Instructor.objects.filter(user=user)
        if self.instance and self.instance.pk:
            existing = existing.exclude(pk=self.instance.pk)
        if existing.exists():
            raise forms.ValidationError("That user is already assigned to another instructor.")

        return user

class TrainingLocationForm(forms.ModelForm):
    class Meta:
        model = TrainingLocation
        fields = ['name','address_line','town','postcode',
                  'contact_name','telephone','email']
        widgets = {
            'business': forms.HiddenInput(),  # we’ll set it in the view
        }

class InstructorProfileForm(forms.ModelForm):
    """
    Used by INSTRUCTORS themselves. Does NOT expose the `user` field.
    """
    class Meta:
        model = Instructor
        # explicitly list editable fields for instructors
        fields = [
            "name", "address_line", "town", "postcode",
            "telephone", "email",
            "bank_sort_code", "bank_account_number", "name_on_account",
        ]

class AdminInstructorForm(forms.ModelForm):
    """
    Used by ADMINS in the admin UI. DOES expose the `user` link so an admin can
    assign or change which Django user account is tied to the instructor record.
    """
    user = forms.ModelChoiceField(
        queryset=User.objects.order_by("username"),
        required=False,
        help_text="Optional: link to an existing Django user account (for login)."
    )

    class Meta:
        model = Instructor
        fields = [
            "user",             # admin can assign/change
            "name", "address_line", "town", "postcode",
            "telephone", "email",
            "bank_sort_code", "bank_account_number", "name_on_account",
        ]