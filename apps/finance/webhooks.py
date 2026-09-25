"""Finance webhooks: M-Pesa callback, idempotent confirmation."""
import logging
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from apps.audit.services import audit_event
from apps.finance.models import Payment
from apps.finance.providers import verify_mpesa_callback

logger = logging.getLogger("apps.finance.webhooks")


def _dec(value):
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0.00")


def _extract_mpesa_payload(body):
    """Parse the Daraja STK callback envelope into a flat dict."""
    if not isinstance(body, dict):
        return {}
    stk = body.get("Body", {}).get("stkCallback", {})
    result = stk.get("ResultCode")
    checkout = stk.get("CheckoutRequestID", "")
    meta = {item.get("Name"): item.get("Value") for item in stk.get("CallbackMetadata", {}).get("Item", [])}
    return {
        "result_code": result,
        "result_desc": stk.get("ResultDesc", ""),
        "checkout_request_id": checkout,
        "amount": meta.get("Amount"),
        "mpesa_receipt": meta.get("MpesaReceiptNumber"),
        "phone": meta.get("PhoneNumber"),
        "transaction_date": meta.get("TransactionDate"),
    }


@csrf_exempt
def mpesa_callback(request):
    """Daraja STK callback endpoint.

    Idempotent: a given CheckoutRequestID is confirmed only once.
    """
    body = request.body or b""
    try:
        payload = request.POST.dict()
    except Exception:
        payload = {}

    try:
        import json

        parsed = json.loads(body) if body else payload
    except Exception:
        parsed = payload

    data = _extract_mpesa_payload(parsed)

    payment = Payment.objects.filter(metadata__checkout_request_id=data["checkout_request_id"]).first()
    if not payment:
        # Unknown STK reference the school may have surfaced externally.
        logger.warning("M-Pesa callback for unknown checkout id %s", data.get("checkout_request_id"))
        return JsonResponse({"ResultCode": 1, "ResultDesc": "Unknown checkout request"})

    if payment.status == Payment.Status.SUCCESS:
        # Idempotent; re-issuing the acknowledgement is harmless.
        return JsonResponse({"ResultCode": 0, "ResultDesc": "Already confirmed"})

    with transaction.atomic():
        if str(data.get("result_code")) in ("0", "1"):
            amount = _dec(data.get("amount")) or payment.amount
            payment.status = Payment.Status.SUCCESS
            payment.amount = amount
            payment.provider_ref = data.get("mpesa_receipt") or payment.provider_ref
            payment.paid_at = timezone.now()
            payment.metadata["mpesa_receipt"] = data.get("mpesa_receipt") or ""
            payment.metadata["callback_at"] = timezone.now().isoformat()
            payment.save(update_fields=["amount", "status", "provider_ref", "paid_at", "metadata", "updated_at"])

            from apps.finance.services import allocate_payment, issue_receipt

            try:
                allocate_payment(payment, [{"invoice_id": inv.id, "amount": amount} for inv in payment.student.invoices.filter(school=payment.school, status__in=["SENT", "PARTIALLY_PAID"])], by=None)
            except Exception as exc:
                # On allocation failure third-party bank records still sit pending;
                # surface for a reconciliation queue rather than returning success.
                logger.error("MPESA allocation error for %s: %s", payment.transaction_ref, exc)

            receipt = issue_receipt(school=payment.school, payment=payment)
            payment.metadata["receipt"] = str(receipt.receipt_number)
            payment.save(update_fields=["metadata", "updated_at"])

            from apps.communication.tasks import notify_users
            from apps.people.services import student_guardian_users

            recipients = [u.id for u in student_guardian_users(payment.student)]
            if recipients:
                notify_users.delay(
                    recipients,
                    title="Payment Received",
                    body=f"Payment of KES {amount} received. Receipt {receipt.receipt_number} is available.",
                    entity_type="Payment", entity_id=payment.id, school_id=payment.school_id,
                )

            audit_event(
                None, "payment.confirm", "finance", "Payment", payment.id,
                old_value={"status": "PROCESSING"}, new_value={"status": "SUCCESS", "amount": str(amount)},
                school=payment.school,
            )
        else:
            payment.status = Payment.Status.FAILED
            payment.metadata["result_desc"] = data.get("result_desc", "")
            payment.metadata["callback_at"] = timezone.now().isoformat()
            payment.save(update_fields=["status", "metadata", "updated_at"])
            audit_event(
                None, "payment.failed", "finance", "Payment", payment.id,
                old_value={"status": "PROCESSING"}, new_value={"status": "FAILED"}, school=payment.school,
            )

    return JsonResponse({"ResultCode": 0, "ResultDesc": "Success"})


@csrf_exempt
def bank_webhook(request):
    """Minimal bank-transfer webhook placeholder honoring the SALA envelope.

    Accepts a POST with {transaction_ref, status, amount} and flips a pending
    Payment when it matches. Idempotent per payment.
    """
    try:
        import json

        parsed = json.loads(request.body or b"{}")
    except Exception:
        parsed = request.POST.dict()

    ref = parsed.get("transaction_ref") or parsed.get("reference")
    status = parsed.get("status", "SUCCESS").upper()
    if not ref:
        return JsonResponse({"success": False, "data": None, "error": {"code": "BAD_REQUEST", "message": "Missing transaction_ref"}}, status=400)

    payment = Payment.objects.filter(transaction_ref=ref).first()
    if not payment:
        return JsonResponse({"success": False, "data": None, "error": {"code": "NOT_FOUND", "message": "Payment not found"}}, status=404)

    if payment.status in (Payment.Status.SUCCESS, Payment.Status.FAILED):
        return JsonResponse({"success": True, "data": {"status": payment.status}})

    from apps.finance.services import allocate_payment, issue_receipt

    with transaction.atomic():
        if status == "SUCCESS":
            payment.status = Payment.Status.SUCCESS
            payment.paid_at = timezone.now()
            payment.save(update_fields=["status", "paid_at", "updated_at"])
            try:
                allocate_payment(payment, [{"invoice_id": inv.id, "amount": payment.amount} for inv in payment.student.invoices.filter(school=payment.school, status__in=["SENT", "PARTIALLY_PAID"])])
            except Exception as exc:
                logger.error("Bank webhook allocation error for %s: %s", ref, exc)
            issue_receipt(school=payment.school, payment=payment)
        else:
            payment.status = Payment.Status.FAILED
            payment.save(update_fields=["status", "updated_at"])

    return JsonResponse({"success": True, "data": {"status": payment.status}})