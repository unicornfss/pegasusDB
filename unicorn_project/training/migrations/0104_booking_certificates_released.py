from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("training", "0103_accidentreport_reported_to"),
    ]

    operations = [
        migrations.AddField(
            model_name="booking",
            name="certificates_released",
            field=models.BooleanField(
                default=False,
                help_text="When enabled, delegates can view certificates (and course details) via the public portal.",
            ),
        ),
    ]
