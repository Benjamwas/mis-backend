from rest_framework import serializers

from apps.finance.models import (
    FeeItem,
    FeePromptReminder,
    FeeStructure,
    Invoice,
    InvoiceItem,
    Payment,
    PaymentAllocation,
    Receipt,
    StudentFeeAccount,
)


class FeeItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = FeeItem
        fields = ["id", "name", "amount", "is_mandatory", "is_recurring", "description"]


class FeeStructureSerializer(serializers.ModelSerializer):
    items = FeeItemSerializer(many=True, required=False)
    grade_level_name = serializers.CharField(source="grade_level.name", read_only=True, default="")

    class Meta:
        model = FeeStructure
        fields = ["id", "school", "name", "grade_level", "grade_level_name", "billing_cycle",
                  "description", "is_active", "items"]
        read_only_fields = ["school"]

    def create(self, validated_data):
        items = validated_data.pop("items", [])
        structure = FeeStructure.objects.create(**validated_data)
        for item in items:
            FeeItem.objects.create(fee_structure=structure, **item)
        return structure

    def update(self, instance, validated_data):
        items = validated_data.pop("items", None)
        if items is not None:
            instance.items.all().delete()
            for item in items:
                FeeItem.objects.create(fee_structure=instance, **item)
        for k, v in validated_data.items():
            setattr(instance, k, v)
        instance.save()
        return instance


class StudentFeeAccountSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source="student.full_name", read_only=True)
    balance = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    fee_structure_name = serializers.CharField(source="fee_structure.name", read_only=True, default="")

    class Meta:
        model = StudentFeeAccount
        fields = ["id", "school", "student", "student_name", "fee_structure", "fee_structure_name",
                  "opening_balance", "credit_limit", "is_blocked", "remarks", "balance"]
        read_only_fields = ["school"]


class InvoiceItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = InvoiceItem
        fields = ["id", "description", "quantity", "unit_price", "amount"]


class InvoiceSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source="student.full_name", read_only=True)
    admission_number = serializers.CharField(source="student.admission_number", read_only=True)
    items = InvoiceItemSerializer(many=True, required=False)
    balance = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = Invoice
        fields = ["id", "school", "student", "student_name", "admission_number", "invoice_number",
                  "invoice_type", "issue_date", "due_date", "amount_due", "amount_paid", "adjustments",
                  "balance", "status", "term", "description", "payment_due_date", "items", "created_at"]
        read_only_fields = ["school", "invoice_number", "status"]

    def create(self, validated_data):
        items = validated_data.pop("items", [])
        from apps.finance.services import create_invoice

        return create_invoice(
            school=validated_data.pop("school"),
            student=validated_data.pop("student"),
            invoice_type=validated_data.pop("invoice_type", "TUITION"),
            issue_date=validated_data.pop("issue_date"),
            due_date=validated_data.pop("due_date"),
            items=items or [{"description": "Tuition", "quantity": 1, "unit_price": validated_data.pop("amount_due", 0)}],
            description=validated_data.pop("description", ""),
            term=validated_data.pop("term", None),
            by=self.context["request"].user,
        )


class PaymentSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source="student.full_name", read_only=True)
    admission_number = serializers.CharField(source="student.admission_number", read_only=True)

    class Meta:
        model = Payment
        fields = ["id", "school", "student", "student_name", "admission_number", "transaction_ref",
                  "amount", "method", "status", "paid_at", "provider", "provider_ref", "metadata"]
        read_only_fields = ["school", "transaction_ref", "status"]


class PaymentAllocationSerializer(serializers.ModelSerializer):
    invoice_number = serializers.CharField(source="invoice.invoice_number", read_only=True)

    class Meta:
        model = PaymentAllocation
        fields = ["id", "payment", "invoice", "invoice_number", "amount", "allocated_at"]
        read_only_fields = ["allocated_at"]


class ReceiptSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source="student.full_name", read_only=True)
    payment_transaction_ref = serializers.CharField(source="payment.transaction_ref", read_only=True)

    class Meta:
        model = Receipt
        fields = ["id", "school", "receipt_number", "payment", "payment_transaction_ref", "student",
                  "student_name", "amount", "issued_at", "pdf_url", "method"]
        read_only_fields = ["school", "receipt_number", "issued_at", "pdf_url"]


class FeePromptReminderSerializer(serializers.ModelSerializer):
    class Meta:
        model = FeePromptReminder
        fields = ["id", "invoice", "sent_via", "sent_at", "recipient_count"]
        read_only_fields = ["sent_at"]