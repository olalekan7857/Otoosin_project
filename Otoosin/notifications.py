"""Post-commit notification extension points."""

import logging

from .email_service import send_email
from .models import EmailDelivery, OrderNotificationRecipient
from .transactional_emails import order_notification_email

logger = logging.getLogger(__name__)


def _masked_email(email):
    local, separator, domain = str(email or "").partition("@")
    if not separator:
        return "***"
    return f"{local[:1]}***@{domain}"


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
    try:
        _notify_order_email(order)
    except Exception:
        # A notification provider must never turn a committed payment into a
        # failed checkout response.
        logger.exception(
            "Unexpected paid-order email failure for order %s.",
            order.reference,
        )


def order_status_changed(order, old_status, new_status, actor=None):
    logger.info(
        "Order %s status changed from %s to %s.",
        order.reference,
        old_status,
        new_status,
    )
