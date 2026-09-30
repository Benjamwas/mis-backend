"""Finance business services: invoicing, allocations, payments, receipts, reports."""
import logging
import uuid
from decimal import Decimal

from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from apps.common.exceptions import AccountingError, ConflictError, NotFoundError, ValidationFailedError
from apps.finance.models import (
    FeeItem,
    FeeStructure,
    Invoice,
    InvoiceItem,
    Payment,
    PaymentAllocation,
    Receipt,
    StudentFeeAccount,
)

logger = logging.getLogger("apps.finance")


def generate_invoice_number(school) -> str:
    year = timezone.now().year
    count = Invoice.objects.filter(school=school).count() + 1
    return f"INV-{year}-{count:05d}"


def generate_receipt_number(school) -> str:
    year = timezone.now().year
    count = Receipt.objects.filter(school=school).count() + 1
    return f"RCP-{year}-{count:05d}"


def generate_transaction_ref() -> str:
    return f"PAY-{uuid.uuid4().hex[:12].upper()}"


@transaction.atomic
def create_invoice(*, school, student, invoice_type="TUITION", issue_date, due_date,
                   items, description="", term=None, by=None):
    """Create an invoice with line items and compute totals."""
    if not items:
        raise ValidationFailedError("At least one invoice item is required.", code="NO_INVOICE_ITEMS")

    invoice = Invoice.objects.create(
        school=school, student=student, invoice_number=generate_invoice_number(school),
        invoice_type=invoice_type, issue_date=issue_date, due_date=due_date,
        amount_due=0, description=description, term=term, created_by=by,
    )
    total = 0
    for item in items:
        qty = item.get("quantity", 1)
        unit = item.get("unit_price", item.get("amount", 0))
        amount = (qty or 1) * (unit or 0)
        InvoiceItem.objects.create(
            school=school, invoice=invoice, description=item.get("description", ""),
            quantity=qty, unit_price=unit, amount=amount,
        )
        total += amount
    invoice.amount_due = round(total, 2)
    invoice.save(update_fields=["amount_due", "updated_at"])
    return invoice


@transaction.atomic
def reverse_invoice(invoice, by=None, reason=""):
    if invoice.status in ("PAID", "CANCELLED"):
        raise ConflictError("Only unpaid invoices can be reversed.", code="INVOICE_NOT_REVERSIBLE")
    invoice.status = Invoice.Status.CANCELLED
    invoice.save(update_fields=["status", "updated_at"])
    return invoice


def allocate_payment(payment, allocations, by=None):
    """Allocate a successful payment to invoices, verifying amounts match."""
    total_allocated = sum(float(a.get("amount", 0)) for a in allocations or [])
    if round(total_allocated, 2) != round(float(payment.amount), 2):
        raise AccountingError("Allocation total does not match the payment amount.", code="ALLOCATION_MISMATCH")

    for alloc in allocations:
        invoice = Invoice.objects.filter(school=payment.school, id=alloc["invoice_id"]).first()
        if not invoice:
            raise NotFoundError(message="Invoice does not exist.")
        if str(invoice.student_id) != str(payment.student_id):
            raise ValidationFailedError("Invoice belongs to a different student.", code="ALLOCATION_STUDENT_MISMATCH")
        available = invoice.balance
        amt = Decimal(str(alloc["amount"]))
        if amt > available:
            raise AccountingError("Allocation exceeds the invoice balance.", code="ALLOCATION_EXCEEDS_BALANCE")

        PaymentAllocation.objects.create(
            school=payment.school, payment=payment, invoice=invoice, amount=amt, allocated_by=by,
        )
        invoice.amount_paid = (invoice.amount_paid or Decimal("0")) + amt
        invoice.status = (
            Invoice.Status.PAID
            if round(invoice.balance, 2) <= 0
            else Invoice.Status.PARTIALLY_PAID
        )
        invoice.save(update_fields=["amount_paid", "status", "updated_at"])
    return payment


@transaction.atomic
def record_payment(*, school, student, amount, method="MPESA", status="SUCCESS", provider="", provider_ref="",
                   transaction_ref=None, allocations=None, by=None, metadata=None):
    """Create a payment and, on success, allocate and issue a receipt."""
    transaction_ref = transaction_ref or generate_transaction_ref()
    amount = Decimal(str(amount))

    duplicate = Payment.objects.filter(transaction_ref=transaction_ref).first()
    if duplicate:
        if duplicate.status == status:
            return duplicate, None
        raise ConflictError("Transaction reference already used.", code="DUPLICATE_TRANSACTION")
    # Provider-level dedupe check
    if provider_ref:
        prov_dup = Payment.objects.filter(provider=provider, provider_ref=provider_ref).first()
        if prov_dup:
            raise ConflictError("Duplicate provider reference.", code="DUPLICATE_PROVIDER_REF")

    payment = Payment.objects.create(
        school=school, student=student, transaction_ref=transaction_ref, amount=amount,
        method=method, status=status, provider=provider, provider_ref=provider_ref,
        metadata=metadata or {}, initiated_by=by,
    )

    receipt = None
    if status == Payment.Status.SUCCESS:
        payment.paid_at = timezone.now()
        payment.save(update_fields=["paid_at", "updated_at"])
        if allocations:
            allocate_payment(payment, allocations, by=by)
        receipt = issue_receipt(school=school, payment=payment, by=by)

    return payment, receipt


def issue_receipt(*, school, payment, by=None) -> Receipt:
    receipt = Receipt.objects.create(
        school=school, receipt_number=generate_receipt_number(school), payment=payment,
        student=payment.student, amount=payment.amount, issued_by=by, method=payment.method,
    )
    from apps.finance.services_pdf import render_receipt_pdf

    url, _ = render_receipt_pdf(receipt)
    receipt.pdf_url = url
    receipt.save(update_fields=["pdf_url", "updated_at"])
    return receipt


@transaction.atomic
def reverse_payment(payment, by=None, reason=""):
    """Refund/reverse a successful payment and roll back invoice allocations."""
    if payment.status != Payment.Status.SUCCESS:
        raise ConflictError("Only successful payments can be reversed.", code="PAYMENT_NOT_REVERSED")

    for alloc in payment.allocations.select_related("invoice"):
        invoice = alloc.invoice
        invoice.amount_paid -= alloc.amount
        invoice.status = (
            Invoice.Status.OVERDUE
            if invoice.balance > 0 and timezone.localdate() > invoice.due_date
            else Invoice.Status.PARTIALLY_PAID if invoice.balance > 0 else Invoice.Status.PAID
        )
        invoice.save(update_fields=["amount_paid", "status", "updated_at"])

    payment.status = Payment.Status.REVERSED
    payment.save(update_fields=["status", "updated_at"])
    return payment


def apply_fee_structure_to_student(*, school, student, fee_structure_id=None, by=None):
    """Attach a fee structure to a student, creating a fee account if missing."""
    account, created = StudentFeeAccount.objects.get_or_create(school=school, student=student)
    if fee_structure_id:
        structure = FeeStructure.objects.filter(school=school, id=fee_structure_id).first()
        if not structure:
            raise NotFoundError(message="Fee structure not found.")
        account.fee_structure = structure
        account.save(update_fields=["fee_structure", "updated_at"])
    return account


def generate_fee_invoice(*, school, student, term=None, by=None, due_days=14):
    """Build an invoice from the student's active fee structure."""
    account = StudentFeeAccount.objects.filter(school=school, student=student).select_related("fee_structure").first()
    if not account or not account.fee_structure:
        raise ValidationFailedError("Student has no fee structure assigned.", code="NO_FEE_STRUCTURE")

    structure = account.fee_structure
    issue_date = timezone.localdate()
    due_date = issue_date + timezone.timedelta(days=due_days)
    items = [{"description": item.name, "quantity": 1, "unit_price": item.amount}
             for item in structure.items.filter(is_recurring=True)]
    if not items:
        raise ValidationFailedError("Fee structure has no billable items.", code="EMPTY_FEE_STRUCTURE")

    return create_invoice(
        school=school, student=student, invoice_type="TUITION", issue_date=issue_date,
        due_date=due_date, items=items, term=term, description=f"Fee for {structure.name}", by=by,
    )


def fee_balance_report(school):
    """Student-by-student outstanding balances used by dashboards and reports."""
    rows = []
    accounts = StudentFeeAccount.objects.filter(school=school).select_related("student__person")
    for account in accounts:
        balance = account.balance
        if balance <= 0:
            continue
        enrollment = account.student.enrollments.select_related("school_class__grade_level").order_by("-created_at").first()
        rows.append({
            "student": {
                "id": str(account.student.id),
                "name": account.student.full_name,
                "admission_number": account.student.admission_number,
                "grade": enrollment.school_class.grade_level.name if enrollment and enrollment.school_class.grade_level_id else "",
            },
            "balance": balance,
        })
    rows.sort(key=lambda r: r["balance"], reverse=True)
    return rows


def calculate_overdue(school):
    today = timezone.localdate()
    return Invoice.objects.filter(school=school, status__in=["SENT", "PARTIALLY_PAID"], due_date__lt=today).count()


def prompt_fee_reminder(invoice, via="SMS", by=None):
    """Queue an SMS/email reminder to a student's guardians."""
    from apps.communication.tasks import notify_users
    from apps.finance.models import FeePromptReminder
    from apps.people.services import student_guardian_users

    users = student_guardian_users(invoice.student)
    recipient_ids = [u.id for u in users]
    if not recipient_ids:
        return None

    notify_users.delay(
        recipient_ids,
        title="School Fee Reminder",
        body=f"Dear parent, invoice {invoice.invoice_number} of KES {invoice.balance} is due. Kindly pay.",
        entity_type="Invoice", entity_id=invoice.id, school_id=invoice.school_id,
    )
    return FeePromptReminder.objects.create(
        school=invoice.school, invoice=invoice, sent_via=via, recipient_count=len(recipient_ids),
    )