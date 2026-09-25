from rest_framework.routers import DefaultRouter

from apps.finance.views import FeeStructureViewSet, InvoiceViewSet, ReceiptViewSet, StudentFeeAccountViewSet

router = DefaultRouter()
router.register(r"fees", FeeStructureViewSet, basename="fee-structure")
router.register(r"accounts", StudentFeeAccountViewSet, basename="student-fee-account")
router.register(r"invoices", InvoiceViewSet, basename="invoice")
router.register(r"receipts", ReceiptViewSet, basename="receipt")

urlpatterns = router.urls