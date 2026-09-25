"""CRM: leads, interactions, tasks and school visits."""
from django.conf import settings
from django.db import models

from apps.common.models import SchoolScopedModel, SoftDeleteModel, TimeStampedModel, UUIDPKMixin


class CrmLead(UUIDPKMixin, TimeStampedModel, SoftDeleteModel, SchoolScopedModel):
    class Source(models.TextChoices):
        WALK_IN = "WALK_IN", "Walk-in"
        REFERRAL = "REFERRAL", "Referral"
        WEBSITE = "WEBSITE", "Website"
        ADMISSIONS = "ADMISSIONS", "Admissions"
        SOCIAL_MEDIA = "SOCIAL_MEDIA", "Social Media"
        EXISTING_PARENT = "EXISTING_PARENT", "Existing Parent"
        OTHER = "OTHER", "Other"

    class Status(models.TextChoices):
        NEW = "NEW", "New"
        CONTACTED = "CONTACTED", "Contacted"
        QUALIFIED = "QUALIFIED", "Qualified"
        CONVERTED = "CONVERTED", "Converted"
        LOST = "LOST", "Lost"
        ARCHIVED = "ARCHIVED", "Archived"

    person = models.ForeignKey("identity.Person", on_delete=models.PROTECT, null=True, blank=True, related_name="crm_leads")
    first_name = models.CharField(max_length=120, blank=True, default="")
    last_name = models.CharField(max_length=120, blank=True, default="")
    email = models.EmailField(blank=True, default="")
    phone = models.CharField(max_length=20, blank=True, default="")
    source = models.CharField(max_length=20, choices=Source.choices, default=Source.OTHER, db_index=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.NEW, db_index=True)
    interested_grade = models.ForeignKey("schools.GradeLevel", on_delete=models.SET_NULL, null=True, blank=True, related_name="crm_leads")
    preferred_class = models.ForeignKey("schools.SchoolClass", on_delete=models.SET_NULL, null=True, blank=True, related_name="crm_leads")
    notes = models.TextField(blank=True, default="")
    converted_to_student = models.ForeignKey("people.Student", on_delete=models.SET_NULL, null=True, blank=True, related_name="crm_lead")
    follow_up_date = models.DateField(null=True, blank=True)
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="crm_leads")
    last_contacted_at = models.DateTimeField(null=True, blank=True)
    opt_in_sms = models.BooleanField(default=True)
    opt_in_email = models.BooleanField(default=True)

    class Meta:
        ordering = ["-created_at"]

    @property
    def full_name(self):
        if self.person:
            return self.person.full_name
        return f"{self.first_name} {self.last_name}".strip()

    def __str__(self):
        return self.full_name


class CrmInteraction(UUIDPKMixin, TimeStampedModel, SchoolScopedModel):
    class InteractionType(models.TextChoices):
        CALL = "CALL", "Call"
        EMAIL = "EMAIL", "Email"
        SMS = "SMS", "SMS"
        WHATSAPP = "WHATSAPP", "WhatsApp"
        MEETING = "MEETING", "Meeting"
        VISIT = "VISIT", "Visit"
        FOLLOW_UP = "FOLLOW_UP", "Follow Up"

    class Outcome(models.TextChoices):
        NO_ANSWER = "NO_ANSWER", "No Answer"
        LEFT_MESSAGE = "LEFT_MESSAGE", "Left Message"
        CONTACTED = "CONTACTED", "Contacted"
        NOT_INTERESTED = "NOT_INTERESTED", "Not Interested"
        BOOKED_VISIT = "BOOKED_VISIT", "Booked Visit"
        OTHER = "OTHER", "Other"

    lead = models.ForeignKey(CrmLead, on_delete=models.CASCADE, related_name="interactions")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="crm_interactions")
    interaction_type = models.CharField(max_length=12, choices=InteractionType.choices, db_index=True)
    notes = models.TextField(blank=True, default="")
    outcome = models.CharField(max_length=20, choices=Outcome.choices, blank=True, default="")
    scheduled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.lead_id}:{self.interaction_type}"


class CrmTask(UUIDPKMixin, TimeStampedModel, SchoolScopedModel):
    class Status(models.TextChoices):
        TODO = "TODO", "To Do"
        IN_PROGRESS = "IN_PROGRESS", "In Progress"
        DONE = "DONE", "Done"
        CANCELLED = "CANCELLED", "Cancelled"

    lead = models.ForeignKey(CrmLead, on_delete=models.CASCADE, related_name="tasks", null=True, blank=True)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    due_date = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.TODO, db_index=True)
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="crm_tasks")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="crm_tasks_created")

    class Meta:
        ordering = ["due_date", "-created_at"]

    def __str__(self):
        return self.title


class SchoolVisit(UUIDPKMixin, TimeStampedModel, SchoolScopedModel):
    class Status(models.TextChoices):
        SCHEDULED = "SCHEDULED", "Scheduled"
        ATTENDED = "ATTENDED", "Attended"
        NO_SHOW = "NO_SHOW", "No Show"
        CANCELLED = "CANCELLED", "Cancelled"
        RESCHEDULED = "RESCHEDULED", "Rescheduled"

    lead = models.ForeignKey(CrmLead, on_delete=models.SET_NULL, null=True, blank=True, related_name="school_visits")
    student_name = models.CharField(max_length=200, blank=True, default="")
    parent_name = models.CharField(max_length=200, blank=True, default="")
    parent_phone = models.CharField(max_length=20, blank=True, default="")
    parent_email = models.EmailField(blank=True, default="")
    visit_date = models.DateTimeField()
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.SCHEDULED, db_index=True)
    toured_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="school_visits")
    notes = models.TextField(blank=True, default="")
    feedback = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["visit_date"]

    def __str__(self):
        return f"{self.parent_name or self.student_name} {self.visit_date.date()}"