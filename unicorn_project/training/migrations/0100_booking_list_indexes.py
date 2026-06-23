from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("training", "0099_emergency_takeover_and_invoice_fk"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="booking",
            index=models.Index(
                fields=["instructor", "status"],
                name="training_book_instr_status_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="booking",
            index=models.Index(
                fields=["status", "course_date"],
                name="training_book_status_date_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="bookingday",
            index=models.Index(
                fields=["instructor", "booking"],
                name="training_day_instr_book_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="invoice",
            index=models.Index(
                fields=["booking", "instructor"],
                name="training_inv_book_instr_idx",
            ),
        ),
    ]
