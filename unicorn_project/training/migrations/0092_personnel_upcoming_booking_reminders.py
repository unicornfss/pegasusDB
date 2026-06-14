from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("training", "0091_booking_travel_duration_departure_reminder"),
    ]

    operations = [
        migrations.AddField(
            model_name="personnel",
            name="notify_upcoming_bookings_telegram",
            field=models.BooleanField(
                default=False,
                help_text="Telegram reminders before upcoming bookings (days chosen on profile).",
            ),
        ),
        migrations.AddField(
            model_name="personnel",
            name="upcoming_reminder_days_1",
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="personnel",
            name="upcoming_reminder_days_2",
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="personnel",
            name="upcoming_reminder_days_3",
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="personnel",
            name="notify_reminders_telegram",
            field=models.BooleanField(
                default=False,
                help_text="Telegram departure reminder on the course day.",
            ),
        ),
    ]
