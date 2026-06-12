import io

import qrcode
from django.urls import reverse
from urllib.parse import urlencode


def course_register_short_path(course_code: str) -> str:
    return reverse("public_register_short", kwargs={"code": course_code})


def course_register_short_url(request, course_code: str) -> str:
    return request.build_absolute_uri(course_register_short_path(course_code))


def course_register_full_url(request, course_code: str) -> str:
    query = urlencode({"ct": course_code})
    return request.build_absolute_uri(f"{reverse('public_delegate_register')}?{query}")


def qr_png_bytes(data: str, *, box_size: int = 8, border: int = 2) -> bytes:
    qr = qrcode.QRCode(box_size=box_size, border=border)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
