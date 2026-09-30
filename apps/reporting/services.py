"""Reporting aggregations: computed reports and dashboard sums built from real ORM."""
import logging
import io
from datetime import date, timedelta

from django.db.models import Avg, Count, DecimalField, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.common.exceptions import ValidationFailedError

logger = logging.getLogger("apps.reporting")


def _student_rows(school):
    from apps.people.models import Student

    return Student.objects.filter(school=school).select_related("person").prefetch_related("enrollments__school_class__grade_level")


def build_report(school, report_type, params=None):
    builder = REPORT_BUILDERS.get(report_type)
    if builder is None:
        raise ValidationFailedError(f"Unknown report type: {report_type}", code="UNKNOWN_REPORT")
    return builder(school, params or {})


# --------------------------------------------------------------------------
# Builders
# --------------------------------------------------------------------------
def _student_list(school, params):
    qs = _student_rows(school)
    rows = []
    for s in qs.iterator(chunk_size=500):
        enrollment = s.enrollments.order_by("-created_at").first()
        rows.append({
            "admission_number": s.admission_number,
            "full_name": s.person.full_name,
            "class": enrollment.school_class.name if enrollment else "",
            "grade": enrollment.school_class.grade_level.name if enrollment and enrollment.school_class.grade_level_id else "",
            "status": s.status,
        })
    rows.sort(key=lambda r: (r["grade"], r["class"], r["full_name"]))
    return {
        "columns": ["Admission No", "Student Name", "Class", "Grade", "Status"],
        "rows": [[r["admission_number"], r["full_name"], r["class"], r["grade"], r["status"]] for r in rows],
        "summary": {"total_students": len(rows),
                    "active": sum(1 for r in rows if r["status"] == "ACTIVE")},
    }


def _class_roster(school, params):
    from apps.academics.models import Enrollment

    qs = Enrollment.objects.filter(
        school=school, status=Enrollment.Status.ACTIVE
    ).select_related("student__person", "school_class__grade_level")
    class_id = params.get("class_id")
    if class_id:
        qs = qs.filter(school_class_id=class_id)
    rows = []
    for e in qs.iterator(chunk_size=500):
        rows.append({
            "class": e.school_class.name,
            "grade": e.school_class.grade_level.name if e.school_class.grade_level_id else "",
            "name": e.student.person.full_name,
            "admission_number": e.student.admission_number,
        })
    rows.sort(key=lambda r: (r["class"], r["name"]))
    return {
        "columns": ["Class", "Grade", "Student Name", "Admission No"],
        "rows": [[r["class"], r["grade"], r["name"], r["admission_number"]] for r in rows],
        "summary": {"enrolled": len(rows)},
    }


def _attendance_summary(school, params):
    from apps.attendance.models import StudentAttendance

    qs = StudentAttendance.objects.filter(school=school).select_related(
        "student__person", "session__school_class__grade_level"
    )
    start = params.get("start_date")
    end = params.get("end_date")
    if start:
        qs = qs.filter(session__attendance_date__gte=start)
    if end:
        qs = qs.filter(session__attendance_date__lte=end)
    students = {}
    for rec in qs.iterator(chunk_size=500):
        key = str(rec.student_id)
        a = students.setdefault(key, {"name": rec.student.person.full_name,
                                      "class": rec.session.school_class.name if rec.session.school_class_id else "",
                                      "present": 0, "absent": 0, "late": 0, "excused": 0})
        a[rec.status.lower() if rec.status.lower() in ("present", "absent", "late", "excused") else "present"] += 1
    rows = list(students.values())
    rows.sort(key=lambda r: r["name"])
    total = sum(r["present"] + r["absent"] + r["late"] + r["excused"] for r in rows)
    return {
        "columns": ["Student", "Class", "Present", "Absent", "Late", "Excused", "Rate"],
        "rows": [[r["name"], r["class"], r["present"], r["absent"], r["late"], r["excused"],
                  f"{(r['present'] * 100 / (r['present'] + r['absent'] + r['late'] + r['excused'] or 1)):.1f}%"] for r in rows],
        "summary": {"total_records": total, "overall_rate": (sum(r["present"] for r in rows) * 100 / max(total, 1))},
    }


def _fee_balances(school, params):
    from apps.finance.models import StudentFeeAccount

    accounts = StudentFeeAccount.objects.filter(school=school).select_related("student__person")
    rows = []
    for acc in accounts:
        balance = (acc.balance if hasattr(acc, "balance") else 0)
        if balance <= 0:
            continue
        enrollment = acc.student.enrollments.order_by("-created_at").first()
        rows.append({
            "admission_number": acc.student.admission_number,
            "name": acc.student.full_name,
            "class": enrollment.school_class.name if enrollment else "",
            "balance": float(balance),
        })
    rows.sort(key=lambda r: r["balance"], reverse=True)
    return {
        "columns": ["Admission No", "Student", "Class", "Outstanding Balance"],
        "rows": [[r["admission_number"], r["name"], r["class"], f"{r['balance']:.2f}"] for r in rows],
        "summary": {"total_outstanding": sum(r["balance"] for r in rows), "defaulters": len(rows)},
    }


def _payment_ledger(school, params):
    from apps.finance.models import Payment

    qs = Payment.objects.filter(school=school).select_related("student__person")
    start = params.get("start_date")
    end = params.get("end_date")
    if start:
        qs = qs.filter(paid_at__date__gte=start)
    if end:
        qs = qs.filter(paid_at__date__lte=end)
    qs = qs.order_by("-paid_at")
    rows = []
    for p in qs.iterator(chunk_size=500):
        rows.append({
            "date": p.paid_at.date().isoformat() if p.paid_at else "",
            "student": p.student.person.full_name,
            "method": p.method,
            "status": p.status,
            "ref": p.transaction_ref,
            "amount": float(p.amount),
        })
    return {
        "columns": ["Date", "Student", "Method", "Status", "Ref", "Amount"],
        "rows": [[r["date"], r["student"], r["method"], r["status"], r["ref"], f"{r['amount']:.2f}"] for r in rows],
        "summary": {"total_amount": sum(r["amount"] for r in rows), "payments": len(rows)},
    }


def _performance(school, params):
    from apps.academics.models import StudentSubjectResult

    qs = StudentSubjectResult.objects.filter(school=school).select_related(
        "student__person", "subject", "term__academic_year"
    )
    term_id = params.get("term_id")
    if term_id:
        qs = qs.filter(term_id=term_id)
    rows = []
    for r in qs.iterator(chunk_size=500):
        rows.append({
            "student": r.student.full_name,
            "admission_number": r.student.admission_number,
            "subject": r.subject.name,
            "total_score": float(r.total_score),
            "grade": r.grade,
            "term": r.term.name if r.term_id else "",
        })
    rows.sort(key=lambda r: r["student"])
    scores = [r["total_score"] for r in rows]
    return {
        "columns": ["Student", "Admission No", "Subject", "Score", "Grade", "Term"],
        "rows": [[r["student"], r["admission_number"], r["subject"], r["total_score"], r["grade"], r["term"]] for r in rows],
        "summary": {"results": len(rows), "average": (sum(scores) / len(scores)) if scores else 0},
    }


def _staff_roster(school, params):
    from apps.hr.models import Employee

    qs = Employee.objects.filter(school=school).select_related("person", "department")
    rows = []
    for e in qs.iterator(chunk_size=500):
        rows.append({
            "employee_number": e.employee_number,
            "name": e.person.full_name,
            "department": e.department.name if e.department_id else "",
            "title": e.role_title,
            "status": e.employment_status,
        })
    rows.sort(key=lambda r: r["name"])
    return {
        "columns": ["Employee No", "Name", "Department", "Title", "Status"],
        "rows": [[r["employee_number"], r["name"], r["department"], r["title"], r["status"]] for r in rows],
        "summary": {"staff": len(rows)},
    }


def _parent_contacts(school, params):
    from apps.people.models import Parent

    qs = Parent.objects.filter(school=school).select_related("person").prefetch_related("children__student__person")
    rows = []
    for p in qs.iterator(chunk_size=500):
        students = ", ".join(c.student.full_name for c in p.children.all())
        rows.append({
            "name": p.full_name,
            "phone": p.person.phone,
            "email": p.person.email,
            "students": students,
        })
    rows.sort(key=lambda r: r["name"])
    return {
        "columns": ["Parent Name", "Phone", "Email", "Linked Students"],
        "rows": [[r["name"], r["phone"], r["email"], r["students"]] for r in rows],
        "summary": {"parents": len(rows)},
    }


def _lead_pipeline(school, params):
    from apps.crm.models import CrmLead

    counts = {s: CrmLead.objects.filter(school=school, status=s).count() for s, _ in CrmLead.Status.choices}
    rows = [{"status": s, "count": c} for s, c in counts.items()]
    return {
        "columns": ["Stage", "Count"],
        "rows": [[r["status"], r["count"]] for r in rows],
        "summary": {"total": sum(counts.values()), **counts},
    }


def _event_attendance(school, params):
    from apps.content.models import Event

    qs = Event.objects.filter(school=school).prefetch_related("participants").order_by("-start_time")
    rows = []
    for e in qs.iterator(chunk_size=500):
        confirmed = e.participants.exclude(status="CANCELLED").count()
        attended = e.participants.filter(status="ATTENDED").count()
        rows.append({
            "title": e.title,
            "date": e.start_time.date().isoformat(),
            "registered": confirmed,
            "attended": attended,
        })
    return {
        "columns": ["Event", "Date", "Registered", "Attended"],
        "rows": [[r["title"], r["date"], r["registered"], r["attended"]] for r in rows],
        "summary": {"events": len(rows)},
    }


def _daily_attendance(school, params):
    from apps.attendance.models import AttendanceSession

    qs = AttendanceSession.objects.filter(school=school).prefetch_related("records", "school_class").order_by("-attendance_date")
    rows = []
    for s in qs.iterator(chunk_size=500):
        total = s.records.count()
        present = s.records.filter(status="PRESENT").count()
        rows.append({
            "date": s.attendance_date.isoformat(),
            "class": s.school_class.name if s.school_class_id else "",
            "present": present,
            "total": total,
        })
    return {
        "columns": ["Date", "Class", "Present", "Total"],
        "rows": [[r["date"], r["class"], r["present"], r["total"]] for r in rows],
        "summary": {"days": len(rows), "avg_rate": (sum(r["present"] for r in rows) * 100 / max(sum(r["total"] for r in rows), 1))},
    }


REPORT_BUILDERS = {
    "student_list": _student_list,
    "class_roster": _class_roster,
    "attendance_summary": _attendance_summary,
    "fee_balance": _fee_balances,
    "payment_ledger": _payment_ledger,
    "performance": _performance,
    "staff_roster": _staff_roster,
    "parent_contacts": _parent_contacts,
    "lead_pipeline": _lead_pipeline,
    "event_attendance": _event_attendance,
    "daily_attendance": _daily_attendance,
}


# --------------------------------------------------------------------------
# Dashboard summaries
# --------------------------------------------------------------------------
def dashboard_overview(school):
    from apps.academics.models import Enrollment
    from apps.attendance.models import StudentAttendance
    from apps.content.models import Event
    from apps.crm.models import CrmLead
    from apps.hr.models import Employee, LeaveRequest
    from apps.people.models import Parent, Student
    from apps.schools.models import AcademicYear

    today = timezone.localdate()
    year = AcademicYear.objects.filter(school=school, status="OPEN").order_by("-start_date").first() or (
        AcademicYear.objects.filter(school=school).order_by("-start_date").first()
    )

    attendance = StudentAttendance.objects.filter(school=school)
    total_records = attendance.count()
    present_records = attendance.filter(status="PRESENT").count()

    return {
        "students": {
            "total": Student.objects.filter(school=school).count(),
            "active": Student.objects.filter(school=school, is_active=True).count(),
            "parents": Parent.objects.filter(school=school).count(),
        },
        "staff": {
            "teachers": Employee.objects.filter(school=school, teacher_profile__isnull=False).count(),
            "employees": Employee.objects.filter(school=school).count(),
        },
        "academics": {
            "active_enrollments": Enrollment.objects.filter(school=school, status="ACTIVE").count(),
            "current_year": year.name if year else "",
        },
        "attendance": {
            "records": total_records,
            "present": present_records,
            "rate": round(present_records * 100 / max(total_records, 1), 1),
        },
        "upcoming_events": Event.objects.filter(
            school=school, status="PUBLISHED", start_time__gte=timezone.now()
        ).count(),
        "pending_admissions": _status_count(school, "AdmissionApplication", "SUBMITTED"),
        "pending_leave": LeaveRequest.objects.filter(school=school, status="PENDING").count(),
        "new_leads": CrmLead.objects.filter(school=school, status="NEW").count(),
    }


def _status_count(school, model_name, status):
    from apps.admissions.models import AdmissionApplication

    return AdmissionApplication.objects.filter(school=school, status=status).count()


def dashboard_students(school):
    from apps.academics.models import Enrollment
    from apps.people.models import Student
    from apps.schools.models import GradeLevel

    thirty_days = timezone.now() - timedelta(days=30)
    grade_rows = []
    for g in GradeLevel.objects.filter(school=school).order_by("display_order"):
        grade_rows.append({"grade": g.name, "count": Enrollment.objects.filter(
            school=school, status="ACTIVE", school_class__grade_level=g).count()})

    return {
        "by_grade": grade_rows,
        "by_gender": list(
            Student.objects.filter(school=school).values("person__gender").annotate(count=Count("id"))
        ),
        "new_this_month": Student.objects.filter(school=school, created_at__gte=thirty_days).count(),
        "active": Student.objects.filter(school=school, is_active=True).count(),
        "archived": Student.objects.filter(school=school, status="ARCHIVED").count(),
    }


def dashboard_finance(school):
    from apps.finance.models import Invoice, Payment, StudentFeeAccount
    from apps.schools.models import AcademicYear

    year = AcademicYear.objects.filter(school=school).order_by("-start_date").first()
    invoiced = Invoice.objects.filter(school=school)
    if year:
        invoiced = invoiced.filter(issue_date__gte=year.start_date)
    total_invoiced = float(invoiced.aggregate(
        total=Coalesce(Sum("amount_due"), Value(0, output_field=DecimalField(max_digits=12, decimal_places=2)))
    )["total"])
    collected = float(Payment.objects.filter(school=school, status="SUCCESS").aggregate(
        total=Coalesce(Sum("amount"), Value(0, output_field=DecimalField(max_digits=12, decimal_places=2)))
    )["total"])
    outstanding_rows = _fee_balances(school, {})["rows"]
    return {
        "total_invoiced": round(total_invoiced, 2),
        "collected": round(collected, 2),
        "outstanding": round(total_invoiced - collected, 2),
        "overdue_invoices": Invoice.objects.filter(
            school=school, status__in=["SENT", "PARTIALLY_PAID"], due_date__lt=timezone.localdate()
        ).count(),
        "top_defaulters": outstanding_rows[:5],
    }


def dashboard_attendance(school):
    from apps.attendance.models import StudentAttendance

    today = timezone.localdate()
    last7 = [today - timedelta(days=i) for i in range(6, -1, -1)]
    trend = []
    for day in last7:
        recs = StudentAttendance.objects.filter(school=school, session__attendance_date=day)
        total = recs.count()
        present = recs.filter(status="PRESENT").count()
        trend.append({"date": day.isoformat(), "present": present, "total": total})

    class_rows = []
    for rec in StudentAttendance.objects.filter(school=school).select_related("session__school_class").values(
        "session__school_class__name"
    ).annotate(total=Count("id"), present=Count("id", filter=Q(status="PRESENT"))):
        class_rows.append({"class": rec["session__school_class__name"], "total": rec["total"], "present": rec["present"]})
    return {"weekly_trend": trend, "by_class": class_rows}


def dashboard_performance(school):
    from apps.academics.models import StudentSubjectResult
    from apps.schools.models import GradeLevel

    avg_score = StudentSubjectResult.objects.filter(school=school).aggregate(
        avg=Coalesce(Avg("total_score"), Value(0, output_field=DecimalField(max_digits=8, decimal_places=2)))
    )["avg"]
    top_rows = []
    results = StudentSubjectResult.objects.filter(school=school).select_related(
        "student__person", "term"
    ).order_by("-total_score")[:10]
    for r in results:
        top_rows.append({"name": r.student.full_name, "score": float(r.total_score), "grade": r.grade})
    return {
        "average_score": round(float(avg_score), 2),
        "results_count": StudentSubjectResult.objects.filter(school=school).count(),
        "top_students": top_rows,
        "grades_distribution": list(
            StudentSubjectResult.objects.filter(school=school).values("grade").annotate(count=Count("id"))
        ),
    }


def dashboard_hr(school):
    from apps.hr.models import DutyAssignment, Employee, HrTicket, LeaveRequest

    today = timezone.localdate()
    return {
        "by_department": list(
            Employee.objects.filter(school=school).values("department__name").annotate(count=Count("id"))
        ),
        "on_leave_today": LeaveRequest.objects.filter(
            school=school, status="APPROVED", start_date__lte=today, end_date__gte=today
        ).count(),
        "duties_today": DutyAssignment.objects.filter(school=school, date=today).count(),
        "pending_tickets": HrTicket.objects.filter(school=school, status="OPEN").count(),
    }


def dashboard_announcements(school, user):
    from apps.communication.models import Announcement, Notification

    return {
        "published_this_month": Announcement.objects.filter(
            school=school, status="PUBLISHED", published_at__year=timezone.now().year,
            published_at__month=timezone.now().month,
        ).count(),
        "unread": Notification.objects.filter(
            school=school, user=user, is_read=False
        ).count() if user else 0,
    }


def dashboard_student(school, user):
    """Return the signed-in learner's dashboard metrics and current work."""
    from apps.academics.models import Assignment, StudentSubjectResult
    from apps.attendance.models import StudentAttendance
    from apps.people.models import Student

    student = Student.objects.filter(school=school, person__users=user).select_related("person").first()
    if student is None:
        return {"student": None, "assignments": [], "subject_results": [], "attendance": {"present": 0, "absent": 0, "late": 0, "percentage": 0}}

    assignments = Assignment.objects.filter(
        school=school,
        teaching_assignment__school_class__enrollments__student=student,
        status="PUBLISHED",
    ).select_related("teaching_assignment__subject").distinct().order_by("due_date")[:20]
    assignment_rows = [
        {
            "id": str(item.id),
            "title": item.title,
            "subject": item.teaching_assignment.subject.name,
            "topic": item.topic,
            "due_date": item.due_date.isoformat() if item.due_date else None,
            "max_marks": item.max_marks,
            "status": item.status,
        }
        for item in assignments
    ]

    results = StudentSubjectResult.objects.filter(school=school, student=student).select_related("subject", "term").order_by("-created_at")[:30]
    result_rows = [
        {
            "subject": result.subject.name,
            "score": float(result.total_score),
            "grade": result.grade,
            "term": result.term.name if result.term_id else "",
        }
        for result in results
    ]
    attendance = StudentAttendance.objects.filter(school=school, student=student)
    present = attendance.filter(status="PRESENT").count()
    absent = attendance.filter(status="ABSENT").count()
    late = attendance.filter(status="LATE").count()
    total = present + absent + late + attendance.filter(status="EXCUSED").count()
    return {
        "student": {"id": str(student.id), "name": student.full_name, "admission_number": student.admission_number},
        "assignments": assignment_rows,
        "subject_results": result_rows,
        "attendance": {"present": present, "absent": absent, "late": late, "percentage": round(present * 100 / max(total, 1), 1)},
    }


# --------------------------------------------------------------------------
# PDF rendering
# --------------------------------------------------------------------------
def render_report_pdf(title, columns, rows):
    """Render a report to a PDF bytes buffer with reportlab."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import SimpleDocTemplate, Spacer, Table, TableStyle, Paragraph

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    story = [Paragraph(title, styles["Title"]), Spacer(1, 12)]
    data = [list(columns)] + [list(r) for r in rows]
    table = Table(data)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#16a34a")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
    ]))
    story.append(table)
    doc.build(story)
    return buffer.getvalue()
