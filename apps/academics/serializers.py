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
    StudentGroup,
    StudentGroupMember,
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


class StudentGroupMemberSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source="student.full_name", read_only=True)

    class Meta:
        model = StudentGroupMember
        fields = ["id", "group", "student", "student_name", "is_leader", "created_at"]


class StudentGroupSerializer(serializers.ModelSerializer):
    class_name = serializers.CharField(source="school_class.display_name", read_only=True)
    subject_name = serializers.CharField(source="subject.name", read_only=True)
    members = StudentGroupMemberSerializer(many=True, read_only=True)
    member_count = serializers.IntegerField(source="members.count", read_only=True)

    class Meta:
        model = StudentGroup
        fields = ["id", "school", "school_class", "class_name", "subject", "subject_name", "name",
                  "description", "status", "member_count", "members", "created_at"]
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
    my_submission_status = serializers.SerializerMethodField()
    my_submission_marks = serializers.SerializerMethodField()
    my_submission_feedback = serializers.SerializerMethodField()

    class Meta:
        model = Assignment
        fields = ["id", "school", "teaching_assignment", "topic", "title", "description", "instructions",
                  "max_marks", "due_date", "submission_type", "status", "created_by", "published_at",
                  "subject", "class_name", "my_submission_status", "my_submission_marks", "my_submission_feedback", "created_at"]
        read_only_fields = ["school", "created_by", "published_at", "status"]

    def validate(self, attrs):
        school = self.context.get("school")
        teaching_assignment = attrs.get("teaching_assignment", getattr(self.instance, "teaching_assignment", None))
        topic = attrs.get("topic", getattr(self.instance, "topic", None))
        if school is not None:
            if teaching_assignment and teaching_assignment.school_id != school.id:
                raise serializers.ValidationError({"teaching_assignment": "Teaching assignment must belong to the active school."})
            if topic and topic.school_id != school.id:
                raise serializers.ValidationError({"topic": "Topic must belong to the active school."})
        return attrs

    def _submission(self, obj):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        student = getattr(getattr(user, "person", None), "students", None)
        if not student:
            return None
        student = student.filter(school=obj.school_id).first()
        return obj.submissions.filter(student=student).prefetch_related("grades").first() if student else None

    def get_my_submission_status(self, obj):
        submission = self._submission(obj)
        return submission.status if submission else None

    def get_my_submission_marks(self, obj):
        submission = self._submission(obj)
        grade = submission.grades.first() if submission else None
        return str(grade.marks) if grade else None

    def get_my_submission_feedback(self, obj):
        submission = self._submission(obj)
        grade = submission.grades.first() if submission else None
        return grade.feedback if grade else ""


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
