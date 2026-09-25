"""Public (unauthenticated) endpoints for published content.

Mounted at the root of /api/v1/ by config/urls.py. All responses use the SALA
envelope; event registration is rate-limited.
"""
from django.shortcuts import get_object_or_404
from django.urls import path
from rest_framework import status
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from apps.common.exceptions import ValidationFailedError
from apps.content.models import CmsPage, CmsPost, Event, GalleryAlbum
from apps.content.serializers import (
    CmsPageSerializer,
    CmsPostSerializer,
    EventParticipantSerializer,
    EventSerializer,
    GalleryAlbumSerializer,
)
from apps.content.services import register_event_participant


class RepeatPostAnonRateThrottle(AnonRateThrottle):
    scope = "anon_event_register"
    rate = "5/hour"


class PublicCmsPagesView(APIView):
    permission_classes = []

    def get(self, request):
        qs = CmsPage.objects.filter(school__isnull=False, status=CmsPage.Status.PUBLISHED)
        slug = request.query_params.get("slug")
        if slug:
            qs = qs.filter(slug=slug)
        order = request.query_params.get("order")
        qs = qs.order_by(order if order in ("title", "-title") else "title")
        return Response(CmsPageSerializer(qs, many=True).data)


class PublicCmsPageDetailView(APIView):
    permission_classes = []

    def get(self, request, slug):
        page = get_object_or_404(CmsPage, slug=slug, status=CmsPage.Status.PUBLISHED)
        return Response(CmsPageSerializer(page).data)


class PublicCmsPostsView(APIView):
    permission_classes = []

    def get(self, request):
        qs = CmsPost.objects.filter(status=CmsPost.Status.PUBLISHED).order_by("-published_at")
        category = request.query_params.get("category")
        if category:
            qs = qs.filter(category=category)
        return Response(CmsPostSerializer(qs, many=True).data)


class PublicCmsPostDetailView(APIView):
    permission_classes = []

    def get(self, request, slug):
        post = get_object_or_404(CmsPost, slug=slug, status=CmsPost.Status.PUBLISHED)
        return Response(CmsPostSerializer(post).data)


class PublicEventsView(APIView):
    permission_classes = []

    def get(self, request):
        from django.utils import timezone

        qs = Event.objects.filter(status=Event.Status.PUBLISHED).order_by("start_time")
        if request.query_params.get("upcoming") == "1":
            qs = qs.filter(start_time__gte=timezone.now())
        return Response(EventSerializer(qs, many=True).data)


class PublicEventDetailView(APIView):
    permission_classes = []

    def get(self, request, pk):
        event = get_object_or_404(Event, pk=pk, status=Event.Status.PUBLISHED)
        return Response(EventSerializer(event).data)


class PublicEventRegisterView(APIView):
    permission_classes = []
    throttle_classes = [RepeatPostAnonRateThrottle]

    def post(self, request, pk):
        event = get_object_or_404(Event, pk=pk, status=Event.Status.PUBLISHED)
        full_name = request.data.get("full_name")
        email = request.data.get("email")
        if not full_name or not email:
            raise ValidationFailedError("full_name and email are required.", code="INVALID_REGISTRATION")
        participant = register_event_participant(
            event=event, full_name=full_name, email=email,
            phone=request.data.get("phone", ""), student_id=request.data.get("student_id"),
        )
        return Response(EventParticipantSerializer(participant).data, status=status.HTTP_201_CREATED)


class PublicGalleryAlbumsView(APIView):
    permission_classes = []

    def get(self, request):
        qs = GalleryAlbum.objects.filter(status=GalleryAlbum.Status.PUBLISHED).order_by("-published_at")
        return Response(GalleryAlbumSerializer(qs, many=True).data)


urlpatterns = [
    path("public/cms/pages/", PublicCmsPagesView.as_view(), name="public-cms-pages"),
    path("public/cms/pages/<slug:slug>/", PublicCmsPageDetailView.as_view(), name="public-cms-page-detail"),
    path("public/cms/posts/", PublicCmsPostsView.as_view(), name="public-cms-posts"),
    path("public/cms/posts/<slug:slug>/", PublicCmsPostDetailView.as_view(), name="public-cms-post-detail"),
    path("public/events/", PublicEventsView.as_view(), name="public-events"),
    path("public/events/<uuid:pk>/", PublicEventDetailView.as_view(), name="public-event-detail"),
    path("public/events/<uuid:pk>/register/", PublicEventRegisterView.as_view(), name="public-event-register"),
    path("public/gallery/albums/", PublicGalleryAlbumsView.as_view(), name="public-gallery-albums"),
]