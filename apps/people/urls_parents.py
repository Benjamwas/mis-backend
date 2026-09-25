from rest_framework.routers import DefaultRouter

from apps.people.views import ParentViewSet

router = DefaultRouter()
router.register(r"", ParentViewSet, basename="parent")

urlpatterns = router.urls