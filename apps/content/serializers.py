from rest_framework import serializers

from apps.content.models import (
    CmsPage,
    CmsPost,
    Event,
    EventParticipant,
    GalleryAlbum,
    GalleryMedia,
)


class CmsPageSerializer(serializers.ModelSerializer):
    author_name = serializers.CharField(source="author.full_name", read_only=True, default="")

    class Meta:
        model = CmsPage
        fields = ["id", "school", "title", "slug", "content", "status", "author", "author_name",
                  "published_at", "meta_title", "meta_description", "template_name", "created_at", "updated_at"]
        read_only_fields = ["school"]


class CmsPostSerializer(serializers.ModelSerializer):
    author_name = serializers.CharField(source="author.full_name", read_only=True, default="")
    featured_image_url = serializers.CharField(source="featured_image.file.url", read_only=True, default="")

    class Meta:
        model = CmsPost
        fields = ["id", "school", "title", "slug", "excerpt", "content", "featured_image",
                  "featured_image_url", "category", "tags", "status", "published_at", "author",
                  "author_name", "created_at", "updated_at"]
        read_only_fields = ["school"]


class EventSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source="created_by.full_name", read_only=True, default="")
    participant_count = serializers.IntegerField(read_only=True)
    cover_image_url = serializers.CharField(source="cover_image.file.url", read_only=True, default="")

    class Meta:
        model = Event
        fields = ["id", "school", "title", "description", "event_type", "start_time", "end_time",
                  "venue", "capacity", "status", "cover_image", "cover_image_url", "allow_registration",
                  "is_recurring", "published_at", "created_by", "created_by_name",
                  "participant_count", "created_at", "updated_at"]
        read_only_fields = ["school"]


class EventParticipantSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source="student.full_name", read_only=True, default="")
    event_title = serializers.CharField(source="event.title", read_only=True)

    class Meta:
        model = EventParticipant
        fields = ["id", "school", "event", "event_title", "full_name", "email", "phone", "student",
                  "student_name", "status", "checked_in_at", "created_at"]
        read_only_fields = ["school"]


class GalleryMediaSerializer(serializers.ModelSerializer):
    file_url = serializers.CharField(source="file.file.url", read_only=True, default="")

    class Meta:
        model = GalleryMedia
        fields = ["id", "album", "file", "file_url", "caption", "sort_order", "is_cover"]


class GalleryAlbumSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source="created_by.full_name", read_only=True, default="")
    media_count = serializers.IntegerField(read_only=True)
    cover_image_url = serializers.CharField(source="cover_image.file.url", read_only=True, default="")
    media = GalleryMediaSerializer(many=True, read_only=True)

    class Meta:
        model = GalleryAlbum
        fields = ["id", "school", "title", "description", "cover_image", "cover_image_url", "status",
                  "published_at", "created_by", "created_by_name", "media_count", "media",
                  "created_at", "updated_at"]
        read_only_fields = ["school"]