"""Finance webhook endpoints (public, CSRF-exempt, signature-verified where possible)."""
from django.urls import path

from apps.finance.webhooks import bank_webhook, mpesa_callback

urlpatterns = [
    path("mpesa/", mpesa_callback, name="webhook-mpesa"),
    path("bank/", bank_webhook, name="webhook-bank"),
]