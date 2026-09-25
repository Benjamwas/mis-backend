"""Identity services: school context resolution and permission checking.

Shared permission logic used by roles, view permissions, and object-level checks.
"""
from django.contrib.auth import get_user_model

from apps.identity.models import Permission, Role, UserGrant, UserRole


def get_user_school_ids(user):
    """Every school the user has a scoped role in. SUPER_ADMIN -> all schools (empty = platform)."""
    if user.is_superuser:
        return []
    return list(
        UserRole.objects.filter(user=user, school__isnull=False).values_list("school_id", flat=True).distinct()
    )


def get_user_schools(user):
    from apps.schools.models import School

    ids = get_user_school_ids(user)
    if user.is_superuser:
        return list(School.objects.all())
    return list(School.objects.filter(id__in=ids))


def resolve_school_context(request):
    """Determine which school a request is scoped to.

    Rules (never trust the client blindly):
    - SUPER_ADMIN with no school membership may act platform-wide.
    - If the user belongs to exactly one school, that school is used.
    - If the user belongs to multiple schools, the `X-School-Id` header must
      name one of their schools; otherwise the request is rejected.
    """
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return None
    if user.is_superuser:
        header = request.headers.get("X-School-Id")
        if header:
            from apps.schools.models import School

            try:
                return School.objects.get(pk=header)
            except School.DoesNotExist:
                return None
        return None  # platform scope

    school_ids = get_user_school_ids(user)
    if len(school_ids) == 1:
        from apps.schools.models import School

        return School.objects.filter(pk=school_ids[0]).first()
    if len(school_ids) > 1:
        header = request.headers.get("X-School-Id")
        if header and header in school_ids:
            from apps.schools.models import School

            return School.objects.filter(pk=header).first()
        return None  # ambiguous -> caller must provide header
    return None


def effective_permission_codes(user, school_id=None):
    """Set of permission codes the user holds for the given school context."""
    result = set()

    if getattr(user, "is_superuser", False):
        from apps.identity.seed import PERMISSION_CODES

        return set(PERMISSION_CODES)

    role_ids = None
    if school_id is not None:
        role_ids = UserRole.objects.filter(user=user, school_id=school_id).values_list("role_id", flat=True)
    else:
        # platform-role or school-wide: SUPER_ADMIN-like roles, plus all school roles without school context
        role_ids = UserRole.objects.filter(user=user).values_list("role_id", flat=True)

    perms = (
        Role.objects.filter(id__in=role_ids)
        .prefetch_related("permissions")
    )
    for role in perms:
        for p in role.permissions.all():
            result.add(p.code)

    grants = UserGrant.objects.filter(user=user)
    if school_id is not None:
        grants = grants.filter(school_id=school_id)
    for g in grants:
        result.add(g.permission.code)

    return result


def user_has_permission(user, code: str, school_id=None) -> bool:
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return code in effective_permission_codes(user, school_id)


def module_enabled_for_school(school, module_code: str) -> bool:
    """Gate: the school_modules config must enable the module."""
    if school is None:
        return True
    from apps.schools.models import SchoolModule

    try:
        sm = SchoolModule.objects.select_related("module").get(school=school, module__code=module_code)
        return sm.enabled
    except SchoolModule.DoesNotExist:
        # Default: modules are enabled unless explicitly disabled.
        return True


def get_user_model_eager():  # pragma: no cover - helper
    return get_user_model()


def assign_role(user, role_code: str, school=None, by=None):
    """Idempotent role assignment. `by` is the acting admin user (for audit)."""
    role = Role.objects.get(code=role_code)
    UserRole.objects.get_or_create(user=user, role=role, school=school)
    return role


def remove_role(user, role_code: str, school=None):
    role = Role.objects.get(code=role_code)
    UserRole.objects.filter(user=user, role=role, school=school).delete()