from rest_framework.routers import DefaultRouter

from apps.finance.views import PaymentViewSet

router = DefaultRouter()
router.register(r"", PaymentViewSet, basename="payment")

urlpatterns = router.urls