import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

from config.celery import app as celery_app  # noqa: E402

__all__ = ("celery_app",)