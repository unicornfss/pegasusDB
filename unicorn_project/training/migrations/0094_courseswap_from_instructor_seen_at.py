from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("training", "0093_courseswap"),
    ]

    operations = [
        migrations.AddField(
            model_name="courseswap",
            name="from_instructor_seen_at",
            field=models.DateTimeField(
                blank=True,
                help_text="When the offering instructor viewed the accept/decline outcome.",
                null=True,
            ),
        ),
    ]
