"""Root URL configuration for the SALA API."""
from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.common.views import HealthView, ReadinessView

api_v1_patterns = [
    path("auth/", include("apps.identity.urls")),
    path("schools/", include("apps.schools.urls")),
    path("students/", include("apps.people.urls")),
    path("parents/", include("apps.people.urls_parents")),
    path("", include("apps.people.urls_misc")),
    path("subjects/", include("apps.academics.urls")),
    path("", include("apps.academics.urls_misc")),
    path("lms/", include("apps.lms.urls")),
    path("attendance/", include("apps.attendance.urls")),
    path("finance/", include("apps.finance.urls")),
    path("payments/", include("apps.finance.urls_payments")),
    path("webhooks/", include("apps.finance.urls_webhooks")),
    path("admissions/", include("apps.admissions.urls")),
    path("crm/", include("apps.crm.urls")),
    path("hr/", include("apps.hr.urls")),
    path("", include("apps.hr.urls_misc")),
    path("notifications/", include("apps.communication.urls")),
    path("", include("apps.communication.urls_misc")),
    path("cms/", include("apps.content.urls")),
    path("events/", include("apps.content.urls_events")),
    path("gallery/", include("apps.content.urls_gallery")),
    path("reports/", include("apps.reporting.urls")),
    path("audit/", include("apps.audit.urls")),
    path("files/", include("apps.files.urls")),
    path("search/", include("apps.reporting.urls_search")),
    path("dashboards/", include("apps.identity.urls_dashboards")),
    path("", include("apps.content.urls_public")),
]

urlpatterns = [
    path("health", HealthView.as_view(), name="health"),
    path("ready", ReadinessView.as_view(), name="readiness"),
    path("api/v1/", include(api_v1_patterns)),
    path("api/schema/", SpectacularAPIView.as_view(), name="api-schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="api-schema"), name="api-docs"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)