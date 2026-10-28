import json
import os
import shutil
import subprocess
import sys
import tempfile
from decimal import Decimal
from io import BytesIO

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, SimpleTestCase, TestCase, override_settings
from PIL import Image

from .models import Category, Inventory, Product, ProductImage, ProductVariant


def make_image(name="test.png", size=(4, 3)):
    buffer = BytesIO()
    Image.new("RGB", size, (12, 120, 40)).save(buffer, format="PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


def make_product(sku="PROD-001", category_slug="pork", **overrides):
    category = Category.objects.get(slug=category_slug)
    values = {
        "name": f"Product {sku}",
        "sku": sku,
        "category": category,
        "condition": Product.Condition.FRESH,
        "description": "Test product",
        "price_basis": "Per kilogram",
        "availability_status": Product.Availability.IN_STOCK,
    }
    values.update(overrides)
    return Product.objects.create(**values)


class CatalogueModelTests(TestCase):
    def test_canonical_categories_are_seeded(self):
        top_level = list(
            Category.objects.filter(parent__isnull=True).order_by("sort_order")
        )
        self.assertEqual(
            [category.name for category in top_level],
            ["Meats", "Fish", "Live Animals", "Eggs", "Veggies", "Fruits"],
        )
        meats = Category.objects.get(slug="meats")
        self.assertEqual(
            list(meats.children.values_list("name", flat=True)),
            ["Pork", "Chicken", "Turkey", "Beef", "Goat Meat"],
        )

    def test_live_condition_rules(self):
        live = make_product(
            sku="LIVE-001",
            category_slug="live-animals",
            condition=Product.Condition.LIVE,
        )
        live.full_clean()

        invalid = Product(
            name="Invalid live",
            sku="LIVE-002",
            category=Category.objects.get(slug="live-animals"),
            condition=Product.Condition.FRESH,
            description="Invalid",
            price_basis="Each",
        )
        with self.assertRaisesMessage(
            Exception, "Live Animals must use the Live condition"
        ):
            invalid.full_clean()

        invalid_non_live = Product(
            name="Invalid meat",
            sku="MEAT-002",
            category=Category.objects.get(slug="pork"),
            condition=Product.Condition.LIVE,
            description="Invalid",
            price_basis="Each",
        )
        with self.assertRaisesMessage(
            Exception, "only valid for Live Animals"
        ):
            invalid_non_live.full_clean()

    def test_only_one_default_variant(self):
        product = make_product()
        first = ProductVariant.objects.create(
            product=product,
            sku="PROD-001-1KG",
            label="1kg",
            unit_kind=ProductVariant.UnitKind.KG,
            price=Decimal("4800.00"),
            is_default=True,
        )
        second = ProductVariant.objects.create(
            product=product,
            sku="PROD-001-2KG",
            label="2kg",
            unit_kind=ProductVariant.UnitKind.KG,
            price=Decimal("9000.00"),
            is_default=True,
        )
        first.refresh_from_db()
        self.assertFalse(first.is_default)
        self.assertTrue(second.is_default)
        self.assertEqual(
            product.variants.filter(is_default=True).count(), 1
        )

    def test_primary_image_moves_and_reassigns_after_delete(self):
        product = make_product()
        first = ProductImage.objects.create(
            product=product, image=make_image("first.png"), alt="First"
        )
        self.assertTrue(first.is_primary)

        second = ProductImage.objects.create(
            product=product,
            image=make_image("second.png"),
            alt="Second",
            is_primary=True,
        )
        first.refresh_from_db()
        self.assertFalse(first.is_primary)
        self.assertTrue(second.is_primary)

        second.delete()
        first.refresh_from_db()
        self.assertTrue(first.is_primary)

    def test_untracked_inventory_is_not_out_of_stock(self):
        product = make_product()
        variant = ProductVariant.objects.create(
            product=product,
            sku="PROD-001-1KG",
            label="1kg",
            unit_kind=ProductVariant.UnitKind.KG,
            price=Decimal("4800.00"),
            is_default=True,
        )
        inventory = Inventory.objects.create(
            variant=variant, track_stock=False, quantity_available=0
        )
        self.assertFalse(inventory.is_out_of_stock)

    def test_duplicate_names_get_numbered_slugs(self):
        first = make_product(sku="SLUG-001", name="Pork Chops")
        second = make_product(sku="SLUG-002", name="Pork Chops")
        third = make_product(sku="SLUG-003", name="Pork Chops")
        self.assertEqual(first.slug, "pork-chops")
        self.assertEqual(second.slug, "pork-chops-1")
        self.assertEqual(third.slug, "pork-chops-2")


class StaffAccessTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.staff = User.objects.create_user(
            username="owner",
            password="strong-pass-123",
            is_staff=True,
            is_superuser=True,
        )
        self.plain_staff = User.objects.create_user(
            username="plain", password="strong-pass-123", is_staff=True
        )
        self.customer = User.objects.create_user(
            username="customer", password="strong-pass-123"
        )
        self.client = Client()

    def test_anonymous_redirected_to_staff_login(self):
        response = self.client.get("/staff/products/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/staff/login/", response["Location"])

    def test_non_staff_denied(self):
        self.client.force_login(self.customer)
        response = self.client.get("/staff/products/")
        self.assertEqual(response.status_code, 403)

    def test_staff_without_permission_denied(self):
        self.client.force_login(self.plain_staff)
        response = self.client.get("/staff/products/")
        self.assertEqual(response.status_code, 403)

    def test_superuser_can_open_product_pages(self):
        self.client.force_login(self.staff)
        for path in (
            "/staff/",
            "/staff/products/",
            "/staff/products/new/",
            "/staff/categories/",
            "/staff/inventory/",
        ):
            self.assertEqual(self.client.get(path).status_code, 200, path)

    def test_login_rejects_non_staff(self):
        response = self.client.post(
            "/staff/login/",
            {"username": "customer", "password": "strong-pass-123"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Please enter a correct")

    def test_login_accepts_staff(self):
        response = self.client.post(
            "/staff/login/",
            {
                "username": "owner",
                "password": "strong-pass-123",
                "next": "/staff/products/",
            },
        )
        self.assertRedirects(response, "/staff/products/")


class ProductAdminTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="owner",
            password="strong-pass-123",
            is_staff=True,
            is_superuser=True,
        )
        self.client = Client()
        self.client.force_login(self.user)
        self.media_dir = tempfile.mkdtemp()
        self.override = override_settings(MEDIA_ROOT=self.media_dir)
        self.override.enable()
        self.pork = Category.objects.get(slug="pork")

    def tearDown(self):
        self.override.disable()
        shutil.rmtree(self.media_dir, ignore_errors=True)

    def product_post_data(self):
        return {
            "name": "Admin Created Product",
            "slug": "",
            "sku": "ADMIN-001",
            "category": self.pork.pk,
            "condition": Product.Condition.FRESH,
            "cut": "Bone-in",
            "description": "Created from the custom admin.",
            "price_basis": "Per kilogram",
            "availability_status": Product.Availability.IN_STOCK,
            "badge": "",
            "is_active": "True",
            "is_featured": "False",
            "meta_title": "",
            "meta_description": "",
        }

    def test_create_product_with_variant_and_image(self):
        data = self.product_post_data()
        data.update(
            {
                "variants-TOTAL_FORMS": "1",
                "variants-INITIAL_FORMS": "0",
                "variants-MIN_NUM_FORMS": "0",
                "variants-MAX_NUM_FORMS": "1000",
                "variants-0-sku": "ADMIN-001-1KG",
                "variants-0-label": "1kg",
                "variants-0-unit_kind": ProductVariant.UnitKind.KG,
                "variants-0-price": "4800.00",
                "variants-0-is_default": "on",
                "variants-0-is_active": "on",
                "variants-0-sort_order": "1",
                "images-TOTAL_FORMS": "1",
                "images-INITIAL_FORMS": "0",
                "images-MIN_NUM_FORMS": "0",
                "images-MAX_NUM_FORMS": "1000",
                "images-0-image": make_image(),
                "images-0-alt": "Fresh pork chops",
                "images-0-sort_order": "1",
                "images-0-is_primary": "on",
            }
        )
        response = self.client.post(
            "/staff/products/new/", data, follow=False
        )
        self.assertEqual(response.status_code, 302)

        product = Product.objects.get(sku="ADMIN-001")
        self.assertEqual(product.variants.count(), 1)
        self.assertEqual(product.images.count(), 1)
        image = product.images.get()
        self.assertTrue(image.is_primary)
        self.assertEqual(image.alt, "Fresh pork chops")
        self.assertEqual(image.width, 4)
        self.assertEqual(image.height, 3)
        self.assertTrue(image.image.storage.exists(image.image.name))

    def test_featured_visibility_can_be_chosen(self):
        data = self.product_post_data()
        data.update(
            {
                "sku": "FEAT-001",
                "name": "Featured Product",
                "is_active": "False",
                "is_featured": "True",
                "variants-TOTAL_FORMS": "1",
                "variants-INITIAL_FORMS": "0",
                "variants-MIN_NUM_FORMS": "0",
                "variants-MAX_NUM_FORMS": "1000",
                "variants-0-sku": "FEAT-001-1KG",
                "variants-0-label": "1kg",
                "variants-0-unit_kind": ProductVariant.UnitKind.KG,
                "variants-0-price": "4800.00",
                "variants-0-is_default": "on",
                "variants-0-is_active": "on",
                "variants-0-sort_order": "1",
                "images-TOTAL_FORMS": "0",
                "images-INITIAL_FORMS": "0",
                "images-MIN_NUM_FORMS": "0",
                "images-MAX_NUM_FORMS": "1000",
            }
        )
        response = self.client.post("/staff/products/new/", data)
        self.assertEqual(response.status_code, 302)
        product = Product.objects.get(sku="FEAT-001")
        self.assertFalse(product.is_active)
        self.assertTrue(product.is_featured)

    def test_variant_sku_is_generated_when_left_blank(self):
        data = self.product_post_data()
        data.update(
            {
                "sku": "AUTO-001",
                "name": "Auto SKU Product",
                "variants-TOTAL_FORMS": "1",
                "variants-INITIAL_FORMS": "0",
                "variants-MIN_NUM_FORMS": "0",
                "variants-MAX_NUM_FORMS": "1000",
                "variants-0-sku": "",
                "variants-0-label": "1 kg",
                "variants-0-unit_kind": ProductVariant.UnitKind.KG,
                "variants-0-price": "4800.00",
                "variants-0-is_default": "on",
                "variants-0-is_active": "on",
                "variants-0-sort_order": "1",
                "images-TOTAL_FORMS": "0",
                "images-INITIAL_FORMS": "0",
                "images-MIN_NUM_FORMS": "0",
                "images-MAX_NUM_FORMS": "1000",
            }
        )
        response = self.client.post("/staff/products/new/", data)
        self.assertEqual(response.status_code, 302)
        variant = Product.objects.get(sku="AUTO-001").variants.get()
        self.assertEqual(variant.sku, "AUTO-001-1-KG")

    def test_product_code_and_price_basis_are_generated_when_left_blank(self):
        data = self.product_post_data()
        data.update(
            {
                "name": "Auto Product Details",
                "sku": "",
                "price_basis": "",
                "variants-TOTAL_FORMS": "1",
                "variants-INITIAL_FORMS": "0",
                "variants-MIN_NUM_FORMS": "0",
                "variants-MAX_NUM_FORMS": "1000",
                "variants-0-sku": "",
                "variants-0-label": "1 kg",
                "variants-0-unit_kind": ProductVariant.UnitKind.KG,
                "variants-0-price": "3500.00",
                "variants-0-is_default": "on",
                "variants-0-is_active": "on",
                "variants-0-sort_order": "1",
                "images-TOTAL_FORMS": "0",
                "images-INITIAL_FORMS": "0",
                "images-MIN_NUM_FORMS": "0",
                "images-MAX_NUM_FORMS": "1000",
            }
        )
        response = self.client.post("/staff/products/new/", data)
        self.assertEqual(response.status_code, 302)
        product = Product.objects.get(name="Auto Product Details")
        self.assertEqual(product.sku, "AUTO-PRODUCT-DETAILS")
        self.assertEqual(product.price_basis, "Per kilogram")

    def test_empty_extra_variant_and_image_rows_are_ignored(self):
        data = self.product_post_data()
        data.update(
            {
                "sku": "ADMIN-002",
                "name": "Admin Product With Blank Rows",
                "variants-TOTAL_FORMS": "3",
                "variants-INITIAL_FORMS": "0",
                "variants-MIN_NUM_FORMS": "0",
                "variants-MAX_NUM_FORMS": "1000",
                "variants-0-sku": "ADMIN-002-1KG",
                "variants-0-label": "1kg",
                "variants-0-unit_kind": ProductVariant.UnitKind.KG,
                "variants-0-price": "4800.00",
                "variants-0-is_default": "on",
                "variants-0-is_active": "on",
                "variants-0-sort_order": "1",
                "variants-1-sku": "",
                "variants-1-label": "",
                "variants-1-unit_kind": "",
                "variants-1-price": "",
                "variants-1-sort_order": "2",
                "variants-2-sku": "",
                "variants-2-label": "",
                "variants-2-unit_kind": "",
                "variants-2-price": "",
                "variants-2-sort_order": "3",
                "images-TOTAL_FORMS": "3",
                "images-INITIAL_FORMS": "0",
                "images-MIN_NUM_FORMS": "0",
                "images-MAX_NUM_FORMS": "1000",
                "images-0-alt": "",
                "images-0-sort_order": "1",
                "images-1-alt": "",
                "images-1-sort_order": "2",
                "images-2-alt": "",
                "images-2-sort_order": "3",
            }
        )
        response = self.client.post("/staff/products/new/", data)
        self.assertEqual(response.status_code, 302)
        product = Product.objects.get(sku="ADMIN-002")
        self.assertEqual(product.variants.count(), 1)
        self.assertEqual(product.images.count(), 0)

    def test_variant_defaults_are_chosen_when_ticks_are_missing(self):
        data = self.product_post_data()
        data.update(
            {
                "sku": "ADMIN-003",
                "name": "Admin Product Without Ticks",
                "variants-TOTAL_FORMS": "1",
                "variants-INITIAL_FORMS": "0",
                "variants-MIN_NUM_FORMS": "0",
                "variants-MAX_NUM_FORMS": "1000",
                "variants-0-sku": "ADMIN-003-1KG",
                "variants-0-label": "1kg",
                "variants-0-unit_kind": ProductVariant.UnitKind.KG,
                "variants-0-price": "4800.00",
                "variants-0-sort_order": "1",
                "images-TOTAL_FORMS": "1",
                "images-INITIAL_FORMS": "0",
                "images-MIN_NUM_FORMS": "0",
                "images-MAX_NUM_FORMS": "1000",
                "images-0-alt": "",
                "images-0-sort_order": "1",
            }
        )
        response = self.client.post("/staff/products/new/", data)
        self.assertEqual(response.status_code, 302)
        product = Product.objects.get(sku="ADMIN-003")
        variant = product.variants.get()
        self.assertTrue(variant.is_active)
        self.assertTrue(variant.is_default)

    def test_edit_preserves_existing_variant_and_image(self):
        product = make_product(sku="EDIT-001")
        variant = ProductVariant.objects.create(
            product=product,
            sku="EDIT-001-1KG",
            label="1kg",
            unit_kind=ProductVariant.UnitKind.KG,
            price=Decimal("4800.00"),
            is_default=True,
        )
        image = ProductImage.objects.create(
            product=product, image=make_image("keep.png"), alt="Keep me"
        )

        data = self.product_post_data()
        data.update(
            {
                "name": "Renamed Product",
                "slug": product.slug,
                "sku": product.sku,
                "category": product.category.pk,
                "variants-TOTAL_FORMS": "1",
                "variants-INITIAL_FORMS": "1",
                "variants-MIN_NUM_FORMS": "0",
                "variants-MAX_NUM_FORMS": "1000",
                "variants-0-id": variant.pk,
                "variants-0-sku": variant.sku,
                "variants-0-label": variant.label,
                "variants-0-unit_kind": variant.unit_kind,
                "variants-0-price": str(variant.price),
                "variants-0-is_default": "on",
                "variants-0-is_active": "on",
                "variants-0-sort_order": "1",
                "images-TOTAL_FORMS": "1",
                "images-INITIAL_FORMS": "1",
                "images-MIN_NUM_FORMS": "0",
                "images-MAX_NUM_FORMS": "1000",
                "images-0-id": image.pk,
                "images-0-alt": image.alt,
                "images-0-sort_order": "1",
                "images-0-is_primary": "on",
            }
        )
        response = self.client.post(
            f"/staff/products/{product.pk}/edit/", data
        )
        self.assertEqual(response.status_code, 302)

        product.refresh_from_db()
        self.assertEqual(product.name, "Renamed Product")
        self.assertEqual(product.variants.count(), 1)
        self.assertEqual(product.images.count(), 1)
        self.assertTrue(product.images.get().is_primary)

    def test_edit_form_shows_all_saved_values(self):
        product = make_product(
            name="Shown Product",
            sku="SHOW-001",
            description="Saved description.",
            cut="Bone-in",
            badge="Farm fresh",
            meta_title="Saved search title",
            meta_description="Saved search description.",
        )
        variant = ProductVariant.objects.create(
            product=product,
            sku="SHOW-001-1KG",
            label="1kg",
            unit_kind=ProductVariant.UnitKind.KG,
            price=Decimal("4800.00"),
            is_default=True,
        )
        ProductImage.objects.create(
            product=product,
            image=make_image("shown.png"),
            alt="Shown product photo",
            is_primary=True,
        )

        response = self.client.get(f"/staff/products/{product.pk}/edit/")
        self.assertEqual(response.status_code, 200)
        for value in (
            "Shown Product",
            "SHOW-001",
            "Saved description.",
            "Bone-in",
            "Farm fresh",
            "Saved search title",
            "Saved search description.",
            variant.label,
            variant.sku,
            "Shown product photo",
        ):
            self.assertContains(response, value)
        self.assertContains(response, "Saved product details are already loaded")
        self.assertContains(response, 'class="fd-edit-more" open')
        self.assertContains(response, "Saved variant code")
        self.assertContains(response, "Replace photo (optional)")
        self.assertContains(response, 'name="images-TOTAL_FORMS" value="1"')
        self.assertContains(response, 'name="images-0-image"')
        self.assertNotContains(response, 'name="images-1-image"')

    def test_create_form_has_one_blank_photo_row(self):
        response = self.client.get("/staff/products/new/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="images-TOTAL_FORMS" value="1"')
        self.assertContains(response, 'name="images-0-image"')
        self.assertNotContains(response, 'name="images-1-image"')

    def test_category_create_and_toggle(self):
        response = self.client.post(
            "/staff/categories/",
            {
                "action": "save",
                "name": "Test Produce",
                "slug": "",
                "parent": "",
                "kind": Category.Kind.VEGETABLES,
                "description": "Test category",
                "sort_order": "20",
                "is_active": "on",
                "meta_title": "",
                "meta_description": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        category = Category.objects.get(name="Test Produce")
        self.assertTrue(category.is_active)

        response = self.client.post(
            "/staff/categories/",
            {"action": "toggle", "category_id": category.pk},
        )
        self.assertEqual(response.status_code, 302)
        category.refresh_from_db()
        self.assertFalse(category.is_active)

    def test_subcategory_can_be_added_and_deleted_without_losing_parent(self):
        meats = Category.objects.get(slug="meats")
        response = self.client.post(
            "/staff/categories/",
            {
                "action": "save",
                "name": "Smoked Pork",
                "parent": meats.pk,
                "kind": Category.Kind.RED_MEAT,
                "description": "Smoked cuts",
                "sort_order": "50",
                "is_active": "on",
                "meta_title": "",
                "meta_description": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        child = Category.objects.get(name="Smoked Pork")
        self.assertEqual(child.parent, meats)

        response = self.client.post(
            "/staff/categories/",
            {"action": "delete", "category_id": meats.pk},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Category.objects.filter(pk=meats.pk).exists())

        response = self.client.post(
            "/staff/categories/",
            {"action": "delete", "category_id": child.pk},
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Category.objects.filter(pk=child.pk).exists())

    def test_admin_image_fields_use_uploader_widget(self):
        for path in ("/staff/categories/", "/staff/products/new/"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, path)
            self.assertContains(response, "data-image-upload", msg_prefix=path)
            self.assertContains(response, "data-image-input", msg_prefix=path)

    def test_inventory_update_persists(self):
        product = make_product(sku="INV-001")
        variant = ProductVariant.objects.create(
            product=product,
            sku="INV-001-1KG",
            label="1kg",
            unit_kind=ProductVariant.UnitKind.KG,
            price=Decimal("4800.00"),
            is_default=True,
        )
        response = self.client.post(
            "/staff/inventory/",
            {
                "product_id": product.pk,
                "availability_status": Product.Availability.LIMITED,
                "track_stock": "on",
                "quantity_available": "5.500",
                "low_stock_threshold": "2.000",
            },
        )
        self.assertEqual(response.status_code, 302)

        product.refresh_from_db()
        inventory = Inventory.objects.get(variant=variant)
        self.assertEqual(
            product.availability_status, Product.Availability.LIMITED
        )
        self.assertTrue(inventory.track_stock)
        self.assertEqual(inventory.quantity_available, Decimal("5.500"))

    def test_admin_product_list_paginates_thirty_per_page(self):
        for index in range(31):
            make_product(
                name=f"Paged Admin Product {index:02d}",
                sku=f"ADMIN-PAGE-{index:02d}",
            )
        response = self.client.get("/staff/products/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["paginator"].count, 31)
        self.assertEqual(response.context["paginator"].num_pages, 2)
        self.assertEqual(len(response.context["products"]), 30)
        self.assertContains(response, "page=2")

        response = self.client.get("/staff/products/?page=2")
        self.assertEqual(len(response.context["products"]), 1)

    def test_storefront_still_renders(self):
        for path in ("/", "/shop/", "/cart/", "/contact/"):
            self.assertEqual(self.client.get(path).status_code, 200, path)


class StorefrontCatalogueTests(TestCase):
    def setUp(self):
        self.pork = make_product(
            name="Pork Chops",
            sku="SHOP-PORK",
            category_slug="pork",
            description="Tender pork chops for the grill.",
            is_featured=True,
        )
        self.pork_variant = ProductVariant.objects.create(
            product=self.pork,
            sku="SHOP-PORK-1KG",
            label="1kg",
            unit_kind=ProductVariant.UnitKind.KG,
            price=Decimal("4800.00"),
            is_default=True,
        )
        self.chicken = make_product(
            name="Whole Chicken",
            sku="SHOP-CHICKEN",
            category_slug="chicken",
            condition=Product.Condition.FROZEN,
            description="A whole chicken for roasting.",
        )
        self.chicken_variant = ProductVariant.objects.create(
            product=self.chicken,
            sku="SHOP-CHICKEN-1KG",
            label="1kg",
            unit_kind=ProductVariant.UnitKind.KG,
            price=Decimal("3500.00"),
            is_default=True,
        )
        self.hidden = make_product(
            name="Hidden Product",
            sku="SHOP-HIDDEN",
            category_slug="beef",
            is_active=False,
        )
        ProductVariant.objects.create(
            product=self.hidden,
            sku="SHOP-HIDDEN-1KG",
            label="1kg",
            unit_kind=ProductVariant.UnitKind.KG,
            price=Decimal("1000.00"),
            is_default=True,
        )

    def test_home_renders_only_featured_database_products(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Popular Picks from O’TOOSIN Farms")
        self.assertContains(response, "Shop All Products")
        self.assertContains(response, "Pork Chops")
        self.assertContains(response, "Tender pork chops for the grill.")
        self.assertContains(response, "₦4,800")
        self.assertContains(response, "1kg")
        self.assertEqual(
            [product.pk for product in response.context["featured_products"]],
            [self.pork.pk],
        )
        self.assertNotContains(response, "Hidden Product")
        self.assertNotContains(response, "demo-pork-chops")
        self.assertNotContains(response, "Latest from the farm")
        self.assertNotContains(response, "Newly added products")
        self.assertContains(response, 'id="fd-storefront-catalog"')
        self.assertContains(response, "4800.0")

    def test_shop_filters_active_products_and_category(self):
        response = self.client.get("/shop/")
        self.assertContains(response, "Pork Chops")
        self.assertContains(response, "Whole Chicken")
        self.assertNotContains(response, "Hidden Product")

        response = self.client.get("/shop/?category=meats")
        self.assertContains(response, "Pork Chops")
        self.assertContains(response, "Whole Chicken")

        response = self.client.get("/shop/?q=chicken")
        names = [product.name for product in response.context["products"]]
        self.assertEqual(names, ["Whole Chicken"])

        response = self.client.get("/shop/?state=frozen")
        names = [product.name for product in response.context["products"]]
        self.assertEqual(names, ["Whole Chicken"])

    def test_shop_paginates_twenty_products_per_page(self):
        for index in range(23):
            product = make_product(
                name=f"Extra Shop Product {index:02d}",
                sku=f"SHOP-EXTRA-{index:02d}",
                category_slug="pork",
            )
            ProductVariant.objects.create(
                product=product,
                sku=f"SHOP-EXTRA-{index:02d}-1KG",
                label="1kg",
                unit_kind=ProductVariant.UnitKind.KG,
                price=Decimal("2500.00"),
                is_default=True,
            )
        response = self.client.get("/shop/")
        self.assertEqual(response.context["paginator"].count, 25)
        self.assertEqual(response.context["paginator"].num_pages, 2)
        self.assertEqual(len(response.context["products"]), 20)
        self.assertContains(response, "fd-pagination")
        self.assertContains(response, "page=2")

        response = self.client.get("/shop/?page=2")
        self.assertEqual(len(response.context["products"]), 5)

    def test_home_featured_products_and_related_products_are_limited(self):
        for index in range(7):
            product = make_product(
                name=f"Featured Farm Product {index:02d}",
                sku=f"SHOP-FEATURED-{index:02d}",
                category_slug="pork",
                is_featured=True,
            )
            ProductVariant.objects.create(
                product=product,
                sku=f"SHOP-FEATURED-{index:02d}-1KG",
                label="1kg",
                unit_kind=ProductVariant.UnitKind.KG,
                price=Decimal("3000.00"),
                is_default=True,
            )

        response = self.client.get("/")
        self.assertEqual(len(response.context["featured_products"]), 8)
        self.assertNotIn("latest_products", response.context)
        self.assertNotContains(response, "Latest from the farm")
        self.assertNotIn(
            self.chicken.pk,
            [product.pk for product in response.context["featured_products"]],
        )

        response = self.client.get(
            f"/product-details/?id={self.pork.slug}"
        )
        related = response.context["related_products"]
        self.assertEqual(len(related), 4)
        self.assertNotIn(self.pork.pk, [product.pk for product in related])
        self.assertTrue(
            all(product.category_id == self.pork.category_id for product in related)
        )

    def test_category_page_renders_products_and_counts(self):
        response = self.client.get("/category/?category=Pork")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Shop Pork")
        names = [product.name for product in response.context["products"]]
        self.assertEqual(names, ["Pork Chops"])
        self.assertContains(response, "1 product")

        response = self.client.get("/category/?category=meats")
        self.assertContains(response, "Pork Chops")
        self.assertContains(response, "Whole Chicken")

    def test_product_details_uses_database_product(self):
        response = self.client.get(f"/product-details/?id={self.pork.slug}")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Pork Chops")
        self.assertContains(response, "Tender pork chops for the grill.")
        self.assertContains(response, "₦4,800")
        self.assertContains(response, "fd-pdp-jsonld")
        self.assertContains(response, "1kg")

        response = self.client.get("/product-details/?id=does-not-exist")
        self.assertEqual(response.status_code, 404)
        self.assertContains(response, "Product not found", status_code=404)

    def test_catalogue_feed_only_contains_public_products(self):
        response = self.client.get("/shop/")
        catalog = response.context["fd_catalog"]
        self.assertIn(self.pork.slug, catalog)
        self.assertIn(self.chicken.slug, catalog)
        self.assertNotIn(self.hidden.slug, catalog)
        self.assertEqual(catalog[self.pork.slug]["id"], self.pork.slug)
        self.assertEqual(
            catalog[self.pork.slug]["defaultVariant"],
            str(self.pork_variant.pk),
        )
        self.assertEqual(catalog[self.pork.slug]["variants"][0]["price"], 4800.0)

    def test_inactive_category_hides_products_from_storefront(self):
        Category.objects.filter(slug="meats").update(is_active=False)
        response = self.client.get("/shop/")
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Pork Chops")
        self.assertNotContains(response, "Whole Chicken")
        self.assertNotIn(self.pork.slug, response.context["fd_catalog"])

    def test_empty_catalogue_shows_empty_states(self):
        Product.objects.all().delete()
        for path, message in (
            ("/", "No products available yet"),
            ("/shop/", "No products available yet"),
            ("/category/", "No products available yet"),
        ):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, path)
            self.assertContains(response, message)
            self.assertNotContains(response, "demo-pork-chops")

    def test_cart_template_does_not_seed_demo_lines(self):
        Product.objects.all().delete()
        response = self.client.get("/cart/")
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'class="fd-cartpage-item"')
        self.assertNotContains(response, "₦7,200")
        self.assertContains(response, "Your cart is empty")


class CartValidationTests(TestCase):
    def setUp(self):
        self.product = make_product(
            name="Cart Pork",
            sku="CART-PORK",
            category_slug="pork",
            description="Cart validation test product.",
        )
        self.variant = ProductVariant.objects.create(
            product=self.product,
            sku="CART-PORK-1KG",
            label="1kg",
            unit_kind=ProductVariant.UnitKind.KG,
            price=Decimal("4800.00"),
            is_default=True,
        )
        self.inventory = Inventory.objects.create(
            variant=self.variant,
            track_stock=True,
            quantity_available=Decimal("3.500"),
        )
        self.piece_product = make_product(
            name="Cart Eggs",
            sku="CART-EGGS",
            category_slug="eggs",
            description="Cart piece validation test product.",
        )
        self.piece_variant = ProductVariant.objects.create(
            product=self.piece_product,
            sku="CART-EGGS-CRATE",
            label="Crate",
            unit_kind=ProductVariant.UnitKind.CRATE,
            price=Decimal("2500.00"),
            is_default=True,
        )

    def post_cart(self, items, path="/api/cart/validate/"):
        return self.client.post(
            path,
            data=json.dumps({"items": items}),
            content_type="application/json",
        )

    def line(self, quantity, product=None, variant=None, price=None):
        product = self.product if product is None else product
        variant_ref = str(self.variant.pk) if variant is None else (
            str(variant.pk) if hasattr(variant, "pk") else str(variant)
        )
        payload = {
            "product": product.slug,
            "variant": variant_ref,
            "quantity": quantity,
        }
        if price is not None:
            payload["price"] = price
        return payload

    def test_valid_line_uses_database_price_and_accepts_default_variant(self):
        response = self.post_cart([self.line("1.5", variant="", price="1")])
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertEqual(len(data["items"]), 1)
        item = data["items"][0]
        self.assertEqual(item["variantId"], str(self.variant.pk))
        self.assertEqual(item["price"], 4800.0)
        self.assertEqual(item["qty"], 1.5)
        self.assertEqual(data["subtotal"], 7200.0)

    def test_quantity_update_and_removal_revalidate_remaining_lines(self):
        response = self.post_cart([self.line("2")])
        self.assertEqual(response.json()["subtotal"], 9600.0)

        response = self.post_cart([])
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["items"], [])
        self.assertEqual(data["line_count"], 0)
        self.assertTrue(data["ok"])

    def test_unknown_product_and_inactive_variant_are_rejected(self):
        response = self.post_cart(
            [
                {"product": "does-not-exist", "quantity": 1},
                self.line("1", variant="999999"),
            ]
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["items"], [])
        self.assertEqual(len(data["errors"]), 2)

        self.variant.is_active = False
        self.variant.save(update_fields=["is_active"])
        response = self.post_cart([self.line("1")])
        self.assertEqual(response.json()["items"], [])

    def test_invalid_quantities_are_rejected(self):
        for quantity in (0, -1, "0.25"):
            response = self.post_cart([self.line(quantity)])
            self.assertFalse(response.json()["ok"], quantity)
            self.assertEqual(response.json()["items"], [], quantity)

        response = self.post_cart(
            [
                self.line(
                    "1.5",
                    product=self.piece_product,
                    variant=self.piece_variant,
                )
            ]
        )
        data = response.json()
        self.assertFalse(data["ok"])
        self.assertEqual(data["items"], [])
        self.assertIn("whole units", data["errors"][0]["message"])

    def test_stock_is_clamped_for_cart_and_rejected_at_checkout(self):
        response = self.post_cart([self.line("5")])
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["items"][0]["qty"], 3.5)
        self.assertEqual(data["subtotal"], 16800.0)
        self.assertTrue(data["notices"])

        response = self.post_cart(
            [self.line("5")], path="/api/cart/checkout/"
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data["ok"])
        self.assertIn("Only 3.50 kg", data["errors"][0]["message"])

    def test_price_change_is_reported_and_database_price_wins(self):
        response = self.post_cart([self.line("1", price="100")])
        data = response.json()
        self.assertEqual(data["items"][0]["price"], 4800.0)
        self.assertEqual(data["subtotal"], 4800.0)
        self.assertTrue(
            any("price" in notice["message"].lower() for notice in data["notices"])
        )

    def test_checkout_accepts_valid_cart_and_reports_out_of_stock(self):
        response = self.post_cart(
            [self.line("2")], path="/api/cart/checkout/"
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])

        self.product.availability_status = Product.Availability.OUT_OF_STOCK
        self.product.save(update_fields=["availability_status"])
        response = self.post_cart(
            [self.line("2")], path="/api/cart/checkout/"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("out of stock", response.json()["errors"][0]["message"])


class SettingsEnvironmentTests(SimpleTestCase):
    settings_script = (
        "import json\n"
        "from django.conf import settings\n"
        "print(json.dumps({\n"
        "    'debug': settings.DEBUG,\n"
        "    'allowed_hosts': settings.ALLOWED_HOSTS,\n"
        "    'csrf_trusted_origins': settings.CSRF_TRUSTED_ORIGINS,\n"
        "    'time_zone': settings.TIME_ZONE,\n"
        "    'use_tz': settings.USE_TZ,\n"
        "}))"
    )

    def run_settings(self, **overrides):
        environment = os.environ.copy()
        environment.update(
            {
                "DJANGO_SETTINGS_MODULE": "Otoosin_project.settings",
                "SECRET_KEY": "test-settings-secret",
                "DEBUG": "True",
                "ALLOWED_HOSTS": "localhost",
                "CSRF_TRUSTED_ORIGINS": "http://localhost:8000",
                "PYTHONIOENCODING": "utf-8",
            }
        )
        environment.update(overrides)
        return subprocess.run(
            [sys.executable, "-c", self.settings_script],
            cwd=settings.BASE_DIR,
            env=environment,
            capture_output=True,
            text=True,
            timeout=30,
        )

    def test_environment_values_are_parsed_and_validated(self):
        result = self.run_settings(
            DEBUG="False",
            SECRET_KEY="production-settings-secret",
            ALLOWED_HOSTS="farm.example.com, 127.0.0.1",
            CSRF_TRUSTED_ORIGINS=(
                "https://farm.example.com/,"
                "https://www.farm.example.com"
            ),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertFalse(data["debug"])
        self.assertEqual(
            data["allowed_hosts"], ["farm.example.com", "127.0.0.1"]
        )
        self.assertEqual(
            data["csrf_trusted_origins"],
            [
                "https://farm.example.com",
                "https://www.farm.example.com",
            ],
        )
        self.assertEqual(data["time_zone"], "Africa/Lagos")
        self.assertTrue(data["use_tz"])

    def test_production_requires_a_secret_key(self):
        result = self.run_settings(
            DEBUG="False",
            SECRET_KEY=" ",
            ALLOWED_HOSTS="farm.example.com",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SECRET_KEY must be set", result.stderr)
        self.assertNotIn("production-settings-secret", result.stderr)

    def test_production_requires_allowed_hosts(self):
        result = self.run_settings(
            DEBUG="False",
            SECRET_KEY="production-settings-secret",
            ALLOWED_HOSTS=" ",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ALLOWED_HOSTS must be set", result.stderr)

    def test_invalid_csrf_origin_is_rejected(self):
        result = self.run_settings(
            DEBUG="False",
            SECRET_KEY="production-settings-secret",
            ALLOWED_HOSTS="farm.example.com",
            CSRF_TRUSTED_ORIGINS="farm.example.com",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "CSRF_TRUSTED_ORIGINS entries must be", result.stderr
        )
