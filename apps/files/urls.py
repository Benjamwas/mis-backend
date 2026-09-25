from rest_framework.routers import DefaultRouter

from apps.files.views import FileUploadViewSet

router = DefaultRouter()
router.register(r"uploads", FileUploadViewSet, basename="file-upload")

urlpatterns = router.urls