from django.db.models.signals import post_migrate
from django.dispatch import receiver

from .permissions import provision_staff_roles


@receiver(post_migrate)
def provision_roles_after_migrate(sender, **kwargs):
    if getattr(sender, "label", None) != "Otoosin":
        return
    provision_staff_roles()
