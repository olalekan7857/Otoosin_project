from django.contrib.auth.management.commands.createsuperuser import (
    Command as CreatesuperuserCommand,
)
from django.core.management.base import CommandError
from django.db import DEFAULT_DB_ALIAS, connection, connections


class Command(CreatesuperuserCommand):
    help = (
        "Create the first production administrator directly in PostgreSQL. "
        "Aborts unless the active database vendor is postgresql."
    )

    def execute(self, *args, **options):
        self._require_postgresql(connection.vendor, using="default")

        database = options.get("database", DEFAULT_DB_ALIAS)
        self._require_postgresql(connections[database].vendor, using=database)

        return super().execute(*args, **options)

    def _require_postgresql(self, vendor, *, using):
        if vendor != "postgresql":
            raise CommandError(
                "Refusing to create an administrator: the active database "
                f"connection '{using}' uses vendor '{vendor}', not "
                "'postgresql'. This command may only run against the live "
                "production PostgreSQL database."
            )
