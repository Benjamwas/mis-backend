"""Storage backend for files. Supports local disk and Supabase Storage.

The Supabase backend talks to the Storage API of SUPABASE_URL using the
service-role key. This key is backend-only and never exposed to the frontend.
"""
import logging
import os
from urllib.parse import urljoin

import requests
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.files.storage import FileSystemStorage

logger = logging.getLogger("apps.files")


class SupabaseStorage(FileSystemStorage):
    """Minimal Supabase Storage adapter.

    If SUPABASE_* env vars are missing the driver falls back to local disk with a
    warning, so development never breaks while production wiring stays explicit.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bucket = getattr(settings, "SUPABASE_STORAGE_BUCKET", "sala-files")
        self.endpoint = getattr(settings, "SUPABASE_URL", "").rstrip("/")
        self.service_key = getattr(settings, "SUPABASE_SERVICE_ROLE_KEY", "")

    @property
    def configured(self):
        return bool(self.endpoint and self.service_key)

    def _headers(self):
        return {"apikey": self.service_key, "Authorization": f"Bearer {self.service_key}"}

    def _base_url(self):
        return f"{self.endpoint}/storage/v1/object/{self.bucket}"

    def _save_file(self, name, content):
        url = f"{self._base_url()}/{name}"
        resp = requests.post(url, headers=self._headers(), data=content, timeout=30)
        if resp.status_code not in (200, 201):
            logger.error("supabase upload failed: %s %s", resp.status_code, resp.text[:400])
            raise OSError(f"Supabase upload failed: {resp.status_code}")

    def _delete_file(self, name):
        url = f"{self._base_url()}/{name}"
        resp = requests.delete(url, headers=self._headers(), timeout=30)
        if resp.status_code >= 400 and resp.status_code != 404:
            logger.error("supabase delete failed: %s %s", resp.status_code, resp.text[:400])

    def _read_file(self, name):
        url = f"{self._base_url()}/public/{name}"
        resp = requests.get(url, headers=self._headers(), timeout=30)
        if resp.status_code != 200:
            raise FileNotFoundError(name)
        return resp.content


def upload_to_storage(uploaded_file, folder="uploads", category="OTHER"):
    """Persist a file via the configured driver and return stored path."""
    backend = _get_backend()
    ext = os.path.splitext(uploaded_file.name)[1]
    name = f"{folder}/{category.lower()}/{uuid_text()}{ext}"
    content = uploaded_file.read()
    try:
        if isinstance(backend, SupabaseStorage) and backend.configured:
            long_name = f"{settings.SUPABASE_STORAGE_BUCKET}_stored"
            backend._save_file(name, content)
            return name
    except Exception as exc:  # noqa: BLE001
        logger.exception("storage upload error")
        raise OSError(f"Failed to store file: {exc}") from exc

    return _save_local(backend, name, content)


def uuid_text():
    import uuid

    return str(uuid.uuid4())


def _get_backend():
    from django.core.files.storage import default_storage

    return default_storage


def _save_local(backend, name, content):
    path = backend.path(name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(content)
    return name


def public_url(stored_path: str) -> str:
    backend = _get_backend()
    if isinstance(backend, SupabaseStorage) and backend.configured:
        return f"{backend._base_url()}/public/{stored_path}"
    if settings.MEDIA_URL:
        return urljoin(settings.MEDIA_URL, stored_path)
    return stored_path