from rest_framework.routers import DefaultRouter

from apps.hr.views import (
    DepartmentViewSet,
    DutyAssignmentViewSet,
    DutyViewSet,
    EmployeeViewSet,
    HrTicketViewSet,
    LeaveRequestViewSet,
    LeaveTypeViewSet,
    PayrollPeriodViewSet,
)

router = DefaultRouter()
router.register(r"departments", DepartmentViewSet, basename="department")
router.register(r"employees", EmployeeViewSet, basename="employee")
router.register(r"leave-types", LeaveTypeViewSet, basename="leave-type")
router.register(r"leave-requests", LeaveRequestViewSet, basename="leave-request")
router.register(r"payroll-periods", PayrollPeriodViewSet, basename="payroll-period")
router.register(r"duties", DutyViewSet, basename="duty")
router.register(r"duty-assignments", DutyAssignmentViewSet, basename="duty-assignment")
router.register(r"tickets", HrTicketViewSet, basename="hr-ticket")

# Django will treat /hr/ as the prefix; attendance clock routes already under /attendance/hr/
urlpatterns = router.urls