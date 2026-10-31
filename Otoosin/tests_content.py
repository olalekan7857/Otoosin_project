from decimal import Decimal

from django.test import TestCase, override_settings

from .models import Category, Product, ProductVariant, SiteConfiguration


SITE = "https://otoosinfarms.example"


@override_settings(SITE_URL=SITE)
class ContentAndSeoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        config = SiteConfiguration.load()
        config.business_name = "O’Toosin Farms"
        config.address = "14 Farm Settlement Road, Abeokuta, Ogun"
        config.contact_phone = "08031234567"
        config.whatsapp_number = "08031234567"
        config.support_email = "support@otoosinfarms.example"
        config.description = "Farm-fresh meats, fish, eggs, vegetables and fruits."
        config.full_clean()
        config.save()

        cls.category = Category.objects.create(
            name="Chicken",
            slug="content-chicken",
            kind=Category.Kind.POULTRY,
            description="Fresh and frozen chicken for household meals.",
            meta_title="Buy Chicken | O’Toosin Farms",
            meta_description="Shop fresh and frozen chicken from O’Toosin Farms.",
        )
        cls.product = Product.objects.create(
            name="Whole Chicken",
            slug="content-whole-chicken",
            sku="CONTENT-CHK-WHOLE",
            category=cls.category,
            condition=Product.Condition.FRESH,
            description="A whole fresh chicken prepared for household cooking.",
            price_basis="per kg",
            meta_title="Buy Whole Chicken | O’Toosin Farms",
            meta_description="Order a whole fresh chicken from O’Toosin Farms.",
        )
        ProductVariant.objects.create(
            product=cls.product,
            sku="CONTENT-CHK-WHOLE-1KG",
            label="1 kg",
            unit_kind=ProductVariant.UnitKind.KG,
            price=Decimal("2500.00"),
            is_default=True,
        )

        cls.inactive_category = Category.objects.create(
            name="Archive",
            slug="content-archive",
            kind=Category.Kind.EGGS,
            is_active=False,
        )
        cls.inactive_product = Product.objects.create(
            name="Archived Eggs",
            slug="content-archived-eggs",
            sku="CONTENT-EGG-ARCHIVE",
            category=cls.category,
            condition=Product.Condition.FRESH,
            description="An inactive product used only for sitemap exclusion.",
            price_basis="per crate",
            is_active=False,
        )
        ProductVariant.objects.create(
            product=cls.inactive_product,
            sku="CONTENT-EGG-ARCHIVE-CRATE",
            label="1 crate",
            unit_kind=ProductVariant.UnitKind.CRATE,
            price=Decimal("3000.00"),
            is_default=True,
        )

    def test_public_pages_render_with_canonical_and_description(self):
        paths = [
            "/",
            "/about/",
            "/contact/",
            "/privacy/",
            "/terms/",
            "/shop/",
            "/category/?category=content-chicken",
            "/product-details/?id=content-whole-chicken",
        ]
        for path in paths:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, '<link rel="canonical"')
                self.assertContains(response, '<meta name="description"')
                self.assertContains(response, SITE)

    def test_business_settings_propagate_to_contact_page(self):
        response = self.client.get("/contact/")
        self.assertContains(response, "O’Toosin Farms")
        self.assertContains(response, "14 Farm Settlement Road")
        self.assertContains(response, "+2348031234567")
        self.assertContains(response, "support@otoosinfarms.example")
        self.assertContains(response, "https://wa.me/2348031234567")
        self.assertContains(
            response, "Farm-fresh meats, fish, eggs, vegetables and fruits."
        )

    def test_product_seo_uses_database_metadata(self):
        response = self.client.get("/product-details/?id=content-whole-chicken")
        self.assertContains(
            response,
            "<title>Buy Whole Chicken | O’Toosin Farms</title>",
            html=True,
        )
        self.assertContains(
            response,
            '<meta name="description" content="Order a whole fresh chicken '
            'from O’Toosin Farms.">',
            html=True,
        )
        self.assertContains(
            response,
            f'<link rel="canonical" href="{SITE}/product-details/?id=content-whole-chicken">',
            html=True,
        )
        self.assertContains(
            response, '<meta property="og:type" content="product">'
        )
        self.assertContains(response, "CONTENT-CHK-WHOLE-1KG")
        self.assertContains(response, "2500.0")

    def test_category_seo_uses_database_metadata(self):
        response = self.client.get("/category/?category=content-chicken")
        self.assertContains(
            response, "<title>Buy Chicken | O’Toosin Farms</title>", html=True
        )
        self.assertContains(
            response,
            f'<link rel="canonical" href="{SITE}/category/?category=content-chicken">',
            html=True,
        )
        self.assertContains(
            response,
            '<meta name="description" content="Shop fresh and frozen chicken '
            'from O’Toosin Farms.">',
            html=True,
        )

    def test_private_and_sensitive_pages_are_noindex(self):
        for path in ("/cart/", "/checkout/"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "noindex,nofollow")
                self.assertEqual(
                    response.headers.get("X-Robots-Tag"),
                    "noindex, nofollow",
                )

        for path in ("/order-confirmation/", "/missing-page/"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 404)
                self.assertContains(
                    response, "noindex,nofollow", status_code=404
                )

    def test_robots_txt_allows_storefront_and_blocks_private_routes(self):
        response = self.client.get("/robots.txt")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response["Content-Type"].startswith("text/plain"))
        body = response.content.decode()
        self.assertIn("User-agent: *", body)
        self.assertIn("Allow: /", body)
        self.assertIn("Disallow: /staff/", body)
        self.assertIn("Disallow: /admin/", body)
        self.assertIn("Disallow: /cart/", body)
        self.assertIn("Disallow: /checkout/", body)
        self.assertIn("Disallow: /order-confirmation/", body)
        self.assertIn("Disallow: /payments/", body)
        self.assertIn("Disallow: /api/", body)
        self.assertNotIn("Disallow: /\n", body)
        self.assertIn(f"Sitemap: {SITE}/sitemap.xml", body)

    def test_sitemap_includes_public_content_and_excludes_private_routes(self):
        response = self.client.get("/sitemap.xml")
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        for public_url in (
            f"{SITE}/",
            f"{SITE}/shop/",
            f"{SITE}/about/",
            f"{SITE}/contact/",
            f"{SITE}/privacy/",
            f"{SITE}/terms/",
            f"{SITE}/category/?category=content-chicken",
            f"{SITE}/product-details/?id=content-whole-chicken",
        ):
            self.assertIn(public_url, body)
        for private_path in (
            "/staff/",
            "/admin/",
            "/cart/",
            "/checkout/",
            "/order-confirmation/",
            "/payments/",
            "/api/",
            "content-archived-eggs",
            "category=content-archive",
        ):
            self.assertNotIn(private_path, body)

    def test_legacy_urls_redirect_permanently_and_preserve_filters(self):
        cases = [
            ("/index.html", "/"),
            ("/about.html", "/about/"),
            ("/privacy.html", "/privacy/"),
            ("/terms.html", "/terms/"),
            ("/cart.html", "/cart/"),
            ("/checkout.html", "/checkout/"),
            (
                "/product-details.html?id=content-whole-chicken",
                "/product-details/?id=content-whole-chicken",
            ),
            (
                "/order-confirmation.html?order=OF-LEGACY123",
                "/order-confirmation/OF-LEGACY123/",
            ),
        ]
        for source, expected in cases:
            with self.subTest(source=source):
                response = self.client.get(source)
                self.assertEqual(response.status_code, 301)
                self.assertEqual(response["Location"], expected)

        response = self.client.get(
            "/product.html?q=chicken&category=Chicken&state=fresh"
            "&sort=price&page=2&utm_source=old"
        )
        self.assertEqual(response.status_code, 301)
        self.assertEqual(
            response["Location"],
            "/shop/?q=chicken&category=Chicken&state=fresh"
            "&sort=price&page=2",
        )

        response = self.client.get(
            "/product-category.html?category=Chicken&state=frozen"
        )
        self.assertEqual(response.status_code, 301)
        self.assertEqual(
            response["Location"],
            "/category/?category=Chicken&state=frozen",
        )

    def test_unknown_legacy_and_invalid_urls_are_not_redirected_home(self):
        for path in ("/made-up.html", "/not-a-real-page/"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 404)
                self.assertNotIn("Location", response)
