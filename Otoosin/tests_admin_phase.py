import socket
import urllib.error
from decimal import Decimal
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.tokens import default_token_generator
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from .forms import PickupLocationForm
from .models import (
    AuditEvent,
    ContactMessage,
    DeliveryLocation,
    EmailDelivery,
    PickupLocation,
    SiteConfiguration,
    StaffInvitation,
    normalise_nigerian_phone,
)
from .permissions import provision_staff_roles


class ResendEmailServiceTests(TestCase):
    @override_settings(
        RESEND_API_KEY="test-resend-key",
        RESEND_FROM_EMAIL="OToosin <no-reply@example.com>",
    )
    def test_valid_configuration_builds_provider_request(self):
        from .email_service import send_email

        captured = {}

        def fake_send(payload):
            captured.update(payload)
            return 200, '{"id":"email-123"}'

        with mock.patch("Otoosin.email_service._send_request", side_effect=fake_send):
            delivery = send_email(
                category=EmailDelivery.Category.STAFF_INVITE,
                recipient="staff@example.com",
                subject="Invitation",
                text="Activate here",
            )
        self.assertEqual(delivery.status, EmailDelivery.Status.SENT)
        self.assertEqual(delivery.provider_message_id, "email-123")
        self.assertEqual(captured["from"], "OToosin <no-reply@example.com>")
        self.assertEqual(captured["to"], ["staff@example.com"])
        self.assertEqual(captured["subject"], "Invitation")
        self.assertIn("Activate here", captured["text"])

    @override_settings(RESEND_API_KEY="", RESEND_FROM_EMAIL="sender@example.com")
    def test_missing_configuration_fails_without_request(self):
        from .email_service import send_email

        with mock.patch("Otoosin.email_service._send_request") as request:
            delivery = send_email(
                category=EmailDelivery.Category.PASSWORD_RESET,
                recipient="staff@example.com",
                subject="Reset",
                text="Reset here",
            )
        request.assert_not_called()
        self.assertEqual(delivery.status, EmailDelivery.Status.FAILED)
        self.assertIn("not configured", delivery.last_error)

    @override_settings(
        RESEND_API_KEY="test-resend-key",
        RESEND_FROM_EMAIL="sender@example.com",
    )
    def test_provider_rejection_is_recorded_honestly(self):
        from .email_service import send_email

        error = urllib.error.HTTPError(
            "https://api.resend.com/emails", 422, "Unprocessable", {}, None
        )
        with mock.patch("Otoosin.email_service._send_request", side_effect=error):
            delivery = send_email(
                category=EmailDelivery.Category.STAFF_INVITE,
                recipient="staff@example.com",
                subject="Invitation",
                text="Activate here",
            )
        self.assertEqual(delivery.status, EmailDelivery.Status.FAILED)
        self.assertFalse(delivery.retryable)
        self.assertNotIn("test-resend-key", delivery.last_error)
        self.assertIn("HTTP 422", delivery.last_error)

    @override_settings(
        RESEND_API_KEY="test-resend-key",
        RESEND_FROM_EMAIL="sender@example.com",
    )
    def test_timeout_marks_delivery_retryable(self):
        from .email_service import send_email

        with mock.patch(
            "Otoosin.email_service._send_request",
            side_effect=socket.timeout(),
        ):
            delivery = send_email(
                category=EmailDelivery.Category.STAFF_INVITE,
                recipient="staff@example.com",
                subject="Invitation",
                text="Activate here",
            )
        self.assertEqual(delivery.status, EmailDelivery.Status.FAILED)
        self.assertTrue(delivery.retryable)
        self.assertIn("timed out", delivery.last_error)


class BrandedStaffEmailTests(TestCase):
    site_url = "https://otoosinfarms.com.ng"
    logo_url = (
        "https://otoosinfarms.com.ng/static/assets/img/harvest_castle/"
        "of_favicon.png"
    )

    def _user(self, **kwargs):
        User = get_user_model()
        defaults = {
            "username": "branded-staff",
            "email": "branded@example.com",
            "first_name": "Ada",
            "last_name": "Okafor",
            "is_staff": True,
        }
        defaults.update(kwargs)
        return User.objects.create_user(password="strong-pass-123", **defaults)

    @override_settings(
        SITE_URL=site_url,
        STAFF_INVITATION_HOURS=72,
        SUPPORT_EMAIL="support@otoosinfarms.com.ng",
    )
    def test_staff_invitation_email_is_branded_and_has_absolute_logo(self):
        from .transactional_emails import staff_invitation_email

        user = self._user()
        invitation = StaffInvitation.objects.create(
            user=user,
            email=user.email,
            role=StaffInvitation.Role.MANAGER,
            token_hash=StaffInvitation.hash_token("invite-token"),
            expires_at=timezone.now() + timezone.timedelta(hours=72),
        )
        message = staff_invitation_email(
            invitation, f"{self.site_url}/staff/activate/uid/invite-token/"
        )
        self.assertIn("invited", message["subject"].lower())
        self.assertIn("Ada Okafor", message["html"])
        self.assertIn("Manager", message["html"])
        self.assertIn(self.logo_url, message["html"])
        self.assertIn("invitation expires", message["text"].lower())
        self.assertIn("/staff/activate/uid/invite-token/", message["html"])
        self.assertIn("ignore", message["html"].lower())
        self.assertIn("O’Toosin Farms", message["text"])
        self.assertNotIn("<script", message["html"].lower())

    @override_settings(
        SITE_URL=site_url,
        PASSWORD_RESET_TIMEOUT=86400,
        SUPPORT_EMAIL="support@otoosinfarms.com.ng",
    )
    def test_password_reset_email_is_branded_and_has_absolute_logo(self):
        from .transactional_emails import staff_password_reset_email

        user = self._user()
        message = staff_password_reset_email(
            user, f"{self.site_url}/staff/password-reset/uid/token/"
        )
        self.assertIn("password", message["subject"].lower())
        self.assertIn("Ada Okafor", message["html"])
        self.assertIn(self.logo_url, message["html"])
        self.assertIn("24 hours", message["text"].lower())
        self.assertIn("/staff/password-reset/uid/token/", message["html"])
        self.assertIn("did not request", message["html"].lower())
        self.assertIn("O’Toosin Farms", message["text"])

    @override_settings(
        SITE_URL=site_url,
        RESEND_API_KEY="test-resend-key",
        RESEND_FROM_EMAIL="O’Toosin Farms <no-reply@otoosinfarms.com.ng>",
    )
    def test_send_email_includes_html_and_text_alternative(self):
        from .email_service import send_email

        captured = {}

        def fake_send(payload):
            captured.update(payload)
            return 200, '{"id":"email-html-1"}'

        with mock.patch("Otoosin.email_service._send_request", side_effect=fake_send):
            delivery = send_email(
                category=EmailDelivery.Category.STAFF_INVITE,
                recipient="staff@example.com",
                subject="Invitation",
                text="Plain alternative",
                html="<p>HTML alternative</p>",
            )
        self.assertEqual(delivery.status, EmailDelivery.Status.SENT)
        self.assertEqual(captured["html"], "<p>HTML alternative</p>")
        self.assertEqual(captured["text"], "Plain alternative")


class StaffRoleAndTeamTests(TestCase):
    def setUp(self):
        cache.clear()
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
        self.support = User.objects.create_user(
            username="support",
            email="support@example.com",
            password="strong-pass-123",
            is_staff=True,
        )
        self.support.groups.add(Group.objects.get(name="Support"))
        self.fulfilment = User.objects.create_user(
            username="fulfilment",
            email="fulfilment@example.com",
            password="strong-pass-123",
            is_staff=True,
        )
        self.fulfilment.groups.add(Group.objects.get(name="Fulfilment"))
        self.client = Client()

    def test_role_groups_are_provisioned_repeatably(self):
        provision_staff_roles()
        manager = Group.objects.get(name="Manager")
        owner = Group.objects.get(name="Owner")
        support = Group.objects.get(name="Support")
        self.assertTrue(manager.permissions.filter(codename="change_product").exists())
        self.assertFalse(manager.permissions.filter(codename="manage_staff").exists())
        self.assertTrue(owner.permissions.filter(codename="manage_staff").exists())
        self.assertTrue(
            support.permissions.filter(codename="change_contactmessage").exists()
        )
        self.assertFalse(
            support.permissions.filter(codename="change_product").exists()
        )

    def test_role_access_is_enforced_server_side(self):
        self.client.force_login(self.manager)
        self.assertEqual(self.client.get("/staff/team/").status_code, 403)
        self.assertEqual(self.client.get("/staff/settings/").status_code, 200)
        self.assertEqual(self.client.get("/staff/messages/").status_code, 200)

        self.client.force_login(self.support)
        self.assertEqual(self.client.get("/staff/messages/").status_code, 200)
        self.assertEqual(self.client.get("/staff/team/").status_code, 403)
        self.assertEqual(self.client.get("/staff/settings/").status_code, 403)
        self.assertEqual(self.client.get("/staff/products/").status_code, 403)

        self.client.force_login(self.fulfilment)
        self.assertEqual(self.client.get("/staff/messages/").status_code, 403)
        self.assertEqual(self.client.get("/staff/products/").status_code, 403)

        self.client.force_login(self.owner)
        for path in ("/staff/team/", "/staff/settings/", "/staff/messages/"):
            self.assertEqual(self.client.get(path).status_code, 200, path)

    @override_settings(
        RESEND_API_KEY="test-resend-key",
        RESEND_FROM_EMAIL="sender@example.com",
        SITE_URL="https://farm.example.com",
    )
    def test_owner_can_invite_and_email_failure_is_not_reported_as_sent(self):
        self.client.force_login(self.owner)
        with mock.patch(
            "Otoosin.email_service._send_request",
            side_effect=urllib.error.URLError("offline"),
        ):
            response = self.client.post(
                "/staff/team/",
                {
                    "action": "invite",
                    "email": "newstaff@example.com",
                    "role": "support",
                },
            )
        self.assertRedirects(response, "/staff/team/")
        User = get_user_model()
        invited = User.objects.get(email="newstaff@example.com")
        self.assertFalse(invited.is_active)
        self.assertTrue(invited.is_staff)
        invitation = StaffInvitation.objects.get(user=invited)
        self.assertIsNone(invitation.used_at)
        self.assertIsNotNone(invitation.email_delivery)
        self.assertEqual(
            invitation.email_delivery.status, EmailDelivery.Status.FAILED
        )

    def test_invitation_activation_is_single_use_and_role_bounded(self):
        User = get_user_model()
        invited = User.objects.create_user(
            username="invitee",
            email="invitee@example.com",
            password=None,
            is_staff=True,
            is_active=False,
        )
        raw = "single-use-test-token"
        invitation = StaffInvitation.objects.create(
            user=invited,
            email=invited.email,
            role=StaffInvitation.Role.SUPPORT,
            token_hash=StaffInvitation.hash_token(raw),
            expires_at=timezone.now() + timezone.timedelta(hours=1),
        )
        uid = urlsafe_base64_encode(str(invited.pk).encode())
        path = f"/staff/activate/{uid}/{raw}/"
        page = self.client.get(path)
        self.assertContains(page, "Username")
        response = self.client.post(
            path,
            {
                "username": "chosen-invitee",
                "new_password1": "new-strong-pass-456",
                "new_password2": "new-strong-pass-456",
            },
        )
        self.assertRedirects(response, "/staff/login/")
        invited.refresh_from_db()
        invitation.refresh_from_db()
        self.assertTrue(invited.is_active)
        self.assertEqual(invited.username, "chosen-invitee")
        self.assertIsNotNone(invitation.used_at)
        self.assertTrue(invited.groups.filter(name="Support").exists())
        self.assertFalse(invited.groups.filter(name="Owner").exists())

        login = self.client.post(
            "/staff/login/",
            {
                "username": "invitee@example.com",
                "password": "new-strong-pass-456",
            },
        )
        self.assertRedirects(login, "/staff/products/", fetch_redirect_response=False)
        self.client.post("/staff/logout/")

        self.client.force_login(self.owner)
        team = self.client.get("/staff/team/")
        self.assertContains(team, "chosen-invitee")
        self.assertNotContains(team, "Invitation accepted")

        second = self.client.post(
            path,
            {
                "new_password1": "another-pass-789",
                "new_password2": "another-pass-789",
            },
        )
        self.assertEqual(second.status_code, 400)

    def test_expired_and_invalid_invitation_tokens_fail_safely(self):
        User = get_user_model()
        invited = User.objects.create_user(
            username="expired",
            email="expired@example.com",
            password=None,
            is_staff=True,
            is_active=False,
        )
        raw = "expired-token"
        StaffInvitation.objects.create(
            user=invited,
            email=invited.email,
            role=StaffInvitation.Role.SUPPORT,
            token_hash=StaffInvitation.hash_token(raw),
            expires_at=timezone.now() - timezone.timedelta(minutes=1),
        )
        uid = urlsafe_base64_encode(str(invited.pk).encode())
        response = self.client.get(f"/staff/activate/{uid}/{raw}/")
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "not valid", status_code=400)

    def test_last_owner_cannot_be_disabled(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            "/staff/team/",
            {"action": "toggle_active", "user_id": self.owner.pk},
            follow=True,
        )
        self.owner.refresh_from_db()
        self.assertTrue(self.owner.is_active)
        self.assertContains(response, "last usable owner")

    def test_role_change_and_deactivation_take_effect_on_next_request(self):
        self.client.force_login(self.owner)
        self.client.post(
            "/staff/team/",
            {
                "action": "change_role",
                "user_id": self.manager.pk,
                "role": "support",
            },
        )
        self.client.force_login(self.manager)
        self.assertEqual(self.client.get("/staff/messages/").status_code, 200)
        self.assertEqual(self.client.get("/staff/products/").status_code, 403)

        self.client.force_login(self.owner)
        self.client.post(
            "/staff/team/",
            {"action": "toggle_active", "user_id": self.manager.pk},
        )
        self.manager.refresh_from_db()
        self.assertFalse(self.manager.is_active)
        self.client.force_login(self.manager)
        self.assertIn(self.client.get("/staff/messages/").status_code, {302, 403})

    def test_staff_can_sign_in_with_email_or_username(self):
        email_login = self.client.post(
            "/staff/login/",
            {
                "username": "owner@example.com",
                "password": "strong-pass-123",
            },
        )
        self.assertRedirects(email_login, "/staff/products/")
        self.client.post("/staff/logout/")

        username_login = self.client.post(
            "/staff/login/",
            {
                "username": "owner",
                "password": "strong-pass-123",
            },
        )
        self.assertRedirects(username_login, "/staff/products/")

    def test_login_is_throttled_and_generic_for_inactive_accounts(self):
        User = get_user_model()
        inactive = User.objects.create_user(
            username="inactive",
            email="inactive@example.com",
            password="strong-pass-123",
            is_staff=True,
            is_active=False,
        )
        response = self.client.post(
            "/staff/login/",
            {"username": inactive.username, "password": "strong-pass-123"},
        )
        self.assertContains(response, "Please enter a correct")
        self.assertNotContains(response, "This account is inactive")

        for _ in range(5):
            self.client.post(
                "/staff/login/",
                {"username": "owner", "password": "wrong-password"},
            )
        blocked = self.client.post(
            "/staff/login/",
            {"username": "owner", "password": "strong-pass-123"},
        )
        self.assertEqual(blocked.status_code, 200)
        self.assertContains(blocked, "Too many sign-in attempts")
        self.assertGreaterEqual(
            AuditEvent.objects.filter(action="login_failed").count(), 5
        )
        self.assertTrue(
            AuditEvent.objects.filter(action="login_throttled").exists()
        )

    def test_password_reset_response_does_not_reveal_accounts(self):
        with mock.patch("Otoosin.views.send_email") as send:
            send.return_value = mock.Mock(status=EmailDelivery.Status.SENT)
            known = self.client.post(
                "/staff/password-reset/", {"email": "owner@example.com"}
            )
            unknown = self.client.post(
                "/staff/password-reset/", {"email": "missing@example.com"}
            )
        self.assertRedirects(known, "/staff/password-reset/done/")
        self.assertRedirects(unknown, "/staff/password-reset/done/")
        self.assertEqual(send.call_count, 1)


class ContactFlowTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = Client()

    def valid_payload(self, **overrides):
        payload = {
            "name": "Adaeze Okafor",
            "email": "adaeze@example.com",
            "phone": "08031234567",
            "subject": "product",
            "message": "Please tell me more about the fresh pork options.",
        }
        payload.update(overrides)
        return payload

    def test_valid_submission_creates_exactly_one_record(self):
        response = self.client.post("/contact/", self.valid_payload())
        self.assertRedirects(response, "/contact/?sent=1#contact-form")
        self.assertEqual(ContactMessage.objects.count(), 1)
        enquiry = ContactMessage.objects.get()
        self.assertEqual(enquiry.status, ContactMessage.Status.NEW)
        self.assertEqual(enquiry.name, "Adaeze Okafor")
        receipt = self.client.get("/contact/?sent=1")
        self.assertContains(receipt, "Your enquiry was sent successfully.")
        self.assertContains(receipt, "Dismiss message")

    def test_invalid_and_unapproved_subjects_are_rejected(self):
        response = self.client.post(
            "/contact/", self.valid_payload(subject="not-a-choice")
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(ContactMessage.objects.count(), 0)

        response = self.client.post(
            "/contact/", self.valid_payload(message="short")
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Your enquiry was not sent.")
        self.assertContains(response, "Message:")
        self.assertEqual(ContactMessage.objects.count(), 0)

    def test_honeypot_autofill_does_not_block_a_real_enquiry(self):
        response = self.client.post(
            "/contact/", self.valid_payload(website="https://spam.example")
        )
        self.assertRedirects(response, "/contact/?sent=1#contact-form")
        self.assertEqual(ContactMessage.objects.count(), 1)

    def test_csrf_protection(self):
        csrf_client = Client(enforce_csrf_checks=True)
        response = csrf_client.post("/contact/", self.valid_payload())
        self.assertEqual(response.status_code, 403)
        self.assertEqual(ContactMessage.objects.count(), 0)

    def test_repeated_submissions_are_rate_limited(self):
        for index in range(5):
            response = self.client.post(
                "/contact/",
                self.valid_payload(email=f"person{index}@example.com"),
            )
            self.assertEqual(response.status_code, 302)
        blocked = self.client.post(
            "/contact/", self.valid_payload(email="blocked@example.com")
        )
        self.assertEqual(blocked.status_code, 429)
        self.assertEqual(ContactMessage.objects.count(), 5)

    def test_contact_submission_does_not_send_email(self):
        with mock.patch("Otoosin.views.send_email") as send:
            self.client.post("/contact/", self.valid_payload())
        send.assert_not_called()


class ContactInboxTests(TestCase):
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
        self.enquiry = ContactMessage.objects.create(
            name="Ada",
            email="ada@example.com",
            phone="08031234567",
            subject=ContactMessage.Subject.GENERAL,
            message="<script>alert(1)</script> Please help with this enquiry.",
        )

    def test_anonymous_cannot_view_inbox_or_detail(self):
        self.assertEqual(self.client.get("/staff/messages/").status_code, 302)
        self.assertEqual(
            self.client.get(f"/staff/messages/{self.enquiry.pk}/").status_code,
            302,
        )

    def test_content_is_escaped_in_staff_templates(self):
        self.client.force_login(self.support)
        response = self.client.get(f"/staff/messages/{self.enquiry.pk}/")
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "<script>alert(1)</script>")
        self.assertContains(response, "&lt;script&gt;alert(1)&lt;/script&gt;")

    def test_status_and_notes_require_post_and_permission(self):
        manager = get_user_model().objects.create_user(
            username="manager", password="strong-pass-123", is_staff=True
        )
        manager.groups.add(Group.objects.get(name="Manager"))
        self.client.force_login(manager)
        self.assertEqual(
            self.client.get(f"/staff/messages/{self.enquiry.pk}/").status_code, 200
        )
        self.client.force_login(self.support)
        self.assertEqual(
            self.client.get(f"/staff/messages/{self.enquiry.pk}/").status_code, 200
        )
        self.client.post(
            f"/staff/messages/{self.enquiry.pk}/",
            {"action": "status", "status": "replied"},
        )
        self.enquiry.refresh_from_db()
        self.assertEqual(self.enquiry.status, ContactMessage.Status.REPLIED)
        self.assertEqual(self.enquiry.handled_by, self.support)
        self.assertIsNotNone(self.enquiry.handled_at)

        self.client.post(
            f"/staff/messages/{self.enquiry.pk}/",
            {"action": "notes", "internal_notes": "Called the customer."},
        )
        self.enquiry.refresh_from_db()
        self.assertEqual(self.enquiry.internal_notes, "Called the customer.")
        self.assertTrue(
            AuditEvent.objects.filter(action="contact_status_changed").exists()
        )
        self.assertTrue(
            AuditEvent.objects.filter(action="contact_notes_updated").exists()
        )

    def test_dashboard_counts_reflect_database(self):
        self.client.force_login(self.support)
        response = self.client.get("/staff/")
        self.assertContains(response, "Total enquiries")
        self.assertEqual(response.context["contact_summary"]["total"], 1)
        self.assertEqual(response.context["contact_summary"]["new"], 1)


class SettingsAndDeliveryTests(TestCase):
    def setUp(self):
        provision_staff_roles()
        User = get_user_model()
        self.owner = User.objects.create_user(
            username="owner",
            password="strong-pass-123",
            is_staff=True,
            is_superuser=True,
        )
        self.client = Client()
        self.client.force_login(self.owner)

    def test_contact_page_uses_saved_settings_and_active_pickup(self):
        config = SiteConfiguration.load()
        config.business_name = "O’Toosin Test Farm"
        config.address = "12 Farm Road, Abeokuta"
        config.save()
        PickupLocation.objects.create(
            name="Test Pickup Point",
            address="1 Market Road, Abeokuta",
            customer_instructions="Collect at the front desk.",
            is_active=True,
        )
        response = self.client.get("/contact/")
        self.assertContains(response, "O’Toosin Test Farm")
        self.assertContains(response, "12 Farm Road, Abeokuta")
        self.assertContains(response, "Test Pickup Point")
        self.assertContains(response, "Collect at the front desk.")

    def test_site_configuration_is_a_safe_singleton(self):
        first = SiteConfiguration.load()
        second = SiteConfiguration.load()
        self.assertEqual(first.pk, 1)
        self.assertEqual(second.pk, 1)
        self.assertEqual(SiteConfiguration.objects.count(), 1)

    def test_business_settings_save_creates_audit_event(self):
        response = self.client.post(
            "/staff/settings/",
            {
                "action": "business",
                "business_name": "O’Toosin Farms",
                "address": "Camp, Abeokuta",
                "contact_phone": "08031234567",
                "whatsapp_number": "09011058873",
                "support_email": "support@example.com",
                "description": "Farm fresh food.",
                "delivery_cutoff_time": "17:00",
                "delivery_cutoff_note": "Same-day orders before 5 PM.",
            },
        )
        self.assertRedirects(response, "/staff/settings/")
        config = SiteConfiguration.load()
        self.assertEqual(config.contact_phone, "+2348031234567")
        self.assertTrue(
            AuditEvent.objects.filter(action="site_configuration_updated").exists()
        )

    def test_phone_normalisation(self):
        self.assertEqual(
            normalise_nigerian_phone("0803 123 4567"), "+2348031234567"
        )
        with self.assertRaises(Exception):
            normalise_nigerian_phone("12345")

    def test_invalid_business_phone_renders_specific_error(self):
        response = self.client.post(
            "/staff/settings/",
            {
                "action": "business",
                "business_name": "O’Toosin Farms",
                "contact_phone": "12345",
                "whatsapp_number": "09011058873",
                "support_email": "support@example.com",
                "description": "Farm fresh food.",
                "delivery_cutoff_time": "17:00",
                "delivery_cutoff_note": "",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Enter a valid Nigerian phone number")
        self.assertEqual(SiteConfiguration.load().contact_phone, "")

    def delivery_payload(self, **overrides):
        payload = {
            "action": "delivery_create",
            "location_type": "doorstep",
            "name": "Camp",
            "city": "Abeokuta",
            "state": "Ogun",
            "area": "Camp",
            "fee": "1500.00",
            "customer_instructions": "",
            "is_active": "on",
            "sort_order": "1",
        }
        payload.update(overrides)
        return payload

    def test_invalid_delivery_fees_and_areas_are_rejected(self):
        response = self.client.post(
            "/staff/delivery/", self.delivery_payload(fee="-1")
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "greater than or equal to 0")
        self.assertEqual(DeliveryLocation.objects.count(), 0)

        response = self.client.post(
            "/staff/delivery/", self.delivery_payload(fee="")
        )
        self.assertContains(response, "Enter the approved fee")
        self.assertEqual(DeliveryLocation.objects.count(), 0)

        response = self.client.post(
            "/staff/delivery/",
            self.delivery_payload(
                location_type="park",
                name="Park One",
                customer_instructions="",
            ),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "park collection instructions")
        self.assertEqual(DeliveryLocation.objects.count(), 0)

    def test_delivery_creation_is_active_default_and_audited(self):
        response = self.client.post("/staff/delivery/", self.delivery_payload())
        self.assertRedirects(response, "/staff/delivery/")
        location = DeliveryLocation.objects.get()
        self.assertTrue(location.is_active)
        self.assertEqual(location.city, "Abeokuta")
        self.assertEqual(location.state, "Ogun")
        self.assertEqual(location.sort_order, 1)
        self.assertTrue(
            AuditEvent.objects.filter(action="delivery_location_created").exists()
        )

    def test_delivery_fee_change_is_audited(self):
        self.client.post("/staff/delivery/", self.delivery_payload())
        location = DeliveryLocation.objects.get()
        response = self.client.post(
            "/staff/delivery/",
            self.delivery_payload(
                action="delivery_edit",
                location_id=location.pk,
                fee="2000.00",
            ),
        )
        self.assertRedirects(response, "/staff/delivery/")
        location.refresh_from_db()
        self.assertEqual(location.fee, Decimal("2000.00"))
        self.assertTrue(
            AuditEvent.objects.filter(action="delivery_location_updated").exists()
        )

    def test_pickup_model_is_separate_and_fee_free(self):
        self.assertNotIn("fee", PickupLocationForm().fields)
        response = self.client.post(
            "/staff/delivery/",
            {
                "action": "pickup_create",
                "name": "Mummy-D Stores",
                "address": "Beside FUNAAB MANCOT Park, Camp, Abeokuta",
                "customer_instructions": "Collect during store hours.",
                "opening_hours": "",
                "is_active": "on",
            },
        )
        self.assertRedirects(response, "/staff/delivery/")
        pickup = PickupLocation.objects.get()
        self.assertEqual(pickup.name, "Mummy-D Stores")
        self.assertTrue(pickup.is_active)
        self.assertFalse(hasattr(pickup, "fee"))

    def test_no_unapproved_delivery_or_pickup_records_are_seeded(self):
        self.assertEqual(DeliveryLocation.objects.count(), 0)
        self.assertEqual(PickupLocation.objects.count(), 0)


class StaffPasswordResetLinkTests(TestCase):
    def setUp(self):
        provision_staff_roles()
        User = get_user_model()
        self.staff = User.objects.create_user(
            username="reset-staff",
            email="reset@example.com",
            password="strong-pass-123",
            is_staff=True,
        )
        self.non_staff = User.objects.create_user(
            username="reset-public",
            email="public@example.com",
            password="strong-pass-123",
        )

    def _url(self, user):
        return reverse(
            "Otoosin:staff_password_reset_confirm",
            kwargs={
                "uidb64": urlsafe_base64_encode(force_bytes(user.pk)),
                "token": default_token_generator.make_token(user),
            },
        )

    def test_active_staff_link_is_accepted(self):
        response = self.client.get(self._url(self.staff))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/set-password/", response["Location"])
        form_page = self.client.get(response["Location"])
        self.assertEqual(form_page.status_code, 200)
        self.assertContains(form_page, "Choose a new password")
        self.assertContains(form_page, 'class="form-control"')

    def test_non_staff_link_is_rejected(self):
        response = self.client.get(self._url(self.non_staff))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "invalid or has expired")
