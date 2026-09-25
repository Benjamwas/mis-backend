from rest_framework import serializers

from apps.identity.serializers import PersonSerializer
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
    PayslipItem,
)


class DepartmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Department
        fields = ["id", "school", "name", "description", "created_at"]
        read_only_fields = ["school"]


class EmployeeSerializer(serializers.ModelSerializer):
    person = PersonSerializer()
    full_name = serializers.CharField(read_only=True)
    is_teacher = serializers.BooleanField(read_only=True)
    department_name = serializers.CharField(source="department.name", read_only=True, default="")

    class Meta:
        model = Employee
        fields = ["id", "school", "person", "full_name", "employee_number", "department", "department_name",
                  "employment_date", "employment_status", "role_title", "base_salary", "is_active", "is_teacher",
                  "created_at"]
        read_only_fields = ["school"]

    def create(self, validated_data):
        person_data = validated_data.pop("person")
        from apps.identity.models import Person

        person = Person.objects.create(**person_data)
        school = self.context.get("school") or self.context["request"].school
        return Employee.objects.create(school=school, person=person, **validated_data)

    def update(self, instance, validated_data):
        person_data = validated_data.pop("person", None)
        if person_data:
            person = instance.person
            for k, v in person_data.items():
                setattr(person, k, v)
            person.save()
        for k, v in validated_data.items():
            setattr(instance, k, v)
        instance.save()
        return instance


class LeaveTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = LeaveType
        fields = ["id", "school", "name", "days_allowed", "is_paid", "description"]
        read_only_fields = ["school"]


class LeaveRequestSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)
    leave_type_name = serializers.CharField(source="leave_type.name", read_only=True)
    days = serializers.IntegerField(read_only=True)

    class Meta:
        model = LeaveRequest
        fields = ["id", "school", "employee", "employee_name", "leave_type", "leave_type_name",
                  "start_date", "end_date", "days", "reason", "status", "reviewed_by",
                  "decision_comment", "decided_at", "created_at"]
        read_only_fields = ["school", "status", "reviewed_by", "decision_comment", "decided_at"]


class PayrollPeriodSerializer(serializers.ModelSerializer):
    payslip_count = serializers.SerializerMethodField()

    class Meta:
        model = PayrollPeriod
        fields = ["id", "school", "name", "start_date", "end_date", "status", "payment_date", "payslip_count"]
        read_only_fields = ["school"]

    def get_payslip_count(self, obj):
        return obj.payslips.count()


class PayslipSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)
    employee_number = serializers.CharField(source="employee.employee_number", read_only=True)
    items = serializers.SerializerMethodField()

    class Meta:
        model = Payslip
        fields = ["id", "school", "payroll_period", "employee", "employee_name", "employee_number",
                  "gross_salary", "total_deductions", "net_salary", "payment_date", "status", "pdf_url", "items"]
        read_only_fields = ["school"]

    def get_items(self, obj):
        return [{"item_type": i.item_type, "description": i.description, "amount": str(i.amount)}
                for i in obj.items.all()]


class DutySerializer(serializers.ModelSerializer):
    class Meta:
        model = Duty
        fields = ["id", "school", "name", "location", "description"]
        read_only_fields = ["school"]


class DutyAssignmentSerializer(serializers.ModelSerializer):
    duty_name = serializers.CharField(source="duty.name", read_only=True)
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)

    class Meta:
        model = DutyAssignment
        fields = ["id", "school", "duty", "duty_name", "employee", "employee_name", "date",
                  "start_time", "end_time", "status"]
        read_only_fields = ["school"]


class HrTicketSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)
    message_count = serializers.SerializerMethodField()

    class Meta:
        model = HrTicket
        fields = ["id", "school", "employee", "employee_name", "category", "subject", "description",
                  "priority", "status", "assigned_to", "message_count", "created_at"]
        read_only_fields = ["school"]

    def get_message_count(self, obj):
        return obj.messages.count()


class HrTicketMessageSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source="user.full_name", read_only=True)

    class Meta:
        model = HrTicketMessage
        fields = ["id", "school", "ticket", "user", "user_name", "message", "created_at"]
        read_only_fields = ["school", "user", "created_at"]