"""Admissions API views."""
import csv

from django.http import HttpResponse
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.admissions.models import (
    AdmissionApplication,
    Applicant,
    ApplicationDocument,
    ApplicationStatusHistory,
)
from apps.admissions.services import (
    enroll_accepted_application,
    submit_application,
    update_application_status,
)
from apps.admissions.serializers import (
    AdmissionApplicationSerializer,
    ApplicantSerializer,
    ApplicationDocumentSerializer,
    ApplicationStatusHistorySerializer,
)
from apps.common.exceptions import ValidationFailedError
from apps.common.permissions import HasPermission
from apps.common.viewsets import SchoolScopedViewSet

APPLICATION_STATUS_ACTION = {
    "UNDER_REVIEW": None, "SHORTLISTED": None, "INTERVIEW": None,
    "DECISION_PENDING": None, "WAITLISTED": None,
}


class ApplicantViewSet(SchoolScopedViewSet):
    queryset = Applicant.objects.select_related("person").all()
    serializer_class = ApplicantSerializer
    permission_classes = [HasPermission]
    permission_code = "admission.read"
    audit_module = "admissions"
    audit_entity_type = "Applicant"
    search_fields = ["first_name", "last_name", "email", "phone"]
    filterset_fields = ["status"]

    def get_permissions(self):
        if self.action in ("create", "update", "partial_update"):
            self.permission_code = "admission.create"
        return super().get_permissions()

    def perform_create(self, serializer):
        obj = serializer.save()
        self._audit("admission.applicant.create", obj, new_value={"name": obj.full_name})

    @action(detail=True, methods=["post"])
    def link_person(self, request, pk=None):
        from apps.identity.models import Person

        obj = self.get_object()
        person = Person.objects.filter(id=request.data.get("person_id")).first()
        if not person:
            raise ValidationFailedError("Person not found.", code="PERSON_NOT_FOUND", status_code=404)
        obj.person = person
        obj.save(update_fields=["person", "updated_at"])
        self._audit("admission.applicant.link_person", obj, new_value={"person_id": str(person.id)})
        return Response(ApplicantSerializer(obj).data)


class AdmissionApplicationViewSet(SchoolScopedViewSet):
    queryset = AdmissionApplication.objects.select_related(
        "applicant__person", "grade_level", "academic_year", "term"
    ).prefetch_related("status_history").all()
    serializer_class = AdmissionApplicationSerializer
    permission_classes = [HasPermission]
    permission_code = "admission.read"
    audit_module = "admissions"
    audit_entity_type = "AdmissionApplication"
    search_fields = ["application_number"]
    filterset_fields = ["status", "grade_level", "academic_year"]

    def get_queryset(self):
        qs = super().get_queryset()
        status_param = self.request.query_params.get("status")
        grade_param = self.request.query_params.get("grade_level")
        if status_param:
            qs = qs.filter(status=status_param)
        if grade_param:
            qs = qs.filter(grade_level_id=grade_param)
        return qs

    def get_permissions(self):
        if self.action in ("create", "update", "partial_update", "enroll"):
            self.permission_code = "admission.create"
        elif self.action in ("submit",):
            self.permission_code = "admission.update"
        elif self.action in ("approve", "reject", "waitlist", "interview"):
            self.permission_code = "admission.approve"
        return super().get_permissions()

    def perform_create(self, serializer):
        obj = serializer.save()
        self._audit("admission.application.create", obj, new_value={"number": obj.application_number})

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        obj = self.get_object()
        submit_application(obj, by=request.user)
        self._audit("admission.submit", obj, old_value={"status": "DRAFT"}, new_value={"status": obj.status})
        from apps.communication.tasks import send_transactional_email_job

        send_transactional_email_job.delay(
            to_email=obj.applicant.guardian_email or obj.applicant.email,
            subject="Admission Application Received",
            template="application_received",
            context={"name": obj.applicant.full_name, "application_number": obj.application_number},
        )
        return Response(AdmissionApplicationSerializer(obj).data)

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        obj = self.get_object()
        obj = update_application_status(obj, AdmissionApplication.ACCEPTED, by=request.user,
                                        comment=request.data.get("comment", ""))
        self._audit("admission.approve", obj, old_value={"submitted": True}, new_value={"status": obj.status})
        from apps.communication.tasks import send_transactional_email_job

        send_transactional_email_job.delay(
            to_email=obj.applicant.guardian_email or obj.applicant.email,
            subject="Admission Offer",
            template="application_accepted",
            context={"name": obj.applicant.full_name, "application_number": obj.application_number},
        )
        return Response(AdmissionApplicationSerializer(obj).data)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        obj = self.get_object()
        obj = update_application_status(obj, AdmissionApplication.REJECTED, by=request.user,
                                        comment=request.data.get("comment", ""))
        self._audit("admission.reject", obj, new_value={"status": obj.status})
        return Response(AdmissionApplicationSerializer(obj).data)

    @action(detail=True, methods=["post"])
    def waitlist(self, request, pk=None):
        obj = self.get_object()
        obj = update_application_status(obj, AdmissionApplication.WAITLISTED, by=request.user,
                                        comment=request.data.get("comment", ""))
        self._audit("admission.waitlist", obj, new_value={"status": obj.status})
        return Response(AdmissionApplicationSerializer(obj).data)

    @action(detail=True, methods=["post"])
    def interview(self, request, pk=None):
        obj = self.get_object()
        obj = update_application_status(obj, AdmissionApplication.INTERVIEW, by=request.user,
                                        comment=request.data.get("comment", ""))
        self._audit("admission.interview", obj, new_value={"status": obj.status})
        return Response(AdmissionApplicationSerializer(obj).data)

    @action(detail=True, methods=["post"])
    def enroll(self, request, pk=None):
        obj = self.get_object()
        student = enroll_accepted_application(obj, by=request.user)
        self._audit("admission.enroll", obj, new_value={"student": str(student.id)})
        return Response({
            "application": AdmissionApplicationSerializer(obj).data,
            "student": {"id": str(student.id), "admission_number": student.admission_number},
        }, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"])
    def status_history(self, request, pk=None):
        obj = self.get_object()
        qs = obj.status_history.order_by("changed_at")
        return Response(ApplicationStatusHistorySerializer(qs, many=True).data)

    @action(detail=True, methods=["post"])
    def upload_document(self, request, pk=None):
        from apps.files.models import FileUpload

        obj = self.get_object()
        file = FileUpload.objects.filter(school=obj.school, id=request.data.get("file_id")).first()
        if not file:
            raise ValidationFailedError("File not found.", code="FILE_NOT_FOUND", status_code=404)
        doc = ApplicationDocument.objects.create(
            school=obj.school, application=obj, file=file,
            document_type=request.data.get("document_type", "OTHER"),
        )
        if request.data.get("verify"):
            from apps.common.permissions import require_permission

            require_permission(request, "admission.approve")
            doc.is_verified = True
            doc.save(update_fields=["is_verified", "updated_at"])
        self._audit("admission.document.upload", obj, new_value={"document": str(doc.id)})
        return Response(ApplicationDocumentSerializer(doc).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["get"])
    def summary(self, request):
        school = self.get_school()
        counts = {s: AdmissionApplication.objects.filter(school=school, status=s).count() for s, _ in AdmissionApplication.STATUS_CHOICES}
        total = AdmissionApplication.objects.filter(school=school).count()
        counts["TOTAL"] = total
        return Response({"status_counts": counts})

    @action(detail=False, methods=["get"])
    def export_csv(self, request):
        import io

        school = self.get_school()
        qs = self.filter_queryset(
            AdmissionApplication.objects.filter(school=school).select_related("applicant", "grade_level", "academic_year")
        )

        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["Application No", "Applicant", "Email", "Phone", "Grade", "Academic Year", "Status", "Submitted At"])
        for app in qs.iterator():
            writer.writerow([
                app.application_number, app.applicant.full_name, app.applicant.email, app.applicant.phone,
                app.grade_level.name, app.academic_year.name, app.status,
                app.submitted_at.isoformat() if app.submitted_at else "",
            ])
        buffer.seek(0)
        return HttpResponse(buffer.getvalue(), content_type="text/csv",
                            headers={"Content-Disposition": 'attachment; filename="applications.csv"'})