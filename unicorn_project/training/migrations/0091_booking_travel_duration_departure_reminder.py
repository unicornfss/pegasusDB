from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("training", "0090_fix_telegramnotification_schema"),
    ]

    operations = [
        migrations.AddField(
            model_name="booking",
            name="travel_duration_seconds",
            field=models.PositiveIntegerField(
                blank=True,
                help_text="One-way driving time (seconds) from instructor to venue via Google Maps.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="bookingday",
            name="departure_reminder_sent_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
