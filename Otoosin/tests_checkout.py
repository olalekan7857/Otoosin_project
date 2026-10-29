"""Money-critical checkout, Paystack and staff order tests.

All Paystack calls are mocked. No real payment, email or WhatsApp request is
made by this module.
"""

import hashlib
import hmac
import json
import secrets
from datetime import datetime
from decimal import Decimal
from unittest import mock
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import (
    AuditEvent,
    Category,
    DeliveryLocation,
    Inventory,
    Order,
    OrderItem,
    OrderStatusEvent,
    Payment,
    PaymentWebhookEvent,
    PickupLocation,
    Product,
    ProductVariant,
    SiteConfiguration,
)
from .orders import CheckoutError, expected_delivery_date
from .payments import process_webhook, verify_payment
from .permissions import provision_staff_roles


PAYSTACK_SECRET = "sk_test_checkout_secret"


def make_product(sku="CHK-001", category_slug="pork", **overrides):
    category = Category.objects.get(slug=category_slug)
    values = {
        "name": f"Checkout Product {sku}",
        "sku": sku,
        "category": category,
        "condition": Product.Condition.FRESH,
        "description": "Checkout test product",
        "price_basis": "Per kilogram",
        "availability_status": Product.Availability.IN_STOCK,
    }
    values.update(overrides)
    return Product.objects.create(**values)


def success_data(payment, **overrides):
    data = {
        "id": 9000 + payment.pk,
        "status": "success",
        "reference": payment.provider_reference,
        "amount": int(Decimal(payment.amount) * 100),
        "currency": "NGN",
        "gateway_response": "Successful",
        "paid_at": "2026-10-29T10:00:00.000Z",
        "channel": "card",
    }
    data.update(overrides)
    return data


@override_settings(
    PAYSTACK_SECRET_KEY=PAYSTACK_SECRET,
    PAYSTACK_PUBLIC_KEY="pk_test_public",
    PAYSTACK_BASE_URL="https://api.paystack.co",
    PAYSTACK_TIMEOUT_SECONDS=5,
    SITE_URL="https://farm.example.com",
)
class CheckoutTestCase(TestCase):
    def setUp(self):
        cache.clear()
        self.client = Client()
        self.product = make_product()
        self.variant = ProductVariant.objects.create(
            product=self.product,
            sku="CHK-001-KG",
            label="1kg",
            unit_kind=ProductVariant.UnitKind.KG,
            price=Decimal("4800.00"),
            is_default=True,
        )
        Inventory.objects.create(
            variant=self.variant,
            track_stock=True,
            quantity_available=Decimal("3.500"),
        )
        self.piece_product = make_product(
            sku="CHK-EGG", category_slug="eggs", name="Checkout Eggs"
        )
        self.piece_variant = ProductVariant.objects.create(
            product=self.piece_product,
            sku="CHK-EGG-CRATE",
            label="Crate",
            unit_kind=ProductVariant.UnitKind.CRATE,
            price=Decimal("2500.00"),
            is_default=True,
        )
        self.doorstep = DeliveryLocation.objects.create(
            location_type=DeliveryLocation.LocationType.DOORSTEP,
            name="Camp",
            area="Camp Road",
            city="Abeokuta",
            state="Ogun",
            fee=Decimal("500.00"),
        )
        self.park = DeliveryLocation.objects.create(
            location_type=DeliveryLocation.LocationType.PARK,
            name="Challenge Park",
            city="Ibadan",
            state="Oyo",
            fee=Decimal("700.00"),
            customer_instructions="Collect at the park gate.",
        )
        self.pickup = PickupLocation.objects.create(
            name="Farm Gate",
            address="12 Farm Road, Abeokuta",
            opening_hours="Mon-Sat, 8am-6pm",
        )
        self.config = SiteConfiguration.load()

    # ---------- helpers ----------

    def checkout_token(self):
        response = self.client.get(reverse("Otoosin:checkout"))
        self.assertEqual(response.status_code, 200)
        return response.context["checkout_token"]

    def line(self, quantity="1.5", product=None, variant=None, price=None):
        product = product or self.product
        variant = variant or self.variant
        payload = {
            "product": product.slug,
            "variant": str(variant.pk),
            "quantity": quantity,
        }
        if price is not None:
            payload["price"] = price
        return payload

    def checkout_payload(self, token, **overrides):
        payload = {
            "checkout_token": token,
            "name": "Ada Okafor",
            "phone": "08031234567",
            "email": "ada@example.com",
            "receive_method": "delivery",
            "delivery_location": str(self.doorstep.pk),
            "pickup_location": "",
            "address": "12 Camp Road, Alabata",
            "landmark": "Opposite the filling station",
            "instructions": "Call on arrival",
            "items": [self.line(price="1")],
        }
        payload.update(overrides)
        return payload

    def post_checkout(self, token, **overrides):
        return self.client.post(
            reverse("Otoosin:checkout"),
            data=json.dumps(self.checkout_payload(token, **overrides)),
            content_type="application/json",
        )

    def fake_initialize(self, *, reference, amount, email, currency, callback_url, metadata=None):
        return {
            "reference": reference,
            "authorization_url": "https://checkout.paystack.com/test",
            "access_code": "access-code",
        }

    def make_order(
        self,
        *,
        status=Order.Status.PENDING,
        paid=False,
        method=Order.ReceiveMethod.PICKUP,
        reference=None,
        phone="+2348031234567",
        total=Decimal("5000.00"),
    ):
        reference = reference or f"OF-T{secrets.token_hex(4).upper()}"
        order = Order.objects.create(
            reference=reference,
            access_token=secrets.token_hex(16),
            customer_name="Ada Okafor",
            customer_phone=phone,
            customer_email="ada@example.com",
            status=status,
            receive_method=method,
            location_name="Farm Gate",
            location_address="12 Farm Road",
            subtotal=total,
            delivery_fee=Decimal("0.00"),
            total=total,
            currency="NGN",
        )
        OrderItem.objects.create(
            order=order,
            product=self.product,
            variant=self.variant,
            product_name=self.product.name,
            variant_label=self.variant.label,
            sku=self.variant.sku,
            unit="Kilogram",
            unit_kind="kg",
            category_name=self.product.category.name,
            condition=self.product.get_condition_display(),
            quantity=Decimal("1.000"),
            quantity_label="1 kg",
            unit_price=total,
            line_total=total,
            currency="NGN",
        )
        payment = Payment.objects.create(
            order=order,
            provider_reference=f"PAY-{secrets.token_hex(6).upper()}",
            amount=total,
            currency="NGN",
            status=Payment.Status.PAID if paid else Payment.Status.PENDING,
            verified_at=timezone.now() if paid else None,
            initialized_at=timezone.now(),
        )
        return order, payment


class CheckoutPricingTests(CheckoutTestCase):
    @mock.patch("Otoosin.paystack.initialize_transaction")
    def test_empty_cart_rejected(self, initialize):
        initialize.side_effect = self.fake_initialize
        token = self.checkout_token()
        response = self.post_checkout(token, items=[])
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["ok"])
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(Payment.objects.count(), 0)

    @mock.patch("Otoosin.paystack.initialize_transaction")
    def test_inactive_product_and_variant_rejected(self, initialize):
        initialize.side_effect = self.fake_initialize
        token = self.checkout_token()
        self.product.is_active = False
        self.product.save(update_fields=["is_active"])
        response = self.post_checkout(token)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Order.objects.count(), 0)

        self.product.is_active = True
        self.product.save(update_fields=["is_active"])
        self.variant.is_active = False
        self.variant.save(update_fields=["is_active"])
        token = self.checkout_token()
        response = self.post_checkout(token)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Order.objects.count(), 0)

    @mock.patch("Otoosin.paystack.initialize_transaction")
    def test_invalid_quantity_and_unit_increment_rejected(self, initialize):
        initialize.side_effect = self.fake_initialize
        for quantity in ("0.25", "0", "-1"):
            token = self.checkout_token()
            response = self.post_checkout(token, items=[self.line(quantity)])
            self.assertEqual(response.status_code, 400, quantity)
        token = self.checkout_token()
        response = self.post_checkout(
            token,
            items=[
                self.line(
                    "1.5",
                    product=self.piece_product,
                    variant=self.piece_variant,
                )
            ],
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("whole units", response.json()["message"])
        self.assertEqual(Order.objects.count(), 0)

    @mock.patch("Otoosin.paystack.initialize_transaction")
    def test_database_price_used_despite_forged_client_price(self, initialize):
        initialize.side_effect = self.fake_initialize
        token = self.checkout_token()
        response = self.post_checkout(token, items=[self.line(price="1")])
        self.assertEqual(response.status_code, 200)
        order = Order.objects.get()
        item = order.items.get()
        self.assertEqual(item.unit_price, Decimal("4800.00"))
        self.assertEqual(item.line_total, Decimal("7200.00"))
        self.assertEqual(order.subtotal, Decimal("7200.00"))
        self.assertEqual(order.delivery_fee, Decimal("500.00"))
        self.assertEqual(order.total, Decimal("7700.00"))

    @mock.patch("Otoosin.paystack.initialize_transaction")
    def test_doorstep_fee_comes_from_active_database_location(self, initialize):
        initialize.side_effect = self.fake_initialize
        token = self.checkout_token()
        response = self.post_checkout(token)
        self.assertEqual(response.status_code, 200)
        order = Order.objects.get()
        self.assertEqual(order.receive_method, Order.ReceiveMethod.DOORSTEP)
        self.assertEqual(order.delivery_fee, Decimal("500.00"))
        self.assertEqual(order.delivery_address, "12 Camp Road, Alabata")

    @mock.patch("Otoosin.paystack.initialize_transaction")
    def test_park_fee_included_in_total(self, initialize):
        initialize.side_effect = self.fake_initialize
        token = self.checkout_token()
        response = self.post_checkout(
            token,
            delivery_location=str(self.park.pk),
            address="",
            landmark="",
        )
        self.assertEqual(response.status_code, 200)
        order = Order.objects.get()
        self.assertEqual(order.receive_method, Order.ReceiveMethod.PARK)
        self.assertEqual(order.delivery_fee, Decimal("700.00"))
        self.assertEqual(order.total, Decimal("7900.00"))
        self.assertEqual(order.location_instructions, "Collect at the park gate.")

    @mock.patch("Otoosin.paystack.initialize_transaction")
    def test_pickup_fee_is_zero_and_no_delivery_date(self, initialize):
        initialize.side_effect = self.fake_initialize
        token = self.checkout_token()
        response = self.post_checkout(
            token,
            receive_method="pickup",
            delivery_location="",
            pickup_location=str(self.pickup.pk),
            address="",
        )
        self.assertEqual(response.status_code, 200)
        order = Order.objects.get()
        self.assertEqual(order.receive_method, Order.ReceiveMethod.PICKUP)
        self.assertEqual(order.delivery_fee, Decimal("0.00"))
        self.assertEqual(order.total, Decimal("7200.00"))
        self.assertIsNone(order.expected_delivery_date)

    def test_missing_inactive_location_and_missing_fee_block_checkout(self):
        token = self.checkout_token()
        self.doorstep.is_active = False
        self.doorstep.save(update_fields=["is_active"])
        response = self.post_checkout(token)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Order.objects.count(), 0)

        DeliveryLocation.objects.filter(pk=self.doorstep.pk).update(
            is_active=True, fee=None
        )
        token = self.checkout_token()
        response = self.post_checkout(token)
        self.assertEqual(response.status_code, 400)
        self.assertIn("approved fee", response.json()["message"])
        self.assertEqual(Order.objects.count(), 0)

    def test_doorstep_address_required(self):
        token = self.checkout_token()
        response = self.post_checkout(token, address="")
        self.assertEqual(response.status_code, 400)
        self.assertIn("delivery address", response.json()["message"].lower())
        self.assertEqual(Order.objects.count(), 0)

    @mock.patch("Otoosin.paystack.initialize_transaction")
    def test_stock_and_price_change_are_revalidated_at_checkout(self, initialize):
        initialize.side_effect = self.fake_initialize
        token = self.checkout_token()
        response = self.post_checkout(token, items=[self.line("10")])
        self.assertEqual(response.status_code, 400)
        self.assertIn("Only 3.50 kg", response.json()["message"])
        self.assertEqual(Order.objects.count(), 0)

        self.variant.price = Decimal("5000.00")
        self.variant.save(update_fields=["price"])
        token = self.checkout_token()
        response = self.post_checkout(token, items=[self.line("1")])
        self.assertEqual(response.status_code, 200)
        order = Order.objects.get()
        self.assertEqual(order.items.get().unit_price, Decimal("5000.00"))

    def test_expected_date_respects_cutoff_timezone_and_boundary(self):
        self.config.delivery_cutoff_time = datetime.strptime("17:00", "%H:%M").time()
        self.config.save(update_fields=["delivery_cutoff_time"])
        lagos = ZoneInfo("Africa/Lagos")
        before = datetime(2026, 10, 29, 16, 59, tzinfo=lagos)
        at_cutoff = datetime(2026, 10, 29, 17, 0, tzinfo=lagos)
        after = datetime(2026, 10, 29, 18, 0, tzinfo=lagos)
        with mock.patch("Otoosin.orders.timezone.localtime", return_value=before):
            self.assertEqual(expected_delivery_date(self.config).day, 29)
        with mock.patch(
            "Otoosin.orders.timezone.localtime", return_value=at_cutoff
        ):
            self.assertEqual(expected_delivery_date(self.config).day, 30)
        with mock.patch("Otoosin.orders.timezone.localtime", return_value=after):
            self.assertEqual(expected_delivery_date(self.config).day, 30)


class OrderCreationTests(CheckoutTestCase):
    @mock.patch("Otoosin.paystack.initialize_transaction")
    def test_order_and_item_snapshots_saved(self, initialize):
        initialize.side_effect = self.fake_initialize
        token = self.checkout_token()
        response = self.post_checkout(token)
        self.assertEqual(response.status_code, 200)
        order = Order.objects.get()
        self.assertTrue(order.reference.startswith("OF-"))
        self.assertEqual(len(order.reference), 13)
        self.assertEqual(len(order.access_token), 64)
        self.assertEqual(order.currency, "NGN")
        self.assertEqual(order.status, Order.Status.PENDING)
        item = order.items.get()
        self.assertEqual(item.product, self.product)
        self.assertEqual(item.variant, self.variant)
        self.assertEqual(item.product_name, self.product.name)
        self.assertEqual(item.category_name, self.product.category.name)
        self.assertEqual(item.quantity, Decimal("1.500"))
        self.assertEqual(item.quantity_label, "1.5 kg")
        self.assertTrue(
            OrderStatusEvent.objects.filter(order=order, to_status="pending").exists()
        )

    @mock.patch("Otoosin.paystack.initialize_transaction")
    def test_duplicate_checkout_submission_creates_one_order(self, initialize):
        initialize.side_effect = self.fake_initialize
        token = self.checkout_token()
        first = self.post_checkout(token)
        second = self.post_checkout(token)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(Payment.objects.count(), 1)
        self.assertEqual(
            first.json()["order_reference"], second.json()["order_reference"]
        )

    @mock.patch("Otoosin.paystack.initialize_transaction")
    def test_new_checkout_page_same_cart_reuses_pending_order(self, initialize):
        initialize.side_effect = self.fake_initialize
        token = self.checkout_token()
        first = self.post_checkout(token)
        self.assertEqual(first.status_code, 200)

        # Simulate a browser refresh: a new server checkout token, same cart.
        new_token = self.checkout_token()
        second = self.post_checkout(new_token)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(
            first.json()["order_reference"], second.json()["order_reference"]
        )
        self.assertTrue(second.json().get("resumed"))

    def test_invalid_checkout_creates_no_order_or_payment(self):
        token = self.checkout_token()
        response = self.post_checkout(token, items=[self.line("0.25")])
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(Payment.objects.count(), 0)

    @mock.patch("Otoosin.paystack.initialize_transaction")
    def test_order_history_unchanged_after_catalogue_edit(self, initialize):
        initialize.side_effect = self.fake_initialize
        token = self.checkout_token()
        self.post_checkout(token)
        order = Order.objects.get()
        item = order.items.get()

        self.product.name = "Renamed Product"
        self.product.save(update_fields=["name"])
        self.variant.price = Decimal("9999.00")
        self.variant.save(update_fields=["price"])
        self.doorstep.fee = Decimal("9999.00")
        self.doorstep.save(update_fields=["fee"])

        item.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(item.product_name, "Checkout Product CHK-001")
        self.assertEqual(item.unit_price, Decimal("4800.00"))
        self.assertEqual(order.delivery_fee, Decimal("500.00"))
        self.assertEqual(order.total, Decimal("7700.00"))

    @mock.patch("Otoosin.orders._decrement_stock")
    def test_order_creation_rolls_back_on_stock_failure(self, decrement):
        decrement.side_effect = CheckoutError(
            "Stock failed.", field="items", category="stock"
        )
        token = self.checkout_token()
        response = self.post_checkout(token)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(OrderItem.objects.count(), 0)
        self.assertEqual(Payment.objects.count(), 0)

    @mock.patch("Otoosin.paystack.initialize_transaction")
    def test_guest_confirmation_access_is_protected(self, initialize):
        initialize.side_effect = self.fake_initialize
        token = self.checkout_token()
        self.post_checkout(token)
        order = Order.objects.get()
        url = reverse(
            "Otoosin:order_confirmation_detail",
            kwargs={"reference": order.reference},
        )
        self.assertEqual(self.client.get(url).status_code, 200)

        stranger = Client()
        self.assertEqual(stranger.get(url).status_code, 404)
        self.assertEqual(
            stranger.get(f"{url}?token=wrong-token").status_code, 404
        )
        self.assertEqual(
            stranger.get(f"{url}?token={order.access_token}").status_code, 200
        )


class PaystackInitializationTests(CheckoutTestCase):
    @mock.patch("Otoosin.paystack.initialize_transaction")
    def test_amount_currency_reference_and_secret(self, initialize):
        initialize.side_effect = self.fake_initialize
        token = self.checkout_token()
        response = self.post_checkout(token)
        self.assertEqual(response.status_code, 200)
        order = Order.objects.get()
        payment = order.payments.get()
        kwargs = initialize.call_args.kwargs
        self.assertEqual(kwargs["reference"], payment.provider_reference)
        self.assertEqual(kwargs["amount"], Decimal("7700.00"))
        self.assertEqual(kwargs["currency"], "NGN")
        self.assertEqual(kwargs["email"], "ada@example.com")
        self.assertTrue(kwargs["callback_url"].startswith("https://farm.example.com/"))
        self.assertNotIn(PAYSTACK_SECRET, response.content.decode())
        self.assertNotIn(PAYSTACK_SECRET, json.dumps(response.json()))

    @mock.patch("Otoosin.paystack.initialize_transaction")
    def test_successful_initialization_never_marks_paid(self, initialize):
        initialize.side_effect = self.fake_initialize
        token = self.checkout_token()
        self.post_checkout(token)
        order = Order.objects.get()
        payment = order.payments.get()
        self.assertEqual(payment.status, Payment.Status.PENDING)
        self.assertIsNone(payment.verified_at)
        self.assertEqual(order.status, Order.Status.PENDING)

    @mock.patch("Otoosin.paystack.initialize_transaction")
    def test_provider_rejection_is_safe_and_recoverable(self, initialize):
        from .paystack import PaystackError

        initialize.side_effect = PaystackError(
            "Provider rejected the request.", category="provider_rejected"
        )
        token = self.checkout_token()
        response = self.post_checkout(token)
        self.assertEqual(response.status_code, 502)
        data = response.json()
        self.assertFalse(data["ok"])
        self.assertIn("confirmation_url", data)
        self.assertEqual(Order.objects.count(), 1)
        payment = Payment.objects.get()
        self.assertEqual(payment.status, Payment.Status.FAILED)
        self.assertIsNone(payment.verified_at)

    @mock.patch("Otoosin.paystack.verify_transaction")
    @mock.patch("Otoosin.paystack.initialize_transaction")
    def test_ambiguous_timeout_reconciles_without_duplicate_attempt(
        self, initialize, verify
    ):
        from .paystack import PaystackError

        state = {"calls": 0}

        def initialize_side_effect(**kwargs):
            state["calls"] += 1
            if state["calls"] == 1:
                raise PaystackError(
                    "Timed out.", category="timeout", retryable=True
                )
            return self.fake_initialize(**kwargs)

        initialize.side_effect = initialize_side_effect
        verify.side_effect = PaystackError(
            "Not found.", category="not_found", retryable=False
        )
        token = self.checkout_token()
        first = self.post_checkout(token)
        self.assertEqual(first.status_code, 503)
        self.assertTrue(first.json()["ambiguous"])
        order = Order.objects.get()
        payment = order.payments.get()
        self.assertEqual(payment.status, Payment.Status.PENDING)
        self.assertEqual(Payment.objects.count(), 1)

        second = self.post_checkout(token)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(Payment.objects.count(), 1)
        self.assertEqual(Payment.objects.get().provider_reference, payment.provider_reference)

    @mock.patch("Otoosin.paystack.initialize_transaction")
    def test_unsafe_authorization_url_is_rejected(self, initialize):
        initialize.side_effect = lambda **kwargs: {
            "reference": kwargs["reference"],
            "authorization_url": "http://evil.example/pay",
            "access_code": "code",
        }
        token = self.checkout_token()
        response = self.post_checkout(token)
        self.assertEqual(response.status_code, 502)
        payment = Payment.objects.get()
        self.assertEqual(payment.status, Payment.Status.PENDING)
        self.assertIsNone(payment.verified_at)

    @mock.patch("Otoosin.paystack.initialize_transaction")
    def test_failed_attempt_can_retry_against_same_order(self, initialize):
        order, failed = self.make_order()
        failed.status = Payment.Status.FAILED
        failed.save(update_fields=["status"])
        initialize.side_effect = self.fake_initialize
        self.client.session["order_references"] = [order.reference]
        self.client.session.save()

        response = self.client.post(
            reverse(
                "Otoosin:order_retry_payment",
                kwargs={"reference": order.reference},
            ),
            {"access_token": order.access_token},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(order.payments.count(), 2)
        self.assertEqual(
            order.payments.order_by("-pk").first().status, Payment.Status.PENDING
        )

    @mock.patch("Otoosin.paystack.initialize_transaction")
    def test_paid_attempt_cannot_be_retried(self, initialize):
        order, paid = self.make_order(paid=True)
        initialize.side_effect = self.fake_initialize
        response = self.client.post(
            reverse(
                "Otoosin:order_retry_payment",
                kwargs={"reference": order.reference},
            ),
            {"access_token": order.access_token},
        )
        self.assertEqual(response.status_code, 302)
        initialize.assert_not_called()
        self.assertEqual(order.payments.count(), 1)


class VerificationAndWebhookTests(CheckoutTestCase):
    def test_direct_verification_requires_matching_amount_currency_reference(self):
        order, payment = self.make_order()
        for overrides in (
            {"amount": int(payment.amount * 100) + 1},
            {"currency": "USD"},
            {"reference": "PAY-WRONG"},
        ):
            result = verify_payment(
                payment, provider_data=success_data(payment, **overrides)
            )
            payment.refresh_from_db()
            self.assertNotEqual(payment.status, Payment.Status.PAID, overrides)
            self.assertFalse(result.get("changed", False), overrides)
        result = verify_payment(
            payment, provider_data=success_data(payment, status="failed")
        )
        payment.refresh_from_db()
        self.assertNotEqual(payment.status, Payment.Status.PAID)
        self.assertEqual(payment.status, Payment.Status.FAILED)
        result = verify_payment(payment, provider_data=success_data(payment))
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.PAID)
        self.assertIsNotNone(payment.verified_at)
        self.assertTrue(result["changed"])

    @mock.patch("Otoosin.paystack.verify_transaction")
    def test_browser_return_parameters_alone_cannot_mark_paid(self, verify):
        order, payment = self.make_order()
        verify.return_value = success_data(payment, status="failed")
        response = self.client.get(
            reverse("Otoosin:payment_callback"),
            {"reference": payment.provider_reference, "status": "success"},
        )
        self.assertEqual(response.status_code, 302)
        payment.refresh_from_db()
        self.assertNotEqual(payment.status, Payment.Status.PAID)

    def webhook_post(self, payload, signature=None):
        raw = json.dumps(payload).encode("utf-8")
        if signature is None:
            signature = hmac.new(
                PAYSTACK_SECRET.encode("utf-8"), raw, hashlib.sha512
            ).hexdigest()
        return self.client.post(
            reverse("Otoosin:paystack_webhook"),
            data=raw,
            content_type="application/json",
            HTTP_X_PAYSTACK_SIGNATURE=signature,
        )

    @mock.patch("Otoosin.paystack.verify_transaction")
    def test_valid_webhook_signature_marks_paid_once(self, verify):
        order, payment = self.make_order()
        verify.return_value = success_data(payment)
        payload = {"event": "charge.success", "data": success_data(payment)}
        response = self.webhook_post(payload)
        self.assertEqual(response.status_code, 200)
        payment.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.PAID)
        self.assertIsNotNone(payment.verified_at)
        self.assertEqual(order.status, Order.Status.PENDING)
        self.assertEqual(PaymentWebhookEvent.objects.count(), 1)

    def test_invalid_or_missing_webhook_signature_rejected(self):
        order, payment = self.make_order()
        payload = {"event": "charge.success", "data": success_data(payment)}
        response = self.webhook_post(payload, signature="bad-signature")
        self.assertEqual(response.status_code, 401)
        payment.refresh_from_db()
        self.assertNotEqual(payment.status, Payment.Status.PAID)
        self.assertEqual(PaymentWebhookEvent.objects.count(), 0)

        response = self.webhook_post(payload, signature="")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(PaymentWebhookEvent.objects.count(), 0)

    @mock.patch("Otoosin.paystack.verify_transaction")
    def test_duplicate_webhook_is_idempotent(self, verify):
        order, payment = self.make_order()
        verify.return_value = success_data(payment)
        payload = {"event": "charge.success", "data": success_data(payment)}
        first = self.webhook_post(payload)
        second = self.webhook_post(payload)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(PaymentWebhookEvent.objects.count(), 1)
        self.assertEqual(
            AuditEvent.objects.filter(action="payment.verified_paid").count(), 1
        )

    @mock.patch("Otoosin.paystack.verify_transaction")
    def test_delayed_failure_cannot_downgrade_paid(self, verify):
        order, payment = self.make_order(paid=True)
        failure = success_data(payment, status="failed", gateway_response="Declined")
        payload = {"event": "charge.failed", "data": failure}
        response = self.webhook_post(payload)
        self.assertEqual(response.status_code, 200)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.PAID)
        verify.assert_not_called()

    @mock.patch("Otoosin.paystack.verify_transaction")
    def test_webhook_amount_mismatch_is_rejected(self, verify):
        order, payment = self.make_order()
        verify.return_value = success_data(
            payment, amount=int(payment.amount * 100) + 100
        )
        payload = {
            "event": "charge.success",
            "data": success_data(
                payment, amount=int(payment.amount * 100) + 100
            ),
        }
        response = self.webhook_post(payload)
        self.assertEqual(response.status_code, 200)
        payment.refresh_from_db()
        self.assertNotEqual(payment.status, Payment.Status.PAID)
        self.assertEqual(payment.failure_category, "verification_mismatch")

    @mock.patch("Otoosin.paystack.verify_transaction")
    def test_webhook_failure_event_with_mismatched_amount_is_ignored(self, verify):
        order, payment = self.make_order()
        payload = {
            "event": "charge.failed",
            "data": success_data(
                payment,
                status="failed",
                amount=int(payment.amount * 100) + 100,
            ),
        }
        response = self.webhook_post(payload)
        self.assertEqual(response.status_code, 200)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.PENDING)

    @mock.patch("Otoosin.paystack.verify_transaction")
    def test_direct_verification_and_webhook_race_produce_one_paid_transition(
        self, verify
    ):
        order, payment = self.make_order()
        verify.return_value = success_data(payment)
        verify_payment(payment, provider_data=success_data(payment))
        payload = {"event": "charge.success", "data": success_data(payment)}
        response = self.webhook_post(payload)
        self.assertEqual(response.status_code, 200)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.PAID)
        self.assertEqual(
            AuditEvent.objects.filter(action="payment.verified_paid").count(), 1
        )

    @mock.patch("Otoosin.paystack.verify_transaction")
    def test_transient_webhook_failure_is_retryable(self, verify):
        from .paystack import PaystackError

        order, payment = self.make_order()
        verify.side_effect = PaystackError(
            "Timed out.", category="timeout", retryable=True
        )
        payload = {"event": "charge.success", "data": success_data(payment)}
        response = self.webhook_post(payload)
        self.assertEqual(response.status_code, 503)
        event = PaymentWebhookEvent.objects.get()
        self.assertEqual(event.processing_status, "failed")
        payment.refresh_from_db()
        self.assertNotEqual(payment.status, Payment.Status.PAID)

    def test_duplicate_paid_payments_are_blocked(self):
        order, first = self.make_order()
        second = Payment.objects.create(
            order=order,
            provider_reference="PAY-SECOND",
            amount=order.total,
            currency="NGN",
            status=Payment.Status.PENDING,
        )
        verify_payment(first, provider_data=success_data(first))
        result = verify_payment(second, provider_data=success_data(second))
        second.refresh_from_db()
        first.refresh_from_db()
        self.assertEqual(first.status, Payment.Status.PAID)
        self.assertEqual(second.status, Payment.Status.PENDING)
        self.assertTrue(result["conflict"])
        self.assertEqual(second.failure_category, "possible_duplicate_charge")


class CartClearingTests(CheckoutTestCase):
    @mock.patch("Otoosin.paystack.initialize_transaction")
    def test_no_clear_instruction_before_verified_payment(self, initialize):
        initialize.side_effect = self.fake_initialize
        token = self.checkout_token()
        self.post_checkout(token)
        order = Order.objects.get()
        url = reverse(
            "Otoosin:order_confirmation_detail",
            kwargs={"reference": order.reference},
        )
        response = self.client.get(f"{url}?token={order.access_token}")
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["clear_payload"])
        self.assertNotContains(response, "data-clear-cart=")

    @mock.patch("Otoosin.paystack.initialize_transaction")
    def test_verified_payment_emits_matching_cart_cleanup_payload(self, initialize):
        initialize.side_effect = self.fake_initialize
        token = self.checkout_token()
        self.post_checkout(token)
        order = Order.objects.get()
        payment = order.payments.get()
        verify_payment(payment, provider_data=success_data(payment))

        url = reverse(
            "Otoosin:order_confirmation_detail",
            kwargs={"reference": order.reference},
        )
        response = self.client.get(f"{url}?token={order.access_token}")
        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.context["clear_payload"])
        item = order.items.get()
        self.assertEqual(payload["reference"], order.reference)
        self.assertEqual(
            payload["lines"],
            [
                {
                    "key": f"{self.product.slug}__{self.variant.pk}",
                    "quantity": "1.5",
                }
            ],
        )
        self.assertContains(response, "data-clear-cart=")

    @mock.patch("Otoosin.paystack.initialize_transaction")
    def test_confirmation_remains_available_without_cart_cleanup(self, initialize):
        initialize.side_effect = self.fake_initialize
        token = self.checkout_token()
        self.post_checkout(token)
        order = Order.objects.get()
        payment = order.payments.get()
        verify_payment(payment, provider_data=success_data(payment))

        # A different tab with the secure token still sees the paid order.
        other_tab = Client()
        url = reverse(
            "Otoosin:order_confirmation_detail",
            kwargs={"reference": order.reference},
        )
        response = other_tab.get(f"{url}?token={order.access_token}")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Payment verified")


class StaffOrderTests(CheckoutTestCase):
    def setUp(self):
        super().setUp()
        provision_staff_roles()
        User = get_user_model()
        self.owner = User.objects.create_user(
            username="owner",
            email="owner@example.com",
            password="strong-pass-123",
            is_staff=True,
            is_superuser=True,
        )
        self.manager = User.objects.create_user(
            username="manager",
            email="manager@example.com",
            password="strong-pass-123",
            is_staff=True,
        )
        self.manager.groups.add(Group.objects.get(name="Manager"))
        self.fulfilment = User.objects.create_user(
            username="fulfilment",
            email="fulfilment@example.com",
            password="strong-pass-123",
            is_staff=True,
        )
        self.fulfilment.groups.add(Group.objects.get(name="Fulfilment"))
        self.support = User.objects.create_user(
            username="support",
            email="support@example.com",
            password="strong-pass-123",
            is_staff=True,
        )
        self.support.groups.add(Group.objects.get(name="Support"))

    def test_anonymous_and_unauthorised_staff_are_denied(self):
        self.assertEqual(self.client.get("/staff/orders/").status_code, 302)
        self.client.force_login(self.support)
        self.assertEqual(self.client.get("/staff/orders/").status_code, 403)
        order, _ = self.make_order()
        detail = reverse(
            "Otoosin:staff_order_detail",
            kwargs={"reference": order.reference},
        )
        self.assertEqual(self.client.get(detail).status_code, 403)

        non_staff = get_user_model().objects.create_user(
            username="customer", password="strong-pass-123"
        )
        self.client.force_login(non_staff)
        self.assertEqual(self.client.get("/staff/orders/").status_code, 403)

    def test_fulfilment_and_manager_can_view_and_update_status(self):
        order, _ = self.make_order()
        detail = reverse(
            "Otoosin:staff_order_detail",
            kwargs={"reference": order.reference},
        )
        for user in (self.fulfilment, self.manager, self.owner):
            self.client.force_login(user)
            self.assertEqual(self.client.get("/staff/orders/").status_code, 200)
            self.assertEqual(self.client.get(detail).status_code, 200)

        self.client.force_login(self.fulfilment)
        response = self.client.post(detail, {"status": "completed"})
        self.assertEqual(response.status_code, 302)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.COMPLETED)
        self.assertIsNotNone(order.completed_at)
        event = order.status_events.get()
        self.assertEqual(event.actor, self.fulfilment)
        self.assertEqual(event.from_status, Order.Status.PENDING)
        self.assertEqual(event.to_status, Order.Status.COMPLETED)
        self.assertTrue(
            AuditEvent.objects.filter(action="order.status_changed").exists()
        )

    def test_status_update_is_post_only_and_csrf_protected(self):
        order, _ = self.make_order()
        detail = reverse(
            "Otoosin:staff_order_detail",
            kwargs={"reference": order.reference},
        )
        self.client.force_login(self.owner)
        self.client.get(detail)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PENDING)

        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.owner)
        response = csrf_client.post(detail, {"status": "cancelled"})
        self.assertEqual(response.status_code, 403)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PENDING)

    def test_staff_status_change_never_changes_payment_truth(self):
        order, payment = self.make_order(paid=True)
        detail = reverse(
            "Otoosin:staff_order_detail",
            kwargs={"reference": order.reference},
        )
        self.client.force_login(self.owner)
        response = self.client.post(
            detail, {"status": "cancelled", "reason": "Customer request"}
        )
        self.assertEqual(response.status_code, 302)
        order.refresh_from_db()
        payment.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CANCELLED)
        self.assertEqual(payment.status, Payment.Status.PAID)
        self.assertIsNotNone(payment.verified_at)
        event = order.status_events.get()
        self.assertIn("refund", event.note.lower())

    def test_staff_cannot_mark_payment_paid_or_edit_totals(self):
        order, payment = self.make_order()
        detail = reverse(
            "Otoosin:staff_order_detail",
            kwargs={"reference": order.reference},
        )
        self.client.force_login(self.owner)
        response = self.client.post(
            detail,
            {
                "status": "paid",
                "total": "1.00",
                "subtotal": "1.00",
                "delivery_fee": "0.00",
            },
        )
        self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        payment.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PENDING)
        self.assertEqual(order.total, Decimal("5000.00"))
        self.assertEqual(payment.status, Payment.Status.PENDING)
        self.assertIsNone(payment.verified_at)

    def test_search_filters_and_pagination_use_database(self):
        self.client.force_login(self.owner)
        order, payment = self.make_order(
            reference="OF-SEARCH1", phone="+2348031112222"
        )
        other, _ = self.make_order(
            reference="OF-OTHER2", paid=True, status=Order.Status.COMPLETED
        )
        for index in range(30):
            self.make_order(reference=f"OF-PAGE{index:02d}")

        response = self.client.get("/staff/orders/", {"q": "SEARCH1"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "OF-SEARCH1")
        self.assertNotContains(response, "OF-OTHER2")

        response = self.client.get("/staff/orders/", {"payment": "paid"})
        self.assertContains(response, "OF-OTHER2")
        self.assertNotContains(response, "OF-SEARCH1")

        response = self.client.get(
            "/staff/orders/", {"status": "pending", "page": 2}
        )
        self.assertContains(response, "OF-SEARCH1")
        self.assertNotContains(response, "OF-OTHER2")

        response = self.client.get("/staff/orders/", {"page": 2})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["page_obj"].object_list), 7)

    def test_empty_state_and_dashboard_metrics_are_database_backed(self):
        self.client.force_login(self.owner)
        response = self.client.get("/staff/orders/")
        self.assertContains(response, "No orders yet")

        pending, _ = self.make_order()
        paid, _ = self.make_order(paid=True)
        response = self.client.get("/staff/")
        self.assertEqual(response.status_code, 200)
        summary = response.context["order_summary"]
        self.assertEqual(summary["total"], 2)
        self.assertEqual(summary["pending"], 2)
        self.assertEqual(summary["paid"], 1)

    def test_invalid_date_filter_does_not_crash(self):
        self.client.force_login(self.owner)
        self.make_order()
        response = self.client.get(
            "/staff/orders/", {"date_from": "not-a-date", "date_to": "also-bad"}
        )
        self.assertEqual(response.status_code, 200)
