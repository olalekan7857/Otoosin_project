from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from .models import AuditEvent, ContactMessage, StaffInvitation
from .permissions import provision_staff_roles


@override_settings(
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"]
)
class StaffAccountDeletionTests(TestCase):
    def setUp(self):
        cache.clear()
        provision_staff_roles()
        User = get_user_model()
        self.owner = User.objects.create_user(
            username="owner",
            email="owner@example.com",
            password="strong-pass-123",
            is_staff=True,
        )
        self.owner.groups.add(Group.objects.get(name="Owner"))
        self.superuser = User.objects.create_user(
            username="root",
            email="root@example.com",
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
        self.victim = User.objects.create_user(
            username="formerstaff",
            email="formerstaff@example.com",
            password="strong-pass-123",
            is_staff=True,
            is_active=False,
        )
        self.victim.groups.add(Group.objects.get(name="Support"))
        self.invitation = StaffInvitation.objects.create(
            user=self.victim,
            email=self.victim.email,
            role=StaffInvitation.Role.SUPPORT,
            token_hash=StaffInvitation.hash_token("token"),
            expires_at=timezone.now() + timedelta(hours=1),
        )
        self.client = Client()

    def _delete(self, target, client=None, **kwargs):
        return (client or self.client).post(
            "/staff/team/",
            {"action": "delete_account", "user_id": target.pk},
            **kwargs,
        )

    def test_owner_can_permanently_delete_a_deactivated_admin(self):
        self.client.force_login(self.owner)
        response = self._delete(self.victim, follow=True)
        User = get_user_model()
        self.assertFalse(User.objects.filter(pk=self.victim.pk).exists())
        self.assertFalse(
            StaffInvitation.objects.filter(user_id=self.victim.pk).exists()
        )
        self.assertContains(response, "was permanently deleted")
        self.assertTrue(
            AuditEvent.objects.filter(action="staff_account_deleted").exists()
        )

    def test_manager_cannot_delete_an_admin(self):
        self.client.force_login(self.manager)
        response = self._delete(self.victim)
        self.assertEqual(response.status_code, 403)
        self.assertTrue(
            get_user_model().objects.filter(pk=self.victim.pk).exists()
        )

    def test_self_deletion_is_blocked(self):
        self.client.force_login(self.owner)
        response = self._delete(self.owner, follow=True)
        self.assertTrue(
            get_user_model().objects.filter(pk=self.owner.pk).exists()
        )
        self.assertContains(response, "cannot delete the account you are signed in with")

    def test_superuser_account_is_protected(self):
        self.client.force_login(self.owner)
        response = self._delete(self.superuser, follow=True)
        self.assertTrue(
            get_user_model().objects.filter(pk=self.superuser.pk).exists()
        )
        self.assertContains(response, "highest access account")

    def test_deleting_an_admin_preserves_business_records(self):
        message = ContactMessage.objects.create(
            name="Customer",
            email="customer@example.com",
            subject=ContactMessage.Subject.GENERAL,
            message="Please help with my order.",
            handled_by=self.victim,
        )
        event = AuditEvent.objects.create(
            actor=self.victim,
            action="login_success",
            summary="Historical staff action.",
        )
        self.client.force_login(self.owner)
        self._delete(self.victim)

        message.refresh_from_db()
        event.refresh_from_db()
        self.assertIsNone(message.handled_by_id)
        self.assertIsNone(event.actor_id)
        self.assertEqual(message.name, "Customer")
        self.assertEqual(event.action, "login_success")

    def test_existing_activation_toggle_still_works(self):
        self.client.force_login(self.owner)
        self.client.post(
            "/staff/team/",
            {"action": "toggle_active", "user_id": self.victim.pk},
        )
        self.victim.refresh_from_db()
        self.assertTrue(self.victim.is_active)
        self.client.post(
            "/staff/team/",
            {"action": "toggle_active", "user_id": self.victim.pk},
        )
        self.victim.refresh_from_db()
        self.assertFalse(self.victim.is_active)

    def test_get_request_never_deletes_an_account(self):
        self.client.force_login(self.owner)
        self.client.get(
            "/staff/team/", {"action": "delete_account", "user_id": self.victim.pk}
        )
        self.assertTrue(
            get_user_model().objects.filter(pk=self.victim.pk).exists()
        )

    def test_deletion_requires_a_csrf_token(self):
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.owner)
        response = self._delete(self.victim, client=strict)
        self.assertEqual(response.status_code, 403)
        self.assertTrue(
            get_user_model().objects.filter(pk=self.victim.pk).exists()
        )

    def test_delete_pages_use_the_confirmation_dialog(self):
        self.client.force_login(self.owner)
        team = self.client.get("/staff/team/")
        self.assertContains(team, "fd-delete-modal")
        self.assertContains(team, "data-fd-delete")
        self.assertContains(team, "data-fd-delete-cancel")
        self.assertContains(team, "Delete admin account?")

        categories = self.client.get("/staff/categories/")
        self.assertContains(categories, "data-fd-delete")
        self.assertNotContains(categories, "onsubmit=\"return confirm(")

        settings_page = self.client.get("/staff/settings/")
        self.assertContains(settings_page, "data-fd-delete")
        self.assertNotContains(settings_page, "onsubmit=\"return confirm(")

        legal = self.client.get("/staff/legal/")
        self.assertContains(legal, "data-remove-section")
        self.assertContains(legal, "FdAdminConfirm")
