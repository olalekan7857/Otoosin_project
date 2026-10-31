"""Small, database-safe SEO context helpers for public storefront pages."""

from urllib.parse import urlencode

from django.conf import settings
from django.templatetags.static import static


DEFAULT_DESCRIPTION = (
    "O’Toosin Farms delivers safe, healthy and nutritious foods to your "
    "doorstep. Shop pork, chicken, turkey, beef, goat meat, fish, live "
    "animals, eggs, veggies and fruits."
)


def absolute_url(path):
    base = (getattr(settings, "SITE_URL", "") or "").rstrip("/")
    return f"{base}{path}" if base else path


def canonical_url(path, params=None):
    query = {
        key: value
        for key, value in (params or {}).items()
        if value not in (None, "")
    }
    url = path or ""
    if query:
        url = f"{url}?{urlencode(query)}"
    return absolute_url(url) if url else ""


def default_image_url():
    return absolute_url(static("assets/img/categorie/otoosin-farms.png"))


def seo_context(
    *,
    title,
    description=DEFAULT_DESCRIPTION,
    path="/",
    params=None,
    robots="index,follow",
    og_type="website",
    image=None,
):
    """Return a ``seo`` context dictionary consumed by ``layout.html``."""
    return {
        "seo": {
            "title": title,
            "description": description,
            "canonical": canonical_url(path, params) if path else "",
            "robots": robots,
            "og_type": og_type,
            "image": image or default_image_url(),
        }
    }
