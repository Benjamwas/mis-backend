"""HR API views."""
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from apps.common.permissions import HasPermission
from apps.common.viewsets import SchoolScopedViewSet
from apps.hr.models import (
    Department,
    Duty,
    DutyAssignment,
    Employee,
    HrTicket,
    HrTicketMessage,
    LeaveRequest,
    LeaveType,
    PayrollPeriod,
    Payslip,
)
from apps.hr.serializers import (
    DepartmentSerializer,
    DutyAssignmentSerializer,
    DutySerializer,
    EmployeeSerializer,
    HrTicketMessageSerializer,
    HrTicketSerializer,
    LeaveRequestSerializer,
    LeaveTypeSerializer,
    PayrollPeriodSerializer,
    PayslipSerializer,
)
from apps.hr.services import (
    approve_leave,
    finalize_payroll,
    generate_payslip_pdf,
    reject_leave,
    request_leave,
    resolve_employee_for_user,
    run_payroll,
)

HR_PERMISSION_MAP = {
    "employee": "employee.read",
    "department": "department.read",
    "leave": "leave.read",
    "payroll": "payroll.read",
    "payslip": "payslip.read",
    "duty": "duty.read",
    "ticket": "hrticket.read",
}


class DepartmentViewSet(SchoolScopedViewSet):
    queryset = Department.objects.all()
    serializer_class = DepartmentSerializer
    permission_classes = [HasPermission]
    permission_code = "department.read"
    audit_module = "hr"
    audit_entity_type = "Department"

    def get_permissions(self):
        if self.action in ("create", "update", "partial_update", "destroy"):
            self.permission_code = "department.create"
        return super().get_permissions()

    def perform_create(self, serializer):
        obj = serializer.save()
        self._audit("department.create", obj, new_value={"name": obj.name})


class EmployeeViewSet(SchoolScopedViewSet):
    queryset = Employee.objects.select_related("person", "department").all()
    serializer_class = EmployeeSerializer
    permission_classes = [HasPermission]
    permission_code = "employee.read"
    audit_module = "hr"
    audit_entity_type = "Employee"
    search_fields = ["employee_number", "person__first_name", "person__last_name", "person__email"]
    filterset_fields = ["department", "employment_status"]

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["school"] = self.get_school()
        return ctx

    def get_permissions(self):
        if self.action in ("create", "update", "partial_update", "destroy"):
            self.permission_code = "employee.manage"
        elif self.action == "me":
            self.permission_code = "employee.read"
        return super().get_permissions()

    def perform_create(self, serializer):
        obj = serializer.save()
        self._audit("employee.create", obj, new_value={"employee_number": obj.employee_number})

    def perform_update(self, serializer):
        obj = serializer.save()
        self._audit("employee.update", obj, new_value={"employee_number": obj.employee_number})

    def perform_destroy(self, instance):
        self._audit("employee.archive", instance, old_value={"status": instance.employment_status})
        instance.delete()

    @action(detail=False, methods=["get"])
    def me(self, request):
        school = self.get_school()
        emp = resolve_employee_for_user(request.user, school) if school else None
        if not emp:
            return Response(None)
        return Response(EmployeeSerializer(emp).data)

    @action(detail=True, methods=["get"])
    def leave(self, request, pk=None):
        emp = self.get_object()
        reqs = emp.leave_requests.all().order_by("-created_at")
        return Response(LeaveRequestSerializer(reqs, many=True).data)


class LeaveTypeViewSet(SchoolScopedViewSet):
    queryset = LeaveType.objects.all()
    serializer_class = LeaveTypeSerializer
    permission_classes = [HasPermission]
    permission_code = "leave.read"
    audit_module = "hr"
    audit_entity_type = "LeaveType"

    def get_permissions(self):
        if self.action in ("create", "update", "partial_update", "destroy"):
            self.permission_code = "leave.request"
        return super().get_permissions()


class LeaveRequestViewSet(SchoolScopedViewSet):
    queryset = LeaveRequest.objects.select_related("employee__person", "leave_type").all()
    serializer_class = LeaveRequestSerializer
    permission_classes = [HasPermission]
    permission_code = "leave.read"
    audit_module = "hr"
    audit_entity_type = "LeaveRequest"
    filterset_fields = ["employee", "leave_type", "status"]

    def get_queryset(self):
        qs = super().get_queryset()
        employee_id = self.request.query_params.get("employee")
        if employee_id:
            qs = qs.filter(employee_id=employee_id)
        return qs

    def get_permissions(self):
        if self.action == "create":
            self.permission_code = "leave.request"
        elif self.action in ("approve", "reject"):
            self.permission_code = "leave.approve"
        return super().get_permissions()

    def create(self, request, *args, **kwargs):
        school = self.get_school()
        emp = resolve_employee_for_user(request.user, school) if request.data.get("employee_id") is None else None
        employee = get_object_or_404(Employee.objects.filter(school=school), pk=request.data.get("employee_id")) if request.data.get("employee_id") else emp
        leave_type = get_object_or_404(LeaveType.objects.filter(school=school), pk=request.data.get("leave_type_id"))
        req = request_leave(
            employee, leave_type,
            request.data.get("start_date"), request.data.get("end_date"),
            reason=request.data.get("reason", ""), by=request.user,
        )
        self._audit("leave.request", req, new_value={"start": req.start_date.isoformat(), "end": req.end_date.isoformat()})
        return Response(LeaveRequestSerializer(req).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["get"])
    def me(self, request):
        school = self.get_school()
        emp = resolve_employee_for_user(request.user, school) if school else None
        if not emp:
            return Response([])
        reqs = emp.leave_requests.order_by("-created_at")
        return Response(LeaveRequestSerializer(reqs, many=True).data)

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        obj = self.get_object()
        approved = approve_leave(obj, request.user, request.data.get("comment", ""))
        self._audit("leave.approve", obj, old_value={"status": "PENDING"}, new_value={"status": obj.status})
        from apps.communication.tasks import send_transactional_email_job

        send_transactional_email_job.delay(
            to_email=obj.employee.person.email or obj.employee.person.phone,
            subject="Leave Approved",
            template="leave_approved",
            context={"name": obj.employee.full_name, "leave_type": obj.leave_type.name, "dates": f"{obj.start_date} to {obj.end_date}"},
        )
        return Response(LeaveRequestSerializer(approved).data)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        obj = self.get_object()
        rejected = reject_leave(obj, request.user, request.data.get("comment", ""))
        self._audit("leave.reject", obj, old_value={"status": "PENDING"}, new_value={"status": obj.status})
        from apps.communication.tasks import send_transactional_email_job

        send_transactional_email_job.delay(
            to_email=obj.employee.person.email or obj.employee.person.phone,
            subject="Leave Request Update",
            template="leave_rejected",
            context={"name": obj.employee.full_name, "leave_type": obj.leave_type.name},
        )
        return Response(LeaveRequestSerializer(rejected).data)


class PayrollPeriodViewSet(SchoolScopedViewSet):
    queryset = PayrollPeriod.objects.all()
    serializer_class = PayrollPeriodSerializer
    permission_classes = [HasPermission]
    permission_code = "payroll.read"
    audit_module = "hr"
    audit_entity_type = "PayrollPeriod"

    def get_permissions(self):
        if self.action in ("create", "update", "partial_update", "destroy", "run"):
            self.permission_code = "payroll.manage"
        return super().get_permissions()

    def get_queryset(self):
        return super().get_queryset().select_related("school").prefetch_related("payslips")

    @action(detail=True, methods=["post"])
    def run(self, request, pk=None):
        from apps.hr.models import Payslip
        from apps.hr.services import run_payroll

        period = self.get_object()
        employee_ids = request.data.get("employee_ids") or None
        base_overrides = {
            str(e["employee_id"]): e["base_salary"] for e in request.data.get("base_overrides", [])
        } or None
        deductions = request.data.get("deductions", {}) or {}

        payslips = run_payroll(
            period, employee_ids=employee_ids,
            base_overrides=base_overrides or {}, deductions_overrides=deductions, by=request.user,
        )
        self._audit("payroll.run", period, new_value={"count": len(payslips)})
        return Response(PayslipSerializer(payslips, many=True).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def finalize(self, request, pk=None):
        from apps.hr.services import finalize_payroll

        period = self.get_object()
        finalize_payroll(period)
        self._audit("payroll.finalize", period, old_value={"status": "PROCESSING"}, new_value={"status": period.status})
        return Response(PayrollPeriodSerializer(period).data)


class PayslipViewSet(SchoolScopedViewSet):
    queryset = Payslip.objects.select_related("employee__person", "payroll_period").prefetch_related("items").all()
    serializer_class = PayslipSerializer
    permission_classes = [HasPermission]
    permission_code = "payslip.read"
    audit_module = "hr"
    audit_entity_type = "Payslip"
    filterset_fields = ["employee", "payroll_period", "status"]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        school = self.get_school()
        if hasattr(user, "person") and not user.is_superuser:
            from apps.identity.services import user_has_permission

            if school and not user_has_permission(user, "payroll.read", school_id=school.id):
                emp = resolve_employee_for_user(user, school)
                if emp:
                    qs = qs.filter(employee=emp)
                else:
                    qs = qs.none()
        period = self.request.query_params.get("payroll_period")
        if period:
            qs = qs.filter(payroll_period_id=period)
        return qs

    def get_permissions(self):
        if self.action == "generate_pdf":
            self.permission_code = "payslip.read"
        return super().get_permissions()

    @action(detail=True, methods=["post"])
    def generate_pdf(self, request, pk=None):
        obj = self.get_object()
        url, _ = generate_payslip_pdf(obj)
        self._audit("payslip.pdf_generate", obj, new_value={"pdf_url": url})
        return Response({"pdf_url": url})


class PayrollRunViewsetAction:
    """Attached to PayrollPeriodViewSet below via method; kept for clarity."""


class DutyViewSet(SchoolScopedViewSet):
    queryset = Duty.objects.all()
    serializer_class = DutySerializer
    permission_classes = [HasPermission]
    permission_code = "duty.read"
    audit_module = "hr"
    audit_entity_type = "Duty"

    def get_permissions(self):
        if self.action in ("create", "update", "partial_update", "destroy"):
            self.permission_code = "duty.manage"
        return super().get_permissions()

    def get_queryset(self):
        return super().get_queryset().prefetch_related("assignments")


class DutyAssignmentViewSet(SchoolScopedViewSet):
    queryset = DutyAssignment.objects.select_related("duty", "employee__person").all()
    serializer_class = DutyAssignmentSerializer
    permission_classes = [HasPermission]
    permission_code = "duty.read"
    audit_module = "hr"
    audit_entity_type = "DutyAssignment"
    filterset_fields = ["employee", "duty", "date", "status"]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        school = self.get_school()
        if hasattr(user, "person") and not user.is_superuser:
            from apps.identity.services import user_has_permission

            if school and not user_has_permission(user, "duty.manage", school_id=school.id):
                emp = resolve_employee_for_user(user, school)
                if emp:
                    qs = qs.filter(employee=emp)
                else:
                    qs = qs.none()
        return qs

    def get_permissions(self):
        if self.action in ("create", "update", "partial_update", "destroy"):
            self.permission_code = "duty.manage"
        return super().get_permissions()

    def perform_create(self, serializer):
        obj = serializer.save()
        self._audit("duty.assign", obj, new_value={"duty": str(obj.duty_id), "employee": str(obj.employee_id), "date": obj.date.isoformat()})


class HrTicketViewSet(SchoolScopedViewSet):
    queryset = HrTicket.objects.select_related("employee__person").all()
    serializer_class = HrTicketSerializer
    permission_classes = [HasPermission]
    permission_code = "hrticket.read"
    audit_module = "hr"
    audit_entity_type = "HrTicket"
    filterset_fields = ["status", "priority", "category"]

    def get_queryset(self):
        qs = super().get_queryset()
        employee_id = self.request.query_params.get("employee")
        if employee_id:
            qs = qs.filter(employee_id=employee_id)
        return qs

    def get_permissions(self):
        if self.action == "create":
            self.permission_code = "hrticket.create"
        elif self.action in ("update", "partial_update", "close", "assign"):
            self.permission_code = "hrticket.update"
        return super().get_permissions()

    def create(self, request, *args, **kwargs):
        school = self.get_school()
        emp = resolve_employee_for_user(request.user, school)
        ticket = HrTicket.objects.create(
            school=school,
            employee=emp,
            category=request.data.get("category", "GENERAL"),
            subject=request.data.get("subject", ""),
            description=request.data.get("description", ""),
            priority=request.data.get("priority", "MEDIUM"),
        )
        self._audit("hrticket.create", ticket, new_value={"subject": ticket.subject})
        return Response(HrTicketSerializer(ticket).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def message(self, request, pk=None):
        ticket = self.get_object()
        msg = HrTicketMessage.objects.create(
            school=ticket.school, ticket=ticket, user=request.user, message=request.data.get("message", "")
        )
        if ticket.status == "AWAITING_RESPONSE":
            ticket.status = "IN_PROGRESS"
            ticket.save(update_fields=["status", "updated_at"])
        self._audit("hrticket.message", ticket, new_value={"message_id": str(msg.id)})
        return Response(HrTicketMessageSerializer(msg).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        ticket = self.get_object()
        ticket.status = "CLOSED"
        ticket.save(update_fields=["status", "updated_at"])
        self._audit("hrticket.close", ticket, old_value={"status": "OPEN"}, new_value={"status": "CLOSED"})
        return Response(HrTicketSerializer(ticket).data)

    @action(detail=True, methods=["post"])
    def assign(self, request, pk=None):
        ticket = self.get_object()
        ticket.assigned_to_id = request.data.get("assigned_to_id")
        ticket.status = "IN_PROGRESS"
        ticket.save(update_fields=["assigned_to", "status", "updated_at"])
        self._audit("hrticket.assign", ticket, new_value={"assigned_to": ticket.assigned_to_id})
        return Response(HrTicketSerializer(ticket).data)