"""CRM business services: lead lifecycle, interactions, conversions and visits."""
import logging

from django.db import transaction
from django.utils import timezone

from apps.common.exceptions import ConflictError, ValidationFailedError
from apps.crm.models import CrmInteraction, CrmLead, CrmTask, SchoolVisit

logger = logging.getLogger("apps.crm")


def create_lead(*, school, first_name="", last_name="", email="", phone="", source="OTHER",
                assigned_to=None, notes="", by=None, **kwargs) -> CrmLead:
    existing = CrmLead.objects.filter(school=school).exclude(status__in=["LOST", "ARCHIVED"])
    if email:
        existing = existing.filter(email__iexact=email)
    elif phone:
        existing = existing.filter(phone=phone)
    else:
        existing = existing.none()
    if existing.exists():
        raise ConflictError("A lead with this contact already exists.", code="LEAD_EXISTS")

    return CrmLead.objects.create(
        school=school, first_name=first_name, last_name=last_name, email=email, phone=phone,
        source=source, assigned_to=assigned_to, notes=notes, **kwargs,
    )


@transaction.atomic
def log_interaction(*, school, lead, user, interaction_type, notes="", outcome="", scheduled_at=None) -> CrmInteraction:
    interaction = CrmInteraction.objects.create(
        school=school, lead=lead, user=user, interaction_type=interaction_type,
        notes=notes, outcome=outcome, scheduled_at=scheduled_at,
    )
    lead.last_contacted_at = timezone.now()
    if lead.status == CrmLead.Status.NEW:
        lead.status = CrmLead.Status.CONTACTED
    lead.save(update_fields=["last_contacted_at", "status", "updated_at"])

    if outcome == CrmInteraction.Outcome.BOOKED_VISIT:
        SchoolVisit.objects.create(
            school=school, lead=lead, student_name=lead.full_name, parent_name="",
            parent_phone=lead.phone, parent_email=lead.email, visit_date=scheduled_at or timezone.now(),
        )
    return interaction


@transaction.atomic
def convert_lead(lead, by=None, create_student=True):
    if lead.status == CrmLead.Status.CONVERTED:
        raise ConflictError("Lead is already converted.", code="LEAD_CONVERTED")
    if lead.status in (CrmLead.Status.LOST, CrmLead.Status.ARCHIVED):
        raise ConflictError("Cannot convert a lost or archived lead.", code="LEAD_NOT_ACTIVE")

    student = None
    if create_student:
        from apps.people.models import Student
        from apps.people.services import create_student

        person_data = {}
        person = lead.person
        if person:
            person_data = {"first_name": person.first_name, "last_name": person.last_name,
                           "email": person.email or lead.email, "phone": person.phone or lead.phone}
        else:
            person_data = {"first_name": lead.first_name, "last_name": lead.last_name,
                           "email": lead.email, "phone": lead.phone}
        admission_number = f"ADM-{timezone.now().year}-{Student.objects.filter(school=lead.school).count() + 1:04d}"
        student = create_student(
            school=lead.school, person_data=person_data, admission_number=admission_number,
            admission_date=timezone.localdate(),
        )
        lead.converted_to_student = student
        lead.person = student.person

    lead.status = CrmLead.Status.CONVERTED
    lead.save(update_fields=["status", "converted_to_student", "person", "updated_at"])

    from apps.communication.tasks import notify_users

    return lead


def schedule_follow_up(lead, follow_up_date, by=None):
    lead.follow_up_date = follow_up_date
    lead.save(update_fields=["follow_up_date", "updated_at"])
    CrmTask.objects.create(
        school=lead.school, lead=lead, title=f"Follow-up on {lead.full_name}",
        due_date=follow_up_date, assigned_to=lead.assigned_to or by,
        created_by=by,
    )
    return lead


def mark_contacted(lead, by=None):
    lead.status = CrmLead.Status.CONTACTED
    lead.last_contacted_at = timezone.now()
    lead.save(update_fields=["status", "last_contacted_at", "updated_at"])
    return lead


def add_task(*, school, lead, title, description="", due_date=None, assigned_to=None, by=None) -> CrmTask:
    return CrmTask.objects.create(
        school=school, lead=lead, title=title, description=description, due_date=due_date,
        assigned_to=assigned_to, created_by=by,
    )


def complete_task(task, by=None):
    if task.status == CrmTask.Status.DONE:
        raise ConflictError("Task is already done.", code="TASK_DONE")
    task.status = CrmTask.Status.DONE
    task.save(update_fields=["status", "updated_at"])
    return task


def cancel_task(task, by=None):
    task.status = CrmTask.Status.CANCELLED
    task.save(update_fields=["status", "updated_at"])
    return task


def update_visit_status(visit, new_status, by=None, notes=""):
    allowed = {
        SchoolVisit.Status.SCHEDULED: {SchoolVisit.Status.ATTENDED, SchoolVisit.Status.NO_SHOW,
                                       SchoolVisit.Status.CANCELLED, SchoolVisit.Status.RESCHEDULED},
        SchoolVisit.Status.ATTENDED: {SchoolVisit.Status.CANCELLED},
        SchoolVisit.Status.RESCHEDULED: {SchoolVisit.Status.ATTENDED, SchoolVisit.Status.NO_SHOW,
                                         SchoolVisit.Status.CANCELLED},
        SchoolVisit.Status.NO_SHOW: {SchoolVisit.Status.SCHEDULED},
    }
    if new_status not in allowed.get(visit.status, set()):
        raise ConflictError(
            f"Cannot move visit from {visit.status} to {new_status}.", code="INVALID_VISIT_TRANSITION"
        )
    visit.status = new_status
    if notes:
        visit.notes = notes
    visit.save(update_fields=["status", "notes", "updated_at"])
    return visit