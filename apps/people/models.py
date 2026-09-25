"""Students, parents and parent-student relationships."""
from django.core.validators import RegexValidator
from django.db import models

from apps.common.models import SchoolScopedModel, SoftDeleteModel, TimeStampedModel, UUIDPKMixin


class Student(UUIDPKMixin, TimeStampedModel, SoftDeleteModel, SchoolScopedModel):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        ARCHIVED = "ARCHIVED", "Archived"
        TRANSFERRED = "TRANSFERRED", "Transferred"
        ALUMNI = "ALUMNI", "Alumni"

    person = models.ForeignKey("identity.Person", on_delete=models.PROTECT, related_name="students")
    admission_number = models.CharField(max_length=40, db_index=True)
    admission_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.ACTIVE, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["school", "admission_number"], name="uq_student_admission_number")
        ]

    @property
    def full_name(self):
        return self.person.full_name

    def __str__(self):
        return f"{self.admission_number} {self.full_name}"

    def archive(self, by=None):
        self.status = Student.Status.ARCHIVED
        self.is_active = False
        self.save(update_fields=["status", "is_active", "updated_at"])

    def restore(self):
        self.status = Student.Status.ACTIVE
        self.is_active = True
        self.is_deleted = False
        self.deleted_at = None
        self.save(update_fields=["status", "is_active", "is_deleted", "deleted_at", "updated_at"])


class Parent(UUIDPKMixin, TimeStampedModel, SoftDeleteModel, SchoolScopedModel):
    person = models.ForeignKey("identity.Person", on_delete=models.PROTECT, related_name="parents")
    occupation = models.CharField(max_length=160, blank=True, default="")
    employer = models.CharField(max_length=160, blank=True, default="")
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    @property
    def full_name(self):
        return self.person.full_name

    def __str__(self):
        return self.full_name


class RelationshipType(models.TextChoices):
    FATHER = "FATHER", "Father"
    MOTHER = "MOTHER", "Mother"
    GUARDIAN = "GUARDIAN", "Guardian"
    SIBLING = "SIBLING", "Sibling"
    OTHER = "OTHER", "Other"


class ParentStudent(UUIDPKMixin, TimeStampedModel):
    parent = models.ForeignKey(Parent, on_delete=models.CASCADE, related_name="children")
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="guardians")
    relationship_type = models.CharField(max_length=15, choices=RelationshipType.choices, default=RelationshipType.GUARDIAN)
    is_primary_contact = models.BooleanField(default=False)
    can_view_finance = models.BooleanField(default=True)
    can_view_academics = models.BooleanField(default=True)

    class Meta:
        ordering = ["-is_primary_contact", "created_at"]
        constraints = [
            models.UniqueConstraint(fields=["parent", "student"], name="uq_parent_student"),
        ]

    def __str__(self):
        return f"{self.parent_id} -> {self.student_id}"