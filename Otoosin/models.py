import hashlib
import re
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.images import get_image_dimensions
from django.core.validators import FileExtensionValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone
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


NIGERIAN_PHONE_RE = re.compile(r"^\+?234[789][01]\d{8}$")


def normalise_nigerian_phone(value, *, required=False):
    """Return a canonical +234 phone number or blank for an optional field."""
    raw = (value or "").strip()
    if not raw:
        if required:
            raise ValidationError("Enter a phone number.")
        return ""

    digits = re.sub(r"\D", "", raw)
    if digits.startswith("0") and len(digits) == 11:
        digits = "234" + digits[1:]
    elif digits.startswith("234"):
        pass
    elif len(digits) == 10 and digits[0] in "789":
        digits = "234" + digits

    candidate = f"+{digits}"
    if not NIGERIAN_PHONE_RE.match(candidate):
        raise ValidationError(
            "Enter a valid Nigerian phone number, for example 0803 123 4567."
        )
    return candidate


class SiteConfiguration(models.Model):
    """Single owner-managed business configuration record."""

    business_name = models.CharField(max_length=120, default="O’Toosin Farms")
    address = models.CharField(max_length=300, blank=True)
    contact_phone = models.CharField(max_length=30, blank=True)
    whatsapp_number = models.CharField(max_length=30, blank=True)
    support_email = models.EmailField(blank=True)
    description = models.TextField(blank=True)
    delivery_cutoff_time = models.TimeField(default="17:00")
    delivery_cutoff_note = models.CharField(max_length=300, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "site configuration"
        verbose_name_plural = "site configuration"

    def __str__(self):
        return self.business_name

    @classmethod
    def load(cls):
        instance, _ = cls.objects.get_or_create(pk=1)
        return instance

    def clean(self):
        super().clean()
        if self.pk and self.pk != 1:
            raise ValidationError("Only one site configuration record is allowed.")
        if self.contact_phone:
            self.contact_phone = normalise_nigerian_phone(self.contact_phone)
        if self.whatsapp_number:
            self.whatsapp_number = normalise_nigerian_phone(
                self.whatsapp_number
            )

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @property
    def whatsapp_digits(self):
        return re.sub(r"\D", "", self.whatsapp_number or "")


class DeliveryLocation(models.Model):
    class LocationType(models.TextChoices):
        DOORSTEP = "doorstep", "Doorstep delivery"
        PARK = "park", "Park delivery"

    location_type = models.CharField(
        max_length=20, choices=LocationType.choices
    )
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, unique=True, blank=True)
    city = models.CharField(max_length=80, blank=True)
    state = models.CharField(max_length=80, blank=True)
    area = models.CharField(max_length=200, blank=True)
    fee = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
    )
    customer_instructions = models.CharField(max_length=300, blank=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["location_type", "name"],
                name="unique_delivery_location_name_per_type",
            )
        ]

    def __str__(self):
        return f"{self.get_location_type_display()}: {self.name}"

    def _unique_slug(self, base):
        base = (base or "").strip("-") or "delivery-location"
        candidate = base
        model = type(self)
        counter = 2
        while model.objects.exclude(pk=self.pk).filter(slug=candidate).exists():
            candidate = f"{base}-{counter}"
            counter += 1
        return candidate

    def clean(self):
        super().clean()
        if self.fee is not None and self.fee < 0:
            raise ValidationError({"fee": "Delivery fees cannot be negative."})
        if self.is_active and self.fee is None:
            raise ValidationError(
                {"fee": "An active delivery location needs an approved fee."}
            )
        if self.location_type == self.LocationType.DOORSTEP:
            if (self.city or "").strip().casefold() != "abeokuta":
                raise ValidationError(
                    {"city": "Doorstep delivery is currently limited to Abeokuta."}
                )
            if (self.state or "").strip().casefold() not in {"", "ogun"}:
                raise ValidationError(
                    {"state": "Doorstep delivery is currently limited to Ogun State."}
                )
        elif self.location_type == self.LocationType.PARK:
            if not (self.customer_instructions or "").strip():
                raise ValidationError(
                    {
                        "customer_instructions": (
                            "Add a short instruction so customers know how the "
                            "park delivery works."
                        )
                    }
                )

    def save(self, *args, **kwargs):
        if self.location_type == self.LocationType.DOORSTEP:
            self.city = "Abeokuta"
            self.state = "Ogun"
        if not self.slug:
            self.slug = self._unique_slug(
                slugify(f"{self.name}-{self.location_type}")
            )
        super().save(*args, **kwargs)


class PickupLocation(models.Model):
    name = models.CharField(max_length=120)
    address = models.CharField(max_length=300)
    customer_instructions = models.TextField(blank=True)
    opening_hours = models.CharField(max_length=200, blank=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name


class ContactMessage(models.Model):
    class Subject(models.TextChoices):
        PRODUCT = "product", "Product or category question"
        ORDER = "order", "Existing order"
        DELIVERY = "delivery", "Delivery or pickup"
        GENERAL = "general", "General enquiry"
        FEEDBACK = "feedback", "Feedback or other"

    class Status(models.TextChoices):
        NEW = "new", "New"
        READ = "read", "Read"
        REPLIED = "replied", "Replied"
        CLOSED = "closed", "Closed"

    name = models.CharField(max_length=120)
    email = models.EmailField()
    phone = models.CharField(max_length=30, blank=True)
    subject = models.CharField(max_length=20, choices=Subject.choices)
    message = models.TextField()
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.NEW
    )
    internal_notes = models.TextField(blank=True)
    handled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="handled_contact_messages",
    )
    handled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-pk"]

    def __str__(self):
        return f"{self.get_subject_display()} from {self.name}"


class AuditEvent(models.Model):
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_events",
    )
    action = models.CharField(max_length=80)
    target_type = models.CharField(max_length=80, blank=True)
    target_id = models.CharField(max_length=80, blank=True)
    summary = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at", "-pk"]

    def __str__(self):
        return f"{self.action} at {self.created_at:%Y-%m-%d %H:%M}"


class EmailDelivery(models.Model):
    class Category(models.TextChoices):
        STAFF_INVITE = "staff_invite", "Staff invitation"
        PASSWORD_RESET = "password_reset", "Password reset"

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        SENT = "sent", "Accepted by provider"
        FAILED = "failed", "Failed"

    category = models.CharField(max_length=30, choices=Category.choices)
    recipient = models.EmailField()
    subject = models.CharField(max_length=200)
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.QUEUED
    )
    provider_message_id = models.CharField(max_length=120, blank=True)
    attempts = models.PositiveIntegerField(default=0)
    retryable = models.BooleanField(default=True)
    last_error = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-pk"]

    def __str__(self):
        return f"{self.get_category_display()} to {self.recipient} ({self.status})"


class StaffInvitation(models.Model):
    class Role(models.TextChoices):
        OWNER = "owner", "Owner"
        MANAGER = "manager", "Manager"
        FULFILMENT = "fulfilment", "Fulfilment"
        SUPPORT = "support", "Support"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="staff_invitations",
    )
    email = models.EmailField()
    role = models.CharField(max_length=20, choices=Role.choices)
    token_hash = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_staff_invitations",
    )
    email_delivery = models.ForeignKey(
        EmailDelivery,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="staff_invitations",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        permissions = [("manage_staff", "Can manage staff accounts")]

    def __str__(self):
        return f"Invitation for {self.email} ({self.get_role_display()})"

    @staticmethod
    def hash_token(raw_token):
        return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

    @property
    def is_pending(self):
        return (
            self.used_at is None
            and self.revoked_at is None
            and self.expires_at > timezone.now()
        )

    @classmethod
    def default_expiry(cls):
        return timezone.now() + timedelta(
            hours=getattr(settings, "STAFF_INVITATION_HOURS", 72)
        )
