"""LMS views."""
from django.shortcuts import get_object_or_404
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.common.permissions import HasPermission
from apps.common.viewsets import SchoolScopedViewSet
from apps.lms.models import Lesson, Resource, StudentTopicProgress, Topic
from apps.lms.serializers import (
    LessonSerializer,
    ResourceSerializer,
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
        return super().get_queryset().select_related("subject").prefetch_related("lessons")

    def get_permissions(self):
        if self.action in ("create", "update", "partial_update", "destroy"):
            self.permission_code = "subject.update"
        return super().get_permissions()

    def perform_create(self, serializer):
        obj = serializer.save()
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
        return super().get_queryset().select_related("topic").prefetch_related("resources")

    def get_permissions(self):
        if self.action in ("create", "update", "partial_update", "destroy"):
            self.permission_code = "subject.update"
        return super().get_permissions()

    def perform_create(self, serializer):
        obj = serializer.save()
        self._audit("lesson.create", obj, new_value={"title": obj.title})


class ResourceViewSet(SchoolScopedViewSet):
    queryset = Resource.objects.all()
    serializer_class = ResourceSerializer
    permission_classes = [HasPermission]
    permission_code = "subject.read"
    filterset_fields = ["lesson", "resource_type"]

    def get_queryset(self):
        return super().get_queryset().select_related("lesson__topic")

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
        return super().get_queryset().select_related("student__person", "topic")

    @action(detail=True, methods=["post"], permission_classes=[HasPermission])
    def update_progress(self, request, pk=None):
        """Record learner progress (student self-service or teacher entry)."""
        obj = self.get_object()
        percentage = request.data.get("progress_percentage")
        if percentage is None:
            return Response({"error": "progress_percentage required."}, status=400)
        obj.mark_progress(percentage)
        return Response(StudentTopicProgressSerializer(obj).data)