"""LMS: topics, lessons, resources, and student progress."""
from django.conf import settings
from django.db import models

from apps.common.models import SchoolScopedModel, SoftDeleteModel, TimeStampedModel, UUIDPKMixin


class TopicStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    PUBLISHED = "PUBLISHED", "Published"
    ARCHIVED = "ARCHIVED", "Archived"


class Topic(UUIDPKMixin, TimeStampedModel, SoftDeleteModel, SchoolScopedModel):
    subject = models.ForeignKey("academics.Subject", on_delete=models.CASCADE, related_name="topics")
    name = models.CharField(max_length=160)
    description = models.TextField(blank=True, default="")
    order_number = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=12, choices=TopicStatus.choices, default=TopicStatus.DRAFT, db_index=True)

    class Meta:
        ordering = ["subject__name", "order_number"]

    def __str__(self):
        return self.name


class Lesson(UUIDPKMixin, TimeStampedModel, SoftDeleteModel, SchoolScopedModel):
    topic = models.ForeignKey(Topic, on_delete=models.CASCADE, related_name="lessons")
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    content = models.TextField(blank=True, default="")
    order_number = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=12, choices=TopicStatus.choices, default=TopicStatus.DRAFT, db_index=True)

    class Meta:
        ordering = ["topic__order_number", "order_number"]

    def __str__(self):
        return self.title


class ResourceType(models.TextChoices):
    PDF = "PDF", "PDF"
    VIDEO = "VIDEO", "Video"
    IMAGE = "IMAGE", "Image"
    DOCUMENT = "DOCUMENT", "Document"
    LINK = "LINK", "Link"
    AUDIO = "AUDIO", "Audio"


class Resource(UUIDPKMixin, TimeStampedModel, SoftDeleteModel, SchoolScopedModel):
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name="resources")
    title = models.CharField(max_length=200)
    resource_type = models.CharField(max_length=12, choices=ResourceType.choices, default=ResourceType.LINK)
    file_url = models.URLField(blank=True, default="")
    external_url = models.URLField(blank=True, default="")
    description = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title


class ProgressStatus(models.TextChoices):
    NOT_STARTED = "NOT_STARTED", "Not Started"
    IN_PROGRESS = "IN_PROGRESS", "In Progress"
    COMPLETED = "COMPLETED", "Completed"
    NEEDS_SUPPORT = "NEEDS_SUPPORT", "Needs Support"


class StudentTopicProgress(UUIDPKMixin, TimeStampedModel, SchoolScopedModel):
    student = models.ForeignKey("people.Student", on_delete=models.CASCADE, related_name="topic_progress")
    topic = models.ForeignKey(Topic, on_delete=models.CASCADE, related_name="student_progress")
    progress_percentage = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=15, choices=ProgressStatus.choices, default=ProgressStatus.NOT_STARTED, db_index=True)
    last_activity_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-last_activity_at"]
        constraints = [
            models.UniqueConstraint(fields=["student", "topic"], name="uq_student_topic_progress"),
        ]

    def mark_progress(self, percentage: int):
        self.progress_percentage = max(0, min(100, int(percentage)))
        if self.progress_percentage >= 100:
            self.status = ProgressStatus.COMPLETED
        elif self.progress_percentage > 0:
            self.status = ProgressStatus.IN_PROGRESS
        else:
            self.status = ProgressStatus.NOT_STARTED
        self.save(update_fields=["progress_percentage", "status", "last_activity_at", "updated_at"])


class Quiz(UUIDPKMixin, TimeStampedModel, SoftDeleteModel, SchoolScopedModel):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        PUBLISHED = "PUBLISHED", "Published"
        CLOSED = "CLOSED", "Closed"

    topic = models.ForeignKey(Topic, on_delete=models.CASCADE, related_name="quizzes")
    title = models.CharField(max_length=200)
    instructions = models.TextField(blank=True, default="")
    questions = models.JSONField(default=list)
    max_attempts = models.PositiveIntegerField(default=2)
    pass_percentage = models.PositiveIntegerField(default=60)
    time_limit_minutes = models.PositiveIntegerField(null=True, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT, db_index=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="created_quizzes")
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at"]

    @property
    def question_count(self):
        return len(self.questions or [])


class QuizAttempt(UUIDPKMixin, TimeStampedModel, SoftDeleteModel, SchoolScopedModel):
    class Status(models.TextChoices):
        IN_PROGRESS = "IN_PROGRESS", "In Progress"
        SUBMITTED = "SUBMITTED", "Submitted"

    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name="attempts")
    student = models.ForeignKey("people.Student", on_delete=models.CASCADE, related_name="quiz_attempts")
    attempt_number = models.PositiveIntegerField(default=1)
    answers = models.JSONField(default=list)
    score = models.PositiveIntegerField(default=0)
    percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.IN_PROGRESS, db_index=True)
    started_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["quiz", "student", "attempt_number"], name="uq_quiz_student_attempt"),
        ]
