from rest_framework.routers import DefaultRouter

from apps.schools.views import (
    AcademicYearViewSet,
    GradeLevelViewSet,
    ModuleViewSet,
    SchoolClassViewSet,
    SchoolModuleViewSet,
    SchoolViewSet,
    SettingsViewSet,
    TermViewSet,
)

router = DefaultRouter()
router.register(r"schools", SchoolViewSet, basename="school")
router.register(r"academic-years", AcademicYearViewSet, basename="academic-year")
router.register(r"terms", TermViewSet, basename="term")
router.register(r"grade-levels", GradeLevelViewSet, basename="grade-level")
router.register(r"classes", SchoolClassViewSet, basename="class")
router.register(r"modules", ModuleViewSet, basename="module")
router.register(r"school-modules", SchoolModuleViewSet, basename="school-module")
router.register(r"settings", SettingsViewSet, basename="settings")

urlpatterns = router.urls