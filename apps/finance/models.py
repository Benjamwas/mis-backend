"""Finance: fee structures, invoices, payments, allocations and receipts."""
from django.conf import settings
from django.db import models

from apps.common.models import SchoolScopedModel, TimeStampedModel, UUIDPKMixin


class FeeStructure(UUIDPKMixin, TimeStampedModel, SchoolScopedModel):
    class BillingCycle(models.TextChoices):
        TERM = "TERM", "Per Term"
        YEAR = "YEAR", "Per Year"
        MONTHLY = "MONTHLY", "Per Month"

    name = models.CharField(max_length=160)
    grade_level = models.ForeignKey(
        "schools.GradeLevel", on_delete=models.PROTECT, related_name="fee_structures", null=True, blank=True
    )
    billing_cycle = models.CharField(max_length=10, choices=BillingCycle.choices, default=BillingCycle.TERM)
    description = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["school", "name"], name="uq_fee_structure_name_school")]

    def __str__(self):
        return self.name


class FeeItem(UUIDPKMixin, TimeStampedModel, SchoolScopedModel):
    """A single line within a fee structure (e.g. Tuition, Lunch)."""

    fee_structure = models.ForeignKey(FeeStructure, on_delete=models.CASCADE, related_name="items")
    name = models.CharField(max_length=160)
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    is_mandatory = models.BooleanField(default=True)
    is_recurring = models.BooleanField(default=True)
    description = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["fee_structure", "name"], name="uq_fee_item_name_structure")]

    def __str__(self):
        return f"{self.fee_structure.name} - {self.name}"


class StudentFeeAccount(UUIDPKMixin, TimeStampedModel, SchoolScopedModel):
    student = models.OneToOneField("people.Student", on_delete=models.CASCADE, related_name="fee_account")
    fee_structure = models.ForeignKey(
        FeeStructure, on_delete=models.SET_NULL, null=True, blank=True, related_name="fee_accounts"
    )
    opening_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    credit_limit = models.DecimalField(max_digits=12, decimal_places=2, default=10000)
    is_blocked = models.BooleanField(default=False, db_index=True)
    remarks = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-created_at"]

    @property
    def balance(self):
        invoiced = self.student.invoices.aggregate(
            total=models.Sum("amount_due"), paid=models.Sum("amount_paid"), adjustments=models.Sum("adjustments")
        )
        b = (invoiced["total"] or 0) - (invoiced["paid"] or 0) + (invoiced["adjustments"] or 0)
        return round(b, 2)

    @property
    def outstanding(self):
        return max(self.balance, 0)

    def __str__(self):
        return f"{self.student_id}"


class Invoice(UUIDPKMixin, TimeStampedModel, SchoolScopedModel):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        SENT = "SENT", "Sent"
        PARTIALLY_PAID = "PARTIALLY_PAID", "Partially Paid"
        PAID = "PAID", "Paid"
        OVERDUE = "OVERDUE", "Overdue"
        CANCELLED = "CANCELLED", "Cancelled"

    class InvoiceType(models.TextChoices):
        TUITION = "TUITION", "Tuition"
        ACTIVITY = "ACTIVITY", "Activity"
        TRANSPORT = "TRANSPORT", "Transport"
        UNIFORM = "UNIFORM", "Uniform"
        MEDICAL = "MEDICAL", "Medical"
        OTHER = "OTHER", "Other"

    student = models.ForeignKey("people.Student", on_delete=models.PROTECT, related_name="invoices")
    invoice_number = models.CharField(max_length=40, db_index=True)
    invoice_type = models.CharField(max_length=12, choices=InvoiceType.choices, default=InvoiceType.TUITION)
    issue_date = models.DateField(db_index=True)
    due_date = models.DateField(db_index=True)
    amount_due = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    adjustments = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.SENT, db_index=True)
    term = models.ForeignKey("schools.Term", on_delete=models.SET_NULL, null=True, blank=True, related_name="invoices")
    description = models.TextField(blank=True, default="")
    payment_due_date = models.DateField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="invoices_created"
    )

    class Meta:
        ordering = ["-issue_date"]
        constraints = [models.UniqueConstraint(fields=["school", "invoice_number"], name="uq_invoice_number_school")]

    @property
    def balance(self):
        return round((self.amount_due - self.amount_paid) + self.adjustments, 2)

    def __str__(self):
        return self.invoice_number


class InvoiceItem(UUIDPKMixin, TimeStampedModel, SchoolScopedModel):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="items")
    description = models.CharField(max_length=255)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        self.amount = (self.quantity or 0) * (self.unit_price or 0)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.invoice_number if hasattr(self, 'invoice_number') else self.invoice_id}:{self.description}"


class Payment(UUIDPKMixin, TimeStampedModel, SchoolScopedModel):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        PROCESSING = "PROCESSING", "Processing"
        SUCCESS = "SUCCESS", "Success"
        FAILED = "FAILED", "Failed"
        CANCELLED = "CANCELLED", "Cancelled"
        REVERSED = "REVERSED", "Reversed"
        REFUNDED = "REFUNDED", "Refunded"

    class Method(models.TextChoices):
        MPESA = "MPESA", "M-Pesa"
        BANK = "BANK", "Bank Transfer"
        CASH = "CASH", "Cash"
        CARD = "CARD", "Card"
        OTHER = "OTHER", "Other"

    student = models.ForeignKey("people.Student", on_delete=models.PROTECT, related_name="payments")
    transaction_ref = models.CharField(max_length=80, unique=True, db_index=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    method = models.CharField(max_length=8, choices=Method.choices, default=Method.MPESA)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING, db_index=True)
    paid_at = models.DateTimeField(null=True, blank=True, db_index=True)
    provider = models.CharField(max_length=40, blank=True, default="")
    provider_ref = models.CharField(max_length=120, blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)
    initiated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="payments_initiated"
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.transaction_ref


class PaymentAllocation(UUIDPKMixin, TimeStampedModel, SchoolScopedModel):
    payment = models.ForeignKey(Payment, on_delete=models.CASCADE, related_name="allocations")
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="allocations")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    allocated_at = models.DateTimeField(auto_now_add=True)
    allocated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="allocations_made"
    )

    class Meta:
        ordering = ["-allocated_at"]

    def __str__(self):
        return f"{self.payment_id}:{self.invoice_id}"


class Receipt(UUIDPKMixin, TimeStampedModel, SchoolScopedModel):
    receipt_number = models.CharField(max_length=40, unique=True, db_index=True)
    payment = models.OneToOneField(Payment, on_delete=models.PROTECT, related_name="receipt")
    student = models.ForeignKey("people.Student", on_delete=models.PROTECT, related_name="receipts")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    issued_at = models.DateTimeField(auto_now_add=True)
    issued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="receipts_issued"
    )
    pdf_url = models.URLField(blank=True, default="")
    method = models.CharField(max_length=8, default="MPESA")

    class Meta:
        ordering = ["-issued_at"]

    def __str__(self):
        return self.receipt_number


class FeePromptReminder(UUIDPKMixin, TimeStampedModel, SchoolScopedModel):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="prompt_reminders")
    sent_via = models.CharField(max_length=20, default="SMS", choices=(("SMS", "SMS"), ("EMAIL", "Email"), ("WHATSAPP", "WhatsApp")))
    sent_at = models.DateTimeField(auto_now_add=True)
    recipient_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-sent_at"]

    def __str__(self):
        return f"{self.invoice_id}:{self.sent_via}"