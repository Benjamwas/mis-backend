from rest_framework import serializers

from apps.identity.models import Person
from apps.identity.serializers import PersonSerializer
from apps.people.models import MedicalRecord, Parent, ParentStudent, RelationshipType, Student


class StudentSerializer(serializers.ModelSerializer):
    person = PersonSerializer()
    full_name = serializers.CharField(read_only=True)
    current_class = serializers.SerializerMethodField()

    class Meta:
        model = Student
        fields = ["id", "school", "person", "full_name", "admission_number", "admission_date",
                  "status", "is_active", "current_class", "created_at", "updated_at"]
        read_only_fields = ["school", "is_active", "created_at", "updated_at"]

    def get_current_class(self, obj):
        enrollment = obj.enrollments.filter(status="ACTIVE").select_related("school_class").first()
        return str(enrollment.school_class_id) if enrollment else None

    def validate_admission_number(self, value):
        from apps.people.services import validate_admission_number_uniqueness

        request = self.context.get("request")
        school = getattr(request, "school", None) or getattr(self.context.get("view"), "get_school", lambda: None)()
        if school:
            validate_admission_number_uniqueness(school, value, exclude_id=getattr(self.instance, "id", None))
        return value

    def create(self, validated_data):
        from apps.people.services import create_student

        person_data = validated_data.pop("person")
        school = self.context.get("school") or self.context["request"].school
        return create_student(
            school=school,
            person_data=person_data,
            admission_number=validated_data.pop("admission_number"),
            admission_date=validated_data.pop("admission_date", None),
            **validated_data,
        )

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


class ParentSerializer(serializers.ModelSerializer):
    person = PersonSerializer()
    full_name = serializers.CharField(read_only=True)

    class Meta:
        model = Parent
        fields = ["id", "school", "person", "full_name", "occupation", "employer", "is_active", "created_at"]
        read_only_fields = ["school", "created_at"]

    def create(self, validated_data):
        from apps.people.services import create_parent

        person_data = validated_data.pop("person")
        school = self.context.get("school") or self.context["request"].school
        return create_parent(school=school, person_data=person_data, occupation=validated_data.pop("occupation", ""))

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


class ParentStudentSerializer(serializers.ModelSerializer):
    child = StudentSerializer(source="student", read_only=True)
    relationship_type = serializers.ChoiceField(choices=RelationshipType.choices)

    class Meta:
        model = ParentStudent
        fields = ["id", "parent", "student", "child", "relationship_type", "is_primary_contact",
                  "can_view_finance", "can_view_academics", "created_at"]

    def validate(self, attrs):
        parent = attrs.get("parent") or getattr(self.instance, "parent", None)
        student = attrs.get("student") or getattr(self.instance, "student", None)
        if parent and student and parent.school_id != student.school_id:
            raise serializers.ValidationError("Parent and student must belong to the same school.")
        return attrs


class MedicalRecordSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source="student.full_name", read_only=True)
    bmi = serializers.SerializerMethodField()

    class Meta:
        model = MedicalRecord
        fields = ["id", "school", "student", "student_name", "record_date",
                  "height_cm", "weight_kg", "bmi", "blood_group", "vision", "hearing",
                  "general_condition", "allergies", "chronic_conditions", "medications",
                  "physical_exam_notes", "examined_by", "next_checkup_date", "status", "created_at"]
        read_only_fields = ["school"]

    def get_bmi(self, obj):
        return obj.bmi
