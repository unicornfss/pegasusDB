
from django.core.management.base import BaseCommand
from django.utils.timezone import now
from unicorn_project.training.models import Booking, Invoice

class Command(BaseCommand):
    help = "Backfill all existing invoices from Instructor profile (date + bank fields) without overwriting populated values."

    def handle(self, *args, **options):
        created_count = 0
        updated_count = 0
        skipped = 0

        for b in Booking.objects.select_related("instructor"):
            instr = getattr(b, "instructor", None)
            if not instr:
                skipped += 1
                continue

            inv, created = Invoice.objects.get_or_create(
                booking=b,
                defaults=dict(
                    instructor=instr,
                    invoice_date=now().date(),
                    account_name=(getattr(instr, "name_on_account", "") or ""),
                    sort_code=(getattr(instr, "bank_sort_code", "") or ""),
                    account_number=(getattr(instr, "bank_account_number", "") or ""),
                )
            )
            changed = False
            if not inv.invoice_date:
                inv.invoice_date = now().date(); changed = True
            if not (inv.account_name or "").strip():
                inv.account_name = getattr(instr, "name_on_account", "") or ""; changed = True
            if not (inv.sort_code or "").strip():
                inv.sort_code = getattr(instr, "bank_sort_code", "") or ""; changed = True
            if not (inv.account_number or "").strip():
                inv.account_number = getattr(instr, "bank_account_number", "") or ""; changed = True

            if changed:
                inv.save(update_fields=["invoice_date","account_name","sort_code","account_number"])
                updated_count += 1

            if created:
                created_count += 1

        self.stdout.write(self.style.SUCCESS(
            f"Backfill complete. Created: {created_count}, Updated: {updated_count}, Skipped (no instructor): {skipped}"
        ))
