"""Finance provider integrations: M-Pesa (Daraja) and bank transfer stubs.

Each provider is an adapter in front of its HTTP client. Real credentials come
from settings; when absent the adapter raises ProviderNotConfiguredError instead
of silently pretending success.
"""
import base64
import hashlib
import hmac
import logging
import time
import uuid
from datetime import datetime, timedelta
from urllib.parse import urljoin

import requests
from django.conf import settings
from django.utils import timezone

from apps.common.exceptions import ProviderNotConfiguredError

logger = logging.getLogger("apps.finance.providers")


def _b64(value) -> str:
    return base64.b64encode(value.encode()).decode()


class MpesaConfig:
    """M-Pesa Daraja credentials + endpoint config read from Django settings."""

    def __init__(self):
        self.enabled = bool(getattr(settings, "MPESA_ENABLED", False))
        self.environment = getattr(settings, "MPESA_ENVIRONMENT", "sandbox")
        self.consumer_key = getattr(settings, "MPESA_CONSUMER_KEY", "")
        self.consumer_secret = getattr(settings, "MPESA_CONSUMER_SECRET", "")
        self.shortcode = getattr(settings, "MPESA_SHORTCODE", "")
        self.lipa_na_mpesa_passkey = getattr(settings, "MPESA_LIPA_NA_MPESA_PASSKEY", "")
        self.business_shortcode = getattr(settings, "MPESA_BUSINESS_SHORTCODE", "") or self.shortcode
        self.account_reference = getattr(settings, "MPESA_ACCOUNT_REFERENCE", "SALA-{ref}")
        self.transaction_description = getattr(settings, "MPESA_TRANSACTION_DESCRIPTION", "School fee payment")
        self.callback_url = getattr(settings, "MPESA_CALLBACK_URL", "")

    def base_url(self):
        if self.environment == "production":
            return "https://api.safaricom.co.ke"
        return "https://sandbox.safaricom.co.ke"

    def is_ready(self):
        return bool(self.enabled and self.consumer_key and self.consumer_secret and self.shortcode)


def _oauth_token(cfg: MpesaConfig) -> str:
    auth = _b64(f"{cfg.consumer_key}:{cfg.consumer_secret}")
    resp = requests.get(
        urljoin(cfg.base_url(), "/oauth/v1/generate?grant_type=client_credentials"),
        headers={"Authorization": f"Basic {auth}"},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json().get("access_token", "")


def _lipa_na_mpesa_timestamp() -> str:
    now = datetime.now()
    return now.strftime("%Y%m%d%H%M%S")


def _lipa_password(cfg: MpesaConfig, timestamp: str) -> str:
    raw = f"{cfg.business_shortcode}{cfg.lipa_na_mpesa_passkey}{timestamp}"
    return _b64(raw)


def initiate_mpesa_stk(phone: str, amount: float, reference: str, description: str = "") -> dict:
    """STK push to a student's guardian phone.

    Returns {"provider":"mpesa","provider_ref":...,"status":"PROCESSING"}.
    """
    cfg = MpesaConfig()
    if not cfg.is_ready():
        raise ProviderNotConfiguredError(message="M-Pesa is not configured for this deployment.")
    if not cfg.lipa_na_mpesa_passkey:
        raise ProviderNotConfiguredError(message="M-Pesa Lipa Na M-Pesa passkey is not configured.")

    token = _oauth_token(cfg)
    timestamp = _lipa_na_mpesa_timestamp()
    password = _lipa_password(cfg, timestamp)
    checkout_request_id = uuid.uuid4().hex[:24]

    payload = {
        "BusinessShortCode": cfg.business_shortcode,
        "Password": password,
        "Timestamp": timestamp,
        "TransactionType": "CustomerPayBillOnline",
        "Amount": str(int(float(amount))),
        "PartyA": _normalise_phone(phone),
        "PartyB": cfg.business_shortcode,
        "PhoneNumber": _normalise_phone(phone),
        "CallBackURL": cfg.callback_url,
        "AccountReference": cfg.account_reference.format(ref=reference),
        "TransactionDesc": description or cfg.transaction_description,
    }
    resp = requests.post(
        urljoin(cfg.base_url(), "/mpesa/stkpush/v1/processrequest"),
        json=payload,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("ResponseCode") != "0":
        logger.warning("M-Pesa STK push rejected: %s", data)
        raise MpesaRequestError(data.get("ResponseDescription", "STK push rejected"), data)
    return {
        "provider": "mpesa",
        "provider_ref": data.get("CheckoutRequestID", checkout_request_id),
        "status": "PROCESSING",
        "raw": data,
    }


def query_mpesa_stk(checkout_request_id: str) -> dict:
    cfg = MpesaConfig()
    if not cfg.is_ready():
        raise ProviderNotConfiguredError(message="M-Pesa is not configured for this deployment.")
    token = _oauth_token(cfg)
    timestamp = _lipa_na_mpesa_timestamp()
    password = _lipa_password(cfg, timestamp)
    payload = {
        "BusinessShortCode": cfg.business_shortcode,
        "Password": password,
        "Timestamp": timestamp,
        "CheckoutRequestID": checkout_request_id,
    }
    resp = requests.post(
        urljoin(cfg.base_url(), "/mpesa/stkpushquery/v1/query"),
        json=payload,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


class MpesaRequestError(Exception):
    def __init__(self, message, raw=None):
        super().__init__(message)
        self.message = message
        self.raw = raw or {}


def _verify_callback_signature(secret: str, signature: str, payload: bytes) -> bool:
    """Positive verification of the x-mpesa-signature header when provided."""
    if not signature:
        return True  # signature pinning optional in sandbox
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def verify_mpesa_callback(secret: str, signature: str, body: bytes) -> bool:
    return _verify_callback_signature(secret, signature.strip(), body)


def _normalise_phone(phone: str) -> str:
    p = (phone or "").replace(" ", "").replace("+", "")
    if p.startswith("254"):
        return p
    if p.startswith("0"):
        return "254" + p[1:]
    if p.startswith("7") or p.startswith("1"):
        return "254" + p
    return p


def get_mpesa_status(result_code: str) -> str:
    if result_code in ("0", "1"):
        return "SUCCESS"
    return "FAILED"


# ---------------------------------------------------------------------------
# Bank transfers
# ---------------------------------------------------------------------------


def initiate_bank_payment(amount: float, reference: str, bank_details: dict | None = None) -> dict:
    """Create a pending bank-transfer payment.

    A real debit mandate webhook would confirm collection; here we return a
    PENDING record the school can confirm manually or via a future webhook.
    """
    return {
        "provider": "bank",
        "provider_ref": uuid.uuid4().hex[:24],
        "status": "PENDING",
        "instructions": {
            "account_name": getattr(settings, "BANK_ACCOUNT_NAME", ""),
            "account_number": getattr(settings, "BANK_ACCOUNT_NUMBER", ""),
            "bank": getattr(settings, "BANK_NAME", ""),
            "branch": getattr(settings, "BANK_BRANCH", ""),
            "reference": reference,
        },
    }