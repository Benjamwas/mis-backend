"""Tenant (school) model, academic structure, modules & settings."""
import uuid

from django.db import models

from apps.common.models import SchoolScopedModel, SoftDeleteModel, TimeStampedModel, UUIDPKMixin


# --------------------------------------------------------------------------
# School
# --------------------------------------------------------------------------
class SchoolStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Active"
    TRIAL = "TRIAL", "Trial"
    SUSPENDED = "SUSPENDED", "Suspended"
    INACTIVE = "INACTIVE", "Inactive"


class School(UUIDPKMixin, TimeStampedModel):
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=20, unique=True, db_index=True)
    slug = models.SlugField(max_length=160, unique=True)
    email = models.EmailField(blank=True, default="")
    phone = models.CharField(max_length=30, blank=True, default="")
    address = models.CharField(max_length=255, blank=True, default="")
    logo_url = models.URLField(blank=True, default="")
    motto = models.CharField(max_length=255, blank=True, default="")
    status = models.CharField(max_length=15, choices=SchoolStatus.choices, default=SchoolStatus.TRIAL, db_index=True)

    def __str__(self):
        return self.name

    def active_year(self):
        return AcademicYear.objects.filter(school=self, status=AcademicYear.Status.ACTIVE).first()

    class Meta:
        ordering = ["name"]


# --------------------------------------------------------------------------
# Modules (platform-level catalogue + per-school toggle)
# --------------------------------------------------------------------------
class Module(UUIDPKMixin, TimeStampedModel):
    code = models.CharField(max_length=60, unique=True, db_index=True)
    name = models.CharField(max_length=160)
    description = models.TextField(blank=True, default="")
    is_core = models.BooleanField(default=False)

    def __str__(self):
        return self.code

    class Meta:
        ordering = ["code"]


class SchoolModule(UUIDPKMixin, TimeStampedModel):
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="modules", db_index=True)
    module = models.ForeignKey(Module, on_delete=models.CASCADE, related_name="school_modules")
    enabled = models.BooleanField(default=True)
    configuration = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["school", "module"], name="uq_school_module")]

    def __str__(self):
        return f"{self.school.code}:{self.module.code}={self.enabled}"


# --------------------------------------------------------------------------
# Academic structure
# --------------------------------------------------------------------------
class AcademicYear(UUIDPKMixin, TimeStampedModel, SoftDeleteModel, SchoolScopedModel):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        PREPARED = "PREPARED", "Prepared"
        CLOSED = "CLOSED", "Closed"

    name = models.CharField(max_length=120)
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PREPARED, db_index=True)

    class Meta:
        ordering = ["-start_date"]
        constraints = [models.UniqueConstraint(fields=["school", "name"], name="uq_year_name_school")]

    def __str__(self):
        return self.name


class Term(UUIDPKMixin, TimeStampedModel, SoftDeleteModel, SchoolScopedModel):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        UPCOMING = "UPCOMING", "Upcoming"
        CLOSED = "CLOSED", "Closed"

    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE, related_name="terms")
    name = models.CharField(max_length=80)
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.UPCOMING, db_index=True)

    class Meta:
        ordering = ["start_date"]
        constraints = [models.UniqueConstraint(fields=["academic_year", "name"], name="uq_term_name_year")]

    def __str__(self):
        return f"{self.academic_year.name} {self.name}"


class GradeLevel(UUIDPKMixin, TimeStampedModel, SoftDeleteModel, SchoolScopedModel):
    class Category(models.TextChoices):
        PRE_PRIMARY = "PRE_PRIMARY", "Pre-Primary"
        PRIMARY = "PRIMARY", "Primary"
        JUNIOR_SECONDARY = "JUNIOR_SECONDARY", "Junior Secondary"
        SENIOR_SECONDARY = "SENIOR_SECONDARY", "Senior Secondary"

    name = models.CharField(max_length=80)
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.PRIMARY)
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["display_order", "name"]
        constraints = [models.UniqueConstraint(fields=["school", "name"], name="uq_grade_name_school")]

    def __str__(self):
        return self.name


class SchoolClass(UUIDPKMixin, TimeStampedModel, SoftDeleteModel, SchoolScopedModel):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        ARCHIVED = "ARCHIVED", "Archived"

    academic_year = models.ForeignKey(AcademicYear, on_delete=models.PROTECT, related_name="classes")
    grade_level = models.ForeignKey(GradeLevel, on_delete=models.PROTECT, related_name="classes")
    name = models.CharField(max_length=80)
    section = models.CharField(max_length=20, blank=True, default="")
    class_teacher = models.ForeignKey(
        "hr.Employee", on_delete=models.SET_NULL, null=True, blank=True, related_name="class_teacher_of"
    )
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ACTIVE, db_index=True)

    @property
    def display_name(self):
        return f"{self.name}{' ' + self.section if self.section else ''}"

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["school", "academic_year", "grade_level", "name", "section"], name="uq_class_name_year")]

    def __str__(self):
        return self.display_name


class SchoolSettings(UUIDPKMixin, TimeStampedModel, SchoolScopedModel):
    """Key/value school settings. Only non-secret values."""

    key = models.CharField(max_length=80)
    value = models.JSONField(default=None, null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["school", "key"], name="uq_school_setting_key")]

    def __str__(self):
        return f"{self.school.code}:{self.key}"