"""Small Paystack HTTP adapter.

Only the standard library is used so no new runtime dependency is required.
The secret key is read from Django settings and never logged or returned to
callers. Network calls are deliberately kept outside database transactions.
"""

import hashlib
import hmac
import json
import logging
from decimal import Decimal, ROUND_HALF_UP
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

from django.conf import settings

logger = logging.getLogger(__name__)


class PaystackError(Exception):
    def __init__(self, message, *, category="provider_error", retryable=False):
        super().__init__(message)
        self.category = category
        self.retryable = retryable


def configured():
    return bool(getattr(settings, "PAYSTACK_SECRET_KEY", "").strip())


def valid_authorization_url(value):
    """Only https provider-hosted URLs may ever be used for a redirect."""
    try:
        parsed = urlparse(str(value or ""))
    except ValueError:
        return False
    return parsed.scheme == "https" and bool(parsed.netloc)


def naira_to_kobo(amount):
    value = Decimal(amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return int((value * 100).to_integral_value(rounding=ROUND_HALF_UP))


def _headers():
    secret = getattr(settings, "PAYSTACK_SECRET_KEY", "").strip()
    if not secret:
        raise PaystackError(
            "Online payment is not configured yet.",
            category="not_configured",
        )
    return {
        "Authorization": f"Bearer {secret}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        # Paystack sits behind Cloudflare, which blocks urllib's default
        # "Python-urllib/x.y" signature with HTTP 403 error 1010.
        "User-Agent": "OToosinFarms/1.0 (+https://otoosinfarms.com)",
    }


def _request(method, path, payload=None):
    url = f"{settings.PAYSTACK_BASE_URL}{path}"
    body = None
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
    request = Request(url, data=body, method=method, headers=_headers())
    try:
        with urlopen(
            request, timeout=getattr(settings, "PAYSTACK_TIMEOUT_SECONDS", 30)
        ) as response:
            raw = response.read()
    except HTTPError as exc:
        # The provider body is intentionally not logged: it can contain
        # customer or payment metadata. Only the status and path are recorded.
        logger.warning(
            "Paystack HTTP %s on %s (%s)",
            exc.code,
            path,
            "provider rejected the request",
        )
        category = "not_found" if exc.code == 404 else "provider_rejected"
        raise PaystackError(
            "The payment provider rejected the request.",
            category=category,
            retryable=exc.code >= 500,
        ) from exc
    except TimeoutError as exc:
        raise PaystackError(
            "The payment provider did not respond in time.",
            category="timeout",
            retryable=True,
        ) from exc
    except URLError as exc:
        reason = getattr(exc, "reason", None)
        category = (
            "timeout" if isinstance(reason, TimeoutError) else "network"
        )
        raise PaystackError(
            "We could not reach the payment provider.",
            category=category,
            retryable=True,
        ) from exc
    except OSError as exc:
        raise PaystackError(
            "We could not reach the payment provider.",
            category="network",
            retryable=True,
        ) from exc

    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PaystackError(
            "The payment provider returned an invalid response.",
            category="malformed_response",
            retryable=True,
        ) from exc
    if not isinstance(data, dict):
        raise PaystackError(
            "The payment provider returned an invalid response.",
            category="malformed_response",
            retryable=True,
        )
    if not data.get("status"):
        message = str(data.get("message") or "").strip()
        raise PaystackError(
            message[:200] or "The payment provider rejected the request.",
            category="provider_rejected",
        )
    return data


def initialize_transaction(
    *, reference, amount, email, currency="NGN", callback_url, metadata=None
):
    if not email:
        raise PaystackError(
            "A valid email address is required for online payment.",
            category="validation",
        )
    payload = {
        "email": email,
        "amount": naira_to_kobo(amount),
        "currency": currency,
        "reference": reference,
        "callback_url": callback_url,
    }
    if metadata:
        payload["metadata"] = metadata
    data = _request("POST", "/transaction/initialize", payload)
    result = data.get("data")
    if not isinstance(result, dict):
        raise PaystackError(
            "The payment provider returned an invalid response.",
            category="malformed_response",
        )
    if not result.get("authorization_url") or not result.get("reference"):
        raise PaystackError(
            "The payment provider returned an incomplete response.",
            category="malformed_response",
        )
    if str(result.get("reference")) != str(reference):
        raise PaystackError(
            "The payment provider returned an unexpected reference.",
            category="malformed_response",
        )
    if not valid_authorization_url(result.get("authorization_url")):
        raise PaystackError(
            "The payment provider returned an unsafe payment URL.",
            category="malformed_response",
        )
    return result


def verify_transaction(reference):
    if not reference:
        raise PaystackError(
            "The payment reference is missing.", category="validation"
        )
    data = _request("GET", f"/transaction/verify/{quote(str(reference), safe='')}")
    result = data.get("data")
    if not isinstance(result, dict):
        raise PaystackError(
            "The payment provider returned an invalid response.",
            category="malformed_response",
        )
    return result


def valid_webhook_signature(raw_body, signature):
    secret = getattr(settings, "PAYSTACK_SECRET_KEY", "").strip()
    if not secret or not signature:
        return False
    expected = hmac.new(
        secret.encode("utf-8"), raw_body, hashlib.sha512
    ).hexdigest()
    return hmac.compare_digest(expected, str(signature).strip())


def sanitize_payment_data(data):
    """Return only the non-sensitive fields needed for support and audit."""
    if not isinstance(data, dict):
        return {}
    authorization = data.get("authorization")
    safe_authorization = {}
    if isinstance(authorization, dict):
        for key in ("card_type", "bank", "brand", "last4", "exp_month", "exp_year"):
            value = authorization.get(key)
            if value not in (None, ""):
                safe_authorization[key] = value
    allowed = (
        "id",
        "reference",
        "status",
        "amount",
        "currency",
        "channel",
        "gateway_response",
        "paid_at",
        "created_at",
        "fees",
    )
    result = {key: data.get(key) for key in allowed if data.get(key) not in (None, "")}
    if safe_authorization:
        result["authorization"] = safe_authorization
    return result
