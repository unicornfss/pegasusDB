from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("training", "0103_accidentreport_reported_to"),
    ]

    operations = [
        migrations.AddField(
            model_name="personnel",
            name="dismissed_release_notes_id",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Release-notes modal ID the user chose not to see again.",
                max_length=40,
            ),
        ),
    ]
