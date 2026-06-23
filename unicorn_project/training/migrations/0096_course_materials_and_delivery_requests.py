from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone
import uuid


def grant_deliverable_courses_to_instructors(apps, schema_editor):
    Personnel = apps.get_model("training", "Personnel")
    CourseType = apps.get_model("training", "CourseType")
    User = apps.get_model("auth", "User")
    Group = apps.get_model("auth", "Group")
    Through = apps.get_model("training", "Personnel_deliverable_course_types")

    instructor_group = Group.objects.filter(name__iexact="instructor").first()
    if not instructor_group:
        return

    course_ids = list(
        CourseType.objects.filter(is_suspended=False).values_list("id", flat=True)
    )
    if not course_ids:
        return

    instructor_user_ids = set(
        instructor_group.user_set.values_list("id", flat=True)
    )
    for personnel in Personnel.objects.filter(user_id__in=instructor_user_ids, is_active=True):
        for course_id in course_ids:
            Through.objects.get_or_create(
                personnel_id=personnel.id,
                coursetype_id=course_id,
            )


class Migration(migrations.Migration):

    dependencies = [
        ("training", "0095_personnel_notify_cover_requests_telegram"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="personnel",
            name="notify_course_materials_email",
            field=models.BooleanField(
                default=False,
                help_text="Email alert when OneDrive course materials folders you deliver are updated.",
            ),
        ),
        migrations.AddField(
            model_name="personnel",
            name="notify_course_materials_telegram",
            field=models.BooleanField(
                default=False,
                help_text="Daily alert when OneDrive course materials folders you deliver are updated.",
            ),
        ),
        migrations.AddField(
            model_name="personnel",
            name="deliverable_course_types",
            field=models.ManyToManyField(
                blank=True,
                help_text="Course types this instructor is allowed to deliver.",
                related_name="qualified_instructors",
                to="training.coursetype",
            ),
        ),
        migrations.CreateModel(
            name="CourseFolderSnapshot",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("folder_url", models.URLField(blank=True, default="")),
                ("file_snapshot", models.JSONField(blank=True, default=dict)),
                ("last_checked_at", models.DateTimeField(blank=True, null=True)),
                ("last_changed_at", models.DateTimeField(blank=True, null=True)),
                ("last_error", models.TextField(blank=True, default="")),
                (
                    "course_type",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="folder_snapshot",
                        to="training.coursetype",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="InstructorCourseRequest",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("approved", "Approved"),
                            ("declined", "Declined"),
                        ],
                        db_index=True,
                        default="pending",
                        max_length=16,
                    ),
                ),
                ("message", models.TextField(blank=True, default="")),
                ("admin_note", models.TextField(blank=True, default="")),
                (
                    "requested_at",
                    models.DateTimeField(default=django.utils.timezone.now),
                ),
                ("resolved_at", models.DateTimeField(blank=True, null=True)),
                (
                    "course_type",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="delivery_requests",
                        to="training.coursetype",
                    ),
                ),
                (
                    "instructor",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="course_delivery_requests",
                        to="training.personnel",
                    ),
                ),
                (
                    "resolved_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="resolved_course_delivery_requests",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-requested_at"],
            },
        ),
        migrations.CreateModel(
            name="StaffInboxItem",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "kind",
                    models.CharField(
                        choices=[
                            (
                                "course_delivery_request",
                                "Course delivery request",
                            )
                        ],
                        db_index=True,
                        max_length=40,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[("open", "Open"), ("resolved", "Resolved")],
                        db_index=True,
                        default="open",
                        max_length=16,
                    ),
                ),
                ("summary", models.CharField(max_length=500)),
                (
                    "created_at",
                    models.DateTimeField(default=django.utils.timezone.now),
                ),
                ("resolved_at", models.DateTimeField(blank=True, null=True)),
                (
                    "course_delivery_request",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="inbox_items",
                        to="training.instructorcourserequest",
                    ),
                ),
                (
                    "resolved_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="resolved_inbox_items",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="CourseMaterialsNotificationLog",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("notified_on", models.DateField()),
                (
                    "course_type",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="materials_notifications",
                        to="training.coursetype",
                    ),
                ),
                (
                    "personnel",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="course_materials_notifications",
                        to="training.personnel",
                    ),
                ),
            ],
        ),
        migrations.AddConstraint(
            model_name="instructorcourserequest",
            constraint=models.UniqueConstraint(
                condition=models.Q(("status", "pending")),
                fields=("instructor", "course_type"),
                name="uniq_pending_instructor_course_request",
            ),
        ),
        migrations.AddConstraint(
            model_name="coursematerialsnotificationlog",
            constraint=models.UniqueConstraint(
                fields=("personnel", "course_type", "notified_on"),
                name="uniq_course_materials_notify_per_day",
            ),
        ),
        migrations.RunPython(
            grant_deliverable_courses_to_instructors,
            migrations.RunPython.noop,
        ),
    ]
