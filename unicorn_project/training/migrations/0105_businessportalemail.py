from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ("training", "0104_booking_certificates_released"),
    ]

    operations = [
        migrations.CreateModel(
            name="BusinessPortalEmail",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("email", models.EmailField(max_length=254)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "business",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="portal_emails",
                        to="training.business",
                    ),
                ),
            ],
            options={
                "ordering": ["email"],
            },
        ),
        migrations.AddConstraint(
            model_name="businessportalemail",
            constraint=models.UniqueConstraint(
                fields=("business", "email"),
                name="uniq_business_portal_email",
            ),
        ),
    ]
