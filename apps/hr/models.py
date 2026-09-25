"""Human Resources: departments, employees, teacher profiles, leave, payroll,
payslips, duties and HR tickets."""
from django.conf import settings
from django.db import models

from apps.common.models import SchoolScopedModel, SoftDeleteModel, TimeStampedModel, UUIDPKMixin


class EmploymentStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Active"
    ON_LEAVE = "ON_LEAVE", "On Leave"
    SUSPENDED = "SUSPENDED", "Suspended"
    TERMINATED = "TERMINATED", "Terminated"
    RESIGNED = "RESIGNED", "Resigned"


class Department(UUIDPKMixin, TimeStampedModel, SoftDeleteModel, SchoolScopedModel):
    name = models.CharField(max_length=160)
    description = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["school", "name"], name="uq_department_name_school")]

    def __str__(self):
        return self.name


class Employee(UUIDPKMixin, TimeStampedModel, SoftDeleteModel, SchoolScopedModel):
    person = models.ForeignKey("identity.Person", on_delete=models.PROTECT, related_name="hr_employees")
    employee_number = models.CharField(max_length=40, db_index=True)
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True, related_name="employees")
    employment_date = models.DateField(null=True, blank=True)
    employment_status = models.CharField(max_length=15, choices=EmploymentStatus.choices, default=EmploymentStatus.ACTIVE, db_index=True)
    role_title = models.CharField(max_length=160, blank=True, default="")
    base_salary = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["school", "employee_number"], name="uq_employee_number_school")]

    @property
    def full_name(self):
        return self.person.full_name

    @property
    def is_teacher(self):
        return self.teacher_profiles.exists()

    def __str__(self):
        return f"{self.employee_number} {self.full_name}"


class TeacherProfile(UUIDPKMixin, TimeStampedModel, SchoolScopedModel):
    class TeacherType(models.TextChoices):
        CLASS_TEACHER = "CLASS_TEACHER", "Class Teacher"
        SUBJECT_TEACHER = "SUBJECT_TEACHER", "Subject Teacher"
        SUPPORT = "SUPPORT", "Support"

    employee = models.OneToOneField(Employee, on_delete=models.CASCADE, related_name="teacher_profile")
    teacher_type = models.CharField(max_length=20, choices=TeacherType.choices, default=TeacherType.SUBJECT_TEACHER)
    qualification = models.CharField(max_length=255, blank=True, default="")
    specialization = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.employee_id}:{self.teacher_type}"


class LeaveType(UUIDPKMixin, TimeStampedModel, SchoolScopedModel):
    name = models.CharField(max_length=120)
    days_allowed = models.PositiveIntegerField(default=0)
    is_paid = models.BooleanField(default=True)
    description = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["school", "name"], name="uq_leave_type_name_school")]

    def __str__(self):
        return self.name


class LeaveRequest(UUIDPKMixin, TimeStampedModel, SchoolScopedModel):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"
        CANCELLED = "CANCELLED", "Cancelled"

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="leave_requests")
    leave_type = models.ForeignKey(LeaveType, on_delete=models.PROTECT, related_name="leave_requests")
    start_date = models.DateField()
    end_date = models.DateField()
    reason = models.TextField(blank=True, default="")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING, db_index=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="reviewed_leave_requests"
    )
    decision_comment = models.TextField(blank=True, default="")
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    @property
    def days(self):
        return (self.end_date - self.start_date).days + 1 if self.end_date and self.start_date else 0

    def __str__(self):
        return f"{self.employee_id}:{self.leave_type_id} ({self.status})"


class PayrollPeriod(UUIDPKMixin, TimeStampedModel, SchoolScopedModel):
    class Status(models.TextChoices):
        OPEN = "OPEN", "Open"
        PROCESSING = "PROCESSING", "Processing"
        COMPLETED = "COMPLETED", "Completed"
        CANCELLED = "CANCELLED", "Cancelled"

    name = models.CharField(max_length=120)
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.OPEN, db_index=True)
    payment_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["-start_date"]
        constraints = [models.UniqueConstraint(fields=["school", "name"], name="uq_payroll_period_name_school")]

    def __str__(self):
        return self.name


class Payslip(UUIDPKMixin, TimeStampedModel, SchoolScopedModel):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        PAID = "PAID", "Paid"
        CANCELLED = "CANCELLED", "Cancelled"

    payroll_period = models.ForeignKey(PayrollPeriod, on_delete=models.PROTECT, related_name="payslips")
    employee = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name="payslips")
    gross_salary = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_deductions = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    net_salary = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    payment_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT, db_index=True)
    pdf_url = models.URLField(blank=True, default="")

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["payroll_period", "employee"], name="uq_payslip_period_employee"),
        ]

    def __str__(self):
        return f"{self.employee_id}:{self.payroll_period_id}"


class PayslipItem(UUIDPKMixin, TimeStampedModel):
    class ItemType(models.TextChoices):
        EARNINGS = "EARNINGS", "Earnings"
        ALLOWANCE = "ALLOWANCE", "Allowance"
        DEDUCTION = "DEDUCTION", "Deduction"
        TAX = "TAX", "Tax"
        OTHER = "OTHER", "Other"

    payslip = models.ForeignKey(Payslip, on_delete=models.CASCADE, related_name="items")
    item_type = models.CharField(max_length=12, choices=ItemType.choices, default=ItemType.EARNINGS)
    description = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.payslip_id}:{self.description}"


class Duty(UUIDPKMixin, TimeStampedModel, SoftDeleteModel, SchoolScopedModel):
    name = models.CharField(max_length=160)
    location = models.CharField(max_length=160, blank=True, default="")
    description = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class DutyAssignment(UUIDPKMixin, TimeStampedModel, SchoolScopedModel):
    duty = models.ForeignKey(Duty, on_delete=models.CASCADE, related_name="assignments")
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="duty_assignments")
    date = models.DateField(db_index=True)
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    status = models.CharField(max_length=12, default="SCHEDULED", db_index=True, choices=(
        ("SCHEDULED", "Scheduled"), ("COMPLETED", "Completed"), ("CANCELLED", "Cancelled"),
    ))

    class Meta:
        ordering = ["date"]

    def __str__(self):
        return f"{self.duty_id} {self.employee_id} {self.date}"


class HrTicket(UUIDPKMixin, TimeStampedModel, SchoolScopedModel):
    class Status(models.TextChoices):
        OPEN = "OPEN", "Open"
        IN_PROGRESS = "IN_PROGRESS", "In Progress"
        AWAITING_RESPONSE = "AWAITING_RESPONSE", "Awaiting Response"
        RESOLVED = "RESOLVED", "Resolved"
        CLOSED = "CLOSED", "Closed"

    class Priority(models.TextChoices):
        LOW = "LOW", "Low"
        MEDIUM = "MEDIUM", "Medium"
        HIGH = "HIGH", "High"
        URGENT = "URGENT", "Urgent"

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="hr_tickets")
    category = models.CharField(max_length=120, default="GENERAL")
    subject = models.CharField(max_length=255)
    description = models.TextField()
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.MEDIUM)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN, db_index=True)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="assigned_hr_tickets"
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.subject


class HrTicketMessage(UUIDPKMixin, TimeStampedModel, SchoolScopedModel):
    ticket = models.ForeignKey(HrTicket, on_delete=models.CASCADE, related_name="messages")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="hr_ticket_messages")
    message = models.TextField()

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.ticket_id}:{self.user_id}"