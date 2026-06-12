from django.db import migrations, models
import django.db.models.deletion


def drop_legacy_telegram_tables(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        if schema_editor.connection.vendor == "sqlite":
            cursor.execute("DROP TABLE IF EXISTS training_telegramnotification")
            cursor.execute("DROP TABLE IF EXISTS training_telegramaccount")


class Migration(migrations.Migration):

    dependencies = [
        ("training", "0082_personnel_default_dashboard_role"),
    ]

    operations = [
        migrations.RunPython(drop_legacy_telegram_tables, migrations.RunPython.noop),
        migrations.AddField(
            model_name="personnel",
            name="notify_booking_changes_telegram",
            field=models.BooleanField(
                default=False,
                help_text="Telegram alert when a booking is updated or cancelled.",
            ),
        ),
        migrations.AddField(
            model_name="personnel",
            name="notify_new_bookings_telegram",
            field=models.BooleanField(
                default=False,
                help_text="Telegram alert when a new booking is assigned to you.",
            ),
        ),
        migrations.AddField(
            model_name="personnel",
            name="notify_reminders_telegram",
            field=models.BooleanField(
                default=False,
                help_text="Telegram reminder before upcoming bookings.",
            ),
        ),
        migrations.AddField(
            model_name="personnel",
            name="telegram_chat_id",
            field=models.CharField(blank=True, default="", max_length=32),
        ),
        migrations.AddField(
            model_name="personnel",
            name="telegram_linked_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.CreateModel(
            name="TelegramNotification",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("notification_type", models.CharField(max_length=32)),
                ("message_id", models.CharField(blank=True, default="", max_length=64)),
                ("sent_at", models.DateTimeField(auto_now_add=True)),
                ("success", models.BooleanField(default=True)),
                ("error_text", models.TextField(blank=True, default="")),
                (
                    "booking",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="telegram_notifications",
                        to="training.booking",
                    ),
                ),
                (
                    "personnel",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="telegram_notifications",
                        to="training.personnel",
                    ),
                ),
            ],
            options={
                "ordering": ["-sent_at"],
            },
        ),
    ]
