from django.db import migrations, models
import django.core.validators


class Migration(migrations.Migration):

    dependencies = [
        ("training", "0080_add_totp_backup_codes"),
    ]

    operations = [
        migrations.AddField(
            model_name="coursetype",
            name="optional_modules_required",
            field=models.PositiveSmallIntegerField(
                default=0,
                help_text="How many optional competencies must be selected in the assessment matrix (0-5).",
                validators=[
                    django.core.validators.MinValueValidator(0),
                    django.core.validators.MaxValueValidator(5),
                ],
            ),
        ),
    ]
