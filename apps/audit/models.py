"""Audit log model.

Sensitive data is never stored: only semantic summaries (`old_value`/`new_value`
are JSON-safe non-secret snapshots prepared by the caller).
"""
from django.conf import settings
from django.db import models

from apps.common.models import TimeStampedModel, UUIDPKMixin


class AuditLog(UUIDPKMixin, TimeStampedModel):
    school = models.ForeignKey(
        "schools.School", on_delete=models.SET_NULL, null=True, blank=True, related_name="audit_logs", db_index=True
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="audit_logs"
    )
    action = models.CharField(max_length=120, db_index=True)
    module = models.CharField(max_length=120, db_index=True)
    entity_type = models.CharField(max_length=120)
    entity_id = models.CharField(max_length=120, blank=True, default="")
    old_value = models.JSONField(null=True, blank=True)
    new_value = models.JSONField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["module", "entity_type", "entity_id"]),
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["school", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.user_id} {self.action} {self.entity_type}:{self.entity_id}"

    def meta(self):
        return {"action": self.action, "module": self.module, "entity_type": self.entity_type,
                "entity_id": self.entity_id, "created_at": self.created_at.isoformat()}