from itertools import groupby

from django.db.models import Count
from rest_framework import serializers, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.models import AuditLog
from apps.common.permissions import HasPermission
from apps.identity.services import resolve_school_context


class AuditLogSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source="user.full_name", read_only=True)
    school_name = serializers.CharField(source="school.name", read_only=True)

    class Meta:
        model = AuditLog
        fields = ["id", "school", "school_name", "user", "user_name", "action", "module",
                  "entity_type", "entity_id", "old_value", "new_value", "ip_address", "user_agent", "created_at"]


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = AuditLog.objects.all()
    serializer_class = AuditLogSerializer
    permission_classes = [HasPermission]
    permission_code = "audit.read"

    def get_queryset(self):
        qs = AuditLog.objects.select_related("user", "school")
        user = self.request.user
        if user.is_superuser:
            pass  # platform-wide visibility
        else:
            school = resolve_school_context(self.request)
            qs = qs.filter(school=school) if school else qs.none()
        module = self.request.query_params.get("module")
        action = self.request.query_params.get("action")
        entity = self.request.query_params.get("entity_type")
        if module:
            qs = qs.filter(module=module)
        if action:
            qs = qs.filter(action=action)
        if entity:
            qs = qs.filter(entity_type=entity)
        return qs


class AuditSummaryView(APIView):
    """Counts grouped by module+action for dashboards."""

    permission_classes = [HasPermission]
    permission_code = "audit.read"

    def get(self, request):
        user = request.user
        if not user.is_superuser:
            school = resolve_school_context(request)
            rows = AuditLog.objects.filter(school=school)
        else:
            rows = AuditLog.objects.all()
        counts = list(rows.values("module", "action").annotate(count=Count("id")).order_by("module", "action"))
        by_module = {}
        for row in counts:
            by_module.setdefault(row["module"], {})[row["action"]] = row["count"]
        return Response({"by_module": by_module, "total": rows.count()})