"""Misc people endpoints (medical records)."""
from rest_framework.routers import DefaultRouter

from apps.people.views import MedicalRecordViewSet

router = DefaultRouter()
router.register(r"medical-records", MedicalRecordViewSet, basename="medical-record")

urlpatterns = router.urls
