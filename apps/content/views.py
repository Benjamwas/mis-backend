"""Content CMS API views."""
import csv
import io

from django.http import HttpResponse
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.common.exceptions import ValidationFailedError
from apps.common.permissions import HasPermission
from apps.common.viewsets import SchoolScopedViewSet
from apps.content.models import CmsPage, CmsPost, Event, EventParticipant, GalleryAlbum, GalleryMedia
from apps.content.serializers import (
    CmsPageSerializer,
    CmsPostSerializer,
    EventParticipantSerializer,
    EventSerializer,
    GalleryAlbumSerializer,
    GalleryMediaSerializer,
)
from apps.content.services import (
    add_media_to_album,
    cancel_registration,
    check_in_participant,
    publish,
    register_event_participant,
    set_album_cover,
    unpublish,
)
from apps.identity.services import user_has_permission


class CmsPageViewSet(SchoolScopedViewSet):
    queryset = CmsPage.objects.all()
    serializer_class = CmsPageSerializer
    permission_classes = [HasPermission]
    permission_code = "cms.read"
    audit_module = "content"
    audit_entity_type = "CmsPage"
    search_fields = ["title", "slug"]
    filterset_fields = ["status"]

    def get_queryset(self):
        qs = super().get_queryset()
        status_q = self.request.query_params.get("status")
        if status_q:
            qs = qs.filter(status=status_q)
        elif not self._can_publish():
            qs = qs.filter(status=CmsPage.Status.PUBLISHED)
        return qs

    def _can_publish(self):
        school = self.get_school()
        return user_has_permission(self.request.user, "cms.publish", school_id=school.id if school else None)

    def get_permissions(self):
        if self.action == "create":
            self.permission_code = "cms.create"
        elif self.action in ("update", "partial_update", "unpublish"):
            self.permission_code = "cms.update"
        elif self.action == "publish":
            self.permission_code = "cms.publish"
        return super().get_permissions()

    @action(detail=True, methods=["post"])
    def publish_action(self, request, pk=None):
        obj = publish(self.get_object())
        self._audit("cms.page.publish", obj, old_value={"status": "DRAFT"}, new_value={"status": obj.status})
        return Response(CmsPageSerializer(obj).data)

    @action(detail=True, methods=["post"])
    def unpublish_action(self, request, pk=None):
        obj = unpublish(self.get_object())
        self._audit("cms.page.unpublish", obj, new_value={"status": obj.status})
        return Response(CmsPageSerializer(obj).data)


class CmsPostViewSet(SchoolScopedViewSet):
    queryset = CmsPost.objects.all()
    serializer_class = CmsPostSerializer
    permission_classes = [HasPermission]
    permission_code = "cms.read"
    audit_module = "content"
    audit_entity_type = "CmsPost"
    search_fields = ["title", "tags"]

    def get_queryset(self):
        qs = super().get_queryset()
        category_q = self.request.query_params.get("category")
        if category_q:
            qs = qs.filter(category=category_q)
        status_q = self.request.query_params.get("status")
        if status_q:
            qs = qs.filter(status=status_q)
        elif not self._can_publish():
            qs = qs.filter(status=CmsPost.Status.PUBLISHED)
        return qs

    def _can_publish(self):
        school = self.get_school()
        return user_has_permission(self.request.user, "cms.publish", school_id=school.id if school else None)

    def get_permissions(self):
        if self.action == "create":
            self.permission_code = "cms.create"
        elif self.action in ("update", "partial_update", "unpublish"):
            self.permission_code = "cms.update"
        elif self.action == "publish":
            self.permission_code = "cms.publish"
        return super().get_permissions()

    def perform_create(self, serializer):
        obj = serializer.save(author=self.request.user)
        self._audit("cms.post.create", obj, new_value={"title": obj.title})

    @action(detail=True, methods=["post"])
    def publish_action(self, request, pk=None):
        obj = publish(self.get_object())
        self._audit("cms.post.publish", obj, old_value={"status": "DRAFT"}, new_value={"status": obj.status})
        return Response(CmsPostSerializer(obj).data)

    @action(detail=True, methods=["post"])
    def unpublish_action(self, request, pk=None):
        obj = unpublish(self.get_object())
        self._audit("cms.post.unpublish", obj, new_value={"status": obj.status})
        return Response(CmsPostSerializer(obj).data)


class EventViewSet(SchoolScopedViewSet):
    queryset = Event.objects.prefetch_related("participants").all()
    serializer_class = EventSerializer
    permission_classes = [HasPermission]
    permission_code = "event.read"
    audit_module = "content"
    audit_entity_type = "Event"
    filterset_fields = ["event_type", "status"]

    def get_queryset(self):
        qs = super().get_queryset()
        upcoming = self.request.query_params.get("upcoming")
        if upcoming == "1":
            from django.utils import timezone

            qs = qs.filter(status=Event.Status.PUBLISHED, start_time__gte=timezone.now())
        return qs

    def get_permissions(self):
        if self.action == "create":
            self.permission_code = "event.create"
        elif self.action in ("update", "partial_update", "cancel", "complete", "register", "check_in"):
            self.permission_code = "event.update"
        elif self.action == "publish":
            self.permission_code = "cms.publish"
        return super().get_permissions()

    def perform_create(self, serializer):
        obj = serializer.save(created_by=self.request.user)
        self._audit("event.create", obj, new_value={"title": obj.title})

    @action(detail=True, methods=["post"])
    def publish_action(self, request, pk=None):
        obj = publish(self.get_object())
        self._audit("event.publish", obj, old_value={"status": "DRAFT"}, new_value={"status": obj.status})
        return Response(EventSerializer(obj).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        obj = self.get_object()
        obj.status = Event.Status.CANCELLED
        obj.save(update_fields=["status", "updated_at"])
        self._audit("event.cancel", obj, old_value={"status": "PUBLISHED"}, new_value={"status": obj.status})
        return Response(EventSerializer(obj).data)

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        obj = self.get_object()
        obj.status = Event.Status.COMPLETED
        obj.save(update_fields=["status", "updated_at"])
        self._audit("event.complete", obj, new_value={"status": obj.status})
        return Response(EventSerializer(obj).data)

    @action(detail=True, methods=["post"])
    def register(self, request, pk=None):
        obj = self.get_object()
        participant = register_event_participant(
            event=obj, full_name=request.data.get("full_name", ""),
            email=request.data.get("email", ""), phone=request.data.get("phone", ""),
            student_id=request.data.get("student_id"), by=request.user,
        )
        self._audit("event.register", obj, new_value={"participant": str(participant.id)})
        return Response(EventParticipantSerializer(participant).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"])
    def participants(self, request, pk=None):
        obj = self.get_object()
        qs = obj.participants.order_by("created_at")
        return Response(EventParticipantSerializer(qs, many=True).data)

    @action(detail=True, methods=["post"], url_path="participants/(?P<participant_id>[^/.]+)/check-in")
    def check_in(self, request, pk=None, participant_id=None):
        obj = self.get_object()
        participant = obj.participants.filter(pk=participant_id).first()
        if not participant:
            raise ValidationFailedError("Participant not found.", code="PARTICIPANT_NOT_FOUND", status_code=404)
        check_in_participant(participant, by=request.user)
        self._audit("event.check_in", obj, new_value={"participant": participant_id})
        return Response(EventParticipantSerializer(participant).data)

    @action(detail=True, methods=["get"])
    def export_csv(self, request, pk=None):
        obj = self.get_object()
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["Full Name", "Email", "Phone", "Status", "Checked In At"])
        for p in obj.participants.order_by("created_at").iterator():
            writer.writerow([p.full_name, p.email, p.phone, p.status,
                             p.checked_in_at.isoformat() if p.checked_in_at else ""])
        buffer.seek(0)
        return HttpResponse(buffer.getvalue(), content_type="text/csv",
                            headers={"Content-Disposition": f'attachment; filename="event-{obj.title}.csv"'})

    @action(detail=True, methods=["post"])
    def participant_cancel(self, request, pk=None):
        from apps.content.models import EventParticipant

        obj = self.get_object()
        pid = request.data.get("participant_id")
        participant = obj.participants.filter(pk=pid).first()
        if not participant:
            raise ValidationFailedError("Participant not found.", code="PARTICIPANT_NOT_FOUND", status_code=404)
        cancel_registration(participant, by=request.user)
        self._audit("event.participant_cancel", obj, new_value={"participant": pid})
        return Response(EventParticipantSerializer(participant).data)


class EventParticipantViewSet(SchoolScopedViewSet):
    queryset = EventParticipant.objects.select_related("event", "student").all()
    serializer_class = EventParticipantSerializer
    permission_classes = [HasPermission]
    permission_code = "event.read"
    filterset_fields = ["event", "status"]

    def get_queryset(self):
        qs = super().get_queryset()
        event_id = self.request.query_params.get("event")
        if event_id:
            qs = qs.filter(event_id=event_id)
        return qs

    def get_permissions(self):
        if self.action in ("update", "partial_update", "check_in"):
            self.permission_code = "event.update"
        return super().get_permissions()

    @action(detail=True, methods=["post"])
    def check_in(self, request, pk=None):
        participant = self.get_object()
        check_in_participant(participant, by=request.user)
        self._audit("event.check_in", participant, new_value={"status": participant.status})
        return Response(EventParticipantSerializer(participant).data)


class GalleryAlbumViewSet(SchoolScopedViewSet):
    queryset = GalleryAlbum.objects.prefetch_related("media").all()
    serializer_class = GalleryAlbumSerializer
    permission_classes = [HasPermission]
    permission_code = "gallery.read"
    audit_module = "content"
    audit_entity_type = "GalleryAlbum"

    def get_queryset(self):
        qs = super().get_queryset()
        if not self._can_publish():
            qs = qs.filter(status=GalleryAlbum.Status.PUBLISHED)
        return qs

    def _can_publish(self):
        school = self.get_school()
        return user_has_permission(self.request.user, "gallery.publish", school_id=school.id if school else None)

    def get_permissions(self):
        if self.action == "create":
            self.permission_code = "gallery.create"
        elif self.action in ("update", "partial_update", "upload_media", "set_cover"):
            self.permission_code = "gallery.update"
        elif self.action == "publish":
            self.permission_code = "gallery.publish"
        return super().get_permissions()

    def perform_create(self, serializer):
        obj = serializer.save(created_by=self.request.user)
        self._audit("gallery.album.create", obj, new_value={"title": obj.title})

    @action(detail=True, methods=["post"])
    def publish_action(self, request, pk=None):
        obj = publish(self.get_object())
        self._audit("gallery.album.publish", obj, old_value={"status": "DRAFT"}, new_value={"status": obj.status})
        return Response(GalleryAlbumSerializer(obj).data)

    @action(detail=True, methods=["post"])
    def upload_media(self, request, pk=None):
        from apps.files.models import FileUpload

        album = self.get_object()
        media = []
        for file_id in request.data.get("file_ids", []):
            file = FileUpload.objects.filter(school=album.school, id=file_id).first()
            if not file:
                raise ValidationFailedError("File not found.", code="FILE_NOT_FOUND", status_code=404)
            media.append(add_media_to_album(album=album, file=file, caption=request.data.get("caption", "")))
        self._audit("gallery.media.upload", album, new_value={"count": len(media)})
        return Response(GalleryMediaSerializer(media, many=True).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def set_cover(self, request, pk=None):
        album = self.get_object()
        media = album.media.filter(pk=request.data.get("media_id")).first()
        if not media:
            raise ValidationFailedError("Gallery media not found.", code="MEDIA_NOT_FOUND", status_code=404)
        set_album_cover(album, media, by=request.user)
        self._audit("gallery.album.set_cover", album, new_value={"media": str(media.id)})
        return Response(GalleryAlbumSerializer(album).data)