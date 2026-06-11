from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("training", "0081_coursetype_optional_modules_required"),
    ]

    operations = [
        migrations.AddField(
            model_name="personnel",
            name="default_dashboard_role",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Preferred dashboard when logging in (for users with multiple roles).",
                max_length=20,
            ),
        ),
    ]
