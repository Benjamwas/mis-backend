from rest_framework.routers import DefaultRouter

from apps.people.views import ParentViewSet, StudentViewSet

router = DefaultRouter()
router.register(r"", StudentViewSet, basename="student")

urlpatterns = router.urls