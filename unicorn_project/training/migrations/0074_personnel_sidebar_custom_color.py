from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("training", "0073_personnel_sidebar_theme_personnel_avatar_icon"),
    ]

    operations = [
        migrations.AddField(
            model_name="personnel",
            name="sidebar_custom_color",
            field=models.CharField(blank=True, default="", max_length=7),
        ),
    ]