from django.contrib.staticfiles import finders
from django.template.loader import render_to_string
from django.test import SimpleTestCase, override_settings

from .models import ProductImage


class CustomErrorPageTests(SimpleTestCase):
    @override_settings(
        STORAGES={
            "default": {
                "BACKEND": "django.core.files.storage.FileSystemStorage",
            },
            "staticfiles": {
                "BACKEND": (
                    "django.contrib.staticfiles.storage.StaticFilesStorage"
                ),
            },
        }
    )
    def test_500_page_renders_without_request_context_or_site_config(self):
        html = render_to_string("500.html")
        self.assertIn("Something Went Wrong", html)
        self.assertIn("Back to Home", html)


class StaticAssetReferenceTests(SimpleTestCase):
    referenced_assets = (
        "assets/img/harvest_castle/of_favicon.png",
        "assets/img/categorie/otoosin-live-animals.webp",
        "assets/img/categorie/otoosin-veggies.webp",
        "assets/img/categorie/fish-meat.webp",
        "assets/img/categorie/otoosin-eggs.webp",
        "assets/img/categorie/otoosin-fruits.webp",
        "assets/img/hero/oto-hero-meat.jpg",
        "assets/fonts/fa-brands-400.woff2",
        "assets/fonts/fa-solid-900.woff2",
    )

    def test_referenced_assets_exist_in_static_sources(self):
        for path in self.referenced_assets:
            self.assertIsNotNone(finders.find(path), path)


class ProductMediaUrlTests(SimpleTestCase):
    @override_settings(MEDIA_URL="/media/")
    def test_product_image_url_uses_configured_media_url(self):
        image = ProductImage(image="products/2026/11/1003961.jpg")
        self.assertEqual(
            image.image.url,
            "/media/products/2026/11/1003961.jpg",
        )
