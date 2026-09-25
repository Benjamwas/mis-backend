"""CRM API views."""
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.common.exceptions import ValidationFailedError
from apps.common.permissions import HasPermission
from apps.common.viewsets import SchoolScopedViewSet
from apps.crm.models import CrmInteraction, CrmLead, CrmTask, SchoolVisit
from apps.crm.serializers import (
    CrmInteractionSerializer,
    CrmLeadSerializer,
    CrmTaskSerializer,
    SchoolVisitSerializer,
)
from apps.crm.services import (
    add_task,
    cancel_task,
    complete_task,
    convert_lead,
    create_lead,
    log_interaction,
    mark_contacted,
    schedule_follow_up,
    update_visit_status,
)


class CrmLeadViewSet(SchoolScopedViewSet):
    queryset = CrmLead.objects.select_related("person", "interested_grade", "preferred_class", "assigned_to").all()
    serializer_class = CrmLeadSerializer
    permission_classes = [HasPermission]
    permission_code = "lead.read"
    audit_module = "crm"
    audit_entity_type = "CrmLead"
    search_fields = ["first_name", "last_name", "email", "phone"]
    filterset_fields = ["status", "source", "assigned_to"]

    def get_queryset(self):
        qs = super().get_queryset()
        status_q = self.request.query_params.get("status")
        if status_q:
            qs = qs.filter(status=status_q)
        return qs

    def get_permissions(self):
        if self.action == "create":
            self.permission_code = "lead.create"
        elif self.action in ("update", "partial_update", "follow_up", "assign", "add_task"):
            self.permission_code = "lead.update"
        elif self.action in ("convert", "archive"):
            self.permission_code = "crm.manage"
        return super().get_permissions()

    def create(self, request, *args, **kwargs):
        school = self.get_school()
        if school is None:
            raise ValidationFailedError("A school context is required.", code="NO_SCHOOL_CONTEXT", status_code=403)
        lead = create_lead(
            school=school,
            first_name=request.data.get("first_name", ""),
            last_name=request.data.get("last_name", ""),
            email=request.data.get("email", ""),
            phone=request.data.get("phone", ""),
            source=request.data.get("source", "OTHER"),
            assigned_to_id=request.data.get("assigned_to_id"),
            notes=request.data.get("notes", ""),
            interested_grade_id=request.data.get("interested_grade_id"),
            preferred_class_id=request.data.get("preferred_class_id"),
            by=request.user,
        )
        self._audit("crm.lead.create", lead, new_value={"name": lead.full_name})
        return Response(CrmLeadSerializer(lead).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def contact(self, request, pk=None):
        from django.shortcuts import get_object_or_404

        lead = get_object_or_404(self.get_queryset(), pk=pk)
        interaction = log_interaction(
            school=lead.school, lead=lead, user=request.user,
            interaction_type=request.data.get("interaction_type", "CALL"),
            notes=request.data.get("notes", ""),
            outcome=request.data.get("outcome", ""),
            scheduled_at=request.data.get("scheduled_at"),
        )
        self._audit("crm.lead.contact", lead, new_value={"interaction": str(interaction.id)})
        return Response(CrmInteractionSerializer(interaction).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def convert(self, request, pk=None):
        lead = self.get_object()
        convert_lead(lead, by=request.user, create_student=request.data.get("create_student", True))
        self._audit("crm.lead.convert", lead, new_value={"student": str(lead.converted_to_student_id)})
        return Response(CrmLeadSerializer(lead).data)

    @action(detail=True, methods=["post"])
    def follow_up(self, request, pk=None):
        lead = self.get_object()
        follow_up_date = request.data.get("follow_up_date")
        if not follow_up_date:
            raise ValidationFailedError("follow_up_date is required.", code="FOLLOW_UP_DATE_REQUIRED")
        schedule_follow_up(lead, follow_up_date, by=request.user)
        self._audit("crm.lead.follow_up", lead, new_value={"follow_up_date": follow_up_date})
        return Response(CrmLeadSerializer(lead).data)

    @action(detail=True, methods=["post"])
    def assign(self, request, pk=None):
        lead = self.get_object()
        lead.assigned_to_id = request.data.get("assigned_to_id")
        lead.save(update_fields=["assigned_to", "updated_at"])
        self._audit("crm.lead.assign", lead, new_value={"assigned_to": lead.assigned_to_id})
        return Response(CrmLeadSerializer(lead).data)

    @action(detail=True, methods=["post"])
    def add_task(self, request, pk=None):
        lead = self.get_object()
        task = add_task(
            school=lead.school, lead=lead, title=request.data.get("title", ""),
            description=request.data.get("description", ""), due_date=request.data.get("due_date"),
            assigned_to_id=request.data.get("assigned_to_id"), by=request.user,
        )
        self._audit("crm.task.create", task, new_value={"title": task.title})
        return Response(CrmTaskSerializer(task).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def mark_contacted(self, request, pk=None):
        lead = self.get_object()
        mark_contacted(lead, by=request.user)
        self._audit("crm.lead.mark_contacted", lead, new_value={"status": lead.status})
        return Response(CrmLeadSerializer(lead).data)

    @action(detail=True, methods=["post"])
    def archive(self, request, pk=None):
        lead = self.get_object()
        lead.status = CrmLead.Status.ARCHIVED
        lead.save(update_fields=["status", "updated_at"])
        self._audit("crm.lead.archive", lead, old_value={"status": "ACTIVE"}, new_value={"status": "ARCHIVED"})
        return Response(CrmLeadSerializer(lead).data)

    @action(detail=False, methods=["get"])
    def summary(self, request):
        school = self.get_school()
        counts = {}
        for s, _ in CrmLead.Status.choices:
            counts[s] = CrmLead.objects.filter(school=school, status=s).count()
        counts["TOTAL"] = sum(counts.values())
        return Response(counts)


class CrmInteractionViewSet(SchoolScopedViewSet):
    queryset = CrmInteraction.objects.select_related("lead", "user").all()
    serializer_class = CrmInteractionSerializer
    permission_classes = [HasPermission]
    permission_code = "lead.read"

    def get_permissions(self):
        if self.action == "create":
            self.permission_code = "lead.create"
        return super().get_permissions()

    def get_queryset(self):
        qs = super().get_queryset()
        lead_id = self.request.query_params.get("lead")
        if lead_id:
            qs = qs.filter(lead_id=lead_id)
        return qs


class CrmTaskViewSet(SchoolScopedViewSet):
    queryset = CrmTask.objects.select_related("lead", "assigned_to").all()
    serializer_class = CrmTaskSerializer
    permission_classes = [HasPermission]
    permission_code = "lead.read"

    def get_permissions(self):
        if self.action == "create":
            self.permission_code = "lead.create"
        elif self.action in ("update", "partial_update", "complete", "cancel"):
            self.permission_code = "lead.update"
        return super().get_permissions()

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        task = self.get_object()
        complete_task(task, by=request.user)
        self._audit("crm.task.complete", task, old_value={"status": "TODO"}, new_value={"status": task.status})
        return Response(CrmTaskSerializer(task).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        task = self.get_object()
        cancel_task(task, by=request.user)
        self._audit("crm.task.cancel", task, new_value={"status": task.status})
        return Response(CrmTaskSerializer(task).data)


class SchoolVisitViewSet(SchoolScopedViewSet):
    queryset = SchoolVisit.objects.select_related("lead", "toured_by").all()
    serializer_class = SchoolVisitSerializer
    permission_classes = [HasPermission]
    permission_code = "visit.read"

    def get_permissions(self):
        if self.action == "create":
            self.permission_code = "visit.create"
        elif self.action in ("update", "partial_update", "mark_attended", "no_show", "cancel", "reschedule"):
            self.permission_code = "visit.update"
        return super().get_permissions()

    @action(detail=True, methods=["post"])
    def mark_attended(self, request, pk=None):
        visit = self.get_object()
        visit = update_visit_status(visit, SchoolVisit.Status.ATTENDED, by=request.user)
        self._audit("crm.visit.attended", visit, old_value={"status": "SCHEDULED"}, new_value={"status": visit.status})
        return Response(SchoolVisitSerializer(visit).data)

    @action(detail=True, methods=["post"])
    def no_show(self, request, pk=None):
        visit = self.get_object()
        visit = update_visit_status(visit, SchoolVisit.Status.NO_SHOW, by=request.user)
        self._audit("crm.visit.no_show", visit, new_value={"status": visit.status})
        return Response(SchoolVisitSerializer(visit).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        visit = self.get_object()
        visit = update_visit_status(visit, SchoolVisit.Status.CANCELLED, by=request.user,
                                    notes=request.data.get("notes", ""))
        self._audit("crm.visit.cancel", visit, new_value={"status": visit.status})
        return Response(SchoolVisitSerializer(visit).data)

    @action(detail=True, methods=["post"])
    def reschedule(self, request, pk=None):
        visit = self.get_object()
        new_date = request.data.get("visit_date")
        if not new_date:
            raise ValidationFailedError("visit_date is required.", code="VISIT_DATE_REQUIRED")
        visit.visit_date = new_date
        visit = update_visit_status(visit, SchoolVisit.Status.RESCHEDULED, by=request.user)
        visit.save(update_fields=["visit_date", "status", "updated_at"])
        self._audit("crm.visit.reschedule", visit, new_value={"visit_date": str(new_date)})
        return Response(SchoolVisitSerializer(visit).data)