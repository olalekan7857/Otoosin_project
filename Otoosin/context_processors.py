from .catalogue import build_storefront_catalog
from .models import PickupLocation, SiteConfiguration


def storefront_catalog(request):
    path = request.path
    if path.startswith("/staff/") or path.startswith("/admin/"):
        return {}
    return {"fd_catalog": build_storefront_catalog()}


def storefront_settings(request):
    if request.path.startswith("/admin/"):
        return {}
    return {
        "site_config": SiteConfiguration.load(),
        "active_pickup_locations": PickupLocation.objects.filter(
            is_active=True
        ).order_by("sort_order", "name"),
    }
