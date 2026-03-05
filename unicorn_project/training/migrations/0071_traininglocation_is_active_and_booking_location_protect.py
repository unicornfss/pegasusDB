from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("training", "0070_remove_examquestion_image_examquestion_image_url"),
    ]

    operations = [
        migrations.AddField(
            model_name="traininglocation",
            name="is_active",
            field=models.BooleanField(db_index=True, default=True),
        ),
        migrations.AlterField(
            model_name="booking",
            name="training_location",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="bookings",
                to="training.traininglocation",
            ),
        ),
    ]
