# unicorn_project/training/views_certificates.py

from django.shortcuts import get_object_or_404
from django.http import HttpResponse

from .models import Booking
from .utils.certificates import build_certificates_pdf_for_booking


def booking_certificates_preview(request, booking_id):
    booking = get_object_or_404(Booking, id=booking_id)
    result = build_certificates_pdf_for_booking(booking)
    if not result:
        return HttpResponse("No delegates for this booking.", content_type="text/plain")

    filename, pdf_bytes = result
    resp = HttpResponse(pdf_bytes, content_type="application/pdf")
    resp["Content-Disposition"] = f'inline; filename="{filename}"'
    return resp
