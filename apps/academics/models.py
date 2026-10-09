"""Academic domain: subjects, class subjects, enrollments, teaching assignments,
assignments, submissions, grading, assessments, scores, results and learning recommendations."""
from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.common.models import SchoolScopedModel, SoftDeleteModel, TimeStampedModel, UUIDPKMixin


# --------------------------------------------------------------------------
# Subjects & class-subject linking
# --------------------------------------------------------------------------
class Subject(UUIDPKMixin, TimeStampedModel, SoftDeleteModel, SchoolScopedModel):
    name = models.CharField(max_length=120)
    code = models.CharField(max_length=20, db_index=True)
    description = models.TextField(blank=True, default="")
    status = models.CharField(max_length=12, default="ACTIVE", db_index=True, choices=(
        ("ACTIVE", "Active"), ("ARCHIVED", "Archived"), ("INACTIVE", "Inactive"),
    ))

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["school", "code"], name="uq_subject_code_school"),
            models.UniqueConstraint(fields=["school", "name"], name="uq_subject_name_school"),
        ]

    def __str__(self):
        return f"{self.code} {self.name}"


class ClassSubject(UUIDPKMixin, TimeStampedModel, SchoolScopedModel):
    school_class = models.ForeignKey("schools.SchoolClass", on_delete=models.CASCADE, related_name="class_subjects")
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name="class_subjects")

    class Meta:
        ordering = ["subject__name"]
        constraints = [
            models.UniqueConstraint(fields=["school_class", "subject"], name="uq_class_subject"),
        ]

    def __str__(self):
        return f"{self.school_class_id}:{self.subject_id}"


# --------------------------------------------------------------------------
# Teaching assignments (authoritative teacher->class->subject->term)
# --------------------------------------------------------------------------
class TeachingAssignment(UUIDPKMixin, TimeStampedModel, SoftDeleteModel, SchoolScopedModel):
    teacher = models.ForeignKey("hr.Employee", on_delete=models.CASCADE, related_name="teaching_assignments")
    school_class = models.ForeignKey("schools.SchoolClass", on_delete=models.CASCADE, related_name="teaching_assignments")
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name="teaching_assignments")
    term = models.ForeignKey("schools.Term", on_delete=models.CASCADE, related_name="teaching_assignments")
    is_primary = models.BooleanField(default=False)
    status = models.CharField(max_length=12, default="ACTIVE", db_index=True, choices=(
        ("ACTIVE", "Active"), ("INACTIVE", "Inactive"), ("ARCHIVED", "Archived"),
    ))

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["teacher", "school_class", "subject", "term"],
                name="uq_teaching_assignment",
            ),
        ]

    def __str__(self):
        return f"{self.teacher_id} {self.school_class_id} {self.subject_id}"


class StudentGroup(UUIDPKMixin, TimeStampedModel, SchoolScopedModel):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        ARCHIVED = "ARCHIVED", "Archived"

    school_class = models.ForeignKey("schools.SchoolClass", on_delete=models.CASCADE, related_name="student_groups")
    subject = models.ForeignKey(Subject, on_delete=models.SET_NULL, null=True, blank=True, related_name="student_groups")
    name = models.CharField(max_length=160)
    description = models.TextField(blank=True, default="")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ACTIVE, db_index=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="created_student_groups")

    class Meta:
        ordering = ["name"]


class StudentGroupMember(UUIDPKMixin, TimeStampedModel):
    group = models.ForeignKey(StudentGroup, on_delete=models.CASCADE, related_name="members")
    student = models.ForeignKey("people.Student", on_delete=models.CASCADE, related_name="student_groups")
    is_leader = models.BooleanField(default=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["group", "student"], name="uq_student_group_member")]


# --------------------------------------------------------------------------
# Enrollments
# --------------------------------------------------------------------------
class Enrollment(UUIDPKMixin, TimeStampedModel, SoftDeleteModel, SchoolScopedModel):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        COMPLETED = "COMPLETED", "Completed"
        TRANSFERRED_OUT = "TRANSFERRED_OUT", "Transferred Out"
        DROPPED = "DROPPED", "Dropped"
        PENDING = "PENDING", "Pending"

    student = models.ForeignKey("people.Student", on_delete=models.CASCADE, related_name="enrollments")
    school_class = models.ForeignKey("schools.SchoolClass", on_delete=models.CASCADE, related_name="enrollments")
    academic_year = models.ForeignKey("schools.AcademicYear", on_delete=models.CASCADE, related_name="enrollments")
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.PENDING, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["student", "status"], name="idx_enrollment_student_status"),
            models.Index(fields=["school_class", "status"], name="idx_enrollment_class_status"),
        ]

    def __str__(self):
        return f"{self.student_id}->{self.school_class_id} ({self.status})"


# --------------------------------------------------------------------------
# Assignments
# --------------------------------------------------------------------------
class Assignment(UUIDPKMixin, TimeStampedModel, SoftDeleteModel, SchoolScopedModel):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        PUBLISHED = "PUBLISHED", "Published"
        CLOSED = "CLOSED", "Closed"
        ARCHIVED = "ARCHIVED", "Archived"

    class SubmissionType(models.TextChoices):
        TEXT = "TEXT", "Text"
        FILE = "FILE", "File"
        QUIZ = "QUIZ", "Quiz"
        BOTH = "BOTH", "Both"

    teaching_assignment = models.ForeignKey(TeachingAssignment, on_delete=models.PROTECT, related_name="assignments")
    topic = models.ForeignKey("lms.Topic", on_delete=models.SET_NULL, null=True, blank=True, related_name="assignments")
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    instructions = models.TextField(blank=True, default="")
    max_marks = models.DecimalField(max_digits=6, decimal_places=2, default=100)
    due_date = models.DateTimeField(null=True, blank=True)
    submission_type = models.CharField(max_length=10, choices=SubmissionType.choices, default=SubmissionType.TEXT)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT, db_index=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="created_assignments")
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title

    def publish(self, by=None):
        from django.utils import timezone

        self.status = Assignment.Status.PUBLISHED
        self.published_at = timezone.now()
        self.save(update_fields=["status", "published_at", "updated_at"])

    def close(self):
        self.status = Assignment.Status.CLOSED
        self.save(update_fields=["status", "updated_at"])


class AssignmentSubmission(UUIDPKMixin, TimeStampedModel, SoftDeleteModel, SchoolScopedModel):
    class Status(models.TextChoices):
        NOT_STARTED = "NOT_STARTED", "Not Started"
        IN_PROGRESS = "IN_PROGRESS", "In Progress"
        SUBMITTED = "SUBMITTED", "Submitted"
        RETURNED = "RETURNED", "Returned"
        GRADED = "GRADED", "Graded"
        OVERDUE = "OVERDUE", "Overdue"
        LATE = "LATE", "Late"

    assignment = models.ForeignKey(Assignment, on_delete=models.CASCADE, related_name="submissions")
    student = models.ForeignKey("people.Student", on_delete=models.CASCADE, related_name="assignment_submissions")
    submission_content = models.TextField(blank=True, default="")
    submitted_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.NOT_STARTED, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["assignment", "student"], name="uq_assignment_student"),
        ]


class AssignmentGrade(UUIDPKMixin, TimeStampedModel):
    submission = models.ForeignKey(AssignmentSubmission, on_delete=models.CASCADE, related_name="grades")
    graded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="assignment_grades")
    marks = models.DecimalField(max_digits=8, decimal_places=2)
    feedback = models.TextField(blank=True, default="")
    graded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-graded_at"]

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.marks is not None and self.submission_id and self.marks > self.submission.assignment.max_marks:
            raise ValidationError({"marks": "Marks cannot exceed the assignment maximum."})


# --------------------------------------------------------------------------
# Assessments & scores
# --------------------------------------------------------------------------
class Assessment(UUIDPKMixin, TimeStampedModel, SoftDeleteModel, SchoolScopedModel):
    class AssessmentType(models.TextChoices):
        QUIZ = "QUIZ", "Quiz"
        TEST = "TEST", "Test"
        CAT = "CAT", "CAT"
        EXAM = "EXAM", "Exam"
        PROJECT = "PROJECT", "Project"
        ASSIGNMENT = "ASSIGNMENT", "Assignment"
        CONTINUOUS_ASSESSMENT = "CONTINUOUS_ASSESSMENT", "Continuous Assessment"

    teaching_assignment = models.ForeignKey(TeachingAssignment, on_delete=models.PROTECT, related_name="assessments")
    term = models.ForeignKey("schools.Term", on_delete=models.CASCADE, related_name="assessments")
    title = models.CharField(max_length=255)
    assessment_type = models.CharField(max_length=25, choices=AssessmentType.choices, default=AssessmentType.TEST)
    max_score = models.DecimalField(max_digits=7, decimal_places=2)
    date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=12, default="DRAFT", db_index=True, choices=(
        ("DRAFT", "Draft"), ("PUBLISHED", "Published"), ("CLOSED", "Closed"),
    ))

    class Meta:
        ordering = ["-date"]

    def __str__(self):
        return self.title


class AssessmentScore(UUIDPKMixin, TimeStampedModel, SoftDeleteModel, SchoolScopedModel):
    assessment = models.ForeignKey(Assessment, on_delete=models.CASCADE, related_name="scores")
    student = models.ForeignKey("people.Student", on_delete=models.CASCADE, related_name="assessment_scores")
    score = models.DecimalField(max_digits=7, decimal_places=2, validators=[MinValueValidator(0)])
    grade = models.CharField(max_length=2, blank=True, default="")
    teacher_comment = models.TextField(blank=True, default="")
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="recorded_scores")

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["assessment", "student"], name="uq_assessment_student"),
        ]

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.score is not None and self.assessment_id and self.score > self.assessment.max_score:
            raise ValidationError({"score": "Score cannot exceed the assessment maximum."})


# --------------------------------------------------------------------------
# Results
# --------------------------------------------------------------------------
class StudentSubjectResult(UUIDPKMixin, TimeStampedModel, SoftDeleteModel, SchoolScopedModel):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        SUBMITTED = "SUBMITTED", "Submitted"
        VERIFIED = "VERIFIED", "Verified"
        PUBLISHED = "PUBLISHED", "Published"

    student = models.ForeignKey("people.Student", on_delete=models.CASCADE, related_name="subject_results")
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name="subject_results")
    term = models.ForeignKey("schools.Term", on_delete=models.CASCADE, related_name="subject_results")
    total_score = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    grade = models.CharField(max_length=2, blank=True, default="")
    teacher_comment = models.TextField(blank=True, default="")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT, db_index=True)

    class Meta:
        ordering = ["-term__start_date"]
        constraints = [
            models.UniqueConstraint(fields=["student", "subject", "term"], name="uq_student_subject_term"),
        ]

    def publish(self, by=None):
        self.status = StudentSubjectResult.Status.PUBLISHED
        self.save(update_fields=["status", "updated_at"])


# --------------------------------------------------------------------------
# Personalized learning (rule-based foundation)
# --------------------------------------------------------------------------
class LearningRecommendation(UUIDPKMixin, TimeStampedModel, SchoolScopedModel):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        COMPLETED = "COMPLETED", "Completed"
        DISMISSED = "DISMISSED", "Dismissed"

    class Priority(models.TextChoices):
        LOW = "LOW", "Low"
        MEDIUM = "MEDIUM", "Medium"
        HIGH = "HIGH", "High"

    student = models.ForeignKey("people.Student", on_delete=models.CASCADE, related_name="learning_recommendations")
    topic = models.ForeignKey("lms.Topic", on_delete=models.SET_NULL, null=True, blank=True, related_name="recommendations")
    subject = models.ForeignKey(Subject, on_delete=models.SET_NULL, null=True, blank=True, related_name="recommendations")
    reason = models.CharField(max_length=255)
    detail = models.TextField(blank=True, default="")
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.MEDIUM)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ACTIVE, db_index=True)

    class Meta:
        ordering = ["-created_at"]


# --------------------------------------------------------------------------
# Timetable
# --------------------------------------------------------------------------
class SchoolPeriod(UUIDPKMixin, TimeStampedModel, SchoolScopedModel):
    name = models.CharField(max_length=40)
    start_time = models.TimeField()
    end_time = models.TimeField()
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["display_order", "start_time"]

    def __str__(self):
        return f"{self.name} ({self.start_time}-{self.end_time})"


class TimetableSlot(UUIDPKMixin, TimeStampedModel, SchoolScopedModel):
    DAY_CHOICES = (
        ("MON", "Monday"), ("TUE", "Tuesday"), ("WED", "Wednesday"),
        ("THU", "Thursday"), ("FRI", "Friday"), ("SAT", "Saturday"),
    )
    school_class = models.ForeignKey("schools.SchoolClass", on_delete=models.CASCADE, related_name="timetable_slots")
    period = models.ForeignKey(SchoolPeriod, on_delete=models.CASCADE, related_name="timetable_slots")
    teaching_assignment = models.ForeignKey(TeachingAssignment, on_delete=models.CASCADE, related_name="timetable_slots", null=True, blank=True)
    day_of_week = models.CharField(max_length=3, choices=DAY_CHOICES, db_index=True)
    room = models.CharField(max_length=60, blank=True, default="")
    status = models.CharField(max_length=12, default="ACTIVE", choices=(
        ("ACTIVE", "Active"), ("CANCELLED", "Cancelled"),
    ))

    class Meta:
        ordering = ["day_of_week", "period__display_order"]
        constraints = [
            models.UniqueConstraint(fields=["school_class", "period", "day_of_week"], name="uq_timetable_slot_class_period_day"),
        ]

    def __str__(self):
        return f"{self.school_class_id} {self.day_of_week} {self.period_id}"
