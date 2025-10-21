from django.shortcuts import render, get_object_or_404
from django.utils import timezone
from django.db.models import Q
from .models import Exam, DelegateRegister
from .forms_exam import DelegateExamStartForm
from django.views.decorators.csrf import ensure_csrf_cookie, csrf_protect
from math import ceil



@ensure_csrf_cookie   # set csrftoken on GET
@csrf_protect         # validate on POST
def delegate_exam_start(request):
    # GET/POST both supported (POST keeps the query param via hidden field)
    code = (request.GET.get("examcode") or request.POST.get("examcode") or "").upper()
    if not code:
        return render(request, "exam/delegate_start_missing_code.html", status=400)

    exam = get_object_or_404(Exam, exam_code=code)
    course_type = exam.course_type

    message = None
    match_ok = None

    if request.method == "POST":
        form = DelegateExamStartForm(request.POST, initial={"exam_code": exam.exam_code})
        if form.is_valid():
            # Normalise inputs
            raw_name = form.cleaned_data["name"]
            name = " ".join(raw_name.split()).strip()  # collapse extra spaces
            dob = form.cleaned_data["date_of_birth"]
            ex_date = form.cleaned_data["exam_date"]
            instructor = form.cleaned_data["instructor"]  # kept for later flow

            # Match:
            # 1) by name + dob
            # 2) AND either:
            #    a) linked booking_day with matching course type + date, OR
            #    b) no booking_day but a direct date field matching exam date (legacy rows)
            qs = (
                DelegateRegister.objects.filter(
                    name__iexact=name,
                    date_of_birth=dob,
                )
                .filter(
                    Q(
                        booking_day__booking__course_type=course_type,
                        booking_day__date=ex_date,
                    )
                    | Q(booking_day__isnull=True, date=ex_date)
                )
            )

            if qs.exists():
                match_ok = True
                message = (
                    f"We found you on the register for {course_type.name} "
                    f"on {ex_date:%d %b %Y}."
                )
            else:
                # Near-match helper list to aid the delegate
                near = (
                    DelegateRegister.objects.filter(date_of_birth=dob)
                    .filter(
                        Q(
                            booking_day__booking__course_type=course_type,
                            booking_day__date=ex_date,
                        )
                        | Q(booking_day__isnull=True, date=ex_date)
                    )
                    .values_list("name", flat=True)
                )
                match_ok = False
                if near:
                    unique_names = ", ".join(sorted(set(near)))
                    message = (
                        "We couldn’t find an exact match for your name. "
                        f"Names on the register for this course/date: {unique_names}. "
                        "Please check the spelling or speak to your instructor."
                    )
                else:
                    message = (
                        "We couldn’t find a matching register entry. "
                        "Please double-check your name and date of birth, or ask your instructor."
                    )
    else:
        form = DelegateExamStartForm(
            initial={
                "exam_code": exam.exam_code,
                "exam_date": timezone.localdate(),
            }
        )

    ctx = {
        "exam": exam,
        "course_type": course_type,
        "form": form,
        "message": message,
        "match_ok": match_ok,
    }
    return render(request, "exam/delegate_start.html", ctx)

from math import ceil
# ...

def delegate_exam_rules(request):
    code = (request.GET.get("examcode") or "").upper()
    exam = get_object_or_404(Exam, exam_code=code)
    course_type = exam.course_type

    num_questions = exam.questions.count()

    # pass mark %
    pct = exam.pass_mark_percent or 80

    # whole number required correct
    required_correct = ceil(num_questions * pct / 100.0)

    # total time: 90 seconds per question
    total_seconds = num_questions * 90
    minutes, seconds = divmod(total_seconds, 60)

    # NEW: viva threshold, if enabled
    viva_pct = exam.viva_pass_percent if getattr(exam, "allow_viva", False) else None
    viva_required = ceil(num_questions * viva_pct / 100.0) if viva_pct else None

    ctx = {
        "exam": exam,
        "course_type": course_type,
        "num_questions": num_questions,
        "pass_mark_percent": pct,
        "required_correct": required_correct,
        "total_seconds": total_seconds,
        "minutes": minutes,
        "seconds": seconds,
        # NEW
        "viva_percent": viva_pct,
        "viva_required": viva_required,
    }
    return render(request, "exam/rules.html", ctx)

    code = (request.GET.get("examcode") or "").upper()
    exam = get_object_or_404(Exam, exam_code=code)
    course_type = exam.course_type

    # number of questions (you already use ex.questions.count in templates)
    num_questions = exam.questions.count()

    # pass mark %
    pct = exam.pass_mark_percent or 70

    # whole number required correct
    required_correct = ceil(num_questions * pct / 100.0)

    # total time: 90 seconds per question
    total_seconds = num_questions * 90
    minutes, seconds = divmod(total_seconds, 60)

    ctx = {
        "exam": exam,
        "course_type": course_type,
        "num_questions": num_questions,
        "pass_mark_percent": pct,
        "required_correct": required_correct,
        "total_seconds": total_seconds,
        "minutes": minutes,
        "seconds": seconds,
    }
    return render(request, "exam/rules.html", ctx)