from django import forms
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.forms import inlineformset_factory
from . import models as m

from .models import (
    Business,
    CourseType,
    Instructor,
    TrainingLocation,
    Booking,
    BookingDay,
    Attendance,
    DelegateRegister,
    CourseCompetency
)

import string, secrets

# ---------------- Attendance ----------------
#class AttendanceForm(forms.ModelForm):
#    class Meta:
#        model = Attendance
#         fields = ["delegate_name", "delegate_email", "result", "notes"]


# ---------------- Booking ----------------

class BookingForm(forms.ModelForm):
    class Meta:
        model = Booking
        fields = [
            "business",
            "training_location",
            "course_type",
            "instructor",
            "course_date",
            "start_time",
            "course_fee",
            "instructor_fee",
            "contact_name",
            "telephone",
            "email",
            "course_reference",
            "comments",
        ]
        widgets = {
            "course_date": forms.DateInput(attrs={"type": "date"}),
            "start_time": forms.TimeInput(attrs={"type": "time"}),
            "course_reference": forms.TextInput(attrs={"readonly": "readonly"}),
            "comments": forms.Textarea(attrs={"rows": 3, "class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Start with none until we know the business
        self.fields["training_location"].queryset = TrainingLocation.objects.none()

        # --- Always display a blank option at the top ---
        # CHANGED: force an explicit choice and keep a visible blank row
        self.fields["training_location"].empty_label = "— Select a training location —"  # NEW
        self.fields["training_location"].required = True                                  # NEW
        # Make sure we don't carry any implicit initial on create
        if not (self.instance and self.instance.pk):                                      # NEW
            self.fields["training_location"].initial = None                               # NEW

        # Determine selected business (POST > instance)
        data = self.data if self.is_bound else None
        biz_id = None
        if data and data.get("business"):
            biz_id = data.get("business")
        elif self.instance and self.instance.pk:
            biz_id = self.instance.business_id

        qs = TrainingLocation.objects.none()
        if biz_id:
            qs = TrainingLocation.objects.filter(business_id=biz_id).order_by("name")
            self.fields["training_location"].queryset = qs

            # HARD-GUARANTEE the blank row shows up even if Django would hide it
            # (e.g., when an initial sneaks in or browser autofill happens)
            choices = [("", "— Select a training location —")]                            # NEW
            choices += [(str(o.pk), str(o)) for o in qs]                                  # NEW
            self.fields["training_location"].widget.choices = choices                     # NEW

        # Prefill fees & contacts on CREATE (don’t overwrite user POST values)
        creating = not (self.instance and self.instance.pk)

        if creating:
            # Fees from course type
            ct_id = (data.get("course_type") if data else self.initial.get("course_type"))
            if ct_id:
                try:
                    ct = CourseType.objects.get(pk=ct_id)
                    if not (data and data.get("course_fee")):
                        self.initial["course_fee"] = ct.default_course_fee
                    if not (data and data.get("instructor_fee")):
                        self.initial["instructor_fee"] = ct.default_instructor_fee
                except CourseType.DoesNotExist:
                    pass

            # Contacts from location (two behaviours):
            #   A) if user already selected a location in POST -> use that
            #   B) if there is EXACTLY ONE location for the business and user hasn’t picked yet,
            #      prefill contacts from that single location BUT keep the select blank.
            loc_id = data.get("training_location") if data else None
            try:
                loc = None
                if loc_id:
                    loc = TrainingLocation.objects.get(pk=loc_id)
                elif biz_id and qs.count() == 1:                                          # NEW
                    loc = qs.first()                                                      # NEW

                if loc:
                    if not (data and data.get("contact_name")):
                        self.initial["contact_name"] = loc.contact_name
                    if not (data and data.get("telephone")):
                        self.initial["telephone"] = loc.telephone
                    if not (data and data.get("email")):
                        self.initial["email"] = loc.email
            except TrainingLocation.DoesNotExist:
                pass

    # --- helpers for course reference ---
    @staticmethod
    def _rand_code(n=6):
        alphabet = string.ascii_uppercase + string.digits
        return "".join(secrets.choice(alphabet) for _ in range(n))

    def clean(self):
        cleaned = super().clean()

        # Ensure location belongs to selected business
        biz = cleaned.get("business")
        loc = cleaned.get("training_location")
        if biz and loc and loc.business_id != biz.id:
            self.add_error("training_location", "Selected location does not belong to the chosen business.")

        # Generate a unique course reference if empty
        if not cleaned.get("course_reference"):
            ct = cleaned.get("course_type")
            if ct:
                base = (ct.code or "COURSE").upper()
                for _ in range(50):
                    candidate = f"{base}-{self._rand_code(6)}"
                    qs = Booking.objects.filter(course_reference=candidate)
                    if self.instance and self.instance.pk:
                        qs = qs.exclude(pk=self.instance.pk)
                    if not qs.exists():
                        cleaned["course_reference"] = candidate
                        break
                else:
                    raise ValidationError("Could not generate a unique course reference; please try again.")

        return cleaned





# ---------------- Business ----------------
class BusinessForm(forms.ModelForm):
    add_as_training_location = forms.BooleanField(
        required=False,
        label="Also add/update a training location with this address"
    )

    class Meta:
        model = Business
        fields = [
            'name', 'address_line', 'town', 'postcode',
            'contact_name', 'telephone', 'email',
            'add_as_training_location',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class':'form-control'}),
            'address_line': forms.TextInput(attrs={'class':'form-control', 'id':'id_business_address'}),
            'town': forms.TextInput(attrs={'class':'form-control'}),
            'postcode': forms.TextInput(attrs={'class':'form-control'}),
            'contact_name': forms.TextInput(attrs={'class':'form-control'}),
            'telephone': forms.TextInput(attrs={'class':'form-control'}),
            'email': forms.EmailInput(attrs={'class':'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Pre-tick if an identical “default” location appears to exist
        if self.instance and self.instance.pk:
            exists = TrainingLocation.objects.filter(
                business=self.instance,
                name=self.instance.name
            ).exists()
            self.fields['add_as_training_location'].initial = exists

    def save(self, commit=True):
        biz = super().save(commit=commit)
        make = self.cleaned_data.get('add_as_training_location')

        if make:
            # create or update a location matching the business name
            loc, created = TrainingLocation.objects.get_or_create(
                business=biz,
                name=biz.name,
                defaults={
                    'address_line': biz.address_line,
                    'town': biz.town,
                    'postcode': biz.postcode,
                    'contact_name': biz.contact_name,
                    'telephone': biz.telephone,
                    'email': biz.email,
                }
            )
            if not created:
                loc.address_line = biz.address_line
                loc.town = biz.town
                loc.postcode = biz.postcode
                loc.contact_name = biz.contact_name
                loc.telephone = biz.telephone
                loc.email = biz.email
                loc.save()
        else:
            # remove the “default” location if it exists
            TrainingLocation.objects.filter(
                business=biz,
                name=biz.name
            ).delete()

        return biz


# ---------------- CourseType ----------------
class CourseTypeForm(forms.ModelForm):
    class Meta:
        model = CourseType
        fields = [
            "name",
            "code",
            "duration_days",
            "default_course_fee",
            "default_instructor_fee",
            "has_exam",  # <-- include this so the checkbox renders
        ]

class CourseCompetencyForm(forms.ModelForm):
    class Meta:
        model = CourseCompetency
        fields = ["name", "sort_order"]  # ONLY these two

        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Competency"}),
            "sort_order": forms.NumberInput(attrs={"class": "form-control", "style": "max-width:7rem"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["name"].label = "Competency"
        self.fields["sort_order"].label = "Order"


CourseCompetencyFormSet = inlineformset_factory(
    parent_model=CourseType,
    model=CourseCompetency,
    form=CourseCompetencyForm,
    extra=2,            # two blank rows for quick add
    can_delete=True,
)

# ---------------- Instructor (Admin view) ----------------
class InstructorForm(forms.ModelForm):
    """
    Admin form for instructors with a 'user' selector that:
      - lists only non-superusers not already assigned to another instructor
      - keeps the currently assigned user when editing
    """
    user = forms.ModelChoiceField(
        queryset=User.objects.none(),
        required=False,
        help_text="Optional login for this instructor. Only unassigned (non-superuser) users are listed.",
    )

    class Meta:
        model = Instructor
        fields = [
            "name",
            "address_line",
            "town",
            "postcode",
            "telephone",
            "email",
            "bank_sort_code",
            "bank_account_number",
            "name_on_account",
            "user",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "address_line": forms.TextInput(attrs={"class": "form-control", "id": "id_address_line"}),
            "town": forms.TextInput(attrs={"class": "form-control", "id": "id_town"}),
            "postcode": forms.TextInput(attrs={"class": "form-control", "id": "id_postcode"}),
            "telephone": forms.TextInput(attrs={"class": "form-control"}),
            "email": forms.EmailInput(attrs={"class": "form-control"}),
            "bank_sort_code": forms.TextInput(attrs={"class": "form-control"}),
            "bank_account_number": forms.TextInput(attrs={"class": "form-control"}),
            "name_on_account": forms.TextInput(attrs={"class": "form-control"}),
            "user": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        base_qs = User.objects.filter(is_superuser=False)

        if self.instance and self.instance.pk and self.instance.user_id:
            qs = base_qs.filter(Q(instructor__isnull=True) | Q(pk=self.instance.user_id))
        else:
            qs = base_qs.filter(instructor__isnull=True)

        self.fields["user"].queryset = qs.order_by("username")

    def clean_user(self):
        user = self.cleaned_data.get("user")
        if not user:
            return user
        if user.is_superuser:
            raise forms.ValidationError("You cannot assign a superuser account.")
        existing = Instructor.objects.filter(user=user)
        if self.instance and self.instance.pk:
            existing = existing.exclude(pk=self.instance.pk)
        if existing.exists():
            raise forms.ValidationError("That user is already assigned to another instructor.")
        return user


# ---------------- TrainingLocation ----------------
class TrainingLocationForm(forms.ModelForm):
    class Meta:
        model = TrainingLocation
        fields = [
            "name",
            "address_line",
            "town",
            "postcode",
            "contact_name",
            "telephone",
            "email",
        ]
        # (business is set in the view; it’s not an editable form field here)


# ---------------- Instructor (self-service) ----------------
class InstructorProfileForm(forms.ModelForm):
    """Used by instructors themselves; no 'user' linkage exposed here."""
    class Meta:
        model = Instructor
        fields = [
            "name",
            "address_line",
            "town",
            "postcode",
            "telephone",
            "email",
            "bank_sort_code",
            "bank_account_number",
            "name_on_account",
        ]


# ---------------- Admin Instructor (explicit) ----------------
class AdminInstructorForm(forms.ModelForm):
    user = forms.ModelChoiceField(
        queryset=User.objects.order_by("username"),
        required=False,
        help_text="Optional: link to an existing Django user account (for login).",
    )

    class Meta:
        model = Instructor
        fields = [
            "user",
            "name",
            "address_line",
            "town",
            "postcode",
            "telephone",
            "email",
            "bank_sort_code",
            "bank_account_number",
            "name_on_account",
        ]

class DelegateRegisterForm(forms.ModelForm):
    # Use the model’s choices and render as radios
    health_status = forms.ChoiceField(
        choices=DelegateRegister.HealthStatus.choices,
        widget=forms.RadioSelect,
        required=True,
    )

    class Meta:
        model = DelegateRegister
        fields = [
            "name",
            "date_of_birth",
            "job_title",
            "employee_id",
            "date",
            "instructor",
            "health_status",
        ]
        widgets = {
            "date_of_birth": forms.DateInput(attrs={"type": "date"}),
            "date":          forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # default to FIT if nothing set
        if not self.is_bound and not self.initial.get("health_status"):
            self.initial["health_status"] = DelegateRegister.HealthStatus.FIT
   
class DelegateRegisterAdminForm(forms.ModelForm):
    class Meta:
        model = DelegateRegister
        # No "date" field here (date comes from BookingDay)
        fields = ["name", "date_of_birth", "job_title", "employee_id", "instructor", "health_status"]
        widgets = {
            # Force ISO so <input type="date"> shows the saved value
            "date_of_birth": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        }


    def clean_name(self):
        # Title-case the name to tidy common variations
        name = (self.cleaned_data.get("name") or "").strip()
        return " ".join(part.capitalize() for part in name.split())

class DelegateRegisterInstructorForm(forms.ModelForm):
    # Keep radios – this guarantees the widget even if Meta changes
    health_status = forms.ChoiceField(
        choices=DelegateRegister.HealthStatus.choices,
        widget=forms.RadioSelect,
        required=True,
    )

    class Meta:
        model = DelegateRegister
        fields = ["name", "date_of_birth", "job_title", "employee_id", "instructor", "health_status", "notes"]  # + notes
        widgets = {
            # IMPORTANT: include format so HTML5 date shows the saved value
            "date_of_birth": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "instructor": forms.HiddenInput(),
            "notes": forms.Textarea(attrs={"rows": 1, "placeholder": "Optional notes…"}),  # tidy inline
        }

    def __init__(self, *args, **kwargs):
        current_instructor = kwargs.pop("current_instructor", None)
        super().__init__(*args, **kwargs)
        if current_instructor:
            self.fields["instructor"].queryset = Instructor.objects.filter(pk=current_instructor.pk)
            self.fields["instructor"].initial = current_instructor.pk

        # sensible default for new rows
        if not self.is_bound and not self.initial.get("health_status"):
            self.initial["health_status"] = DelegateRegister.HealthStatus.FIT

class BookingNotesForm(forms.ModelForm):
    class Meta:
        model = Booking
        fields = ["booking_notes"]
        widgets = {
            "booking_notes": forms.Textarea(
                attrs={"rows": 4, "placeholder": "Notes about this course (visible to instructors and admin)."}
            ),
        }
