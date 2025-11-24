from django import forms
from django.contrib.auth.models import User, Group
from django.core.exceptions import ValidationError
from django.core.validators import EmailValidator
from django.db.models import Q
from django.forms import inlineformset_factory, BaseInlineFormSet
from django.utils import timezone
from . import models as m

from .models import (
    AccidentReport,
    Business,
    CourseType,
    Personnel,
    TrainingLocation,
    Booking,
    BookingDay,
    Attendance,
    DelegateRegister,
    CourseCompetency,
    FeedbackResponse,
    Exam,
    ExamQuestion,
    ExamAnswer,
    MetaSetting
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
            "precise_lat",
            "precise_lng",
            "course_type",
            "instructor",
            "course_date",
            "start_time",
            "course_fee",
            "instructor_fee",
            "allow_mileage_claim",
            "mileage_fee",
            "contact_name",
            "telephone",
            "email",
            "course_reference",
            "booking_notes",
        ]
        # BookingForm.Meta.widgets
        widgets = {
            "course_date": forms.DateInput(attrs={"type": "date"}),
            "start_time": forms.TimeInput(attrs={"type": "time"}),
            "course_reference": forms.TextInput(attrs={"readonly": "readonly"}),
            "booking_notes": forms.Textarea(attrs={"rows": 4, "class": "form-control"}),
            'precise_lat': forms.HiddenInput(),
            'precise_lng': forms.HiddenInput(), 
            "allow_mileage_claim": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "mileage_fee": forms.HiddenInput(),
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
            "name", "code", "duration_days",
            "certificate_duration",
            "default_course_fee", "default_instructor_fee",
            "has_exam", "number_of_exams",
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
class PersonnelAdminForm(forms.ModelForm):
    """
    Admin form for Personnel with a 'user' selector that:
      - lists non-superusers
      - lists only users not already assigned to another Personnel
      - keeps the current linked user when editing
    """

    user = forms.ModelChoiceField(
        queryset=User.objects.none(),
        required=False,
        help_text="Optional login for this person. Only unassigned (non-superuser) users are listed.",
        widget=forms.Select(attrs={"class": "form-select"})
    )

    class Meta:
        model = Personnel
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
            "address_line": forms.TextInput(attrs={"class": "form-control"}),
            "town": forms.TextInput(attrs={"class": "form-control"}),
            "postcode": forms.TextInput(attrs={"class": "form-control"}),
            "telephone": forms.TextInput(attrs={"class": "form-control"}),
            "email": forms.EmailInput(attrs={"class": "form-control"}),
            "bank_sort_code": forms.TextInput(attrs={"class": "form-control"}),
            "bank_account_number": forms.TextInput(attrs={"class": "form-control"}),
            "name_on_account": forms.TextInput(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        base_qs = User.objects.filter(is_superuser=False)

        if self.instance and self.instance.pk and self.instance.user_id:
            qs = base_qs.filter(
                Q(personnel__isnull=True) | Q(pk=self.instance.user_id)
            )
        else:
            qs = base_qs.filter(personnel__isnull=True)

        self.fields["user"].queryset = qs.order_by("email", "username")

    def clean_user(self):
        user = self.cleaned_data.get("user")
        if not user:
            return user

        if user.is_superuser:
            raise forms.ValidationError("You cannot assign a superuser account.")

        existing = Personnel.objects.filter(user=user)
        if self.instance and self.instance.pk:
            existing = existing.exclude(pk=self.instance.pk)

        if existing.exists():
            raise forms.ValidationError("That user is already linked to another Personnel record.")

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
class PersonnelProfileForm(forms.ModelForm):
    """
    Form used in your custom front-end for instructors to edit their own profile.
    Does NOT allow changing the linked User account.
    """
    class Meta:
        model = Personnel
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
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "address_line": forms.TextInput(attrs={"class": "form-control"}),
            "town": forms.TextInput(attrs={"class": "form-control"}),
            "postcode": forms.TextInput(attrs={"class": "form-control"}),
            "telephone": forms.TextInput(attrs={"class": "form-control"}),
            "email": forms.EmailInput(attrs={"class": "form-control"}),
            "bank_sort_code": forms.TextInput(attrs={"class": "form-control"}),
            "bank_account_number": forms.TextInput(attrs={"class": "form-control"}),
            "name_on_account": forms.TextInput(attrs={"class": "form-control"}),
        }



# ---------------- Admin Instructor (explicit) ----------------
class AdminInstructorForm(forms.ModelForm):
    user = forms.ModelChoiceField(
        queryset=User.objects.order_by("username"),
        required=False,
        help_text="Optional: link to an existing Django user account (for login).",
    )

    class Meta:
        model = Personnel
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

from django import forms
from django.utils import timezone

class DelegateRegisterForm(forms.ModelForm):
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
        # Force HTML5 date format so initial shows up
        widgets = {
            "date_of_birth": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "date":          forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # default health status
        if not self.is_bound and not self.initial.get("health_status"):
            self.initial["health_status"] = DelegateRegister.HealthStatus.FIT

        # default date to today if not provided by the view
        if not self.is_bound and not self.initial.get("date"):
            self.initial["date"] = timezone.localdate()

        # Make sure parsing accepts the browser's YYYY-MM-DD
        self.fields["date"].input_formats = ["%Y-%m-%d"]
        self.fields["date_of_birth"].input_formats = ["%Y-%m-%d"]

        # (nice-to-have) avoid autofill weirdness
        self.fields["date"].widget.attrs.setdefault("autocomplete", "off")
        self.fields["date_of_birth"].widget.attrs.setdefault("autocomplete", "off")

   
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
            self.fields["instructor"].queryset = Personnel.objects.filter(pk=current_instructor.pk)
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
                attrs={"rows": 4, "placeholder": "Notes about this course (visible to instructor and admin)."}
            ),
        }

from django import forms
from .models import FeedbackResponse, Personnel as Instructor, CourseType

RATING_CHOICES = [(i, str(i)) for i in range(1, 6)]

class SmileyRadioSelect(forms.RadioSelect):
    template_name = "widgets/smiley_radio.html"

EMOJI_1_TO_5 = (
    (1, "😟 1"),
    (2, "🙁 2"),
    (3, "😐 3"),
    (4, "🙂 4"),
    (5, "😀 5"),
)

# forms.py
from django import forms
from .models import FeedbackResponse, CourseType, Personnel as Instructor

RATING_CHOICES = (
    (1, "1"),
    (2, "2"),
    (3, "3"),
    (4, "4"),
    (5, "5"),
)

class FeedbackForm(forms.ModelForm):
    class Meta:
        model = FeedbackResponse
        fields = [
            "course_type", "date", "instructor",
            "prior_knowledge", "post_knowledge",
            "q_purpose_clear", "q_personal_needs", "q_exercises_useful",
            "q_structure", "q_pace", "q_content_clear", "q_instructor_knowledge",
            "q_materials_quality", "q_books_quality",
            "q_venue_suitable",
            "q_benefit_at_work", "q_benefit_outside",  # <-- ensure included
            "overall_rating",
            "comments", "wants_callback",
            "contact_name", "contact_email", "contact_phone",
        ]
        widgets = {
            # 1–5 radio widgets for all rating questions, including the two “Summary” ones:
            "prior_knowledge":        forms.RadioSelect(choices=RATING_CHOICES),
            "post_knowledge":         forms.RadioSelect(choices=RATING_CHOICES),
            "q_purpose_clear":        forms.RadioSelect(choices=RATING_CHOICES),
            "q_personal_needs":       forms.RadioSelect(choices=RATING_CHOICES),
            "q_exercises_useful":     forms.RadioSelect(choices=RATING_CHOICES),
            "q_structure":            forms.RadioSelect(choices=RATING_CHOICES),
            "q_pace":                 forms.RadioSelect(choices=RATING_CHOICES),
            "q_content_clear":        forms.RadioSelect(choices=RATING_CHOICES),
            "q_instructor_knowledge": forms.RadioSelect(choices=RATING_CHOICES),
            "q_materials_quality":    forms.RadioSelect(choices=RATING_CHOICES),
            "q_books_quality":        forms.RadioSelect(choices=RATING_CHOICES),
            "q_venue_suitable":       forms.RadioSelect(choices=RATING_CHOICES),
            "q_benefit_at_work":      forms.RadioSelect(choices=RATING_CHOICES),   # <-- FIX
            "q_benefit_outside":      forms.RadioSelect(choices=RATING_CHOICES),   # <-- FIX
            "overall_rating":         forms.RadioSelect(choices=RATING_CHOICES),

            # the rest are normal inputs/textarea/checkbox:
            "comments":       forms.Textarea(attrs={"rows": 4}),
            "wants_callback": forms.CheckboxInput(),
            "date":           forms.DateInput(attrs={"type": "date"}),
        }

class ExamForm(forms.ModelForm):
    class Meta:
        model = Exam
        fields = ["sequence", "title"]

# ...imports above...

class BaseAnswerFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        alive = 0
        correct = 0
        for f in self.forms:
            if not getattr(f, "cleaned_data", None) or f.cleaned_data.get("DELETE"):
                continue
            if f.cleaned_data.get("text"):
                alive += 1
                if f.cleaned_data.get("is_correct"):
                    correct += 1
        if alive:
            if alive < 2:
                raise forms.ValidationError("Each question must have at least two answers.")
            if correct != 1:
                raise forms.ValidationError("Exactly one answer must be marked correct.")

AnswerFormSet = inlineformset_factory(
    parent_model=ExamQuestion,
    model=ExamAnswer,
    fields=["order", "text", "is_correct"],
    extra=0,           # <<< important: JS adds the rows
    can_delete=True,
    formset=BaseAnswerFormSet,
)


QuestionFormSet = inlineformset_factory(
    parent_model=Exam,
    model=ExamQuestion,
    fields=["order", "text"],
    extra=0,              # add via “Add question” button (empty_form)
    can_delete=True,
)

class AccidentReportForm(forms.ModelForm):
    class Meta:
        model = AccidentReport
        fields = [
            "date", "time", "location",
            "injured_name", "injured_address",
            "what_happened", "injuries_sustained",
            "actions_carried_out", "actions_prevent_recurrence",
            "first_aider_name", "reporter_name",
        ]
        widgets = {
            "date":  forms.DateInput(attrs={"type": "date", "class": "form-control", "id": "ar-date"}),
            "time":  forms.TimeInput(attrs={"type": "time", "class": "form-control", "id": "ar-time"}),
            "location": forms.TextInput(attrs={"class": "form-control"}),
            "injured_name": forms.TextInput(attrs={"class": "form-control"}),

            # TextInput so Places can attach
            "injured_address": forms.TextInput(attrs={
                "class": "form-control", "id": "ar-injured-address", "autocomplete": "off"
            }),

            "what_happened": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "injuries_sustained": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "actions_carried_out": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "actions_prevent_recurrence": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "first_aider_name": forms.TextInput(attrs={"class": "form-control", "id": "ar-first-aider"}),
            "reporter_name":    forms.TextInput(attrs={"class": "form-control", "id": "ar-reporter"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # belt-and-braces: ensure IDs exist even if a widget gets swapped
        self.fields["date"].widget.attrs.setdefault("id", "ar-date")
        self.fields["time"].widget.attrs.setdefault("id", "ar-time")
        self.fields["injured_address"].widget.attrs.setdefault("id", "ar-injured-address")
        self.fields["first_aider_name"].widget.attrs.setdefault("id", "ar-first-aider")
        self.fields["reporter_name"].widget.attrs.setdefault("id", "ar-reporter")

class PersonnelForm(forms.ModelForm):

    groups = forms.ModelMultipleChoiceField(
        queryset=Group.objects.all().order_by("name"),
        required=False,
        widget=forms.CheckboxSelectMultiple(
            attrs={"class": "form-check-input"}
        ),
    )

    class Meta:
        model = Personnel
        fields = [
            "name",
            "email",
            "telephone",
            "address_line",
            "town",
            "postcode",
            "bank_sort_code",
            "bank_account_number",
            "name_on_account",
            "can_login",
            "is_active",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "email": forms.EmailInput(attrs={"class": "form-control"}),
            "telephone": forms.TextInput(attrs={"class": "form-control"}),
            "address_line": forms.TextInput(attrs={"class": "form-control"}),
            "town": forms.TextInput(attrs={"class": "form-control"}),
            "postcode": forms.TextInput(attrs={"class": "form-control"}),
            "bank_sort_code": forms.TextInput(attrs={"class": "form-control"}),
            "bank_account_number": forms.TextInput(attrs={"class": "form-control"}),
            "name_on_account": forms.TextInput(attrs={"class": "form-control"}),
            "can_login": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    # --------------------------
    # PRE-POPULATE GROUPS
    # --------------------------
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.instance and self.instance.user:
            # Load user's groups into the form
            self.fields["groups"].initial = self.instance.user.groups.all()

        # Disable the "can_login" checkbox if inactive
        if self.instance and not self.instance.is_active:
            self.fields["can_login"].widget.attrs["disabled"] = True

    # --------------------------
    # SAVE LOGIC
    # --------------------------
    def save(self, commit=True):
        inst = super().save(commit=False)

        # If inactive → force disable login
        if not inst.is_active:
            inst.can_login = False

        if commit:
            inst.save()

        # APPLY GROUPS + LOGIN SETTINGS TO USER
        if inst.user:

            # Apply groups
            groups = self.cleaned_data.get("groups", [])
            inst.user.groups.set(groups)

            # Activate/deactivate user login
            inst.user.is_active = inst.can_login and inst.is_active
            inst.user.save()

        return inst
    

class MetaSettingForm(forms.ModelForm):
    class Meta:
        model = MetaSetting
        fields = ["key", "value"]