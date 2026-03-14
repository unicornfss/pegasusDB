from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("training", "0072_personnel_totp_secret"),
    ]

    operations = [
        migrations.AddField(
            model_name="personnel",
            name="avatar_icon",
            field=models.CharField(
                choices=[
                    ("initials", "Initials"),
                    ("person", "Person"),
                    ("star", "Star"),
                    ("graduation", "Graduation Cap"),
                    ("tools", "Tools"),
                    ("unicorn", "Sparkles"),
                    ("briefcase", "Briefcase"),
                    ("books", "Books"),
                    ("note", "Note"),
                    ("cog", "Cog"),
                    ("heart", "Heart"),
                ],
                default="initials",
                max_length=30,
            ),
        ),
        migrations.AddField(
            model_name="personnel",
            name="sidebar_theme",
            field=models.CharField(
                choices=[
                    ("default", "Default Burgundy"),
                    ("ocean", "Ocean Blue"),
                    ("forest", "Forest Green"),
                    ("plum", "Plum"),
                    ("charcoal", "Charcoal"),
                ],
                default="default",
                max_length=20,
            ),
        ),
    ]