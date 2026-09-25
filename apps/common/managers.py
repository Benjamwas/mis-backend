from django.db import models


class SoftDeleteQuerySet(models.QuerySet):
    def delete(self):
        from django.utils import timezone

        now = timezone.now()
        return super().update(is_deleted=True, deleted_at=now)

    def hard_delete(self):
        return super().delete()

    def alive(self):
        return self.filter(is_deleted=False)

    def dead(self):
        return self.filter(is_deleted=True)


class SoftDeleteManager(models.Manager):
    def get_queryset(self):
        return SoftDeleteQuerySet(self.model, using=self._db).alive()


class ActiveManager(models.Manager):
    def get_queryset(self):
        return SoftDeleteQuerySet(self.model, using=self._db).alive().filter(is_active=True)