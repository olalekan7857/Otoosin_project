from .catalogue import build_storefront_catalog


def storefront_catalog(request):
    path = request.path
    if path.startswith("/staff/") or path.startswith("/admin/"):
        return {}
    return {"fd_catalog": build_storefront_catalog()}
