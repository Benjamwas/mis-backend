from rest_framework import viewsets

from apps.common.permissions import HasPermission
from apps.common.viewsets import SchoolScopedViewSet
from apps.files.models import FileUpload
from apps.files.serializers import FileUploadSerializer


class FileUploadViewSet(SchoolScopedViewSet):
    queryset = FileUpload.objects.all()
    serializer_class = FileUploadSerializer
    permission_classes = [HasPermission]
    permission_code = "file.upload"
    audit_module = "files"
    audit_entity_type = "FileUpload"

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["school"] = self.get_school()
        ctx["user"] = self.request.user
        return ctx

    def perform_create(self, serializer):
        obj = serializer.save()
        self._audit("files.upload", obj, new_value={"category": obj.category, "original_name": obj.original_name})

    def perform_destroy(self, instance):
        self._audit("files.archive", instance, old_value={"id": str(instance.id)})
        instance.is_archived = True
        instance.save(update_fields=["is_archived", "updated_at"])