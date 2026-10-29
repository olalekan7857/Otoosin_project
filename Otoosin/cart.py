import json
from decimal import Decimal, InvalidOperation, ROUND_DOWN, ROUND_HALF_UP

from django.db.models import Q

from .catalogue import public_products
from .models import Inventory, Product


KG_MIN = Decimal("0.5")
QTY_MAX = Decimal("99")
MONEY_STEP = Decimal("0.01")
KG_STEP = Decimal("0.01")
MAX_CART_LINES = 50
PRICE_LABELS = {
    "kg": "Per kilogram",
    "piece": "Per piece",
    "crate": "Per crate",
    "basket": "Per basket",
    "pack": "Per pack",
    "live_animal": "Per live animal",
}


class CartPayloadError(ValueError):
    pass


def _money(value):
    return Decimal(value).quantize(MONEY_STEP, rounding=ROUND_HALF_UP)


def _message(key, text):
    return {"key": key or "", "message": text}


def _read_payload(request):
    if not request.body:
        return {}
    if (request.content_type or "").startswith("application/json"):
        try:
            data = json.loads(request.body.decode(request.encoding or "utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CartPayloadError(
                "The cart data could not be read. Please refresh and try again."
            ) from exc
        if not isinstance(data, dict):
            raise CartPayloadError(
                "The cart data is invalid. Please refresh and try again."
            )
        return data
    data = request.POST.dict()
    raw_items = data.get("items")
    if isinstance(raw_items, str) and raw_items.strip().startswith("["):
        try:
            data["items"] = json.loads(raw_items)
        except json.JSONDecodeError as exc:
            raise CartPayloadError("The cart items are invalid.") from exc
    return data


def read_cart_lines(request):
    data = _read_payload(request)
    lines = data.get("items", [])
    if not isinstance(lines, list):
        raise CartPayloadError("The cart items are invalid.")
    if len(lines) > MAX_CART_LINES:
        raise CartPayloadError(
            f"A cart can contain at most {MAX_CART_LINES} different items."
        )
    return lines


def _line_value(line, *names):
    if not isinstance(line, dict):
        return ""
    for name in names:
        value = line.get(name)
        if value not in (None, ""):
            return value
    return ""


def _line_key(product_ref, variant_ref):
    return f"{product_ref or 'unknown'}__{variant_ref or ''}"


def _find_product(product_ref):
    product_ref = str(product_ref or "").strip()
    if not product_ref:
        return None
    query = Q(slug__iexact=product_ref)
    if product_ref.isdigit():
        query |= Q(pk=product_ref)
    return public_products().filter(query).first()


def _find_variant(product, variant_ref):
    variant_ref = str(variant_ref or "").strip()
    if not variant_ref:
        return product.default_variant
    if variant_ref.isdigit():
        variant = product.variants.filter(pk=variant_ref).first()
    else:
        # Older cart lines stored the visible variant label, not its PK.
        variant = (
            product.variants.filter(
                is_active=True, label__iexact=variant_ref
            )
            .order_by("-is_default", "sort_order", "pk")
            .first()
        )
    if variant is None or not variant.is_active:
        return None
    return variant


def _parse_quantity(raw, is_kg):
    try:
        quantity = Decimal(str(raw).strip())
    except (InvalidOperation, TypeError, ValueError, AttributeError):
        return None, "Enter a valid quantity."
    if not quantity.is_finite() or quantity <= 0:
        return None, "Quantity must be greater than zero."
    if is_kg:
        if quantity < KG_MIN:
            return None, "The minimum quantity is 0.5 kg."
        if quantity != quantity.quantize(KG_STEP):
            return None, "Use no more than two decimal places for kilograms."
    elif quantity != quantity.to_integral_value():
        return None, "This product is sold in whole units only."
    return quantity, None


def _stock_limit(variant):
    inventory = Inventory.objects.filter(
        variant=variant, track_stock=True
    ).first()
    if inventory is None:
        return None
    available = Decimal(inventory.quantity_available)
    if available <= 0:
        return Decimal("0")
    if variant.unit_kind == "kg":
        return available.quantize(KG_STEP, rounding=ROUND_DOWN)
    return available.to_integral_value(rounding=ROUND_DOWN)


def _line_payload(product, variant, quantity):
    is_kg = variant.unit_kind == "kg"
    image = product.primary_image
    price = _money(variant.price)
    return {
        "key": f"{product.slug}__{variant.pk}",
        "id": product.slug,
        "name": product.name,
        "variant": variant.label,
        "variantId": str(variant.pk),
        "price": float(price),
        "qty": float(quantity),
        "unit": variant.label,
        "unitKind": variant.unit_kind,
        "isKg": is_kg,
        "category": product.category.name if product.category_id else "",
        "image": image.image.url if image else "",
        "alt": image.alt if image else product.name,
        "priceLabel": PRICE_LABELS.get(
            variant.unit_kind, variant.get_unit_kind_display()
        ),
    }


def _validate_line(line, normalize):
    product_ref = _line_value(line, "product", "product_id", "productId", "id")
    variant_ref = _line_value(line, "variant", "variant_id", "variantId")
    raw_qty = _line_value(line, "quantity", "qty")
    submitted_price = _line_value(line, "price", "unitPrice")
    key = _line_key(product_ref, variant_ref)
    errors = []
    notices = []

    product = _find_product(product_ref)
    if product is None:
        return None, [_message(key, "This product is no longer available.")], []

    variant = _find_variant(product, variant_ref)
    if variant is None:
        return (
            None,
            [_message(key, "This selling option is no longer available.")],
            [],
        )

    key = f"{product.slug}__{variant.pk}"
    if product.availability_status == Product.Availability.OUT_OF_STOCK:
        return None, [_message(key, f"{product.name} is out of stock.")], []

    is_kg = variant.unit_kind == "kg"
    quantity, qty_error = _parse_quantity(raw_qty, is_kg)
    if qty_error:
        return None, [_message(key, qty_error)], []

    if quantity > QTY_MAX:
        if normalize:
            quantity = QTY_MAX
            notices.append(
                _message(key, f"Quantity reduced to the maximum of {QTY_MAX}.")
            )
        else:
            return (
                None,
                [_message(key, f"Quantity cannot be more than {QTY_MAX}.")],
                [],
            )

    stock = _stock_limit(variant)
    if stock is not None:
        if stock <= 0:
            return None, [_message(key, f"{product.name} is out of stock.")], []
        if quantity > stock:
            if normalize:
                if stock < (KG_MIN if is_kg else Decimal("1")):
                    return (
                        None,
                        [
                            _message(
                                key,
                                f"{product.name} no longer has enough stock.",
                            )
                        ],
                        [],
                    )
                quantity = stock
                unit = "kg" if is_kg else "unit"
                suffix = "" if is_kg else ("s" if stock != 1 else "")
                notices.append(
                    _message(
                        key,
                        f"Quantity reduced to {quantity} {unit}{suffix} because "
                        "that is all the stock available.",
                    )
                )
            else:
                unit = "kg" if is_kg else "unit"
                suffix = "" if is_kg else ("s" if stock != 1 else "")
                return (
                    None,
                    [
                        _message(
                            key,
                            f"Only {stock} {unit}{suffix} of {product.name} "
                            "is available.",
                        )
                    ],
                    [],
                )

    price = _money(variant.price)
    if submitted_price not in (None, ""):
        try:
            old_price = _money(Decimal(str(submitted_price)))
        except (InvalidOperation, TypeError, ValueError):
            old_price = None
        if old_price is not None and old_price != price:
            notices.append(
                _message(
                    key,
                    f"The price of {product.name} was updated to "
                    f"₦{price:,.2f}.",
                )
            )

    return _line_payload(product, variant, quantity), errors, notices


def validate_cart_lines(lines, normalize=False):
    items = []
    merged = {}
    errors = []
    notices = []

    for line in lines:
        item, line_errors, line_notices = _validate_line(line, normalize)
        errors.extend(line_errors)
        notices.extend(line_notices)
        if item is None:
            continue
        key = item["key"]
        if key in merged:
            merged[key]["qty"] = round(merged[key]["qty"] + item["qty"], 2)
            notices.append(
                _message(key, "Duplicate cart lines were combined.")
            )
        else:
            merged[key] = item

    for item in merged.values():
        product = _find_product(item["id"])
        variant = _find_variant(product, item["variantId"]) if product else None
        if variant is None:
            errors.append(
                _message(item["key"], "This selling option is no longer available.")
            )
            continue

        # Duplicate lines are combined above, so check the combined quantity.
        quantity = Decimal(str(item["qty"]))
        if quantity > QTY_MAX:
            if normalize:
                quantity = QTY_MAX
                notices.append(
                    _message(
                        item["key"],
                        f"Quantity reduced to the maximum of {QTY_MAX}.",
                    )
                )
            else:
                errors.append(
                    _message(
                        item["key"],
                        f"Quantity cannot be more than {QTY_MAX}.",
                    )
                )
                continue

        stock = _stock_limit(variant)
        if stock is not None and quantity > stock:
            is_kg = item["isKg"]
            minimum = KG_MIN if is_kg else Decimal("1")
            if normalize:
                if stock < minimum:
                    errors.append(
                        _message(
                            item["key"],
                            f"{item['name']} no longer has enough stock.",
                        )
                    )
                    continue
                quantity = stock
                unit = "kg" if is_kg else "unit"
                suffix = "" if is_kg else ("s" if stock != 1 else "")
                notices.append(
                    _message(
                        item["key"],
                        f"Quantity reduced to {quantity} {unit}{suffix} because "
                        "that is all the stock available.",
                    )
                )
            else:
                unit = "kg" if is_kg else "unit"
                suffix = "" if is_kg else ("s" if stock != 1 else "")
                errors.append(
                    _message(
                        item["key"],
                        f"Only {stock} {unit}{suffix} of {item['name']} "
                        "is available.",
                    )
                )
                continue

        price = _money(variant.price)
        item["qty"] = float(quantity)
        item["price"] = float(price)
        item["subtotal"] = float(_money(price * quantity))
        items.append(item)

    subtotal = sum(Decimal(str(item["subtotal"])) for item in items)
    return {
        "ok": not errors and (bool(items) if not normalize else True),
        "items": items,
        "errors": errors,
        "notices": notices,
        "subtotal": float(_money(subtotal)),
        "line_count": len(items),
    }


def validate_cart_request(request, normalize=False):
    lines = read_cart_lines(request)
    result = validate_cart_lines(lines, normalize=normalize)
    if not normalize and not result["items"] and not result["errors"]:
        result["errors"].append(_message("", "Your cart is empty."))
        result["ok"] = False
    return result


def build_checkout_lines(lines):
    """Return authoritative Decimal line data for order creation.

    This deliberately reuses the same validator used by the cart endpoints so
    checkout cannot drift into a second, weaker set of rules. The client price
    is never used for money.
    """
    result = validate_cart_lines(lines, normalize=False)
    if not result["items"] and not result["errors"]:
        result["errors"].append(_message("", "Your cart is empty."))
    if result["errors"] or not result["items"]:
        return [], result

    authoritative = []
    for item in result["items"]:
        product = _find_product(item["id"])
        variant = _find_variant(product, item["variantId"]) if product else None
        if product is None or variant is None:
            result["errors"].append(
                _message(item.get("key", ""), "This product is no longer available.")
            )
            continue
        try:
            quantity = Decimal(str(item["qty"]))
        except (InvalidOperation, TypeError, ValueError):
            result["errors"].append(
                _message(item.get("key", ""), "Enter a valid quantity.")
            )
            continue
        unit_price = _money(variant.price)
        line_total = _money(unit_price * quantity)
        authoritative.append(
            {
                "key": item["key"],
                "product": product,
                "variant": variant,
                "quantity": quantity,
                "unit_price": unit_price,
                "line_total": line_total,
            }
        )

    if result["errors"] or not authoritative:
        return [], result
    return authoritative, result
