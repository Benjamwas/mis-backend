"""Content CMS: pages, posts, events, gallery."""
from django.conf import settings
from django.db import models

from apps.common.models import SchoolScopedModel, SoftDeleteModel, TimeStampedModel, UUIDPKMixin


class CmsPage(UUIDPKMixin, TimeStampedModel, SoftDeleteModel, SchoolScopedModel):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        PUBLISHED = "PUBLISHED", "Published"

    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255)
    content = models.TextField(blank=True, default="")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT, db_index=True)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="cms_pages")
    published_at = models.DateTimeField(null=True, blank=True)
    meta_title = models.CharField(max_length=255, blank=True, default="")
    meta_description = models.CharField(max_length=400, blank=True, default="")
    template_name = models.CharField(max_length=120, blank=True, default="")

    class Meta:
        ordering = ["title"]
        constraints = [models.UniqueConstraint(fields=["school", "slug"], name="uq_cms_slug_school")]

    def __str__(self):
        return self.title


class CmsPost(UUIDPKMixin, TimeStampedModel, SoftDeleteModel, SchoolScopedModel):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        PUBLISHED = "PUBLISHED", "Published"

    class Category(models.TextChoices):
        NEWS = "NEWS", "News"
        ACHIEVEMENT = "ACHIEVEMENT", "Achievement"
        ANNOUNCEMENT = "ANNOUNCEMENT", "Announcement"
        OTHER = "OTHER", "Other"

    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255)
    excerpt = models.CharField(max_length=400, blank=True, default="")
    content = models.TextField()
    featured_image = models.ForeignKey("files.FileUpload", on_delete=models.SET_NULL, null=True, blank=True, related_name="cms_posts")
    category = models.CharField(max_length=12, choices=Category.choices, default=Category.NEWS, db_index=True)
    tags = models.CharField(max_length=255, blank=True, default="")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT, db_index=True)
    published_at = models.DateTimeField(null=True, blank=True)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="cms_posts")

    class Meta:
        ordering = ["-published_at", "-created_at"]
        constraints = [models.UniqueConstraint(fields=["school", "slug"], name="uq_cms_post_slug_school")]

    def __str__(self):
        return self.title


class Event(UUIDPKMixin, TimeStampedModel, SoftDeleteModel, SchoolScopedModel):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        PUBLISHED = "PUBLISHED", "Published"
        CANCELLED = "CANCELLED", "Cancelled"
        COMPLETED = "COMPLETED", "Completed"

    class EventType(models.TextChoices):
        ACADEMIC = "ACADEMIC", "Academic"
        SPORTS = "SPORTS", "Sports"
        CULTURAL = "CULTURAL", "Cultural"
        MEETING = "MEETING", "Meeting"
        FUN = "FUN", "Fun"
        FUNDRAISER = "FUNDRAISER", "Fundraiser"
        OTHER = "OTHER", "Other"

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    event_type = models.CharField(max_length=12, choices=EventType.choices, default=EventType.OTHER)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField(null=True, blank=True)
    venue = models.CharField(max_length=200, blank=True, default="")
    capacity = models.PositiveIntegerField(null=True, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT, db_index=True)
    cover_image = models.ForeignKey("files.FileUpload", on_delete=models.SET_NULL, null=True, blank=True, related_name="events")
    allow_registration = models.BooleanField(default=True)
    is_recurring = models.BooleanField(default=False)
    published_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="events_created")

    class Meta:
        ordering = ["-start_time"]

    @property
    def participant_count(self):
        return self.participants.count()

    def __str__(self):
        return self.title


class EventParticipant(UUIDPKMixin, TimeStampedModel, SchoolScopedModel):
    class Status(models.TextChoices):
        CONFIRMED = "CONFIRMED", "Confirmed"
        CANCELLED = "CANCELLED", "Cancelled"
        ATTENDED = "ATTENDED", "Attended"

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="participants")
    full_name = models.CharField(max_length=200)
    email = models.EmailField(blank=True, default="")
    phone = models.CharField(max_length=20, blank=True, default="")
    student = models.ForeignKey("people.Student", on_delete=models.SET_NULL, null=True, blank=True, related_name="event_participations")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.CONFIRMED, db_index=True)
    checked_in_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["event", "email"], name="uq_event_participant_email")]

    def __str__(self):
        return f"{self.event_id}:{self.full_name}"


class GalleryAlbum(UUIDPKMixin, TimeStampedModel, SoftDeleteModel, SchoolScopedModel):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        PUBLISHED = "PUBLISHED", "Published"

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    cover_image = models.ForeignKey("files.FileUpload", on_delete=models.SET_NULL, null=True, blank=True, related_name="gallery_albums_cover")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT, db_index=True)
    published_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="gallery_albums")

    class Meta:
        ordering = ["-created_at"]

    @property
    def media_count(self):
        return self.media.count()

    def __str__(self):
        return self.title


class GalleryMedia(UUIDPKMixin, TimeStampedModel, SchoolScopedModel):
    album = models.ForeignKey(GalleryAlbum, on_delete=models.CASCADE, related_name="media")
    file = models.ForeignKey("files.FileUpload", on_delete=models.CASCADE, related_name="gallery_media")
    caption = models.CharField(max_length=200, blank=True, default="")
    sort_order = models.PositiveIntegerField(default=0)
    is_cover = models.BooleanField(default=False)

    class Meta:
        ordering = ["sort_order", "created_at"]

    def __str__(self):
        return f"{self.album_id}:{self.file_id}"