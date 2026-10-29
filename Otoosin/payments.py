"""Shared, idempotent Paystack payment processing.

Both the browser return and the webhook converge here. A payment becomes paid
only after a server-to-server Paystack verification with matching reference,
amount, currency and order association.
"""

import hashlib
import json
import logging
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.utils import timezone

from . import notifications, paystack
from .audit import record_audit
from .models import Order, Payment, PaymentWebhookEvent

logger = logging.getLogger(__name__)

KOBO = Decimal("100")


class PaymentProcessingError(Exception):
    def __init__(self, message, *, retryable=False):
        super().__init__(message)
        self.message = message
        self.retryable = retryable


def _kobo(amount):
    return int((Decimal(amount) * KOBO).to_integral_value())


def _safe_status(data):
    return str((data or {}).get("status") or "").strip().lower()


def _validate_success(payment, data):
    if _safe_status(data) != "success":
        return False, "The provider has not confirmed this payment as successful."
    if str(data.get("reference") or "") != payment.provider_reference:
        return False, "The provider reference does not match this payment."
    try:
        provider_amount = int(data.get("amount"))
    except (TypeError, ValueError):
        return False, "The provider amount is invalid."
    if provider_amount != _kobo(payment.amount):
        return False, "The verified amount does not match the order total."
    if provider_amount != _kobo(payment.order.total):
        return False, "The verified amount does not match the order total."
    if str(data.get("currency") or "").upper() != "NGN":
        return False, "The verified currency is not supported."
    return True, ""


def _event_matches(payment, data):
    """Check reference, amount, currency and order association for an event."""
    if str(data.get("reference") or "") != payment.provider_reference:
        return False, "The provider reference does not match this payment."
    try:
        provider_amount = int(data.get("amount"))
    except (TypeError, ValueError):
        return False, "The provider amount is invalid."
    if provider_amount != _kobo(payment.amount):
        return False, "The provider amount does not match this payment."
    if provider_amount != _kobo(payment.order.total):
        return False, "The provider amount does not match the order total."
    if str(data.get("currency") or "").upper() != "NGN":
        return False, "The verified currency is not supported."
    return True, ""


def _mark_conflict(payment, data, message):
    payment.failure_category = "possible_duplicate_charge"
    payment.failure_message = message[:300]
    payment.last_checked_at = timezone.now()
    payment.gateway_response = paystack.sanitize_payment_data(data)
    payment.save(
        update_fields=[
            "failure_category",
            "failure_message",
            "last_checked_at",
            "gateway_response",
            "updated_at",
        ]
    )
    record_audit(
        action="payment.duplicate_charge_detected",
        target=payment.order,
        summary=f"{payment.provider_reference}: {message}",
    )


def _record_failure(payment, category, message):
    payment.failure_category = category[:60]
    payment.failure_message = message[:300]
    payment.last_checked_at = timezone.now()
    payment.save(
        update_fields=[
            "failure_category",
            "failure_message",
            "last_checked_at",
            "updated_at",
        ]
    )
    record_audit(
        action="payment.verification_failed",
        target=payment.order,
        summary=f"{payment.provider_reference}: {category}",
    )


def apply_success(payment, data):
    """Apply a verified success once. Returns (changed, conflict).

    A database-level partial unique constraint guarantees that only one
    payment per order can ever hold the paid status, even if two requests
    race on SQLite where select_for_update() is not a real row lock.
    """
    changed = False
    conflict = False
    with transaction.atomic():
        locked = Payment.objects.select_for_update().get(pk=payment.pk)
        if locked.status == Payment.Status.PAID and locked.verified_at:
            return False, False
        competing = (
            Payment.objects.select_for_update()
            .filter(order_id=locked.order_id, status=Payment.Status.PAID)
            .exclude(pk=locked.pk)
            .first()
        )
        if competing is not None:
            conflict = True
            _mark_conflict(
                locked,
                data,
                "Another payment attempt for this order is already verified.",
            )
            return False, True

        locked.status = Payment.Status.PAID
        locked.verified_at = timezone.now()
        locked.last_checked_at = locked.verified_at
        locked.failure_category = ""
        locked.failure_message = ""
        locked.gateway_response = paystack.sanitize_payment_data(data)
        try:
            with transaction.atomic():
                locked.save(
                    update_fields=[
                        "status",
                        "verified_at",
                        "last_checked_at",
                        "failure_category",
                        "failure_message",
                        "gateway_response",
                        "updated_at",
                    ]
                )
        except IntegrityError:
            # Lost a race against another successful attempt; the inner
            # savepoint is rolled back and the outer transaction remains valid.
            Payment.objects.filter(pk=payment.pk).update(
                failure_category="possible_duplicate_charge",
                failure_message=(
                    "Another payment attempt for this order is already verified."
                ),
                last_checked_at=timezone.now(),
                gateway_response=paystack.sanitize_payment_data(data),
                updated_at=timezone.now(),
            )
            record_audit(
                action="payment.duplicate_charge_detected",
                target=locked.order,
                summary=(
                    f"{locked.provider_reference} lost a paid-payment race "
                    "to another verified attempt."
                ),
            )
            return False, True

        record_audit(
            action="payment.verified_paid",
            target=locked.order,
            summary=f"{locked.provider_reference} verified by the provider.",
        )
        changed = True
        transaction.on_commit(
            lambda order=locked.order, attempt=locked: notifications.payment_verified(
                order, attempt
            )
        )
    return changed, conflict


def apply_provider_status(payment, data):
    """Apply a non-success provider state without ever downgrading paid."""
    status = _safe_status(data)
    if payment.status == Payment.Status.PAID:
        return False
    mapping = {
        "failed": Payment.Status.FAILED,
        "abandoned": Payment.Status.ABANDONED,
        "reversed": Payment.Status.REFUNDED,
    }
    new_status = mapping.get(status, Payment.Status.PENDING)
    if payment.status == Payment.Status.REFUNDED:
        return False
    payment.status = new_status
    payment.last_checked_at = timezone.now()
    payment.gateway_response = paystack.sanitize_payment_data(data)
    if status in {"failed", "abandoned"}:
        payment.failure_category = status
        payment.failure_message = str(
            data.get("gateway_response") or f"Provider status: {status}"
        )[:300]
    payment.save(
        update_fields=[
            "status",
            "last_checked_at",
            "gateway_response",
            "failure_category",
            "failure_message",
            "updated_at",
        ]
    )
    return True


def verify_payment(payment, *, provider_data=None):
    """Verify one attempt with Paystack and apply the verified state."""
    if payment.status == Payment.Status.PAID and payment.verified_at:
        return {"status": "paid", "changed": False, "conflict": False}

    try:
        data = provider_data or paystack.verify_transaction(
            payment.provider_reference
        )
    except paystack.PaystackError as exc:
        payment.last_checked_at = timezone.now()
        payment.failure_category = exc.category[:60]
        payment.failure_message = str(exc)[:300]
        payment.save(
            update_fields=[
                "last_checked_at",
                "failure_category",
                "failure_message",
                "updated_at",
            ]
        )
        return {
            "status": payment.status,
            "changed": False,
            "conflict": False,
            "error": exc.category,
            "retryable": exc.retryable,
        }

    if _validate_success(payment, data)[0]:
        changed, conflict = apply_success(payment, data)
        payment.refresh_from_db()
        return {
            "status": payment.status,
            "changed": changed,
            "conflict": conflict,
        }

    valid = _validate_success(payment, data)
    if _safe_status(data) == "success" and not valid[0]:
        _record_failure(payment, "verification_mismatch", valid[1])
        payment.refresh_from_db()
        return {
            "status": payment.status,
            "changed": False,
            "conflict": False,
            "error": "verification_mismatch",
        }

    if _safe_status(data) != "success":
        matched, reason = _event_matches(payment, data)
        if not matched:
            _record_failure(payment, "verification_mismatch", reason)
            payment.refresh_from_db()
            return {
                "status": payment.status,
                "changed": False,
                "conflict": False,
                "error": "verification_mismatch",
            }

    changed = apply_provider_status(payment, data)
    payment.refresh_from_db()
    return {
        "status": payment.status,
        "changed": changed,
        "conflict": False,
        "error": "" if changed else "pending",
    }


def _event_identity(event_type, data):
    transaction_id = data.get("id") if isinstance(data, dict) else None
    reference = data.get("reference") if isinstance(data, dict) else None
    if transaction_id not in (None, ""):
        return f"{event_type}:{transaction_id}"
    if reference:
        return f"{event_type}:{reference}"
    return hashlib.sha256(
        json.dumps(data or {}, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


def process_webhook(raw_body, signature):
    """Validate and process a Paystack webhook. Returns a result dict."""
    if not paystack.valid_webhook_signature(raw_body, signature):
        return {"ok": False, "status": 401, "error": "invalid_signature"}

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {"ok": False, "status": 400, "error": "invalid_payload"}
    if not isinstance(payload, dict):
        return {"ok": False, "status": 400, "error": "invalid_payload"}

    event_type = str(payload.get("event") or "")[:80]
    data = payload.get("data")
    if not isinstance(data, dict):
        data = {}
    event_id = _event_identity(event_type, data)[:120]
    summary = paystack.sanitize_payment_data(data)

    try:
        event, created = PaymentWebhookEvent.objects.get_or_create(
            provider="paystack",
            event_id=event_id,
            defaults={
                "event_type": event_type,
                "payload_summary": summary,
                "signature_valid": True,
            },
        )
    except IntegrityError:
        event = PaymentWebhookEvent.objects.filter(
            provider="paystack", event_id=event_id
        ).first()
        created = False
    if event is None:
        return {"ok": False, "status": 500, "error": "event_storage"}
    if not created and event.processing_status in {
        PaymentWebhookEvent.ProcessingStatus.PROCESSED,
        PaymentWebhookEvent.ProcessingStatus.IGNORED,
    }:
        return {"ok": True, "status": 200, "duplicate": True}

    reference = str(data.get("reference") or "").strip()
    if event_type not in {"charge.success", "charge.failed"}:
        event.processing_status = PaymentWebhookEvent.ProcessingStatus.IGNORED
        event.processed_at = timezone.now()
        event.save(
            update_fields=["processing_status", "processed_at"]
        )
        return {"ok": True, "status": 200, "ignored": True}

    payment = Payment.objects.filter(provider_reference=reference).first()
    if payment is None:
        event.processing_status = PaymentWebhookEvent.ProcessingStatus.IGNORED
        event.processing_error = "unknown_reference"
        event.processed_at = timezone.now()
        event.save(
            update_fields=[
                "processing_status",
                "processing_error",
                "processed_at",
            ]
        )
        return {"ok": True, "status": 200, "ignored": True}

    try:
        if event_type == "charge.success":
            # Never trust the webhook JSON as proof; verify server-to-server.
            result = verify_payment(payment)
            if result.get("error") in {"timeout", "network"}:
                event.processing_status = PaymentWebhookEvent.ProcessingStatus.FAILED
                event.processing_error = result.get("error", "")[:300]
                event.processed_at = timezone.now()
                event.save(
                    update_fields=[
                        "processing_status",
                        "processing_error",
                        "processed_at",
                    ]
                )
                return {"ok": False, "status": 503, "error": "transient"}
        else:
            matched, reason = _event_matches(payment, data)
            if not matched:
                event.processing_status = (
                    PaymentWebhookEvent.ProcessingStatus.FAILED
                )
                event.processing_error = "verification_mismatch"
                event.processed_at = timezone.now()
                event.save(
                    update_fields=[
                        "processing_status",
                        "processing_error",
                        "processed_at",
                    ]
                )
                _record_failure(payment, "webhook_mismatch", reason)
                return {"ok": True, "status": 200, "ignored": True}
            apply_provider_status(payment, data)
    except Exception:
        logger.exception("Webhook processing failed for event %s", event_id)
        event.processing_status = PaymentWebhookEvent.ProcessingStatus.FAILED
        event.processing_error = "processing_error"
        event.processed_at = timezone.now()
        event.save(
            update_fields=["processing_status", "processing_error", "processed_at"]
        )
        return {"ok": False, "status": 500, "error": "processing_error"}

    event.processing_status = PaymentWebhookEvent.ProcessingStatus.PROCESSED
    event.processed_at = timezone.now()
    event.payload_summary = summary
    event.save(
        update_fields=[
            "processing_status",
            "processed_at",
            "payload_summary",
        ]
    )
    return {"ok": True, "status": 200}
