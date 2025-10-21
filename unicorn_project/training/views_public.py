from datetime import timedelta
from django.db import transaction
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.db.models import Q
from .models import Exam, DelegateRegister, ExamAnswer, ExamAttempt, ExamAttemptAnswer, ExamQuestion
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

def _get_or_create_attempt(request, exam: Exam):
    """
    Create an attempt on first entry to /exam/run/, using details captured on the start page.
    We pass those details via query for now; you can later persist them in session if preferred.
    """
    # Try to resume an unfinished attempt for this exam + same delegate (basic resume)
    dn = (request.GET.get("name") or request.POST.get("name") or "").strip()
    dob = (request.GET.get("dob") or request.POST.get("dob") or "").strip()
    instr_id = request.GET.get("instructor") or request.POST.get("instructor")
    ex_date = request.GET.get("date") or request.POST.get("date")

    # If an attempt id is supplied, prefer that
    att_id = request.GET.get("attempt") or request.POST.get("attempt")
    if att_id:
        att = get_object_or_404(ExamAttempt, pk=att_id, exam=exam)
        return att

    # Otherwise create new
    total_qs = exam.questions.count()
    total_seconds = total_qs * 90
    expires_at = timezone.now() + timedelta(seconds=total_seconds)

    att = ExamAttempt.objects.create(
        exam=exam,
        delegate_name=dn or "Delegate",
        date_of_birth=dob or "1900-01-01",  # string accepted; DB layer will coerce via ISO format
        instructor_id=int(instr_id) if instr_id else None,
        exam_date=ex_date or timezone.localdate(),
        started_at=timezone.now(),
        expires_at=expires_at,
        total_questions=total_qs,
    )
    return att

@ensure_csrf_cookie
@csrf_protect
def delegate_exam_run(request):
    """
    One question per page; single total timer (90s per question).
    URL: /exam/run/?examcode=FAAW01[&q=1][&name=...&dob=YYYY-MM-DD&instructor=<id>&date=YYYY-MM-DD]
    """
    code = (request.GET.get("examcode") or request.POST.get("examcode") or "").upper()
    if not code:
        return redirect(f'{reverse("delegate_exam_start")}')

    exam = get_object_or_404(Exam, exam_code=code)
    questions = list(exam.questions.order_by("order", "id"))
    if not questions:
        # No questions configured
        return render(request, "exam/run_empty.html", {"exam": exam, "course_type": exam.course_type})

    # Create or resume the attempt
    attempt = _get_or_create_attempt(request, exam)

    # Hard-stop if expired or finished
    if attempt.remaining_seconds() <= 0:
        return redirect(f'{reverse("delegate_exam_finish")}?examcode={exam.exam_code}&attempt={attempt.pk}')

    # Which question index?
    q_index = int(request.GET.get("q") or request.POST.get("q") or 1)
    q_index = max(1, min(q_index, len(questions)))
    question = questions[q_index - 1]
    answers = list(question.answers.order_by("order", "id"))

    # Persist answer on POST
    # Persist answer on POST
    if request.method == "POST":
        selected_id = request.POST.get("answer")
        with transaction.atomic():
            aa, _ = ExamAttemptAnswer.objects.get_or_create(attempt=attempt, question=question)
            if selected_id:
                try:
                    ans = ExamAnswer.objects.get(pk=int(selected_id), question=question)
                except (ValueError, ExamAnswer.DoesNotExist):
                    ans = None
                aa.answer = ans
                aa.is_correct = bool(ans and ans.is_correct)
            else:
                aa.answer = None
                aa.is_correct = False
            aa.save()

        # Next / Prev / Finish
        if "prev" in request.POST and q_index > 1:
            return redirect(f'{reverse("delegate_exam_run")}?examcode={exam.exam_code}&attempt={attempt.pk}&q={q_index-1}')
        if "next" in request.POST and q_index < len(questions):
            return redirect(f'{reverse("delegate_exam_run")}?examcode={exam.exam_code}&attempt={attempt.pk}&q={q_index+1}')
        if "finish" in request.POST:
            # send to the review page (not final results)
            return redirect(f'{reverse("delegate_exam_review")}?examcode={exam.exam_code}&attempt={attempt.pk}')


    # Preselect previous answer if any
    try:
        prev = ExamAttemptAnswer.objects.get(attempt=attempt, question=question)
        selected_pk = prev.answer_id
    except ExamAttemptAnswer.DoesNotExist:
        selected_pk = None

    ctx = {
        "exam": exam,
        "course_type": exam.course_type,
        "attempt": attempt,
        "question": question,
        "answers": answers,
        "q_index": q_index,
        "q_total": len(questions),
        "remaining": attempt.remaining_seconds(),
        "selected_pk": selected_pk,
    }
    return render(request, "exam/run.html", ctx)

# training/views_public.py
from django.db.models import Prefetch
from django.urls import reverse

def delegate_exam_review(request):
    code = (request.GET.get("examcode") or "").upper()
    exam = get_object_or_404(Exam, exam_code=code)
    att_id = request.GET.get("attempt")
    attempt = get_object_or_404(ExamAttempt, pk=att_id, exam=exam)

    # If time is up, jump directly to results
    if attempt.remaining_seconds() <= 0:
        return redirect(f'{reverse("delegate_exam_finish")}?examcode={exam.exam_code}&attempt={attempt.pk}')

    # Pull all questions with answers, and any selected answers for this attempt
    questions = list(
        exam.questions.order_by("order", "id").prefetch_related("answers")
    )
    chosen = {
        aa.question_id: aa for aa in attempt.answers.select_related("answer", "question")
    }

    # Submit from the review page goes to final scoring
    if request.method == "POST":
        return redirect(f'{reverse("delegate_exam_finish")}?examcode={exam.exam_code}&attempt={attempt.pk}')

    ctx = {
        "exam": exam,
        "course_type": exam.course_type,
        "attempt": attempt,
        "questions": questions,
        "chosen": chosen,
        "remaining": attempt.remaining_seconds(),
    }
    return render(request, "exam/review.html", ctx)


def _score_attempt(attempt: ExamAttempt):
    # Score and apply pass/viva
    # Count correct answers
    correct = attempt.answers.filter(is_correct=True).count()
    attempt.score_correct = correct
    attempt.total_questions = attempt.exam.questions.count()

    pct = attempt.exam.pass_mark_percent or 80
    required = ceil(attempt.total_questions * pct / 100.0)

    viva_pct = attempt.exam.viva_pass_percent if getattr(attempt.exam, "allow_viva", False) else None
    viva_required = ceil(attempt.total_questions * viva_pct / 100.0) if viva_pct else None

    attempt.passed = (correct >= required)
    attempt.viva_eligible = (not attempt.passed) and (viva_required is not None) and (correct >= viva_required)

    if not attempt.finished_at:
        attempt.finished_at = timezone.now()

    attempt.save()
    return required, viva_required

def delegate_exam_finish(request):
    code = (request.GET.get("examcode") or "").upper()
    exam = get_object_or_404(Exam, exam_code=code)
    att_id = request.GET.get("attempt")
    attempt = get_object_or_404(ExamAttempt, pk=att_id, exam=exam)

    # If time’s up, ensure it’s marked finished and scored
    required, viva_required = _score_attempt(attempt)

    ctx = {
        "exam": exam,
        "course_type": exam.course_type,
        "attempt": attempt,
        "required_correct": required,
        "viva_required": viva_required,
    }
    return render(request, "exam/finish.html", ctx)