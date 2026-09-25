"""Reusable permission classes for the SALA backend.

- HasPermission: role/permission based (school-scoped).
- IsSchoolAdmin / IsSuperAdmin helpers.
- SchoolObjectPermission: object-level tenant isolation.
- ModuleEnabled: gates endpoints when a school disabled the module.
"""
from rest_framework import permissions

from apps.common.exceptions import ModuleDisabledError, TenantIsolationError
from apps.identity.services import module_enabled_for_school, resolve_school_context, user_has_permission


class HasPermission(permissions.BasePermission):
    """Grant access when the user holds `code` in the request's school context.

    The code is taken from the permission class (`code`) or, if unset, from the
    view's `permission_code` attribute.
    """

    code = None

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        code = self.code or getattr(view, "permission_code", None)
        if code is None:
            return True
        school = resolve_school_context(request)
        return user_has_permission(request.user, code, school_id=school.id if school else None)


class And(permissions.BasePermission):
    """All listed permissions must pass."""

    def __init__(self, *perms):
        self._perms = perms

    def has_permission(self, request, view):
        return all(p().has_permission(request, view) for p in self._perms)


class SchoolScopedPermission(permissions.BasePermission):
    """Super-admin or a user that belongs to the school."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        school = resolve_school_context(request)
        if request.user.is_superuser:
            return True
        return school is not None


class IsSchoolAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        from apps.identity.services import user_has_permission

        if not request.user or not request.user.is_authenticated:
            return False
        school = resolve_school_context(request)
        school_id = school.id if school else None
        return user_has_permission(request.user, "school.update", school_id=school_id)


class IsSuperAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user is not None and request.user.is_authenticated and request.user.is_superuser


class SchoolObjectPermission(permissions.BasePermission):
    """Ensure the object belongs to the caller's school context."""

    scope_field = "school"  # attribute name on instance, or a callable

    def has_object_permission(self, request, view, obj):
        if request.user.is_superuser:
            return True
        school = resolve_school_context(request)
        if school is None:
            return False
        owner = getattr(obj, self.scope_field, None)
        if callable(owner):
            owner = owner()
        owner_id = getattr(owner, "id", owner)
        if owner_id is None:
            # Fall back to traversing __school if present
            owner_id = getattr(getattr(obj, "school", None), "id", None)
        return owner_id == school.id


class ModuleEnabled(permissions.BasePermission):
    """Reject when the school has disabled the named module."""

    module = None
    message = "This feature is not enabled for the school."

    def has_permission(self, request, view):
        school = resolve_school_context(request)
        if school is None:
            return True
        return module_enabled_for_school(school, self.module)


class IsOwnerOrSuperUser(permissions.BasePermission):
    """Object-level: user owns the record (user FK) or is a super admin."""

    user_field = "user"

    def has_object_permission(self, request, view, obj):
        if request.user.is_superuser:
            return True
        owner = getattr(obj, self.user_field, None)
        owner_id = getattr(owner, "id", owner)
        return owner_id == request.user.id


def require_permission(request, code):
    """Convenience helper for service-layer calls that already have a request."""
    school = resolve_school_context(request)
    if not user_has_permission(request.user, code, school_id=school.id if school else None):
        from apps.common.exceptions import PermissionDeniedError

        raise PermissionDeniedError()


def require_school(request):
    """Return request school context or raise tenant error."""
    school = resolve_school_context(request)
    if request.user.is_superuser and school is None:
        return None
    if school is None:
        raise TenantIsolationError("A school context is required for this request.")
    return school


def require_module(school, module_code):
    if school is not None and not module_enabled_for_school(school, module_code):
        raise ModuleDisabledError()