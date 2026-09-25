from rest_framework.routers import DefaultRouter

from apps.hr.views import PayslipViewSet

router = DefaultRouter()
router.register(r"payslips", PayslipViewSet, basename="payslip")

urlpatterns = router.urls