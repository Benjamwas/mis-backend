from django.urls import path

from apps.admissions.public import PublicApplicationTrackView, PublicApplicationView

urlpatterns = [
    path("public/admissions/applications/", PublicApplicationView.as_view()),
    path("public/admissions/track/", PublicApplicationTrackView.as_view()),
]
