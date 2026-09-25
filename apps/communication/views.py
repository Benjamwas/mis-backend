"""Communication views."""
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from apps.common.permissions import HasPermission
from apps.common.viewsets import SchoolScopedViewSet
from apps.communication.models import Announcement, BroadcastCampaign, Notification
from apps.communication.serializers import (
    AnnouncementSerializer,
    BroadcastCampaignSerializer,
    NotificationSerializer,
)
from apps.identity.services import resolve_school_context


class NotificationViewSet(ModelViewSet):
    queryset = Notification.objects.all()
    serializer_class = NotificationSerializer
    permission_classes = [HasPermission]
    permission_code = "notification.read"
    filterset_fields = ["is_read", "type"]

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user).order_by("-created_at")

    def perform_destroy(self, instance):
        if instance.user_id != self.request.user.id:
            from apps.common.exceptions import PermissionDeniedError

            raise PermissionDeniedError()
        instance.delete()

    @action(detail=True, methods=["post"])
    def read(self, request, pk=None):
        obj = self.get_object()
        if obj.user_id != request.user.id:
            from apps.common.exceptions import PermissionDeniedError

            raise PermissionDeniedError()
        from django.utils import timezone

        obj.is_read = True
        obj.read_at = timezone.now()
        obj.save(update_fields=["is_read", "read_at", "updated_at"])
        return Response(NotificationSerializer(obj).data)

    @action(detail=False, methods=["post"])
    def read_all(self, request):
        from django.utils import timezone

        Notification.objects.filter(user=request.user, is_read=False).update(is_read=True, read_at=timezone.now())
        return Response({"message": "All notifications marked as read."})

    @action(detail=False, methods=["get"])
    def unread_count(self, request):
        return Response({"count": Notification.objects.filter(user=request.user, is_read=False).count()})


class AnnouncementViewSet(SchoolScopedViewSet):
    queryset = Announcement.objects.all()
    serializer_class = AnnouncementSerializer
    permission_classes = [HasPermission]
    permission_code = "announcement.read"
    audit_module = "communication"
    audit_entity_type = "Announcement"
    filterset_fields = ["audience", "status"]

    def get_permissions(self):
        if self.action in ("create", "publish"):
            self.permission_code = "announcement.create"
        elif self.action in ("update", "partial_update"):
            self.permission_code = "announcement.create"
        return super().get_permissions()

    def perform_create(self, serializer):
        obj = serializer.save(created_by=self.request.user)
        self._audit("announcement.create", obj, new_value={"title": obj.title})

    @action(detail=True, methods=["post"])
    def publish(self, request, pk=None):
        from django.utils import timezone

        obj = self.get_object()
        obj.status = "PUBLISHED"
        obj.published_at = timezone.now()
        obj.save(update_fields=["status", "published_at", "updated_at"])
        self._audit("announcement.publish", obj, old_value={"status": "DRAFT"}, new_value={"status": obj.status})
        return Response(AnnouncementSerializer(obj).data)


class BroadcastCampaignViewSet(SchoolScopedViewSet):
    queryset = BroadcastCampaign.objects.all()
    serializer_class = BroadcastCampaignSerializer
    permission_classes = [HasPermission]
    permission_code = "campaign.read"
    audit_module = "communication"
    audit_entity_type = "BroadcastCampaign"
    filterset_fields = ["status", "channel"]

    def get_permissions(self):
        if self.action in ("create", "send", "dispatch"):
            self.permission_code = "campaign.send"
        elif self.action in ("update", "partial_update"):
            self.permission_code = "campaign.manage"
        return super().get_permissions()

    def perform_create(self, serializer):
        obj = serializer.save(created_by=self.request.user)
        self._audit("campaign.create", obj, new_value={"title": obj.title})

    @action(detail=True, methods=["post"])
    def send(self, request, pk=None):
        obj = self.get_object()
        if obj.status == "COMPLETED":
            return Response({"message": "Campaign already completed."})
        from apps.communication.tasks import dispatch_broadcast

        if obj.scheduled_at:
            obj.status = "SCHEDULED"
            obj.save(update_fields=["status", "updated_at"])
        else:
            obj.status = "PROCESSING"
            obj.save(update_fields=["status", "updated_at"])
            dispatch_broadcast.delay(str(obj.id))
        self._audit("campaign.send", obj, new_value={"status": obj.status})
        return Response(BroadcastCampaignSerializer(obj).data)

    @action(detail=False, methods=["post"])
    def send_sms(self, request):
        """Direct single SMS (e.g. admin broadcast)."""
        from apps.communication.tasks import send_sms

        to = request.data.get("to")
        body = request.data.get("body")
        school = self.get_school()
        send_sms.delay(to, body, school_id=school.id if school else None)
        return Response({"message": "SMS queued."}, status=status.HTTP_202_ACCEPTED)

    @action(detail=False, methods=["post"])
    def send_email(self, request):
        from apps.communication.tasks import send_email

        to = request.data.get("to")
        subject = request.data.get("subject")
        body = request.data.get("body")
        school = self.get_school()
        send_email.delay(to, subject, body, school_id=school.id if school else None)
        return Response({"message": "Email queued."}, status=status.HTTP_202_ACCEPTED)

    @action(detail=False, methods=["post"])
    def send_whatsapp(self, request):
        from apps.communication.tasks import send_whatsapp

        to = request.data.get("to")
        body = request.data.get("body")
        school = self.get_school()
        send_whatsapp.delay(to, body, school_id=school.id if school else None)
        return Response({"message": "WhatsApp message queued."}, status=status.HTTP_202_ACCEPTED)