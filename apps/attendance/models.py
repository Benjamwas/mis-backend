"""Attendance: classroom sessions/records and staff clock-in/out."""
from django.conf import settings
from django.db import models

from apps.common.models import SchoolScopedModel, TimeStampedModel, UUIDPKMixin


class AttendanceStatus(models.TextChoices):
    PRESENT = "PRESENT", "Present"
    ABSENT = "ABSENT", "Absent"
    LATE = "LATE", "Late"
    EXCUSED = "EXCUSED", "Excused"


# --------------------------------------------------------------------------
# Student attendance
# --------------------------------------------------------------------------
class AttendanceSession(UUIDPKMixin, TimeStampedModel, SchoolScopedModel):
    school_class = models.ForeignKey("schools.SchoolClass", on_delete=models.CASCADE, related_name="attendance_sessions")
    term = models.ForeignKey("schools.Term", on_delete=models.CASCADE, related_name="attendance_sessions")
    attendance_date = models.DateField(db_index=True)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="attendance_sessions")
    remarks = models.TextField(blank=True, default="")
    status = models.CharField(max_length=12, default="OPEN", db_index=True, choices=(
        ("OPEN", "Open"), ("CLOSED", "Closed"),
    ))

    class Meta:
        ordering = ["-attendance_date"]
        constraints = [
            models.UniqueConstraint(fields=["school_class", "attendance_date"], name="uq_attendance_session_day"),
        ]

    def __str__(self):
        return f"{self.school_class_id} {self.attendance_date}"


class StudentAttendance(UUIDPKMixin, TimeStampedModel, SchoolScopedModel):
    session = models.ForeignKey(AttendanceSession, on_delete=models.CASCADE, related_name="records")
    student = models.ForeignKey("people.Student", on_delete=models.CASCADE, related_name="attendance")
    status = models.CharField(max_length=10, choices=AttendanceStatus.choices, default=AttendanceStatus.PRESENT)
    remarks = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        ordering = ["-session__attendance_date"]
        constraints = [
            models.UniqueConstraint(fields=["session", "student"], name="uq_student_session"),
        ]
        indexes = [models.Index(fields=["student", "session"], name="idx_student_attendance")]


# --------------------------------------------------------------------------
# Staff attendance
# --------------------------------------------------------------------------
class EmployeeAttendance(UUIDPKMixin, TimeStampedModel, SchoolScopedModel):
    employee = models.ForeignKey("hr.Employee", on_delete=models.CASCADE, related_name="attendance")
    attendance_date = models.DateField(db_index=True)
    clock_in = models.DateTimeField(null=True, blank=True)
    clock_out = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=12, default="PRESENT", db_index=True, choices=(
        ("PRESENT", "Present"), ("ABSENT", "Absent"), ("LATE", "Late"), ("ON_LEAVE", "On Leave"),
    ))
    remarks = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        ordering = ["-attendance_date"]
        constraints = [
            models.UniqueConstraint(fields=["employee", "attendance_date"], name="uq_employee_attendance_day"),
        ]