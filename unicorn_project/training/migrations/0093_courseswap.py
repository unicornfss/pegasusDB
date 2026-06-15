import uuid

from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ("training", "0092_personnel_upcoming_booking_reminders"),
    ]

    operations = [
        migrations.CreateModel(
            name="CourseSwap",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("accepted", "Accepted"),
                            ("declined", "Declined"),
                            ("cancelled", "Cancelled"),
                        ],
                        db_index=True,
                        default="pending",
                        max_length=16,
                    ),
                ),
                ("message", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("responded_at", models.DateTimeField(blank=True, null=True)),
                (
                    "booking",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="swap_requests",
                        to="training.booking",
                    ),
                ),
                (
                    "from_instructor",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="course_swaps_offered",
                        to="training.personnel",
                    ),
                ),
                (
                    "to_instructor",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="course_swaps_received",
                        to="training.personnel",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddConstraint(
            model_name="courseswap",
            constraint=models.UniqueConstraint(
                condition=models.Q(("status", "pending")),
                fields=("booking",),
                name="uniq_pending_course_swap_per_booking",
            ),
        ),
    ]
