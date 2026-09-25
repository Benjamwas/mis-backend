from rest_framework.routers import DefaultRouter

from apps.content.views import EventParticipantViewSet, EventViewSet

participants_router = DefaultRouter()
participants_router.register(r"participants", EventParticipantViewSet, basename="event-participant")

events_router = DefaultRouter()
events_router.register(r"", EventViewSet, basename="event")

# participants patterns first so they are not shadowed by the event detail match
urlpatterns = participants_router.urls + events_router.urls