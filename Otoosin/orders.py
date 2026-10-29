"""Server-authoritative checkout, delivery pricing and order creation."""

import hashlib
import logging
import secrets
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

from .models import (
    Inventory,
    Order,
    OrderItem,
    OrderStatusEvent,
    Payment,
    PickupLocation,
    DeliveryLocation,
    SiteConfiguration,
    ORDER_REFERENCE_ALPHABET,
)

logger = logging.getLogger(__name__)

MONEY = Decimal("0.01")
PRICE_LABELS = {
    "kg": "Per kilogram",
    "piece": "Per piece",
    "crate": "Per crate",
    "basket": "Per basket",
    "pack": "Per pack",
    "live_animal": "Per live animal",
}


class CheckoutError(Exception):
    def __init__(self, message, *, field="", category="validation"):
        super().__init__(message)
        self.message = message
        self.field = field
        self.category = category


def money(value):
    return Decimal(value).quantize(MONEY, rounding=ROUND_HALF_UP)


def new_order_reference():
    suffix = "".join(
        secrets.choice(ORDER_REFERENCE_ALPHABET) for _ in range(10)
    )
    return f"OF-{suffix}"


def new_payment_reference(order):
    return f"{order.reference}-{secrets.token_hex(5).upper()}"


def cart_fingerprint(items):
    """Identify the exact purchased lines, including the database price.

    Price is part of the identity so a resumed checkout cannot silently reuse
    an old order after the catalogue price has changed.
    """
    parts = sorted(
        (
            f"{item['key']}:"
            f"{Decimal(item['quantity']).quantize(Decimal('0.01')):.2f}:"
            f"{money(item['unit_price']):.2f}"
        )
        for item in items
    )
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def expected_delivery_date(config=None):
    """Apply only the approved cut-off rule: at/after cut-off, next day.

    Weekend and public-holiday handling is still an unresolved owner decision,
    so this intentionally returns a single calendar day and callers must not
    present it as a guaranteed delivery promise.
    """
    config = config or SiteConfiguration.load()
    now = timezone.localtime()
    cutoff = config.delivery_cutoff_time
    if cutoff is None or now.time() < cutoff:
        return now.date()
    return now.date() + timedelta(days=1)


def resolve_fulfilment(cleaned):
    """Return fee and immutable fulfilment snapshots from current records."""
    method = cleaned["receive_method"]
    address = (cleaned.get("address") or "").strip()
    landmark = (cleaned.get("landmark") or "").strip()

    if method == "pickup":
        lookup = (cleaned.get("pickup_location") or "").strip()
        pickup = None
        if lookup.isdigit():
            pickup = PickupLocation.objects.filter(pk=lookup, is_active=True).first()
        if pickup is None:
            raise CheckoutError(
                "Select an active pickup location.", field="pickup_location"
            )
        return {
            "receive_method": Order.ReceiveMethod.PICKUP,
            "delivery_location": None,
            "pickup_location": pickup,
            "location_name": pickup.name,
            "location_address": pickup.address,
            "location_instructions": " ".join(
                part
                for part in (pickup.opening_hours, pickup.customer_instructions)
                if part
            )[:300],
            "delivery_address": "",
            "landmark": "",
            "city": "Abeokuta",
            "state": "Ogun",
            "delivery_fee": money(0),
        }

    lookup = (cleaned.get("delivery_location") or "").strip()
    location = None
    if lookup.isdigit():
        location = DeliveryLocation.objects.filter(
            pk=lookup, is_active=True
        ).first()
    if location is None:
        raise CheckoutError(
            "Select an active delivery location.", field="delivery_location"
        )
    if location.fee is None:
        raise CheckoutError(
            "The selected delivery location does not have an approved fee yet.",
            field="delivery_location",
        )
    if location.location_type == DeliveryLocation.LocationType.DOORSTEP:
        if len(address) < 5:
            raise CheckoutError(
                "Enter your full delivery address.", field="address"
            )
        if (location.city or "").casefold() != "abeokuta" or (
            location.state or ""
        ).casefold() not in {"", "ogun"}:
            raise CheckoutError(
                "The selected location is not an approved doorstep zone.",
                field="delivery_location",
            )
        receive_method = Order.ReceiveMethod.DOORSTEP
        location_address = location.area or ""
        city = location.city
        state = location.state or "Ogun"
        instructions = location.customer_instructions
    else:
        if not (location.customer_instructions or "").strip():
            raise CheckoutError(
                "The selected park destination is not fully configured.",
                field="delivery_location",
            )
        receive_method = Order.ReceiveMethod.PARK
        address = ""
        landmark = ""
        location_address = location.area or ""
        city = location.city
        state = location.state
        instructions = location.customer_instructions

    return {
        "receive_method": receive_method,
        "delivery_location": location,
        "pickup_location": None,
        "location_name": location.name,
        "location_address": location_address,
        "location_instructions": instructions,
        "delivery_address": address,
        "landmark": landmark,
        "city": city,
        "state": state,
        "delivery_fee": money(location.fee),
    }


def _decrement_stock(items):
    """Decrement tracked stock with a conditional UPDATE (SQLite safe)."""
    for item in items:
        tracked = Inventory.objects.filter(
            variant=item["variant"], track_stock=True
        )
        if not tracked.exists():
            continue
        updated = tracked.filter(
            quantity_available__gte=item["quantity"]
        ).update(quantity_available=F("quantity_available") - item["quantity"])
        if not updated:
            raise CheckoutError(
                f"{item['product'].name} no longer has enough stock. "
                "Please review your cart.",
                field="items",
                category="stock",
            )


def restore_stock(order):
    for item in order.items.select_related("variant"):
        if item.variant_id is None:
            continue
        Inventory.objects.filter(
            variant_id=item.variant_id, track_stock=True
        ).update(quantity_available=F("quantity_available") + item.quantity)


def _generate_order_reference():
    for _ in range(8):
        reference = new_order_reference()
        if not Order.objects.filter(reference=reference).exists():
            return reference
    raise CheckoutError(
        "We could not create an order reference. Please try again.",
        category="reference",
    )


def create_order(*, cleaned, items, session, session_token):
    """Create one order atomically and return (order, created).

    The idempotency token belongs to the server-rendered checkout session.
    A repeat submission with the same token resumes the existing order.
    """
    token = (cleaned.get("checkout_token") or "").strip()
    if not token or len(token) > 64:
        raise CheckoutError("Your checkout session is invalid. Please refresh.")

    existing = Order.objects.filter(checkout_token=token).first()
    if existing is not None:
        references = session.get("order_references", [])
        if existing.reference not in references and token != session_token:
            raise CheckoutError(
                "This checkout session does not match that order. Please refresh.",
                category="idempotency",
            )
        return existing, False

    if token != session_token:
        raise CheckoutError(
            "Your checkout session has expired. Please refresh and try again.",
            category="idempotency",
        )

    fulfilment = resolve_fulfilment(cleaned)
    subtotal = sum((item["line_total"] for item in items), Decimal("0.00"))
    delivery_fee = fulfilment["delivery_fee"]
    total = money(subtotal + delivery_fee)
    if total <= 0:
        raise CheckoutError("Your cart total is invalid.", field="items")

    fingerprint = cart_fingerprint(items)
    config = SiteConfiguration.load()
    expected = (
        expected_delivery_date(config)
        if fulfilment["receive_method"] != Order.ReceiveMethod.PICKUP
        else None
    )

    resumed = _find_resumable_order(session, fingerprint, total)
    if resumed is not None:
        _refresh_pending_order(
            resumed,
            cleaned=cleaned,
            fulfilment=fulfilment,
            subtotal=subtotal,
            delivery_fee=delivery_fee,
            total=total,
            expected=expected,
            fingerprint=fingerprint,
        )
        _bind_reference(session, resumed.reference)
        session["checkout_token"] = None
        return resumed, False

    order = None
    for _ in range(8):
        reference = _generate_order_reference()
        try:
            with transaction.atomic():
                order = Order.objects.create(
                    reference=reference,
                    access_token=secrets.token_hex(32),
                    checkout_token=token,
                    cart_fingerprint=fingerprint,
                    customer_name=cleaned["name"],
                    customer_phone=cleaned["phone"],
                    customer_email=cleaned["email"],
                    status=Order.Status.PENDING,
                    receive_method=fulfilment["receive_method"],
                    ordering_method="website",
                    delivery_location=fulfilment["delivery_location"],
                    pickup_location=fulfilment["pickup_location"],
                    location_name=fulfilment["location_name"],
                    location_address=fulfilment["location_address"],
                    location_instructions=fulfilment["location_instructions"],
                    delivery_address=fulfilment["delivery_address"],
                    landmark=fulfilment["landmark"],
                    city=fulfilment["city"],
                    state=fulfilment["state"],
                    customer_notes=cleaned.get("instructions") or "",
                    subtotal=money(subtotal),
                    delivery_fee=delivery_fee,
                    total=total,
                    currency="NGN",
                    expected_delivery_date=expected,
                )
                for item in items:
                    product = item["product"]
                    variant = item["variant"]
                    image = product.primary_image
                    quantity = item["quantity"]
                    OrderItem.objects.create(
                        order=order,
                        product=product,
                        variant=variant,
                        product_name=product.name,
                        variant_label=variant.label,
                        sku=variant.sku,
                        unit=variant.get_unit_kind_display(),
                        unit_kind=variant.unit_kind,
                        category_name=(
                            product.category.name if product.category_id else ""
                        ),
                        condition=product.get_condition_display(),
                        image_path=image.image.url if image else "",
                        image_alt=image.alt if image else product.name,
                        quantity=quantity,
                        quantity_label=_quantity_label(quantity, variant),
                        unit_price=item["unit_price"],
                        line_total=item["line_total"],
                        currency="NGN",
                    )
                _decrement_stock(items)
                OrderStatusEvent.objects.create(
                    order=order,
                    from_status="",
                    to_status=Order.Status.PENDING,
                    note="Order created at checkout.",
                )
            break
        except IntegrityError:
            existing = Order.objects.filter(checkout_token=token).first()
            if existing is not None:
                return existing, False
            # A reference collision (or another transient unique clash) is
            # retried with a fresh cryptographically secure reference.
            logger.warning(
                "Order creation collided on a unique field; retrying safely."
            )
            order = None
            continue

    if order is None:
        logger.error("Order creation failed after repeated unique collisions.")
        raise CheckoutError(
            "We could not save your order. Please try again.",
            category="integrity",
        )

    _bind_reference(session, order.reference)
    session["checkout_token"] = None
    return order, True


def _bind_reference(session, reference):
    references = list(session.get("order_references", []))
    if reference not in references:
        references.append(reference)
    session["order_references"] = references[-20:]


def _find_resumable_order(session, fingerprint, total):
    """Find a session-bound unpaid order for the same priced cart.

    This protects against a fresh checkout page (new idempotency token) after
    an ambiguous payment timeout creating a second order for the same cart.
    """
    for reference in reversed(list(session.get("order_references", []))[-20:]):
        candidate = Order.objects.filter(
            reference=reference,
            status=Order.Status.PENDING,
            cart_fingerprint=fingerprint,
        ).first()
        if candidate is None:
            continue
        if candidate.payments.filter(
            status=Payment.Status.PAID, verified_at__isnull=False
        ).exists():
            continue
        if money(candidate.total) != money(total):
            continue
        return candidate
    return None


def _refresh_pending_order(
    order,
    *,
    cleaned,
    fulfilment,
    subtotal,
    delivery_fee,
    total,
    expected,
    fingerprint,
):
    """Refresh mutable pending-order details without touching item snapshots.

    Only used before any verified payment exists and only when the priced cart
    is identical, so historical item prices and the charged amount never move.
    """
    with transaction.atomic():
        Order.objects.filter(
            pk=order.pk, status=Order.Status.PENDING
        ).update(
            customer_name=cleaned["name"],
            customer_phone=cleaned["phone"],
            customer_email=cleaned["email"],
            receive_method=fulfilment["receive_method"],
            delivery_location=fulfilment["delivery_location"],
            pickup_location=fulfilment["pickup_location"],
            location_name=fulfilment["location_name"],
            location_address=fulfilment["location_address"],
            location_instructions=fulfilment["location_instructions"],
            delivery_address=fulfilment["delivery_address"],
            landmark=fulfilment["landmark"],
            city=fulfilment["city"],
            state=fulfilment["state"],
            customer_notes=cleaned.get("instructions") or "",
            subtotal=money(subtotal),
            delivery_fee=delivery_fee,
            total=total,
            expected_delivery_date=expected,
            cart_fingerprint=fingerprint,
            updated_at=timezone.now(),
        )
        order.refresh_from_db()
    return order


def _quantity_label(quantity, variant):
    label = f"{quantity.normalize():f}"
    if variant.unit_kind == "kg":
        return f"{label} kg"
    if quantity == 1:
        return f"{label} {variant.get_unit_kind_display().lower()}"
    return f"{label} {variant.get_unit_kind_display().lower()}s"


def create_payment_attempt(order, *, amount=None):
    if order.status != Order.Status.PENDING:
        raise CheckoutError("This order is no longer eligible for payment.")
    active_paid = order.payments.filter(status=Payment.Status.PAID).first()
    if active_paid is not None:
        raise CheckoutError("This order has already been paid.")
    if order.payments.filter(status=Payment.Status.REFUNDED).exists():
        raise CheckoutError(
            "This order's payment was reversed and cannot be charged again."
        )
    amount = money(amount if amount is not None else order.total)
    if amount != money(order.total):
        raise CheckoutError("The payment amount does not match the order.")
    for _ in range(8):
        reference = new_payment_reference(order)
        try:
            return Payment.objects.create(
                order=order,
                provider=Payment.Provider.PAYSTACK,
                provider_reference=reference,
                amount=amount,
                currency="NGN",
                status=Payment.Status.INITIATED,
            )
        except IntegrityError:
            continue
    raise CheckoutError(
        "We could not create a payment reference. Please try again.",
        category="reference",
    )
