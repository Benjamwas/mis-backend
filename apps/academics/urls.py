from rest_framework.routers import DefaultRouter

from apps.academics.views import (
    AssessmentScoreViewSet,
    AssessmentViewSet,
    AssignmentViewSet,
    ClassSubjectViewSet,
    EnrollmentViewSet,
    LearningRecommendationViewSet,
    ResultViewSet,
    SubjectViewSet,
    TeachingAssignmentViewSet,
)

router = DefaultRouter()
router.register(r"subjects", SubjectViewSet, basename="subject")
router.register(r"class-subjects", ClassSubjectViewSet, basename="class-subject")
router.register(r"teaching-assignments", TeachingAssignmentViewSet, basename="teaching-assignment")
router.register(r"enrollments", EnrollmentViewSet, basename="enrollment")
router.register(r"assignments", AssignmentViewSet, basename="assignment")
router.register(r"assessments", AssessmentViewSet, basename="assessment")
router.register(r"assessment-scores", AssessmentScoreViewSet, basename="assessment-score")
router.register(r"results", ResultViewSet, basename="result")
router.register(r"learning-recommendations", LearningRecommendationViewSet, basename="learning-recommendation")

urlpatterns = router.urls