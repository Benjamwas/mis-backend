"""Communication business services."""
from apps.communication.models import BroadcastRecipient


def _user_contact(user, channel):
    if channel in ("SMS", "WHATSAPP"):
        return user.person.phone or user.email
    return user.email or user.person.phone


def audience_recipients(campaign):
    """Resolve recipient rows for a campaign by its audience code."""
    from apps.hr.models import Employee
    from apps.identity.models import UserRole

    audience = (campaign.audience or "ALL").upper()
    rows = []

    role_codes_by_audience = {
        "PARENTS": ["PARENT"],
        "STUDENTS": ["STUDENT"],
        "TEACHERS": ["CLASS_TEACHER", "SUBJECT_TEACHER"],
        "ALL": ["PARENT", "STUDENT", "CLASS_TEACHER", "SUBJECT_TEACHER", "SCHOOL_ADMIN", "FINANCE_ADMIN", "HR_ADMIN"],
    }

    if audience in role_codes_by_audience:
        roles = UserRole.objects.filter(
            school=campaign.school, role__code__in=role_codes_by_audience[audience]
        ).select_related("user__person").distinct()
        for ur in roles:
            contact = _user_contact(ur.user, campaign.channel)
            if contact:
                rows.append(
                    BroadcastRecipient(campaign=campaign, user=ur.user, contact=contact, status="QUEUED")
                )
        return rows

    if audience == "STAFF":
        person_ids = set(
            Employee.objects.filter(school=campaign.school).values_list("person_id", flat=True)
        )
        roles = UserRole.objects.filter(
            school=campaign.school, user__person_id__in=person_ids
        ).select_related("user__person").distinct()
        for ur in roles:
            contact = _user_contact(ur.user, campaign.channel)
            if contact:
                rows.append(
                    BroadcastRecipient(campaign=campaign, user=ur.user, contact=contact, status="QUEUED")
                )
        return rows

    return []


def create_notification(user, title, body="", type_="INFO", entity_type="", entity_id=None, school=None):
    from apps.communication.models import Notification

    return Notification.objects.create(
        user=user, school=school, title=title, body=body, type=type_,
        entity_type=entity_type, entity_id=str(entity_id) if entity_id else "",
    )


def mark_notification_read(user, notification_id):
    from apps.communication.models import Notification
    from django.utils import timezone

    obj = Notification.objects.filter(user=user, pk=notification_id).first()
    if not obj:
        return None
    obj.is_read = True
    obj.read_at = timezone.now()
    obj.save(update_fields=["is_read", "read_at", "updated_at"])
    return obj


def unread_notification_count(user):
    from apps.communication.models import Notification

    return Notification.objects.filter(user=user, is_read=False).count()