"""Provider abstractions: SMS, WhatsApp, Email.

Business code never depends on a concrete vendor. The provider is selected from
settings (SMS_PROVIDER / WHATSAPP_PROVIDER / EMAIL_BACKEND). When credentials are
missing, the architecture, retries, logging and persistence still work — the
provider call fails loudly with a `ProviderNotConfiguredError` and the delivery
status is recorded as FAILED so it can be retried once credentials exist.
"""
import logging

import requests
from django.conf import settings

from apps.common.exceptions import ProviderNotConfiguredError

logger = logging.getLogger("apps.communication")


class SMSProvider:
    """Interface for SMS vendors."""

    name = "base"

    def send(self, to: str, body: str) -> dict:
        raise NotImplementedError


class TwilioSMSProvider(SMSProvider):
    name = "twilio"

    def __init__(self, sid=None, token=None, from_number=None):
        self.sid = sid or settings.TWILIO_ACCOUNT_SID
        self.token = token or settings.TWILIO_AUTH_TOKEN
        self.from_number = from_number or settings.TWILIO_FROM_NUMBER

    @property
    def configured(self):
        return bool(self.sid and self.token and self.from_number)

    def send(self, to: str, body: str) -> dict:
        if not self.configured:
            raise ProviderNotConfiguredError("Twilio SMS credentials are not configured.", code="SMS_NOT_CONFIGURED")
        url = f"https://api.twilio.com/2010-04-01/Accounts/{self.sid}/Messages.json"
        resp = requests.post(
            url,
            auth=(self.sid, self.token),
            data={"To": to, "From": self.from_number, "Body": body},
            timeout=30,
        )
        if resp.status_code >= 400:
            logger.error("twilio send failed: %s %s", resp.status_code, resp.text[:300])
            return {"ok": False, "status_code": resp.status_code, "raw": resp.text[:500]}
        data = resp.json()
        return {"ok": True, "provider_message_id": data.get("sid"), "raw": data}


class GenericHTTPSMSProvider(SMSProvider):
    """Generic HTTP SMS gateway configured via SMS_PROVIDER_URL + API key."""

    name = "generic"

    @property
    def configured(self):
        return bool(settings.SMS_PROVIDER_URL and settings.SMS_PROVIDER_API_KEY)

    def send(self, to: str, body: str) -> dict:
        if not self.configured:
            raise ProviderNotConfiguredError("Generic SMS provider not configured.", code="SMS_NOT_CONFIGURED")
        headers = {"Authorization": f"Bearer {settings.SMS_PROVIDER_API_KEY}"}
        payload = {"to": to, "message": body, "sender_id": settings.SMS_PROVIDER_SENDER_ID}
        resp = requests.post(settings.SMS_PROVIDER_URL, json=payload, headers=headers, timeout=30)
        if resp.status_code >= 400:
            return {"ok": False, "status_code": resp.status_code, "raw": resp.text[:500]}
        return {"ok": True, "raw": resp.json() if resp.headers.get("content-type", "").startswith("application/json") else resp.text}


def get_sms_provider() -> SMSProvider:
    provider = (settings.SMS_PROVIDER or "").lower()
    if provider == "twilio":
        return TwilioSMSProvider()
    if provider == "generic":
        return GenericHTTPSMSProvider()
    raise ProviderNotConfiguredError("No SMS provider configured.", code="SMS_NOT_CONFIGURED")


class WhatsAppProvider:
    """Interface for WhatsApp vendors (template-based)."""

    name = "base"

    def send(self, to: str, template_code: str, variables: dict | None = None, body: str = "") -> dict:
        raise NotImplementedError


class TwilioWhatsAppProvider(WhatsAppProvider):
    name = "twilio"

    @property
    def configured(self):
        return bool(settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN)

    def send(self, to: str, template_code: str, variables: dict | None = None, body: str = "") -> dict:
        if not self.configured:
            raise ProviderNotConfiguredError("Twilio WhatsApp credentials are not configured.", code="WHATSAPP_NOT_CONFIGURED")
        url = f"https://api.twilio.com/2010-04-01/Accounts/{settings.TWILIO_ACCOUNT_SID}/Messages.json"
        from_number = f"whatsapp:{settings.WHATSAPP_FROM_NUMBER}"
        to_number = to if to.startswith("whatsapp:") else f"whatsapp:{to}"
        payload = {"To": to_number, "From": from_number, "Body": body}
        resp = requests.post(url, auth=(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN), data=payload, timeout=30)
        if resp.status_code >= 400:
            return {"ok": False, "status_code": resp.status_code, "raw": resp.text[:500]}
        return {"ok": True, "provider_message_id": resp.json().get("sid"), "raw": resp.json()}


def get_whatsapp_provider() -> WhatsAppProvider:
    provider = (settings.WHATSAPP_PROVIDER or "").lower()
    if provider == "twilio":
        return TwilioWhatsAppProvider()
    raise ProviderNotConfiguredError("No WhatsApp provider configured.", code="WHATSAPP_NOT_CONFIGURED")


class EmailService:
    """Django email wrapper that records a DeliveryLog."""

    @staticmethod
    def send(to: str, subject: str, body: str, html: str = "", from_email: str | None = None, fail_silently: bool = False) -> dict:
        from django.core.mail import EmailMessage, EmailMultiAlternatives

        msg = EmailMultiAlternatives(subject, body, from_email or settings.DEFAULT_FROM_EMAIL, [to])
        if html:
            msg.attach_alternative(html, "text/html")
        try:
            sent = msg.send(fail_silently=fail_silently)
            return {"ok": bool(sent)}
        except Exception as exc:  # noqa: BLE001
            logger.error("email send failed: %s", exc)
            return {"ok": False, "error": str(exc)}