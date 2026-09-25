"""Dashboard endpoints mounted under /api/v1/dashboards/."""
from rest_framework.routers import DefaultRouter

from apps.reporting.views import DashboardViewSet

router = DefaultRouter()
router.register(r"", DashboardViewSet, basename="dashboard")

urlpatterns = router.urls