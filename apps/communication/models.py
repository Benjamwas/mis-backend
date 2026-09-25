"""Communication: notifications, announcements, templates, campaigns, delivery logs."""
from django.conf import settings
from django.db import models

from apps.common.models import SchoolScopedModel, TimeStampedModel, UUIDPKMixin


class Channel(models.TextChoices):
    IN_APP = "IN_APP", "In App"
    SMS = "SMS", "SMS"
    EMAIL = "EMAIL", "Email"
    WHATSAPP = "WHATSAPP", "WhatsApp"


class DeliveryStatus(models.TextChoices):
    QUEUED = "QUEUED", "Queued"
    SENT = "SENT", "Sent"
    DELIVERED = "DELIVERED", "Delivered"
    FAILED = "FAILED", "Failed"
    CANCELLED = "CANCELLED", "Cancelled"


class Notification(UUIDPKMixin, TimeStampedModel):
    """In-app notification for a user; can deep-link to a resource."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications", db_index=True)
    school = models.ForeignKey("schools.School", on_delete=models.CASCADE, related_name="notifications", null=True, blank=True, db_index=True)
    title = models.CharField(max_length=255)
    body = models.TextField(blank=True, default="")
    type = models.CharField(max_length=80, default="INFO")
    entity_type = models.CharField(max_length=80, blank=True, default="")
    entity_id = models.CharField(max_length=80, blank=True, default="")
    is_read = models.BooleanField(default=False, db_index=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "is_read"], name="idx_notification_user_read")]

    def __str__(self):
        return f"{self.user_id}:{self.title}"


class NotificationTemplate(UUIDPKMixin, TimeStampedModel, SchoolScopedModel):
    code = models.CharField(max_length=80)
    channel = models.CharField(max_length=10, choices=Channel.choices, default=Channel.IN_APP)
    subject = models.CharField(max_length=255, blank=True, default="")
    body = models.TextField(help_text="Body supports {{placeholder}} variables.")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["school", "code", "channel"], name="uq_notification_template")]


class Announcement(UUIDPKMixin, TimeStampedModel, SchoolScopedModel):
    title = models.CharField(max_length=255)
    body = models.TextField()
    audience = models.CharField(max_length=80, default="ALL", db_index=True)  # ALL, STAFF, PARENTS, STUDENTS, TEACHERS
    channels = models.JSONField(default=list, blank=True)  # list of Channel values
    published_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=12, default="DRAFT", db_index=True, choices=(
        ("DRAFT", "Draft"), ("PUBLISHED", "Published"), ("ARCHIVED", "Archived"),
    ))
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="announcements")

    class Meta:
        ordering = ["-created_at"]


class BroadcastCampaign(UUIDPKMixin, TimeStampedModel, SchoolScopedModel):
    title = models.CharField(max_length=255)
    message = models.TextField()
    channel = models.CharField(max_length=10, choices=Channel.choices, default=Channel.SMS)
    audience = models.CharField(max_length=80, default="ALL", db_index=True)
    scheduled_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=15, default="DRAFT", db_index=True, choices=(
        ("DRAFT", "Draft"), ("SCHEDULED", "Scheduled"), ("PROCESSING", "Processing"),
        ("COMPLETED", "Completed"), ("FAILED", "Failed"), ("CANCELLED", "Cancelled"),
    ))
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="campaigns")

    class Meta:
        ordering = ["-created_at"]


class BroadcastRecipient(UUIDPKMixin, TimeStampedModel):
    campaign = models.ForeignKey(BroadcastCampaign, on_delete=models.CASCADE, related_name="recipients")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="campaign_recipients")
    contact = models.CharField(max_length=120, blank=True, default="")  # phone/email address
    status = models.CharField(max_length=15, default=DeliveryStatus.QUEUED, choices=DeliveryStatus.choices, db_index=True)
    provider_message_id = models.CharField(max_length=255, blank=True, default="")
    error = models.TextField(blank=True, default="")
    attempts = models.PositiveIntegerField(default=0)
    delivered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]


class DeliveryLog(UUIDPKMixin, TimeStampedModel, SchoolScopedModel):
    """Immutable record of every outbound provider attempt (email/sms/whatsapp)."""

    channel = models.CharField(max_length=10, choices=Channel.choices)
    recipient = models.CharField(max_length=255)
    subject = models.CharField(max_length=255, blank=True, default="")
    body = models.TextField(blank=True, default="")
    status = models.CharField(max_length=15, choices=DeliveryStatus.choices, default=DeliveryStatus.QUEUED, db_index=True)
    provider = models.CharField(max_length=40, blank=True, default="")
    provider_response = models.JSONField(null=True, blank=True)
    error = models.TextField(blank=True, default="")
    idempotency_key = models.CharField(max_length=255, blank=True, default="", db_index=True)
    related_type = models.CharField(max_length=80, blank=True, default="")
    related_id = models.UUIDField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["idempotency_key"], name="uq_delivery_idempotency",
                                    condition=~models.Q(idempotency_key="")),
        ]