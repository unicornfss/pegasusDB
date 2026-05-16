from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ("training", "0081_coursetype_optional_modules_required"),
    ]

    operations = [
        migrations.CreateModel(
            name="TelegramAccount",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "telegram_id",
                    models.BigIntegerField(
                        help_text="Unique Telegram user ID", unique=True
                    ),
                ),
                (
                    "telegram_username",
                    models.CharField(
                        blank=True,
                        help_text="Telegram username (if available)",
                        max_length=32,
                        null=True,
                    ),
                ),
                (
                    "first_name",
                    models.CharField(
                        blank=True,
                        help_text="Telegram first name",
                        max_length=255,
                        null=True,
                    ),
                ),
                (
                    "last_name",
                    models.CharField(
                        blank=True,
                        help_text="Telegram last name",
                        max_length=255,
                        null=True,
                    ),
                ),
                (
                    "linked_at",
                    models.DateTimeField(
                        auto_now_add=True, help_text="When the account was linked"
                    ),
                ),
                (
                    "updated_at",
                    models.DateTimeField(
                        auto_now=True,
                        help_text="Last time this record was updated",
                    ),
                ),
                (
                    "personnel",
                    models.OneToOneField(
                        help_text="The Personnel account linked to Telegram",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="telegram_account",
                        to="training.personnel",
                    ),
                ),
            ],
            options={
                "verbose_name": "Telegram Account",
                "verbose_name_plural": "Telegram Accounts",
                "ordering": ["-linked_at"],
            },
        ),
    ]
