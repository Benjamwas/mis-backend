"""Base model mixins used across every domain."""
import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.common.managers import ActiveManager, SoftDeleteManager


class UUIDPKMixin(models.Model):
    """Use UUID primary keys so records are never enumerable via API."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class SoftDeleteModel(models.Model):
    """Soft deletion shared by sensitive/historical entities.

    Records are never destroyed; callers must use `.delete()` which routes through
    QuerySet.delete -> SoftDeleteQuerySet. `.hard_delete()` bypasses soft delete.
    """

    is_deleted = models.BooleanField(default=False, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    objects = SoftDeleteManager()
    all_objects = models.Manager()
    active_objects = ActiveManager()

    class Meta:
        abstract = True

    def delete(self, using=None, keep_parents=False):
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.save(using=using, update_fields=["is_deleted", "deleted_at", "updated_at"])

    def hard_delete(self, using=None, keep_parents=False):
        super().delete(using=using, keep_parents=keep_parents)

    def restore(self):
        self.is_deleted = False
        self.deleted_at = None
        self.save(update_fields=["is_deleted", "deleted_at", "updated_at"])


class SchoolScopedModel(models.Model):
    """Adds tenant isolation: every school-owned record carries school_id.

    All model code must filter by `school` before any business logic runs.
    """

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="+",
        db_index=True,
    )

    class Meta:
        abstract = True