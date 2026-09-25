"""File validation + upload service."""
from rest_framework import serializers

from apps.files.models import ALLOWED_MIME_TYPES, MAX_FILE_SIZE, FileCategory, FileUpload
from apps.files.storage import upload_to_storage


class FileUploadSerializer(serializers.ModelSerializer):
    url = serializers.CharField(read_only=True)

    class Meta:
        model = FileUpload
        fields = ["id", "file", "original_name", "category", "mime_type", "size",
                  "stored_path", "linked_type", "linked_id", "url", "created_at"]
        read_only_fields = ["original_name", "mime_type", "size", "stored_path", "url"]

    def validate_file(self, value):
        if value.size > MAX_FILE_SIZE:
            raise serializers.ValidationError(f"File exceeds the {MAX_FILE_SIZE // (1024*1024)}MB limit.")
        mime = getattr(value.file, "content_type", None)
        if mime and mime not in ALLOWED_MIME_TYPES:
            raise serializers.ValidationError(f"File type {mime} is not allowed.")
        return value

    def create(self, validated_data):
        school = self.context["school"]
        user = self.context["user"]
        uploaded = validated_data["file"]
        category = validated_data.get("category", FileCategory.OTHER)
        stored_path = upload_to_storage(uploaded, folder="uploads", category=category)

        obj = FileUpload.objects.create(
            school=school,
            file=uploaded,
            original_name=uploaded.name,
            category=category,
            mime_type=getattr(uploaded.file, "content_type", "") or "",
            size=uploaded.size or 0,
            stored_path=stored_path,
            uploaded_by=user,
            linked_type=validated_data.get("linked_type", ""),
            linked_id=validated_data.get("linked_id"),
        )
        return obj