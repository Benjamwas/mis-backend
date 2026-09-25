"""Admissions business services: status transitions and enrollment."""
import logging
from datetime import date

from django.db import transaction
from django.utils import timezone

from apps.common.exceptions import ConflictError, ValidationFailedError
from apps.admissions.models import (
    AdmissionApplication,
    Applicant,
    ApplicationStatusHistory,
)

logger = logging.getLogger("apps.admissions")

_STATUS = AdmissionApplication

ALLOWED_TRANSITIONS = {
    _STATUS.DRAFT: {_STATUS.SUBMITTED, _STATUS.WITHDRAWN},
    _STATUS.SUBMITTED: {_STATUS.UNDER_REVIEW, _STATUS.REJECTED, _STATUS.WITHDRAWN, _STATUS.WAITLISTED},
    _STATUS.UNDER_REVIEW: {_STATUS.SHORTLISTED, _STATUS.REJECTED, _STATUS.INTERVIEW, _STATUS.WITHDRAWN, _STATUS.DECISION_PENDING},
    _STATUS.SHORTLISTED: {_STATUS.INTERVIEW, _STATUS.REJECTED, _STATUS.WITHDRAWN, _STATUS.ACCEPTED, _STATUS.DECISION_PENDING},
    _STATUS.INTERVIEW: {_STATUS.DECISION_PENDING, _STATUS.ACCEPTED, _STATUS.REJECTED, _STATUS.WAITLISTED, _STATUS.WITHDRAWN},
    _STATUS.DECISION_PENDING: {_STATUS.ACCEPTED, _STATUS.REJECTED, _STATUS.WAITLISTED, _STATUS.WITHDRAWN},
    _STATUS.ACCEPTED: {_STATUS.ENROLLED, _STATUS.WITHDRAWN, _STATUS.WAITLISTED},
    _STATUS.REJECTED: set(),
    _STATUS.WAITLISTED: {_STATUS.ACCEPTED, _STATUS.REJECTED, _STATUS.WITHDRAWN},
    _STATUS.ENROLLED: {_STATUS.WITHDRAWN},
    _STATUS.WITHDRAWN: set(),
}


def generate_application_number(school) -> str:
    year = date.today().year
    count = AdmissionApplication.objects.filter(school=school).count() + 1
    return f"APP-{year}-{count:04d}"


@transaction.atomic
def submit_application(application, by=None):
    application.status = AdmissionApplication.SUBMITTED
    application.submitted_at = timezone.now()
    application.save(update_fields=["status", "submitted_at", "updated_at"])
    ApplicationStatusHistory.objects.create(
        school=application.school, application=application, from_status=AdmissionApplication.DRAFT,
        to_status=AdmissionApplication.SUBMITTED, changed_by=by,
    )
    applicant = application.applicant
    if not (applicant.guardian_name or applicant.guardian_phone or applicant.guardian_email):
        raise ValidationFailedError(
            "Applicant guardian contact details are required before submitting.",
            code="GUARDIAN_CONTACT_REQUIRED",
        )
    applicant.status = Applicant.Status.APPLIED
    applicant.save(update_fields=["status", "updated_at"])
    return application


def update_application_status(application, new_status, by=None, comment="") -> AdmissionApplication:
    if new_status == application.status:
        return application
    allowed = ALLOWED_TRANSITIONS.get(application.status, set())
    if new_status not in allowed:
        raise ConflictError(
            f"Cannot move application from {application.status} to {new_status}.",
            code="INVALID_STATUS_TRANSITION",
        )
    from_status = application.status
    application.status = new_status
    if new_status in (AdmissionApplication.ACCEPTED, AdmissionApplication.REJECTED, AdmissionApplication.WAITLISTED):
        application.decided_at = timezone.now()
    application.decision_comment = comment or application.decision_comment
    application.save(update_fields=["status", "decided_at", "decision_comment", "updated_at"])
    ApplicationStatusHistory.objects.create(
        school=application.school, application=application, from_status=from_status,
        to_status=new_status, changed_by=by, comment=comment,
    )
    return application


@transaction.atomic
def enroll_accepted_application(application, by=None):
    """Create the Student record from an accepted application using people services."""
    if application.status != AdmissionApplication.ACCEPTED:
        raise ConflictError("Only accepted applications can be enrolled.", code="APPLICATION_NOT_ACCEPTED")

    applicant = application.applicant

    from apps.people.services import create_student

    admission_number = (
        f"ADM-{date.today().year}-"
        f"{Student_count_for_school(application.school) + 1:04d}"
    )
    person_data = {
        "first_name": applicant.first_name,
        "last_name": applicant.last_name,
        "email": applicant.email,
        "phone": applicant.phone,
        "date_of_birth": applicant.date_of_birth,
        "gender": applicant.gender,
    }
    student = create_student(
        school=application.school,
        person_data=person_data,
        admission_number=admission_number,
        admission_date=date.today(),
    )

    from apps.academics.services import enroll_student
    from apps.schools.models import GradeLevel, SchoolClass

    grade = GradeLevel.objects.filter(school=application.school, id=application.grade_level_id).first()
    school_class = None
    if not grade:
        raise ValidationFailedError("Application grade level not found.", code="GRADE_NOT_FOUND")
    school_class = (
        SchoolClass.objects.filter(school=application.school, grade_level=grade, status=SchoolClass.Status.ACTIVE)
        .order_by("name")
        .first()
    )
    if not school_class:
        raise ValidationFailedError(
            "No active class exists for the target grade level.",
            code="NO_ACTIVE_CLASS",
        )
    enroll_student(student=student, school_class=school_class, by=by)

    application.status = AdmissionApplication.ENROLLED
    application.save(update_fields=["status", "updated_at"])
    ApplicationStatusHistory.objects.create(
        school=application.school, application=application, from_status=AdmissionApplication.ACCEPTED,
        to_status=AdmissionApplication.ENROLLED, changed_by=by, comment="Student record created",
    )
    return student


def Student_count_for_school(school) -> int:
    from apps.people.models import Student

    return Student.objects.filter(school=school).count()


def create_application(*, school, academic_year, grade_level, term=None, notes="", by=None, applicant=None, **applicant_data) -> AdmissionApplication:
    with transaction.atomic():
        applicant = applicant or Applicant.objects.create(school=school, **applicant_data)
        application = AdmissionApplication.objects.create(
            school=school, applicant=applicant, academic_year=academic_year, grade_level=grade_level,
            term=term, application_number=generate_application_number(school), notes=notes,
        )
    return application