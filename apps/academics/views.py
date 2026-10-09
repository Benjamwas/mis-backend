"""Academics API views."""
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.academics.models import (
    Assessment,
    AssessmentScore,
    Assignment,
    SchoolPeriod,
    TimetableSlot,
    AssignmentGrade,
    AssignmentSubmission,
    ClassSubject,
    Enrollment,
    LearningRecommendation,
    StudentSubjectResult,
    StudentGroup,
    StudentGroupMember,
    Subject,
    TeachingAssignment,
)
from apps.academics.serializers import (
    SchoolPeriodSerializer,
    TimetableSlotSerializer,
    AssessmentScoreSerializer,
    AssessmentSerializer,
    AssignmentGradeSerializer,
    AssignmentSerializer,
    AssignmentSubmissionSerializer,
    ClassSubjectSerializer,
    EnrollmentSerializer,
    LearningRecommendationSerializer,
    StudentSubjectResultSerializer,
    StudentGroupMemberSerializer,
    StudentGroupSerializer,
    SubjectSerializer,
    TeachingAssignmentSerializer,
)
from apps.academics.services import (
    aggregate_result_for,
    aggregate_results_for_term,
    close_enrollment,
    enroll_student,
    grade_submission,
    publish_results,
    submit_assignment,
    transfer_student,
)
from apps.common.exceptions import PermissionDeniedError, TenantIsolationError, ValidationFailedError
from apps.common.permissions import HasPermission
from apps.common.viewsets import SchoolScopedViewSet


class SubjectViewSet(SchoolScopedViewSet):
    queryset = Subject.objects.all()
    serializer_class = SubjectSerializer
    permission_classes = [HasPermission]
    permission_code = "subject.read"
    audit_module = "academics"
    audit_entity_type = "Subject"
    search_fields = ["name", "code"]

    def get_permissions(self):
        if self.action in ("create", "update", "partial_update", "destroy"):
            self.permission_code = "subject.update"
        return super().get_permissions()

    def perform_create(self, serializer):
        obj = serializer.save()
        self._audit("subject.create", obj, new_value={"name": obj.name, "code": obj.code})


class ClassSubjectViewSet(SchoolScopedViewSet):
    queryset = ClassSubject.objects.all()
    serializer_class = ClassSubjectSerializer
    permission_classes = [HasPermission]
    permission_code = "subject.update"

    def get_queryset(self):
        qs = super().get_queryset().select_related("subject", "school_class")
        class_id = self.request.query_params.get("class_id")
        if class_id:
            qs = qs.filter(school_class_id=class_id)
        return qs


class StudentGroupViewSet(SchoolScopedViewSet):
    queryset = StudentGroup.objects.select_related("school_class", "subject").prefetch_related("members__student__person").all()
    serializer_class = StudentGroupSerializer
    permission_classes = [HasPermission]
    permission_code = "assignment.read"
    audit_module = "academics"
    audit_entity_type = "StudentGroup"

    def get_permissions(self):
        if self.action in ("create", "update", "partial_update", "destroy", "add_member", "remove_member"):
            self.permission_code = "assignment.create"
        return super().get_permissions()

    def perform_create(self, serializer):
        school = self.get_school()
        if school is None:
            from apps.common.exceptions import TenantIsolationError
            raise TenantIsolationError("A school context is required.")
        school_class = serializer.validated_data.get("school_class")
        subject = serializer.validated_data.get("subject")
        if school_class.school_id != school.id or (subject and subject.school_id != school.id):
            raise ValidationFailedError("Group records must belong to the active school.", code="TENANT_ISOLATION")
        obj = serializer.save(school=school, created_by=self.request.user)
        self._audit("student_group.create", obj, new_value={"name": obj.name})

    @action(detail=True, methods=["get"], url_path="members")
    def members(self, request, pk=None):
        group = self.get_object()
        return Response(StudentGroupMemberSerializer(group.members.select_related("student__person").all(), many=True).data)

    @action(detail=True, methods=["post"], url_path="add-member")
    def add_member(self, request, pk=None):
        group = self.get_object()
        from apps.people.models import Student
        student = get_object_or_404(Student.objects.filter(school=group.school_id), pk=request.data.get("student_id"))
        member, _ = StudentGroupMember.objects.update_or_create(
            group=group, student=student, defaults={"is_leader": bool(request.data.get("is_leader", False))}
        )
        return Response(StudentGroupMemberSerializer(member).data, status=201)

    @action(detail=True, methods=["post"], url_path="remove-member")
    def remove_member(self, request, pk=None):
        group = self.get_object()
        StudentGroupMember.objects.filter(group=group, student_id=request.data.get("student_id")).delete()
        return Response({"removed": True})


class EnrollmentViewSet(SchoolScopedViewSet):
    queryset = Enrollment.objects.all()
    serializer_class = EnrollmentSerializer
    permission_classes = [HasPermission]
    permission_code = "enrollment.read"
    filterset_fields = ["student", "school_class", "academic_year", "status"]

    def get_queryset(self):
        return super().get_queryset().select_related("student__person", "school_class", "academic_year")

    def get_permissions(self):
        if self.action in ("create",):
            self.permission_code = "enrollment.create"
        elif self.action in ("update", "partial_update"):
            self.permission_code = "enrollment.update"
        return super().get_permissions()

    def create(self, request, *args, **kwargs):
        from apps.people.models import Student
        from apps.schools.models import SchoolClass

        student = get_object_or_404(Student.objects.filter(school_id=self.get_school().id), pk=request.data.get("student_id"))
        school_class = get_object_or_404(SchoolClass.objects.filter(school_id=self.get_school().id), pk=request.data.get("class_id"))
        enrollment = enroll_student(student, school_class, by=request.user)
        self._audit("enrollment.create", enrollment, new_value={"class_id": school_class.id, "student_id": student.id})
        return Response(EnrollmentSerializer(enrollment).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], permission_classes=[HasPermission])
    def transfer(self, request, pk=None):
        self.permission_code = "enrollment.transfer"
        self.check_permission_code(self.permission_code)
        enrollment = self.get_object()
        target = request.data.get("target_class_id")
        if not target:
            raise ValidationFailedError("target_class_id required.", code="TARGET_CLASS_REQUIRED")
        new_enrollment = transfer_student(enrollment, target, by=request.user)
        self._audit("enrollment.transfer", new_enrollment, new_value={"from": enrollment.school_class_id, "to": target})
        return Response(EnrollmentSerializer(new_enrollment).data)

    @action(detail=True, methods=["post"], permission_classes=[HasPermission])
    def close(self, request, pk=None):
        self.permission_code = "enrollment.close"
        self.check_permission_code(self.permission_code)
        enrollment = self.get_object()
        close_enrollment(enrollment, by=request.user)
        self._audit("enrollment.close", enrollment, old_value={"status": "ACTIVE"}, new_value={"status": enrollment.status})
        return Response(EnrollmentSerializer(enrollment).data)


class TeachingAssignmentViewSet(SchoolScopedViewSet):
    queryset = TeachingAssignment.objects.select_related("teacher__person", "school_class", "subject", "term").all()
    serializer_class = TeachingAssignmentSerializer
    permission_classes = [HasPermission]
    permission_code = "subject.read"
    filterset_fields = ["teacher", "school_class", "subject", "term", "status"]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user.is_superuser:
            return qs
        school = self.get_school()
        current_roles = set(user.user_roles.values_list("role__code", flat=True))
        if current_roles & {"SUBJECT_TEACHER", "CLASS_TEACHER"} and school:
            emp = user.person.hr_employees.filter(school=school).first() if user.person else None
            if emp:
                return qs.filter(teacher=emp)
            return qs.none()
        return qs

    def get_permissions(self):
        if self.action in ("create", "update", "partial_update", "destroy"):
            self.permission_code = "subject.update"
        return super().get_permissions()

    def perform_create(self, serializer):
        obj = serializer.save()
        self._audit("teaching_assignment.create", obj, new_value={
            "teacher": str(obj.teacher_id), "class": str(obj.school_class_id), "subject": str(obj.subject_id)})


class AssignmentViewSet(SchoolScopedViewSet):
    queryset = Assignment.objects.all()
    serializer_class = AssignmentSerializer
    permission_classes = [HasPermission]
    permission_code = "assignment.read"
    filterset_fields = ["status", "teaching_assignment", "topic"]
    search_fields = ["title"]

    def get_queryset(self):
        qs = super().get_queryset().select_related(
            "teaching_assignment__subject", "teaching_assignment__school_class", "topic"
        )
        student = getattr(getattr(self.request.user, "person", None), "students", None)
        if student:
            student = student.filter(school=self.get_school()).first()
            if student:
                qs = qs.filter(
                    status=Assignment.Status.PUBLISHED,
                    teaching_assignment__school_class__enrollments__student=student,
                    teaching_assignment__school_class__enrollments__status="ACTIVE",
                ).distinct()
        return qs

    def _enforce_teacher_scope(self, obj):
        """Subject teachers may only manage assignments within their teaching scope."""
        if self.request.user.is_superuser:
            return
        school = self.get_school()
        from apps.identity.services import user_has_permission

        if school and user_has_permission(self.request.user, "assignment.manage_all", school_id=school.id):
            return
        current_roles = set(self.request.user.user_roles.values_list("role__code", flat=True))
        if school and current_roles & {"SCHOOL_ADMIN"}:
            return
        if school and current_roles & {"SUBJECT_TEACHER", "CLASS_TEACHER"}:
            owner = obj.teaching_assignment.teacher_id
            emp = self.request.user.person.hr_employees.filter(school=school).first()
            class_teacher = obj.teaching_assignment.school_class.class_teacher_id
            if not emp or (emp.id != owner and not ("CLASS_TEACHER" in current_roles and emp.id == class_teacher)):
                raise PermissionDeniedError()

    def get_permissions(self):
        action_map = {
            "create": "assignment.create",
            "update": "assignment.update",
            "partial_update": "assignment.update",
            "destroy": "assignment.delete",
        }
        self.permission_code = action_map.get(self.action, "assignment.read")
        if self.action in ("grade", "grade_list"):
            self.permission_code = "assignment.grade"
        return super().get_permissions()

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["request"] = self.request
        ctx["school"] = self.get_school()
        return ctx

    def perform_create(self, serializer):
        school = self.get_school()
        if school is None:
            raise TenantIsolationError("A school context is required.")
        obj = serializer.save(school=school, created_by=self.request.user)
        self._audit("assignment.create", obj, new_value={"title": obj.title})

    def perform_update(self, serializer):
        obj = serializer.save()
        self._audit("assignment.update", obj, new_value={"title": obj.title})

    @action(detail=True, methods=["post"], permission_classes=[HasPermission])
    def publish(self, request, pk=None):
        self.permission_code = "assignment.publish"
        self.check_permission_code(self.permission_code)
        obj = self.get_object()
        self._enforce_teacher_scope(obj)
        obj.publish(by=request.user)
        self._audit("assignment.publish", obj, old_value={"status": "DRAFT"}, new_value={"status": obj.status})
        from apps.communication.tasks import notify_enrolled_class_students

        notify_enrolled_class_students.delay(
            school_id=obj.school_id,
            class_id=obj.teaching_assignment.school_class_id,
            title="New Assignment",
            body=f"Assignment '{obj.title}' has been published.",
        )
        return Response(AssignmentSerializer(obj).data)

    @action(detail=True, methods=["post"], permission_classes=[HasPermission])
    def close(self, request, pk=None):
        self.permission_code = "assignment.publish"
        self.check_permission_code(self.permission_code)
        obj = self.get_object()
        self._enforce_teacher_scope(obj)
        obj.close()
        self._audit("assignment.close", obj, old_value={"status": "PUBLISHED"}, new_value={"status": obj.status})
        return Response(AssignmentSerializer(obj).data)

    @action(detail=True, methods=["post"], permission_classes=[HasPermission])
    def submit(self, request, pk=None):
        from apps.people.models import Student

        self.permission_code = "assignment.read"
        self.check_permission_code(self.permission_code)
        obj = self.get_object()
        # student submits for self, or admin/teacher submits on behalf
        student = None
        if request.user.person.students.exists():
            student = request.user.person.students.filter(school=obj.school_id).first()
        elif request.data.get("student_id"):
            student = Student.objects.filter(pk=request.data["student_id"], school=obj.school_id).first()
        if student is None:
            raise PermissionDeniedError("No matching student context for this submission.")
        submission = submit_assignment(obj, student, content=request.data.get("submission_content", ""), by=request.user)
        self._audit("assignment.submit", obj, new_value={"submission_id": str(submission.id), "student": str(student.id)})
        return Response(AssignmentSubmissionSerializer(submission).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"], permission_classes=[HasPermission])
    def submissions(self, request, pk=None):
        self.permission_code = "assignment.read"
        self.check_permission_code(self.permission_code)
        obj = self.get_object()
        self._enforce_teacher_scope(obj)
        subs = obj.submissions.select_related("student__person").order_by("submitted_at")
        return Response(AssignmentSubmissionSerializer(subs, many=True).data)

    @action(detail=True, methods=["post"], permission_classes=[HasPermission])
    def grade_student(self, request, pk=None):
        self.permission_code = "assignment.grade"
        self.check_permission_code(self.permission_code)
        obj = self.get_object()
        self._enforce_teacher_scope(obj)
        submission = get_object_or_404(obj.submissions, pk=request.data.get("submission_id"))
        graded = grade_submission(submission, request.data.get("marks"), request.data.get("feedback", ""), request.user)
        self._audit("assignment.grade", obj, new_value={"submission_id": str(submission.id), "marks": str(request.data.get("marks"))})
        from apps.communication.tasks import notify_users

        student_user = submission.student.person.users.exclude(status__in=["INACTIVE", "SUSPENDED"]).first()
        if student_user:
            notify_users.delay([student_user.id], title="Assignment Graded", body=f"'{obj.title}' has been graded.")
        return Response(AssignmentSubmissionSerializer(graded).data)

    @action(detail=True, methods=["post"], permission_classes=[HasPermission])
    def request_resubmission(self, request, pk=None):
        self.permission_code = "assignment.grade"
        self.check_permission_code(self.permission_code)
        obj = self.get_object()
        self._enforce_teacher_scope(obj)
        submission = get_object_or_404(obj.submissions, pk=request.data.get("submission_id"))
        submission.status = AssignmentSubmission.Status.RETURNED
        submission.save(update_fields=["status", "updated_at"])
        self._audit("assignment.resubmission_request", obj, new_value={"submission_id": str(submission.id)})
        return Response(AssignmentSubmissionSerializer(submission).data)


class AssessmentViewSet(SchoolScopedViewSet):
    queryset = Assessment.objects.select_related("teaching_assignment__subject", "term").all()
    serializer_class = AssessmentSerializer
    permission_classes = [HasPermission]
    permission_code = "assessment.read"
    filterset_fields = ["assessment_type", "term", "status", "teaching_assignment"]

    def get_permissions(self):
        action_map = {"create": "assessment.create", "update": "assessment.update",
                      "partial_update": "assessment.update", "destroy": "assessment.delete"}
        self.permission_code = action_map.get(self.action, "assessment.read")
        return super().get_permissions()

    def perform_create(self, serializer):
        obj = serializer.save()
        self._audit("assessment.create", obj, new_value={"title": obj.title})

    @action(detail=True, methods=["post"], permission_classes=[HasPermission])
    def record_scores(self, request, pk=None):
        from apps.people.models import Student

        self.permission_code = "assessment.record"
        self.check_permission_code(self.permission_code)
        obj = self.get_object()
        entries = request.data.get("scores", [])
        created = []
        with transaction.atomic():
            for entry in entries:
                student = get_object_or_404(Student.objects.filter(school=obj.school_id), pk=entry.get("student_id"))
                if not (0 <= float(entry.get("score", -1)) <= float(obj.max_score)):
                    raise ValidationFailedError(
                        f"Score {entry.get('score')} out of range for {student.full_name}.", code="SCORE_OUT_OF_RANGE"
                    )
                score, _ = AssessmentScore.objects.update_or_create(
                    assessment=obj,
                    student=student,
                    defaults={
                        "school": obj.school,
                        "score": entry["score"],
                        "grade": entry.get("grade", ""),
                        "teacher_comment": entry.get("teacher_comment", ""),
                        "recorded_by": request.user,
                    },
                )
                created.append(score)
        # Auto-aggregate scores into draft subject results
        try:
            from apps.academics.services import aggregate_result_for
            ta = obj.teaching_assignment
            seen = set()
            for sc in created:
                if sc.student_id not in seen:
                    seen.add(sc.student_id)
                    aggregate_result_for(sc.student, ta.subject, obj.term, by=request.user)
        except Exception:
            import logging
            logging.getLogger("apps.academics").exception("Auto-aggregation after record_scores failed")
        self._audit("assessment.record", obj, new_value={"count": len(created)})
        return Response(AssessmentScoreSerializer(created, many=True).data)


class AssessmentScoreViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = AssessmentScore.objects.select_related("student__person", "assessment").all()
    serializer_class = AssessmentScoreSerializer
    permission_classes = [HasPermission]
    permission_code = "assessment.read"


class ResultViewSet(SchoolScopedViewSet):
    queryset = StudentSubjectResult.objects.all()
    serializer_class = StudentSubjectResultSerializer
    permission_classes = [HasPermission]
    permission_code = "result.read"
    filterset_fields = ["student", "subject", "term", "status"]

    def get_queryset(self):
        qs = super().get_queryset().select_related("student__person", "subject", "term")
        from apps.people.services import parent_for_user
        parent = parent_for_user(self.request.user, self.get_school())
        if parent is not None:
            qs = qs.filter(student_id__in=parent.children.values_list("student_id", flat=True), status="PUBLISHED")
        return qs

    def get_permissions(self):
        action_map = {"create": "result.create", "update": "result.update", "partial_update": "result.update"}
        self.permission_code = action_map.get(self.action, "result.read")
        if self.action == "publish":
            self.permission_code = "result.publish"
        return super().get_permissions()

    @action(detail=False, methods=["post"], permission_classes=[HasPermission])
    def publish(self, request):
        result_ids = request.data.get("result_ids", [])
        if not result_ids:
            raise ValidationFailedError("result_ids required.", code="RESULT_IDS_REQUIRED")
        school = self.get_school()
        results = publish_results(result_ids, school, by=request.user)
        return Response(StudentSubjectResultSerializer(results, many=True).data)

    @action(detail=False, methods=["post"], permission_classes=[HasPermission])
    def generate(self, request):
        """Auto-generate draft results from assessment scores for a term."""
        self.permission_code = "result.create"
        self.check_permission_code(self.permission_code)
        school = self.get_school()
        term_id = request.data.get("term_id")
        student_id = request.data.get("student_id")
        subject_id = request.data.get("subject_id")
        from apps.schools.models import Term

        if student_id and subject_id and term_id:
            from apps.academics.models import Subject
            from apps.people.models import Student
            student = get_object_or_404(Student, id=student_id, school=school)
            subject = get_object_or_404(Subject, id=subject_id, school=school)
            term = get_object_or_404(Term, id=term_id, school=school)
            result = aggregate_result_for(student, subject, term, by=request.user)
            if not result:
                raise ValidationFailedError("No assessment scores found for this student/subject/term.", code="NO_SCORES")
            return Response(StudentSubjectResultSerializer(result).data)
        if term_id:
            term = get_object_or_404(Term, id=term_id, school=school)
            results = aggregate_results_for_term(term, school=school, by=request.user)
            return Response(StudentSubjectResultSerializer(results, many=True).data)
        raise ValidationFailedError("term_id required (optional student_id + subject_id).", code="TERM_REQUIRED")


class LearningRecommendationViewSet(SchoolScopedViewSet):
    queryset = LearningRecommendation.objects.all()
    serializer_class = LearningRecommendationSerializer
    permission_classes = [HasPermission]
    permission_code = "result.read"
    filterset_fields = ["student", "status", "priority"]

    @action(detail=False, methods=["post"], permission_classes=[HasPermission])
    def generate(self, request):
        from apps.people.models import Student

        self.permission_code = "result.update"
        self.check_permission_code(self.permission_code)
        school = self.get_school()
        student = get_object_or_404(Student.objects.filter(school=school), pk=request.data.get("student_id"))
        from apps.academics.services import generate_learning_recommendations

        created = generate_learning_recommendations(student, school)
        return Response(LearningRecommendationSerializer(created, many=True).data)


class SchoolPeriodViewSet(SchoolScopedViewSet):
    queryset = SchoolPeriod.objects.all()
    serializer_class = SchoolPeriodSerializer
    permission_classes = [HasPermission]
    permission_code = "class.read"
    audit_module = "academics"
    audit_entity_type = "SchoolPeriod"

    def get_permissions(self):
        if self.action in ("create", "update", "partial_update", "destroy"):
            self.permission_code = "class.update"
        return super().get_permissions()


class TimetableSlotViewSet(SchoolScopedViewSet):
    queryset = TimetableSlot.objects.select_related(
        "school_class", "period", "teaching_assignment__subject", "teaching_assignment__teacher__person"
    ).all()
    serializer_class = TimetableSlotSerializer
    permission_classes = [HasPermission]
    permission_code = "class.read"
    filterset_fields = ["school_class", "teaching_assignment", "day_of_week", "period", "status"]
    audit_module = "academics"
    audit_entity_type = "TimetableSlot"

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user.is_superuser:
            return qs
        school = self.get_school()
        current_roles = set(user.user_roles.values_list("role__code", flat=True))
        if current_roles & {"SUBJECT_TEACHER", "CLASS_TEACHER"} and school:
            emp = user.person.hr_employees.filter(school=school).first() if user.person else None
            if emp:
                return qs.filter(teaching_assignment__teacher=emp)
        student = getattr(getattr(user, "person", None), "students", None)
        if student:
            student = student.filter(school=school).first() if school else None
            if student:
                enrollment = student.enrollments.filter(status="ACTIVE").select_related("school_class").first()
                if enrollment:
                    return qs.filter(school_class=enrollment.school_class)
        return qs

    def get_permissions(self):
        if self.action in ("create", "update", "partial_update", "destroy"):
            self.permission_code = "class.update"
        return super().get_permissions()

    @action(detail=False, methods=["get"])
    def week(self, request):
        """Return the weekly grid: periods, days, and slots for a class or teacher."""
        school = self.get_school()
        class_id = request.query_params.get("class_id")
        term_id = request.query_params.get("term_id")
        qs = self.get_queryset().filter(status="ACTIVE")
        if class_id:
            qs = qs.filter(school_class_id=class_id)
        if term_id:
            qs = qs.filter(teaching_assignment__term_id=term_id)
        if school and not class_id:
            # default to first active class for teachers
            user_roles = set(request.user.user_roles.values_list("role__code", flat=True))
            if user_roles & {"SUBJECT_TEACHER", "CLASS_TEACHER"}:
                emp = request.user.person.hr_employees.filter(school=school).first() if request.user.person else None
                if emp:
                    first = qs.filter(teaching_assignment__teacher=emp).values_list("school_class_id", flat=True).first()
                    if first:
                        qs = qs.filter(school_class_id=first)
        periods = SchoolPeriod.objects.filter(school=school).order_by("display_order") if school else SchoolPeriod.objects.none()
        return Response({
            "periods": SchoolPeriodSerializer(periods, many=True).data,
            "days": [c[0] for c in TimetableSlot.DAY_CHOICES[:5]],
            "slots": TimetableSlotSerializer(qs, many=True).data,
        })
