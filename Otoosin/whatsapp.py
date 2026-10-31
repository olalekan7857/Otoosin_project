"""Small WhatsApp Cloud API adapter for staff order notifications."""

import json
import logging
import re
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from django.conf import settings
from django.urls import reverse
from django.utils import timezone

from .models import Payment

logger = logging.getLogger(__name__)

_GRAPH_VERSION_RE = re.compile(r"^v\d+\.\d+$")
_LANGUAGE_RE = re.compile(r"^[a-z]{2}_[A-Z]{2}$")
_PHONE_CHARS_RE = re.compile(r"^[+\d\s().-]+$")

# Meta rejects a template text parameter longer than 1024 characters. Refuse
# to send an oversized order silently instead of truncating order information.
MAX_TEMPLATE_PARAMETER_LENGTH = 1024

_ORDER_FIELDS = {
    "alert_title",
    "order_reference",
    "order_datetime",
    "order_status",
    "customer_name",
    "customer_phone",
    "customer_email",
    "customer_notes",
    "items",
    "subtotal",
    "delivery_fee",
    "total",
    "currency",
    "payment_status",
    "payment_method",
    "fulfilment",
    "fulfilment_location",
    "delivery_address",
    "delivery_instructions",
    "admin_url",
}


@dataclass(frozen=True)
class WhatsAppResult:
    """Outcome of a WhatsApp API operation.

    ``accepted`` means Meta accepted the request and returned a message ID.
    It does not mean that WhatsApp delivery has completed because delivery
    receipts are not implemented by this integration.
    """

    ok: bool
    accepted: bool = False
    category: str = ""
    message: str = ""
    message_id: str = ""
    recipient: str = ""
    status_code: int | None = None
    error_code: int | None = None
    error_subcode: int | None = None
    trace_id: str = ""


def _result(**kwargs):
    return WhatsAppResult(**kwargs)


def normalize_phone_number(value):
    """Return a WhatsApp-compatible international number without ``+``."""
    raw = str(value or "").strip()
    if not raw or not _PHONE_CHARS_RE.fullmatch(raw):
        raise ValueError("The recipient number contains invalid characters.")

    digits = re.sub(r"\D", "", raw)
    if digits.startswith("00"):
        digits = digits[2:]
    elif digits.startswith("0"):
        if len(digits) != 11:
            raise ValueError("Nigerian local numbers must contain 11 digits.")
        digits = f"234{digits[1:]}"

    if not 8 <= len(digits) <= 15 or digits.startswith("0"):
        raise ValueError("The recipient number must be an international number.")
    return digits


def _masked_recipient(recipient):
    return f"***{recipient[-4:]}" if len(recipient) > 4 else "***"


def _setting(name, default=""):
    value = getattr(settings, name, default)
    if isinstance(value, str):
        return value.strip()
    return value


def _configured_recipients():
    configured = getattr(settings, "WHATSAPP_ADMIN_RECIPIENTS", [])
    if isinstance(configured, str):
        configured = configured.split(",")
    return [str(value).strip() for value in configured if str(value).strip()]


def _string_list_setting(name):
    configured = getattr(settings, name, [])
    if isinstance(configured, str):
        configured = configured.split(",")
    return [str(value).strip() for value in configured if str(value).strip()]


def _configuration():
    if not bool(getattr(settings, "WHATSAPP_ENABLED", False)):
        return None, _result(
            ok=False,
            category="disabled",
            message="WhatsApp notifications are disabled.",
        )

    required = {
        "WHATSAPP_ACCESS_TOKEN": _setting("WHATSAPP_ACCESS_TOKEN"),
        "WHATSAPP_PHONE_NUMBER_ID": _setting("WHATSAPP_PHONE_NUMBER_ID"),
        "WHATSAPP_MESSAGE_TEMPLATE": _setting("WHATSAPP_MESSAGE_TEMPLATE"),
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        return None, _result(
            ok=False,
            category="not_configured",
            message=f"Missing WhatsApp configuration: {', '.join(missing)}.",
        )

    raw_graph_version = _setting("WHATSAPP_GRAPH_API_VERSION", "v25.0")
    graph_version = f"v{str(raw_graph_version).lstrip('vV')}"
    language = _setting("WHATSAPP_TEMPLATE_LANGUAGE", "en_US")
    phone_number_id = required["WHATSAPP_PHONE_NUMBER_ID"]
    if not _GRAPH_VERSION_RE.fullmatch(graph_version):
        return None, _result(
            ok=False,
            category="invalid_configuration",
            message="WHATSAPP_GRAPH_API_VERSION is invalid.",
        )
    if not phone_number_id.isdigit():
        return None, _result(
            ok=False,
            category="invalid_configuration",
            message="WHATSAPP_PHONE_NUMBER_ID is invalid.",
        )
    if not _LANGUAGE_RE.fullmatch(language):
        return None, _result(
            ok=False,
            category="invalid_configuration",
            message="WHATSAPP_TEMPLATE_LANGUAGE is invalid.",
        )

    try:
        timeout = float(_setting("WHATSAPP_TIMEOUT_SECONDS", "10"))
    except (TypeError, ValueError):
        return None, _result(
            ok=False,
            category="invalid_configuration",
            message="WHATSAPP_TIMEOUT_SECONDS is invalid.",
        )
    if timeout <= 0:
        return None, _result(
            ok=False,
            category="invalid_configuration",
            message="WHATSAPP_TIMEOUT_SECONDS must be greater than zero.",
        )

    return {
        "access_token": required["WHATSAPP_ACCESS_TOKEN"],
        "phone_number_id": phone_number_id,
        "graph_version": graph_version,
        "template": required["WHATSAPP_MESSAGE_TEMPLATE"],
        "language": language,
        "timeout": timeout,
    }, None


def _api_error_details(raw_body, access_token):
    details = {
        "message": "Meta rejected the WhatsApp request.",
        "error_code": None,
        "error_subcode": None,
        "trace_id": "",
    }
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        details["message"] = "Meta returned an invalid error response."
        return details
    if not isinstance(payload, dict):
        return details

    error = payload.get("error")
    if not isinstance(error, dict):
        return details
    message = str(error.get("message") or "").strip()
    if access_token and access_token in message:
        message = message.replace(access_token, "[redacted]")
    details["message"] = message[:240] or details["message"]
    for key, target in (("code", "error_code"), ("error_subcode", "error_subcode")):
        value = error.get(key)
        if isinstance(value, int):
            details[target] = value
    details["trace_id"] = str(
        error.get("fbtrace_id") or payload.get("fbtrace_id") or ""
    )[:120]
    return details


def _request(config, recipient, payload):
    url = (
        f"https://graph.facebook.com/{config['graph_version']}/"
        f"{config['phone_number_id']}/messages"
    )
    authorization = "Bearer " + config["access_token"]
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": authorization,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urlopen(request, timeout=config["timeout"]) as response:
            raw_body = response.read()
            status_code = getattr(response, "status", 200)
    except HTTPError as exc:
        details = _api_error_details(exc.read(), config["access_token"])
        logger.warning(
            "WhatsApp API rejected a request with HTTP %s for recipient %s "
            "(error code %s, subcode %s, trace %s).",
            exc.code,
            _masked_recipient(recipient),
            details["error_code"],
            details["error_subcode"],
            details["trace_id"] or "n/a",
        )
        return _result(
            ok=False,
            category="api_rejected",
            message=details["message"],
            recipient=recipient,
            status_code=exc.code,
            error_code=details["error_code"],
            error_subcode=details["error_subcode"],
            trace_id=details["trace_id"],
        )
    except TimeoutError:
        logger.warning(
            "WhatsApp API request timed out for recipient %s.",
            _masked_recipient(recipient),
        )
        return _result(
            ok=False,
            category="timeout",
            message="The WhatsApp API request timed out.",
            recipient=recipient,
        )
    except URLError as exc:
        logger.warning(
            "WhatsApp API network failure for recipient %s (%s).",
            _masked_recipient(recipient),
            type(getattr(exc, "reason", None)).__name__,
        )
        return _result(
            ok=False,
            category="network",
            message="The WhatsApp API could not be reached.",
            recipient=recipient,
        )
    except OSError:
        logger.warning(
            "WhatsApp API network failure for recipient %s.",
            _masked_recipient(recipient),
        )
        return _result(
            ok=False,
            category="network",
            message="The WhatsApp API could not be reached.",
            recipient=recipient,
        )

    try:
        response_data = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return _result(
            ok=False,
            category="malformed_response",
            message="Meta returned an invalid WhatsApp response.",
            recipient=recipient,
            status_code=status_code,
        )

    messages = response_data.get("messages") if isinstance(response_data, dict) else None
    message_id = (
        str(messages[0].get("id") or "")
        if isinstance(messages, list) and messages and isinstance(messages[0], dict)
        else ""
    )
    if not message_id:
        return _result(
            ok=False,
            category="malformed_response",
            message="Meta returned no WhatsApp message ID.",
            recipient=recipient,
            status_code=status_code,
        )
    return _result(
        ok=True,
        accepted=True,
        category="accepted",
        message="Meta accepted the message; delivery receipt not implemented.",
        message_id=message_id,
        recipient=recipient,
        status_code=status_code,
    )


def _text_parameters(values):
    return [{"type": "text", "text": str(value)} for value in values]


def send_template_message(
    recipient,
    *,
    body_parameters=(),
    header_parameters=(),
    url_button_parameter=None,
    url_button_index=0,
    template_name=None,
    language=None,
):
    """Send an approved WhatsApp template and return a structured result."""
    config, error = _configuration()
    if error is not None:
        return error

    try:
        normalized = normalize_phone_number(recipient)
    except ValueError as exc:
        return _result(
            ok=False,
            category="invalid_recipient",
            message=str(exc),
            recipient=str(recipient or ""),
        )

    template = (template_name or config["template"]).strip()
    template_language = (language or config["language"]).strip()
    if not template or not _LANGUAGE_RE.fullmatch(template_language):
        return _result(
            ok=False,
            category="invalid_configuration",
            message="The WhatsApp template name or language is invalid.",
            recipient=normalized,
        )

    if not isinstance(url_button_index, int) or url_button_index < 0:
        return _result(
            ok=False,
            category="invalid_configuration",
            message="The WhatsApp URL button index is invalid.",
            recipient=normalized,
        )

    components = []
    if header_parameters:
        components.append(
            {"type": "header", "parameters": _text_parameters(header_parameters)}
        )
    if body_parameters:
        components.append(
            {"type": "body", "parameters": _text_parameters(body_parameters)}
        )
    if url_button_parameter is not None:
        if not str(url_button_parameter).strip():
            return _result(
                ok=False,
                category="invalid_order",
                message="The WhatsApp URL button parameter is empty.",
                recipient=normalized,
            )
        components.append(
            {
                "type": "button",
                "sub_type": "url",
                "index": str(url_button_index),
                "parameters": _text_parameters([url_button_parameter]),
            }
        )

    template_payload = {
        "name": template,
        "language": {"code": template_language},
    }
    if components:
        template_payload["components"] = components
    payload = {
        "messaging_product": "whatsapp",
        "to": normalized,
        "type": "template",
        "template": template_payload,
    }
    return _request(config, normalized, payload)


def _money(value):
    return f"{value:,.2f}"


def _order_items_text(order):
    currency = order.currency
    lines = []
    for item in order.items.all():
        variant = f" ({item.variant_label})" if item.variant_label else ""
        quantity = item.quantity_label or str(item.quantity.normalize())
        lines.append(
            f"- {item.product_name}{variant} | Qty: {quantity} | "
            f"Unit: {currency} {_money(item.unit_price)} | "
            f"Line: {currency} {_money(item.line_total)}"
        )
    return "\n".join(lines) or "No items recorded"


def _admin_order_url(order):
    site_url = _setting("SITE_URL")
    if not site_url:
        raise ValueError("SITE_URL is not configured.")
    path = reverse(
        "Otoosin:staff_order_detail",
        kwargs={"reference": order.reference},
    )
    return urljoin(f"{site_url.rstrip('/')}/", path.lstrip("/"))


def _order_datetime(order):
    return timezone.localtime(order.placed_at).strftime("%d %b %Y, %I:%M %p %Z")


def _payment_values(order):
    payment = (
        order.payments.filter(
            status=Payment.Status.PAID, verified_at__isnull=False
        )
        .order_by("-verified_at", "-pk")
        .first()
    )
    if payment is None:
        return "Not verified as paid", "Not recorded"
    provider = payment.get_provider_display()
    return f"Paid (verified by {provider})", provider


def _fulfilment_values(order):
    method = order.receive_method
    if method == order.ReceiveMethod.PICKUP:
        location = " | ".join(
            part
            for part in (order.location_name, order.location_address)
            if part
        )
        return {
            "fulfilment": "PICKUP",
            "fulfilment_location": location or "Not specified",
            "delivery_address": "Not applicable (pickup)",
            "delivery_instructions": (
                order.location_instructions
                or order.customer_notes
                or "None recorded"
            ),
            "delivery_fee": "Not applicable (pickup)",
        }

    if method == order.ReceiveMethod.PARK:
        location = " | ".join(
            part
            for part in (
                order.location_name,
                order.location_address,
                order.city,
                order.state,
            )
            if part
        )
        return {
            "fulfilment": "DELIVERY (park)",
            "fulfilment_location": location or "Not specified",
            "delivery_address": location or "Not specified",
            "delivery_instructions": (
                order.location_instructions
                or order.customer_notes
                or "None recorded"
            ),
            "delivery_fee": f"{order.currency} {_money(order.delivery_fee)}",
        }

    address = " | ".join(
        part
        for part in (
            order.delivery_address,
            order.landmark,
            order.location_address,
            order.city,
            order.state,
        )
        if part
    )
    return {
        "fulfilment": "DELIVERY (doorstep)",
        "fulfilment_location": order.location_name or "Not specified",
        "delivery_address": address or "Not specified",
        "delivery_instructions": (
            order.location_instructions
            or order.customer_notes
            or "None recorded"
        ),
        "delivery_fee": f"{order.currency} {_money(order.delivery_fee)}",
    }


def _order_field_values(order):
    payment_status, payment_method = _payment_values(order)
    fulfilment = _fulfilment_values(order)
    return {
        "alert_title": "O'Toosin Farms new order alert",
        "order_reference": order.reference,
        "order_datetime": _order_datetime(order),
        "order_status": order.get_status_display(),
        "customer_name": order.customer_name,
        "customer_phone": order.customer_phone or "Not provided",
        "customer_email": order.customer_email or "Not provided",
        "customer_notes": order.customer_notes or "None recorded",
        "items": _order_items_text(order),
        "subtotal": f"{order.currency} {_money(order.subtotal)}",
        "delivery_fee": fulfilment["delivery_fee"],
        "total": f"{order.currency} {_money(order.total)}",
        "currency": order.currency,
        "payment_status": payment_status,
        "payment_method": payment_method,
        "fulfilment": fulfilment["fulfilment"],
        "fulfilment_location": fulfilment["fulfilment_location"],
        "delivery_address": fulfilment["delivery_address"],
        "delivery_instructions": fulfilment["delivery_instructions"],
        "admin_url": _admin_order_url(order),
    }


def _validated_fields(name, allowed=_ORDER_FIELDS):
    fields = _string_list_setting(name)
    unknown = [field for field in fields if field not in allowed]
    if unknown:
        raise ValueError(f"Unknown WhatsApp template fields: {', '.join(unknown)}.")
    return fields


def send_order_notification(order):
    """Notify configured staff recipients after a verified payment transition."""
    config, error = _configuration()
    if error is not None:
        return error

    try:
        body_fields = _validated_fields("WHATSAPP_TEMPLATE_BODY_FIELDS")
        header_fields = _validated_fields("WHATSAPP_TEMPLATE_HEADER_FIELDS")
    except ValueError as exc:
        return _result(
            ok=False,
            category="invalid_configuration",
            message=str(exc),
        )
    if not body_fields and not header_fields:
        return _result(
            ok=False,
            category="template_not_configured",
            message=(
                "WHATSAPP_TEMPLATE_BODY_FIELDS must list the approved "
                "template body variables in order."
            ),
        )

    url_button_field = _setting("WHATSAPP_TEMPLATE_URL_BUTTON_FIELD")
    if url_button_field and url_button_field not in _ORDER_FIELDS:
        return _result(
            ok=False,
            category="invalid_configuration",
            message=(
                "WHATSAPP_TEMPLATE_URL_BUTTON_FIELD must name a supported "
                "order field."
            ),
        )
    url_button_index = _setting("WHATSAPP_TEMPLATE_URL_BUTTON_INDEX", 0)
    if isinstance(url_button_index, str) and url_button_index.isdigit():
        url_button_index = int(url_button_index)

    recipients = _configured_recipients()
    if not recipients:
        return _result(
            ok=False,
            category="not_configured",
            message="No WhatsApp administrator recipients are configured.",
        )

    try:
        values = _order_field_values(order)
    except (AttributeError, ValueError) as exc:
        logger.exception("Could not build WhatsApp notification for an order.")
        return _result(
            ok=False,
            category="invalid_order",
            message=str(exc),
        )

    body_parameters = [values[field] for field in body_fields]
    header_parameters = [values[field] for field in header_fields]
    url_button_parameter = values[url_button_field] if url_button_field else None
    parameters = [*header_parameters, *body_parameters]
    if url_button_parameter is not None:
        parameters.append(url_button_parameter)
    oversized = [
        parameter
        for parameter in parameters
        if len(str(parameter)) > MAX_TEMPLATE_PARAMETER_LENGTH
    ]
    if oversized:
        return _result(
            ok=False,
            category="payload_too_long",
            message=(
                "An order template parameter exceeds Meta's "
                f"{MAX_TEMPLATE_PARAMETER_LENGTH}-character limit; no "
                "truncated message was sent."
            ),
        )

    results = [
        send_template_message(
            recipient,
            body_parameters=body_parameters,
            header_parameters=header_parameters,
            url_button_parameter=url_button_parameter,
            url_button_index=url_button_index,
            template_name=config["template"],
            language=config["language"],
        )
        for recipient in recipients
    ]
    accepted = [result for result in results if result.accepted]
    failures = [result for result in results if not result.accepted]
    for result in failures:
        logger.warning(
            "WhatsApp notification for order %s failed for recipient %s "
            "(category %s, HTTP %s, error code %s, subcode %s, trace %s): %s",
            order.reference,
            _masked_recipient(result.recipient),
            result.category,
            result.status_code,
            result.error_code,
            result.error_subcode,
            result.trace_id or "n/a",
            result.message,
        )
    if failures:
        first = failures[0]
        return _result(
            ok=False,
            accepted=bool(accepted),
            category="partial_failure" if accepted else first.category,
            message="; ".join(result.message for result in failures),
            status_code=first.status_code,
            error_code=first.error_code,
            error_subcode=first.error_subcode,
            trace_id=first.trace_id,
        )
    return _result(
        ok=True,
        accepted=True,
        category="accepted",
        message=f"Meta accepted notifications for {len(accepted)} recipient(s).",
        status_code=accepted[0].status_code,
        message_id=accepted[0].message_id,
    )
