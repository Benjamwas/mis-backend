"""Global search across school-scoped records."""
from django.urls import path
from django.db.models import Q
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.exceptions import ValidationFailedError
from apps.common.permissions import HasPermission
from apps.identity.services import resolve_school_context


class GlobalSearchView(APIView):
    permission_classes = [HasPermission]
    permission_code = "report.read"

    def _school(self, request):
        school = resolve_school_context(request)
        if request.user.is_superuser and school is None:
            return None  # platform-wide
        return school

    def _scoped(self, qs, school):
        if school is not None:
            return qs.filter(school=school)
        return qs

    def get(self, request):
        q = (request.query_params.get("q") or "").strip()
        if len(q) < 2:
            raise ValidationFailedError("Search term must be at least 2 characters.", code="QUERY_TOO_SHORT")
        school = self._school(request)
        search_type = request.query_params.get("type")

        result = {
            "students": [], "parents": [], "staff": [], "invoices": [],
            "leads": [], "applications": [], "announcements": [], "events": [], "cms_pages": [],
        }

        if not search_type or search_type == "student":
            from apps.people.models import Student

            qs = self._scoped(Student.objects.select_related("person"), school)
            names = qs.filter(Q(person__first_name__icontains=q) | Q(person__last_name__icontains=q))
            by_num = qs.filter(admission_number__icontains=q) if q.isdigit() else qs.none()
            seen = set()
            for s in list(names[:10]) + list(by_num[:10]):
                if s.id in seen:
                    continue
                seen.add(s.id)
                result["students"].append({
                    "id": s.id, "name": s.full_name, "admission_number": s.admission_number, "status": s.status,
                })
                if len(result["students"]) >= 10:
                    break

        if not search_type or search_type == "parent":
            from apps.people.models import Parent

            qs = self._scoped(Parent.objects.select_related("person"), school).filter(
                Q(person__first_name__icontains=q) | Q(person__last_name__icontains=q) | Q(person__email__icontains=q)
            )
            result["parents"] = [
                {"id": p.id, "name": p.full_name, "email": p.person.email, "phone": p.person.phone}
                for p in qs[:10]
            ]

        if not search_type or search_type == "staff":
            from apps.hr.models import Employee

            qs = self._scoped(Employee.objects.select_related("person", "department"), school).filter(
                Q(person__first_name__icontains=q) | Q(person__last_name__icontains=q) | Q(employee_number__icontains=q)
            )
            result["staff"] = [
                {"id": e.id, "name": e.full_name, "employee_number": e.employee_number,
                 "department": e.department.name if e.department_id else ""}
                for e in qs[:10]
            ]

        if not search_type or search_type == "invoice":
            from apps.finance.models import Invoice

            qs = self._scoped(Invoice.objects.select_related("student__person"), school).filter(
                Q(invoice_number__icontains=q) | Q(student__person__first_name__icontains=q)
                | Q(student__person__last_name__icontains=q)
            )
            result["invoices"] = [
                {"id": inv.id, "invoice_number": inv.invoice_number, "student": inv.student.full_name,
                 "status": inv.status, "amount_due": str(inv.amount_due)}
                for inv in qs[:10]
            ]

        if not search_type or search_type == "lead":
            from apps.crm.models import CrmLead

            qs = self._scoped(CrmLead.objects.all(), school).filter(
                Q(first_name__icontains=q) | Q(last_name__icontains=q) | Q(email__icontains=q) | Q(phone__icontains=q)
            )
            result["leads"] = [
                {"id": l.id, "name": l.full_name, "email": l.email, "phone": l.phone, "status": l.status}
                for l in qs[:10]
            ]

        if not search_type or search_type == "application":
            from apps.admissions.models import AdmissionApplication

            qs = self._scoped(AdmissionApplication.objects.select_related("applicant"), school).filter(
                Q(application_number__icontains=q) | Q(applicant__first_name__icontains=q)
                | Q(applicant__last_name__icontains=q)
            )
            result["applications"] = [
                {"id": a.id, "number": a.application_number, "applicant": a.applicant.full_name, "status": a.status}
                for a in qs[:10]
            ]

        if not search_type or search_type == "announcement":
            from apps.communication.models import Announcement

            qs = self._scoped(Announcement.objects.all(), school).filter(
                Q(title__icontains=q) | Q(body__icontains=q)
            )
            result["announcements"] = [
                {"id": a.id, "title": a.title, "status": a.status} for a in qs[:10]
            ]

        if not search_type or search_type == "event":
            from apps.content.models import Event

            qs = self._scoped(Event.objects.all(), school).filter(Q(title__icontains=q))
            result["events"] = [
                {"id": e.id, "title": e.title, "status": e.status} for e in qs[:10]
            ]

        if not search_type or search_type == "cms_page":
            from apps.content.models import CmsPage

            qs = self._scoped(CmsPage.objects.all(), school).filter(Q(title__icontains=q) | Q(slug__icontains=q))
            result["cms_pages"] = [
                {"id": p.id, "title": p.title, "slug": p.slug, "status": p.status} for p in qs[:10]
            ]

        return Response(result)


urlpatterns = [path("", GlobalSearchView.as_view(), name="global-search")]