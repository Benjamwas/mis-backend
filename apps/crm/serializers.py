from rest_framework import serializers

from apps.crm.models import CrmInteraction, CrmLead, CrmTask, SchoolVisit


class CrmLeadSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(read_only=True)
    assigned_to_name = serializers.CharField(source="assigned_to.full_name", read_only=True, default="")
    interested_grade_name = serializers.CharField(source="interested_grade.name", read_only=True, default="")
    preferred_class_name = serializers.CharField(source="preferred_class.name", read_only=True, default="")

    class Meta:
        model = CrmLead
        fields = ["id", "school", "person", "first_name", "last_name", "full_name", "email", "phone",
                  "source", "status", "interested_grade", "interested_grade_name", "preferred_class",
                  "preferred_class_name", "notes", "converted_to_student", "follow_up_date",
                  "assigned_to", "assigned_to_name", "last_contacted_at", "opt_in_sms", "opt_in_email",
                  "created_at"]
        read_only_fields = ["school"]


class CrmInteractionSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source="user.full_name", read_only=True, default="")
    lead_name = serializers.CharField(source="lead.full_name", read_only=True, default="")

    class Meta:
        model = CrmInteraction
        fields = ["id", "school", "lead", "lead_name", "user", "user_name", "interaction_type",
                  "notes", "outcome", "scheduled_at", "created_at"]
        read_only_fields = ["school", "user"]


class CrmTaskSerializer(serializers.ModelSerializer):
    assigned_to_name = serializers.CharField(source="assigned_to.full_name", read_only=True, default="")
    created_by_name = serializers.CharField(source="created_by.full_name", read_only=True, default="")

    class Meta:
        model = CrmTask
        fields = ["id", "school", "lead", "title", "description", "due_date", "status",
                  "assigned_to", "assigned_to_name", "created_by", "created_by_name", "created_at"]
        read_only_fields = ["school", "created_by"]


class SchoolVisitSerializer(serializers.ModelSerializer):
    lead_name = serializers.CharField(source="lead.full_name", read_only=True, default="")
    toured_by_name = serializers.CharField(source="toured_by.full_name", read_only=True, default="")

    class Meta:
        model = SchoolVisit
        fields = ["id", "school", "lead", "lead_name", "student_name", "parent_name", "parent_phone",
                  "parent_email", "visit_date", "status", "toured_by", "toured_by_name", "notes",
                  "feedback", "created_at"]
        read_only_fields = ["school"]