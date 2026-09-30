from django.utils import timezone
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from apps.admissions.models import AdmissionApplication, Applicant
from apps.common.exceptions import ValidationFailedError
from apps.schools.models import AcademicYear, GradeLevel, School, Term


class PublicAdmissionThrottle(AnonRateThrottle):
    scope = "public_admissions"
    rate = "20/hour"


def public_school():
    school = School.objects.filter(status="ACTIVE").order_by("created_at").first()
    if not school:
        raise ValidationFailedError("Admissions are not currently available.", code="ADMISSIONS_UNAVAILABLE", status_code=503)
    return school


class PublicApplicationView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [PublicAdmissionThrottle]

    def post(self, request):
        school = public_school()
        data = request.data
        required = ["first_name", "last_name", "guardian_name", "guardian_phone", "guardian_email", "grade_level"]
        missing = [key for key in required if not str(data.get(key, "")).strip()]
        if missing:
            raise ValidationFailedError("Required application fields are missing.", code="APPLICATION_FIELDS_REQUIRED", field_errors={key: ["This field is required."] for key in missing})
        year = AcademicYear.objects.filter(school=school, status="ACTIVE").order_by("-start_date").first()
        grade = GradeLevel.objects.filter(school=school, name__iexact=data["grade_level"]).first() or GradeLevel.objects.filter(school=school).first()
        term = Term.objects.filter(school=school, status="ACTIVE").first()
        if not year or not grade:
            raise ValidationFailedError("No admissions intake is configured.", code="INTAKE_UNAVAILABLE", status_code=503)
        applicant = Applicant.objects.create(
            school=school,
            first_name=str(data["first_name"]).strip(),
            last_name=str(data["last_name"]).strip(),
            email=str(data.get("email", "")).strip(),
            phone=str(data.get("phone", "")).strip(),
            date_of_birth=data.get("date_of_birth") or None,
            gender=str(data.get("gender", "")),
            current_school=str(data.get("current_school", "")),
            previous_results=str(data.get("previous_results", "")),
            guardian_name=str(data["guardian_name"]).strip(),
            guardian_phone=str(data["guardian_phone"]).strip(),
            guardian_email=str(data["guardian_email"]).strip(),
            address=str(data.get("address", "")),
            status=Applicant.Status.APPLIED,
        )
        number = f"APP-{timezone.now().year}-{AdmissionApplication.objects.filter(school=school).count() + 1:04d}"
        application = AdmissionApplication.objects.create(
            school=school, applicant=applicant, academic_year=year, grade_level=grade, term=term,
            application_number=number, status=AdmissionApplication.SUBMITTED, submitted_at=timezone.now(),
            notes=str(data.get("notes", "")),
        )
        return Response({"application_number": application.application_number, "status": application.status}, status=201)


class PublicApplicationTrackView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [PublicAdmissionThrottle]

    def get(self, request):
        school = public_school()
        number = (request.query_params.get("application_number") or "").strip()
        contact = (request.query_params.get("contact") or "").strip().lower()
        application = AdmissionApplication.objects.filter(school=school, application_number__iexact=number).select_related("applicant", "grade_level").first()
        if not application or not contact or contact not in {application.applicant.guardian_email.lower(), application.applicant.guardian_phone.lower(), application.applicant.email.lower(), application.applicant.phone.lower()}:
            raise ValidationFailedError("Application could not be found.", code="APPLICATION_NOT_FOUND", status_code=404)
        return Response({
            "application_number": application.application_number,
            "status": application.status,
            "applicant_name": application.applicant.full_name,
            "grade_level": application.grade_level.name,
            "submitted_at": application.submitted_at,
            "history": list(application.status_history.values("to_status", "comment", "changed_at")),
        })
