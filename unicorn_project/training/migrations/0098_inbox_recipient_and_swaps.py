from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def backfill_inbox_items(apps, schema_editor):
    Personnel = apps.get_model("training", "Personnel")
    CourseSwap = apps.get_model("training", "CourseSwap")
    StaffInboxItem = apps.get_model("training", "StaffInboxItem")
    InstructorCourseRequest = apps.get_model("training", "InstructorCourseRequest")
    Group = apps.get_model("auth", "Group")

    admin_group = Group.objects.filter(name__iexact="admin").first()
    admin_ids = []
    if admin_group:
        admin_ids = list(
            Personnel.objects.filter(
                is_active=True,
                user__is_active=True,
                user__groups=admin_group,
            ).values_list("pk", flat=True)
        )

    for item in StaffInboxItem.objects.filter(
        recipient__isnull=True,
        kind="course_delivery_request",
    ):
        if admin_ids:
            first_admin = admin_ids[0]
            item.recipient_id = first_admin
            item.save(update_fields=["recipient_id"])
            for admin_id in admin_ids[1:]:
                StaffInboxItem.objects.get_or_create(
                    recipient_id=admin_id,
                    kind=item.kind,
                    course_delivery_request_id=item.course_delivery_request_id,
                    defaults={
                        "status": item.status,
                        "summary": item.summary,
                        "read_at": item.read_at,
                        "created_at": item.created_at,
                    },
                )

    for req in InstructorCourseRequest.objects.filter(status="pending"):
        summary = f"Course delivery request (pending)"
        for admin_id in admin_ids:
            if not StaffInboxItem.objects.filter(
                recipient_id=admin_id,
                course_delivery_request_id=req.pk,
                kind="course_delivery_request",
            ).exists():
                StaffInboxItem.objects.create(
                    recipient_id=admin_id,
                    kind="course_delivery_request",
                    status="open",
                    summary=summary,
                    course_delivery_request_id=req.pk,
                )

    for swap in CourseSwap.objects.filter(status="pending").select_related(
        "from_instructor", "to_instructor", "booking", "booking__course_type"
    ):
        if StaffInboxItem.objects.filter(
            course_swap_id=swap.pk,
            kind="course_swap_incoming",
        ).exists():
            continue
        booking = swap.booking
        ref = getattr(booking, "course_reference", None) or str(booking.pk)
        course = getattr(booking, "course_type", None)
        course_name = getattr(course, "name", "Course") if course else "Course"
        summary = (
            f"{swap.from_instructor.name} offered you a course cover: "
            f"{ref} · {course_name}"
        )
        StaffInboxItem.objects.create(
            recipient_id=swap.to_instructor_id,
            kind="course_swap_incoming",
            status="open",
            summary=summary[:500],
            course_swap_id=swap.pk,
        )

    for swap in CourseSwap.objects.filter(
        status__in=["accepted", "declined"],
        from_instructor_seen_at__isnull=True,
    ).select_related("from_instructor", "to_instructor", "booking", "booking__course_type"):
        if StaffInboxItem.objects.filter(
            course_swap_id=swap.pk,
            kind="course_swap_outcome",
        ).exists():
            continue
        verb = "accepted" if swap.status == "accepted" else "declined"
        booking = swap.booking
        ref = getattr(booking, "course_reference", None) or str(booking.pk)
        course = getattr(booking, "course_type", None)
        course_name = getattr(course, "name", "Course") if course else "Course"
        summary = (
            f"{swap.to_instructor.name} {verb} your course cover offer: "
            f"{ref} · {course_name}"
        )
        StaffInboxItem.objects.create(
            recipient_id=swap.from_instructor_id,
            kind="course_swap_outcome",
            status="open",
            summary=summary[:500],
            course_swap_id=swap.pk,
        )


class Migration(migrations.Migration):

    dependencies = [
        ("training", "0097_remove_course_materials_tracking"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="staffinboxitem",
            name="read_at",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="staffinboxitem",
            name="recipient",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="inbox_items",
                to="training.personnel",
            ),
        ),
        migrations.AddField(
            model_name="staffinboxitem",
            name="course_swap",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="inbox_items",
                to="training.courseswap",
            ),
        ),
        migrations.AlterField(
            model_name="staffinboxitem",
            name="kind",
            field=models.CharField(
                choices=[
                    ("course_delivery_request", "Course delivery request"),
                    ("course_swap_incoming", "Course cover request"),
                    ("course_swap_outcome", "Course cover update"),
                ],
                db_index=True,
                max_length=40,
            ),
        ),
        migrations.AddIndex(
            model_name="staffinboxitem",
            index=models.Index(
                fields=["recipient", "status", "read_at"],
                name="training_st_recipie_0d4f2d_idx",
            ),
        ),
        migrations.RunPython(backfill_inbox_items, migrations.RunPython.noop),
    ]
