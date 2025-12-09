# Neutralised migration to prevent premature NOT NULL enforcement
# This migration intentionally does NOTHING on production.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('training', '0058_feedbackresponse_booking'),
    ]

    operations = [
        # Intentionally empty to prevent breaking production
    ]
