from rest_framework import serializers

from apps.lms.models import Lesson, Resource, StudentTopicProgress, Topic


class TopicSerializer(serializers.ModelSerializer):
    subject_name = serializers.CharField(source="subject.name", read_only=True)
    lesson_count = serializers.IntegerField(source="lessons.count", read_only=True)

    class Meta:
        model = Topic
        fields = ["id", "school", "subject", "subject_name", "name", "description", "order_number",
                  "status", "lesson_count", "created_at"]
        read_only_fields = ["school"]


class LessonSerializer(serializers.ModelSerializer):
    topic_name = serializers.CharField(source="topic.name", read_only=True)
    resource_count = serializers.IntegerField(source="resources.count", read_only=True)

    class Meta:
        model = Lesson
        fields = ["id", "school", "topic", "topic_name", "title", "description", "content",
                  "order_number", "status", "resource_count", "created_at"]
        read_only_fields = ["school"]


class ResourceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Resource
        fields = ["id", "school", "lesson", "title", "resource_type", "file_url",
                  "external_url", "description", "created_at"]
        read_only_fields = ["school"]


class StudentTopicProgressSerializer(serializers.ModelSerializer):
    topic_name = serializers.CharField(source="topic.name", read_only=True)
    student_name = serializers.CharField(source="student.full_name", read_only=True)

    class Meta:
        model = StudentTopicProgress
        fields = ["id", "school", "student", "student_name", "topic", "topic_name",
                  "progress_percentage", "status", "last_activity_at"]
        read_only_fields = ["school"]