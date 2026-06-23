from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("training", "0096_course_materials_and_delivery_requests"),
    ]

    operations = [
        migrations.DeleteModel(
            name="CourseMaterialsNotificationLog",
        ),
        migrations.DeleteModel(
            name="CourseFolderSnapshot",
        ),
        migrations.RemoveField(
            model_name="personnel",
            name="notify_course_materials_email",
        ),
        migrations.RemoveField(
            model_name="personnel",
            name="notify_course_materials_telegram",
        ),
    ]
