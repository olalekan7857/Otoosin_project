from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.files.images import get_image_dimensions
from django.core.validators import FileExtensionValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils.text import slugify


MAX_IMAGE_BYTES = 5 * 1024 * 1024
ALLOWED_IMAGE_EXTENSIONS = ["jpg", "jpeg", "png", "webp", "gif"]


def validate_image_size(image):
    if image and getattr(image, "size", 0) > MAX_IMAGE_BYTES:
        raise ValidationError("Product images must be 5 MB or smaller.")


class Category(models.Model):
    class Kind(models.TextChoices):
        MEAT_GROUP = "meat_group", "Meat group"
        RED_MEAT = "red_meat", "Red meat"
        POULTRY = "poultry", "Poultry"
        SEAFOOD = "seafood", "Seafood"
        LIVE_ANIMAL = "live_animal", "Live animal"
        EGGS = "eggs", "Eggs"
        VEGETABLES = "vegetables", "Vegetables"
        FRUITS = "fruits", "Fruits"

    name = models.CharField(max_length=80)
    slug = models.SlugField(max_length=90, unique=True, blank=True)
    parent = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="children",
    )
    kind = models.CharField(max_length=20, choices=Kind.choices)
    description = models.TextField(blank=True)
    image = models.ImageField(
        upload_to="categories/%Y/%m/",
        blank=True,
        validators=[
            FileExtensionValidator(ALLOWED_IMAGE_EXTENSIONS),
            validate_image_size,
        ],
    )
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    meta_title = models.CharField(max_length=160, blank=True)
    meta_description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name_plural = "categories"

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        if self.parent_id:
            if self.pk and self.parent_id == self.pk:
                raise ValidationError({"parent": "A category cannot be its own parent."})
            if self.parent.parent_id:
                raise ValidationError(
                    {"parent": "Only one level of subcategories is supported."}
                )
            if self.pk and self.children.exists():
                raise ValidationError(
                    {"parent": "A category with subcategories cannot itself have a parent."}
                )

    def _unique_slug(self, base):
        base = (base or "").strip("-") or "category"
        candidate = base
        model = type(self)
        counter = 1
        while (
            model.objects.exclude(pk=self.pk)
            .filter(slug=candidate)
            .exists()
        ):
            candidate = f"{base}-{counter}"
            counter += 1
        return candidate

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = self._unique_slug(slugify(self.name))
        super().save(*args, **kwargs)


class Product(models.Model):
    class Condition(models.TextChoices):
        FRESH = "fresh", "Fresh"
        FROZEN = "frozen", "Frozen"
        FRIED = "fried", "Fried"
        LIVE = "live", "Live"

    class Availability(models.TextChoices):
        IN_STOCK = "in", "Available"
        LIMITED = "limited", "Limited"
        OUT_OF_STOCK = "out", "Out of Stock"

    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, unique=True, blank=True)
    sku = models.CharField(max_length=40, unique=True)
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="products",
    )
    condition = models.CharField(max_length=10, choices=Condition.choices)
    cut = models.CharField(max_length=120, blank=True)
    description = models.TextField()
    price_basis = models.CharField(max_length=60)
    availability_status = models.CharField(
        max_length=10,
        choices=Availability.choices,
        default=Availability.IN_STOCK,
    )
    badge = models.CharField(max_length=30, blank=True)
    is_active = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)
    meta_title = models.CharField(max_length=160, blank=True)
    meta_description = models.TextField(blank=True)
    search_text = models.TextField(blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["category__sort_order", "category__name", "name"]

    def __str__(self):
        return self.name

    @property
    def primary_image(self):
        images = list(self.images.all())
        for image in images:
            if image.is_primary:
                return image
        return images[0] if images else None

    @property
    def default_variant(self):
        variants = list(self.variants.all())
        active = [variant for variant in variants if variant.is_active]
        for variant in active:
            if variant.is_default:
                return variant
        return active[0] if active else None

    def clean(self):
        super().clean()
        if not self.category_id:
            return

        category = self.category
        if category.kind == Category.Kind.MEAT_GROUP:
            raise ValidationError(
                {"category": "Choose a specific meat category, not the Meats group."}
            )

        if category.kind == Category.Kind.LIVE_ANIMAL:
            if self.condition != self.Condition.LIVE:
                raise ValidationError(
                    {"condition": "Products in Live Animals must use the Live condition."}
                )
        elif self.condition == self.Condition.LIVE:
            raise ValidationError(
                {"condition": "The Live condition is only valid for Live Animals."}
            )

        if category.kind == Category.Kind.LIVE_ANIMAL:
            allowed = {self.Condition.LIVE}
        elif category.kind in {
            Category.Kind.RED_MEAT,
            Category.Kind.POULTRY,
            Category.Kind.SEAFOOD,
        }:
            allowed = {
                self.Condition.FRESH,
                self.Condition.FROZEN,
                self.Condition.FRIED,
            }
        else:
            allowed = {self.Condition.FRESH}

        if self.condition not in allowed:
            raise ValidationError(
                {"condition": "This condition is not valid for the selected category."}
            )

    def _unique_slug(self, base):
        base = (base or "").strip("-") or "product"
        candidate = base
        model = type(self)
        counter = 1
        while (
            model.objects.exclude(pk=self.pk)
            .filter(slug=candidate)
            .exists()
        ):
            candidate = f"{base}-{counter}"
            counter += 1
        return candidate

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = self._unique_slug(slugify(self.name))
        self.search_text = " ".join(
            part
            for part in [
                self.name,
                self.sku,
                self.cut,
                self.description,
                self.category.name if self.category_id else "",
            ]
            if part
        )
        super().save(*args, **kwargs)


class ProductVariant(models.Model):
    class UnitKind(models.TextChoices):
        KG = "kg", "Kilogram"
        PIECE = "piece", "Piece"
        CRATE = "crate", "Crate"
        BASKET = "basket", "Basket"
        PACK = "pack", "Pack"
        LIVE_ANIMAL = "live_animal", "Live animal"

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="variants",
    )
    sku = models.CharField(max_length=40, unique=True)
    label = models.CharField(max_length=60)
    unit_kind = models.CharField(max_length=20, choices=UnitKind.choices)
    price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["product"],
                condition=Q(is_default=True),
                name="unique_default_variant_per_product",
            )
        ]

    def __str__(self):
        return f"{self.product.name} - {self.label}"

    def clean(self):
        super().clean()
        if self.price is not None and self.price <= 0:
            raise ValidationError({"price": "Price must be greater than zero."})
        if self.is_default and not self.is_active:
            raise ValidationError(
                {"is_default": "The default variant must be active."}
            )

    def save(self, *args, **kwargs):
        if self.is_default and self.product_id:
            ProductVariant.objects.filter(
                product_id=self.product_id, is_default=True
            ).exclude(pk=self.pk).update(is_default=False)
        super().save(*args, **kwargs)


class ProductImage(models.Model):
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="images",
    )
    image = models.ImageField(
        upload_to="products/%Y/%m/",
        validators=[
            FileExtensionValidator(ALLOWED_IMAGE_EXTENSIONS),
            validate_image_size,
        ],
    )
    alt = models.CharField(max_length=125)
    width = models.PositiveIntegerField(null=True, blank=True)
    height = models.PositiveIntegerField(null=True, blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    is_primary = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sort_order", "pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["product"],
                condition=Q(is_primary=True),
                name="unique_primary_image_per_product",
            )
        ]

    def __str__(self):
        return f"{self.product.name} image"

    def clean(self):
        super().clean()
        if not self.alt or not self.alt.strip():
            raise ValidationError({"alt": "Alternative text is required."})
        if self.image:
            validate_image_size(self.image)

    def save(self, *args, **kwargs):
        if not self.pk and self.product_id and not self.sort_order:
            last_order = (
                ProductImage.objects.filter(product_id=self.product_id)
                .aggregate(models.Max("sort_order"))
                .get("sort_order__max")
                or 0
            )
            self.sort_order = last_order + 1
        if self.is_primary and self.product_id:
            ProductImage.objects.filter(
                product_id=self.product_id, is_primary=True
            ).exclude(pk=self.pk).update(is_primary=False)
        if (
            not self.pk
            and not self.is_primary
            and self.product_id
            and not ProductImage.objects.filter(
                product_id=self.product_id, is_primary=True
            ).exists()
        ):
            self.is_primary = True

        super().save(*args, **kwargs)

        if self.image and (self.width is None or self.height is None):
            try:
                self.image.open()
                width, height = get_image_dimensions(self.image)
            except Exception:
                width = height = None
            finally:
                try:
                    self.image.close()
                except Exception:
                    pass
            if width and height:
                ProductImage.objects.filter(pk=self.pk).update(
                    width=width, height=height
                )
                self.width = width
                self.height = height

    def delete(self, *args, **kwargs):
        product_id = self.product_id
        was_primary = self.is_primary
        result = super().delete(*args, **kwargs)
        if was_primary:
            replacement = (
                ProductImage.objects.filter(product_id=product_id)
                .order_by("sort_order", "pk")
                .first()
            )
            if replacement:
                replacement.is_primary = True
                replacement.save(update_fields=["is_primary"])
        return result


class Inventory(models.Model):
    variant = models.OneToOneField(
        ProductVariant,
        on_delete=models.CASCADE,
        related_name="inventory",
    )
    track_stock = models.BooleanField(default=False)
    quantity_available = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    low_stock_threshold = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "inventory"

    def __str__(self):
        return f"Inventory - {self.variant}"

    @property
    def is_out_of_stock(self):
        if not self.track_stock:
            return False
        return self.quantity_available <= 0
