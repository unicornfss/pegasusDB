from django.db import migrations, models


def add_certificates_released_if_missing(apps, schema_editor):
    """Column may already exist if applied from another branch's 0104."""
    table = "training_booking"
    column = "certificates_released"
    connection = schema_editor.connection
    with connection.cursor() as cursor:
        if connection.vendor == "sqlite":
            cols = {
                row[1]
                for row in cursor.execute(f"PRAGMA table_info({table})").fetchall()
            }
            if column not in cols:
                cursor.execute(
                    f"ALTER TABLE {table} ADD COLUMN {column} bool NOT NULL DEFAULT 0"
                )
            return

        cursor.execute(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_name = %s AND column_name = %s
            """,
            [table, column],
        )
        if cursor.fetchone():
            return
        cursor.execute(
            f"ALTER TABLE {table} ADD COLUMN {column} boolean DEFAULT false NOT NULL"
        )


class Migration(migrations.Migration):

    dependencies = [
        ("training", "0104_personnel_dismissed_release_notes"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name="booking",
                    name="certificates_released",
                    field=models.BooleanField(
                        default=False,
                        help_text=(
                            "When enabled, delegates can view certificates "
                            "(and course details) via the public portal."
                        ),
                    ),
                ),
            ],
            database_operations=[
                migrations.RunPython(
                    add_certificates_released_if_missing,
                    migrations.RunPython.noop,
                ),
            ],
        ),
    ]
