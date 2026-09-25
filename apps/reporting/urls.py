from rest_framework.routers import DefaultRouter

from apps.reporting.views import ReportViewSet

router = DefaultRouter()
router.register(r"", ReportViewSet, basename="report")

urlpatterns = router.urls