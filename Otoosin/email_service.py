import json
import socket
from urllib import error as urlerror
from urllib import request as urlrequest

from django.conf import settings
from django.utils import timezone

from .models import EmailDelivery


class EmailConfigurationError(Exception):
    pass


def _send_request(payload):
    """Perform the Resend HTTPS request. Isolated so tests can mock it."""
    api_key = getattr(settings, "RESEND_API_KEY", "")
    if not api_key:
        raise EmailConfigurationError("Resend is not configured.")
    body = json.dumps(payload).encode("utf-8")
    request = urlrequest.Request(
        getattr(settings, "RESEND_API_URL", "https://api.resend.com/emails"),
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "OtoosinFarms/1.0",
        },
        method="POST",
    )
    timeout = max(1, int(getattr(settings, "RESEND_TIMEOUT_SECONDS", 10)))
    with urlrequest.urlopen(request, timeout=timeout) as response:
        return response.status, response.read().decode("utf-8", "replace")


def _fail(delivery, message, *, retryable=True):
    delivery.status = EmailDelivery.Status.FAILED
    delivery.retryable = retryable
    delivery.last_error = str(message)[:300]
    delivery.save(
        update_fields=[
            "status",
            "retryable",
            "last_error",
            "attempts",
            "updated_at",
        ]
    )
    return delivery


def send_email(*, category, recipient, subject, text, html=None):
    """Send one transactional email through Resend and persist delivery state.

    A queued record is created before the provider call. It is only marked
    "sent" when Resend accepts the request (a 2xx response).
    """
    delivery = EmailDelivery.objects.create(
        category=category,
        recipient=recipient,
        subject=subject,
        status=EmailDelivery.Status.QUEUED,
    )
    delivery.attempts += 1

    from_email = getattr(settings, "RESEND_FROM_EMAIL", "") or getattr(
        settings, "DEFAULT_FROM_EMAIL", ""
    )
    if not from_email:
        return _fail(delivery, "No verified Resend sender is configured.")
    if not getattr(settings, "RESEND_API_KEY", ""):
        return _fail(delivery, "Resend API key is not configured.")

    payload = {
        "from": from_email,
        "to": [recipient],
        "subject": subject,
        "text": text,
    }
    if html:
        payload["html"] = html

    try:
        status_code, response_body = _send_request(payload)
    except EmailConfigurationError as exc:
        return _fail(delivery, str(exc))
    except socket.timeout:
        return _fail(delivery, "The Resend request timed out.")
    except urlerror.HTTPError as exc:
        retryable = exc.code == 429 or exc.code >= 500
        detail = ""
        try:
            raw_body = exc.read().decode("utf-8", "replace") if exc.fp else ""
            parsed = json.loads(raw_body or "{}")
            detail = str(parsed.get("message") or "").strip()
        except (AttributeError, ValueError, OSError):
            detail = ""
        message = f"Resend rejected the request (HTTP {exc.code})."
        if detail:
            message = f"{message} {detail}"
        return _fail(delivery, message, retryable=retryable)
    except urlerror.URLError:
        return _fail(delivery, "Could not reach the Resend service.")
    except Exception:
        return _fail(delivery, "The Resend request failed.")

    if not 200 <= status_code < 300:
        return _fail(
            delivery,
            f"Resend rejected the request (HTTP {status_code}).",
            retryable=status_code == 429 or status_code >= 500,
        )

    provider_id = ""
    try:
        provider_id = str(json.loads(response_body or "{}").get("id", ""))[:120]
    except (ValueError, AttributeError):
        provider_id = ""

    delivery.status = EmailDelivery.Status.SENT
    delivery.retryable = False
    delivery.provider_message_id = provider_id
    delivery.last_error = ""
    delivery.sent_at = timezone.now()
    delivery.save(
        update_fields=[
            "status",
            "retryable",
            "provider_message_id",
            "last_error",
            "attempts",
            "sent_at",
            "updated_at",
        ]
    )
    return delivery
