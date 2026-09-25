from rest_framework import serializers

from apps.schools.models import (
    AcademicYear,
    GradeLevel,
    Module,
    School,
    SchoolClass,
    SchoolModule,
    SchoolSettings,
    Term,
)


class SchoolSerializer(serializers.ModelSerializer):
    class Meta:
        model = School
        fields = ["id", "name", "code", "slug", "email", "phone", "address", "logo_url", "motto", "status", "created_at"]


class SchoolDetailSerializer(SchoolSerializer):
    class Meta(SchoolSerializer.Meta):
        fields = SchoolSerializer.Meta.fields


class AcademicYearSerializer(serializers.ModelSerializer):
    class Meta:
        model = AcademicYear
        fields = ["id", "school", "name", "start_date", "end_date", "status", "created_at", "updated_at"]


class TermSerializer(serializers.ModelSerializer):
    academic_year_name = serializers.CharField(source="academic_year.name", read_only=True)

    class Meta:
        model = Term
        fields = ["id", "school", "academic_year", "academic_year_name", "name", "start_date", "end_date", "status"]


class GradeLevelSerializer(serializers.ModelSerializer):
    class Meta:
        model = GradeLevel
        fields = ["id", "school", "name", "category", "display_order"]


class SchoolClassSerializer(serializers.ModelSerializer):
    display_name = serializers.CharField(read_only=True)
    grade_level_name = serializers.CharField(source="grade_level.name", read_only=True)
    academic_year_name = serializers.CharField(source="academic_year.name", read_only=True)

    class Meta:
        model = SchoolClass
        fields = [
            "id", "school", "academic_year", "academic_year_name", "grade_level", "grade_level_name",
            "name", "section", "display_name", "class_teacher", "status",
        ]


class ModuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Module
        fields = ["id", "code", "name", "description", "is_core"]


class SchoolModuleSerializer(serializers.ModelSerializer):
    module_code = serializers.CharField(source="module.code", read_only=True)
    module_name = serializers.CharField(source="module.name", read_only=True)

    class Meta:
        model = SchoolModule
        fields = ["id", "school", "module", "module_code", "module_name", "enabled", "configuration"]


class SchoolSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = SchoolSettings
        fields = ["id", "school", "key", "value"]