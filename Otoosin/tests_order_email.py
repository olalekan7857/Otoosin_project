from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client, TestCase, override_settings
from django.utils import timezone
from django.utils.formats import date_format

from .models import (
    AuditEvent,
    EmailDelivery,
    Order,
    OrderItem,
    OrderNotificationRecipient,
    Payment,
)
from .permissions import provision_staff_roles
from .payments import verify_payment
from .transactional_emails import order_notification_email


RESEND_OK = {
    "RESEND_API_KEY": "test-resend-key",
    "RESEND_FROM_EMAIL": "O’Toosin Farms <no-reply@example.com>",
    "SITE_URL": "https://farm.example.com",
}


def make_order(
    *,
    reference="OF-EMAIL1234",
    receive_method=Order.ReceiveMethod.DOORSTEP,
    notes="Ring the bell at the gate",
    paid=True,
):
    is_pickup = receive_method == Order.ReceiveMethod.PICKUP
    order = Order.objects.create(
        reference=reference,
        access_token=f"email-{reference}-token",
        customer_name="Ada Okafor",
        customer_phone="08031234567",
        customer_email="ada@example.com",
        customer_notes=notes,
        receive_method=receive_method,
        location_name="Mummy-D Stores" if is_pickup else "Camp",
        location_address=(
            "12 Ijaiye Road, Abeokuta" if is_pickup else "Camp area"
        ),
        location_instructions=(
            "Collect at the front desk" if is_pickup else "Use the service gate"
        ),
        delivery_address="" if is_pickup else "14 Farm Settlement Road",
        landmark="" if is_pickup else "Opposite the sawmill",
        city="Abeokuta",
        state="Ogun",
        subtotal=Decimal("4800.00"),
        delivery_fee=Decimal("0.00") if is_pickup else Decimal("500.00"),
        total=Decimal("4800.00") if is_pickup else Decimal("5300.00"),
        currency="NGN",
    )
    OrderItem.objects.create(
        order=order,
        product_name="Fresh Chicken",
        variant_label="1kg",
        sku="CHK-1KG",
        quantity=Decimal("1"),
        quantity_label="1 kg",
        unit_price=Decimal("1800.00"),
        line_total=Decimal("1800.00"),
        currency="NGN",
    )
    OrderItem.objects.create(
        order=order,
        product_name="Goat Meat",
        variant_label="2kg",
        sku="GOAT-2KG",
        quantity=Decimal("1"),
        quantity_label="2 kg",
        unit_price=Decimal("3000.00"),
        line_total=Decimal("3000.00"),
        currency="NGN",
    )
    payment = Payment.objects.create(
        order=order,
        provider_reference=f"{reference}-PAY",
        amount=order.total,
        currency="NGN",
        status=Payment.Status.PAID if paid else Payment.Status.INITIATED,
        verified_at=timezone.now() if paid else None,
    )
    return order, payment


class RecipientManagementTests(TestCase):
    def setUp(self):
        provision_staff_roles()
        User = get_user_model()
        self.owner = User.objects.create_user(
            username="owner",
            password="strong-pass-123",
            is_staff=True,
            is_superuser=True,
        )
        self.support = User.objects.create_user(
            username="support", password="strong-pass-123", is_staff=True
        )
        self.support.groups.add(Group.objects.get(name="Support"))
        self.client = Client()

    def test_owner_can_add_normalized_recipient_without_creating_user(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            "/staff/settings/",
            {"action": "recipient_add", "email": "Owner@Example.com"},
        )
        self.assertRedirects(response, "/staff/settings/")
        recipient = OrderNotificationRecipient.objects.get()
        self.assertEqual(recipient.email, "owner@example.com")
        self.assertTrue(recipient.is_active)
        self.assertFalse(
            get_user_model().objects.filter(email__iexact="owner@example.com").exists()
        )
        self.assertTrue(
            AuditEvent.objects.filter(
                action="order_notification_recipient_added"
            ).exists()
        )

    def test_invalid_and_case_insensitive_duplicate_are_rejected(self):
        self.client.force_login(self.owner)
        self.client.post(
            "/staff/settings/",
            {"action": "recipient_add", "email": "owner@example.com"},
        )
        response = self.client.post(
            "/staff/settings/",
            {"action": "recipient_add", "email": "OWNER@EXAMPLE.COM"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already configured")
        self.assertEqual(OrderNotificationRecipient.objects.count(), 1)

        response = self.client.post(
            "/staff/settings/",
            {"action": "recipient_add", "email": "not-an-email"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(OrderNotificationRecipient.objects.count(), 1)

    def test_recipients_can_be_disabled_reenabled_and_removed(self):
        self.client.force_login(self.owner)
        recipient = OrderNotificationRecipient.objects.create(
            email="manager@example.com"
        )
        response = self.client.post(
            "/staff/settings/",
            {"action": "recipient_toggle", "recipient_id": recipient.pk},
        )
        self.assertRedirects(response, "/staff/settings/")
        recipient.refresh_from_db()
        self.assertFalse(recipient.is_active)

        self.client.post(
            "/staff/settings/",
            {"action": "recipient_toggle", "recipient_id": recipient.pk},
        )
        recipient.refresh_from_db()
        self.assertTrue(recipient.is_active)

        self.client.post(
            "/staff/settings/",
            {"action": "recipient_remove", "recipient_id": recipient.pk},
        )
        self.assertFalse(
            OrderNotificationRecipient.objects.filter(pk=recipient.pk).exists()
        )
        self.assertTrue(
            AuditEvent.objects.filter(
                action="order_notification_recipient_removed"
            ).exists()
        )

    def test_multiple_recipients_are_supported(self):
        OrderNotificationRecipient.objects.create(email="a@example.com")
        OrderNotificationRecipient.objects.create(email="b@example.com")
        self.assertEqual(OrderNotificationRecipient.objects.count(), 2)

    def test_unauthorized_and_anonymous_users_cannot_manage_recipients(self):
        self.client.post(
            "/staff/settings/",
            {"action": "recipient_add", "email": "blocked@example.com"},
        )
        self.assertFalse(OrderNotificationRecipient.objects.exists())

        self.client.force_login(self.support)
        response = self.client.post(
            "/staff/settings/",
            {"action": "recipient_add", "email": "blocked@example.com"},
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(OrderNotificationRecipient.objects.exists())

    def test_warning_state_appears_only_without_active_recipients(self):
        self.client.force_login(self.owner)
        response = self.client.get("/staff/settings/")
        self.assertContains(
            response,
            "No active order notification email addresses are configured.",
        )

        OrderNotificationRecipient.objects.create(
            email="active@example.com", is_active=True
        )
        response = self.client.get("/staff/settings/")
        self.assertNotContains(
            response,
            "No active order notification email addresses are configured.",
        )


class OrderEmailContentTests(TestCase):
    @override_settings(**RESEND_OK)
    def test_delivery_email_contains_complete_persisted_order(self):
        order, payment = make_order(notes="<script>alert(1)</script>")
        message = order_notification_email(order)
        html = message["html"]
        text = message["text"]

        self.assertIn(order.reference, message["subject"])
        self.assertIn(
            date_format(timezone.localtime(order.placed_at), "j F Y, H:i"),
            html,
        )
        for value in (
            order.reference,
            "Ada Okafor",
            "08031234567",
            "ada@example.com",
            "Fresh Chicken",
            "1kg",
            "1 kg",
            "CHK-1KG",
            "Goat Meat",
            "2kg",
            "2 kg",
            "GOAT-2KG",
            "OF-EMAIL1234-PAY",
            "NGN 1,800.00",
            "NGN 3,000.00",
            "NGN 4,800.00",
            "NGN 500.00",
            "NGN 5,300.00",
            "14 Farm Settlement Road",
            "Opposite the sawmill",
            "Camp area",
            "Abeokuta",
            "Ogun",
            "Use the service gate",
            "Paid (verified by Paystack)",
            "Paystack",
            "https://farm.example.com/staff/orders/OF-EMAIL1234/",
            "View Order in Admin",
            "This is an automated order notification from O’Toosin Farms.",
        ):
            self.assertIn(value, html)
        self.assertIn("DELIVERY DETAILS", html)
        self.assertIn("Fresh Chicken", text)
        self.assertIn("Goat Meat", text)
        self.assertIn(order.reference, text)
        self.assertIn("CHK-1KG", text)
        self.assertIn("OF-EMAIL1234-PAY", text)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertGreater(len(payment.provider_reference), 0)

    @override_settings(**RESEND_OK)
    def test_pickup_email_uses_pickup_details_only(self):
        order, _ = make_order(
            reference="OF-PICKUP99",
            receive_method=Order.ReceiveMethod.PICKUP,
        )
        message = order_notification_email(order)
        html = message["html"]
        text = message["text"]

        self.assertIn("PICKUP DETAILS", html)
        self.assertIn("Mummy-D Stores", html)
        self.assertIn("12 Ijaiye Road, Abeokuta", html)
        self.assertIn("Collect at the front desk", html)
        self.assertIn("No delivery fee", html)
        self.assertNotIn("DELIVERY DETAILS", html)
        self.assertNotIn("Street / house address", html)
        self.assertNotIn("Landmark:", html)
        self.assertNotIn("14 Farm Settlement Road", text)

    @override_settings(**RESEND_OK)
    def test_logo_is_an_absolute_url(self):
        order, _ = make_order()
        html = order_notification_email(order)["html"]
        self.assertIn(
            "https://farm.example.com/static/assets/img/harvest_castle/of_favicon.png",
            html,
        )


class OrderEmailTriggerTests(TestCase):
    def setUp(self):
        provision_staff_roles()
        self.owner = get_user_model().objects.create_user(
            username="owner",
            password="strong-pass-123",
            is_staff=True,
            is_superuser=True,
        )
        self.client = Client()
        self.client.force_login(self.owner)
        OrderNotificationRecipient.objects.create(email="owner@example.com")
        OrderNotificationRecipient.objects.create(email="manager@example.com")
        OrderNotificationRecipient.objects.create(
            email="disabled@example.com", is_active=False
        )

    def provider_data(self, payment, status="success"):
        return {
            "status": status,
            "reference": payment.provider_reference,
            "amount": int(payment.amount * 100),
            "currency": "NGN",
        }

    @override_settings(**RESEND_OK)
    @mock.patch(
        "Otoosin.email_service._send_request",
        return_value=(200, '{"id":"email-123"}'),
    )
    def test_successful_verification_emails_all_active_recipients(self, request):
        order, payment = make_order(paid=False)
        with self.captureOnCommitCallbacks(execute=True):
            result = verify_payment(
                payment, provider_data=self.provider_data(payment)
            )

        self.assertTrue(result["changed"])
        deliveries = EmailDelivery.objects.filter(
            category=EmailDelivery.Category.ORDER_NOTIFICATION
        )
        self.assertEqual(deliveries.count(), 2)
        self.assertEqual(
            set(deliveries.values_list("recipient", flat=True)),
            {"owner@example.com", "manager@example.com"},
        )
        self.assertTrue(
            all(
                delivery.status == EmailDelivery.Status.SENT
                for delivery in deliveries
            )
        )
        self.assertEqual(request.call_count, 2)

    @override_settings(**RESEND_OK)
    @mock.patch(
        "Otoosin.email_service._send_request",
        return_value=(200, '{"id":"email-123"}'),
    )
    def test_pending_and_failed_payments_send_no_email(self, request):
        order, payment = make_order(paid=False)
        for status in ("pending", "failed", "abandoned"):
            with self.captureOnCommitCallbacks(execute=True):
                verify_payment(
                    payment, provider_data=self.provider_data(payment, status)
                )
        self.assertFalse(
            EmailDelivery.objects.filter(
                category=EmailDelivery.Category.ORDER_NOTIFICATION
            ).exists()
        )
        request.assert_not_called()

    @override_settings(**RESEND_OK)
    @mock.patch(
        "Otoosin.email_service._send_request",
        return_value=(200, '{"id":"email-123"}'),
    )
    def test_duplicate_verification_sends_no_duplicate_emails(self, request):
        order, payment = make_order(paid=False)
        with self.captureOnCommitCallbacks(execute=True):
            verify_payment(payment, provider_data=self.provider_data(payment))
            verify_payment(payment, provider_data=self.provider_data(payment))
        self.assertEqual(
            EmailDelivery.objects.filter(
                category=EmailDelivery.Category.ORDER_NOTIFICATION
            ).count(),
            2,
        )
        self.assertEqual(request.call_count, 2)

    @override_settings(RESEND_API_KEY="", RESEND_FROM_EMAIL="")
    def test_resend_failure_does_not_reverse_verified_payment(self):
        order, payment = make_order(paid=False)
        with self.captureOnCommitCallbacks(execute=True):
            result = verify_payment(
                payment, provider_data=self.provider_data(payment)
            )
        self.assertTrue(result["changed"])
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.PAID)
        self.assertEqual(
            EmailDelivery.objects.filter(
                category=EmailDelivery.Category.ORDER_NOTIFICATION,
                status=EmailDelivery.Status.FAILED,
            ).count(),
            2,
        )

    def test_no_active_recipients_is_safe(self):
        OrderNotificationRecipient.objects.update(is_active=False)
        order, payment = make_order(paid=False)
        with self.captureOnCommitCallbacks(execute=True):
            result = verify_payment(
                payment, provider_data=self.provider_data(payment)
            )
        self.assertTrue(result["changed"])
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.PAID)
        self.assertFalse(
            EmailDelivery.objects.filter(
                category=EmailDelivery.Category.ORDER_NOTIFICATION
            ).exists()
        )

    @override_settings(**RESEND_OK)
    def test_one_recipient_failure_does_not_stop_others(self):
        order, payment = make_order(paid=False)
        sent = mock.Mock(status=EmailDelivery.Status.SENT, last_error="")
        calls = []

        def fake_send_email(**kwargs):
            calls.append(kwargs["recipient"])
            if kwargs["recipient"] == "manager@example.com":
                raise RuntimeError("provider down for this recipient")
            return sent

        with mock.patch(
            "Otoosin.notifications.send_email", side_effect=fake_send_email
        ):
            with self.captureOnCommitCallbacks(execute=True):
                result = verify_payment(
                    payment, provider_data=self.provider_data(payment)
                )

        self.assertTrue(result["changed"])
        self.assertEqual(
            calls, ["manager@example.com", "owner@example.com"]
        )

    @override_settings(
        **(
            RESEND_OK
            | {
                "WHATSAPP_ENABLED": False,
                "WHATSAPP_ORDER_NOTIFICATIONS_ENABLED": False,
                "WHATSAPP_ACCESS_TOKEN": "",
                "WHATSAPP_PHONE_NUMBER_ID": "",
                "WHATSAPP_MESSAGE_TEMPLATE": "",
            }
        )
    )
    @mock.patch(
        "Otoosin.email_service._send_request",
        return_value=(200, '{"id":"email-123"}'),
    )
    @mock.patch("Otoosin.notifications.whatsapp.send_order_notification")
    def test_email_is_independent_of_whatsapp(self, whatsapp_notify, request):
        order, payment = make_order(paid=False)
        with self.captureOnCommitCallbacks(execute=True):
            verify_payment(payment, provider_data=self.provider_data(payment))
        self.assertEqual(
            EmailDelivery.objects.filter(
                category=EmailDelivery.Category.ORDER_NOTIFICATION,
                status=EmailDelivery.Status.SENT,
            ).count(),
            2,
        )
        whatsapp_notify.assert_not_called()
