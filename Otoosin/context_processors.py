from .catalogue import build_storefront_catalog
from .models import (
    Category,
    LegalDocument,
    Order,
    PickupLocation,
    SiteConfiguration,
)


def storefront_catalog(request):
    path = request.path
    if path.startswith("/staff/") or path.startswith("/admin/"):
        return {}
    return {"fd_catalog": build_storefront_catalog()}


def admin_pending_orders(request):
    """Expose the live pending-order count to the shared admin navigation."""
    if not request.path.startswith("/staff/"):
        return {}
    user = getattr(request, "user", None)
    if (
        not user
        or not user.is_authenticated
        or not user.is_active
        or not user.is_staff
        or not user.has_perm("Otoosin.view_order")
    ):
        return {"admin_pending_orders_count": 0}
    return {
        "admin_pending_orders_count": Order.objects.filter(
            status=Order.Status.PENDING
        ).count()
    }


def storefront_settings(request):
    if request.path.startswith("/admin/"):
        return {}
    legal_pages = dict(
        LegalDocument.objects.filter(is_published=True).values_list(
            "slug", "title"
        )
    )
    return {
        "site_config": SiteConfiguration.load(),
        "active_pickup_locations": PickupLocation.objects.filter(
            is_active=True
        ).order_by("sort_order", "name"),
        "legal_pages": legal_pages,
        "nav_categories": Category.objects.filter(
            parent__isnull=True, is_active=True
        ).order_by("sort_order", "name"),
    }
