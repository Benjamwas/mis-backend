from rest_framework.routers import DefaultRouter

from apps.admissions.views import AdmissionApplicationViewSet, ApplicantViewSet

router = DefaultRouter()
router.register(r"applicants", ApplicantViewSet, basename="applicant")
router.register(r"applications", AdmissionApplicationViewSet, basename="application")

urlpatterns = router.urls