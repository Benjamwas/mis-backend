"""File upload model + storage abstractions (local and Supabase)."""
import mimetypes
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.common.models import SchoolScopedModel, TimeStampedModel, UUIDPKMixin


class FileCategory(models.TextChoices):
    PROFILE_PHOTO = "PROFILE_PHOTO", "Profile Photo"
    ADMISSION_DOCUMENT = "ADMISSION_DOCUMENT", "Admission Document"
    ASSIGNMENT_ATTACHMENT = "ASSIGNMENT_ATTACHMENT", "Assignment Attachment"
    LEARNING_RESOURCE = "LEARNING_RESOURCE", "Learning Resource"
    GALLERY_MEDIA = "GALLERY_MEDIA", "Gallery Media"
    PAYSLIP = "PAYSLIP", "Payslip"
    RECEIPT = "RECEIPT", "Receipt"
    REPORT = "REPORT", "Report"
    OTHER = "OTHER", "Other"


ALLOWED_MIME_TYPES = {
    "application/pdf",
    "image/jpeg", "image/png", "image/webp", "image/gif",
    "video/mp4", "video/webm",
    "audio/mpeg", "audio/mp4",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
    "text/plain", "text/csv",
}
MAX_FILE_SIZE = 25 * 1024 * 1024  # 25 MB


class FileUpload(UUIDPKMixin, TimeStampedModel, SchoolScopedModel):
    """Metadata for a stored file. The binary lives in configured storage."""

    file = models.FileField(upload_to="uploads/%Y/%m/", max_length=500)
    original_name = models.CharField(max_length=255)
    category = models.CharField(max_length=30, choices=FileCategory.choices, default=FileCategory.OTHER)
    mime_type = models.CharField(max_length=120, blank=True, default="")
    size = models.PositiveBigIntegerField(default=0)
    stored_path = models.CharField(max_length=500, blank=True, default="")
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="uploads"
    )
    linked_type = models.CharField(max_length=120, blank=True, default="")
    linked_id = models.UUIDField(null=True, blank=True)
    is_archived = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]

    def clean(self):
        if self.mime_type and self.mime_type not in ALLOWED_MIME_TYPES:
            raise ValidationError({"file": f"File type {self.mime_type} is not allowed."})
        if self.size and self.size > MAX_FILE_SIZE:
            raise ValidationError({"file": f"File exceeds the {MAX_FILE_SIZE // (1024*1024)}MB limit."})

    def save(self, *args, **kwargs):
        if self.file:
            self.original_name = self.original_name or self.file.name
            self.size = self.size or self.file.size or 0
            if not self.mime_type:
                self.mime_type = mimetypes.guess_type(self.file.name)[0] or "application/octet-stream"
            self.stored_path = self.file.name
        super().save(*args, **kwargs)

    @property
    def url(self):
        try:
            return self.file.url
        except Exception:
            return ""

    def __str__(self):
        return f"{self.category}:{self.original_name}"