"""Branded transactional emails for staff invitations and password resets.

The provider lives in ``email_service``; this module only builds the message
content so templates can be tested and changed independently of Resend.
"""

import math
from urllib.parse import urljoin

from django.conf import settings
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import date_format

from .models import Payment

LOGO_STATIC_PATH = "assets/img/harvest_castle/of_favicon.png"
LOGO_WIDTH = 180
LOGO_HEIGHT = 128
LOGO_ALT = "O’Toosin Farms logo"


def absolute_static_url(path):
    """Return a stable absolute URL for a static asset.

    Email clients keep old messages for a long time, so the logo URL must not
    depend on a hashed manifest name. It is built from the public SITE_URL and
    STATIC_URL instead, which resolves after every deploy.
    """
    relative = path.lstrip("/")
    static_url = settings.STATIC_URL or "/static/"
    if static_url.startswith(("http://", "https://")):
        return urljoin(static_url, relative)
    base = (settings.SITE_URL or "").rstrip("/") + "/"
    return urljoin(base, f"{static_url}{relative}")


def _display_name(user):
    full_name = (user.get_full_name() or "").strip()
    if full_name:
        return full_name
    first_name = (getattr(user, "first_name", "") or "").strip()
    if first_name:
        return first_name
    return "there"


def _base_context(*, action_url, action_label):
    return {
        "site_url": settings.SITE_URL,
        "logo_url": absolute_static_url(LOGO_STATIC_PATH),
        "logo_width": LOGO_WIDTH,
        "logo_height": LOGO_HEIGHT,
        "logo_alt": LOGO_ALT,
        "action_url": action_url,
        "action_label": action_label,
        "support_email": getattr(settings, "SUPPORT_EMAIL", ""),
    }


def _render(html_template, text_template, context):
    return {
        "html": render_to_string(html_template, context),
        "text": render_to_string(text_template, context),
    }


def staff_invitation_email(invitation, invitation_url):
    local_expiry = timezone.localtime(invitation.expires_at)
    expiry_text = (
        f"{date_format(local_expiry, 'j F Y')} at "
        f"{date_format(local_expiry, 'H:i')} (Africa/Lagos)"
    )
    context = _base_context(
        action_url=invitation_url,
        action_label="Accept invitation",
    )
    context.update(
        {
            "invited_name": _display_name(invitation.user),
            "role_label": invitation.get_role_display(),
            "expiry_text": expiry_text,
            "expiry_hours": getattr(settings, "STAFF_INVITATION_HOURS", 72),
        }
    )
    message = _render(
        "emails/staff_invitation.html",
        "emails/staff_invitation.txt",
        context,
    )
    message["subject"] = "You’re invited to the O’Toosin Farms administration team"
    return message


def staff_password_reset_email(user, reset_url):
    hours = max(
        1,
        math.ceil(
            int(getattr(settings, "PASSWORD_RESET_TIMEOUT", 86400)) / 3600
        ),
    )
    expiry_text = f"{hours} hour{'s' if hours != 1 else ''} from when this email was sent"
    context = _base_context(
        action_url=reset_url,
        action_label="Reset password",
    )
    context.update(
        {
            "invited_name": _display_name(user),
            "expiry_text": expiry_text,
            "expiry_hours": hours,
        }
    )
    message = _render(
        "emails/staff_password_reset.html",
        "emails/staff_password_reset.txt",
        context,
    )
    message["subject"] = "Reset your O’Toosin Farms staff password"
    return message


def _order_admin_url(order):
    path = reverse(
        "Otoosin:staff_order_detail",
        kwargs={"reference": order.reference},
    )
    return f"{(settings.SITE_URL or '').rstrip('/')}{path}"


def order_notification_email(order):
    """Build the branded paid-order notification sent to configured staff."""
    paid_payment = (
        order.payments.filter(
            status=Payment.Status.PAID, verified_at__isnull=False
        )
        .order_by("-verified_at", "-pk")
        .first()
    )
    local_placed = timezone.localtime(order.placed_at)
    is_pickup = order.receive_method == order.ReceiveMethod.PICKUP
    context = _base_context(
        action_url=_order_admin_url(order),
        action_label="View Order in Admin",
    )
    context.update(
        {
            "order": order,
            "paid_payment": paid_payment,
            "order_datetime": date_format(local_placed, "j F Y, H:i"),
            "is_pickup": is_pickup,
            "is_park": order.receive_method == order.ReceiveMethod.PARK,
            "items": order.items.all(),
            "payment_status": (
                f"Paid (verified by {paid_payment.get_provider_display()})"
                if paid_payment
                else "Not verified as paid"
            ),
            "payment_method": (
                paid_payment.get_provider_display()
                if paid_payment
                else "Not recorded"
            ),
            "verified_at": (
                date_format(
                    timezone.localtime(paid_payment.verified_at),
                    "j F Y, H:i",
                )
                if paid_payment and paid_payment.verified_at
                else ""
            ),
            "payment_reference": (
                paid_payment.provider_reference if paid_payment else ""
            ),
        }
    )
    message = _render(
        "emails/order_notification.html",
        "emails/order_notification.txt",
        context,
    )
    message["subject"] = (
        f"New Paid Order – {order.reference} | O’Toosin Farms"
    )
    return message
