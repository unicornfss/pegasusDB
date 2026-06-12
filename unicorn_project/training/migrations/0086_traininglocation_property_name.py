from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("training", "0085_drop_orphan_is_practice_booking"),
    ]

    operations = [
        migrations.AddField(
            model_name="traininglocation",
            name="property_name",
            field=models.CharField(
                blank=True,
                help_text="Building or site name (e.g. Progress House), if different from the street address.",
                max_length=255,
                null=True,
            ),
        ),
    ]
