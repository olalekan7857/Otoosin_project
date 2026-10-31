"""Post-commit notification extension points."""

import logging

from django.conf import settings

from . import whatsapp
from .email_service import send_email
from .models import EmailDelivery, OrderNotificationRecipient
from .transactional_emails import order_notification_email

logger = logging.getLogger(__name__)


def _masked_email(email):
    local, separator, domain = str(email or "").partition("@")
    if not separator:
        return "***"
    return f"{local[:1]}***@{domain}"


def _notify_order_whatsapp(order):
    """Preserved WhatsApp hook, deliberately gated off by default."""
    if not (
        getattr(settings, "WHATSAPP_ORDER_NOTIFICATIONS_ENABLED", False)
        and getattr(settings, "WHATSAPP_ENABLED", False)
    ):
        return
    try:
        result = whatsapp.send_order_notification(order)
    except Exception:
        logger.exception(
            "Unexpected WhatsApp notification failure for order %s.",
            order.reference,
        )
        return
    if result.accepted:
        logger.info(
            "WhatsApp notification accepted by Meta for order %s "
            "(wamid %s); delivery receipt is not implemented.",
            order.reference,
            result.message_id or "not returned",
        )
    elif result.category == "disabled":
        logger.info(
            "WhatsApp notifications are disabled; order %s was not sent.",
            order.reference,
        )
    else:
        logger.warning(
            "WhatsApp notification was not accepted for order %s "
            "(category %s, HTTP %s): %s",
            order.reference,
            result.category,
            result.status_code,
            result.message,
        )


def _notify_order_email(order):
    recipients = list(
        OrderNotificationRecipient.objects.filter(is_active=True)
        .order_by("email")
        .values_list("email", flat=True)
    )
    if not recipients:
        logger.warning(
            "No active order notification email recipients; "
            "skipped paid-order email for order %s.",
            order.reference,
        )
        return []
    try:
        message = order_notification_email(order)
    except Exception:
        logger.exception(
            "Could not build paid-order email for order %s.",
            order.reference,
        )
        return []

    results = []
    for recipient in recipients:
        try:
            delivery = send_email(
                category=EmailDelivery.Category.ORDER_NOTIFICATION,
                recipient=recipient,
                subject=message["subject"],
                text=message["text"],
                html=message["html"],
            )
        except Exception:
            logger.exception(
                "Paid-order email for order %s failed for recipient %s.",
                order.reference,
                _masked_email(recipient),
            )
            results.append(None)
            continue
        if delivery.status == EmailDelivery.Status.SENT:
            logger.info(
                "Paid-order email for order %s was accepted by Resend "
                "for recipient %s (delivery not confirmed).",
                order.reference,
                _masked_email(recipient),
            )
        else:
            logger.warning(
                "Paid-order email for order %s failed for recipient %s: %s",
                order.reference,
                _masked_email(recipient),
                delivery.last_error or "unknown provider error",
            )
        results.append(delivery)
    return results


def payment_verified(order, payment):
    """Notify staff once after a payment transitions to verified paid."""
    logger.info(
        "Payment verified for order %s (reference %s).",
        order.reference,
        payment.provider_reference,
    )
    # Email is the active administrative notification channel. WhatsApp is
    # preserved but gated off by default and is never required by email.
    try:
        _notify_order_email(order)
    except Exception:
        # A secondary provider must never turn a committed payment into a
        # failed checkout response.
        logger.exception(
            "Unexpected paid-order email failure for order %s.",
            order.reference,
        )
    _notify_order_whatsapp(order)


def order_status_changed(order, old_status, new_status, actor=None):
    logger.info(
        "Order %s status changed from %s to %s.",
        order.reference,
        old_status,
        new_status,
    )
