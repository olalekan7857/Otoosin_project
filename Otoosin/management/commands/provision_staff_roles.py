from django.core.management.base import BaseCommand

from Otoosin.permissions import provision_staff_roles


class Command(BaseCommand):
    help = (
        "Create or reconcile the Owner, Manager, Fulfilment and Support groups "
        "with their Django model permissions. Safe to rerun."
    )

    def handle(self, *args, **options):
        groups = provision_staff_roles()
        for role, group in groups.items():
            self.stdout.write(
                self.style.SUCCESS(
                    f"{role}: {group.name} "
                    f"({group.permissions.filter(content_type__app_label='Otoosin').count()} permissions)"
                )
            )
