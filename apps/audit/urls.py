from django.urls import path

from apps.audit.views import AuditLogViewSet, AuditSummaryView

urlpatterns = [
    path("logs", AuditLogViewSet.as_view({"get": "list"}), name="audit-logs"),
    path("summary", AuditSummaryView.as_view(), name="audit-summary"),
]