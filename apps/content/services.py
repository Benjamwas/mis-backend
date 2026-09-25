"""Content business services: publishing, event registration, gallery."""
import logging

from django.db import transaction
from django.utils import timezone

from apps.common.exceptions import ConflictError, ValidationFailedError
from apps.content.models import Event, EventParticipant, GalleryAlbum, GalleryMedia

logger = logging.getLogger("apps.content")


def publish(obj, by=None):
    if getattr(obj, "status", "DRAFT") == "PUBLISHED":
        raise ConflictError("Content is already published.", code="ALREADY_PUBLISHED")
    obj.status = obj.Status.PUBLISHED if hasattr(obj.Status, "PUBLISHED") else "PUBLISHED"
    obj.published_at = timezone.now()
    obj.save(update_fields=["status", "published_at"])
    return obj


def unpublish(obj, by=None):
    obj.status = obj.Status.DRAFT
    obj.published_at = None
    obj.save(update_fields=["status", "published_at"])
    return obj


@transaction.atomic
def register_event_participant(*, event, full_name, email, phone="", student=None, student_id=None, by=None) -> EventParticipant:
    if not event.allow_registration:
        raise ValidationFailedError("Registration is closed for this event.", code="REGISTRATION_CLOSED")
    confirmed = event.participants.exclude(status=EventParticipant.Status.CANCELLED).count()
    if event.capacity and confirmed >= event.capacity:
        raise ConflictError("This event is fully booked.", code="EVENT_FULL")
    if EventParticipant.objects.filter(event=event, email__iexact=email).exists():
        raise ConflictError("You are already registered for this event.", code="ALREADY_REGISTERED")

    if student_id and student is None:
        from apps.people.models import Student

        student = Student.objects.filter(school=event.school, id=student_id).first()

    participant = EventParticipant.objects.create(
        school=event.school, event=event, full_name=full_name, email=email, phone=phone, student=student,
    )

    from apps.communication.tasks import send_transactional_email_job

    if email:
        send_transactional_email_job.delay(
            to_email=email,
            subject=f"Event Confirmation - {event.title}",
            template="event_confirmation",
            context={"name": full_name, "event": event.title,
                     "start_time": event.start_time.isoformat(), "venue": event.venue},
        )
    return participant


def cancel_registration(participant, by=None):
    if participant.status == EventParticipant.Status.CANCELLED:
        raise ConflictError("Registration is already cancelled.", code="ALREADY_CANCELLED")
    participant.status = EventParticipant.Status.CANCELLED
    participant.save(update_fields=["status", "updated_at"])
    return participant


def check_in_participant(participant, by=None):
    if participant.status == EventParticipant.Status.CANCELLED:
        raise ValidationFailedError("Cannot check in a cancelled registration.", code="REGISTRATION_CANCELLED")
    participant.status = EventParticipant.Status.ATTENDED
    participant.checked_in_at = timezone.now()
    participant.save(update_fields=["status", "checked_in_at", "updated_at"])
    return participant


def add_media_to_album(*, album, file, caption="", sort_order=0, is_cover=False) -> GalleryMedia:
    media = GalleryMedia.objects.create(
        school=album.school, album=album, file=file, caption=caption, sort_order=sort_order,
    )
    if is_cover or not album.cover_image_id:
        album.cover_image = file
        album.save(update_fields=["cover_image", "updated_at"])
        if is_cover:
            GalleryMedia.objects.filter(album=album).exclude(pk=media.pk).update(is_cover=False)
            media.is_cover = True
            media.save(update_fields=["is_cover"])
    return media


def set_album_cover(album, media, by=None):
    album.cover_image = media.file
    album.save(update_fields=["cover_image", "updated_at"])
    GalleryMedia.objects.filter(album=album).update(is_cover=False)
    media.is_cover = True
    media.save(update_fields=["is_cover"])
    return album