from rest_framework import serializers

from apps.admissions.models import (
    AdmissionApplication,
    Applicant,
    ApplicationDocument,
    ApplicationStatusHistory,
)


class ApplicantSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(read_only=True)

    class Meta:
        model = Applicant
        fields = ["id", "school", "first_name", "last_name", "full_name", "email", "phone",
                  "date_of_birth", "gender", "current_school", "previous_results", "guardian_name",
                  "guardian_phone", "guardian_email", "address", "status", "created_at"]
        read_only_fields = ["school"]


class ApplicationStatusHistorySerializer(serializers.ModelSerializer):
    changed_by_name = serializers.CharField(source="changed_by.full_name", read_only=True, default="")

    class Meta:
        model = ApplicationStatusHistory
        fields = ["id", "from_status", "to_status", "changed_by", "changed_by_name", "comment", "changed_at"]
        read_only_fields = ["changed_at"]


class ApplicationDocumentSerializer(serializers.ModelSerializer):
    file_name = serializers.CharField(source="file.original_name", read_only=True, default="")
    file_url = serializers.CharField(source="file.file.url", read_only=True, default="")

    class Meta:
        model = ApplicationDocument
        fields = ["id", "application", "file", "file_name", "file_url", "document_type", "is_verified"]
        read_only_fields = ["school"]


class AdmissionApplicationSerializer(serializers.ModelSerializer):
    applicant = ApplicantSerializer(read_only=True)
    applicant_id = serializers.UUIDField(required=False)
    grade_level_name = serializers.CharField(source="grade_level.name", read_only=True)
    academic_year_name = serializers.CharField(source="academic_year.name", read_only=True)
    term_name = serializers.CharField(source="term.name", read_only=True, default="")
    status_history = serializers.SerializerMethodField()
    applicant_name = serializers.CharField(source="applicant.full_name", read_only=True)

    class Meta:
        model = AdmissionApplication
        fields = ["id", "school", "applicant", "applicant_id", "applicant_name", "academic_year",
                  "academic_year_name", "grade_level", "grade_level_name", "term", "term_name",
                  "status", "application_number", "submitted_at", "decided_at", "decision_comment",
                  "notes", "status_history", "created_at"]
        read_only_fields = ["school", "application_number", "submitted_at", "decided_at"]

    def get_status_history(self, obj):
        qs = obj.status_history.all()[:5]
        return ApplicationStatusHistorySerializer(qs, many=True).data

    def create(self, validated_data):
        school = validated_data.pop("school")
        from apps.admissions.services import create_application

        applicant_id = validated_data.pop("applicant_id", None)
        applicant = None
        if applicant_id:
            applicant = Applicant.objects.filter(school=school, id=applicant_id).first()
            if not applicant:
                raise serializers.ValidationError({"applicant_id": "Applicant not found."})
        elif "applicant_data" in validated_data:
            applicant = Applicant.objects.create(school=school, **validated_data.pop("applicant_data"))

        if not applicant:
            raise serializers.ValidationError({"applicant_id": "An applicant is required."})

        return create_application(
            school=school,
            academic_year=validated_data.pop("academic_year"),
            grade_level=validated_data.pop("grade_level"),
            term=validated_data.pop("term", None),
            notes=validated_data.pop("notes", ""),
            applicant=applicant,
        )

    def create_with_applicant(self, **validated_data):
        school = validated_data.pop("school")
        from apps.admissions.services import create_application

        return create_application(school=school, **validated_data, by=self.context["request"].user)

    def update(self, instance, validated_data):
        new_status = validated_data.pop("status", instance.status)
        from apps.admissions.services import update_application_status

        if new_status != instance.status:
            instance = update_application_status(
                instance, new_status, by=self.context["request"].user,
                comment=validated_data.pop("decision_comment", ""),
            )
        for k, v in validated_data.items():
            setattr(instance, k, v)
        instance.save()
        return instance