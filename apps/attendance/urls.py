from rest_framework.routers import DefaultRouter

from apps.attendance.views import AttendanceSessionViewSet, EmployeeAttendanceViewSet

router = DefaultRouter()
router.register(r"sessions", AttendanceSessionViewSet, basename="attendance-session")
router.register(r"hr", EmployeeAttendanceViewSet, basename="employee-attendance")

urlpatterns = router.urls