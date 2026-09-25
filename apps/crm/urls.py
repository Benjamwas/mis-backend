from rest_framework.routers import DefaultRouter

from apps.crm.views import CrmInteractionViewSet, CrmLeadViewSet, CrmTaskViewSet, SchoolVisitViewSet

router = DefaultRouter()
router.register(r"leads", CrmLeadViewSet, basename="lead")
router.register(r"interactions", CrmInteractionViewSet, basename="crm-interaction")
router.register(r"tasks", CrmTaskViewSet, basename="crm-task")
router.register(r"visits", SchoolVisitViewSet, basename="school-visit")

urlpatterns = router.urls