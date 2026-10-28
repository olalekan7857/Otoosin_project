import re

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, SetPasswordForm
from django.forms import BaseInlineFormSet, inlineformset_factory
from django.utils.text import slugify

from .models import (
    Category,
    ContactMessage,
    DeliveryLocation,
    Inventory,
    PickupLocation,
    Product,
    ProductImage,
    ProductVariant,
    SiteConfiguration,
    StaffInvitation,
    ALLOWED_IMAGE_EXTENSIONS,
    normalise_nigerian_phone,
)
from .widgets import AdminImageInput


TEXT_INPUT = {"class": "form-control"}
SELECT_INPUT = {"class": "form-select"}
CHECKBOX_INPUT = {"class": "form-check-input"}
IMAGE_ACCEPT = ",".join(f"image/{ext}" for ext in ("jpeg", "png", "webp", "gif"))


class StaffLoginForm(AuthenticationForm):
    username = forms.CharField(
        label="Email or username",
        widget=forms.TextInput(
            attrs={
                **TEXT_INPUT,
                "autocomplete": "username",
                "autofocus": True,
                "placeholder": "Email address or username",
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

    def clean(self):
        identifier = (self.cleaned_data.get("username") or "").strip()
        if "@" in identifier:
            User = get_user_model()
            matches = list(
                User.objects.filter(email__iexact=identifier, is_staff=True)
                .order_by("-is_active", "pk")[:2]
            )
            if len(matches) == 1:
                self.cleaned_data["username"] = matches[0].get_username()
            elif len(matches) > 1:
                raise forms.ValidationError(
                    self.error_messages["invalid_login"],
                    code="invalid_login",
                    params={"username": self.username_field.verbose_name},
                )
        return super().clean()

    def confirm_login_allowed(self, user):
        if not user.is_staff or not user.is_active:
            raise forms.ValidationError(
                self.error_messages["invalid_login"],
                code="invalid_login",
                params={"username": self.username_field.verbose_name},
            )
        super().confirm_login_allowed(user)


class StaffSetPasswordForm(SetPasswordForm):
    """SetPasswordForm with the admin input styling and autocomplete hints."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("new_password1", "new_password2"):
            field = self.fields[name]
            field.widget.attrs.update(
                {
                    **TEXT_INPUT,
                    "autocomplete": "new-password",
                }
            )
        self.fields["new_password1"].widget.attrs["autofocus"] = True


class StaffActivationForm(StaffSetPasswordForm):
    username = forms.CharField(
        label="Username",
        max_length=150,
        widget=forms.TextInput(
            attrs={
                **TEXT_INPUT,
                "autocomplete": "username",
                "autocapitalize": "none",
                "spellcheck": "false",
            }
        ),
        help_text=(
            "You can sign in with your email address or this username. "
            "Change it now if you prefer something easier to remember."
        ),
    )

    def __init__(self, user, *args, **kwargs):
        super().__init__(user, *args, **kwargs)
        self.fields["username"].initial = user.get_username()

    def clean_username(self):
        value = (self.cleaned_data.get("username") or "").strip()
        if not value:
            raise forms.ValidationError("Enter a username.")
        User = get_user_model()
        field = User._meta.get_field("username")
        try:
            field.run_validators(value)
        except forms.ValidationError as exc:
            raise forms.ValidationError(exc.messages)
        if User.objects.filter(username__iexact=value).exclude(pk=self.user.pk).exists():
            raise forms.ValidationError("That username is already in use.")
        return value

    def save(self, commit=True):
        user = super().save(commit=False)
        user.username = self.cleaned_data["username"]
        if commit:
            user.save()
        return user


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
            "If you leave this unticked, the first active option is used."
        )
        self.fields["is_active"].help_text = (
            "Keep this ticked to sell the option. At least one filled option "
            "stays active automatically, even if every box is unticked."
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

        complete = []
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

            complete.append(form)
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

        if not complete:
            raise forms.ValidationError(
                "Add at least one selling option with a price."
            )

        if not active:
            first = complete[0]
            first.cleaned_data["is_active"] = True
            first.instance.is_active = True
            active.append(first)

        default = next(
            (form for form in defaults if form in active), None
        )
        if default is None:
            default = active[0]
            default.cleaned_data["is_default"] = True
            default.instance.is_default = True

        for form in defaults:
            if form is not default:
                form.cleaned_data["is_default"] = False
                form.instance.is_default = False


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


class ContactForm(forms.ModelForm):
    website = forms.CharField(
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "oto-honeypot",
                "tabindex": "-1",
                "autocomplete": "off",
                "aria-hidden": "true",
            }
        ),
        label="Website",
    )

    class Meta:
        model = ContactMessage
        fields = ["name", "email", "phone", "subject", "message"]
        widgets = {
            "name": forms.TextInput(
                attrs={
                    **TEXT_INPUT,
                    "id": "oto-contact-name",
                    "autocomplete": "name",
                    "placeholder": "e.g. Adaeze Okafor",
                    "maxlength": 120,
                    "minlength": 2,
                }
            ),
            "email": forms.EmailInput(
                attrs={
                    **TEXT_INPUT,
                    "id": "oto-contact-email",
                    "autocomplete": "email",
                    "placeholder": "you@example.com",
                }
            ),
            "phone": forms.TextInput(
                attrs={
                    **TEXT_INPUT,
                    "id": "oto-contact-phone",
                    "autocomplete": "tel",
                    "placeholder": "e.g. 0803 123 4567",
                }
            ),
            "subject": forms.Select(
                attrs={**SELECT_INPUT, "id": "oto-contact-subject"}
            ),
            "message": forms.Textarea(
                attrs={
                    **TEXT_INPUT,
                    "id": "oto-contact-message",
                    "rows": 6,
                    "minlength": 10,
                    "maxlength": 5000,
                    "placeholder": (
                        "Tell us what you need help with. If your enquiry is "
                        "about an order, include the name used at checkout and "
                        "your order reference if you have one."
                    ),
                }
            ),
        }

    def clean_name(self):
        name = " ".join((self.cleaned_data.get("name") or "").split())
        if len(name) < 2:
            raise forms.ValidationError("Enter at least 2 characters for your name.")
        return name[:120]

    def clean_phone(self):
        phone = (self.cleaned_data.get("phone") or "").strip()
        if not phone:
            return ""
        digits = re.sub(r"\D", "", phone)
        if not 7 <= len(digits) <= 15:
            raise forms.ValidationError(
                "Enter a valid phone number, or leave this field blank."
            )
        return phone[:30]

    def clean_message(self):
        message = (self.cleaned_data.get("message") or "").strip()
        if len(message) < 10:
            raise forms.ValidationError(
                "Add a little more detail so we can help (at least 10 characters)."
            )
        if len(message) > 5000:
            raise forms.ValidationError("Keep your message under 5,000 characters.")
        return message

    def clean_website(self):
        # Honeypot only. Real visitors can have this filled by password
        # managers or accessibility tools, so it must never block a genuine
        # enquiry. Rate limiting remains the primary abuse control.
        return ""

    def clean_subject(self):
        subject = self.cleaned_data.get("subject")
        if subject not in ContactMessage.Subject.values:
            raise forms.ValidationError("Choose a valid enquiry type.")
        return subject


STAFF_ROLE_CHOICES = [
    (
        StaffInvitation.Role.OWNER,
        "Owner — full access (team, catalogue, delivery, settings, enquiries)",
    ),
    (
        StaffInvitation.Role.MANAGER,
        "Manager — catalogue, delivery, settings and enquiries (no team access)",
    ),
    (
        StaffInvitation.Role.SUPPORT,
        "Support — enquiries only",
    ),
    (
        StaffInvitation.Role.FULFILMENT,
        "Fulfilment — orders only (reserved until order management is added)",
    ),
]


class StaffInviteForm(forms.Form):
    email = forms.EmailField(
        widget=forms.EmailInput(
            attrs={**TEXT_INPUT, "autocomplete": "email", "autofocus": True}
        ),
        label="Email address",
        help_text=(
            "The invitation and password-setup link are sent to this address. "
            "Use the staff member's own work or personal email."
        ),
    )
    first_name = forms.CharField(
        max_length=150,
        required=False,
        widget=forms.TextInput(attrs=TEXT_INPUT),
        label="First name",
        help_text="Optional. This appears on the staff account.",
    )
    last_name = forms.CharField(
        max_length=150,
        required=False,
        widget=forms.TextInput(attrs=TEXT_INPUT),
        label="Last name",
        help_text="Optional. This appears on the staff account.",
    )
    role = forms.ChoiceField(
        choices=STAFF_ROLE_CHOICES,
        widget=forms.Select(attrs=SELECT_INPUT),
        label="Role",
        help_text=(
            "Owner can manage everything including staff. Manager manages the "
            "catalogue, settings and messages. Support only handles enquiries. "
            "Fulfilment is reserved for orders when order management is added."
        ),
    )

    def clean_email(self):
        return self.cleaned_data["email"].strip().lower()


class StaffRoleForm(forms.Form):
    role = forms.ChoiceField(
        choices=STAFF_ROLE_CHOICES,
        widget=forms.Select(attrs=SELECT_INPUT),
        label="New role",
        help_text="The new permissions take effect on the staff member's next request.",
    )


class SiteConfigurationForm(forms.ModelForm):
    class Meta:
        model = SiteConfiguration
        fields = [
            "business_name",
            "address",
            "contact_phone",
            "whatsapp_number",
            "support_email",
            "description",
            "delivery_cutoff_time",
            "delivery_cutoff_note",
        ]
        widgets = {
            "business_name": forms.TextInput(attrs={**TEXT_INPUT, "maxlength": 120}),
            "address": forms.TextInput(attrs={**TEXT_INPUT, "maxlength": 300}),
            "contact_phone": forms.TextInput(attrs={**TEXT_INPUT, "inputmode": "tel"}),
            "whatsapp_number": forms.TextInput(attrs={**TEXT_INPUT, "inputmode": "tel"}),
            "support_email": forms.EmailInput(attrs=TEXT_INPUT),
            "description": forms.Textarea(attrs={**TEXT_INPUT, "rows": 4, "maxlength": 1500}),
            "delivery_cutoff_time": forms.TimeInput(attrs={**TEXT_INPUT, "type": "time"}),
            "delivery_cutoff_note": forms.TextInput(attrs={**TEXT_INPUT, "maxlength": 300}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["business_name"].help_text = (
            "The public business name used in page titles, metadata and contact copy."
        )
        self.fields["address"].help_text = (
            "Optional public business address. Add a full, customer-safe address."
        )
        self.fields["contact_phone"].help_text = (
            "Optional public phone number. Nigerian numbers are saved in +234 format."
        )
        self.fields["whatsapp_number"].help_text = (
            "Optional WhatsApp number used for customer contact links. "
            "Enter a Nigerian number such as 0803 123 4567."
        )
        self.fields["support_email"].help_text = (
            "Optional public support email shown where a contact email is needed."
        )
        self.fields["description"].help_text = (
            "Optional short introduction used in page descriptions and storefront metadata."
        )
        self.fields["delivery_cutoff_time"].help_text = (
            "The daily cut-off time shown to customers. Use 24-hour time."
        )
        self.fields["delivery_cutoff_note"].help_text = (
            "Optional explanation shown beside the cut-off time, for example same-day rules."
        )

    def clean_contact_phone(self):
        value = self.cleaned_data.get("contact_phone") or ""
        return normalise_nigerian_phone(value) if value else ""

    def clean_whatsapp_number(self):
        value = self.cleaned_data.get("whatsapp_number") or ""
        return normalise_nigerian_phone(value) if value else ""


class DeliveryLocationForm(forms.ModelForm):
    class Meta:
        model = DeliveryLocation
        fields = [
            "location_type",
            "name",
            "area",
            "fee",
            "customer_instructions",
            "is_active",
        ]
        widgets = {
            "location_type": forms.Select(attrs=SELECT_INPUT),
            "name": forms.TextInput(attrs={**TEXT_INPUT, "maxlength": 120}),
            "area": forms.TextInput(attrs={**TEXT_INPUT, "maxlength": 200}),
            "fee": forms.NumberInput(attrs={**TEXT_INPUT, "step": "0.01", "min": "0"}),
            "customer_instructions": forms.TextInput(attrs={**TEXT_INPUT, "maxlength": 300}),
            "is_active": forms.CheckboxInput(attrs=CHECKBOX_INPUT),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["location_type"].help_text = (
            "Doorstep is for the approved Abeokuta area. Park is for an approved "
            "park or motor-park destination."
        )
        self.fields["name"].help_text = (
            "A clear customer-facing name, for example “Abeokuta — Camp” or "
            "“Ibadan — Challenge Park”."
        )
        self.fields["area"].help_text = (
            "Optional landmark, neighbourhood or covered area that helps customers "
            "recognise the destination."
        )
        self.fields["fee"].help_text = (
            "The approved delivery fee in Naira. Required before the location can "
            "be active. Do not invent a fee."
        )
        self.fields["customer_instructions"].help_text = (
            "Required for park delivery. Tell the customer where to collect or "
            "how the park handover works."
        )
        self.fields["is_active"].help_text = (
            "Active locations can be offered to customers. New records are active "
            "by default; untick this if the destination or fee is not approved yet."
        )

    def clean_name(self):
        return (self.cleaned_data.get("name") or "").strip()

    def clean(self):
        cleaned = super().clean()
        location_type = cleaned.get("location_type")
        name = cleaned.get("name") or ""
        fee = cleaned.get("fee")
        is_active = cleaned.get("is_active")
        instructions = (cleaned.get("customer_instructions") or "").strip()
        if location_type == DeliveryLocation.LocationType.PARK:
            if not instructions:
                self.add_error(
                    "customer_instructions",
                    "Enter the park collection instructions for customers.",
                )
            cleaned["customer_instructions"] = instructions
            self.instance.city = ""
            self.instance.state = ""
        elif location_type == DeliveryLocation.LocationType.DOORSTEP:
            cleaned["customer_instructions"] = ""
            self.instance.city = "Abeokuta"
            self.instance.state = "Ogun"
        if is_active and fee is None:
            self.add_error(
                "fee",
                "Enter the approved fee before activating this delivery location.",
            )
        if location_type and name:
            duplicates = DeliveryLocation.objects.filter(
                location_type=location_type, name__iexact=name
            )
            if self.instance.pk:
                duplicates = duplicates.exclude(pk=self.instance.pk)
            if duplicates.exists():
                self.add_error(
                    "name",
                    "A location with this name already exists for this delivery type.",
                )
        return cleaned

    def save(self, commit=True):
        location = super().save(commit=False)
        if location.location_type == DeliveryLocation.LocationType.DOORSTEP:
            location.city = "Abeokuta"
            location.state = "Ogun"
        if commit:
            location.save()
            self.save_m2m()
        return location


class PickupLocationForm(forms.ModelForm):
    class Meta:
        model = PickupLocation
        fields = [
            "name",
            "address",
            "customer_instructions",
            "opening_hours",
            "is_active",
        ]
        widgets = {
            "name": forms.TextInput(attrs={**TEXT_INPUT, "maxlength": 120}),
            "address": forms.TextInput(attrs={**TEXT_INPUT, "maxlength": 300}),
            "customer_instructions": forms.Textarea(attrs={**TEXT_INPUT, "rows": 3}),
            "opening_hours": forms.TextInput(attrs={**TEXT_INPUT, "maxlength": 200}),
            "is_active": forms.CheckboxInput(attrs=CHECKBOX_INPUT),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["name"].help_text = (
            "The pickup point name customers will see, for example “Mummy-D Stores”."
        )
        self.fields["address"].help_text = (
            "The full collection address, including a landmark where useful."
        )
        self.fields["customer_instructions"].help_text = (
            "Optional instructions explaining where to go and who to meet."
        )
        self.fields["opening_hours"].help_text = (
            "Optional collection hours, for example “Mon–Sat, 8am–6pm”."
        )
        self.fields["is_active"].help_text = (
            "Active pickup locations are shown to customers. New records are "
            "active by default; untick this if the location is not approved yet."
        )


class ContactMessageStatusForm(forms.Form):
    status = forms.ChoiceField(
        choices=ContactMessage.Status.choices,
        widget=forms.Select(attrs=SELECT_INPUT),
        label="Enquiry status",
        help_text=(
            "Use New for unhandled enquiries, Read after reviewing, Replied after "
            "contacting the customer, and Closed when no further action is needed."
        ),
    )


class ContactMessageNoteForm(forms.Form):
    internal_notes = forms.CharField(
        required=False,
        max_length=5000,
        widget=forms.Textarea(attrs={**TEXT_INPUT, "rows": 5}),
        label="Internal notes",
        help_text=(
            "Private staff notes only. Do not enter payment card details or "
            "information the customer has not agreed to share."
        ),
    )


class StaffPasswordResetRequestForm(forms.Form):
    email = forms.EmailField(
        widget=forms.EmailInput(
            attrs={
                **TEXT_INPUT,
                "autocomplete": "email",
                "placeholder": "you@example.com",
                "autofocus": True,
            }
        )
    )
