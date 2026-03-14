from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("training", "0074_personnel_sidebar_custom_color"),
    ]

    operations = [
        migrations.AddField(
            model_name="personnel",
            name="night_mode",
            field=models.BooleanField(default=False),
        ),
    ]