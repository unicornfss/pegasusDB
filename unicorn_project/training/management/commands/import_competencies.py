from django.core.management.base import BaseCommand
import csv

from unicorn_project.training.models import CourseType, CourseCompetency


class Command(BaseCommand):
    help = "Import course competencies from CSV"

    def handle(self, *args, **options):

        created = 0
        skipped = 0

        with open("competencies.csv", newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)

            self.stdout.write(f"Detected columns: {reader.fieldnames}")

            for row in reader:
                course_code = row["code"].strip()      # ✅ CORRECT COLUMN
                competency_name = row["name"].strip() # ✅ CORRECT COLUMN

                try:
                    course_type = CourseType.objects.get(code=course_code)
                except CourseType.DoesNotExist:
                    self.stdout.write(self.style.ERROR(
                        f"❌ Missing CourseType for code: {course_code}"
                    ))
                    skipped += 1
                    continue

                obj, was_created = CourseCompetency.objects.get_or_create(
                    course_type=course_type,
                    name=competency_name,
                    defaults={
                        "description": row.get("description", "").strip(),
                        "sort_order": int(row.get("sort_order") or 0),
                        "is_active": bool(int(row.get("is_active") or 1)),
                    }
                )

                if was_created:
                    created += 1

        self.stdout.write(self.style.SUCCESS(f"✅ Created: {created}"))
        self.stdout.write(self.style.WARNING(f"⚠️ Skipped: {skipped}"))
