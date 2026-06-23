import json
import queue

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .models import StaffInboxItem, StaffInboxItemKind, StaffInboxItemStatus
from .services.course_swaps import CourseSwapError, accept_swap, decline_swap
from .services.instructor_course_requests import (
    CourseDeliveryRequestError,
    approve_course_delivery_request,
    decline_course_delivery_request,
)
from .services.staff_inbox import (
    inbox_items_for_personnel,
    mark_inbox_items_read,
    unread_inbox_count,
    user_can_act_on_inbox_item,
)
from .utils.user_roles import available_roles_for_user, set_active_role, user_has_role

INBOX_URL_NAMES = frozenset({"inbox_list", "admin_inbox_list"})


def _get_personnel(request):
    try:
        return request.user.personnel
    except Exception:
        return None


def _inbox_url_name(request) -> str:
    """URL name for the inbox list the user is viewing."""
    name = getattr(getattr(request, "resolver_match", None), "url_name", None)
    if name == "admin_inbox_list":
        return "admin_inbox_list"
    return "inbox_list"


def _inbox_return_url_name(request) -> str:
    """Where to send the user after an inbox action."""
    return_to = (request.POST.get("return_to") or request.GET.get("return_to") or "").strip()
    if return_to in INBOX_URL_NAMES:
        return return_to
    return "inbox_list"


def _inbox_scope(request) -> str:
    return "admin" if _inbox_url_name(request) == "admin_inbox_list" else "staff"


def _redirect_inbox(request):
    return redirect(_inbox_return_url_name(request))


@login_required
def inbox_list(request):
    personnel = _get_personnel(request)
    if not personnel:
        messages.error(request, "No personnel profile linked to this account.")
        return redirect("no_roles")

    status = (request.GET.get("status") or "open").strip().lower()
    if status not in {"open", "resolved"}:
        status = "open"

    inbox_url_name = _inbox_url_name(request)
    inbox_scope = _inbox_scope(request)

    items = list(
        inbox_items_for_personnel(personnel, status=status, scope=inbox_scope)[:200]
    )

    if status == "open" and items:
        mark_inbox_items_read(
            personnel,
            scope=inbox_scope,
            item_ids=[item.pk for item in items],
        )

    open_count = inbox_items_for_personnel(
        personnel, status="open", scope=inbox_scope
    ).count()
    menu_role = "admin" if inbox_url_name == "admin_inbox_list" else "instructor"
    if menu_role in available_roles_for_user(request.user):
        set_active_role(request.session, menu_role)
    is_admin_view = (
        inbox_url_name == "admin_inbox_list" and user_has_role(request.user, "admin")
    )

    return render(
        request,
        "inbox/list.html",
        {
            "title": "Inbox",
            "items": items,
            "status": status,
            "open_count": open_count,
            "is_admin_view": is_admin_view,
            "inbox_url_name": inbox_url_name,
            "inbox_scope": inbox_scope,
        },
    )


@login_required
@require_http_methods(["POST"])
def inbox_course_request_action(request, pk):
    if not user_has_role(request.user, "admin"):
        messages.error(request, "Only admins can approve course delivery requests.")
        return _redirect_inbox(request)

    personnel = _get_personnel(request)
    item = get_object_or_404(
        StaffInboxItem.objects.select_related(
            "course_delivery_request__instructor",
            "course_delivery_request__course_type",
        ),
        pk=pk,
        kind=StaffInboxItemKind.COURSE_DELIVERY_REQUEST,
    )
    if personnel and not user_can_act_on_inbox_item(request.user, item):
        messages.error(request, "You do not have access to this inbox item.")
        return _redirect_inbox(request)

    course_request = item.course_delivery_request
    if not course_request:
        messages.error(request, "This inbox item is missing its linked request.")
        return _redirect_inbox(request)

    action = (request.POST.get("action") or "").strip().lower()
    admin_note = (request.POST.get("admin_note") or "").strip()

    try:
        if action == "approve":
            approve_course_delivery_request(
                course_request,
                admin_user=request.user,
                admin_note=admin_note,
            )
            messages.success(
                request,
                f"Approved {course_request.instructor.name} to deliver {course_request.course_type.name}.",
            )
        elif action == "decline":
            decline_course_delivery_request(
                course_request,
                admin_user=request.user,
                admin_note=admin_note,
            )
            messages.success(request, "Course delivery request declined.")
        else:
            messages.error(request, "Unknown action.")
    except CourseDeliveryRequestError as exc:
        messages.error(request, str(exc))

    return _redirect_inbox(request)


@login_required
@require_POST
def inbox_swap_accept(request, pk):
    personnel = _get_personnel(request)
    if not personnel:
        return _redirect_inbox(request)

    item = get_object_or_404(
        StaffInboxItem.objects.select_related("course_swap"),
        pk=pk,
        kind=StaffInboxItemKind.COURSE_SWAP_INCOMING,
        recipient=personnel,
    )
    try:
        accept_swap(swap_id=item.course_swap_id, recipient=personnel)
        messages.success(request, "Course cover accepted.")
    except CourseSwapError as exc:
        messages.error(request, str(exc))
    return _redirect_inbox(request)


@login_required
@require_POST
def inbox_swap_decline(request, pk):
    personnel = _get_personnel(request)
    if not personnel:
        return _redirect_inbox(request)

    item = get_object_or_404(
        StaffInboxItem.objects.select_related("course_swap"),
        pk=pk,
        kind=StaffInboxItemKind.COURSE_SWAP_INCOMING,
        recipient=personnel,
    )
    try:
        decline_swap(swap_id=item.course_swap_id, recipient=personnel)
        messages.success(request, "Course cover declined.")
    except CourseSwapError as exc:
        messages.error(request, str(exc))
    return _redirect_inbox(request)


@login_required
@require_GET
def api_inbox_unread(request):
    personnel = _get_personnel(request)
    if not personnel:
        return JsonResponse(
            {
                "unread_count": 0,
                "staff_unread_count": 0,
                "admin_unread_count": 0,
            }
        )

    from .services.staff_inbox import unread_inbox_counts

    counts = unread_inbox_counts(personnel)
    return JsonResponse(
        {
            "unread_count": counts["total"],
            "staff_unread_count": counts["staff"],
            "admin_unread_count": counts["admin"],
        }
    )


@login_required
@require_GET
def api_inbox_open(request):
    """Dashboard widget — recent open inbox items for the current user."""
    personnel = _get_personnel(request)
    if not personnel:
        return JsonResponse({"open_count": 0, "unread_count": 0, "data": []})

    items = (
        inbox_items_for_personnel(personnel, status="open", scope="admin")
        .order_by("-created_at")[:10]
    )
    data = []
    for item in items:
        row = {
            "id": str(item.id),
            "kind": item.get_kind_display(),
            "summary": item.summary,
            "created_at": item.created_at.isoformat(),
            "unread": item.read_at is None,
            "url": reverse("admin_inbox_list"),
        }
        data.append(row)

    return JsonResponse(
        {
            "open_count": inbox_items_for_personnel(
                personnel, status="open", scope="admin"
            ).count(),
            "unread_count": unread_inbox_count(personnel, scope="admin"),
            "data": data,
        }
    )


@login_required
@require_GET
def inbox_stream(request):
    """Server-Sent Events stream for real-time inbox badge updates."""
    personnel = _get_personnel(request)
    if not personnel:
        return JsonResponse({"error": "No personnel profile."}, status=403)

    from .services.inbox_push import (
        build_inbox_payload,
        get_cache_stamp,
        subscribe,
        unsubscribe,
    )

    personnel_id = str(personnel.pk)

    def event_stream():
        subscriber = subscribe(personnel_id)
        try:
            yield f"data: {json.dumps(build_inbox_payload(personnel))}\n\n"
            last_stamp = get_cache_stamp(personnel_id)
            while True:
                try:
                    payload = subscriber.get(timeout=2.0)
                    yield f"data: {json.dumps(payload)}\n\n"
                    last_stamp = get_cache_stamp(personnel_id)
                except queue.Empty:
                    stamp = get_cache_stamp(personnel_id)
                    if stamp != last_stamp:
                        last_stamp = stamp
                        yield f"data: {json.dumps(build_inbox_payload(personnel))}\n\n"
                    else:
                        yield ": keepalive\n\n"
        finally:
            unsubscribe(personnel_id, subscriber)

    response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response
