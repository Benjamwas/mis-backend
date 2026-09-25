"""Shared base ViewSets enforcing tenant isolation and the SALA envelope."""
import logging

from django.db import transaction
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.audit.services import audit
from apps.common.exceptions import PermissionDeniedError
from apps.common.permissions import IsSuperAdmin
from apps.identity.services import resolve_school_context, user_has_permission

logger = logging.getLogger("apps.common")


class SchoolScopedViewSet(viewsets.ModelViewSet):
    """Base for school-scoped resources.

    - Filters the queryset by the caller's resolved school (tenant isolation).
    - Super admins with no school header operate platform-wide against the
      full set only where the serializer allows it; otherwise they must select
      a school.
    """

    audit_actions = {}  # {action_name: {"module":..., "entity":...}} optional
    permission_code = None  # optional granular code enforced in list/create

    def get_school(self):
        return resolve_school_context(self.request)

    def get_permissions(self):
        perms = super().get_permissions()
        return perms

    def check_permission_code(self, code):
        if getattr(self.request.user, "is_superuser", False):
            return True
        school = self.get_school()
        if not user_has_permission(self.request.user, code, school_id=school.id if school else None):
            raise PermissionDeniedError()

    def filter_queryset_by_school(self, qs):
        school = self.get_school()
        if self.request.user.is_superuser and school is None:
            return qs
        if school is None:
            return qs.none()
        return qs.filter(school=school)

    def get_queryset(self):
        qs = super().get_queryset()
        return self.filter_queryset_by_school(qs)

    def _audit(self, action, obj, **old_new):
        audit(
            self.request,
            self.request.user,
            action,
            module=getattr(self, "audit_module", "app"),
            entity_type=getattr(self, "audit_entity_type", self.queryset.model.__name__),
            entity_id=getattr(obj, "id", ""),
            school=getattr(obj, "school", None),
            **old_new,
        )


class PlatformAdminViewSet(viewsets.ModelViewSet):
    """Base for SUPER_ADMIN-only platform administration."""