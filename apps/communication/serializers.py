from rest_framework import serializers

from apps.communication.models import Announcement, BroadcastCampaign, Notification


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ["id", "user", "school", "title", "body", "type", "entity_type", "entity_id",
                  "is_read", "read_at", "created_at"]
        read_only_fields = ["user", "created_at", "read_at"]


class AnnouncementSerializer(serializers.ModelSerializer):
    author = serializers.CharField(source="created_by.full_name", read_only=True)

    class Meta:
        model = Announcement
        fields = ["id", "school", "title", "body", "audience", "channels", "published_at", "status",
                  "created_by", "author", "created_at"]
        read_only_fields = ["school", "created_by", "published_at"]


class BroadcastCampaignSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source="created_by.full_name", read_only=True)
    recipient_count = serializers.SerializerMethodField()

    class Meta:
        model = BroadcastCampaign
        fields = ["id", "school", "title", "message", "channel", "audience", "scheduled_at",
                  "status", "created_by", "created_by_name", "recipient_count", "created_at"]
        read_only_fields = ["school", "created_by", "status"]

    def get_recipient_count(self, obj):
        return obj.recipients.count()