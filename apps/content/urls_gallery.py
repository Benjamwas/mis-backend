from rest_framework.routers import DefaultRouter

from apps.content.views import GalleryAlbumViewSet

router = DefaultRouter()
router.register(r"", GalleryAlbumViewSet, basename="gallery-album")

urlpatterns = router.urls