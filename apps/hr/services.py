"""HR business services: leave, payroll and ticket processing."""
import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.common.exceptions import ConflictError, ValidationFailedError

logger = logging.getLogger("apps.hr")


def days_taken_in_period(employee, leave_type, start, end):
    from apps.hr.models import LeaveRequest

    qs = LeaveRequest.objects.filter(
        employee=employee, leave_type=leave_type, status__in=["APPROVED"]
    ).exclude(
        end_date__lt=start
    ).exclude(
        start_date__gt=end
    )
    total = 0
    for req in qs:
        total += req.days
    return total


def request_leave(employee, leave_type, start_date, end_date, reason="", by=None):
    """Request leave with overlap and entitlement validation."""
    from apps.hr.models import LeaveRequest

    if end_date < start_date:
        raise ValidationFailedError("End date cannot be before start date.", code="INVALID_DATE_RANGE")

    # overlap check on active requests
    overlapping = LeaveRequest.objects.filter(
        employee=employee, status__in=["PENDING", "APPROVED"]
    ).exclude(
        end_date__lt=start_date
    ).exclude(
        start_date__gt=end_date
    )
    if overlapping.exists():
        raise ConflictError("Leave request overlaps an existing request.", code="LEAVE_OVERLAP")

    taken = days_taken_in_period(employee, leave_type, leave_type_interval(leave_type))
    requested = (end_date - start_date).days + 1
    if leave_type.days_allowed and (taken + requested) > leave_type.days_allowed:
        raise ConflictError(
            f"Leave entitlement exceeded ({taken + requested} > {leave_type.days_allowed} days).",
            code="LEAVE_ENTITLEMENT_EXCEEDED",
        )

    return LeaveRequest.objects.create(
        employee=employee, leave_type=leave_type, start_date=start_date,
        end_date=end_date, reason=reason,
    )


def leave_type_interval(leave_type):
    from datetime import date

    try:
        return date(year=date.today().year, month=1, day=1)
    except ValueError:
        return date.today()


def approve_leave(request, reviewer, comment=""):
    from apps.hr.models import LeaveRequest

    if request.status != LeaveRequest.Status.PENDING:
        raise ConflictError("Only pending requests can be approved.", code="LEAVE_NOT_PENDING")
    request.status = LeaveRequest.Status.APPROVED
    request.reviewed_by = reviewer
    request.decision_comment = comment
    request.decided_at = timezone.now()
    request.save(update_fields=["status", "reviewed_by", "decision_comment", "decided_at", "updated_at"])
    return request


def reject_leave(request, reviewer, comment=""):
    from apps.hr.models import LeaveRequest

    if request.status != LeaveRequest.Status.PENDING:
        raise ConflictError("Only pending requests can be rejected.", code="LEAVE_NOT_PENDING")
    request.status = LeaveRequest.Status.REJECTED
    request.reviewed_by = reviewer
    request.decision_comment = comment
    request.decided_at = timezone.now()
    request.save(update_fields=["status", "reviewed_by", "decision_comment", "decided_at", "updated_at"])
    return request


@transaction.atomic
def run_payroll(payroll_period, employee_ids=None, by=None, base_overrides=None, deductions_overrides=None):
    """Generate payslips for employees in the period.

    Returns (payslips, report). Re-running is idempotent: existing payslips are
    refreshed for the same period/employee.
    """
    from apps.hr.models import Employee, Payslip, PayslipItem

    base_overrides = base_overrides or {}
    deductions_overrides = deductions_overrides or {}

    employees = Employee.objects.filter(school=payroll_period.school, employment_status="ACTIVE", is_active=True)
    if employee_ids:
        employees = employees.filter(id__in=employee_ids)

    results = []
    for emp in employees:
        base = base_overrides.get(str(emp.id), emp.base_salary)
        deductions = deductions_overrides.get(str(emp.id), {})

        payslip, _ = Payslip.objects.update_or_create(
            payroll_period=payroll_period,
            employee=emp,
            defaults={
                "gross_salary": base,
                "total_deductions": 0,
                "net_salary": 0,
                "status": Payslip.Status.DRAFT,
            },
        )
        payslip.items.all().delete()
        PayslipItem.objects.create(payslip=payslip, item_type="EARNINGS", description="Basic Salary", amount=base)

        total_deductions = 0
        for item_type, entries in deductions.items():
            for entry in entries or []:
                amount = entry.get("amount", 0)
                PayslipItem.objects.create(
                    payslip=payslip, item_type=item_type, description=entry.get("description", item_type), amount=amount
                )
                if item_type in ("DEDUCTION", "TAX", "OTHER"):
                    total_deductions += amount

        net = float(base) - float(total_deductions)
        payslip.total_deductions = total_deductions
        payslip.net_salary = max(net, 0)
        payslip.payment_date = payroll_period.payment_date
        payslip.save(update_fields=["total_deductions", "net_salary", "payment_date", "updated_at"])
        results.append(payslip)

    payroll_period.status = "PROCESSING"
    payroll_period.save(update_fields=["status", "updated_at"])
    return results


def finalize_payroll(payroll_period):
    from apps.hr.models import PayrollPeriod

    payroll_period.status = PayrollPeriod.Status.COMPLETED
    payroll_period.save(update_fields=["status", "updated_at"])
    return payroll_period


def generate_payslip_pdf(payslip):
    """Generate a PDF payslip; returns (url, exists). Real PDF via reportlab."""
    from apps.hr.services_pdf import render_payslip_pdf

    return render_payslip_pdf(payslip)


def employee_for_user(user, school):
    """The Employee profile for a portal user in a school, or None."""
    if not user or not user.person_id:
        return None
    return user.person.hr_employees.filter(school=school).first()


def resolve_employee_for_user(user, school):
    emp = employee_for_user(user, school)
    if not emp:
        raise ValidationFailedError("No employee profile is linked to your account.", code="NO_EMPLOYEE_PROFILE", status_code=404)
    return emp