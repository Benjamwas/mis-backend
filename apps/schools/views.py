"""Schools, academic structure and module views."""
from django.db import transaction
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.audit.services import audit
from apps.common.exceptions import ValidationFailedError
from apps.common.permissions import HasPermission, IsSchoolAdmin, IsSuperAdmin, SchoolScopedPermission
from apps.common.viewsets import PlatformAdminViewSet, SchoolScopedViewSet
from apps.identity.services import resolve_school_context
from apps.schools.models import (
    AcademicYear,
    GradeLevel,
    Module,
    School,
    SchoolClass,
    SchoolModule,
    SchoolSettings,
    Term,
)
from apps.schools.serializers import (
    AcademicYearSerializer,
    GradeLevelSerializer,
    ModuleSerializer,
    SchoolClassSerializer,
    SchoolDetailSerializer,
    SchoolModuleSerializer,
    SchoolSerializer,
    SchoolSettingsSerializer,
    TermSerializer,
)


class SchoolViewSet(viewsets.ModelViewSet):
    """Schools: superadmins manage all; school admins read/update their own school profile."""

    queryset = School.objects.all()
    serializer_class = SchoolSerializer
    permission_classes = [SchoolScopedPermission]

    def get_serializer_class(self):
        if self.action == "retrieve":
            return SchoolDetailSerializer
        return SchoolSerializer

    def get_permissions(self):
        if self.action in ("create", "destroy"):
            from rest_framework.permissions import IsAdminUser

            return [IsAdminUser()]
        if self.action in ("update", "partial_update"):
            return [IsSchoolAdmin()]
        return super().get_permissions()

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user.is_superuser:
            return qs
        school = resolve_school_context(self.request)
        return qs.filter(id=school.id) if school else qs.none()

    @action(detail=False, methods=["get"], permission_classes=[SchoolScopedPermission])
    def me(self, request):
        school = resolve_school_context(request)
        if school is None:
            raise ValidationFailedError("No school context.", code="NO_SCHOOL_CONTEXT", status_code=404)
        return Response(SchoolDetailSerializer(school).data)

    def perform_create(self, serializer):
        obj = serializer.save()
        audit(self.request, self.request.user, "school.create", "school", "School", str(obj.id),
              new_value={"name": obj.name, "code": obj.code})

    def perform_update(self, serializer):
        obj = serializer.save()
        audit(self.request, self.request.user, "school.update", "school", "School", str(obj.id),
              new_value={"name": obj.name, "status": obj.status})


class AcademicYearViewSet(SchoolScopedViewSet):
    queryset = AcademicYear.objects.all()
    serializer_class = AcademicYearSerializer
    permission_classes = [HasPermission]
    permission_code = "class.read"
    audit_module = "academics"
    audit_entity_type = "AcademicYear"

    def get_permissions(self):
        if self.action in ("create", "update", "partial_update", "destroy"):
            self.permission_code = "school.update"
        return super().get_permissions()

    def perform_create(self, serializer):
        obj = serializer.save()
        self._audit("academic_year.create", obj, new_value={"name": obj.name})

    def perform_update(self, serializer):
        obj = serializer.save()
        self._audit("academic_year.update", obj, new_value={"name": obj.name})

    @action(detail=False, methods=["get"])
    def current(self, request):
        school = self.get_school()
        if school is None:
            return Response(AcademicYearSerializer(AcademicYear.objects.none(), many=True).data)
        year = school.active_year()
        return Response(AcademicYearSerializer(year).data if year else None)


class TermViewSet(SchoolScopedViewSet):
    queryset = Term.objects.all()
    serializer_class = TermSerializer
    permission_classes = [HasPermission]
    permission_code = "class.read"
    audit_module = "academics"
    audit_entity_type = "Term"

    def get_queryset(self):
        qs = super().get_queryset()
        year = self.request.query_params.get("academic_year")
        if year:
            qs = qs.filter(academic_year_id=year)
        return qs.select_related("academic_year")

    def get_permissions(self):
        if self.action in ("create", "update", "partial_update", "destroy"):
            self.permission_code = "school.update"
        return super().get_permissions()

    def perform_create(self, serializer):
        obj = serializer.save()
        self._audit("term.create", obj, new_value={"name": obj.name})


class GradeLevelViewSet(SchoolScopedViewSet):
    queryset = GradeLevel.objects.all()
    serializer_class = GradeLevelSerializer
    permission_classes = [HasPermission]
    permission_code = "class.read"
    audit_module = "academics"
    audit_entity_type = "GradeLevel"

    def get_permissions(self):
        if self.action in ("create", "update", "partial_update", "destroy"):
            self.permission_code = "school.update"
        return super().get_permissions()

    def perform_create(self, serializer):
        obj = serializer.save()
        self._audit("grade_level.create", obj, new_value={"name": obj.name})


class SchoolClassViewSet(SchoolScopedViewSet):
    queryset = SchoolClass.objects.all()
    serializer_class = SchoolClassSerializer
    permission_classes = [HasPermission]
    permission_code = "class.read"
    audit_module = "academics"
    audit_entity_type = "SchoolClass"

    def get_queryset(self):
        qs = super().get_queryset().select_related("academic_year", "grade_level", "class_teacher")
        year = self.request.query_params.get("academic_year")
        grade = self.request.query_params.get("grade_level")
        if year:
            qs = qs.filter(academic_year_id=year)
        if grade:
            qs = qs.filter(grade_level_id=grade)
        return qs

    def get_permissions(self):
        if self.action in ("create", "update", "partial_update", "destroy"):
            self.permission_code = "class.update"
        return super().get_permissions()

    def perform_create(self, serializer):
        obj = serializer.save()
        self._audit("class.create", obj, new_value={"name": obj.display_name})

    def perform_update(self, serializer):
        obj = serializer.save()
        self._audit("class.update", obj, new_value={"name": obj.display_name})

    @action(detail=True, methods=["get"], permission_classes=[HasPermission])
    def students(self, request, pk=None):
        from apps.people.serializers import StudentSerializer

        cls = self.get_object()
        students = cls.enrollments.filter(status="ACTIVE").select_related("student__person")
        data = [StudentSerializer(e.student).data for e in students]
        return Response(data)


class SchoolModuleViewSet(SchoolScopedViewSet):
    queryset = SchoolModule.objects.all()
    serializer_class = SchoolModuleSerializer
    permission_classes = [IsSuperAdmin]
    permission_code = "module.manage"
    audit_module = "platform"
    audit_entity_type = "SchoolModule"

    def get_queryset(self):
        qs = SchoolModule.objects.select_related("module", "school")
        if not self.request.user.is_superuser:
            school = self.get_school()
            qs = qs.filter(school=school) if school else qs.none()
        return qs

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["school"] = self.get_school()
        return ctx

    def perform_create(self, serializer):
        school = self.get_school()
        if serializer.validated_data.get("school") is None and school is not None:
            serializer.validated_data["school"] = school
        obj = serializer.save()
        self._audit("module.configure", obj, new_value={"module": obj.module.code, "enabled": obj.enabled})

    def perform_update(self, serializer):
        obj = serializer.save()
        self._audit("module.configure", obj, new_value={"module": obj.module.code, "enabled": obj.enabled})


class ModuleViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Module.objects.all()
    serializer_class = ModuleSerializer
    permission_classes = [HasPermission]
    permission_code = "module.read"


class SettingsViewSet(viewsets.ModelViewSet):
    queryset = SchoolSettings.objects.all()
    serializer_class = SchoolSettingsSerializer
    permission_classes = [HasPermission]
    permission_code = "school.update"
    audit_module = "school"
    audit_entity_type = "SchoolSettings"

    def get_queryset(self):
        if not self.request.user.is_superuser:
            school = resolve_school_context(self.request)
            return self.queryset.filter(school=school) if school else self.queryset.none()
        return self.queryset

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["school"] = resolve_school_context(self.request)
        return ctx

    def perform_create(self, serializer):
        school = resolve_school_context(self.request)
        if serializer.validated_data.get("school") is None and school is not None:
            serializer.validated_data["school"] = school
        obj = serializer.save()
        audit(self.request, self.request.user, "school.setting.set", "school", "SchoolSettings", str(obj.id),
              new_value={"key": obj.key})

    def perform_update(self, serializer):
        obj = serializer.save()
        audit(self.request, self.request.user, "school.setting.set", "school", "SchoolSettings", str(obj.id),
              new_value={"key": obj.key})