from .models import AuditEvent


def record_audit(*, actor=None, action, target=None, summary="", target_type="", target_id=""):
    """Append a concise, secret-free audit event."""
    if target is not None:
        target_type = target_type or target.__class__.__name__
        target_id = target_id or str(getattr(target, "pk", "") or "")
    return AuditEvent.objects.create(
        actor=actor if getattr(actor, "pk", None) else None,
        action=str(action)[:80],
        target_type=str(target_type or "")[:80],
        target_id=str(target_id or "")[:80],
        summary=str(summary or "")[:500],
    )
