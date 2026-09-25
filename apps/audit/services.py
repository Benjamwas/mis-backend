"""Audit logging helpers."""
import logging

from apps.audit.models import AuditLog

logger = logging.getLogger("apps.audit")


def audit(request, user, action, module, entity_type, entity_id="", old_value=None, new_value=None, school=None):
    """Write an audit event.

    Only semantic snapshots should be passed. Never log passwords, tokens,
    provider secrets, or full payment payloads.
    """
    if user is None and request is not None:
        user = getattr(request, "user", None)

    ip = None
    ua = ""
    if request is not None:
        ip = request.META.get("REMOTE_ADDR")
        xff = request.META.get("HTTP_X_FORWARDED_FOR")
        if xff:
            ip = xff.split(",")[0].strip()
        ua = request.META.get("HTTP_USER_AGENT", "")[:500]

    try:
        AuditLog.objects.create(
            school=school,
            user=user if (user is None or getattr(user, "is_authenticated", False)) else None,
            action=action,
            module=module,
            entity_type=entity_type,
            entity_id=str(entity_id or ""),
            old_value=old_value,
            new_value=new_value,
            ip_address=ip,
            user_agent=ua,
        )
    except Exception as exc:  # audit must never break the request
        logger.warning("audit write failed: %s", exc)


def audit_event(user, action, module, entity_type, entity_id="", old_value=None, new_value=None, school=None):
    """Audit without a request (background/async context)."""
    AuditLog.objects.create(
        school=school,
        user=user,
        action=action,
        module=module,
        entity_type=entity_type,
        entity_id=str(entity_id or ""),
        old_value=old_value,
        new_value=new_value,
    )