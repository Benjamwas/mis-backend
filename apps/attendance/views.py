"""Attendance views."""
from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.attendance.models import AttendanceSession, EmployeeAttendance, StudentAttendance
from apps.attendance.serializers import (
    AttendanceSessionSerializer,
    EmployeeAttendanceSerializer,
    StudentAttendanceSerializer,
)
from apps.attendance.services import (
    class_attendance_summary,
    create_session,
    employee_clock_in,
    employee_clock_out,
    record_attendance,
    student_attendance_summary,
)
from apps.common.exceptions import ValidationFailedError
from apps.common.permissions import HasPermission
from apps.common.viewsets import SchoolScopedViewSet
from apps.people.models import Student
from apps.schools.models import SchoolClass, Term


class AttendanceSessionViewSet(SchoolScopedViewSet):
    queryset = AttendanceSession.objects.all()
    serializer_class = AttendanceSessionSerializer
    permission_classes = [HasPermission]
    permission_code = "attendance.read"
    audit_module = "attendance"
    audit_entity_type = "AttendanceSession"
    filterset_fields = ["school_class", "term", "attendance_date"]

    def get_queryset(self):
        qs = super().get_queryset().select_related("school_class", "term")
        from apps.people.services import parent_for_user
        parent = parent_for_user(self.request.user, self.get_school())
        if parent is not None:
            qs = qs.filter(records__student_id__in=parent.children.values_list("student_id", flat=True)).distinct()
        return qs

    def get_permissions(self):
        if self.action in ("create", "records"):
            self.permission_code = "attendance.record"
        elif self.action in ("update", "partial_update"):
            self.permission_code = "attendance.update"
        return super().get_permissions()

    def create(self, request, *args, **kwargs):
        school = self.get_school()
        school_class = get_object_or_404(SchoolClass.objects.filter(school=school), pk=request.data.get("school_class_id"))
        term = get_object_or_404(Term.objects.filter(school=school), pk=request.data.get("term_id"))
        session = create_session(
            school=school,
            school_class=school_class,
            term=term,
            attendance_date=request.data.get("attendance_date"),
            recorded_by=request.user,
            remarks=request.data.get("remarks", ""),
        )
        self._audit("attendance.session_create", session, new_value={"date": session.attendance_date.isoformat()})
        return Response(AttendanceSessionSerializer(session).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], permission_classes=[HasPermission])
    def records(self, request, pk=None):
        session = self.get_object()
        record_items = []
        for item in request.data.get("records", []):
            student = get_object_or_404(Student.objects.filter(school=session.school_id), pk=item.get("student_id"))
            record_items.append({"student": student, "status": item.get("status", "PRESENT"), "remarks": item.get("remarks", "")})
        if not record_items:
            raise ValidationFailedError("records list is required.", code="RECORDS_REQUIRED")
        recs = record_attendance(session, record_items, request.user)
        # prefill: absent students in the class get ABSENT rows
        present_ids = {r.student_id for r in recs}
        enrolled = session.school_class.enrollments.filter(status="ACTIVE").select_related("student")
        created = []
        for en in enrolled:
            if en.student_id not in present_ids:
                rec, _ = StudentAttendance.objects.get_or_create(
                    session=session, student=en.student, defaults={"school": session.school, "status": "ABSENT"},
                )
                created.append(rec)
        self._audit("attendance.record", session, new_value={"count": len(recs) + len(created)})
        return Response(AttendanceSessionSerializer(session).data)

    @action(detail=True, methods=["get"], permission_classes=[HasPermission])
    def records_list(self, request, pk=None):
        session = self.get_object()
        recs = session.records.select_related("student__person").order_by("student__person__first_name")
        return Response(StudentAttendanceSerializer(recs, many=True).data)


class EmployeeAttendanceViewSet(SchoolScopedViewSet):
    queryset = EmployeeAttendance.objects.all()
    serializer_class = EmployeeAttendanceSerializer
    permission_classes = [HasPermission]
    permission_code = "attendance.read"
    audit_module = "hr"
    audit_entity_type = "EmployeeAttendance"
    filterset_fields = ["employee", "attendance_date"]

    def _get_employee(self, user):
        school = self.get_school()
        emp = user.person.hr_employees.filter(school=school).first() if school else None
        if not emp:
            raise ValidationFailedError("No employee profile linked to your account.", code="NO_EMPLOYEE_PROFILE", status_code=404)
        return emp

    @action(detail=False, methods=["post"], permission_classes=[HasPermission])
    def clock_in(self, request):
        employee = self._get_employee(request.user)
        rec = employee_clock_in(employee)
        self._audit("attendance.clock_in", rec, new_value={"date": rec.attendance_date.isoformat()})
        return Response(EmployeeAttendanceSerializer(rec).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["post"], permission_classes=[HasPermission])
    def clock_out(self, request):
        employee = self._get_employee(request.user)
        rec = employee_clock_out(employee)
        self._audit("attendance.clock_out", rec, new_value={"date": rec.attendance_date.isoformat()})
        return Response(EmployeeAttendanceSerializer(rec).data)

    @action(detail=False, methods=["get"], permission_classes=[HasPermission])
    def me(self, request):
        employee = self._get_employee(request.user)
        recs = employee.attendance.all().order_by("-attendance_date")
        return Response(EmployeeAttendanceSerializer(recs, many=True).data)

    def get_permissions(self):
        if self.action not in ("clock_in", "clock_out", "me"):
            from apps.identity.services import user_has_permission

            school = self.get_school()
            if not user_has_permission(self.request.user, "attendance.record", school_id=school.id if school else None):
                self.permission_code = "attendance.read"
        return super().get_permissions()
