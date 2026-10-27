from django.contrib import admin

from .models import Category, Inventory, Product, ProductImage, ProductVariant


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 0


class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 0


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "kind", "parent", "sort_order", "is_active")
    list_filter = ("kind", "is_active", "parent")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "sku",
        "category",
        "condition",
        "availability_status",
        "is_active",
    )
    list_filter = ("condition", "availability_status", "is_active", "category")
    search_fields = ("name", "sku", "description")
    inlines = [ProductVariantInline, ProductImageInline]


@admin.register(ProductVariant)
class ProductVariantAdmin(admin.ModelAdmin):
    list_display = ("sku", "product", "label", "price", "is_default", "is_active")
    list_filter = ("is_default", "is_active", "unit_kind")
    search_fields = ("sku", "label", "product__name")


@admin.register(Inventory)
class InventoryAdmin(admin.ModelAdmin):
    list_display = (
        "variant",
        "track_stock",
        "quantity_available",
        "low_stock_threshold",
        "updated_at",
    )
    list_filter = ("track_stock",)
