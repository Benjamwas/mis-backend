"""Services for students, parents and enrollments."""
import logging

from django.contrib.auth import get_user_model
from django.db import transaction

from apps.common.exceptions import ValidationFailedError
from apps.identity.models import Person, Role, RoleCode, UserRole
from apps.people.models import Parent

logger = logging.getLogger("apps.people")

User = get_user_model()


def create_student(school, person_data, admission_number, admission_date=None, **kwargs):
    """Create a Student with its Person (and parent link where provided)."""
    person = Person.objects.create(**person_data)
    from apps.people.models import Student

    return Student.objects.create(
        school=school, person=person, admission_number=admission_number,
        admission_date=admission_date or None, **kwargs
    )


def create_parent(school, person_data, occupation="", **kwargs):
    person = Person.objects.create(**person_data)
    from apps.people.models import Parent

    return Parent.objects.create(school=school, person=person, occupation=occupation, **kwargs)


@transaction.atomic
def link_parent_student(parent, student, relationship_type="GUARDIAN", is_primary_contact=False,
                        can_view_finance=True, can_view_academics=True):
    from apps.people.models import ParentStudent, RelationshipType

    rel, created = ParentStudent.objects.update_or_create(
        parent=parent,
        student=student,
        defaults={
            "relationship_type": relationship_type,
            "is_primary_contact": is_primary_contact,
            "can_view_finance": can_view_finance,
            "can_view_academics": can_view_academics,
        },
    )
    if is_primary_contact:
        ParentStudent.objects.filter(student=student).exclude(pk=rel.pk).update(is_primary_contact=False)
    return rel


def ensure_parent_login_user(parent, email, password=None):
    """Create or attach a portal User for a parent."""
    person = parent.person
    user = User.objects.filter(email__iexact=email).first()
    if user is None:
        user = User.objects.create_user(
            person=person, email=email, username=email.split("@")[0],
            password=password or User.objects.make_random_password(),
        )
    role = Role.objects.get(code=RoleCode.PARENT)
    UserRole.objects.get_or_create(user=user, role=role, school=parent.school)
    return user


def students_related_to_parent(parent) -> list:
    """Students linked to a parent within the parent's school."""
    qs = parent.children.select_related("student__person", "student__school")
    return [row.student for row in qs]


def parent_for_user(user, school=None):
    if not user or not getattr(user, "person_id", None):
        return None
    qs = Parent.objects.filter(person_id=user.person_id)
    if school is not None:
        qs = qs.filter(school=school)
    return qs.first()


def parent_student_ids(user, school=None):
    parent = parent_for_user(user, school)
    return list(parent.children.values_list("student_id", flat=True)) if parent else []


def student_guardian_users(student) -> list[User]:
    """All portal users whose parent accounts are linked to this student."""
    parent_ids = student.guardians.values_list("parent_id", flat=True)
    roles = UserRole.objects.filter(role__code=RoleCode.PARENT, school=student.school_id)
    parent_people = Parent.objects.filter(id__in=parent_ids).values_list("person_id", flat=True)
    return list(User.objects.filter(person_id__in=parent_people).values_list("id", flat=True))


def validate_admission_number_uniqueness(school, admission_number, exclude_id=None):
    from apps.people.models import Student

    qs = Student.objects.filter(school=school, admission_number__iexact=admission_number)
    if exclude_id:
        qs = qs.exclude(pk=exclude_id)
    if qs.exists():
        raise ValidationFailedError(f"Admission number {admission_number} already exists.", code="DUPLICATE_ADMISSION_NUMBER", status_code=409)
