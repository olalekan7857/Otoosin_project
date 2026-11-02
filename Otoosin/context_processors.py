from .catalogue import build_storefront_catalog
from .models import Category, LegalDocument, PickupLocation, SiteConfiguration


def storefront_catalog(request):
    path = request.path
    if path.startswith("/staff/") or path.startswith("/admin/"):
        return {}
    return {"fd_catalog": build_storefront_catalog()}


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
