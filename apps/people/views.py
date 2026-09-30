"""Student and parent views."""
from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from apps.audit.services import audit
from apps.common.exceptions import ValidationFailedError
from apps.common.permissions import HasPermission
from apps.common.viewsets import SchoolScopedViewSet
from apps.people.models import Parent, ParentStudent, Student
from apps.people.serializers import ParentSerializer, ParentStudentSerializer, StudentSerializer
from apps.people.services import link_parent_student


class StudentViewSet(SchoolScopedViewSet):
    queryset = Student.objects.select_related("person", "school").all()
    serializer_class = StudentSerializer
    permission_classes = [HasPermission]
    permission_code = "student.read"
    audit_module = "students"
    audit_entity_type = "Student"
    filterset_fields = ["status", "school"]
    search_fields = ["admission_number", "person__first_name", "person__middle_name", "person__last_name"]
    ordering_fields = ["created_at", "admission_number"]

    def get_permissions(self):
        permission_map = {
            "create": "student.create",
            "destroy": "student.delete",
        }
        if self.action in ("update", "partial_update"):
            self.permission_code = "student.update"
        elif self.action in permission_map:
            self.permission_code = permission_map[self.action]
        return super().get_permissions()

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["school"] = self.get_school()
        return ctx

    def get_queryset(self):
        qs = super().get_queryset()
        qs = qs.select_related("person").prefetch_related("enrollments__school_class")
        cls = self.request.query_params.get("class_id")
        if cls:
            qs = qs.filter(enrollments__school_class_id=cls, enrollments__status="ACTIVE")
        search = self.request.query_params.get("search")
        if search:
            qs = self.filter_queryset(qs) if self.action == "list" else qs
        from apps.people.services import parent_for_user
        parent = parent_for_user(self.request.user, self.get_school())
        if parent is not None:
            qs = qs.filter(id__in=parent.children.values_list("student_id", flat=True))
        return qs.distinct()

    def perform_create(self, serializer):
        obj = serializer.save()
        self._audit("student.create", obj, new_value={"admission_number": obj.admission_number, "name": obj.full_name})

    def perform_update(self, serializer):
        from apps.audit.services import audit

        old = serializer.instance
        obj = serializer.save()
        self._audit("student.update", obj, old_value={"status": old.status}, new_value={"status": obj.status})

    def perform_destroy(self, instance):
        self._audit("student.archive", instance, old_value={"status": instance.status})
        instance.archive(by=self.request.user)

    @action(detail=True, methods=["post"], permission_classes=[HasPermission])
    def archive(self, request, pk=None):
        self.permission_code = "student.delete"
        self.check_permission_code(self.permission_code)
        obj = self.get_object()
        obj.archive(by=request.user)
        self._audit("student.archive", obj, old_value={"status": "ACTIVE"}, new_value={"status": obj.status})
        return Response(StudentSerializer(obj).data)

    @action(detail=True, methods=["post"], permission_classes=[HasPermission])
    def restore(self, request, pk=None):
        self.permission_code = "student.delete"
        self.check_permission_code(self.permission_code)
        obj = self.get_object()
        obj.restore()
        self._audit("student.restore", obj, old_value={"status": "ARCHIVED"}, new_value={"status": obj.status})
        return Response(StudentSerializer(obj).data)

    @action(detail=True, methods=["get"], permission_classes=[HasPermission])
    def history(self, request, pk=None):
        self.permission_code = "student.read"
        self.check_permission_code(self.permission_code)
        obj = self.get_object()
        from apps.audit.models import AuditLog

        logs = AuditLog.objects.filter(
            entity_type="Student", entity_id=str(obj.id)
        ).order_by("-created_at")[:50]
        return Response(
            [
                {
                    "action": l.action,
                    "user_id": l.user_id,
                    "old_value": l.old_value,
                    "new_value": l.new_value,
                    "created_at": l.created_at,
                }
                for l in logs
            ]
        )

    @action(detail=True, methods=["get"], permission_classes=[HasPermission])
    def documents(self, request, pk=None):
        self.permission_code = "student.read"
        self.check_permission_code(self.permission_code)
        obj = self.get_object()
        from apps.files.models import FileUpload

        docs = FileUpload.objects.filter(school=obj.school_id, linked_type="Student", linked_id=obj.id)
        return Response(
            [{"id": d.id, "original_name": d.original_name, "category": d.category, "mime_type": d.mime_type,
              "size": d.size, "url": d.url, "created_at": d.created_at} for d in docs]
        )

    @action(detail=True, methods=["post"], permission_classes=[HasPermission])
    def enroll(self, request, pk=None):
        self.permission_code = "enrollment.create"
        self.check_permission_code(self.permission_code)
        from apps.academics.services import enroll_student

        obj = self.get_object()
        class_id = request.data.get("class_id")
        if not class_id:
            raise ValidationFailedError("class_id is required.", code="CLASS_REQUIRED")
        enrollment = enroll_student(student=obj, school_class=parent_class(obj.school_id, class_id), by=request.user)
        self._audit("student.enroll", obj, new_value={"class_id": class_id, "enrollment_id": enrollment.id})
        return Response(enrollment_serialize(enrollment), status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"], permission_classes=[HasPermission])
    def enrollments(self, request, pk=None):
        self.permission_code = "student.read"
        self.check_permission_code(self.permission_code)
        from apps.academics.serializers import EnrollmentSerializer

        obj = self.get_object()
        enrollments = obj.enrollments.select_related("school_class", "academic_year").order_by("-created_at")
        return Response(EnrollmentSerializer(enrollments, many=True).data)

    @action(detail=True, methods=["get"], permission_classes=[HasPermission])
    def attendance(self, request, pk=None):
        from apps.attendance.services import student_attendance_summary

        obj = self.get_object()
        school = self.get_school()
        if school and obj.school_id != school.id:
            from apps.common.exceptions import TenantIsolationError

            raise TenantIsolationError()
        return Response(student_attendance_summary(obj))

    @action(detail=True, methods=["get"], permission_classes=[HasPermission])
    def academic_summary(self, request, pk=None):
        from apps.academics.services import student_academic_summary

        obj = self.get_object()
        school = self.get_school()
        if school and obj.school_id != school.id:
            from apps.common.exceptions import TenantIsolationError

            raise TenantIsolationError()
        return Response(student_academic_summary(obj))


def parent_class(school_id, class_id):
    from apps.schools.models import SchoolClass

    return get_object_or_404(SchoolClass.objects.filter(school_id=school_id), pk=class_id)


def enrollment_serialize(enrollment):
    return {
        "id": enrollment.id,
        "student": enrollment.student_id,
        "class_id": enrollment.school_class_id,
        "academic_year": enrollment.academic_year_id,
        "status": enrollment.status,
        "start_date": enrollment.start_date,
        "end_date": enrollment.end_date,
    }


class ParentViewSet(SchoolScopedViewSet):
    queryset = Parent.objects.select_related("person", "school").all()
    serializer_class = ParentSerializer
    permission_classes = [HasPermission]
    permission_code = "parent.read"
    audit_module = "parents"
    audit_entity_type = "Parent"
    search_fields = ["person__first_name", "person__last_name", "person__email", "person__phone"]

    def get_permissions(self):
        if self.action in ("create",):
            self.permission_code = "parent.create"
        elif self.action in ("update", "partial_update"):
            self.permission_code = "parent.update"
        return super().get_permissions()

    @action(detail=False, methods=["get"], permission_classes=[IsAuthenticated])
    def me(self, request):
        from apps.people.services import parent_for_user
        parent = parent_for_user(request.user, self.get_school())
        return Response(ParentSerializer(parent).data if parent else None)

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["school"] = self.get_school()
        return ctx

    def perform_create(self, serializer):
        obj = serializer.save()
        self._audit("parent.create", obj, new_value={"name": obj.full_name})

    def perform_update(self, serializer):
        obj = serializer.save()
        self._audit("parent.update", obj, new_value={"name": obj.full_name})

    @action(detail=True, methods=["get"], permission_classes=[IsAuthenticated])
    def children(self, request, pk=None):
        obj = self.get_object()
        if obj.person_id != getattr(request.user, "person_id", None) and not request.user.is_staff and not request.user.is_superuser:
            from apps.common.exceptions import PermissionDeniedError
            raise PermissionDeniedError()
        rels = obj.children.select_related("student__person")
        return Response([ParentStudentSerializer(r).data for r in rels])

    @action(detail=True, methods=["post"], permission_classes=[HasPermission])
    def add_child(self, request, pk=None):
        self.permission_code = "parent.update"
        self.check_permission_code(self.permission_code)
        obj = self.get_object()
        student_id = request.data.get("student_id")
        relationship_type = request.data.get("relationship_type", "GUARDIAN")
        is_primary = request.data.get("is_primary_contact", False)
        from apps.people.models import Student

        student = get_object_or_404(Student.objects.filter(school_id=obj.school_id), pk=student_id)
        rel = link_parent_student(obj, student, relationship_type, is_primary)
        self._audit("parent.add_child", obj, new_value={"student_id": student_id})
        return Response(ParentStudentSerializer(rel).data, status=status.HTTP_201_CREATED)
