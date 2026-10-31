import io
import json
from decimal import Decimal
from urllib.error import HTTPError
from unittest import mock

from django.test import TestCase, override_settings
from django.utils import timezone

from .models import Order, OrderItem, Payment
from .payments import verify_payment
from .whatsapp import (
    normalize_phone_number,
    send_order_notification,
    send_template_message,
)


BASE_SETTINGS = {
    "WHATSAPP_ENABLED": True,
    "WHATSAPP_ACCESS_TOKEN": "test-token",
    "WHATSAPP_PHONE_NUMBER_ID": "1316981358175375",
    "WHATSAPP_GRAPH_API_VERSION": "v25.0",
    "WHATSAPP_MESSAGE_TEMPLATE": "otoosin_new_order_admin",
    "WHATSAPP_TEMPLATE_LANGUAGE": "en_US",
    "WHATSAPP_TIMEOUT_SECONDS": 5,
    "WHATSAPP_ADMIN_RECIPIENTS": ["08031234567"],
    "WHATSAPP_TEMPLATE_HEADER_FIELDS": [],
    "WHATSAPP_TEMPLATE_URL_BUTTON_FIELD": "",
    "WHATSAPP_TEMPLATE_URL_BUTTON_INDEX": 0,
    "SITE_URL": "https://farm.example.com",
}


class WhatsAppServiceTests(TestCase):
    def api_response(self, payload=None, status=200):
        response = mock.Mock()
        response.status = status
        response.read.return_value = json.dumps(
            payload or {"messages": [{"id": "wamid.test"}]}
        ).encode("utf-8")
        return response

    @override_settings(WHATSAPP_ENABLED=False)
    @mock.patch("Otoosin.whatsapp.urlopen")
    def test_disabled_does_not_make_external_request(self, urlopen):
        result = send_template_message("+2348031234567")
        self.assertEqual(result.category, "disabled")
        urlopen.assert_not_called()

    @override_settings(
        WHATSAPP_ENABLED=True,
        WHATSAPP_ACCESS_TOKEN="",
        WHATSAPP_PHONE_NUMBER_ID="",
        WHATSAPP_MESSAGE_TEMPLATE="",
    )
    @mock.patch("Otoosin.whatsapp.urlopen")
    def test_missing_configuration_is_safe(self, urlopen):
        result = send_template_message("+2348031234567")
        self.assertEqual(result.category, "not_configured")
        urlopen.assert_not_called()

    @override_settings(**BASE_SETTINGS)
    @mock.patch("Otoosin.whatsapp.urlopen")
    def test_successful_response_builds_template_payload(self, urlopen):
        urlopen.return_value.__enter__.return_value = self.api_response()

        result = send_template_message(
            "0803 123 4567",
            body_parameters=["Order alert", "OF-ABC123"],
        )

        self.assertTrue(result.accepted)
        self.assertEqual(result.message_id, "wamid.test")
        request = urlopen.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(payload["to"], "2348031234567")
        self.assertEqual(payload["messaging_product"], "whatsapp")
        self.assertEqual(payload["type"], "template")
        self.assertEqual(
            payload["template"]["components"][0]["parameters"],
            [
                {"type": "text", "text": "Order alert"},
                {"type": "text", "text": "OF-ABC123"},
            ],
        )
        self.assertEqual(
            request.headers["Authorization"], "Bearer " + "test-token"
        )
        self.assertIn(
            "/v25.0/1316981358175375/messages", request.full_url
        )

    @override_settings(
        **{**BASE_SETTINGS, "WHATSAPP_GRAPH_API_VERSION": "vv25.0"}
    )
    @mock.patch("Otoosin.whatsapp.urlopen")
    def test_graph_version_prefix_is_normalized(self, urlopen):
        urlopen.return_value.__enter__.return_value = self.api_response()
        send_template_message("+2348031234567")
        request = urlopen.call_args.args[0]
        self.assertIn("/v25.0/1316981358175375/messages", request.full_url)
        self.assertNotIn("vv25.0", request.full_url)

    @override_settings(**BASE_SETTINGS)
    @mock.patch("Otoosin.whatsapp.urlopen")
    def test_meta_rejection_is_reported_without_secret(self, urlopen):
        error_body = io.BytesIO(
            b'{"error":{"message":"Template is not approved",'
            b'"code":132001,"error_subcode":2494073,'
            b'"fbtrace_id":"AbCdEf"}}'
        )
        urlopen.side_effect = HTTPError(
            "https://graph.facebook.com", 400, "Bad request", {}, error_body
        )

        result = send_template_message("+2348031234567")

        self.assertEqual(result.category, "api_rejected")
        self.assertEqual(result.status_code, 400)
        self.assertEqual(result.error_code, 132001)
        self.assertEqual(result.error_subcode, 2494073)
        self.assertEqual(result.trace_id, "AbCdEf")
        self.assertIn("Template is not approved", result.message)
        self.assertNotIn("test-token", result.message)

    @override_settings(**BASE_SETTINGS)
    @mock.patch("Otoosin.whatsapp.urlopen")
    def test_invalid_token_failure_is_visible(self, urlopen):
        error_body = io.BytesIO(
            b'{"error":{"message":"Invalid OAuth access token",'
            b'"code":190,"fbtrace_id":"trace-1"}}'
        )
        urlopen.side_effect = HTTPError(
            "https://graph.facebook.com", 401, "Unauthorized", {}, error_body
        )

        result = send_template_message("+2348031234567")

        self.assertFalse(result.ok)
        self.assertFalse(result.accepted)
        self.assertEqual(result.category, "api_rejected")
        self.assertEqual(result.status_code, 401)
        self.assertEqual(result.error_code, 190)

    @override_settings(
        **{**BASE_SETTINGS, "WHATSAPP_TIMEOUT_SECONDS": 5}
    )
    @mock.patch("Otoosin.whatsapp.urlopen", side_effect=TimeoutError)
    def test_timeout_is_reported(self, urlopen):
        result = send_template_message("+2348031234567")
        self.assertEqual(result.category, "timeout")
        urlopen.assert_called_once()

    @override_settings(**BASE_SETTINGS)
    @mock.patch("Otoosin.whatsapp.urlopen")
    def test_invalid_recipient_is_rejected_before_request(self, urlopen):
        result = send_template_message("not-a-phone")
        self.assertEqual(result.category, "invalid_recipient")
        urlopen.assert_not_called()

    def test_recipient_normalization(self):
        self.assertEqual(normalize_phone_number("0803 123 4567"), "2348031234567")
        self.assertEqual(normalize_phone_number("+234 803 123 4567"), "2348031234567")
        self.assertEqual(normalize_phone_number("002348031234567"), "2348031234567")
        with self.assertRaises(ValueError):
            normalize_phone_number("0803-12")
        with self.assertRaises(ValueError):
            normalize_phone_number("phone")

    @override_settings(
        **{
            **BASE_SETTINGS,
            "WHATSAPP_TEMPLATE_HEADER_FIELDS": ["alert_title"],
            "WHATSAPP_TEMPLATE_URL_BUTTON_FIELD": "order_reference",
        }
    )
    @mock.patch("Otoosin.whatsapp.urlopen")
    def test_header_and_url_button_components(self, urlopen):
        urlopen.return_value.__enter__.return_value = self.api_response()
        order = self.make_order(fields=["order_reference"])

        result = send_order_notification(order)

        self.assertTrue(result.accepted)
        payload = json.loads(urlopen.call_args.args[0].data.decode("utf-8"))
        components = payload["template"]["components"]
        self.assertEqual(components[0]["type"], "header")
        self.assertEqual(
            components[0]["parameters"][0]["text"],
            "O'Toosin Farms new order alert",
        )
        self.assertEqual(components[1]["type"], "body")
        self.assertEqual(components[1]["parameters"][0]["text"], order.reference)
        self.assertEqual(components[2]["type"], "button")
        self.assertEqual(components[2]["sub_type"], "url")
        self.assertEqual(components[2]["index"], "0")
        self.assertEqual(
            components[2]["parameters"][0]["text"], order.reference
        )

    def make_order(
        self,
        *,
        fields=None,
        reference="OF-WA123456",
        receive_method=Order.ReceiveMethod.DOORSTEP,
        items=None,
        paid=True,
    ):
        order = Order.objects.create(
            reference=reference,
            access_token=f"wa-{reference}-access-token",
            customer_name="Ada Okafor",
            customer_phone="08031234567",
            customer_email="ada@example.com",
            customer_notes="Call before arrival",
            receive_method=receive_method,
            location_name="Camp"
            if receive_method != Order.ReceiveMethod.PICKUP
            else "Mummy-D Stores",
            location_address="Bode Olude"
            if receive_method != Order.ReceiveMethod.PICKUP
            else "12 Ijaiye Road, Abeokuta",
            location_instructions="Collect at the front desk"
            if receive_method == Order.ReceiveMethod.PICKUP
            else "Gate opens at 7am",
            delivery_address="12 Camp Road, Abeokuta"
            if receive_method != Order.ReceiveMethod.PICKUP
            else "",
            landmark="Beside the filling station"
            if receive_method != Order.ReceiveMethod.PICKUP
            else "",
            city="Abeokuta",
            state="Ogun",
            subtotal=Decimal("4800.00"),
            delivery_fee=Decimal("0.00")
            if receive_method == Order.ReceiveMethod.PICKUP
            else Decimal("500.00"),
            total=Decimal("4800.00")
            if receive_method == Order.ReceiveMethod.PICKUP
            else Decimal("5300.00"),
            currency="NGN",
        )
        for name, variant, quantity, quantity_label, unit_price, line_total in (
            items
            or [
                (
                    "Fresh Chicken",
                    "1kg",
                    Decimal("1"),
                    "1 kg",
                    Decimal("4800.00"),
                    Decimal("4800.00"),
                )
            ]
        ):
            OrderItem.objects.create(
                order=order,
                product_name=name,
                variant_label=variant,
                quantity=quantity,
                quantity_label=quantity_label,
                unit_price=unit_price,
                line_total=line_total,
                currency="NGN",
            )
        if paid:
            Payment.objects.create(
                order=order,
                provider_reference=f"{reference}-PAY",
                amount=order.total,
                currency="NGN",
                status=Payment.Status.PAID,
                verified_at=timezone.now(),
            )
        return order

    @override_settings(
        **{
            **BASE_SETTINGS,
            "WHATSAPP_TEMPLATE_BODY_FIELDS": [
                "alert_title",
                "order_reference",
                "customer_name",
                "customer_phone",
                "items",
                "total",
                "currency",
                "fulfilment",
                "admin_url",
            ],
        }
    )
    @mock.patch("Otoosin.whatsapp.urlopen")
    def test_order_notification_contains_order_data_and_staff_url(self, urlopen):
        urlopen.return_value.__enter__.return_value = self.api_response()
        result = send_order_notification(self.make_order())

        self.assertTrue(result.accepted)
        payload = json.loads(urlopen.call_args.args[0].data.decode("utf-8"))
        parameters = payload["template"]["components"][0]["parameters"]
        values = [parameter["text"] for parameter in parameters]
        self.assertEqual(values[0], "O'Toosin Farms new order alert")
        self.assertEqual(values[1], "OF-WA123456")
        self.assertEqual(values[2], "Ada Okafor")
        self.assertEqual(values[3], "08031234567")
        self.assertIn("Fresh Chicken (1kg)", values[4])
        self.assertEqual(values[5], "NGN 5,300.00")
        self.assertEqual(values[6], "NGN")
        self.assertEqual(values[7], "DELIVERY (doorstep)")
        self.assertEqual(
            values[8],
            "https://farm.example.com/staff/orders/OF-WA123456/",
        )

    @override_settings(
        **{
            **BASE_SETTINGS,
            "WHATSAPP_TEMPLATE_BODY_FIELDS": [
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
            ],
        }
    )
    @mock.patch("Otoosin.whatsapp.urlopen")
    def test_delivery_message_contains_saved_details_and_all_products(self, urlopen):
        urlopen.return_value.__enter__.return_value = self.api_response()
        order = self.make_order(
            items=[
                (
                    "Fresh Chicken",
                    "1kg",
                    Decimal("1"),
                    "1 kg",
                    Decimal("1800.00"),
                    Decimal("1800.00"),
                ),
                (
                    "Goat Meat",
                    "2kg",
                    Decimal("1"),
                    "2 kg",
                    Decimal("3000.00"),
                    Decimal("3000.00"),
                ),
            ]
        )

        send_order_notification(order)

        payload = json.loads(urlopen.call_args.args[0].data.decode("utf-8"))
        values = [
            parameter["text"]
            for parameter in payload["template"]["components"][0]["parameters"]
        ]
        (
            reference,
            placed_at,
            status,
            customer_name,
            customer_phone,
            customer_email,
            customer_notes,
            items,
            subtotal,
            delivery_fee,
            total,
            currency,
            payment_status,
            payment_method,
            fulfilment,
            fulfilment_location,
            delivery_address,
            delivery_instructions,
        ) = values
        self.assertEqual(reference, "OF-WA123456")
        self.assertEqual(
            placed_at,
            timezone.localtime(order.placed_at).strftime("%d %b %Y, %I:%M %p %Z"),
        )
        self.assertEqual(status, "Pending")
        self.assertEqual(customer_name, "Ada Okafor")
        self.assertEqual(customer_phone, "08031234567")
        self.assertEqual(customer_email, "ada@example.com")
        self.assertEqual(customer_notes, "Call before arrival")
        self.assertIn("Fresh Chicken (1kg)", items)
        self.assertIn("Goat Meat (2kg)", items)
        self.assertIn("Unit: NGN 1,800.00", items)
        self.assertIn("Line: NGN 3,000.00", items)
        self.assertEqual(subtotal, "NGN 4,800.00")
        self.assertEqual(delivery_fee, "NGN 500.00")
        self.assertEqual(total, "NGN 5,300.00")
        self.assertEqual(currency, "NGN")
        self.assertEqual(payment_status, "Paid (verified by Paystack)")
        self.assertEqual(payment_method, "Paystack")
        self.assertEqual(fulfilment, "DELIVERY (doorstep)")
        self.assertEqual(fulfilment_location, "Camp")
        self.assertIn("12 Camp Road, Abeokuta", delivery_address)
        self.assertIn("Beside the filling station", delivery_address)
        self.assertEqual(delivery_instructions, "Gate opens at 7am")

    @override_settings(
        **{
            **BASE_SETTINGS,
            "WHATSAPP_TEMPLATE_BODY_FIELDS": [
                "fulfilment",
                "fulfilment_location",
                "delivery_address",
                "delivery_fee",
                "delivery_instructions",
            ],
        }
    )
    @mock.patch("Otoosin.whatsapp.urlopen")
    def test_pickup_message_has_location_and_no_misleading_delivery(self, urlopen):
        urlopen.return_value.__enter__.return_value = self.api_response()
        order = self.make_order(
            reference="OF-WA654321",
            receive_method=Order.ReceiveMethod.PICKUP,
        )
        send_order_notification(order)

        payload = json.loads(urlopen.call_args.args[0].data.decode("utf-8"))
        values = [
            parameter["text"]
            for parameter in payload["template"]["components"][0]["parameters"]
        ]
        self.assertEqual(values[0], "PICKUP")
        self.assertIn("Mummy-D Stores", values[1])
        self.assertIn("12 Ijaiye Road, Abeokuta", values[1])
        self.assertEqual(values[2], "Not applicable (pickup)")
        self.assertEqual(values[3], "Not applicable (pickup)")
        self.assertEqual(values[4], "Collect at the front desk")

    @override_settings(
        **{
            **BASE_SETTINGS,
            "WHATSAPP_TEMPLATE_BODY_FIELDS": ["items"],
        }
    )
    @mock.patch("Otoosin.whatsapp.urlopen")
    def test_oversized_order_data_is_reported_not_truncated(self, urlopen):
        order = self.make_order(
            items=[
                (
                    "X" * 1100,
                    "1kg",
                    Decimal("1"),
                    "1 kg",
                    Decimal("100.00"),
                    Decimal("4800.00"),
                )
            ]
        )
        result = send_order_notification(order)
        self.assertEqual(result.category, "payload_too_long")
        urlopen.assert_not_called()

    @override_settings(
        **{
            **BASE_SETTINGS,
            "WHATSAPP_TEMPLATE_BODY_FIELDS": [],
        }
    )
    @mock.patch("Otoosin.whatsapp.urlopen")
    def test_order_notification_requires_explicit_template_field_order(self, urlopen):
        result = send_order_notification(self.make_order())
        self.assertEqual(result.category, "template_not_configured")
        urlopen.assert_not_called()

    @override_settings(
        **{
            **BASE_SETTINGS,
            "WHATSAPP_TEMPLATE_BODY_FIELDS": ["not_a_real_field"],
        }
    )
    @mock.patch("Otoosin.whatsapp.urlopen")
    def test_unknown_template_field_is_reported(self, urlopen):
        result = send_order_notification(self.make_order())
        self.assertEqual(result.category, "invalid_configuration")
        urlopen.assert_not_called()


class WhatsAppPaymentHookTests(TestCase):
    def make_paid_attempt(self):
        order = Order.objects.create(
            reference="OF-WA987654",
            access_token="wa-payment-access-token",
            customer_name="Ada Okafor",
            customer_phone="08031234567",
            receive_method=Order.ReceiveMethod.PICKUP,
            subtotal=Decimal("1000.00"),
            delivery_fee=Decimal("0.00"),
            total=Decimal("1000.00"),
            currency="NGN",
        )
        payment = Payment.objects.create(
            order=order,
            provider_reference="OF-WA987654-PAY",
            amount=Decimal("1000.00"),
            currency="NGN",
        )
        return order, payment

    def provider_data(self, payment):
        return {
            "status": "success",
            "reference": payment.provider_reference,
            "amount": 100000,
            "currency": "NGN",
        }

    @override_settings(
        WHATSAPP_ORDER_NOTIFICATIONS_ENABLED=True,
        WHATSAPP_ENABLED=True,
    )
    @mock.patch(
        "Otoosin.notifications.whatsapp.send_order_notification",
        return_value=mock.Mock(accepted=True),
    )
    def test_duplicate_payment_processing_notifies_once(self, notify):
        order, payment = self.make_paid_attempt()
        with self.captureOnCommitCallbacks(execute=True):
            verify_payment(payment, provider_data=self.provider_data(payment))
            payment.refresh_from_db()
            verify_payment(payment, provider_data=self.provider_data(payment))

        self.assertEqual(notify.call_count, 1)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.PAID)

    @override_settings(
        WHATSAPP_ORDER_NOTIFICATIONS_ENABLED=True,
        WHATSAPP_ENABLED=True,
    )
    @mock.patch(
        "Otoosin.notifications.whatsapp.send_order_notification",
        side_effect=RuntimeError("secondary provider failed"),
    )
    def test_whatsapp_failure_does_not_break_verified_payment(self, notify):
        order, payment = self.make_paid_attempt()
        with self.captureOnCommitCallbacks(execute=True):
            result = verify_payment(
                payment, provider_data=self.provider_data(payment)
            )

        self.assertTrue(result["changed"])
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.PAID)
        notify.assert_called_once()


    @override_settings(
        WHATSAPP_ORDER_NOTIFICATIONS_ENABLED=False, WHATSAPP_ENABLED=True
    )
    @mock.patch("Otoosin.notifications.whatsapp.send_order_notification")
    def test_whatsapp_order_hook_is_inactive_by_default(self, notify):
        order, payment = self.make_paid_attempt()
        with self.captureOnCommitCallbacks(execute=True):
            verify_payment(payment, provider_data=self.provider_data(payment))
        notify.assert_not_called()
