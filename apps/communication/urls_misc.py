from rest_framework.routers import DefaultRouter

from apps.communication.views import AnnouncementViewSet, BroadcastCampaignViewSet

router = DefaultRouter()
router.register(r"announcements", AnnouncementViewSet, basename="announcement")
router.register(r"campaigns", BroadcastCampaignViewSet, basename="campaign")

urlpatterns = router.urls