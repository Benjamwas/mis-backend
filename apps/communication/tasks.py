"""Celery tasks for communication delivery, reminders and async work."""
import logging

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from apps.common.exceptions import ProviderNotConfiguredError

logger = logging.getLogger("apps.communication")


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def send_sms(self, to: str, body: str, school_id=None, idempotency_key="", related_type="", related_id=None):
    """Send one SMS with retry on transient failures; permanent provider errors do not retry."""
    from apps.communication.models import DeliveryLog
    from apps.communication.providers import get_sms_provider
    from apps.communication.models import Channel, DeliveryStatus

    if idempotency_key and DeliveryLog.objects.filter(idempotency_key=idempotency_key).exists():
        logger.info("sms idempotent skip: %s", idempotency_key)
        return {"skipped": True, "reason": "duplicate"}

    log = DeliveryLog.objects.create(
        school_id=school_id, channel=Channel.SMS, recipient=to, body=body,
        status=DeliveryStatus.QUEUED, idempotency_key=idempotency_key,
        related_type=related_type, related_id=related_id,
    )
    try:
        provider = get_sms_provider()
        result = provider.send(to, body)
    except ProviderNotConfiguredError as exc:
        log.status = DeliveryStatus.FAILED
        log.error = str(exc)
        log.provider = "none"
        log.save(update_fields=["status", "error", "provider", "updated_at"])
        return {"ok": False, "error": str(exc), "configured": False}
    except Exception as exc:  # noqa: BLE001
        log.status = DeliveryStatus.FAILED
        log.error = str(exc)[:500]
        log.save(update_fields=["status", "error", "updated_at"])
        try:
            raise self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            return {"ok": False, "error": str(exc)}

    if result.get("ok"):
        log.status = DeliveryStatus.SENT
        log.provider = getattr(provider, "name", "")
        log.provider_response = {"message_id": result.get("provider_message_id")}
        log.save(update_fields=["status", "provider", "provider_response", "updated_at"])
        return {"ok": True, "log_id": str(log.id)}

    log.status = DeliveryStatus.FAILED
    log.provider = getattr(provider, "name", "")
    log.error = str(result.get("raw"))[:500]
    log.save(update_fields=["status", "provider", "error", "updated_at"])
    # HTTP 4xx = permanent (bad number), do not retry; 5xx retry
    status_code = result.get("status_code")
    if status_code and status_code >= 500:
        try:
            raise self.retry()
        except self.MaxRetriesExceededError:
            pass
    return {"ok": False, "log_id": str(log.id), "error": log.error}


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_email(self, to: str, subject: str, body: str, html: str = "", school_id=None, idempotency_key=""):
    from apps.communication.models import Channel, DeliveryLog, DeliveryStatus
    from apps.communication.providers import EmailService

    if idempotency_key and DeliveryLog.objects.filter(idempotency_key=idempotency_key).exists():
        return {"skipped": True, "reason": "duplicate"}

    log = DeliveryLog.objects.create(
        school_id=school_id, channel=Channel.EMAIL, recipient=to, subject=subject, body=body,
        status=DeliveryStatus.QUEUED, idempotency_key=idempotency_key, provider="django_email",
    )
    result = EmailService.send(to, subject, body, html=html)
    if result.get("ok"):
        log.status = DeliveryStatus.SENT
        log.save(update_fields=["status", "updated_at"])
        return {"ok": True, "log_id": str(log.id)}
    log.status = DeliveryStatus.FAILED
    log.error = str(result.get("error", ""))[:500]
    log.save(update_fields=["status", "error", "updated_at"])
    try:
        raise self.retry()
    except self.MaxRetriesExceededError:
        return {"ok": False, "log_id": str(log.id), "error": log.error}


@shared_task(bind=True, max_retries=3, default_retry_delay=45)
def send_whatsapp(self, to: str, body: str, template_code: str = "", variables: dict | None = None, school_id=None, idempotency_key=""):
    from apps.communication.models import Channel, DeliveryLog, DeliveryStatus
    from apps.communication.providers import get_whatsapp_provider

    if idempotency_key and DeliveryLog.objects.filter(idempotency_key=idempotency_key).exists():
        return {"skipped": True, "reason": "duplicate"}

    log = DeliveryLog.objects.create(
        school_id=school_id, channel=Channel.WHATSAPP, recipient=to, body=body,
        status=DeliveryStatus.QUEUED, idempotency_key=idempotency_key,
    )
    try:
        provider = get_whatsapp_provider()
        result = provider.send(to, template_code, variables or {}, body)
    except ProviderNotConfiguredError as exc:
        log.status = DeliveryStatus.FAILED
        log.error = str(exc)
        log.save(update_fields=["status", "error", "updated_at"])
        return {"ok": False, "error": str(exc), "configured": False}
    except Exception as exc:  # noqa: BLE001
        log.status = DeliveryStatus.FAILED
        log.error = str(exc)[:500]
        log.save(update_fields=["status", "error", "updated_at"])
        try:
            raise self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            return {"ok": False, "error": str(exc)}

    if result.get("ok"):
        log.status = DeliveryStatus.SENT
        log.provider = getattr(provider, "name", "")
        log.provider_response = {"message_id": result.get("provider_message_id")}
        log.save(update_fields=["status", "provider", "provider_response", "updated_at"])
        return {"ok": True, "log_id": str(log.id)}
    log.status = DeliveryStatus.FAILED
    log.provider = getattr(provider, "name", "")
    log.error = str(result.get("raw"))[:500]
    log.save(update_fields=["status", "provider", "error", "updated_at"])
    return {"ok": False, "log_id": str(log.id), "error": log.error}


@shared_task
def notify_users(user_ids, title, body="", entity_type="", entity_id=None, school_id=None, type_="INFO"):
    """Create in-app notifications for a list of users."""
    from apps.communication.models import Notification
    from django.utils import timezone

    now = timezone.now()
    rows = [
        Notification(
            user_id=uid, title=title, body=body, entity_type=entity_type,
            entity_id=str(entity_id) if entity_id else "", school_id=school_id, type=type_, created_at=now, updated_at=now,
        )
        for uid in user_ids
    ]
    Notification.objects.bulk_create(rows, ignore_conflicts=True)
    return {"count": len(rows)}


@shared_task
def send_transactional_email_job(to_email: str, subject: str, template: str, context: dict | None = None, school_id=None):
    """Render a simple template body and enqueue email delivery."""
    context = context or {}
    body = _render_template(template, context)
    return send_email.delay(to_email, subject, body, school_id=school_id, idempotency_key=f"tpl:{template}:{to_email}:{subject}:{context.get('token', '')}")


_TEMPLATES = {
    "password_reset": "Hello {name},\n\nUse this link to reset your password: {reset_link}\n\nIf you did not request this, ignore this email.",
    "payment_receipt": "Hello {name},\n\nWe received your payment of KES {amount}. Receipt: {receipt_number}.\n\nThank you.",
    "assignment_published": "Hello {name},\n\nNew assignment '{title}' has been published for {subject}.",
    "result_published": "Hello {name},\n\nResults for {term} have been published.",
    "leave_approved": "Hello {name},\n\nYour leave request ({leave_type}) has been approved for {dates}.",
    "leave_rejected": "Hello {name},\n\nYour leave request ({leave_type}) was not approved.",
    "admission_decision": "Hello {name},\n\nApplication {application_number}: {status}.",
}


def _render_template(template: str, context: dict) -> str:
    from string import Template

    raw = _TEMPLATES.get(template, str(context.get("body", "")))
    try:
        return raw.format(**context)
    except (KeyError, IndexError):
        return raw


@shared_task
def notify_enrolled_class_students(school_id, class_id, title, body="", type_="INFO"):
    """Fan a notification out to students (via their portal user) in a class."""
    from apps.people.models import Student

    students = Student.objects.filter(
        school_id=school_id, enrollments__school_class_id=class_id, enrollments__status="ACTIVE"
    ).select_related("person")
    user_ids = []
    for s in students:
        u = s.person.users.filter(is_active=True).first()
        if u:
            user_ids.append(u.id)
    if user_ids:
        return notify_users(user_ids, title, body, "Class", class_id, school_id, type_)
    return {"count": 0}


@shared_task
def dispatch_broadcast(campaign_id):
    """Fan out a campaign to its recipients and send per recipient on the right channel."""
    from apps.communication.models import BroadcastCampaign, BroadcastRecipient, Channel
    from apps.communication.services import audience_recipients

    campaign = BroadcastCampaign.objects.get(pk=campaign_id)
    campaign.status = "PROCESSING"
    campaign.save(update_fields=["status", "updated_at"])

    rows = audience_recipients(campaign)
    BroadcastRecipient.objects.bulk_create(rows, ignore_conflicts=True)

    failed = 0
    sent = 0
    for rec in BroadcastRecipient.objects.filter(campaign=campaign, status="QUEUED"):
        try:
            if campaign.channel == Channel.SMS:
                send_sms.delay(rec.contact, campaign.message, school_id=campaign.school_id,
                               idempotency_key=f"camp:{campaign.id}:{rec.id}")
            elif campaign.channel == Channel.EMAIL:
                send_email.delay(rec.contact, campaign.title, campaign.message, school_id=campaign.school_id,
                                 idempotency_key=f"camp:{campaign.id}:{rec.id}")
            elif campaign.channel == Channel.WHATSAPP:
                send_whatsapp.delay(rec.contact, campaign.message, school_id=campaign.school_id,
                                    idempotency_key=f"camp:{campaign.id}:{rec.id}")
            rec.status = "SENT"
            rec.attempts += 1
            rec.save(update_fields=["status", "attempts", "updated_at"])
            sent += 1
        except Exception as exc:  # noqa: BLE001
            rec.status = "FAILED"
            rec.error = str(exc)[:500]
            rec.save(update_fields=["status", "error", "updated_at"])
            failed += 1

    campaign.status = "FAILED" if failed and not sent else "COMPLETED"
    campaign.save(update_fields=["status", "updated_at"])
    return {"sent": sent, "failed": failed}