"""LMS views."""
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.common.permissions import HasPermission
from apps.common.viewsets import SchoolScopedViewSet
from apps.common.exceptions import PermissionDeniedError, TenantIsolationError, ValidationFailedError
from apps.identity.services import user_has_permission
from apps.lms.models import Lesson, Quiz, QuizAttempt, Resource, StudentTopicProgress, Topic, TopicStatus
from apps.lms.serializers import (
    LessonSerializer,
    ResourceSerializer,
    QuizAttemptSerializer,
    QuizSerializer,
    StudentTopicProgressSerializer,
    TopicSerializer,
)


class TopicViewSet(SchoolScopedViewSet):
    queryset = Topic.objects.all()
    serializer_class = TopicSerializer
    permission_classes = [HasPermission]
    permission_code = "subject.read"
    audit_module = "lms"
    audit_entity_type = "Topic"
    filterset_fields = ["subject", "status"]

    def get_queryset(self):
        qs = super().get_queryset().select_related("subject").prefetch_related("lessons")
        school = self.get_school()
        if school and not user_has_permission(self.request.user, "subject.update", school_id=school.id):
            qs = qs.filter(status="PUBLISHED")
        return qs

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["school"] = self.get_school()
        return ctx

    def get_permissions(self):
        if self.action in ("create", "update", "partial_update", "destroy"):
            self.permission_code = "subject.update"
        return super().get_permissions()

    def perform_create(self, serializer):
        school = self.get_school()
        if school is None:
            raise TenantIsolationError("A school context is required.")
        obj = serializer.save(school=school)
        self._audit("topic.create", obj, new_value={"name": obj.name})

    @action(detail=True, methods=["post"], permission_classes=[HasPermission])
    def publish(self, request, pk=None):
        obj = self.get_object()
        obj.status = "PUBLISHED"
        obj.save(update_fields=["status", "updated_at"])
        self._audit("topic.publish", obj, old_value={"status": "DRAFT"}, new_value={"status": obj.status})
        return Response(TopicSerializer(obj).data)

    @action(detail=True, methods=["post"], permission_classes=[HasPermission])
    def archive(self, request, pk=None):
        obj = self.get_object()
        obj.status = "ARCHIVED"
        obj.save(update_fields=["status", "updated_at"])
        self._audit("topic.archive", obj, new_value={"status": obj.status})
        return Response(TopicSerializer(obj).data)


class LessonViewSet(SchoolScopedViewSet):
    queryset = Lesson.objects.all()
    serializer_class = LessonSerializer
    permission_classes = [HasPermission]
    permission_code = "subject.read"
    filterset_fields = ["topic", "status"]

    def get_queryset(self):
        qs = super().get_queryset().select_related("topic").prefetch_related("resources")
        school = self.get_school()
        if school and not user_has_permission(self.request.user, "subject.update", school_id=school.id):
            qs = qs.filter(topic__status="PUBLISHED", status="PUBLISHED")
        return qs

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["school"] = self.get_school()
        return ctx

    def get_permissions(self):
        if self.action in ("create", "update", "partial_update", "destroy"):
            self.permission_code = "subject.update"
        return super().get_permissions()

    def perform_create(self, serializer):
        school = self.get_school()
        if school is None:
            raise TenantIsolationError("A school context is required.")
        obj = serializer.save(school=school)
        self._audit("lesson.create", obj, new_value={"title": obj.title})


class ResourceViewSet(SchoolScopedViewSet):
    queryset = Resource.objects.all()
    serializer_class = ResourceSerializer
    permission_classes = [HasPermission]
    permission_code = "subject.read"
    filterset_fields = ["lesson", "resource_type"]

    def get_queryset(self):
        qs = super().get_queryset().select_related("lesson__topic")
        school = self.get_school()
        if school and not user_has_permission(self.request.user, "subject.update", school_id=school.id):
            qs = qs.filter(lesson__topic__status="PUBLISHED", lesson__status="PUBLISHED")
        return qs

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["school"] = self.get_school()
        return ctx

    def perform_create(self, serializer):
        school = self.get_school()
        if school is None:
            raise TenantIsolationError("A school context is required.")
        serializer.save(school=school)

    def get_permissions(self):
        if self.action in ("create", "update", "partial_update", "destroy"):
            self.permission_code = "subject.update"
        return super().get_permissions()


class TopicProgressViewSet(SchoolScopedViewSet):
    queryset = StudentTopicProgress.objects.all()
    serializer_class = StudentTopicProgressSerializer
    permission_classes = [HasPermission]
    permission_code = "result.read"
    filterset_fields = ["student", "topic", "status"]

    def get_queryset(self):
        qs = super().get_queryset().select_related("student__person", "topic")
        school = self.get_school()
        if school and not user_has_permission(self.request.user, "result.update", school_id=school.id):
            students = self.request.user.person.students.filter(school=school).values_list("id", flat=True)
            qs = qs.filter(student_id__in=students)
        return qs

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["school"] = self.get_school()
        return ctx

    def perform_create(self, serializer):
        school = self.get_school()
        if school is None:
            raise TenantIsolationError("A school context is required.")
        student = serializer.validated_data.get("student")
        if not user_has_permission(self.request.user, "result.update", school_id=school.id):
            if not student or not self.request.user.person.students.filter(pk=student.pk, school=school).exists():
                raise PermissionDeniedError()
        serializer.save(school=school)

    @action(detail=True, methods=["post"], permission_classes=[HasPermission])
    def update_progress(self, request, pk=None):
        """Record learner progress (student self-service or teacher entry)."""
        obj = self.get_object()
        school = self.get_school()
        if school and not user_has_permission(request.user, "result.update", school_id=school.id):
            if not request.user.person.students.filter(pk=obj.student_id, school=school).exists():
                raise PermissionDeniedError()
        percentage = request.data.get("progress_percentage")
        if percentage is None:
            return Response({"error": "progress_percentage required."}, status=400)
        obj.mark_progress(percentage)
        return Response(StudentTopicProgressSerializer(obj).data)


class QuizViewSet(SchoolScopedViewSet):
    queryset = Quiz.objects.all()
    serializer_class = QuizSerializer
    permission_classes = [HasPermission]
    permission_code = "subject.read"
    audit_module = "lms"
    audit_entity_type = "Quiz"
    filterset_fields = ["topic", "status"]

    def get_queryset(self):
        qs = super().get_queryset().select_related("topic__subject")
        school = self.get_school()
        if school and not user_has_permission(self.request.user, "subject.update", school_id=school.id):
            qs = qs.filter(status=Quiz.Status.PUBLISHED, topic__status=TopicStatus.PUBLISHED)
        return qs

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["school"] = self.get_school()
        return ctx

    def get_permissions(self):
        if self.action in ("create", "update", "partial_update", "destroy", "publish", "close"):
            self.permission_code = "subject.update"
        return super().get_permissions()

    def perform_create(self, serializer):
        school = self.get_school()
        if school is None:
            raise TenantIsolationError("A school context is required.")
        serializer.save(school=school, created_by=self.request.user)

    @action(detail=True, methods=["post"])
    def publish(self, request, pk=None):
        quiz = self.get_object()
        quiz.status = Quiz.Status.PUBLISHED
        quiz.published_at = timezone.now()
        quiz.save(update_fields=["status", "published_at", "updated_at"])
        return Response(QuizSerializer(quiz, context={"request": request}).data)

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        quiz = self.get_object()
        quiz.status = Quiz.Status.CLOSED
        quiz.save(update_fields=["status", "updated_at"])
        return Response(QuizSerializer(quiz, context={"request": request}).data)

    @action(detail=True, methods=["post"], permission_classes=[HasPermission])
    def submit(self, request, pk=None):
        quiz = self.get_object()
        student = request.user.person.students.filter(school=quiz.school_id).first()
        if student is None:
            raise PermissionDeniedError("No matching student context for this quiz.")
        if quiz.status != Quiz.Status.PUBLISHED:
            raise ValidationFailedError("This quiz is not open.", code="QUIZ_NOT_OPEN", status_code=409)
        attempt_count = quiz.attempts.filter(student=student).count()
        if attempt_count >= quiz.max_attempts:
            raise ValidationFailedError("Maximum quiz attempts reached.", code="MAX_ATTEMPTS_REACHED", status_code=409)
        answers = request.data.get("answers", [])
        if not isinstance(answers, list):
            raise ValidationFailedError("answers must be a list.", code="ANSWERS_REQUIRED")
        questions = quiz.questions or []
        score = sum(1 for index, question in enumerate(questions) if index < len(answers) and answers[index] == question.get("answer"))
        percentage = round(score * 100 / max(len(questions), 1), 2)
        attempt = QuizAttempt.objects.create(
            school=quiz.school,
            quiz=quiz,
            student=student,
            is_deleted=False,
            attempt_number=attempt_count + 1,
            answers=answers,
            score=score,
            percentage=percentage,
            status=QuizAttempt.Status.SUBMITTED,
            submitted_at=timezone.now(),
        )
        return Response(QuizAttemptSerializer(attempt).data, status=201)

    @action(detail=True, methods=["get"])
    def attempts(self, request, pk=None):
        quiz = self.get_object()
        attempts = quiz.attempts.select_related("student__person")
        if not user_has_permission(request.user, "subject.update", school_id=quiz.school_id):
            student = request.user.person.students.filter(school=quiz.school_id).first()
            attempts = attempts.filter(student=student)
        return Response(QuizAttemptSerializer(attempts, many=True).data)
