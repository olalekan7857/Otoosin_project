from urllib.parse import urlencode

from django.db.models import Prefetch, Q
from django.templatetags.static import static
from django.urls import reverse

from .models import Category, Product, ProductVariant


PLACEHOLDER_IMAGE = static("assets/img/categorie/otoosin-farms.png")

GROUP_LABELS = {
    Category.Kind.RED_MEAT: "Red meat",
    Category.Kind.POULTRY: "Poultry",
    Category.Kind.SEAFOOD: "Seafood",
    Category.Kind.LIVE_ANIMAL: "Farm animals",
    Category.Kind.EGGS: "Farm produce",
    Category.Kind.VEGETABLES: "Farm produce",
    Category.Kind.FRUITS: "Farm produce",
}

UNIT_LABELS = {
    ProductVariant.UnitKind.KG: "per kg",
    ProductVariant.UnitKind.PIECE: "per piece",
    ProductVariant.UnitKind.CRATE: "per crate",
    ProductVariant.UnitKind.BASKET: "per basket",
    ProductVariant.UnitKind.PACK: "per pack",
    ProductVariant.UnitKind.LIVE_ANIMAL: "per live animal",
}


def public_products():
    variants = ProductVariant.objects.filter(is_active=True).order_by(
        "-is_default", "sort_order", "pk"
    )
    return (
        Product.objects.filter(
            is_active=True,
            variants__is_active=True,
            category__is_active=True,
        )
        .filter(
            Q(category__parent__isnull=True) | Q(category__parent__is_active=True)
        )
        .select_related("category", "category__parent")
        .prefetch_related(
            Prefetch("variants", queryset=variants),
            "images",
        )
        .distinct()
    )


def product_group(product):
    if not product.category_id:
        return ""
    return GROUP_LABELS.get(product.category.kind, product.category.name)


def product_url(product):
    return reverse("Otoosin:product_details") + "?" + urlencode(
        {"id": product.slug}
    )


def category_url(category):
    return reverse("Otoosin:product_category") + "?" + urlencode(
        {"category": category.slug}
    )


def _serialise_image(image):
    return {
        "src": image.image.url,
        "alt": image.alt,
        "w": image.width or 480,
        "h": image.height or 360,
    }


def serialise_product(product):
    variants = [variant for variant in product.variants.all() if variant.is_active]
    if not variants:
        return None

    default = next((variant for variant in variants if variant.is_default), variants[0])
    images = [_serialise_image(image) for image in product.images.all()]
    if not images:
        images = [
            {
                "src": PLACEHOLDER_IMAGE,
                "alt": product.name,
                "w": 480,
                "h": 360,
            }
        ]

    return {
        "id": product.slug,
        "slug": product.slug,
        "name": product.name,
        "category": product.category.name,
        "categorySlug": product.category.slug,
        "group": product_group(product),
        "condition": product.get_condition_display(),
        "cut": product.cut,
        "desc": product.description,
        "priceBasis": product.price_basis,
        "badge": product.badge or product.get_condition_display(),
        "status": product.availability_status,
        "defaultVariant": str(default.pk),
        "priceUnit": UNIT_LABELS.get(default.unit_kind, default.get_unit_kind_display()),
        "url": product_url(product),
        "categoryUrl": category_url(product.category),
        "images": images,
        "variants": [
            {
                "id": str(variant.pk),
                "label": variant.label,
                "price": float(variant.price),
                "unitKind": variant.unit_kind,
                "priceUnit": UNIT_LABELS.get(
                    variant.unit_kind, variant.get_unit_kind_display()
                ),
                "isDefault": variant.pk == default.pk,
            }
            for variant in variants
        ],
    }


def build_storefront_catalog():
    catalog = {}
    for product in public_products():
        entry = serialise_product(product)
        if entry:
            catalog[entry["id"]] = entry
    return catalog
