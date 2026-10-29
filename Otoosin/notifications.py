"""Post-commit notification extension point.

No WhatsApp or customer email is sent in this release. Payment/order services
call these functions only from transaction.on_commit(), so a future provider
can be added without changing payment truth or checkout latency.
"""

import logging

logger = logging.getLogger(__name__)


def payment_verified(order, payment):
    """Called once after a payment transitions to verified paid."""
    logger.info(
        "Payment verified for order %s (reference %s).",
        order.reference,
        payment.provider_reference,
    )


def order_status_changed(order, old_status, new_status, actor=None):
    logger.info(
        "Order %s status changed from %s to %s.",
        order.reference,
        old_status,
        new_status,
    )
