"""Academic business services: enrollments, results, dashboards and recommendations."""
import logging
from datetime import date

from django.db import transaction
from django.db.models import Count

from apps.common.exceptions import ConflictError, ValidationFailedError

logger = logging.getLogger("apps.academics")


# --------------------------------------------------------------------------
# Enrollments
# --------------------------------------------------------------------------
@transaction.atomic
def enroll_student(student, school_class, by=None, start_date=None):
    """Enroll a student in a class for the class's active academic year.

    If the student has an active enrollment, it is closed first (history preserved).
    """
    from apps.academics.models import Enrollment
    from apps.schools.models import AcademicYear

    year = school_class.academic_year
    if year.status == AcademicYear.Status.CLOSED:
        raise ConflictError("Cannot enroll into a closed academic year.", code="YEAR_CLOSED")

    if student.school_id != school_class.school_id:
        raise ConflictError("Student and class belong to different schools.", code="TENANT_ISOLATION")

    active = Enrollment.objects.filter(student=student, status=Enrollment.Status.ACTIVE).first()
    if active:
        if active.school_class_id == school_class.id:
            raise ConflictError("Student is already enrolled in this class.", code="ALREADY_ENROLLED")
        active.status = Enrollment.Status.COMPLETED
        active.end_date = date.today()
        active.save(update_fields=["status", "end_date", "updated_at"])

    enrollment = Enrollment.objects.create(
        school=student.school,
        student=student,
        school_class=school_class,
        academic_year=year,
        start_date=start_date or date.today(),
        status=Enrollment.Status.ACTIVE,
    )
    student.is_active = True
    student.status = "ACTIVE"
    student.save(update_fields=["is_active", "status", "updated_at"])
    return enrollment


@transaction.atomic
def transfer_student(enrollment, target_class_id, by=None):
    from apps.academics.models import Enrollment
    from apps.schools.models import SchoolClass

    if enrollment.school_id != enrollment.school_id:
        raise ConflictError("Target class belongs to a different school.", code="TENANT_ISOLATION")

    target = SchoolClass.objects.get(pk=target_class_id, school=enrollment.school)
    prev = enrollment.school_class

    enrollment.status = Enrollment.Status.TRANSFERRED_OUT
    enrollment.end_date = date.today()
    enrollment.save(update_fields=["status", "end_date", "updated_at"])

    new_enrollment = enroll_student(
        student=enrollment.student, school_class=target, by=by, start_date=date.today()
    )
    return new_enrollment


@transaction.atomic
def close_enrollment(enrollment, by=None):
    from apps.academics.models import Enrollment

    if enrollment.status != Enrollment.Status.ACTIVE:
        raise ConflictError("Only active enrollments can be closed.", code="ENROLLMENT_NOT_ACTIVE")
    enrollment.status = Enrollment.Status.COMPLETED
    enrollment.end_date = date.today()
    enrollment.save(update_fields=["status", "end_date", "updated_at"])
    from apps.people.models import Student

    Student.objects.filter(pk=enrollment.student_id).update(is_active=False)
    return enrollment


# --------------------------------------------------------------------------
# Assignments & grading
# --------------------------------------------------------------------------
def visible_assignments_for(student):
    """Assignments relevant to a student in their current active enrollment."""
    from apps.academics.models import Assignment

    enrollment = student.enrollments.filter(status="ACTIVE").select_related("school_class").first()
    if not enrollment:
        return Assignment.objects.none()
    return (
        Assignment.objects.filter(
            school=student.school_id,
            status="PUBLISHED",
            teaching_assignment__school_class_id=enrollment.school_class_id,
        )
        .select_related("teaching_assignment__subject", "teaching_assignment__school_class")
    )


def submit_assignment(assignment, student, content="", by=None):
    """Student submission. Returns (submission, created)."""
    from apps.academics.models import AssignmentSubmission

    if assignment.status != assignment.Status.PUBLISHED:
        raise ConflictError("Assignment is not open for submission.", code="ASSIGNMENT_NOT_OPEN")
    if assignment.school_id != student.school_id:
        raise ConflictError("Assignment and student belong to different schools.", code="TENANT_ISOLATION")

    submission, created = AssignmentSubmission.objects.get_or_create(
        assignment=assignment,
        student=student,
        defaults={
            "school": student.school,
            "submission_content": content,
            "submitted_at": _now_aware(),
            "status": AssignmentSubmission.Status.SUBMITTED,
        },
    )
    if not created:
        if submission.status == AssignmentSubmission.Status.GRADED:
            raise ConflictError("Submission already graded; cannot resubmit.", code="ALREADY_GRADED")
        submission.submission_content = content
        submission.submitted_at = _now_aware()
        submission.status = AssignmentSubmission.Status.SUBMITTED
        submission.save(update_fields=["submission_content", "submitted_at", "status", "updated_at"])
    return submission


def grade_submission(submission, marks, feedback="", graded_by=None):
    """Grade a submission. Validates marks against assignment max_marks."""
    from apps.academics.models import AssignmentGrade, AssignmentSubmission

    max_marks = submission.assignment.max_marks
    from decimal import Decimal

    marks_dec = Decimal(marks)
    if marks_dec < 0:
        raise ValidationFailedError("Marks cannot be negative.", code="INVALID_MARKS")
    if marks_dec > max_marks:
        raise ValidationFailedError(
            f"Marks cannot exceed {max_marks}.", code="MARKS_EXCEED_MAX", status_code=422
        )

    with transaction.atomic():
        AssignmentGrade.objects.filter(submission=submission).delete()
        AssignmentGrade.objects.create(
            submission=submission, graded_by=graded_by, marks=marks_dec, feedback=feedback or ""
        )
        submission.status = AssignmentSubmission.Status.GRADED
        submission.save(update_fields=["status", "updated_at"])
    return submission


# --------------------------------------------------------------------------
# Results
# --------------------------------------------------------------------------
@transaction.atomic
def publish_results(result_ids, school, by=None):
    """Validate a result set then publish; notify students/parents."""
    from apps.academics.models import StudentSubjectResult
    from apps.audit.services import audit_event
    from apps.communication.tasks import notify_users

    results = list(
        StudentSubjectResult.objects.select_related("student__person").filter(
            id__in=result_ids, school=school
        )
    )
    if not results:
        raise ValidationFailedError("No results supplied.", code="RESULT_SET_EMPTY")

    for r in results:
        if r.status == StudentSubjectResult.Status.PUBLISHED:
            raise ConflictError("One or more results are already published.", code="ALREADY_PUBLISHED")
        r.status = StudentSubjectResult.Status.PUBLISHED
    StudentSubjectResult.objects.bulk_update(results, ["status"])

    for r in results:
        audit_event(
            by, "result.publish", "academics", "StudentSubjectResult", str(r.id),
            school=school, new_value={"status": r.status},
        )

    # notify guardians + student
    from apps.people.services import student_guardian_users

    user_ids = set(student_guardian_users(results[0].student))
    student_user = results[0].student.person.users.filter(is_active=True).first()
    if student_user:
        user_ids.add(student_user.id)
    if user_ids:
        notify_users.delay(
            list(user_ids),
            title="Results Published",
            body="Your results have been published.",
            entity_type="StudentSubjectResult",
        )
    return results


def student_academic_summary(student):
    """Aggregated academic dashboard for a student."""
    from apps.academics.models import AssessmentScore, AssignmentSubmission, StudentSubjectResult
    from apps.lms.models import StudentTopicProgress
    from apps.schools.models import Term

    year = student.school.active_year() if student.school else None
    current_term = (
        Term.objects.filter(school=student.school_id, academic_year=year, status="ACTIVE")
        .select_related("academic_year")
        .first()
    )

    results = list(
        StudentSubjectResult.objects.filter(student=student, status="PUBLISHED")
        .select_related("subject", "term")
    )
    subject_performance = []
    strengths = []
    weaknesses = []
    for r in results:
        subject_performance.append({
            "subject": r.subject.name,
            "subject_id": r.subject_id,
            "term": r.term.name,
            "total_score": str(r.total_score),
            "grade": r.grade,
        })
        try:
            if float(r.total_score) >= 80:
                strengths.append(r.subject.name)
            elif float(r.total_score) < 50:
                weaknesses.append(r.subject.name)
        except (TypeError, ValueError):
            pass

    scores = AssessmentScore.objects.filter(student=student).select_related("assessment__teaching_assignment__subject")
    recent_assessments = [
        {
            "assessment": s.assessment.title,
            "score": str(s.score),
            "subject": s.assessment.teaching_assignment.subject.name,
        }
        for s in scores.order_by("-created_at")[:10]
    ]

    progress = StudentTopicProgress.objects.filter(student=student).select_related("topic")
    topic_progress = [
        {"topic": p.topic.name, "progress_percentage": p.progress_percentage, "status": p.status}
        for p in progress
    ]

    assignments = AssignmentSubmission.objects.filter(student=student).select_related("assignment")

    def _avg(rows):
        vals = [float(x["total_score"]) for x in rows if x.get("total_score") is not None]
        return round(sum(vals) / len(vals), 2) if vals else None

    overall = _avg(subject_performance)

    return {
        "current_term": _term_payload(current_term),
        "current_class": current_class_of(student),
        "overall_performance": overall,
        "subject_performance": subject_performance,
        "strengths": strengths,
        "weaknesses": weaknesses,
        "recent_assessments": recent_assessments,
        "assignments": [
            {"title": a.assignment.title, "status": a.status, "marks": _submission_marks(a)}
            for a in assignments.order_by("-created_at")[:10]
        ],
        "topic_progress": topic_progress,
        "attendance": _attendance_summary(student),
    }


def current_class_of(student):
    enrollment = student.enrollments.filter(status="ACTIVE").select_related("school_class__grade_level").first()
    if not enrollment:
        return None
    cls = enrollment.school_class
    return {"id": cls.id, "name": cls.display_name, "grade_level": cls.grade_level.name}


def _term_payload(term):
    if term is None:
        return None
    return {"id": term.id, "name": term.name, "academic_year": term.academic_year.name, "status": term.status}


def _submission_marks(submission):
    grade = submission.grades.first()
    return str(grade.marks) if grade else None


def _attendance_summary(student):
    from apps.attendance.models import StudentAttendance

    rows = StudentAttendance.objects.filter(student=student).values("status").annotate(total=Count("id"))
    summary = {r["status"]: r["total"] for r in rows}
    summary["total"] = sum(summary.values())
    return summary


def _now_aware():
    from django.utils import timezone

    return timezone.now()


def grading_queue(teacher_id, school):
    """Assignments awaiting grading for a teacher's teaching scope."""
    from apps.academics.models import AssignmentSubmission

    return (
        AssignmentSubmission.objects.filter(
            school=school,
            status__in=["SUBMITTED", "RETURNED"],
            assignment__teaching_assignment__teacher_id=teacher_id,
        )
        .select_related("assignment", "student__person")
        .order_by("submitted_at")
    )


def generate_learning_recommendations(student, school):
    """Rule-based learning recommendations.

    Rules use measurable data (topic progress, scores, missing assignments).
    No claim of AI; designed so an AI provider can replace the rule engine later.
    """
    from apps.academics.models import LearningRecommendation, Subject
    from apps.lms.models import StudentTopicProgress, Topic

    created = []
    # Rule 1: zero/very low progress topics -> recommend
    low_progress = StudentTopicProgress.objects.filter(
        student=student, progress_percentage__lt=25, status__in=["NOT_STARTED", "IN_PROGRESS"]
    ).select_related("topic")
    for p in low_progress[:5]:
        rec, was = LearningRecommendation.objects.get_or_create(
            student=student,
            topic=p.topic,
            reason="REVIEW_LOW_PROGRESS",
            defaults={
                "school": school,
                "subject": p.topic.subject,
                "detail": f"Topic {p.topic.name} is below 25% completion.",
                "priority": LearningRecommendation.Priority.MEDIUM,
                "status": LearningRecommendation.Status.ACTIVE,
            },
        )
        if was:
            created.append(rec)

    # Rule 2: assessments below 50% on a subject -> recommend strongest topic gaps
    low_scores = student.assessment_scores.filter(score__lt=50).select_related(
        "assessment__teaching_assignment__subject"
    )
    for s in low_scores[:5]:
        subject = s.assessment.teaching_assignment.subject
        weak_topics = Topic.objects.filter(subject=subject).order_by("order_number")[:1]
        for topic in weak_topics:
            rec, was = LearningRecommendation.objects.get_or_create(
                student=student,
                topic=topic,
                reason="REVIEW_WEAK_SCORE",
                defaults={
                    "school": school,
                    "subject": subject,
                    "detail": f"Scored {s.score} on {s.assessment.title}.",
                    "priority": LearningRecommendation.Priority.HIGH,
                    "status": LearningRecommendation.Status.ACTIVE,
                },
            )
            if was:
                created.append(rec)

    # Rule 3: missing assignments (never submitted, published & due)
    from apps.academics.models import Assignment, AssignmentSubmission

    enrollment = student.enrollments.filter(status="ACTIVE").select_related("school_class").first()
    if enrollment:
        missing = Assignment.objects.filter(
            school=school,
            status="PUBLISHED",
            teaching_assignment__school_class_id=enrollment.school_class_id,
        ).exclude(submissions__student=student)
        for a in missing[:5]:
            rec, was = LearningRecommendation.objects.get_or_create(
                student=student,
                topic=a.topic,
                reason="MISSING_ASSIGNMENT",
                defaults={
                    "school": school,
                    "subject": a.teaching_assignment.subject,
                    "detail": f"Assignment '{a.title}' is unsubmitted.",
                    "priority": LearningRecommendation.Priority.MEDIUM,
                    "status": LearningRecommendation.Status.ACTIVE,
                },
            )
            if was:
                created.append(rec)

    return created