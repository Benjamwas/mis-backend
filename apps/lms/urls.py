from rest_framework.routers import DefaultRouter

from apps.lms.views import LessonViewSet, QuizViewSet, ResourceViewSet, TopicProgressViewSet, TopicViewSet

router = DefaultRouter()
router.register(r"topics", TopicViewSet, basename="topic")
router.register(r"lessons", LessonViewSet, basename="lesson")
router.register(r"resources", ResourceViewSet, basename="resource")
router.register(r"progress", TopicProgressViewSet, basename="progress")
router.register(r"quizzes", QuizViewSet, basename="quiz")

urlpatterns = router.urls
