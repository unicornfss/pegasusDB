from django.db import migrations


def drop_orphan_is_practice_booking(apps, schema_editor):
    connection = schema_editor.connection
    table = "training_booking"
    with connection.cursor() as cursor:
        if connection.vendor == "sqlite":
            cursor.execute(f"PRAGMA table_info({table})")
            columns = {row[1] for row in cursor.fetchall()}
            if "is_practice_booking" in columns:
                schema_editor.execute(
                    f"ALTER TABLE {table} DROP COLUMN is_practice_booking"
                )
        elif connection.vendor == "postgresql":
            schema_editor.execute(
                f"ALTER TABLE {table} DROP COLUMN IF EXISTS is_practice_booking"
            )


class Migration(migrations.Migration):

    dependencies = [
        ("training", "0084_telegram_integration"),
    ]

    operations = [
        migrations.RunPython(drop_orphan_is_practice_booking, migrations.RunPython.noop),
    ]
