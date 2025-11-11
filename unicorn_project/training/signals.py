# unicorn_project/training/signals.py
from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from django.db import transaction

from .models import DelegateRegister, CompetencyAssessment
from .services.carry_forward import carry_forward_competencies


@receiver(pre_save, sender=DelegateRegister)
def _mark_identity_change(sender, instance: DelegateRegister, **kwargs):
    """
    Before saving, detect if name or date_of_birth changed so we can act after save.
    """
    if not instance.pk:
        # new object; handled by post_save(created=True)
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

    identity_changed = (norm(prev.name) != norm(instance.name)) or (
        prev.date_of_birth != instance.date_of_birth
    )
    instance._cf_identity_changed = identity_changed


@receiver(post_save, sender=DelegateRegister)
def _carry_forward_on_register_save(sender, instance: DelegateRegister, created, raw, **kwargs):
    """
    On create: run carry-forward.
    On update with identity change: refresh carried ticks and re-run carry-forward.
    """
    if raw:
        return

    # Always run on create (covers instructor add + public add)
    if created:
        transaction.on_commit(lambda: carry_forward_competencies(instance))
        return

    # On update, only if identity changed
    if getattr(instance, "_cf_identity_changed", False):
        def _refresh():
            # remove previously carried-forward ticks for this register
            CompetencyAssessment.objects.filter(register=instance, is_locked=True).delete()
            # re-run carry forward with the corrected identity
            carry_forward_competencies(instance)

        transaction.on_commit(_refresh)
