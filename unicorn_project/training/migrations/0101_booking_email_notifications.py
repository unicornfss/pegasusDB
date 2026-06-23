from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("training", "0100_booking_list_indexes"),
    ]

    operations = [
        migrations.AddField(
            model_name="personnel",
            name="notify_new_bookings_email",
            field=models.BooleanField(
                default=False,
                help_text="Email alert when a new booking is assigned to you.",
            ),
        ),
        migrations.AddField(
            model_name="personnel",
            name="notify_booking_changes_email",
            field=models.BooleanField(
                default=False,
                help_text="Email alert when a booking is updated or cancelled.",
            ),
        ),
        migrations.AddField(
            model_name="personnel",
            name="notify_reminders_email",
            field=models.BooleanField(
                default=False,
                help_text="Email departure reminder on the course day.",
            ),
        ),
        migrations.AddField(
            model_name="personnel",
            name="notify_upcoming_bookings_email",
            field=models.BooleanField(
                default=False,
                help_text="Email reminders before upcoming bookings (days chosen on profile).",
            ),
        ),
        migrations.CreateModel(
            name="EmailNotification",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("notification_type", models.CharField(max_length=32)),
                ("provider_message_id", models.CharField(blank=True, default="", max_length=128)),
                ("sent_at", models.DateTimeField(auto_now_add=True)),
                ("success", models.BooleanField(default=True)),
                ("error_text", models.TextField(blank=True, default="")),
                (
                    "booking",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="email_notifications",
                        to="training.booking",
                    ),
                ),
                (
                    "personnel",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="email_notifications",
                        to="training.personnel",
                    ),
                ),
            ],
            options={
                "ordering": ["-sent_at"],
            },
        ),
    ]
