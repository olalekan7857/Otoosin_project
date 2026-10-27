import json
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, OuterRef, Prefetch, Q, Subquery
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .cart import CartPayloadError, validate_cart_request
from .catalogue import public_products
from .forms import (
    CategoryForm,
    ImageFormSet,
    ProductForm,
    ProductInventoryForm,
    VariantFormSet,
)
from .models import Category, Product, ProductVariant


def _staff_permission(permission):
    def decorator(view):
        @login_required(login_url="Otoosin:staff_login")
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            user = request.user
            if not user.is_active or not user.is_staff:
                raise PermissionDenied
            if permission and not user.has_perm(permission):
                raise PermissionDenied
            return view(request, *args, **kwargs)

        return wrapped

    return decorator


def _paginate(request, queryset, per_page):
    paginator = Paginator(queryset, per_page)
    page_number = request.GET.get("page")
    if request.method == "POST" and not page_number:
        page_number = request.POST.get("page")
    page_obj = paginator.get_page(page_number)
    page_range = list(
        paginator.get_elided_page_range(
            page_obj.number, on_each_side=1, on_ends=1
        )
    )
    return paginator, page_obj, page_range


def _default_variant_subquery(field):
    variants = ProductVariant.objects.filter(
        product=OuterRef("pk"), is_active=True
    ).order_by("-is_default", "sort_order", "pk")
    return Subquery(variants.values(field)[:1])


def _filtered_products(request):
    products = Product.objects.select_related(
        "category", "category__parent"
    ).prefetch_related("variants", "images")
    products = products.annotate(
        default_price=_default_variant_subquery("price"),
        default_unit=_default_variant_subquery("unit_kind"),
        default_label=_default_variant_subquery("label"),
    )

    search = (request.GET.get("q") or "").strip()
    category_value = (request.GET.get("category") or "").strip()
    condition = (request.GET.get("state") or "").strip().lower()
    availability = (request.GET.get("availability") or "").strip()
    sort = (request.GET.get("sort") or "default").strip()

    if search:
        products = products.filter(
            Q(name__icontains=search)
            | Q(sku__icontains=search)
            | Q(cut__icontains=search)
            | Q(description__icontains=search)
            | Q(category__name__icontains=search)
            | Q(search_text__icontains=search)
        )

    if category_value:
        category = Category.objects.filter(
            Q(slug__iexact=category_value) | Q(name__iexact=category_value)
        ).first()
        if category:
            category_ids = [category.pk]
            category_ids.extend(category.children.values_list("pk", flat=True))
            products = products.filter(category_id__in=category_ids)

    if condition in Product.Condition.values:
        products = products.filter(condition=condition)

    if availability in Product.Availability.values:
        products = products.filter(availability_status=availability)

    if sort == "name-asc":
        products = products.order_by("name", "pk")
    elif sort == "name-desc":
        products = products.order_by("-name", "pk")
    elif sort == "price-asc":
        products = products.order_by("default_price", "name")
    elif sort == "price-desc":
        products = products.order_by("-default_price", "name")

    return products, {
        "q": search,
        "category": category_value,
        "state": condition,
        "availability": availability,
        "sort": sort,
    }


PRICE_BASIS_BY_UNIT = {
    ProductVariant.UnitKind.KG: "Per kilogram",
    ProductVariant.UnitKind.PIECE: "Per piece",
    ProductVariant.UnitKind.CRATE: "Per crate",
    ProductVariant.UnitKind.BASKET: "Per basket",
    ProductVariant.UnitKind.PACK: "Per pack",
    ProductVariant.UnitKind.LIVE_ANIMAL: "Per live animal",
}


def _normalise_saved_product(product):
    variants = list(product.variants.all())
    active_variants = [variant for variant in variants if variant.is_active]
    if active_variants and not any(
        variant.is_default for variant in active_variants
    ):
        first = active_variants[0]
        first.is_default = True
        first.save(update_fields=["is_default"])

    if product.price_basis in {"", "Per unit"} and active_variants:
        default_variant = next(
            (variant for variant in active_variants if variant.is_default),
            active_variants[0],
        )
        product.price_basis = PRICE_BASIS_BY_UNIT.get(
            default_variant.unit_kind,
            default_variant.get_unit_kind_display(),
        )
        product.save(update_fields=["price_basis"])

    images = list(product.images.all())
    if images and not any(image.is_primary for image in images):
        first_image = images[0]
        first_image.is_primary = True
        first_image.save(update_fields=["is_primary"])


def _product_form_view(request, product=None):
    is_create = product is None
    instance = product or Product()

    if request.method == "POST":
        form = ProductForm(
            request.POST, request.FILES, instance=instance
        )
        variant_formset = VariantFormSet(
            request.POST,
            request.FILES,
            instance=instance,
            prefix="variants",
        )
        image_formset = ImageFormSet(
            request.POST,
            request.FILES,
            instance=instance,
            prefix="images",
        )

        if (
            form.is_valid()
            and variant_formset.is_valid()
            and image_formset.is_valid()
        ):
            with transaction.atomic():
                saved_product = form.save()
                variant_formset.instance = saved_product
                variant_formset.save()
                image_formset.instance = saved_product
                image_formset.save()
                _normalise_saved_product(saved_product)

            messages.success(
                request,
                f"{saved_product.name} was {'created' if is_create else 'updated'}.",
            )
            return redirect(
                "Otoosin:staff_product_edit", pk=saved_product.pk
            )

        messages.error(
            request, "Check the highlighted fields and try again."
        )
    else:
        form = ProductForm(instance=instance)
        variant_formset = VariantFormSet(
            instance=instance, prefix="variants"
        )
        image_formset = ImageFormSet(instance=instance, prefix="images")
        # Existing photos already have their own row. Do not add a blank
        # second row on edit; only show one when the product has no photo yet.
        if image_formset.initial_form_count():
            image_formset.extra = 0

    return render(
        request,
        "admin-product-edit.html",
        {
            "form": form,
            "variant_formset": variant_formset,
            "image_formset": image_formset,
            "product": None if is_create else product,
            "is_create": is_create,
            "categories": Category.objects.exclude(
                kind=Category.Kind.MEAT_GROUP
            ).order_by("name"),
        },
    )


@_staff_permission(None)
def staff_dashboard(request):
    products = Product.objects.all()
    summary = products.aggregate(
        total=Count("id"),
        active=Count("id", filter=Q(is_active=True)),
        out=Count(
            "id", filter=Q(availability_status=Product.Availability.OUT_OF_STOCK)
        ),
        limited=Count(
            "id", filter=Q(availability_status=Product.Availability.LIMITED)
        ),
    )
    return render(
        request,
        "admin-dashboard.html",
        {
            "summary": summary,
            "category_count": Category.objects.filter(
                parent__isnull=True
            ).count(),
            "subcategory_count": Category.objects.filter(
                parent__isnull=False
            ).count(),
            "recent_products": products.select_related("category").order_by(
                "-created_at"
            )[:5],
        },
    )


@_staff_permission("Otoosin.view_product")
def staff_product_list(request):
    products, filters = _filtered_products(request)
    paginator, page_obj, page_range = _paginate(request, products, 30)
    summary = Product.objects.aggregate(
        total=Count("id"),
        fresh=Count("id", filter=Q(condition=Product.Condition.FRESH)),
        frozen=Count("id", filter=Q(condition=Product.Condition.FROZEN)),
        fried=Count("id", filter=Q(condition=Product.Condition.FRIED)),
        live=Count("id", filter=Q(condition=Product.Condition.LIVE)),
    )
    return render(
        request,
        "admin-products.html",
        {
            "products": page_obj,
            "paginator": paginator,
            "page_obj": page_obj,
            "page_range": page_range,
            "pagination_label": "Product pages",
            "filters": filters,
            "summary": summary,
            "categories": Category.objects.filter(
                parent__isnull=True
            ).order_by("sort_order", "name"),
        },
    )


@_staff_permission("Otoosin.add_product")
def staff_product_create(request):
    return _product_form_view(request)


@_staff_permission("Otoosin.change_product")
def staff_product_edit(request, pk):
    product = get_object_or_404(Product, pk=pk)
    return _product_form_view(request, product=product)


@_staff_permission("Otoosin.change_category")
def staff_categories(request):
    if request.method == "POST" and request.POST.get("action") == "toggle":
        category = get_object_or_404(
            Category, pk=request.POST.get("category_id")
        )
        category.is_active = not category.is_active
        category.save(update_fields=["is_active", "updated_at"])
        messages.success(
            request,
            f"{category.name} is now "
            f"{'active' if category.is_active else 'inactive'}.",
        )
        return redirect("Otoosin:staff_categories")

    if request.method == "POST" and request.POST.get("action") == "delete":
        category = get_object_or_404(
            Category, pk=request.POST.get("category_id")
        )
        if category.children.exists():
            messages.error(
                request,
                "Move or delete the subcategories before deleting this category.",
            )
        elif category.products.exists():
            messages.error(
                request,
                "Move the products to another category before deleting this one.",
            )
        else:
            name = category.name
            category.delete()
            messages.success(request, f"{name} was deleted.")
        return redirect("Otoosin:staff_categories")

    edit_id = request.GET.get("edit") or request.POST.get("category_id")
    instance = (
        get_object_or_404(Category, pk=edit_id) if edit_id else None
    )
    initial = {}
    parent_id = request.GET.get("parent")
    if instance is None and parent_id:
        parent = get_object_or_404(
            Category, pk=parent_id, parent__isnull=True
        )
        initial["parent"] = parent

    if request.method == "POST":
        form = CategoryForm(
            request.POST, request.FILES, instance=instance
        )
        if form.is_valid():
            category = form.save()
            messages.success(request, f"{category.name} was saved.")
            return redirect("Otoosin:staff_categories")
        messages.error(
            request, "Check the highlighted fields and try again."
        )
    else:
        form = CategoryForm(instance=instance, initial=initial)

    child_categories = Category.objects.annotate(
        product_count=Count("products", distinct=True)
    ).order_by("sort_order", "name")
    categories = list(
        Category.objects.filter(parent__isnull=True)
        .prefetch_related(
            Prefetch("children", queryset=child_categories)
        )
        .annotate(product_count=Count("products", distinct=True))
        .order_by("sort_order", "name")
    )
    for category in categories:
        category.total_product_count = category.product_count + sum(
            child.product_count for child in category.children.all()
        )

    return render(
        request,
        "admin-categories.html",
        {
            "form": form,
            "editing": instance,
            "categories": categories,
            "main_category_count": len(categories),
            "subcategory_count": sum(
                category.children.count() for category in categories
            ),
        },
    )


@_staff_permission("Otoosin.change_inventory")
def staff_inventory(request):
    bound_form = None
    bound_product_id = None

    if request.method == "POST":
        product = get_object_or_404(
            Product, pk=request.POST.get("product_id")
        )
        bound_form = ProductInventoryForm(
            request.POST,
            product=product,
            auto_id=f"inv_{product.pk}_%s",
        )
        if bound_form.is_valid():
            bound_form.save()
            messages.success(
                request, f"Availability updated for {product.name}."
            )
            return redirect("Otoosin:staff_inventory")
        messages.error(
            request, "Check the highlighted inventory fields and try again."
        )
        bound_product_id = product.pk

    products, filters = _filtered_products(request)
    paginator, page_obj, page_range = _paginate(request, products, 30)
    rows = []
    for product in page_obj:
        form = (
            bound_form
            if bound_product_id == product.pk
            else ProductInventoryForm(
                product=product,
                auto_id=f"inv_{product.pk}_%s",
            )
        )
        rows.append((product, form))

    return render(
        request,
        "admin-inventory.html",
        {
            "rows": rows,
            "products": page_obj,
            "paginator": paginator,
            "page_obj": page_obj,
            "page_range": page_range,
            "pagination_label": "Inventory pages",
            "filters": filters,
            "categories": Category.objects.filter(
                parent__isnull=True
            ).order_by("sort_order", "name"),
            "summary": Product.objects.aggregate(
                total=Count("id"),
                available=Count(
                    "id",
                    filter=Q(availability_status=Product.Availability.IN_STOCK),
                ),
                limited=Count(
                    "id",
                    filter=Q(availability_status=Product.Availability.LIMITED),
                ),
                out=Count(
                    "id",
                    filter=Q(
                        availability_status=Product.Availability.OUT_OF_STOCK
                    ),
                ),
            ),
        },
    )


def _public_category_counts():
    child_categories = Category.objects.filter(is_active=True).annotate(
        product_count=Count(
            "products",
            filter=Q(
                products__is_active=True,
                products__variants__is_active=True,
            ),
            distinct=True,
        )
    )
    categories = list(
        Category.objects.filter(parent__isnull=True, is_active=True)
        .prefetch_related(
            Prefetch("children", queryset=child_categories)
        )
        .annotate(
            product_count=Count(
                "products",
                filter=Q(
                    products__is_active=True,
                    products__variants__is_active=True,
                ),
                distinct=True,
            )
        )
        .order_by("sort_order", "name")
    )
    for category in categories:
        category.total_product_count = category.product_count + sum(
            child.product_count for child in category.children.all()
        )
    return categories


def _resolve_public_category(value):
    value = (value or "").strip()
    if not value:
        return None
    return (
        Category.objects.filter(is_active=True)
        .filter(
            Q(slug__iexact=value)
            | Q(name__iexact=value)
            | Q(name__iexact=value.replace("-", " "))
        )
        .first()
    )


def _public_category_ids(category):
    if category is None:
        return None
    ids = [category.pk]
    ids.extend(category.children.values_list("pk", flat=True))
    return ids


def _apply_public_filters(request, products, category=None):
    search = (request.GET.get("q") or "").strip()
    condition = (request.GET.get("state") or "").strip().lower()
    availability = (request.GET.get("availability") or "").strip().lower()
    sort = (request.GET.get("sort") or "featured").strip()

    if search:
        products = products.filter(
            Q(name__icontains=search)
            | Q(cut__icontains=search)
            | Q(description__icontains=search)
            | Q(category__name__icontains=search)
            | Q(search_text__icontains=search)
        )

    category_ids = _public_category_ids(category)
    if category_ids is not None:
        products = products.filter(category_id__in=category_ids)

    if condition in Product.Condition.values:
        products = products.filter(condition=condition)

    if availability in Product.Availability.values:
        products = products.filter(availability_status=availability)

    if sort == "price-asc":
        products = products.order_by(
            Subquery(
                ProductVariant.objects.filter(
                    product=OuterRef("pk"), is_active=True
                )
                .order_by("-is_default", "sort_order", "pk")
                .values("price")[:1]
            ),
            "name",
        )
    elif sort == "price-desc":
        products = products.order_by(
            Subquery(
                ProductVariant.objects.filter(
                    product=OuterRef("pk"), is_active=True
                )
                .order_by("-is_default", "sort_order", "pk")
                .values("price")[:1]
            ).desc(),
            "name",
        )
    elif sort == "name":
        products = products.order_by("name", "pk")
    elif sort == "name-desc":
        products = products.order_by("-name", "pk")
    else:
        products = products.order_by(
            "-is_featured",
            "category__sort_order",
            "category__name",
            "name",
        )

    return products, {
        "q": search,
        "state": condition,
        "availability": availability,
        "sort": sort,
    }


def _catalogue_context(request, category=None):
    products, filters = _apply_public_filters(
        request, public_products(), category=category
    )
    paginator, page_obj, page_range = _paginate(request, products, 20)
    categories = _public_category_counts()
    return {
        "products": page_obj,
        "paginator": paginator,
        "page_obj": page_obj,
        "page_range": page_range,
        "pagination_label": "Product pages",
        "filters": filters,
        "categories": categories,
        "selected_category": category,
        "total_category_count": sum(
            category.total_product_count for category in categories
        ),
        "all_products_count": public_products().count(),
    }


def index(request):
    products = public_products()
    latest = list(products.order_by("-created_at", "-pk")[:8])
    featured = list(
        products.filter(is_featured=True).order_by("-created_at", "-pk")[:8]
    )
    if not featured:
        featured = latest[:8]
    return render(
        request,
        "index.html",
        {"featured_products": featured, "latest_products": latest},
    )


def about(request):
    return render(request, "about.html")


def contact(request):
    return render(request, "contact.html")


def product(request):
    category = _resolve_public_category(request.GET.get("category"))
    context = _catalogue_context(request, category=category)
    return render(request, "product.html", context)


def product_category(request):
    category = _resolve_public_category(request.GET.get("category"))
    context = _catalogue_context(request, category=category)
    context["page_heading"] = (
        f"Shop {category.name}" if category else "Shop All Products"
    )
    context["page_kicker"] = "Category" if category else "Product categories"
    context["page_lead"] = (
        category.description
        if category and category.description
        else (
            f"Browse {category.name} from O’TOOSIN Farms. Each product shows "
            "its unit and condition where it applies, then goes straight "
            "into your cart."
            if category
            else "Browse meats, fish, live animals, eggs, veggies and fruits "
            "by category. Each product shows its unit and condition where it "
            "applies, then goes straight into your cart."
        )
    )
    context["page_image"] = (
        category.image if category and category.image else None
    )
    return render(request, "product-category.html", context)


def _public_product(identifier):
    if not identifier:
        return None
    products = public_products()
    query = Q(slug__iexact=identifier)
    if str(identifier).isdigit():
        query |= Q(pk=identifier)
    return products.filter(query).first()


def product_details(request):
    identifier = (request.GET.get("id") or "").strip()
    product = _public_product(identifier)
    if product is None:
        return render(
            request,
            "product-details.html",
            {"product": None},
            status=404,
        )

    related = list(
        public_products()
        .filter(category_id=product.category_id)
        .exclude(pk=product.pk)[:4]
    )
    if len(related) < 4:
        used = [product.pk] + [item.pk for item in related]
        related.extend(
            list(
                public_products()
                .exclude(pk__in=used)
                .order_by("-is_featured", "name")[: 4 - len(related)]
            )
        )

    default_variant = product.default_variant
    primary_image = product.primary_image
    image_url = (
        request.build_absolute_uri(primary_image.image.url)
        if primary_image
        else request.build_absolute_uri(
            "/static/assets/img/categorie/otoosin-farms.png"
        )
    )
    availability_url = {
        Product.Availability.IN_STOCK: "https://schema.org/InStock",
        Product.Availability.LIMITED: "https://schema.org/LimitedAvailability",
        Product.Availability.OUT_OF_STOCK: "https://schema.org/OutOfStock",
    }.get(product.availability_status, "https://schema.org/InStock")
    product_jsonld = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": product.name,
        "category": product.category.name,
        "description": product.description,
        "image": image_url,
        "brand": {"@type": "Brand", "name": "O’TOOSIN Farms"},
        "offers": {
            "@type": "Offer",
            "priceCurrency": "NGN",
            "price": float(default_variant.price),
            "availability": availability_url,
            "priceSpecification": {
                "@type": "UnitPriceSpecification",
                "price": float(default_variant.price),
                "priceCurrency": "NGN",
                "unitText": default_variant.get_unit_kind_display(),
            },
        },
    }

    return render(
        request,
        "product-details.html",
        {
            "product": product,
            "default_variant": default_variant,
            "product_images": list(product.images.all()),
            "related_products": related,
            "product_jsonld_json": json.dumps(product_jsonld).replace(
                "</", "<\\/"
            ),
        },
    )


def cart(request):
    return render(request, "cart.html")


def checkout(request):
    return render(request, "checkout.html")


def _invalid_cart_response(error, status=400):
    return JsonResponse(
        {
            "ok": False,
            "items": [],
            "errors": [{"key": "", "message": str(error)}],
            "notices": [],
            "subtotal": 0,
            "line_count": 0,
        },
        status=status,
    )


@require_POST
def cart_validate(request):
    try:
        result = validate_cart_request(request, normalize=True)
    except CartPayloadError as exc:
        return _invalid_cart_response(exc)
    return JsonResponse(result)


@require_POST
def checkout_validate(request):
    try:
        result = validate_cart_request(request, normalize=False)
    except CartPayloadError as exc:
        return _invalid_cart_response(exc)
    if not result["ok"] or not result["items"]:
        result["ok"] = False
        return JsonResponse(result, status=400)
    return JsonResponse(result)


def order_confirmation(request):
    return render(request, "order-confirmation.html")


def privacy(request):
    return render(request, "privacy.html")


def terms(request):
    return render(request, "terms.html")


def not_found(request, exception):
    return render(request, "404.html", status=404)
