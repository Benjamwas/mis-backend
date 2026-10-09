"""Misc academics endpoints (timetable)."""
from rest_framework.routers import DefaultRouter

from apps.academics.views import SchoolPeriodViewSet, TimetableSlotViewSet

router = DefaultRouter()
router.register(r"timetable/periods", SchoolPeriodViewSet, basename="school-period")
router.register(r"timetable/slots", TimetableSlotViewSet, basename="timetable-slot")

urlpatterns = router.urls
