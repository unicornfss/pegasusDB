from django.db import migrations


# Known map UI placeholder defaults (instructor / admin fallbacks) — not real pins.
_PLACEHOLDER_POINTS = (
    (52.5, -2.1),
    (52.4895, -1.8986),
)


def _is_placeholder(lat, lng):
    if lat is None or lng is None:
        return True
    lat = float(lat)
    lng = float(lng)
    return any(abs(lat - plat) < 0.01 and abs(lng - plng) < 0.01 for plat, plng in _PLACEHOLDER_POINTS)


def sync_precise_from_admin(apps, schema_editor):
    Booking = apps.get_model("training", "Booking")

    updated = 0
    for booking in Booking.objects.iterator():
        admin_lat = booking.admin_precise_lat
        admin_lng = booking.admin_precise_lng
        precise_lat = booking.precise_lat
        precise_lng = booking.precise_lng

        updates = {}

        if admin_lat is None and admin_lng is None:
            if precise_lat is not None and precise_lng is not None:
                if not _is_placeholder(precise_lat, precise_lng):
                    admin_lat = precise_lat
                    admin_lng = precise_lng
                    updates["admin_precise_lat"] = admin_lat
                    updates["admin_precise_lng"] = admin_lng

        if admin_lat is not None and admin_lng is not None:
            new_lat = float(admin_lat)
            new_lng = float(admin_lng)
            if precise_lat != new_lat or precise_lng != new_lng:
                updates["precise_lat"] = new_lat
                updates["precise_lng"] = new_lng

        if updates:
            Booking.objects.filter(pk=booking.pk).update(**updates)
            updated += 1


class Migration(migrations.Migration):

    dependencies = [
        ("training", "0086_traininglocation_property_name"),
    ]

    operations = [
        migrations.RunPython(sync_precise_from_admin, migrations.RunPython.noop),
    ]
