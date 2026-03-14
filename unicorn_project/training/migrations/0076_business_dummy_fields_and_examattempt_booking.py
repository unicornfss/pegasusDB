from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("training", "0075_personnel_night_mode"),
    ]

    operations = [
        migrations.AddField(
            model_name="business",
            name="dummy_course_type",
            field=models.ForeignKey(blank=True, help_text="Default course type used when instructors create quick dummy bookings.", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="dummy_businesses", to="training.coursetype"),
        ),
        migrations.AddField(
            model_name="business",
            name="is_dummy",
            field=models.BooleanField(default=False, help_text="Marks this as a dummy / familiarisation business."),
        ),
        migrations.AddField(
            model_name="examattempt",
            name="booking",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="exam_attempts", to="training.booking"),
        ),
    ]