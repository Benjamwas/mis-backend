from rest_framework.routers import DefaultRouter

from apps.content.views import CmsPageViewSet, CmsPostViewSet

router = DefaultRouter()
router.register(r"pages", CmsPageViewSet, basename="cms-page")
router.register(r"posts", CmsPostViewSet, basename="cms-post")

urlpatterns = router.urls