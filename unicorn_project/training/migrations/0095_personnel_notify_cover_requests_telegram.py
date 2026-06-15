from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("training", "0094_courseswap_from_instructor_seen_at"),
    ]

    operations = [
        migrations.AddField(
            model_name="personnel",
            name="notify_cover_requests_telegram",
            field=models.BooleanField(
                default=True,
                help_text="Telegram alerts for course cover requests and responses.",
            ),
        ),
    ]
