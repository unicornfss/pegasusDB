# unicorn_project/training/signals.py
from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from django.db import transaction
from django.contrib.auth.models import User

from .models import DelegateRegister, CompetencyAssessment, Personnel
from .services.carry_forward import carry_forward_competencies
from .signal_control import is_disabled, disable, enable

# ============================================================
#  DELEGATE REGISTER SIGNALS (unchanged)
# ============================================================

@receiver(pre_save, sender=DelegateRegister)
def _mark_identity_change(sender, instance: DelegateRegister, **kwargs):
    if not instance.pk:
        instance._cf_identity_changed = False
        return

    try:
        prev = DelegateRegister.objects.select_related(
            "booking_day__booking__course_type"
        ).get(pk=instance.pk)
    except DelegateRegister.DoesNotExist:
        instance._cf_identity_changed = False
        return

    def norm(s):
        return (s or "").strip().lower()

    instance._cf_identity_changed = (
        norm(prev.name) != norm(instance.name)
        or prev.date_of_birth != instance.date_of_birth
    )


@receiver(post_save, sender=DelegateRegister)
def _carry_forward_on_register_save(sender, instance: DelegateRegister, created, raw, **kwargs):
    if raw:
        return

    if created:
        transaction.on_commit(lambda: carry_forward_competencies(instance))
        return

    if getattr(instance, "_cf_identity_changed", False):

        def _refresh():
            CompetencyAssessment.objects.filter(
                register=instance, is_locked=True
            ).delete()
            carry_forward_competencies(instance)

        transaction.on_commit(_refresh)


# ============================================================
#  USER → PERSONNEL SYNC
# ============================================================

@receiver(post_save, sender=User)
def sync_user_to_personnel(sender, instance, update_fields=None, **kwargs):
    """
    Sync User.first_name/last_name → Personnel.name
    BUT:
      - do NOT fire if profile update explicitly disabled sync
      - do NOT overwrite Personnel fields unnecessarily
    """

    if is_disabled():        # <<< PREVENT LOOPS
        return

    if instance.is_superuser:
        return

    if not hasattr(instance, "personnel"):
        return

    # Only skip if update_fields is provided AND does not include name fields
    if update_fields is not None and not (
        "first_name" in update_fields or "last_name" in update_fields
    ):
        return
    
    personnel = instance.personnel
    full = (instance.first_name + " " + instance.last_name).strip()

    if full and personnel.name != full:
        Personnel.objects.filter(pk=personnel.pk).update(name=full)


# ============================================================
#  PERSONNEL → USER SYNC
# ============================================================

def split_name(full_name: str):
    if not full_name:
        return "", ""
    parts = full_name.strip().split()
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], " ".join(parts[1:])


@receiver(post_save, sender=Personnel)
def sync_personnel_to_user(sender, instance, update_fields=None, **kwargs):
    """
    Sync Personnel.name → User.first_name / last_name
    BUT:
      - do NOT fire if profile update explicitly disabled sync
      - only run when Personnel.name changed
    """
    if is_disabled():      # <<< PREVENT LOOPS
        return

    user = instance.user
    if not user:
        return

    if update_fields and "name" not in update_fields:
        return

    first, last = split_name(instance.name)

    if user.first_name != first or user.last_name != last:
        User.objects.filter(pk=user.pk).update(
            first_name=first,
            last_name=last,
        )
