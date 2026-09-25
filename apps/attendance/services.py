"""Attendance business services."""
from django.utils import timezone

from apps.common.exceptions import ConflictError, ValidationFailedError


def create_session(school, school_class, term, attendance_date, recorded_by, remarks=""):
    """Create a class attendance session for a date; duplicate days rejected."""
    from apps.attendance.models import AttendanceSession

    if AttendanceSession.objects.filter(school=school, school_class=school_class, attendance_date=attendance_date).exists():
        raise ConflictError("An attendance session already exists for this class on this date.", code="SESSION_EXISTS")
    if school_class.school_id != school.id:
        raise ConflictError("Class belongs to a different school.", code="TENANT_ISOLATION")
    return AttendanceSession.objects.create(
        school=school, school_class=school_class, term=term,
        attendance_date=attendance_date, recorded_by=recorded_by, remarks=remarks,
    )


def record_attendance(session, records, recorded_by):
    """Bulk-upsert attendance records for a session. Duplicate prevention via constraint."""
    from apps.attendance.models import StudentAttendance

    created = []
    for item in records:
        student = item["student"]
        if student.school_id != session.school_id:
            raise ConflictError("Student belongs to a different school.", code="TENANT_ISOLATION")
        rec, _ = StudentAttendance.objects.update_or_create(
            session=session,
            student=student,
            defaults={"status": item.get("status", "PRESENT"), "remarks": item.get("remarks", "")},
        )
        created.append(rec)
    return created


def student_attendance_summary(student, start=None, end=None):
    """Attendance summary for a student over a range."""
    from apps.attendance.models import StudentAttendance
    from django.db.models import Count

    qs = StudentAttendance.objects.filter(student=student)
    if start:
        qs = qs.filter(session__attendance_date__gte=start)
    if end:
        qs = qs.filter(session__attendance_date__lte=end)
    totals = {}
    for row in qs.values("status").annotate(total=Count("id")):
        totals[row["status"]] = row["total"]
    totals["total"] = sum(totals.values())
    return totals


def class_attendance_summary(school_class, start=None, end=None):
    """Attendance overview for an entire class."""
    from apps.attendance.models import StudentAttendance
    from django.db.models import Count, Q

    qs = StudentAttendance.objects.filter(session__school_class=school_class)
    if start:
        qs = qs.filter(session__attendance_date__gte=start)
    if end:
        qs = qs.filter(session__attendance_date__lte=end)
    rows = list(
        qs.values("student_id", "student__person__first_name", "student__person__last_name")
        .annotate(
            present=Count("id", filter=Q(status="PRESENT")),
            absent=Count("id", filter=Q(status="ABSENT")),
            late=Count("id", filter=Q(status="LATE")),
            excused=Count("id", filter=Q(status="EXCUSED")),
        )
    )
    for r in rows:
        r["name"] = f"{r['student__person__first_name']} {r['student__person__last_name']}"
        r["total"] = r["present"] + r["absent"] + r["late"] + r["excused"]
    return rows


def employee_clock_in(employee, at=None):
    """Clock in an employee; reject an active (open) session for the same employee."""
    from apps.attendance.models import EmployeeAttendance

    at = at or timezone.now()
    today = at.date()
    rec, created = EmployeeAttendance.objects.get_or_create(
        employee=employee,
        attendance_date=today,
        defaults={"school": employee.school, "clock_in": at, "status": "PRESENT"},
    )
    if not created and rec.clock_in and rec.clock_out is None:
        raise ConflictError("Employee already has an active clock-in.", code="ALREADY_CLOCKED_IN")
    if not created and rec.clock_in:
        raise ConflictError("Employee already clocked in today.", code="ALREADY_CLOCKED_IN")
    return rec


def employee_clock_out(employee, at=None):
    from apps.attendance.models import EmployeeAttendance

    at = at or timezone.now()
    today = at.date()
    rec = EmployeeAttendance.objects.filter(employee=employee, attendance_date=today).first()
    if not rec or rec.clock_in is None:
        raise ValidationFailedError("No active clock-in for today.", code="NO_CLOCK_IN")
    if rec.clock_out is not None:
        raise ConflictError("Already clocked out for today.", code="ALREADY_CLOCKED_OUT")
    rec.clock_out = at
    rec.save(update_fields=["clock_out", "updated_at"])
    return rec