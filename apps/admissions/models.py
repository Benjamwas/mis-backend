"""Admissions: applicants, applications, documents and status history."""
from django.conf import settings
from django.db import models

from apps.common.models import SchoolScopedModel, TimeStampedModel, UUIDPKMixin


class Applicant(UUIDPKMixin, TimeStampedModel, SchoolScopedModel):
    class Status(models.TextChoices):
        NEW = "NEW", "New"
        CONTACTED = "CONTACTED", "Contacted"
        APPLIED = "APPLIED", "Applied"
        ACCEPTED = "ACCEPTED", "Accepted"
        WITHDRAWN = "WITHDRAWN", "Withdrawn"

    person = models.OneToOneField(
        "identity.Person", on_delete=models.PROTECT, null=True, blank=True, related_name="applicant"
    )
    first_name = models.CharField(max_length=120)
    last_name = models.CharField(max_length=120)
    email = models.EmailField(blank=True, default="")
    phone = models.CharField(max_length=20, blank=True, default="")
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=10, blank=True, default="")
    current_school = models.CharField(max_length=160, blank=True, default="")
    previous_results = models.TextField(blank=True, default="")
    guardian_name = models.CharField(max_length=200, blank=True, default="")
    guardian_phone = models.CharField(max_length=20, blank=True, default="")
    guardian_email = models.EmailField(blank=True, default="")
    address = models.TextField(blank=True, default="")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.NEW, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    def __str__(self):
        return self.full_name


class AdmissionApplication(UUIDPKMixin, TimeStampedModel, SchoolScopedModel):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    UNDER_REVIEW = "UNDER_REVIEW"
    SHORTLISTED = "SHORTLISTED"
    INTERVIEW = "INTERVIEW"
    DECISION_PENDING = "DECISION_PENDING"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    WAITLISTED = "WAITLISTED"
    ENROLLED = "ENROLLED"
    WITHDRAWN = "WITHDRAWN"

    STATUS_CHOICES = [
        (DRAFT, "Draft"), (SUBMITTED, "Submitted"), (UNDER_REVIEW, "Under Review"),
        (SHORTLISTED, "Shortlisted"), (INTERVIEW, "Interview"), (DECISION_PENDING, "Decision Pending"),
        (ACCEPTED, "Accepted"), (REJECTED, "Rejected"), (WAITLISTED, "Waitlisted"),
        (ENROLLED, "Enrolled"), (WITHDRAWN, "Withdrawn"),
    ]

    applicant = models.ForeignKey(Applicant, on_delete=models.CASCADE, related_name="applications")
    academic_year = models.ForeignKey("schools.AcademicYear", on_delete=models.PROTECT, related_name="applications")
    grade_level = models.ForeignKey("schools.GradeLevel", on_delete=models.PROTECT, related_name="applications")
    term = models.ForeignKey("schools.Term", on_delete=models.SET_NULL, null=True, blank=True, related_name="applications")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=DRAFT, db_index=True)
    application_number = models.CharField(max_length=40, db_index=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_comment = models.TextField(blank=True, default="")
    notes = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["school", "application_number"], name="uq_application_number_school")]

    def __str__(self):
        return self.application_number


class ApplicationDocument(UUIDPKMixin, TimeStampedModel, SchoolScopedModel):
    class DocumentType(models.TextChoices):
        BIRTH_CERTIFICATE = "BIRTH_CERTIFICATE", "Birth Certificate"
        REPORT_CARD = "REPORT_CARD", "Report Card"
        ID_PASSPORT = "ID_PASSPORT", "ID/Passport"
        TRANSFER_LETTER = "TRANSFER_LETTER", "Transfer Letter"
        OTHER = "OTHER", "Other"

    application = models.ForeignKey(AdmissionApplication, on_delete=models.CASCADE, related_name="documents")
    file = models.ForeignKey("files.FileUpload", on_delete=models.PROTECT, related_name="application_documents")
    document_type = models.CharField(max_length=20, choices=DocumentType.choices, default=DocumentType.OTHER)
    is_verified = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.application_id}:{self.document_type}"


class ApplicationStatusHistory(UUIDPKMixin, TimeStampedModel, SchoolScopedModel):
    application = models.ForeignKey(AdmissionApplication, on_delete=models.CASCADE, related_name="status_history")
    from_status = models.CharField(max_length=20, blank=True, default="")
    to_status = models.CharField(max_length=20)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="admission_status_changes"
    )
    comment = models.TextField(blank=True, default="")
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["changed_at"]

    def __str__(self):
        return f"{self.application_id}:{self.from_status}->{self.to_status}"