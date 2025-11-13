from functools import wraps
from django.http import JsonResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages

def _is_ajax(request):
    return request.headers.get("x-requested-with") == "XMLHttpRequest"

def guard_unlocked(allow_when_locked=False):
    """
    Block POST/PUT/PATCH/DELETE when booking.is_locked, unless explicitly allowed.
    Attach `request.booking` for convenience.
    """
    def decorator(view):
        @wraps(view)
        def _wrapped(request, *args, **kwargs):
            from ..models import Booking  # local import to avoid cycles

            pk = (
                kwargs.get("pk")
                or kwargs.get("booking_id")
                or request.POST.get("booking_id")
                or request.GET.get("booking_id")
            )
            booking = get_object_or_404(Booking, pk=pk)
            request.booking = booking

            if booking.is_locked and not allow_when_locked and request.method not in ("GET", "HEAD", "OPTIONS"):
                if _is_ajax(request):
                    return JsonResponse({"error": "Course is closed/read-only."}, status=403)
                messages.error(request, "This course is closed and is read-only.")
                # send them back to the booking page
                return redirect("instructor_booking_detail", pk=booking.pk)

            return view(request, *args, **kwargs)
        return _wrapped
    return decorator
