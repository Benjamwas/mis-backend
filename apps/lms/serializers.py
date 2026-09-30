from rest_framework import serializers

from apps.lms.models import Lesson, Quiz, QuizAttempt, Resource, StudentTopicProgress, Topic


class TopicSerializer(serializers.ModelSerializer):
    subject_name = serializers.CharField(source="subject.name", read_only=True)
    lesson_count = serializers.IntegerField(source="lessons.count", read_only=True)

    class Meta:
        model = Topic
        fields = ["id", "school", "subject", "subject_name", "name", "description", "order_number",
                  "status", "lesson_count", "created_at"]
        read_only_fields = ["school"]

    def validate_subject(self, subject):
        school = self.context.get("school")
        if school is not None and subject.school_id != school.id:
            raise serializers.ValidationError("Subject must belong to the active school.")
        return subject


class LessonSerializer(serializers.ModelSerializer):
    topic_name = serializers.CharField(source="topic.name", read_only=True)
    resource_count = serializers.IntegerField(source="resources.count", read_only=True)

    class Meta:
        model = Lesson
        fields = ["id", "school", "topic", "topic_name", "title", "description", "content",
                  "order_number", "status", "resource_count", "created_at"]
        read_only_fields = ["school"]

    def validate_topic(self, topic):
        school = self.context.get("school")
        if school is not None and topic.school_id != school.id:
            raise serializers.ValidationError("Topic must belong to the active school.")
        return topic


class ResourceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Resource
        fields = ["id", "school", "lesson", "title", "resource_type", "file_url",
                  "external_url", "description", "created_at"]
        read_only_fields = ["school"]

    def validate_lesson(self, lesson):
        school = self.context.get("school")
        if school is not None and lesson.school_id != school.id:
            raise serializers.ValidationError("Lesson must belong to the active school.")
        return lesson


class StudentTopicProgressSerializer(serializers.ModelSerializer):
    topic_name = serializers.CharField(source="topic.name", read_only=True)
    student_name = serializers.CharField(source="student.full_name", read_only=True)

    class Meta:
        model = StudentTopicProgress
        fields = ["id", "school", "student", "student_name", "topic", "topic_name",
                  "progress_percentage", "status", "last_activity_at"]
        read_only_fields = ["school"]

    def validate(self, attrs):
        school = self.context.get("school")
        student = attrs.get("student", getattr(self.instance, "student", None))
        topic = attrs.get("topic", getattr(self.instance, "topic", None))
        if school is not None:
            if student and student.school_id != school.id:
                raise serializers.ValidationError({"student": "Student must belong to the active school."})
            if topic and topic.school_id != school.id:
                raise serializers.ValidationError({"topic": "Topic must belong to the active school."})
        return attrs


class QuizSerializer(serializers.ModelSerializer):
    topic_name = serializers.CharField(source="topic.name", read_only=True)
    subject_name = serializers.CharField(source="topic.subject.name", read_only=True)
    question_count = serializers.IntegerField(read_only=True)
    attempt_count = serializers.SerializerMethodField()

    class Meta:
        model = Quiz
        fields = ["id", "school", "topic", "topic_name", "subject_name", "title", "instructions",
                  "questions", "question_count", "max_attempts", "pass_percentage", "time_limit_minutes",
                  "status", "created_by", "published_at", "attempt_count", "created_at"]
        read_only_fields = ["school", "created_by", "published_at", "question_count", "attempt_count"]

    def get_attempt_count(self, obj):
        request = self.context.get("request")
        students = getattr(getattr(getattr(request, "user", None), "person", None), "students", None)
        if students:
            student = students.filter(school=obj.school_id).first()
            return obj.attempts.filter(student=student).count() if student else 0
        return obj.attempts.count()

    def validate(self, attrs):
        school = self.context.get("school")
        topic = attrs.get("topic", getattr(self.instance, "topic", None))
        questions = attrs.get("questions", getattr(self.instance, "questions", []))
        if school is not None and topic and topic.school_id != school.id:
            raise serializers.ValidationError({"topic": "Topic must belong to the active school."})
        if not isinstance(questions, list) or not questions:
            raise serializers.ValidationError({"questions": "At least one question is required."})
        for question in questions:
            if not isinstance(question, dict) or not question.get("prompt") or not isinstance(question.get("options"), list):
                raise serializers.ValidationError({"questions": "Each question needs a prompt and options."})
            answer = question.get("answer")
            if not isinstance(answer, int) or answer < 0 or answer >= len(question["options"]):
                raise serializers.ValidationError({"questions": "Each answer must reference an option."})
        return attrs


class QuizAttemptSerializer(serializers.ModelSerializer):
    quiz_title = serializers.CharField(source="quiz.title", read_only=True)
    student_name = serializers.CharField(source="student.full_name", read_only=True)

    class Meta:
        model = QuizAttempt
        fields = ["id", "school", "quiz", "quiz_title", "student", "student_name", "attempt_number",
                  "answers", "score", "percentage", "status", "started_at", "submitted_at"]
        read_only_fields = ["school", "student", "attempt_number", "score", "percentage", "status", "started_at", "submitted_at"]
