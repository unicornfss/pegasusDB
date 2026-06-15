from datetime import time as dtime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from ..models import CourseSwap, CourseSwapStatus

from .booking_details import format_booking_course_day_lines, format_booking_dates_compact

COVER_ACCEPT_CALLBACK_PREFIX = "csa:"
COVER_DECLINE_CALLBACK_PREFIX = "csd:"
COVER_REQUEST_BOOKING_CALLBACK_PREFIX = "crb:"
COVER_REQUEST_INSTRUCTOR_CALLBACK_PREFIX = "cri:"
COVER_REQUEST_MESSAGE_CALLBACK_PREFIX = "crm:"
COVER_REQUEST_MESSAGE_SKIP_CALLBACK = f"{COVER_REQUEST_MESSAGE_CALLBACK_PREFIX}skip"
COVER_REQUEST_MESSAGE_ADD_CALLBACK = f"{COVER_REQUEST_MESSAGE_CALLBACK_PREFIX}add"


def personnel_wants_cover_telegram(personnel) -> bool:
    return bool(getattr(personnel, "notify_cover_requests_telegram", True))


def incoming_cover_requests_for_personnel(personnel):
    return list(
        CourseSwap.objects.filter(
            to_instructor=personnel,
            status=CourseSwapStatus.PENDING,
        )
        .select_related(
            "booking",
            "booking__course_type",
            "booking__business",
            "booking__training_location",
            "from_instructor",
        )
        .prefetch_related("booking__days")
        .order_by("booking__course_date", "created_at")
    )


def pending_cover_requests_sent_by_personnel(personnel):
    return list(
        CourseSwap.objects.filter(
            from_instructor=personnel,
            status=CourseSwapStatus.PENDING,
        )
        .select_related("booking", "booking__course_type", "to_instructor")
        .prefetch_related("booking__days")
        .order_by("booking__course_date", "created_at")
    )


def cover_swap_for_personnel_by_id(personnel, swap_id):
    if not swap_id:
        return None
    return (
        CourseSwap.objects.filter(pk=swap_id, to_instructor=personnel, status=CourseSwapStatus.PENDING)
        .select_related(
            "booking",
            "booking__course_type",
            "booking__business",
            "booking__training_location",
            "from_instructor",
            "to_instructor",
        )
        .prefetch_related("booking__days")
        .first()
    )


def _booking_line(booking):
    ref = booking.course_reference or "—"
    course = getattr(booking.course_type, "name", "") or "Course"
    date_str = format_booking_dates_compact(booking)
    return f"<b>{ref}</b> · {course} · {date_str}"


def _booking_detail_block(booking):
    """Course ref/name plus all day lines when the booking spans multiple days."""
    ref = booking.course_reference or "—"
    course = getattr(booking.course_type, "name", "") or "Course"
    day_lines = format_booking_course_day_lines(booking)

    if len(day_lines) > 1:
        lines = [f"<b>{ref}</b> · {course}"]
        lines.extend(f"   {line}" for line in day_lines)
        return "\n".join(lines)

    date_str = format_booking_dates_compact(booking)
    return f"<b>{ref}</b> · {course} · {date_str}"


def _booking_days_ordered(booking):
    cache = getattr(booking, "_prefetched_objects_cache", None)
    if cache and "days" in cache:
        return sorted(cache["days"], key=lambda d: (d.date, d.start_time or dtime.min))
    return list(booking.days.all().order_by("date", "start_time"))


def _keyboard_date_label(booking):
    days = _booking_days_ordered(booking)
    if len(days) >= 2:
        return f"{days[0].date.strftime('%d %b')}–{days[-1].date.strftime('%d %b %Y')}"
    if len(days) == 1:
        return days[0].date.strftime("%d %b %Y")
    if booking.course_date:
        return booking.course_date.strftime("%d %b %Y")
    return "—"


def format_cover_request_message(swap, *, intro=None):
    booking = swap.booking
    lines = []
    if intro:
        lines.append(intro)
        lines.append("")

    lines.extend([
        "<b>Course cover request</b>",
        "",
        f"From: <b>{swap.from_instructor.name}</b>",
        _booking_detail_block(booking),
    ])

    business = getattr(booking.business, "name", "") or ""
    loc = getattr(booking.training_location, "name", "") or ""
    if business:
        lines.append(f"Business: {business}")
    if loc:
        lines.append(f"Location: {loc}")

    if swap.message:
        lines.append("")
        lines.append(f"Message: {swap.message}")

    lines.append("")
    lines.append("Tap Accept or Decline below, or use Course swaps in Pegasus.")
    return "\n".join(lines)


def cover_request_keyboard(swap):
    swap_id = str(swap.pk)
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Accept cover", callback_data=f"{COVER_ACCEPT_CALLBACK_PREFIX}{swap_id}"),
            InlineKeyboardButton("Decline", callback_data=f"{COVER_DECLINE_CALLBACK_PREFIX}{swap_id}"),
        ],
    ])


def format_cover_requests_list(incoming, outgoing):
    lines = ["<b>Course cover requests</b>", ""]

    if incoming:
        lines.append(f"<b>Incoming ({len(incoming)})</b>")
        for i, swap in enumerate(incoming, start=1):
            lines.append(f"{i}. {_booking_line(swap.booking)}")
            day_lines = format_booking_course_day_lines(swap.booking)
            if len(day_lines) > 1:
                for day_line in day_lines:
                    lines.append(f"   {day_line}")
            lines.append(f"   From {swap.from_instructor.name}")
            if swap.message:
                lines.append(f"   “{swap.message}”")
            lines.append("")
        lines.append("👇 Use the buttons on each request, or reply with its number.")
    else:
        lines.append("No incoming cover requests.")

    lines.append("")
    if outgoing:
        lines.append(f"<b>Your pending requests ({len(outgoing)})</b>")
        for swap in outgoing:
            lines.append(f"• {_booking_line(swap.booking)} → {swap.to_instructor.name}")
    else:
        lines.append("You have no pending cover requests waiting for a response.")

    lines.append("")
    lines.append("Use /requestcover to ask another instructor to cover your course.")
    return "\n".join(lines).strip()


def format_swappable_bookings_for_request(bookings):
    if not bookings:
        return "You have no scheduled or in-progress courses available for a cover request."

    lines = [
        "<b>Request course cover</b>",
        "",
        "Which course do you need cover for?",
        "",
    ]
    for i, booking in enumerate(bookings, start=1):
        lines.append(f"{i}. {_booking_line(booking)}")
        day_lines = format_booking_course_day_lines(booking)
        if len(day_lines) > 1:
            for day_line in day_lines:
                lines.append(f"   {day_line}")
        business = getattr(booking.business, "name", "") or ""
        if business:
            lines.append(f"   {business}")
        lines.append("")
    lines.append("Reply with the course number, or tap a button below.")
    lines.append("Send /cancel to stop.")
    return "\n".join(lines).strip()


def swappable_bookings_request_keyboard(bookings):
    rows = []
    for booking in bookings:
        date_str = _keyboard_date_label(booking)
        ref = booking.course_reference or "Course"
        label = f"{date_str} · {ref}"
        if len(label) > 64:
            label = label[:61] + "..."
        rows.append([
            InlineKeyboardButton(
                label,
                callback_data=f"{COVER_REQUEST_BOOKING_CALLBACK_PREFIX}{booking.pk}",
            )
        ])
    return InlineKeyboardMarkup(rows)


def format_instructors_for_cover_request(booking, instructors):
    lines = [
        "<b>Request course cover</b>",
        "",
        f"Course: {_booking_detail_block(booking)}",
        "",
        "Who should cover this course?",
        "",
    ]
    for i, person in enumerate(instructors, start=1):
        lines.append(f"{i}. {person.name}")
    lines.append("")
    lines.append("Reply with the instructor number, or tap a button below.")
    lines.append("Send /cancel to stop.")
    return "\n".join(lines).strip()


def instructors_for_cover_request_keyboard(instructors):
    rows = []
    for person in instructors:
        label = person.name or "Instructor"
        if len(label) > 64:
            label = label[:61] + "..."
        rows.append([
            InlineKeyboardButton(
                label,
                callback_data=f"{COVER_REQUEST_INSTRUCTOR_CALLBACK_PREFIX}{person.pk}",
            )
        ])
    return InlineKeyboardMarkup(rows)


def cover_request_message_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "Send without message",
                callback_data=COVER_REQUEST_MESSAGE_SKIP_CALLBACK,
            ),
            InlineKeyboardButton(
                "Add a message",
                callback_data=COVER_REQUEST_MESSAGE_ADD_CALLBACK,
            ),
        ],
    ])


def format_cover_request_message_prompt(booking, instructor):
    return (
        f"<b>Request course cover</b>\n\n"
        f"Course: {_booking_detail_block(booking)}\n"
        f"Instructor: <b>{instructor.name}</b>\n\n"
        "Tap a button below, or type an optional message (max 500 characters).\n"
        "Send /cancel to stop."
    )


def format_cover_request_sent_confirmation(swap):
    return (
        f"<b>Cover request sent</b>\n\n"
        f"Your request for {_booking_line(swap.booking)} was sent to <b>{swap.to_instructor.name}</b>.\n"
        "They must accept before the course transfers.\n\n"
        "Use /covers to see pending requests."
    )


def format_cover_outcome_message(swap, *, accepted):
    booking = swap.booking
    if accepted:
        headline = "<b>Cover request accepted</b>"
        detail = f"You accepted the cover for {_booking_line(booking)}."
        detail += "\nThe course is now assigned to you in Pegasus."
    else:
        headline = "<b>Cover request declined</b>"
        detail = f"You declined the cover for {_booking_line(booking)}."

    return f"{headline}\n\n{detail}"


def format_cover_outcome_for_offerer(swap, *, accepted):
    booking = swap.booking
    if accepted:
        return (
            f"<b>Cover request accepted</b>\n\n"
            f"{swap.to_instructor.name} accepted your cover request for:\n"
            f"{_booking_line(booking)}"
        )
    return (
        f"<b>Cover request declined</b>\n\n"
        f"{swap.to_instructor.name} declined your cover request for:\n"
        f"{_booking_line(booking)}"
    )


def send_cover_request_telegram(swap):
    from .telegram_client import send_telegram_message

    recipient = swap.to_instructor
    chat_id = (recipient.telegram_chat_id or "").strip()
    if not chat_id or not personnel_wants_cover_telegram(recipient):
        return False

    text = format_cover_request_message(swap)
    keyboard = cover_request_keyboard(swap)
    message, _error = send_telegram_message(chat_id, text, reply_markup=keyboard)
    return message is not None


def send_cover_outcome_telegram_to_offerer(swap, *, accepted):
    from .telegram_client import send_telegram_message

    offerer = swap.from_instructor
    chat_id = (offerer.telegram_chat_id or "").strip()
    if not chat_id or not personnel_wants_cover_telegram(offerer):
        return False

    text = format_cover_outcome_for_offerer(swap, accepted=accepted)
    message, _error = send_telegram_message(chat_id, text)
    return message is not None
