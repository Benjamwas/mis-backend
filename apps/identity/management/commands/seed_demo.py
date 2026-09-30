"""Seed a demo school with users for every portal profile, plus classes, students, finance and content.

Idempotent: wipes any existing demo data for the demo school before recreating, so the
command can be re-run safely. Pass --password to change the shared demo password.
"""
from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.academics.models import (
    Assignment,
    AssignmentGrade,
    AssignmentSubmission,
    ClassSubject,
    Enrollment,
    StudentSubjectResult,
    Subject,
    TeachingAssignment,
)
from apps.attendance.models import AttendanceSession, StudentAttendance
from apps.communication.models import Announcement
from apps.content.models import Event
from apps.finance.models import FeeStructure
from apps.finance.services import (
    apply_fee_structure_to_student,
    generate_fee_invoice,
    record_payment,
)
from apps.hr.models import (
    Department,
    Duty,
    DutyAssignment,
    Employee,
    HrTicket,
    LeaveRequest,
    LeaveType,
    PayrollPeriod,
    TeacherProfile,
)
from apps.hr.services import run_payroll
from apps.identity.models import Person, RoleCode, User
from apps.identity.services import assign_role
from apps.lms.models import Lesson, Quiz, Resource, StudentTopicProgress, Topic
from apps.people.models import Parent, ParentStudent, Student
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

DEMO_SCHOOL_CODE = "DEMO"
EMAIL_DOMAIN = "@sunrise.ac.ke"

DEMO_ACCOUNTS = [
    ("superadmin", "superadmin@sunrise.ac.ke"),
    ("admin", "admin@sunrise.ac.ke"),
    ("finance", "finance@sunrise.ac.ke"),
    ("hr", "hr@sunrise.ac.ke"),
    ("classteacher", "classteacher@sunrise.ac.ke"),
    ("subjectteacher", "subjectteacher@sunrise.ac.ke"),
    ("parent", "parent1@sunrise.ac.ke"),
    ("student", "student1@sunrise.ac.ke"),
]


class Command(BaseCommand):
    help = "Wipe and re-seed a demo school, users, classes, students, finance and content."

    def add_arguments(self, parser):
        parser.add_argument(
            "--password",
            default="password123",
            help="Password used for every seeded demo account.",
        )

    def handle(self, *args, **options):
        self.password = options["password"]
        self._teardown()
        with transaction.atomic():
            self.stdout.write("Seeding demo school...")
            school = School.objects.create(
                name="Sunrise Academy",
                code=DEMO_SCHOOL_CODE,
                slug="sunrise-academy",
                email="info@sunriseacademy.ac.ke",
                phone="+254700000000",
                address="123 Demo Road, Nairobi",
                motto="Knowledge is light",
                status="ACTIVE",
            )
            self._seed_modules(school)
            self._seed_academic_year(school)
            self._seed_people(school)
        self.stdout.write(self.style.SUCCESS("Demo data seeded."))

    def _teardown(self):
        """Remove any previously-seeded demo data in safe FK dependency order."""
        from django.apps import apps as django_apps
        from django.db.models.deletion import ProtectedError

        school = School.objects.filter(code=DEMO_SCHOOL_CODE).first()
        if not school:
            return
        school_id = school.id

        scoped = []
        for label in (
            "academics", "admissions", "attendance", "communication", "content",
            "crm", "files", "finance", "hr", "lms", "people", "schools",
        ):
            for model in django_apps.get_app_config(label).get_models():
                try:
                    model._meta.get_field("school")
                except Exception:
                    continue
                scoped.append(model)

        remaining = list(scoped)
        while remaining:
            progressed = False
            for model in list(remaining):
                manager = model.all_objects if hasattr(model, "all_objects") else model.objects
                try:
                    manager.filter(school_id=school_id).delete()
                except ProtectedError:
                    continue
                remaining.remove(model)
                progressed = True
            if not progressed:
                raise RuntimeError(
                    "Unable to order demo teardown; remaining models: "
                    + ", ".join(m.__name__ for m in remaining)
                )

        User.objects.filter(email__endswith=EMAIL_DOMAIN).delete()
        Person.objects.filter(email__endswith=EMAIL_DOMAIN).delete()
        school.delete()

    def _seed_modules(self, school):
        default_modules = [
            ("identity", "User & roles", True),
            ("students", "Student records", True),
            ("academics", "Academics", True),
            ("finance", "Finance", True),
            ("attendance", "Attendance", True),
            ("hr", "Human resources", True),
            ("admissions", "Admissions", True),
            ("crm", "CRM & leads", True),
            ("content", "CMS & events", True),
            ("reports", "Reports", True),
            ("communication", "Communication", True),
            ("files", "File manager", True),
        ]
        for code, name, core in default_modules:
            module, _ = Module.objects.get_or_create(code=code, defaults={"name": name, "is_core": core})
            SchoolModule.objects.get_or_create(
                school=school, module=module, defaults={"enabled": True}
            )
        SchoolSettings.objects.get_or_create(
            school=school, key="default_currency", defaults={"value": "KES"}
        )

    def _seed_academic_year(self, school):
        today = timezone.localdate()
        year_start = date(today.year, 1, 1)
        year_end = date(today.year, 12, 31)

        year, _ = AcademicYear.objects.get_or_create(
            school=school,
            name=str(today.year),
            defaults={
                "start_date": year_start,
                "end_date": year_end,
                "status": AcademicYear.Status.ACTIVE,
            },
        )
        term_specs = [
            ("Term 1", date(today.year, 1, 1), date(today.year, 3, 31), Term.Status.ACTIVE),
            ("Term 2", date(today.year, 5, 1), date(today.year, 7, 31), Term.Status.UPCOMING),
            ("Term 3", date(today.year, 9, 1), year_end, Term.Status.UPCOMING),
        ]
        for name, start, end, status in term_specs:
            Term.objects.get_or_create(
                academic_year=year,
                name=name,
                defaults={"school": school, "start_date": start, "end_date": end, "status": status},
            )

        grade = GradeLevel.objects.create(
            school=school,
            name="Grade 9",
            category=GradeLevel.Category.JUNIOR_SECONDARY,
            display_order=1,
        )
        clazz = SchoolClass.objects.create(
            school=school,
            academic_year=year,
            grade_level=grade,
            name="Grade 9",
            section="A",
            status=SchoolClass.Status.ACTIVE,
        )
        self.stdout.write(f"  academic structure: {year.name}, Grade 9 A")

    def _seed_people(self, school):
        self._create_platform_admin()
        admin = self._create_school_admin(school)
        self._seed_departments(school)

        year = school.active_year()
        clazz = SchoolClass.objects.filter(school=school, academic_year=year).first()
        term = Term.objects.filter(
            academic_year=year, status=Term.Status.ACTIVE
        ).first()

        class_teacher = self._create_class_teacher(school)
        subject_teacher = self._create_subject_teacher(school)
        hr_admin = self._create_hr_admin(school)
        self._create_finance_admin(school)

        if clazz and class_teacher:
            clazz.class_teacher = class_teacher
            clazz.save(update_fields=["class_teacher", "updated_at"])

        self._seed_subjects(school, clazz, subject_teacher, term)

        students = self._seed_students(school)
        if clazz and year:
            self._enroll_students(school, students, clazz, year)
        if clazz and term:
            self._seed_lms(school, students, clazz, term, subject_teacher)
        if term and clazz:
            self._seed_attendance(school, admin, clazz, students, term)

        self._seed_finance(school, students, term)
        self._seed_hr(school, hr_admin)
        self._seed_content(school, admin)

        self.stdout.write(self.style.SUCCESS(f"  demo accounts (password: {self.password}):"))
        for label, email in DEMO_ACCOUNTS:
            self.stdout.write(f"    {label:<15} {email}")
        self.stdout.write(f"  students seeded: {len(students)}")

    def _create_user(self, person, email, is_staff=False, is_superuser=False):
        return User.objects.create_user(
            person=person,
            email=email,
            username=email,
            password=self.password,
            is_staff=is_staff,
            is_superuser=is_superuser,
            status="ACTIVE",
        )

    def _create_platform_admin(self):
        """Platform-wide operator: SUPER_ADMIN with no school scope."""
        person = Person.objects.create(
            first_name="Eunice", last_name="Wafula", email="superadmin@sunrise.ac.ke"
        )
        user = self._create_user(
            person, "superadmin@sunrise.ac.ke", is_staff=True, is_superuser=True
        )
        assign_role(user, RoleCode.SUPER_ADMIN)
        return user

    def _create_school_admin(self, school):
        person = Person.objects.create(
            first_name="Amina", last_name="Wafula", email="admin@sunrise.ac.ke"
        )
        user = self._create_user(
            person, "admin@sunrise.ac.ke", is_staff=True, is_superuser=False
        )
        assign_role(user, RoleCode.SCHOOL_ADMIN, school=school)
        return user

    def _create_class_teacher(self, school):
        dept = Department.objects.filter(school=school, name="Teaching").first()
        person = Person.objects.create(
            first_name="Kevin", last_name="Otieno", email="classteacher@sunrise.ac.ke"
        )
        user = self._create_user(person, "classteacher@sunrise.ac.ke")
        employee = Employee.objects.create(
            school=school,
            person=person,
            employee_number="EMP-001",
            department=dept,
            employment_date=date(2020, 1, 10),
            role_title="Mathematics Teacher",
            base_salary=60000,
        )
        TeacherProfile.objects.create(
            school=school,
            employee=employee,
            teacher_type=TeacherProfile.TeacherType.CLASS_TEACHER,
            qualification="B.Ed Mathematics",
            specialization="Mathematics",
        )
        assign_role(user, RoleCode.CLASS_TEACHER, school=school)
        return employee

    def _create_subject_teacher(self, school):
        dept = Department.objects.filter(school=school, name="Teaching").first()
        person = Person.objects.create(
            first_name="Lydia", last_name="Achieng", email="subjectteacher@sunrise.ac.ke"
        )
        user = self._create_user(person, "subjectteacher@sunrise.ac.ke")
        employee = Employee.objects.create(
            school=school,
            person=person,
            employee_number="EMP-002",
            department=dept,
            employment_date=date(2022, 1, 5),
            role_title="English Teacher",
            base_salary=65000,
        )
        TeacherProfile.objects.create(
            school=school,
            employee=employee,
            teacher_type=TeacherProfile.TeacherType.SUBJECT_TEACHER,
            qualification="B.Ed English",
            specialization="English",
        )
        assign_role(user, RoleCode.SUBJECT_TEACHER, school=school)
        return employee

    def _create_hr_admin(self, school):
        dept = Department.objects.filter(school=school, name="Administration").first()
        person = Person.objects.create(
            first_name="Susan", last_name="Muthoni", email="hr@sunrise.ac.ke"
        )
        user = self._create_user(person, "hr@sunrise.ac.ke", is_staff=True)
        Employee.objects.create(
            school=school,
            person=person,
            employee_number="EMP-003",
            department=dept,
            employment_date=date(2021, 3, 15),
            role_title="HR Manager",
            base_salary=70000,
        )
        assign_role(user, RoleCode.HR_ADMIN, school=school)
        return user

    def _create_finance_admin(self, school):
        dept = Department.objects.filter(school=school, name="Bursary").first()
        person = Person.objects.create(
            first_name="Peter", last_name="Njoroge", email="finance@sunrise.ac.ke"
        )
        user = self._create_user(person, "finance@sunrise.ac.ke", is_staff=True)
        Employee.objects.create(
            school=school,
            person=person,
            employee_number="EMP-004",
            department=dept,
            employment_date=date(2019, 8, 1),
            role_title="Finance Officer",
            base_salary=75000,
        )
        assign_role(user, RoleCode.FINANCE_ADMIN, school=school)
        return user

    def _seed_departments(self, school):
        for name in ("Administration", "Teaching", "Bursary"):
            Department.objects.get_or_create(school=school, name=name)

    def _seed_subjects(self, school, clazz, teacher, term):
        for name, code in (
            ("Mathematics", "MATH"),
            ("English", "ENG"),
            ("Science", "SCI"),
            ("Kiswahili", "KIS"),
        ):
            subject, _ = Subject.objects.get_or_create(
                school=school, code=code, defaults={"name": name}
            )
            if not clazz:
                continue
            ClassSubject.objects.get_or_create(
                school=school, school_class=clazz, subject=subject
            )
            if term and teacher:
                TeachingAssignment.objects.get_or_create(
                    school=school,
                    teacher=teacher,
                    school_class=clazz,
                    subject=subject,
                    term=term,
                    defaults={"is_primary": True},
                )

    def _seed_students(self, school):
        students = []
        for i in range(1, 6):
            person = Person.objects.create(
                first_name=f"Student{i}",
                last_name="Demo",
                email=f"student{i}@sunrise.ac.ke",
            )
            student = Student.objects.create(
                school=school,
                person=person,
                admission_number=f"DEMO-{1000 + i}",
                admission_date=date(2020, 9, 1),
                status=Student.Status.ACTIVE,
                is_active=True,
            )
            student_user = self._create_user(person, f"student{i}@sunrise.ac.ke")
            assign_role(student_user, RoleCode.STUDENT, school=school)

            parent_person = Person.objects.create(
                first_name=f"Parent{i}",
                last_name="Demo",
                email=f"parent{i}@sunrise.ac.ke",
            )
            parent = Parent.objects.create(school=school, person=parent_person)
            ParentStudent.objects.create(
                parent=parent,
                student=student,
                relationship_type="GUARDIAN",
                is_primary_contact=True,
            )
            parent_user = self._create_user(parent_person, f"parent{i}@sunrise.ac.ke")
            assign_role(parent_user, RoleCode.PARENT, school=school)
            students.append(student)
        return students

    def _seed_lms(self, school, students, clazz, term, teacher):
        """Create a usable LMS catalogue plus submissions and results for demo accounts."""
        subjects = list(Subject.objects.filter(school=school).order_by("code"))
        topics_by_subject = {}
        for subject in subjects:
            topics = []
            for order, name in enumerate((f"{subject.name} foundations", f"{subject.name} practice"), start=1):
                topic = Topic.objects.create(
                    school=school,
                    subject=subject,
                    name=name,
                    description=f"Build confidence in {subject.name.lower()} through guided practice.",
                    order_number=order,
                    status="PUBLISHED",
                )
                topics.append(topic)
                for lesson_order, title in enumerate(("Watch and learn", "Guided practice"), start=1):
                    lesson = Lesson.objects.create(
                        school=school,
                        topic=topic,
                        title=f"{name}: {title}",
                        description="A short lesson followed by a worked example.",
                        content="Read the explanation, work through the example, then complete the practice questions.",
                        order_number=lesson_order,
                        status="PUBLISHED",
                    )
                    Resource.objects.create(
                        school=school,
                        lesson=lesson,
                        title=f"{title} notes",
                        resource_type="LINK",
                        external_url="https://example.com/sala-learning",
                        description="Supporting notes for this lesson.",
                    )
                for student in students:
                    StudentTopicProgress.objects.create(
                        school=school,
                        student=student,
                        topic=topic,
                        progress_percentage=100 if order == 1 else 35,
                        status="COMPLETED" if order == 1 else "IN_PROGRESS",
                    )
            topics_by_subject[subject.id] = topics
            Quiz.objects.create(
                school=school,
                topic=topics[0],
                title=f"{subject.name} foundations quiz",
                instructions="Choose the best answer for each question.",
                questions=[
                    {"prompt": f"Which statement best describes {subject.name.lower()} practice?", "options": ["Read, practise, reflect", "Skip the examples", "Only memorise answers", "Do not review"], "answer": 0},
                    {"prompt": "What should you do when an answer is unclear?", "options": ["Ask a question", "Leave it blank forever", "Copy without checking", "Close the lesson"], "answer": 0},
                    {"prompt": "Which habit supports progress?", "options": ["Regular practice", "Avoiding feedback", "Skipping lessons", "Submitting empty work"], "answer": 0},
                ],
                max_attempts=2,
                pass_percentage=60,
                status="PUBLISHED",
                published_at=timezone.now(),
            )

            teaching = TeachingAssignment.objects.filter(
                school=school, school_class=clazz, subject=subject, term=term
            ).first()
            if not teaching:
                continue
            topic = topics[0]
            for assignment_order, title in enumerate((f"{subject.name} practice", f"{subject.name} reflection"), start=1):
                assignment = Assignment.objects.create(
                    school=school,
                    teaching_assignment=teaching,
                    topic=topic,
                    title=title,
                    description="Complete the questions and explain your working.",
                    instructions="Show your working clearly and submit before the due date.",
                    max_marks=20,
                    due_date=timezone.now() + timedelta(days=assignment_order * 5),
                    submission_type=Assignment.SubmissionType.BOTH,
                    status=Assignment.Status.PUBLISHED,
                    created_by=teacher.user if hasattr(teacher, "user") else None,
                    published_at=timezone.now(),
                )
                for student in students[:3]:
                    submission = AssignmentSubmission.objects.create(
                        school=school,
                        assignment=assignment,
                        student=student,
                        submission_content="My completed working and answer.",
                        submitted_at=timezone.now(),
                        status=AssignmentSubmission.Status.SUBMITTED,
                    )
                    if assignment_order == 1 and student == students[0]:
                        AssignmentGrade.objects.create(
                            submission=submission,
                            graded_by=teacher.user if hasattr(teacher, "user") else User.objects.filter(is_staff=True).first(),
                            marks=16,
                            feedback="Clear working and a well-presented answer.",
                        )
                        submission.status = AssignmentSubmission.Status.GRADED
                        submission.save(update_fields=["status", "updated_at"])

            for student in students:
                StudentSubjectResult.objects.create(
                    school=school,
                    student=student,
                    subject=subject,
                    term=term,
                    total_score=72 if subject.code != "MATH" else 64,
                    grade="B" if subject.code != "MATH" else "B-",
                    teacher_comment="Keep practising and ask questions when you get stuck.",
                    status=StudentSubjectResult.Status.PUBLISHED,
                )
        self.stdout.write("  lms: topics, lessons, resources, progress, assignments and results created")

    def _enroll_students(self, school, students, clazz, year):
        for student in students:
            Enrollment.objects.get_or_create(
                school=school,
                student=student,
                school_class=clazz,
                academic_year=year,
                defaults={
                    "start_date": date(2020, 9, 1),
                    "status": Enrollment.Status.ACTIVE,
                },
            )

    def _seed_attendance(self, school, admin, clazz, students, term):
        for days_ago in (1, 2, 3, 4):
            session = AttendanceSession.objects.create(
                school=school,
                school_class=clazz,
                term=term,
                attendance_date=timezone.localdate() - timedelta(days=days_ago),
                recorded_by=admin,
                remarks="",
                status="CLOSED",
            )
            for student in students:
                StudentAttendance.objects.create(
                    school=school,
                    session=session,
                    student=student,
                    status="PRESENT",
                    remarks="",
                )

    def _seed_finance(self, school, students, term):
        structure = FeeStructure.objects.create(
            school=school,
            name="Grade 9 Tuition",
            grade_level=GradeLevel.objects.filter(school=school).first(),
            billing_cycle=FeeStructure.BillingCycle.TERM,
        )
        for name, amount in (
            ("Tuition", "20000"),
            ("Lunch", "5000"),
            ("Transport", "4000"),
            ("Books", "6000"),
        ):
            structure.items.get_or_create(
                school=school,
                name=name,
                defaults={"amount": amount, "is_mandatory": True, "is_recurring": True},
            )

        for student in students[:3]:
            apply_fee_structure_to_student(
                school=school, student=student, fee_structure_id=structure.id
            )
            invoice = generate_fee_invoice(school=school, student=student, term=term)
            if student.admission_number.endswith("001"):
                record_payment(
                    school=school,
                    student=student,
                    amount="35000",
                    method="CASH",
                    status="SUCCESS",
                    allocations=[{"invoice_id": str(invoice.id), "amount": "35000"}],
                    by=None,
                    metadata={"demo": True},
                )
        self.stdout.write("  finance: fee structure, invoices and a cash payment created")

    def _seed_hr(self, school, hr_admin):
        employees = list(Employee.objects.filter(school=school).order_by("employee_number"))
        leave_types = []
        for name, days, paid in (("Annual leave", 21, True), ("Sick leave", 14, True), ("Compassionate leave", 7, False)):
            leave_types.append(LeaveType.objects.create(school=school, name=name, days_allowed=days, is_paid=paid))

        if employees:
            LeaveRequest.objects.create(
                school=school,
                employee=employees[0],
                leave_type=leave_types[0],
                start_date=timezone.localdate() + timedelta(days=14),
                end_date=timezone.localdate() + timedelta(days=18),
                reason="Family travel",
                status=LeaveRequest.Status.PENDING,
            )

        today = timezone.localdate()
        period = PayrollPeriod.objects.create(
            school=school,
            name=f"{today.strftime('%B')} {today.year}",
            start_date=today.replace(day=1),
            end_date=today,
            status=PayrollPeriod.Status.OPEN,
            payment_date=today + timedelta(days=3),
        )
        run_payroll(period, by=hr_admin)

        duties = []
        for name, location in (("Gate supervision", "Main Gate"), ("Break supervision", "Lower Field"), ("Lunch hall", "Dining Hall")):
            duties.append(Duty.objects.create(school=school, name=name, location=location))
        for index, duty in enumerate(duties):
            if employees:
                DutyAssignment.objects.create(
                    school=school,
                    duty=duty,
                    employee=employees[index % len(employees)],
                    date=today + timedelta(days=index + 1),
                    status="SCHEDULED",
                )

        if employees:
            HrTicket.objects.create(
                school=school,
                employee=employees[0],
                category="PAYROLL",
                subject="Payslip deduction question",
                description="Please confirm the deduction shown on the latest payslip.",
                priority="MEDIUM",
                status="OPEN",
            )
        self.stdout.write("  hr: leave types, pending leave, payroll, duties and ticket created")

    def _seed_content(self, school, admin):
        Announcement.objects.create(
            school=school,
            title="Welcome to the new term",
            body="Classes resume as scheduled. Timetables are posted on the noticeboard.",
            audience="ALL",
            channels=["IN_APP", "EMAIL"],
            published_at=timezone.now(),
            status="PUBLISHED",
            created_by=admin,
        )
        Event.objects.create(
            school=school,
            title="Inter-class Sports Day",
            description="Annual athletics, football and basketball tournament.",
            event_type=Event.EventType.SPORTS,
            start_time=timezone.now() + timedelta(days=10),
            end_time=timezone.now() + timedelta(days=10, hours=6),
            venue="Main Field",
            capacity=200,
            status=Event.Status.PUBLISHED,
            allow_registration=True,
            published_at=timezone.now(),
            created_by=admin,
        )
