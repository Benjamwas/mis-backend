from rest_framework import serializers

from apps.academics.models import (
    Assessment,
    AssessmentScore,
    Assignment,
    AssignmentGrade,
    AssignmentSubmission,
    ClassSubject,
    Enrollment,
    LearningRecommendation,
    StudentSubjectResult,
    Subject,
    TeachingAssignment,
)


class SubjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subject
        fields = ["id", "school", "name", "code", "description", "status", "created_at"]
        read_only_fields = ["school"]


class ClassSubjectSerializer(serializers.ModelSerializer):
    subject_name = serializers.CharField(source="subject.name", read_only=True)
    subject_code = serializers.CharField(source="subject.code", read_only=True)

    class Meta:
        model = ClassSubject
        fields = ["id", "school", "school_class", "subject", "subject_name", "subject_code"]
        read_only_fields = ["school"]


class TeachingAssignmentSerializer(serializers.ModelSerializer):
    teacher_name = serializers.CharField(source="teacher.person.full_name", read_only=True)
    class_name = serializers.CharField(source="school_class.display_name", read_only=True)
    subject_name = serializers.CharField(source="subject.name", read_only=True)
    term_name = serializers.CharField(source="term.name", read_only=True)

    class Meta:
        model = TeachingAssignment
        fields = ["id", "school", "teacher", "teacher_name", "school_class", "class_name",
                  "subject", "subject_name", "term", "term_name", "is_primary", "status"]
        read_only_fields = ["school"]


class EnrollmentSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source="student.full_name", read_only=True)
    class_name = serializers.CharField(source="school_class.display_name", read_only=True)
    academic_year_name = serializers.CharField(source="academic_year.name", read_only=True)

    class Meta:
        model = Enrollment
        fields = ["id", "school", "student", "student_name", "school_class", "class_name",
                  "academic_year", "academic_year_name", "start_date", "end_date", "status"]
        read_only_fields = ["school"]


class AssignmentSerializer(serializers.ModelSerializer):
    subject = serializers.CharField(source="teaching_assignment.subject.name", read_only=True)
    class_name = serializers.CharField(source="teaching_assignment.school_class.display_name", read_only=True)

    class Meta:
        model = Assignment
        fields = ["id", "school", "teaching_assignment", "topic", "title", "description", "instructions",
                  "max_marks", "due_date", "submission_type", "status", "created_by", "published_at",
                  "subject", "class_name", "created_at"]
        read_only_fields = ["school", "created_by", "published_at", "status"]


class AssignmentSubmissionSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source="student.full_name", read_only=True)
    assignment_title = serializers.CharField(source="assignment.title", read_only=True)
    marks = serializers.SerializerMethodField()

    class Meta:
        model = AssignmentSubmission
        fields = ["id", "school", "assignment", "assignment_title", "student", "student_name",
                  "submission_content", "submitted_at", "status", "marks", "created_at"]
        read_only_fields = ["school"]

    def get_marks(self, obj):
        grade = obj.grades.first()
        return str(grade.marks) if grade else None


class AssignmentGradeSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssignmentGrade
        fields = ["id", "submission", "graded_by", "marks", "feedback", "graded_at"]
        read_only_fields = ["graded_by", "graded_at"]


class AssessmentSerializer(serializers.ModelSerializer):
    subject = serializers.CharField(source="teaching_assignment.subject.name", read_only=True)
    class_name = serializers.CharField(source="teaching_assignment.school_class.display_name", read_only=True)

    class Meta:
        model = Assessment
        fields = ["id", "school", "teaching_assignment", "term", "title", "assessment_type",
                  "max_score", "date", "status", "subject", "class_name", "created_at"]
        read_only_fields = ["school"]


class AssessmentScoreSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source="student.full_name", read_only=True)
    assessment_title = serializers.CharField(source="assessment.title", read_only=True)

    class Meta:
        model = AssessmentScore
        fields = ["id", "school", "assessment", "assessment_title", "student", "student_name",
                  "score", "grade", "teacher_comment", "recorded_by", "created_at"]
        read_only_fields = ["school", "recorded_by"]


class StudentSubjectResultSerializer(serializers.ModelSerializer):
    subject_name = serializers.CharField(source="subject.name", read_only=True)
    student_name = serializers.CharField(source="student.full_name", read_only=True)
    term_name = serializers.CharField(source="term.name", read_only=True)

    class Meta:
        model = StudentSubjectResult
        fields = ["id", "school", "student", "student_name", "subject", "subject_name", "term",
                  "term_name", "total_score", "grade", "teacher_comment", "status", "created_at"]
        read_only_fields = ["school"]


class LearningRecommendationSerializer(serializers.ModelSerializer):
    topic_name = serializers.CharField(source="topic.name", read_only=True)
    subject_name = serializers.CharField(source="subject.name", read_only=True)

    class Meta:
        model = LearningRecommendation
        fields = ["id", "school", "student", "topic", "topic_name", "subject", "subject_name",
                  "reason", "detail", "priority", "status", "created_at"]
        read_only_fields = ["school"]