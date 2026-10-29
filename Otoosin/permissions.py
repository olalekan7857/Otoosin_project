from django.contrib.auth.models import Group, Permission

ROLE_GROUPS = {
    "owner": "Owner",
    "manager": "Manager",
    "fulfilment": "Fulfilment",
    "support": "Support",
}

MANAGER_CODENAMES = {
    "add_category",
    "change_category",
    "delete_category",
    "view_category",
    "add_product",
    "change_product",
    "delete_product",
    "view_product",
    "add_productvariant",
    "change_productvariant",
    "delete_productvariant",
    "view_productvariant",
    "add_productimage",
    "change_productimage",
    "delete_productimage",
    "view_productimage",
    "add_inventory",
    "change_inventory",
    "view_inventory",
    "add_deliverylocation",
    "change_deliverylocation",
    "view_deliverylocation",
    "add_pickuplocation",
    "change_pickuplocation",
    "view_pickuplocation",
    "change_siteconfiguration",
    "view_siteconfiguration",
    "view_contactmessage",
    "change_contactmessage",
    "view_order",
    "change_order",
    "view_orderitem",
    "view_payment",
    "view_orderstatusevent",
    "change_order_status",
}

SUPPORT_CODENAMES = {"view_contactmessage", "change_contactmessage"}

FULFILMENT_CODENAMES = {
    "view_order",
    "view_orderitem",
    "view_payment",
    "view_orderstatusevent",
    "change_order_status",
}


def _app_permissions(codenames=None):
    queryset = Permission.objects.filter(content_type__app_label="Otoosin")
    if codenames is not None:
        queryset = queryset.filter(codename__in=codenames)
    return queryset


def provision_staff_roles():
    """Create role groups and add missing permissions safely and repeatably.

    Permissions are only added, never removed, so custom grants made outside
    this helper are preserved. Owner is the only role that can manage staff.
    """
    result = {}
    for role, group_name in ROLE_GROUPS.items():
        group, _ = Group.objects.get_or_create(name=group_name)
        if role == "owner":
            permissions = _app_permissions()
        elif role == "manager":
            permissions = _app_permissions(MANAGER_CODENAMES)
        elif role == "support":
            permissions = _app_permissions(SUPPORT_CODENAMES)
        else:
            permissions = _app_permissions(FULFILMENT_CODENAMES)
        group.permissions.add(*permissions)
        result[role] = group
    return result
