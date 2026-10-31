"""Public sitemap definitions for the O'Toosin Farms storefront."""

from urllib.parse import urlsplit

from django.conf import settings
from django.contrib.sitemaps import Sitemap
from django.db.models import Q
from django.urls import reverse

from .catalogue import category_url, product_url, public_products
from .models import Category


class AbsoluteSitemap(Sitemap):
    """Build locations from the configured public SITE_URL."""

    def get_urls(self, site=None, protocol=None):
        urls = super().get_urls(site=site, protocol=protocol)
        base = (getattr(settings, "SITE_URL", "") or "").rstrip("/")
        if not base:
            return urls
        for item in urls:
            parsed = urlsplit(item["location"])
            path = parsed.path or "/"
            query = f"?{parsed.query}" if parsed.query else ""
            item["location"] = f"{base}{path}{query}"
        return urls


class PublicStaticSitemap(AbsoluteSitemap):
    changefreq = "weekly"
    priority = 0.8

    def items(self):
        return [
            ("Otoosin:index", 1.0, "daily"),
            ("Otoosin:product", 0.9, "daily"),
            ("Otoosin:about", 0.6, "monthly"),
            ("Otoosin:contact", 0.6, "monthly"),
            ("Otoosin:privacy", 0.3, "yearly"),
            ("Otoosin:terms", 0.3, "yearly"),
        ]

    def location(self, item):
        return reverse(item[0])

    def priority(self, item):
        return item[1]

    def changefreq(self, item):
        return item[2]


class PublicCategorySitemap(AbsoluteSitemap):
    changefreq = "weekly"
    priority = 0.7

    def items(self):
        return (
            Category.objects.filter(is_active=True)
            .filter(
                Q(parent__isnull=True) | Q(parent__is_active=True)
            )
            .order_by("sort_order", "name")
        )

    def location(self, category):
        return category_url(category)

    def lastmod(self, category):
        return category.updated_at


class PublicProductSitemap(AbsoluteSitemap):
    changefreq = "weekly"
    priority = 0.8

    def items(self):
        return public_products().order_by("pk")

    def location(self, product):
        return product_url(product)

    def lastmod(self, product):
        return product.updated_at


SITEMAPS = {
    "static": PublicStaticSitemap,
    "categories": PublicCategorySitemap,
    "products": PublicProductSitemap,
}
