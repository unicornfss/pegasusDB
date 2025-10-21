# training/migrations/0022_exam_exam_code.py
from django.db import migrations, models

def populate_exam_codes(apps, schema_editor):
    Exam = apps.get_model("training", "Exam")
    for e in Exam.objects.select_related("course_type"):
        base = (e.course_type.code or "").upper()
        if e.sequence:
            e.exam_code = f"{base}{int(e.sequence):02d}"
            e.save(update_fields=["exam_code"])

class Migration(migrations.Migration):
    dependencies = [("training", "0021_exam_examquestion_examanswer")]
    operations = [
        migrations.AddField(
            model_name="exam",
            name="exam_code",
            field=models.CharField(
                max_length=40, null=True, blank=True, editable=False, db_index=True
            ),
        ),
        migrations.RunPython(populate_exam_codes, migrations.RunPython.noop),
    ]
