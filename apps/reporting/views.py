"""Reporting and dashboard API views."""
from django.http import HttpResponse
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.common.exceptions import ValidationFailedError
from apps.common.permissions import HasPermission
from apps.common.viewsets import SchoolScopedViewSet
from apps.reporting.services import (
    build_report,
    dashboard_announcements,
    dashboard_attendance,
    dashboard_finance,
    dashboard_hr,
    dashboard_overview,
    dashboard_performance,
    dashboard_students,
    render_report_pdf,
)


class ReportViewSet(SchoolScopedViewSet):
    queryset = []
    serializer_class = None
    permission_classes = [HasPermission]
    permission_code = "report.read"
    audit_module = "reporting"
    audit_entity_type = "Report"

    def get_queryset(self):
        return []

    def list(self, request, *args, **kwargs):
        return Response({"reports": list(REPORT_HELPERS.keys())})

    def _params(self):
        p = self.request.query_params
        return {
            "class_id": p.get("class_id"),
            "start_date": p.get("start_date"),
            "end_date": p.get("end_date"),
            "term_id": p.get("term_id"),
        }

    @action(detail=False, methods=["get"])
    def student_list(self, request):
        return Response(build_report(self.get_school(), "student_list", self._params()))

    @action(detail=False, methods=["get"])
    def class_roster(self, request):
        return Response(build_report(self.get_school(), "class_roster", self._params()))

    @action(detail=False, methods=["get"])
    def attendance_summary(self, request):
        return Response(build_report(self.get_school(), "attendance_summary", self._params()))

    @action(detail=False, methods=["get"])
    def fee_balance(self, request):
        return Response(build_report(self.get_school(), "fee_balance", self._params()))

    @action(detail=False, methods=["get"])
    def payment_ledger(self, request):
        return Response(build_report(self.get_school(), "payment_ledger", self._params()))

    @action(detail=False, methods=["get"])
    def performance(self, request):
        return Response(build_report(self.get_school(), "performance", self._params()))

    @action(detail=False, methods=["get"])
    def staff_roster(self, request):
        return Response(build_report(self.get_school(), "staff_roster", self._params()))

    @action(detail=False, methods=["get"])
    def parent_contacts(self, request):
        return Response(build_report(self.get_school(), "parent_contacts", self._params()))

    @action(detail=False, methods=["get"])
    def lead_pipeline(self, request):
        return Response(build_report(self.get_school(), "lead_pipeline", self._params()))

    @action(detail=False, methods=["get"])
    def event_attendance(self, request):
        return Response(build_report(self.get_school(), "event_attendance", self._params()))

    @action(detail=False, methods=["get"])
    def daily_attendance(self, request):
        return Response(build_report(self.get_school(), "daily_attendance", self._params()))

    @action(detail=False, methods=["get"], url_path="export")
    def export(self, request):
        report_type = request.query_params.get("report_type")
        if not report_type:
            raise ValidationFailedError("report_type is required.", code="REPORT_TYPE_REQUIRED")
        if not request.user.is_superuser:
            self.permission_code = "report.export"
            self.check_permission_code("report.export")
        report = build_report(self.get_school(), report_type, self._params())
        fmt = request.query_params.get("format", "csv")
        self._audit("report.export", self.request.user, new_value={"report": report_type, "format": fmt})
        if fmt == "pdf":
            pdf = render_report_pdf(f"{report_type.replace('_', ' ').title()} - SALA", report["columns"], report["rows"])
            response = HttpResponse(pdf, content_type="application/pdf")
            response["Content-Disposition"] = f'attachment; filename="{report_type}.pdf"'
            return response
        # CSV
        import io as _io
        import csv as _csv

        buffer = _io.StringIO()
        writer = _csv.writer(buffer)
        writer.writerow(report["columns"])
        for row in report["rows"]:
            writer.writerow(row)
        buffer.seek(0)
        response = HttpResponse(buffer.getvalue(), content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="{report_type}.csv"'
        return response


REPORT_HELPERS = {
    "student_list": "Active student directory",
    "class_roster": "Enrollment per class",
    "attendance_summary": "Per-student attendance stats",
    "fee_balance": "Outstanding fee balances",
    "payment_ledger": "All payments in range",
    "performance": "Subject results and averages",
    "staff_roster": "Employee list by department",
    "parent_contacts": "Parent contact directory",
    "lead_pipeline": "CRM leads by stage",
    "event_attendance": "Events with registrations",
    "daily_attendance": "Sessions per day",
}


class DashboardViewSet(SchoolScopedViewSet):
    queryset = []
    serializer_class = None
    permission_classes = [HasPermission]
    permission_code = "dashboard.read"
    audit_module = "reporting"
    audit_entity_type = "Dashboard"

    def get_queryset(self):
        return []

    def list(self, request, *args, **kwargs):
        return Response({"dashboards": ["overview", "students", "finance", "attendance", "performance", "hr", "announcements"]})

    def _school(self):
        school = self.get_school()
        if school is None:
            raise ValidationFailedError("A school context is required.", code="NO_SCHOOL_CONTEXT", status_code=403)
        return school

    @action(detail=False, methods=["get"])
    def overview(self, request):
        return Response(dashboard_overview(self._school()))

    @action(detail=False, methods=["get"])
    def students(self, request):
        return Response(dashboard_students(self._school()))

    @action(detail=False, methods=["get"])
    def finance(self, request):
        return Response(dashboard_finance(self._school()))

    @action(detail=False, methods=["get"])
    def attendance(self, request):
        return Response(dashboard_attendance(self._school()))

    @action(detail=False, methods=["get"])
    def performance(self, request):
        return Response(dashboard_performance(self._school()))

    @action(detail=False, methods=["get"])
    def hr(self, request):
        return Response(dashboard_hr(self._school()))

    @action(detail=False, methods=["get"])
    def announcements(self, request):
        return Response(dashboard_announcements(self._school(), request.user))