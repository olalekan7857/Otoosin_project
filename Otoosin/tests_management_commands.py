import os
from types import SimpleNamespace
from unittest import mock

from django.contrib.auth.management.commands.createsuperuser import (
    Command as CreatesuperuserCommand,
)
from django.core.management.base import CommandError
from django.test import SimpleTestCase

from Otoosin.management.commands import create_production_superuser


class CreateProductionSuperuserTests(SimpleTestCase):
    def test_inherits_builtin_createsuperuser(self):
        self.assertTrue(
            issubclass(
                create_production_superuser.Command,
                CreatesuperuserCommand,
            )
        )

    def test_parser_exposes_noinput_and_identity_options(self):
        parser = create_production_superuser.Command().create_parser(
            "manage.py", "create_production_superuser"
        )
        option_strings = {
            option
            for action in parser._actions
            for option in action.option_strings
        }
        self.assertIn("--noinput", option_strings)
        self.assertIn("--username", option_strings)
        self.assertIn("--email", option_strings)

    def test_sqlite_vendor_aborts_before_builtin_execution(self):
        command = create_production_superuser.Command()
        sqlite = SimpleNamespace(vendor="sqlite")
        with mock.patch.object(
            create_production_superuser, "connection", sqlite
        ), mock.patch.object(
            create_production_superuser, "connections", {"default": sqlite}
        ), mock.patch.object(
            CreatesuperuserCommand, "execute", autospec=True
        ) as super_execute:
            with self.assertRaisesMessage(CommandError, "not 'postgresql'"):
                command.execute(database="default")
        super_execute.assert_not_called()

    def test_non_postgresql_selected_alias_aborts_before_creation(self):
        command = create_production_superuser.Command()
        connections = {
            "default": SimpleNamespace(vendor="postgresql"),
            "legacy": SimpleNamespace(vendor="sqlite"),
        }
        with mock.patch.object(
            create_production_superuser, "connection", connections["default"]
        ), mock.patch.object(
            create_production_superuser, "connections", connections
        ), mock.patch.object(
            CreatesuperuserCommand, "execute", autospec=True
        ) as super_execute:
            with self.assertRaisesMessage(CommandError, "connection 'legacy'"):
                command.execute(database="legacy")
        super_execute.assert_not_called()

    def test_postgresql_delegates_to_builtin_execution(self):
        command = create_production_superuser.Command()
        postgres = SimpleNamespace(vendor="postgresql")
        with mock.patch.object(
            create_production_superuser, "connection", postgres
        ), mock.patch.object(
            create_production_superuser, "connections", {"default": postgres}
        ), mock.patch.object(
            CreatesuperuserCommand, "execute", autospec=True
        ) as super_execute:
            result = command.execute(database="default")
        super_execute.assert_called_once_with(command, database="default")
        self.assertIs(result, super_execute.return_value)

    def test_noninteractive_uses_standard_superuser_environment_variables(self):
        command = create_production_superuser.Command()
        manager = mock.Mock()
        manager.db_manager.return_value = manager
        environment = {
            "DJANGO_SUPERUSER_USERNAME": "prodadmin",
            "DJANGO_SUPERUSER_EMAIL": "prodadmin@example.com",
            "DJANGO_SUPERUSER_PASSWORD": "Safe-Password-123!",
        }
        with mock.patch.dict(os.environ, environment, clear=False), mock.patch.object(
            command, "_validate_username", return_value=None
        ), mock.patch.object(command.UserModel._meta, "default_manager", manager):
            command.handle(
                interactive=False,
                database="default",
                username=None,
                email=None,
                verbosity=0,
            )
        manager.create_superuser.assert_called_once_with(
            username="prodadmin",
            email="prodadmin@example.com",
            password="Safe-Password-123!",
        )

    def test_existing_username_is_rejected_without_creation(self):
        command = create_production_superuser.Command()
        manager = mock.Mock()
        manager.db_manager.return_value = manager
        with mock.patch.object(
            command,
            "_validate_username",
            return_value="Error: That username is already taken.",
        ), mock.patch.object(command.UserModel._meta, "default_manager", manager):
            with self.assertRaisesMessage(CommandError, "already taken"):
                command.handle(
                    interactive=False,
                    database="default",
                    username="existing",
                    email="existing@example.com",
                    verbosity=0,
                )
        manager.create_superuser.assert_not_called()
