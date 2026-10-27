from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.forms import BaseInlineFormSet, inlineformset_factory
from django.utils.text import slugify

from .models import (
    Category,
    Inventory,
    Product,
    ProductImage,
    ProductVariant,
    ALLOWED_IMAGE_EXTENSIONS,
)
from .widgets import AdminImageInput


TEXT_INPUT = {"class": "form-control"}
SELECT_INPUT = {"class": "form-select"}
CHECKBOX_INPUT = {"class": "form-check-input"}
IMAGE_ACCEPT = ",".join(f"image/{ext}" for ext in ("jpeg", "png", "webp", "gif"))


class StaffLoginForm(AuthenticationForm):
    username = forms.CharField(
        label="Username",
        widget=forms.TextInput(
            attrs={
                **TEXT_INPUT,
                "autocomplete": "username",
                "autofocus": True,
                "placeholder": "Enter your staff username",
            }
        ),
    )
    password = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(
            attrs={
                **TEXT_INPUT,
                "autocomplete": "current-password",
                "placeholder": "Enter your password",
            }
        ),
    )

    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if not user.is_staff:
            raise forms.ValidationError(
                self.error_messages["invalid_login"],
                code="invalid_login",
                params={"username": self.username_field.verbose_name},
            )


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = [
            "name",
            "parent",
            "kind",
            "description",
            "image",
            "sort_order",
            "is_active",
            "meta_title",
            "meta_description",
        ]
        widgets = {
            "name": forms.TextInput(attrs=TEXT_INPUT),
            "parent": forms.Select(attrs=SELECT_INPUT),
            "kind": forms.Select(attrs=SELECT_INPUT),
            "description": forms.Textarea(attrs={**TEXT_INPUT, "rows": 3}),
            "image": AdminImageInput(
                attrs={
                    "accept": IMAGE_ACCEPT,
                    "class": "fd-image-input",
                    "aria-label": "Upload category image",
                }
            ),
            "sort_order": forms.NumberInput(attrs={**TEXT_INPUT, "min": 0}),
            "is_active": forms.CheckboxInput(attrs=CHECKBOX_INPUT),
            "meta_title": forms.TextInput(attrs=TEXT_INPUT),
            "meta_description": forms.Textarea(attrs={**TEXT_INPUT, "rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        parents = Category.objects.filter(parent__isnull=True)
        if self.instance.pk:
            parents = parents.exclude(pk=self.instance.pk)
        self.fields["parent"].queryset = parents
        self.fields["parent"].empty_label = "Main category (no parent)"
        self.fields["name"].help_text = (
            "The name customers will see, for example “Pork” or “Smoked Fish”."
        )
        self.fields["parent"].help_text = (
            "Leave this as “Main category” for a top-level category, or choose "
            "a main category to place this one underneath it as a subcategory. "
            "A category that already has subcategories must stay at main level."
        )
        self.fields["kind"].help_text = (
            "The category type controls which product conditions staff can "
            "choose later. For example, Live Animals only accepts Live products."
        )
        self.fields["description"].help_text = (
            "A short introduction shown where the category appears. Explain "
            "what customers can expect to find here."
        )
        self.fields["image"].help_text = (
            "Optional image used on category cards. Drag and drop a file, or "
            "use the Choose image button. PNG, JPEG, WebP or GIF up to 5 MB."
        )
        self.fields["sort_order"].help_text = (
            "Lower numbers appear first. Use a small number such as 1, 2 or 3 "
            "to move this category higher in the list."
        )
        self.fields["is_active"].help_text = (
            "Deactivate a category to hide it and its products from the shop "
            "without deleting anything."
        )
        self.fields["meta_title"].help_text = (
            "Optional title used by search engines and browser tabs. Keep it "
            "under 60 characters; leave blank to use the category name."
        )
        self.fields["meta_description"].help_text = (
            "Optional search-engine summary. Aim for 150–160 characters; "
            "leave blank to use the category description."
        )


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = [
            "name",
            "sku",
            "category",
            "condition",
            "cut",
            "description",
            "price_basis",
            "availability_status",
            "badge",
            "is_active",
            "is_featured",
            "meta_title",
            "meta_description",
        ]
        widgets = {
            "name": forms.TextInput(attrs=TEXT_INPUT),
            "sku": forms.TextInput(attrs=TEXT_INPUT),
            "category": forms.Select(attrs=SELECT_INPUT),
            "condition": forms.Select(attrs=SELECT_INPUT),
            "cut": forms.TextInput(attrs=TEXT_INPUT),
            "description": forms.Textarea(attrs={**TEXT_INPUT, "rows": 4}),
            "price_basis": forms.TextInput(attrs=TEXT_INPUT),
            "availability_status": forms.Select(attrs=SELECT_INPUT),
            "badge": forms.TextInput(attrs=TEXT_INPUT),
            "is_active": forms.Select(
                attrs=SELECT_INPUT,
                choices=[
                    (True, "Active — show in the shop"),
                    (False, "Draft — hide from the shop"),
                ],
            ),
            "is_featured": forms.Select(
                attrs=SELECT_INPUT,
                choices=[
                    (True, "Yes — feature on the homepage"),
                    (False, "No — normal catalogue listing"),
                ],
            ),
            "meta_title": forms.TextInput(attrs=TEXT_INPUT),
            "meta_description": forms.Textarea(attrs={**TEXT_INPUT, "rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].queryset = Category.objects.exclude(
            kind=Category.Kind.MEAT_GROUP
        ).select_related("parent")
        self.fields["category"].empty_label = "Choose a category"
        self.fields["name"].help_text = (
            "The product name customers will see, for example "
            "“Fresh Pork Chops”."
        )
        self.fields["sku"].required = False
        self.fields["sku"].help_text = (
            "Optional internal code. Leave blank and we will create one from "
            "the product name. Customers do not see it."
        )
        self.fields["category"].help_text = (
            "Pick the exact subcategory customers should browse. The Meats "
            "group is only a container, so choose a meat below it instead."
        )
        self.fields["condition"].help_text = (
            "How the product is sold. Only conditions that fit the selected "
            "category can be saved."
        )
        self.fields["cut"].help_text = (
            "Optional detail about the cut or pack, for example "
            "“Bone-in, 1-inch chops” or “Whole bird”."
        )
        self.fields["description"].help_text = (
            "Explain the product to customers: size, freshness, preparation, "
            "storage and anything that helps them choose."
        )
        self.fields["price_basis"].required = False
        self.fields["price_basis"].help_text = (
            "Optional. Leave blank to use the default selling option's unit, "
            "for example “Per kilogram”. Set actual prices in Selling options."
        )
        self.fields["availability_status"].help_text = (
            "The availability message shown on the product card right now."
        )
        self.fields["badge"].help_text = (
            "Optional short label on the product card, such as “Farm fresh”. "
            "Leave blank to use the product condition."
        )
        self.fields["is_active"].help_text = (
            "Active products can be found in the shop. Draft products stay "
            "hidden from customers."
        )
        self.fields["is_featured"].help_text = (
            "Featured products are prioritised on the homepage and in the "
            "catalogue. This only affects customers while the product is active."
        )
        self.fields["meta_title"].help_text = (
            "Optional title used by search engines and browser tabs. Keep it "
            "under 60 characters; leave blank to use the product name."
        )
        self.fields["meta_description"].help_text = (
            "Optional search-engine summary. Aim for 150–160 characters; "
            "leave blank to use the product description."
        )

    def _unique_product_sku(self, base):
        base = (base or "PRODUCT")[:34].strip("-") or "PRODUCT"
        candidate = base
        counter = 2
        existing = Product.objects.exclude(pk=self.instance.pk)
        while existing.filter(sku__iexact=candidate).exists():
            candidate = f"{base}-{counter}"
            counter += 1
        return candidate

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("sku"):
            base = slugify(cleaned.get("name") or "product").upper()
            generated = self._unique_product_sku(base)
            cleaned["sku"] = generated
            self.instance.sku = generated
        if not cleaned.get("price_basis"):
            cleaned["price_basis"] = "Per unit"
            self.instance.price_basis = "Per unit"
        return cleaned


class ProductVariantForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["sku"].required = False
        self.fields["label"].help_text = (
            "The option customers choose, for example “1 kg”, “2 kg pack” or "
            "“Whole bird”."
        )
        self.fields["unit_kind"].help_text = (
            "How this option is sold. Kilogram is used for weighed items; "
            "Piece, Crate, Basket, Pack or Live animal cover the rest."
        )
        self.fields["price"].help_text = (
            "The price charged for one of this option. Enter digits only, for "
            "example 4800.00."
        )
        self.fields["is_default"].help_text = (
            "The option whose price appears on shop and homepage cards. "
            "Choose exactly one default option."
        )
        self.fields["is_active"].help_text = (
            "Untick to keep this option out of the shop without deleting it."
        )
        self.fields["sku"].help_text = (
            "Optional. Leave blank and we will create a code from the product "
            "SKU and option name."
        )

    def _unique_variant_sku(self, base):
        base = (base or "VARIANT")[:34].strip("-")
        candidate = base
        counter = 2
        existing = ProductVariant.objects.exclude(pk=self.instance.pk)
        while existing.filter(sku__iexact=candidate).exists():
            candidate = f"{base}-{counter}"
            counter += 1
        return candidate

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("DELETE") or cleaned.get("sku"):
            return cleaned
        product = getattr(self, "parent_product", None)
        if product is None:
            product = self.instance.product
        product_sku = getattr(product, "sku", "") or ""
        label = cleaned.get("label") or ""
        unit_kind = cleaned.get("unit_kind") or ""
        base = slugify(" ".join(part for part in (product_sku, label) if part))
        if not base:
            base = slugify(unit_kind) or "variant"
        generated = self._unique_variant_sku(base.upper())
        cleaned["sku"] = generated
        self.instance.sku = generated
        return cleaned

    def has_changed(self):
        if self.instance.pk:
            return super().has_changed()
        prefix = self.prefix
        field_names = ("sku", "label", "unit_kind", "price")
        if not any(
            (self.data.get(f"{prefix}-{name}") or "").strip()
            for name in field_names
        ):
            return False
        return super().has_changed()

    class Meta:
        model = ProductVariant
        fields = [
            "sku",
            "label",
            "unit_kind",
            "price",
            "is_default",
            "is_active",
            "sort_order",
        ]
        widgets = {
            "sku": forms.TextInput(attrs=TEXT_INPUT),
            "label": forms.TextInput(attrs=TEXT_INPUT),
            "unit_kind": forms.Select(attrs=SELECT_INPUT),
            "price": forms.NumberInput(
                attrs={**TEXT_INPUT, "step": "0.01", "min": "0.01"}
            ),
            "is_default": forms.CheckboxInput(attrs=CHECKBOX_INPUT),
            "is_active": forms.CheckboxInput(attrs=CHECKBOX_INPUT),
            "sort_order": forms.NumberInput(attrs={**TEXT_INPUT, "min": 0}),
        }


class BaseVariantFormSet(BaseInlineFormSet):
    def _construct_form(self, i, **kwargs):
        form = super()._construct_form(i, **kwargs)
        form.parent_product = self.instance
        return form

    def clean(self):
        super().clean()
        if any(self.errors):
            return

        active = []
        defaults = []
        seen_skus = set()
        for form in self.forms:
            if not hasattr(form, "cleaned_data"):
                continue
            data = form.cleaned_data
            if data.get("DELETE"):
                continue
            if not any(
                data.get(field)
                for field in ("sku", "label", "unit_kind", "price")
            ):
                continue

            sku = (data.get("sku") or "").strip().lower()
            if sku:
                if sku in seen_skus:
                    raise forms.ValidationError(
                        "Each variant must have a unique SKU."
                    )
                seen_skus.add(sku)

            if data.get("is_active"):
                active.append(form)
            if data.get("is_default"):
                defaults.append(form)

        if not active:
            raise forms.ValidationError(
                "Add at least one active variant with a price."
            )
        if len(defaults) != 1:
            raise forms.ValidationError(
                "Choose exactly one default variant for this product."
            )
        if defaults and not defaults[0].cleaned_data.get("is_active"):
            raise forms.ValidationError(
                "The default variant must be active."
            )


class ProductImageForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["image"].help_text = (
            "Drag and drop a photo, or use Choose image. PNG, JPEG, WebP or "
            "GIF up to 5 MB."
        )
        self.fields["alt"].help_text = (
            "Describe the image for customers using screen readers, for "
            "example “Fresh pork chops on a wooden board”."
        )
        self.fields["is_primary"].help_text = (
            "The main photo is used on shop cards and search results. If you "
            "leave every photo unticked, the first photo becomes the main one."
        )

    def has_changed(self):
        if self.instance.pk:
            return super().has_changed()
        prefix = self.prefix
        has_file = bool(
            self.files.get(f"{prefix}-image")
            or self.data.get(f"{prefix}-image")
        )
        has_alt = bool((self.data.get(f"{prefix}-alt") or "").strip())
        if not has_file and not has_alt:
            return False
        return super().has_changed()

    class Meta:
        model = ProductImage
        fields = ["image", "alt", "is_primary"]
        widgets = {
            "image": AdminImageInput(
                attrs={
                    "accept": IMAGE_ACCEPT,
                    "class": "fd-image-input",
                    "aria-label": "Upload product image",
                }
            ),
            "alt": forms.TextInput(attrs=TEXT_INPUT),
            "is_primary": forms.CheckboxInput(attrs=CHECKBOX_INPUT),
        }


class BaseImageFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return

        primaries = []
        for form in self.forms:
            if not hasattr(form, "cleaned_data"):
                continue
            data = form.cleaned_data
            if data.get("DELETE"):
                continue
            if data.get("is_primary"):
                primaries.append(form)

        if len(primaries) > 1:
            raise forms.ValidationError(
                "Choose only one primary image for this product."
            )


VariantFormSet = inlineformset_factory(
    Product,
    ProductVariant,
    form=ProductVariantForm,
    formset=BaseVariantFormSet,
    extra=1,
    can_delete=True,
)

ImageFormSet = inlineformset_factory(
    Product,
    ProductImage,
    form=ProductImageForm,
    formset=BaseImageFormSet,
    extra=1,
    can_delete=True,
)


class ProductInventoryForm(forms.Form):
    availability_status = forms.ChoiceField(
        choices=Product.Availability.choices,
        widget=forms.Select(attrs=SELECT_INPUT),
        label="Availability",
    )
    track_stock = forms.BooleanField(required=False, label="Track stock")
    quantity_available = forms.DecimalField(
        max_digits=10,
        decimal_places=3,
        required=False,
        min_value=0,
        widget=forms.NumberInput(attrs={**TEXT_INPUT, "step": "0.001", "min": 0}),
        label="Quantity available",
    )
    low_stock_threshold = forms.DecimalField(
        max_digits=10,
        decimal_places=3,
        required=False,
        min_value=0,
        widget=forms.NumberInput(attrs={**TEXT_INPUT, "step": "0.001", "min": 0}),
        label="Low-stock threshold",
    )

    def __init__(self, *args, product=None, **kwargs):
        self.product = product
        super().__init__(*args, **kwargs)
        self.fields["availability_status"].help_text = (
            "What customers see on the product card right now."
        )
        self.fields["track_stock"].help_text = (
            "Turn this on to track exact quantities for the default selling "
            "option. Leave it off for made-to-order or untracked items."
        )
        self.fields["quantity_available"].help_text = (
            "How many units are currently available. Only used when stock "
            "tracking is on."
        )
        self.fields["low_stock_threshold"].help_text = (
            "Optional warning level. When stock falls to or below this number, "
            "the variant can be treated as low stock."
        )
        if product is not None:
            self.fields["availability_status"].initial = product.availability_status
            variant = (
                product.variants.filter(is_default=True).first()
                or product.variants.order_by("sort_order", "pk").first()
            )
            if variant is not None:
                self.variant = variant
                inventory = getattr(variant, "inventory", None)
                self.fields["track_stock"].initial = bool(
                    inventory and inventory.track_stock
                )
                self.fields["quantity_available"].initial = (
                    inventory.quantity_available if inventory else 0
                )
                self.fields["low_stock_threshold"].initial = (
                    inventory.low_stock_threshold if inventory else None
                )

    def save(self):
        product = self.product
        product.availability_status = self.cleaned_data["availability_status"]
        product.save(update_fields=["availability_status", "updated_at"])

        variant = (
            product.variants.filter(is_default=True).first()
            or product.variants.order_by("sort_order", "pk").first()
        )
        if variant is None:
            return product

        inventory, _ = Inventory.objects.get_or_create(variant=variant)
        inventory.track_stock = self.cleaned_data.get("track_stock", False)
        inventory.quantity_available = (
            self.cleaned_data.get("quantity_available") or 0
        )
        inventory.low_stock_threshold = self.cleaned_data.get(
            "low_stock_threshold"
        )
        inventory.save()
        return product
