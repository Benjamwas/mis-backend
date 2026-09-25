"""Finance API views: fees, invoices, payments, allocations, receipts, reporting."""
from django.db.models import Sum
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.common.exceptions import ValidationFailedError
from apps.common.permissions import HasPermission
from apps.common.viewsets import SchoolScopedViewSet
from apps.finance.models import (
    FeePromptReminder,
    FeeStructure,
    Invoice,
    Payment,
    Receipt,
    StudentFeeAccount,
)
from apps.finance.serializers import (
    FeePromptReminderSerializer,
    FeeStructureSerializer,
    InvoiceSerializer,
    PaymentSerializer,
    ReceiptSerializer,
    StudentFeeAccountSerializer,
)
from apps.finance.services import (
    apply_fee_structure_to_student,
    calculate_overdue,
    fee_balance_report,
    generate_fee_invoice,
    record_payment,
    reverse_invoice,
    reverse_payment,
)

FINANCE_PERMISSION_MAP = {"fee": "fee.read", "invoice": "invoice.read", "payment": "payment.read", "receipt": "receipt.read"}


class FeeStructureViewSet(SchoolScopedViewSet):
    queryset = FeeStructure.objects.prefetch_related("items").all()
    serializer_class = FeeStructureSerializer
    permission_classes = [HasPermission]
    permission_code = "fee.read"
    audit_module = "finance"
    audit_entity_type = "FeeStructure"

    def get_permissions(self):
        if self.action in ("create", "update", "partial_update", "destroy"):
            self.permission_code = "fee.create"
        return super().get_permissions()

    def perform_create(self, serializer):
        obj = serializer.save()
        self._audit("fee.create", obj, new_value={"name": obj.name})

    def perform_update(self, serializer):
        obj = serializer.save()
        self._audit("fee.update", obj, new_value={"name": obj.name})


class StudentFeeAccountViewSet(SchoolScopedViewSet):
    queryset = StudentFeeAccount.objects.select_related("student__person", "fee_structure").all()
    serializer_class = StudentFeeAccountSerializer
    permission_classes = [HasPermission]
    permission_code = "fee.read"
    audit_module = "finance"
    audit_entity_type = "StudentFeeAccount"
    filterset_fields = ["student"]

    def get_permissions(self):
        if self.action in ("create", "update", "partial_update"):
            self.permission_code = "fee.create"
        return super().get_permissions()

    def perform_create(self, serializer):
        obj = serializer.save()
        self._audit("fee.account.create", obj, new_value={"student": str(obj.student_id)})

    @action(detail=True, methods=["post"])
    def assign_fee_structure(self, request, pk=None):
        obj = self.get_object()
        apply_fee_structure_to_student(
            school=obj.school, student=obj.student, fee_structure_id=request.data.get("fee_structure_id"),
            by=request.user,
        )
        obj.refresh_from_db()
        self._audit("fee.structure.assign", obj, new_value={"fee_structure": str(obj.fee_structure_id)})
        return Response(StudentFeeAccountSerializer(obj).data)

    @action(detail=True, methods=["post"])
    def generate_invoice(self, request, pk=None):
        from apps.schools.models import Term

        obj = self.get_object()
        term = Term.objects.filter(school=obj.school, id=request.data.get("term_id")).first() if request.data.get("term_id") else None
        invoice = generate_fee_invoice(
            school=obj.school, student=obj.student, term=term,
            by=request.user, due_days=int(request.data.get("due_days", 14)),
        )
        self._audit("invoice.generate", invoice, new_value={"amount": str(invoice.amount_due)})
        return Response(InvoiceSerializer(invoice).data, status=status.HTTP_201_CREATED)


class InvoiceViewSet(SchoolScopedViewSet):
    queryset = Invoice.objects.select_related("student__person", "term").prefetch_related("items").all()
    serializer_class = InvoiceSerializer
    permission_classes = [HasPermission]
    permission_code = "invoice.read"
    audit_module = "finance"
    audit_entity_type = "Invoice"
    filterset_fields = ["student", "status", "invoice_type", "term"]

    def get_queryset(self):
        qs = super().get_queryset()
        status_param = self.request.query_params.get("status")
        if status_param:
            qs = qs.filter(status=status_param)
        return qs

    def get_permissions(self):
        if self.action in ("create", "update", "partial_update"):
            self.permission_code = "invoice.create"
        elif self.action in ("reverse",):
            self.permission_code = "invoice.reverse"
        elif self.action == "remind":
            self.permission_code = "invoice.update"
        return super().get_permissions()

    def perform_create(self, serializer):
        obj = serializer.save()
        self._audit("invoice.create", obj, new_value={"amount": str(obj.amount_due)})

    @action(detail=True, methods=["post"])
    def reverse(self, request, pk=None):
        obj = self.get_object()
        reverse_invoice(obj, by=request.user, reason=request.data.get("reason", ""))
        self._audit("invoice.reverse", obj, old_value={"status": "SENT"}, new_value={"status": obj.status})
        return Response(InvoiceSerializer(obj).data)

    @action(detail=True, methods=["post"])
    def remind(self, request, pk=None):
        obj = self.get_object()
        via = request.data.get("via", "SMS")
        reminder = None
        try:
            from apps.finance.services import prompt_fee_reminder

            reminder = prompt_fee_reminder(obj, via=via, by=request.user)
        except Exception:
            reminder = None
        self._audit("invoice.remind", obj, new_value={"via": via})
        return Response(FeePromptReminderSerializer(reminder).data if reminder else {"sent": False})

    @action(detail=False, methods=["get"])
    def outstanding(self, request):
        school = self.get_school()
        rows = fee_balance_report(school)
        return Response({
            "total_outstanding": sum(r["balance"] for r in rows),
            "overdue_count": calculate_overdue(school),
            "students": rows[:50],
        })


class PaymentViewSet(SchoolScopedViewSet):
    queryset = Payment.objects.select_related("student__person").prefetch_related("allocations").all()
    serializer_class = PaymentSerializer
    permission_classes = [HasPermission]
    permission_code = "payment.read"
    audit_module = "finance"
    audit_entity_type = "Payment"
    filterset_fields = ["student", "status", "method"]

    def get_permissions(self):
        if self.action == "create":
            self.permission_code = "payment.create"
        elif self.action in ("reverse", "confirm", "mpesa_status"):
            self.permission_code = "payment.reverse"
        elif self.action in ("allocate", "prompt"):
            self.permission_code = "payment.allocate"
        return super().get_permissions()

    def create(self, request, *args, **kwargs):
        school = self.get_school()
        if school is None:
            raise ValidationFailedError("A school context is required.", code="NO_SCHOOL_CONTEXT", status_code=403)
        from apps.people.models import Student

        student_id = request.data.get("student_id") or request.data.get("student")
        student = Student.objects.filter(school=school, id=student_id).first()
        if not student:
            raise ValidationFailedError("Student not found.", code="STUDENT_NOT_FOUND", status_code=404)

        from apps.finance.services import generate_transaction_ref

        payment, receipt = record_payment(
            school=school, student=student,
            amount=request.data.get("amount"),
            method=request.data.get("method", "MPESA"),
            status=request.data.get("status", "SUCCESS"),
            provider=request.data.get("provider", ""),
            provider_ref=request.data.get("provider_ref", ""),
            transaction_ref=request.data.get("transaction_ref") or generate_transaction_ref(),
            allocations=request.data.get("allocations"),
            by=request.user,
            metadata={"source": "manual"},
        )
        self._audit("payment.create", payment, new_value={"amount": str(payment.amount), "method": payment.method})
        data = PaymentSerializer(payment).data
        if receipt:
            data["receipt"] = ReceiptSerializer(receipt).data
        return Response(data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def allocate(self, request, pk=None):
        obj = self.get_object()
        from apps.finance.services import allocate_payment

        allocate_payment(obj, request.data.get("allocations", []), by=request.user)
        obj.refresh_from_db()
        self._audit("payment.allocate", obj, new_value={"allocations": len(request.data.get("allocations", []))})
        return Response(PaymentSerializer(obj).data)

    @action(detail=True, methods=["post"])
    def reverse(self, request, pk=None):
        obj = self.get_object()
        reverse_payment(obj, by=request.user, reason=request.data.get("reason", ""))
        obj.refresh_from_db()
        self._audit("payment.reverse", obj, old_value={"status": "SUCCESS"}, new_value={"status": obj.status})
        return Response(PaymentSerializer(obj).data)

    @action(detail=True, methods=["post"])
    def confirm(self, request, pk=None):
        """Manually confirm a pending bank/cash payment (pending webhook path)."""
        obj = self.get_object()
        from apps.finance.services import allocate_payment, issue_receipt

        if obj.status != "PENDING":
            raise ValidationFailedError("Only pending payments can be confirmed.", code="PAYMENT_NOT_PENDING")
        obj.status = "SUCCESS"
        from django.utils import timezone as tz

        obj.paid_at = tz.now()
        obj.save(update_fields=["status", "paid_at", "updated_at"])
        try:
            allocate_payment(obj, [{"invoice_id": inv.id, "amount": inv.balance} for inv in obj.student.invoices.filter(school=obj.school, status__in=["SENT", "PARTIALLY_PAID"])])
        except Exception:
            pass
        receipt = issue_receipt(school=obj.school, payment=obj)
        self._audit("payment.confirm", obj, new_value={"status": "SUCCESS"})
        return Response({"payment": PaymentSerializer(obj).data, "receipt": ReceiptSerializer(receipt).data})

    @action(detail=True, methods=["get"])
    def mpesa_status(self, request, pk=None):
        obj = self.get_object()
        from apps.finance.providers import MpesaConfig, ProviderNotConfiguredError, query_mpesa_stk

        ref = obj.metadata.get("checkout_request_id") or obj.provider_ref
        if not ref:
            raise ValidationFailedError("No M-Pesa checkout reference.", code="NO_MPESA_REF")
        try:
            result = query_mpesa_stk(ref)
        except ProviderNotConfiguredError:
            raise
        obj.metadata["last_query"] = result
        obj.save(update_fields=["metadata", "updated_at"])
        return Response(result)

    @action(detail=True, methods=["post"])
    def prompt(self, request, pk=None):
        obj = self.get_object()
        from apps.finance.services import prompt_fee_reminder

        reminder = prompt_fee_reminder(obj, via=request.data.get("via", "SMS"), by=request.user)
        return Response(FeePromptReminderSerializer(reminder).data if reminder else {"sent": False})


class ReceiptViewSet(SchoolScopedViewSet):
    queryset = Receipt.objects.select_related("student__person", "payment").all()
    serializer_class = ReceiptSerializer
    permission_classes = [HasPermission]
    permission_code = "receipt.read"
    audit_module = "finance"
    audit_entity_type = "Receipt"
    filterset_fields = ["student", "payment"]

    def get_permissions(self):
        if self.action in ("create",):
            self.permission_code = "receipt.create"
        return super().get_permissions()

    @action(detail=True, methods=["post"])
    def download(self, request, pk=None):
        obj = self.get_object()
        from apps.finance.services_pdf import render_receipt_pdf

        url, _ = render_receipt_pdf(obj)
        self._audit("receipt.download", obj, new_value={"url": url})
        return Response({"pdf_url": url})