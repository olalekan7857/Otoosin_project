"""Storefront checkout, Paystack callback/webhook and guest confirmation."""

import hashlib
import hmac
import json
import logging
import secrets

from django.conf import settings
from django.contrib import messages
from django.core.cache import cache
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from . import paystack
from .cart import CartPayloadError, build_checkout_lines
from .forms import CheckoutForm
from .models import (
    DeliveryLocation,
    Order,
    Payment,
    PickupLocation,
    SiteConfiguration,
)
from .orders import (
    CheckoutError,
    create_order,
    create_payment_attempt,
    expected_delivery_date,
)
from .payments import process_webhook, verify_payment

logger = logging.getLogger(__name__)

CHECKOUT_INIT_LIMIT = 12
CHECKOUT_INIT_WINDOW = 600


def _throttle_key(prefix, request, identifier=""):
    raw = f"{prefix}:{request.META.get('REMOTE_ADDR', '')}:{identifier.strip().lower()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _checkout_payload(request):
    if (request.content_type or "").startswith("application/json"):
        try:
            data = json.loads(request.body.decode(request.encoding or "utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CartPayloadError(
                "The checkout data could not be read. Please refresh and try again."
            ) from exc
        if not isinstance(data, dict):
            raise CartPayloadError("The checkout data is invalid.")
        return data
    data = request.POST.dict()
    raw_items = data.get("items")
    if isinstance(raw_items, str) and raw_items.strip().startswith("["):
        try:
            data["items"] = json.loads(raw_items)
        except json.JSONDecodeError as exc:
            raise CartPayloadError("The checkout items are invalid.") from exc
    return data


def _checkout_locations():
    delivery = [
        {
            "id": str(location.pk),
            "type": location.location_type,
            "name": location.name,
            "areas": location.area,
            "city": location.city,
            "state": location.state,
            "fee": float(location.fee) if location.fee is not None else None,
            "active": True,
            "order": location.sort_order,
            "instructions": location.customer_instructions,
        }
        for location in DeliveryLocation.objects.filter(is_active=True).order_by(
            "sort_order", "name"
        )
    ]
    pickup = [
        {
            "id": str(location.pk),
            "name": location.name,
            "address": location.address,
            "instructions": location.customer_instructions,
            "openingHours": location.opening_hours,
            "active": True,
        }
        for location in PickupLocation.objects.filter(is_active=True).order_by(
            "sort_order", "name"
        )
    ]
    return delivery, pickup


def checkout(request):
    if request.method == "POST":
        return _checkout_submit(request)
    token = secrets.token_urlsafe(32)
    request.session["checkout_token"] = token
    delivery_locations, pickup_locations = _checkout_locations()
    config = SiteConfiguration.load()
    cutoff = config.delivery_cutoff_time
    return render(
        request,
        "checkout.html",
        {
            "checkout_token": token,
            "delivery_locations": delivery_locations,
            "pickup_locations": pickup_locations,
            "expected_delivery_date": expected_delivery_date(config),
            "cutoff_time": cutoff.strftime("%I:%M %p").lstrip("0")
            if cutoff
            else "",
        },
    )


def _checkout_error(message, *, field="", status=400):
    return JsonResponse(
        {
            "ok": False,
            "message": message,
            "errors": {field: [message]} if field else {"__all__": [message]},
        },
        status=status,
    )


def _already_paid_response(order):
    return JsonResponse(
        {
            "ok": True,
            "already_paid": True,
            "order_reference": order.reference,
            "confirmation_url": _confirmation_url(order),
            "cart_fingerprint": order.cart_fingerprint,
        }
    )


def _resume_response(order, redirect_url):
    return JsonResponse(
        {
            "ok": True,
            "resumed": True,
            "order_reference": order.reference,
            "redirect_url": redirect_url,
            "confirmation_url": _confirmation_url(order),
            "cart_fingerprint": order.cart_fingerprint,
        }
    )


def _ambiguous_response(order, payment):
    return JsonResponse(
        {
            "ok": False,
            "ambiguous": True,
            "payment_status": payment.status,
            "message": (
                "We could not confirm the payment provider response. Your "
                "order is saved; use Check payment status before retrying."
            ),
            "order_reference": order.reference,
            "confirmation_url": _confirmation_url(order),
        },
        status=409,
    )


def _confirmation_url(order):
    base = reverse(
        "Otoosin:order_confirmation_detail",
        kwargs={"reference": order.reference},
    )
    return f"{base}?token={order.access_token}"


def _bind_order_to_session(request, order):
    references = list(request.session.get("order_references", []))
    if order.reference not in references:
        references.append(order.reference)
    request.session["order_references"] = references[-20:]


def _initialise_payment(payment, order):
    if not paystack.configured():
        raise paystack.PaystackError(
            "Online payment is not configured yet.", category="not_configured"
        )
    callback = f"{settings.SITE_URL}{reverse('Otoosin:payment_callback')}"
    data = paystack.initialize_transaction(
        reference=payment.provider_reference,
        amount=payment.amount,
        email=order.customer_email,
        currency=payment.currency,
        callback_url=callback,
        metadata={
            "order_reference": order.reference,
            "payment_reference": payment.provider_reference,
        },
    )
    if str(data.get("reference") or "") != payment.provider_reference:
        raise paystack.PaystackError(
            "The payment provider returned an unexpected reference.",
            category="malformed_response",
        )
    authorization_url = str(data.get("authorization_url") or "")
    if not paystack.valid_authorization_url(authorization_url):
        raise paystack.PaystackError(
            "The payment provider returned an unsafe payment URL.",
            category="malformed_response",
        )
    payment.provider_access_code = str(data.get("access_code") or "")[:200]
    payment.authorization_url = authorization_url
    payment.status = Payment.Status.PENDING
    payment.initialized_at = timezone.now()
    payment.failure_category = ""
    payment.failure_message = ""
    payment.gateway_response = paystack.sanitize_payment_data(data)
    payment.save(
        update_fields=[
            "provider_access_code",
            "authorization_url",
            "status",
            "initialized_at",
            "failure_category",
            "failure_message",
            "gateway_response",
            "updated_at",
        ]
    )
    return payment.authorization_url


def _checkout_init_throttled(request):
    key = _throttle_key(
        "checkout-init",
        request,
        str(request.session.get("checkout_token") or "anonymous"),
    )
    count = cache.get(key, 0)
    if count >= CHECKOUT_INIT_LIMIT:
        return True
    cache.set(key, count + 1, CHECKOUT_INIT_WINDOW)
    return False


def _checkout_submit(request):
    try:
        data = _checkout_payload(request)
    except CartPayloadError as exc:
        return _checkout_error(str(exc))

    raw_items = data.get("items")
    if not isinstance(raw_items, list):
        return _checkout_error("Your cart could not be read. Please refresh.")

    form = CheckoutForm(data)
    if not form.is_valid():
        errors = {
            field: [error["message"] for error in items]
            for field, items in form.errors.get_json_data().items()
        }
        first = next(iter(errors.values()))[0] if errors else "Check your details."
        return JsonResponse(
            {"ok": False, "message": first, "errors": errors}, status=400
        )

    items, cart_result = build_checkout_lines(raw_items)
    if cart_result.get("errors") or not items:
        messages_list = [
            error["message"]
            for error in cart_result.get("errors", [])
            if error.get("message")
        ]
        return JsonResponse(
            {
                "ok": False,
                "message": messages_list[0]
                if messages_list
                else "Your cart is no longer valid.",
                "errors": {"items": messages_list},
                "cart": cart_result,
            },
            status=400,
        )

    session_token = request.session.get("checkout_token")
    try:
        order, created = create_order(
            cleaned=form.cleaned_data,
            items=items,
            session=request.session,
            session_token=session_token,
        )
    except CheckoutError as exc:
        return _checkout_error(exc.message, field=exc.field, status=400)

    _bind_order_to_session(request, order)
    request.session["checkout_token"] = None

    paid = order.payments.filter(
        status=Payment.Status.PAID, verified_at__isnull=False
    ).first()
    if paid is not None:
        return JsonResponse(
            {
                "ok": True,
                "already_paid": True,
                "order_reference": order.reference,
                "confirmation_url": _confirmation_url(order),
                "cart_fingerprint": order.cart_fingerprint,
            }
        )

    latest = order.payments.order_by("-created_at", "-pk").first()
    payment = None
    if latest is not None:
        if latest.status == Payment.Status.PAID and latest.verified_at:
            return _already_paid_response(order)
        if latest.status in {
            Payment.Status.PENDING,
            Payment.Status.INITIATED,
        }:
            if latest.authorization_url:
                return _resume_response(order, latest.authorization_url)
            # The outcome is ambiguous (for example an initialization timeout).
            # Reconcile the existing reference before any new attempt is made.
            result = verify_payment(latest)
            latest.refresh_from_db()
            if latest.status == Payment.Status.PAID and latest.verified_at:
                return _already_paid_response(order)
            if latest.status == Payment.Status.REFUNDED:
                return _checkout_error(
                    "This order's payment was reversed and is not eligible "
                    "for another attempt.",
                    status=409,
                )
            if latest.status in {
                Payment.Status.FAILED,
                Payment.Status.ABANDONED,
            }:
                payment = None
            elif result.get("error") == "not_found":
                # The provider never saw this reference, so retrying the same
                # attempt cannot create a duplicate charge.
                payment = latest
            else:
                return _ambiguous_response(order, latest)
        elif latest.status == Payment.Status.REFUNDED:
            return _checkout_error(
                "This order's payment was reversed and is not eligible for "
                "another attempt.",
                status=409,
            )

    if payment is None:
        if _checkout_init_throttled(request):
            return _checkout_error(
                "Too many payment attempts. Please wait a few minutes and try again.",
                status=429,
            )
        try:
            payment = create_payment_attempt(order)
        except CheckoutError as exc:
            return _checkout_error(exc.message, status=409)

    try:
        redirect_url = _initialise_payment(payment, order)
    except paystack.PaystackError as exc:
        payment.last_checked_at = timezone.now()
        payment.failure_category = exc.category[:60]
        payment.failure_message = str(exc)[:300]
        if exc.category in {"timeout", "network", "malformed_response"}:
            payment.status = Payment.Status.PENDING
        else:
            payment.status = Payment.Status.FAILED
        payment.save(
            update_fields=[
                "status",
                "last_checked_at",
                "failure_category",
                "failure_message",
                "updated_at",
            ]
        )
        if exc.category in {"timeout", "network"}:
            result = verify_payment(payment)
            if result.get("status") == Payment.Status.PAID:
                return JsonResponse(
                    {
                        "ok": True,
                        "already_paid": True,
                        "order_reference": order.reference,
                        "confirmation_url": _confirmation_url(order),
                    }
                )
        logger.warning(
            "Payment initialisation failed for %s: %s",
            order.reference,
            exc.category,
        )
        ambiguous = exc.category in {"timeout", "network", "malformed_response"}
        return JsonResponse(
            {
                "ok": False,
                "ambiguous": ambiguous,
                "message": (
                    "We could not confirm the payment provider response. "
                    "Your order is saved; use Check payment status before retrying."
                    if ambiguous
                    else "Online payment is temporarily unavailable. "
                    "Your order is saved and your cart has not been cleared."
                ),
                "order_reference": order.reference,
                "confirmation_url": _confirmation_url(order),
            },
            status=503 if exc.retryable else 502,
        )

    return JsonResponse(
        {
            "ok": True,
            "order_reference": order.reference,
            "redirect_url": redirect_url,
            "confirmation_url": _confirmation_url(order),
            "cart_fingerprint": order.cart_fingerprint,
        }
    )


def _authorised_order(request, reference):
    order = Order.objects.filter(reference__iexact=str(reference or "")).first()
    if order is None:
        raise Http404
    references = request.session.get("order_references", [])
    supplied = request.GET.get("token") or request.POST.get("access_token") or ""
    if order.reference not in references and not (
        supplied and hmac.compare_digest(str(supplied), order.access_token)
    ):
        raise Http404
    _bind_order_to_session(request, order)
    return order


@require_GET
def order_confirmation(request, reference=None):
    lookup = reference or request.GET.get("order")
    order = None
    if lookup:
        try:
            order = _authorised_order(request, lookup)
        except Http404:
            order = None
    latest_payment = None
    verified_paid = None
    clear_payload = None
    if order is not None:
        latest_payment = order.payments.order_by("-created_at", "-pk").first()
        verified_paid = order.payments.filter(
            status=Payment.Status.PAID, verified_at__isnull=False
        ).first()
        if verified_paid is not None:
            clear_payload = json.dumps(
                {
                    "reference": order.reference,
                    "fingerprint": order.cart_fingerprint,
                    "lines": [
                        {
                            # The browser cart key is product slug + variant PK,
                            # matching Otoosin/cart.py line payloads exactly.
                            "key": f"{item.product.slug}__{item.variant_id}"
                            if item.product_id and item.variant_id
                            else "",
                            "quantity": str(item.quantity.normalize()),
                        }
                        for item in order.items.select_related("product")
                    ],
                }
            )
    response = render(
        request,
        "order-confirmation.html",
        {
            "order": order,
            "latest_payment": latest_payment,
            "verified_paid": verified_paid,
            "display_payment": verified_paid or latest_payment,
            "clear_payload": clear_payload,
        },
        status=200 if order else 404,
    )
    response["Cache-Control"] = "no-store"
    response["X-Robots-Tag"] = "noindex"
    return response


@require_GET
def payment_callback(request):
    reference = (
        request.GET.get("reference") or request.GET.get("trxref") or ""
    ).strip()
    payment = (
        Payment.objects.select_related("order")
        .filter(provider_reference=reference)
        .first()
    )
    if payment is None:
        return render(
            request,
            "payment-result.html",
            {"message": "We could not find that payment reference."},
            status=404,
        )
    _bind_order_to_session(request, payment.order)
    verify_payment(payment)
    return redirect(
        reverse(
            "Otoosin:order_confirmation_detail",
            kwargs={"reference": payment.order.reference},
        )
    )


@require_POST
def order_retry_payment(request, reference):
    order = _authorised_order(request, reference)
    confirmation = reverse(
        "Otoosin:order_confirmation_detail",
        kwargs={"reference": order.reference},
    )
    if order.payments.filter(
        status=Payment.Status.PAID, verified_at__isnull=False
    ).exists():
        messages.info(request, "This order has already been paid.")
        return redirect(confirmation)
    if order.status != Order.Status.PENDING:
        messages.error(request, "This order is no longer eligible for payment.")
        return redirect(confirmation)

    payment = None
    latest = order.payments.order_by("-created_at", "-pk").first()
    if latest is not None:
        if latest.status in {
            Payment.Status.PENDING,
            Payment.Status.INITIATED,
        }:
            if latest.authorization_url:
                return redirect(latest.authorization_url)
            result = verify_payment(latest)
            latest.refresh_from_db()
            if latest.status == Payment.Status.PAID and latest.verified_at:
                return redirect(confirmation)
            if latest.status == Payment.Status.REFUNDED:
                messages.error(
                    request,
                    "This order's payment was reversed and is not eligible "
                    "for another attempt.",
                )
                return redirect(confirmation)
            if latest.status in {
                Payment.Status.FAILED,
                Payment.Status.ABANDONED,
            }:
                payment = None
            elif result.get("error") == "not_found":
                payment = latest
            else:
                messages.warning(
                    request,
                    "Your payment is still pending confirmation. "
                    "Please check again shortly.",
                )
                return redirect(confirmation)
        elif latest.status == Payment.Status.REFUNDED:
            messages.error(
                request,
                "This order's payment was reversed and is not eligible for "
                "another attempt.",
            )
            return redirect(confirmation)

    if payment is None:
        if _checkout_init_throttled(request):
            messages.error(
                request,
                "Too many payment attempts. Please wait a few minutes and try again.",
            )
            return redirect(confirmation)
        try:
            payment = create_payment_attempt(order)
        except CheckoutError as exc:
            messages.error(request, exc.message)
            return redirect(confirmation)

    try:
        redirect_url = _initialise_payment(payment, order)
    except paystack.PaystackError:
        logger.warning("Payment retry failed for order %s.", order.reference)
        messages.error(
            request,
            "We could not start another payment right now. Your order is saved.",
        )
        return redirect(confirmation)
    return redirect(redirect_url)


@csrf_exempt
@require_POST
def paystack_webhook(request):
    result = process_webhook(
        request.body, request.headers.get("x-paystack-signature", "")
    )
    return JsonResponse(
        {"ok": result.get("ok", False)}, status=result.get("status", 200)
    )
