# training/forms_exam.py
from django import forms
from django.utils import timezone
from .models import Instructor

class DelegateExamStartForm(forms.Form):
    exam_code = forms.CharField(label="Exam code", disabled=True)
    name = forms.CharField(label="Your full name", max_length=100)
    date_of_birth = forms.DateField(label="Date of birth",
                                    widget=forms.DateInput(attrs={"type": "date"}))
    instructor = forms.ModelChoiceField(label="Instructor",
                                        queryset=Instructor.objects.order_by("name"))
    exam_date = forms.DateField(label="Exam date",
                                initial=timezone.localdate,
                                widget=forms.DateInput(attrs={"type": "date"}))

    def clean_name(self):
        n = self.cleaned_data["name"].strip()
        return " ".join(w.capitalize() for w in n.split())
