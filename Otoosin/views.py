import hashlib
import hmac
import json
import logging
import secrets
from datetime import timedelta
from decimal import Decimal
from functools import wraps
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group
from django.contrib.auth.tokens import default_token_generator
from django.contrib.auth.views import (
    LoginView,
    LogoutView,
    PasswordResetConfirmView,
)
from django.core.cache import cache
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import DatabaseError, transaction
from django.db.models import Count, OuterRef, Prefetch, Q, Subquery
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from . import paystack
from .audit import record_audit
from .cart import (
    CartPayloadError,
    build_checkout_lines,
    validate_cart_request,
)
from .catalogue import public_products
from .email_service import send_email
from .transactional_emails import (
    staff_invitation_email,
    staff_password_reset_email,
)
from .forms import (
    CategoryForm,
    CheckoutForm,
    ContactForm,
    ContactMessageNoteForm,
    ContactMessageStatusForm,
    DeliveryLocationForm,
    ImageFormSet,
    OrderStatusUpdateForm,
    PickupLocationForm,
    ProductForm,
    ProductInventoryForm,
    SiteConfigurationForm,
    STAFF_ROLE_CHOICES,
    StaffActivationForm,
    StaffInviteForm,
    StaffLoginForm,
    StaffPasswordResetRequestForm,
    StaffRoleForm,
    StaffSetPasswordForm,
    VariantFormSet,
)
from .models import (
    Category,
    ContactMessage,
    DeliveryLocation,
    EmailDelivery,
    Order,
    OrderItem,
    OrderStatusEvent,
    Payment,
    PaymentWebhookEvent,
    PickupLocation,
    Product,
    ProductVariant,
    SiteConfiguration,
    StaffInvitation,
)
from .orders import (
    CheckoutError,
    create_order,
    create_payment_attempt,
    expected_delivery_date,
    money,
    restore_stock,
)
from .payments import process_webhook, verify_payment
from .checkout_views import (
    checkout,
    order_confirmation,
    order_retry_payment,
    payment_callback,
    paystack_webhook,
)
from .permissions import ROLE_GROUPS


logger = logging.getLogger(__name__)


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


LOGIN_MAX_ATTEMPTS = 5
LOGIN_WINDOW_SECONDS = 900
CONTACT_MAX_ATTEMPTS = 5
CONTACT_WINDOW_SECONDS = 600


def _client_ip(request):
    return request.META.get("REMOTE_ADDR") or "unknown"


def _throttle_key(prefix, request, identifier=""):
    raw = f"{prefix}:{_client_ip(request)}:{identifier.strip().lower()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class StaffLoginView(LoginView):
    template_name = "admin-login.html"
    authentication_form = StaffLoginForm
    redirect_authenticated_user = False

    def post(self, request, *args, **kwargs):
        identifier = (request.POST.get("username") or "").strip()
        key = _throttle_key("staff-login", request, identifier)
        if cache.get(key, 0) >= LOGIN_MAX_ATTEMPTS:
            form = self.get_form()
            form.add_error(
                None,
                "Too many sign-in attempts. Please wait a few minutes and try again.",
            )
            record_audit(
                action="login_throttled",
                summary=f"Sign-in blocked after repeated attempts for {identifier[:80]}.",
            )
            return self.render_to_response(self.get_context_data(form=form))
        return super().post(request, *args, **kwargs)

    def form_invalid(self, form):
        identifier = (self.request.POST.get("username") or "").strip()
        key = _throttle_key("staff-login", self.request, identifier)
        attempts = cache.get(key, 0) + 1
        cache.set(key, attempts, LOGIN_WINDOW_SECONDS)
        record_audit(
            action="login_failed",
            summary=(
                f"Failed staff sign-in for {identifier[:80]} "
                f"(attempt {attempts})."
            ),
        )
        return super().form_invalid(form)

    def form_valid(self, form):
        identifier = (self.request.POST.get("username") or "").strip()
        cache.delete(_throttle_key("staff-login", self.request, identifier))
        response = super().form_valid(form)
        record_audit(
            actor=self.request.user,
            action="login_success",
            target=self.request.user,
            summary=f"Staff sign-in for {self.request.user.get_username()}.",
        )
        return response


class StaffLogoutView(LogoutView):
    next_page = "Otoosin:staff_login"

    def post(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            record_audit(
                actor=request.user,
                action="logout",
                target=request.user,
                summary=f"Staff sign-out for {request.user.get_username()}.",
            )
        return super().post(request, *args, **kwargs)


def staff_password_reset(request):
    form = StaffPasswordResetRequestForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"].strip().lower()
        user = (
            get_user_model()
            .objects.filter(email__iexact=email, is_staff=True, is_active=True)
            .first()
        )
        if user:
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            path = reverse(
                "Otoosin:staff_password_reset_confirm",
                kwargs={"uidb64": uid, "token": token},
            )
            reset_url = f"{settings.SITE_URL.rstrip('/')}{path}"
            message = staff_password_reset_email(user, reset_url)
            delivery = send_email(
                category=EmailDelivery.Category.PASSWORD_RESET,
                recipient=user.email,
                subject=message["subject"],
                text=message["text"],
                html=message["html"],
            )
            record_audit(
                actor=user,
                action="password_reset_requested",
                target=user,
                summary=(
                    "Staff password reset requested; email "
                    f"{'accepted by Resend' if delivery.status == EmailDelivery.Status.SENT else 'could not be sent'}."
                ),
            )
        return redirect("Otoosin:staff_password_reset_done")
    return render(request, "admin-password-reset.html", {"form": form})


class StaffPasswordResetConfirmView(PasswordResetConfirmView):
    template_name = "admin-password-reset-confirm.html"
    form_class = StaffSetPasswordForm
    success_url = reverse_lazy("Otoosin:staff_password_reset_complete")

    def get_user(self, uidb64):
        user = super().get_user(uidb64)
        if user is not None and (not user.is_staff or not user.is_active):
            return None
        return user

    def form_valid(self, form):
        response = super().form_valid(form)
        record_audit(
            actor=getattr(self, "user", None),
            action="password_reset_completed",
            target=getattr(self, "user", None),
            summary="Staff password was reset through a valid reset link.",
        )
        return response


def staff_password_reset_done(request):
    return render(request, "admin-password-reset-done.html")


def staff_password_reset_complete(request):
    return render(request, "admin-password-reset-complete.html")


def _staff_role_group(role):
    return Group.objects.filter(name=ROLE_GROUPS.get(role, "")).first()


def _apply_staff_role(user, role):
    role_names = set(ROLE_GROUPS.values())
    user.groups.remove(*user.groups.filter(name__in=role_names))
    group = _staff_role_group(role)
    if group is not None:
        user.groups.add(group)


def _usable_owner_count(exclude_user=None):
    users = get_user_model().objects.filter(is_active=True).filter(
        Q(is_superuser=True) | Q(groups__name=ROLE_GROUPS["owner"])
    )
    if exclude_user is not None:
        users = users.exclude(pk=exclude_user.pk)
    return users.distinct().count()


def _unique_staff_username(email):
    User = get_user_model()
    base = (email.split("@", 1)[0] or "staff").strip().lower()
    base = "".join(char for char in base if char.isalnum() or char in "._-")
    base = base[:120] or "staff"
    candidate = base
    counter = 2
    while User.objects.filter(username__iexact=candidate).exists():
        candidate = f"{base}-{counter}"
        counter += 1
    return candidate


def _new_staff_invitation(user, role, actor, email=None):
    raw_token = secrets.token_urlsafe(32)
    invitation = StaffInvitation.objects.create(
        user=user,
        email=email or user.email,
        role=role,
        token_hash=StaffInvitation.hash_token(raw_token),
        expires_at=StaffInvitation.default_expiry(),
        created_by=actor if getattr(actor, "pk", None) else None,
    )
    return invitation, raw_token


def _invitation_url(raw_token, invitation):
    uid = urlsafe_base64_encode(force_bytes(invitation.user_id))
    path = reverse(
        "Otoosin:staff_activate",
        kwargs={"uidb64": uid, "token": raw_token},
    )
    return f"{settings.SITE_URL.rstrip('/')}{path}"


def _send_staff_invitation(invitation, raw_token, actor):
    url = _invitation_url(raw_token, invitation)
    message = staff_invitation_email(invitation, url)
    delivery = send_email(
        category=EmailDelivery.Category.STAFF_INVITE,
        recipient=invitation.email,
        subject=message["subject"],
        text=message["text"],
        html=message["html"],
    )
    invitation.email_delivery = delivery
    invitation.save(update_fields=["email_delivery", "updated_at"])
    record_audit(
        actor=actor,
        action="staff_invitation_sent"
        if delivery.status == EmailDelivery.Status.SENT
        else "staff_invitation_email_failed",
        target=invitation.user,
        summary=(
            f"Invitation email for {invitation.email} as "
            f"{invitation.get_role_display()} was "
            f"{'accepted by Resend' if delivery.status == EmailDelivery.Status.SENT else 'not sent'}."
        ),
    )
    return delivery


def staff_activate(request, uidb64, token):
    User = get_user_model()
    user = None
    invitation = None
    try:
        user_id = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=user_id, is_staff=True)
    except (ValueError, TypeError, OverflowError, User.DoesNotExist):
        user = None

    if user is not None and token:
        invitation = (
            StaffInvitation.objects.filter(
                user=user, token_hash=StaffInvitation.hash_token(token)
            )
            .order_by("-created_at")
            .first()
        )
    valid = bool(invitation and invitation.is_pending)

    if not valid:
        return render(
            request,
            "admin-activate.html",
            {"invalid": True},
            status=400,
        )

    form = StaffActivationForm(user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            form.save()
            user.is_active = True
            user.is_staff = True
            user.save(update_fields=["is_active", "is_staff", "password"])
            _apply_staff_role(user, invitation.role)
            invitation.used_at = timezone.now()
            invitation.save(update_fields=["used_at", "updated_at"])
            StaffInvitation.objects.filter(
                user=user, used_at__isnull=True, revoked_at__isnull=True
            ).exclude(pk=invitation.pk).update(revoked_at=timezone.now())
            record_audit(
                actor=user,
                action="staff_activated",
                target=user,
                summary=(
                    f"Staff account {user.get_username()} activated as "
                    f"{invitation.get_role_display()}."
                ),
            )
        messages.success(request, "Your staff account is active. Please sign in.")
        return redirect("Otoosin:staff_login")

    return render(
        request,
        "admin-activate.html",
        {"invalid": False, "form": form, "invitation": invitation},
    )


@_staff_permission("Otoosin.manage_staff")
def staff_team(request):
    User = get_user_model()

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "invite":
            form = StaffInviteForm(request.POST)
            if form.is_valid():
                email = form.cleaned_data["email"]
                if User.objects.filter(email__iexact=email).exists():
                    messages.error(
                        request,
                        "An account with this email already exists. Use role or activation controls instead.",
                    )
                elif form.cleaned_data["role"] not in StaffInvitation.Role.values:
                    messages.error(request, "Choose a valid staff role.")
                else:
                    with transaction.atomic():
                        user = User.objects.create_user(
                            username=_unique_staff_username(email),
                            email=email,
                            first_name=form.cleaned_data["first_name"].strip(),
                            last_name=form.cleaned_data["last_name"].strip(),
                            is_staff=True,
                            is_active=False,
                        )
                        user.set_unusable_password()
                        user.save(update_fields=["password"])
                        _apply_staff_role(user, form.cleaned_data["role"])
                        invitation, raw_token = _new_staff_invitation(
                            user, form.cleaned_data["role"], request.user
                        )
                    delivery = _send_staff_invitation(
                        invitation, raw_token, request.user
                    )
                    if delivery.status == EmailDelivery.Status.SENT:
                        messages.success(
                            request,
                            f"Invitation sent to {email}. The account stays inactive until it is activated.",
                        )
                    else:
                        messages.error(
                            request,
                            "The invitation was created but the email was not sent. Use Resend invitation after checking Resend configuration.",
                        )
            else:
                messages.error(request, "Check the invitation details and try again.")
            return redirect("Otoosin:staff_team")

        if action == "resend":
            invitation = get_object_or_404(
                StaffInvitation, pk=request.POST.get("invitation_id")
            )
            if invitation.used_at or invitation.revoked_at:
                messages.error(request, "This invitation can no longer be resent.")
                return redirect("Otoosin:staff_team")
            raw_token = secrets.token_urlsafe(32)
            invitation.token_hash = StaffInvitation.hash_token(raw_token)
            invitation.expires_at = StaffInvitation.default_expiry()
            invitation.save(
                update_fields=["token_hash", "expires_at", "updated_at"]
            )
            delivery = _send_staff_invitation(
                invitation, raw_token, request.user
            )
            if delivery.status == EmailDelivery.Status.SENT:
                messages.success(
                    request, f"Invitation resent to {invitation.email}."
                )
            else:
                messages.error(
                    request,
                    "The invitation email could not be sent. Check the Resend configuration and try again.",
                )
            return redirect("Otoosin:staff_team")

        if action == "change_role":
            target = get_object_or_404(User, pk=request.POST.get("user_id"), is_staff=True)
            form = StaffRoleForm(request.POST)
            if not form.is_valid() or form.cleaned_data["role"] not in StaffInvitation.Role.values:
                messages.error(request, "Choose a valid staff role.")
                return redirect("Otoosin:staff_team")
            role = form.cleaned_data["role"]
            target_is_owner = target.is_superuser or target.groups.filter(
                name=ROLE_GROUPS["owner"]
            ).exists()
            if (
                target_is_owner
                and role != StaffInvitation.Role.OWNER
                and _usable_owner_count(exclude_user=target) < 1
            ):
                messages.error(
                    request,
                    "You cannot remove the last usable owner account.",
                )
                return redirect("Otoosin:staff_team")
            with transaction.atomic():
                _apply_staff_role(target, role)
                target.staff_invitations.filter(
                    used_at__isnull=True, revoked_at__isnull=True
                ).update(role=role, updated_at=timezone.now())
                record_audit(
                    actor=request.user,
                    action="staff_role_changed",
                    target=target,
                    summary=f"{target.get_username()} role changed to {role}.",
                )
            messages.success(request, "Staff role updated.")
            return redirect("Otoosin:staff_team")

        if action == "toggle_active":
            target = get_object_or_404(User, pk=request.POST.get("user_id"), is_staff=True)
            deactivating = target.is_active
            target_is_owner = target.is_superuser or target.groups.filter(
                name=ROLE_GROUPS["owner"]
            ).exists()
            if (
                deactivating
                and target_is_owner
                and _usable_owner_count(exclude_user=target) < 1
            ):
                messages.error(
                    request,
                    "You cannot disable the last usable owner account.",
                )
                return redirect("Otoosin:staff_team")
            target.is_active = not target.is_active
            target.save(update_fields=["is_active"])
            if not target.is_active:
                target.staff_invitations.filter(
                    used_at__isnull=True, revoked_at__isnull=True
                ).update(revoked_at=timezone.now())
            record_audit(
                actor=request.user,
                action="staff_activated" if target.is_active else "staff_deactivated",
                target=target,
                summary=(
                    f"Staff account {target.get_username()} was "
                    f"{'activated' if target.is_active else 'deactivated'}."
                ),
            )
            messages.success(
                request,
                f"{target.get_username()} is now {'active' if target.is_active else 'inactive'}.",
            )
            return redirect("Otoosin:staff_team")

        messages.error(request, "Unknown team action.")
        return redirect("Otoosin:staff_team")

    staff_users = (
        User.objects.filter(is_staff=True)
        .prefetch_related("groups")
        .order_by("-is_active", "username")
    )
    invitations = {
        invitation.user_id: invitation
        for invitation in StaffInvitation.objects.filter(
            user_id__in=[user.pk for user in staff_users]
        )
        .select_related("email_delivery")
        .order_by("created_at", "pk")
    }
    rows = []
    for user in staff_users:
        role = "owner" if user.is_superuser else ""
        if not role:
            member_group = user.groups.filter(
                name__in=ROLE_GROUPS.values()
            ).first()
            if member_group:
                role = next(
                    (
                        key
                        for key, name in ROLE_GROUPS.items()
                        if name == member_group.name
                    ),
                    "",
                )
        rows.append(
            {
                "user": user,
                "role": role,
                "invitation": invitations.get(user.pk),
            }
        )
    return render(
        request,
        "admin-team.html",
        {
            "rows": rows,
            "invite_form": StaffInviteForm(),
            "role_choices": STAFF_ROLE_CHOICES,
            "resend_uses_test_sender": "onboarding@resend.dev"
            in (getattr(settings, "RESEND_FROM_EMAIL", "") or "").lower(),
        },
    )


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
            if is_create:
                # Return to a blank add form so staff can keep adding products
                # without reopening the product they just created.
                return redirect("Otoosin:staff_product_create")
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
    can_view_messages = request.user.has_perm("Otoosin.view_contactmessage")
    can_view_orders = request.user.has_perm("Otoosin.view_order")
    order_summary = {
        "total": 0,
        "pending": 0,
        "paid": 0,
    }
    if can_view_orders:
        order_summary = {
            "total": Order.objects.count(),
            "pending": Order.objects.filter(
                status=Order.Status.PENDING
            ).count(),
            "paid": Payment.objects.filter(
                status=Payment.Status.PAID, verified_at__isnull=False
            )
            .values("order_id")
            .distinct()
            .count(),
        }
    contact_summary = {
        "total": 0,
        "new": 0,
    }
    recent_messages = []
    if can_view_messages:
        contact_summary = ContactMessage.objects.aggregate(
            total=Count("id"),
            new=Count("id", filter=Q(status=ContactMessage.Status.NEW)),
        )
        recent_messages = list(
            ContactMessage.objects.order_by("-created_at", "-pk")[:5]
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
            "can_view_messages": can_view_messages,
            "can_view_orders": can_view_orders,
            "order_summary": order_summary,
            "contact_summary": contact_summary,
            "recent_messages": recent_messages,
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


@_staff_permission("Otoosin.view_contactmessage")
def staff_messages(request):
    queryset = ContactMessage.objects.all()
    search = (request.GET.get("q") or "").strip()[:120]
    status_filter = (request.GET.get("status") or "").strip()
    if search:
        queryset = queryset.filter(
            Q(name__icontains=search)
            | Q(email__icontains=search)
            | Q(phone__icontains=search)
            | Q(message__icontains=search)
        )
    if status_filter in ContactMessage.Status.values:
        queryset = queryset.filter(status=status_filter)
    counts = ContactMessage.objects.aggregate(
        total=Count("id"),
        new=Count("id", filter=Q(status=ContactMessage.Status.NEW)),
        read=Count("id", filter=Q(status=ContactMessage.Status.READ)),
        replied=Count("id", filter=Q(status=ContactMessage.Status.REPLIED)),
        closed=Count("id", filter=Q(status=ContactMessage.Status.CLOSED)),
    )
    paginator, page_obj, page_range = _paginate(request, queryset, 25)
    return render(
        request,
        "admin-messages.html",
        {
            "messages_list": page_obj,
            "paginator": paginator,
            "page_obj": page_obj,
            "page_range": page_range,
            "pagination_label": "Enquiry pages",
            "counts": counts,
            "search": search,
            "status_filter": status_filter,
            "status_choices": ContactMessage.Status.choices,
        },
    )


@_staff_permission("Otoosin.view_contactmessage")
def staff_message_detail(request, pk):
    enquiry = get_object_or_404(ContactMessage, pk=pk)
    status_form = ContactMessageStatusForm(
        initial={"status": enquiry.status}
    )
    note_form = ContactMessageNoteForm(
        initial={"internal_notes": enquiry.internal_notes}
    )

    if request.method == "POST":
        if not request.user.has_perm("Otoosin.change_contactmessage"):
            raise PermissionDenied
        action = request.POST.get("action")
        if action == "status":
            status_form = ContactMessageStatusForm(request.POST)
            if status_form.is_valid():
                new_status = status_form.cleaned_data["status"]
                old_status = enquiry.status
                enquiry.status = new_status
                if new_status == ContactMessage.Status.NEW:
                    enquiry.handled_by = None
                    enquiry.handled_at = None
                else:
                    enquiry.handled_by = request.user
                    enquiry.handled_at = timezone.now()
                enquiry.save(
                    update_fields=[
                        "status",
                        "handled_by",
                        "handled_at",
                        "updated_at",
                    ]
                )
                record_audit(
                    actor=request.user,
                    action="contact_status_changed",
                    target=enquiry,
                    summary=(
                        f"Enquiry #{enquiry.pk} status changed from "
                        f"{old_status} to {new_status}."
                    ),
                )
                messages.success(request, "Enquiry status updated.")
                return redirect("Otoosin:staff_message_detail", pk=enquiry.pk)
            messages.error(request, "Choose a valid enquiry status.")
        elif action == "notes":
            note_form = ContactMessageNoteForm(request.POST)
            if note_form.is_valid():
                enquiry.internal_notes = note_form.cleaned_data["internal_notes"]
                enquiry.save(update_fields=["internal_notes", "updated_at"])
                record_audit(
                    actor=request.user,
                    action="contact_notes_updated",
                    target=enquiry,
                    summary=f"Internal notes updated for enquiry #{enquiry.pk}.",
                )
                messages.success(request, "Internal notes saved.")
                return redirect("Otoosin:staff_message_detail", pk=enquiry.pk)
            messages.error(request, "The internal note is too long.")

    return render(
        request,
        "admin-message-detail.html",
        {
            "enquiry": enquiry,
            "status_form": status_form,
            "note_form": note_form,
            "can_change": request.user.has_perm(
                "Otoosin.change_contactmessage"
            ),
        },
    )


def _settings_redirect():
    return redirect("Otoosin:staff_settings")


def _settings_context(request, *, business_form=None):
    config = SiteConfiguration.load()
    return {
        "config": config,
        "business_form": business_form or SiteConfigurationForm(instance=config),
    }


@_staff_permission("Otoosin.change_siteconfiguration")
def staff_settings(request):
    config = SiteConfiguration.load()

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "business":
            form = SiteConfigurationForm(request.POST, instance=config)
            if form.is_valid():
                changed = list(form.changed_data)
                with transaction.atomic():
                    form.save()
                    record_audit(
                        actor=request.user,
                        action="site_configuration_updated",
                        target=config,
                        summary=(
                            "Business settings updated: "
                            + (", ".join(changed) if changed else "no field changes")
                            + "."
                        ),
                    )
                messages.success(request, "Business settings saved.")
                return _settings_redirect()
            return render(
                request,
                "admin-settings.html",
                _settings_context(request, business_form=form),
            )

        messages.error(request, "Unknown settings action.")
        return _settings_redirect()

    return render(
        request,
        "admin-settings.html",
        _settings_context(request),
    )


def _delivery_redirect():
    return redirect("Otoosin:staff_delivery")


def _next_sort_order(model):
    latest = (
        model.objects.order_by("-sort_order")
        .values_list("sort_order", flat=True)
        .first()
    )
    return (latest or 0) + 1


def _delivery_context(request, *, delivery_form=None, pickup_form=None):
    edit_delivery = None
    delivery_id = request.GET.get("edit_delivery")
    if delivery_id:
        edit_delivery = get_object_or_404(DeliveryLocation, pk=delivery_id)
    edit_pickup = None
    pickup_id = request.GET.get("edit_pickup")
    if pickup_id:
        edit_pickup = get_object_or_404(PickupLocation, pk=pickup_id)
    if delivery_form is not None and delivery_form.instance.pk:
        edit_delivery = delivery_form.instance
    if pickup_form is not None and pickup_form.instance.pk:
        edit_pickup = pickup_form.instance
    return {
        "delivery_form": delivery_form or DeliveryLocationForm(instance=edit_delivery, auto_id="id_delivery_%s"),
        "edit_delivery": edit_delivery,
        "delivery_locations": DeliveryLocation.objects.all(),
        "pickup_form": pickup_form or PickupLocationForm(instance=edit_pickup, auto_id="id_pickup_%s"),
        "edit_pickup": edit_pickup,
        "pickup_locations": PickupLocation.objects.all(),
        "can_add_delivery": request.user.has_perm("Otoosin.add_deliverylocation"),
        "can_change_delivery": request.user.has_perm(
            "Otoosin.change_deliverylocation"
        ),
        "can_add_pickup": request.user.has_perm("Otoosin.add_pickuplocation"),
        "can_change_pickup": request.user.has_perm(
            "Otoosin.change_pickuplocation"
        ),
    }


@_staff_permission("Otoosin.view_deliverylocation")
def staff_delivery_locations(request):
    if request.method == "POST":
        action = request.POST.get("action")
        if action in {"delivery_create", "delivery_edit"}:
            if action == "delivery_create" and not request.user.has_perm(
                "Otoosin.add_deliverylocation"
            ):
                raise PermissionDenied
            instance = None
            if action == "delivery_edit":
                if not request.user.has_perm("Otoosin.change_deliverylocation"):
                    raise PermissionDenied
                instance = get_object_or_404(
                    DeliveryLocation, pk=request.POST.get("location_id")
                )
            form = DeliveryLocationForm(request.POST, instance=instance, auto_id="id_delivery_%s")
            if form.is_valid():
                with transaction.atomic():
                    location = form.save(commit=False)
                    if instance is None:
                        location.sort_order = _next_sort_order(DeliveryLocation)
                    location.save()
                    record_audit(
                        actor=request.user,
                        action=(
                            "delivery_location_created"
                            if instance is None
                            else "delivery_location_updated"
                        ),
                        target=location,
                        summary=(
                            f"{location.get_location_type_display()} "
                            f"'{location.name}' saved with fee "
                            f"{location.fee if location.fee is not None else 'unset'}."
                        ),
                    )
                messages.success(request, "Delivery location saved.")
                return _delivery_redirect()
            return render(
                request,
                "admin-delivery.html",
                _delivery_context(request, delivery_form=form),
            )

        if action == "delivery_toggle":
            if not request.user.has_perm("Otoosin.change_deliverylocation"):
                raise PermissionDenied
            location = get_object_or_404(
                DeliveryLocation, pk=request.POST.get("location_id")
            )
            if not location.is_active and location.fee is None:
                messages.error(
                    request,
                    "Set an approved fee before activating this location.",
                )
                return _delivery_redirect()
            location.is_active = not location.is_active
            if location.is_active:
                try:
                    location.full_clean()
                except ValidationError:
                    messages.error(
                        request,
                        "This location cannot be activated until its details are valid.",
                    )
                    return _delivery_redirect()
            location.save(update_fields=["is_active", "updated_at"])
            record_audit(
                actor=request.user,
                action="delivery_location_toggled",
                target=location,
                summary=(
                    f"'{location.name}' is now "
                    f"{'active' if location.is_active else 'inactive'}."
                ),
            )
            messages.success(request, "Delivery location availability updated.")
            return _delivery_redirect()

        if action in {"pickup_create", "pickup_edit"}:
            if action == "pickup_create" and not request.user.has_perm(
                "Otoosin.add_pickuplocation"
            ):
                raise PermissionDenied
            instance = None
            if action == "pickup_edit":
                if not request.user.has_perm("Otoosin.change_pickuplocation"):
                    raise PermissionDenied
                instance = get_object_or_404(
                    PickupLocation, pk=request.POST.get("pickup_id")
                )
            form = PickupLocationForm(request.POST, instance=instance, auto_id="id_pickup_%s")
            if form.is_valid():
                with transaction.atomic():
                    pickup = form.save(commit=False)
                    if instance is None:
                        pickup.sort_order = _next_sort_order(PickupLocation)
                    pickup.save()
                    record_audit(
                        actor=request.user,
                        action=(
                            "pickup_location_created"
                            if instance is None
                            else "pickup_location_updated"
                        ),
                        target=pickup,
                        summary=f"Pickup location '{pickup.name}' saved.",
                    )
                messages.success(request, "Pickup location saved.")
                return _delivery_redirect()
            return render(
                request,
                "admin-delivery.html",
                _delivery_context(request, pickup_form=form),
            )

        if action == "pickup_toggle":
            if not request.user.has_perm("Otoosin.change_pickuplocation"):
                raise PermissionDenied
            pickup = get_object_or_404(
                PickupLocation, pk=request.POST.get("pickup_id")
            )
            pickup.is_active = not pickup.is_active
            pickup.save(update_fields=["is_active", "updated_at"])
            record_audit(
                actor=request.user,
                action="pickup_location_toggled",
                target=pickup,
                summary=(
                    f"Pickup '{pickup.name}' is now "
                    f"{'active' if pickup.is_active else 'inactive'}."
                ),
            )
            messages.success(request, "Pickup availability updated.")
            return _delivery_redirect()

        messages.error(request, "Unknown delivery action.")
        return _delivery_redirect()

    return render(
        request,
        "admin-delivery.html",
        _delivery_context(request),
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
    featured = list(
        public_products()
        .filter(is_featured=True)
        .order_by("-created_at", "-pk")[:8]
    )
    return render(
        request,
        "index.html",
        {"featured_products": featured},
    )


def about(request):
    return render(request, "about.html")


def contact(request):
    submitted = request.GET.get("sent") == "1"
    form = ContactForm()
    status = 200

    if request.method == "POST":
        key = _throttle_key("contact", request)
        attempts = cache.get(key, 0)
        if attempts >= CONTACT_MAX_ATTEMPTS:
            form = ContactForm(request.POST)
            form.is_valid()
            form.add_error(
                None,
                "Too many enquiries were submitted from this connection. Please try again later.",
            )
            status = 429
        else:
            form = ContactForm(request.POST)
            if form.is_valid():
                try:
                    with transaction.atomic():
                        form.save()
                except DatabaseError:
                    logger.exception("Could not save contact enquiry.")
                    form.add_error(
                        None,
                        "We could not save your enquiry right now. Please try again shortly.",
                    )
                    status = 500
                else:
                    cache.set(key, attempts + 1, CONTACT_WINDOW_SECONDS)
                    logger.info("Contact enquiry stored successfully.")
                    return redirect(f"{reverse('Otoosin:contact')}?sent=1#contact-form")
            else:
                logger.warning(
                    "Contact form rejected. Field errors: %s",
                    ", ".join(sorted(form.errors.keys())) or "none",
                )
                cache.set(key, attempts + 1, CONTACT_WINDOW_SECONDS)
                status = 200

    return render(
        request,
        "contact.html",
        {"form": form, "submitted": submitted},
        status=status,
    )


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


def privacy(request):
    return render(request, "privacy.html")


def terms(request):
    return render(request, "terms.html")


def not_found(request, exception):
    return render(request, "404.html", status=404)


@_staff_permission("Otoosin.view_order")
def staff_orders(request):
    latest_payments = Payment.objects.filter(order=OuterRef("pk")).order_by(
        "-created_at", "-pk"
    )
    orders = (
        Order.objects.select_related("delivery_location", "pickup_location")
        .prefetch_related("items")
        .annotate(
            line_count=Count("items", distinct=True),
            latest_payment_status=Subquery(latest_payments.values("status")[:1]),
            latest_payment_reference=Subquery(
                latest_payments.values("provider_reference")[:1]
            ),
            has_paid=Count(
                "payments",
                filter=Q(
                    payments__status=Payment.Status.PAID,
                    payments__verified_at__isnull=False,
                ),
                distinct=True,
            ),
        )
    )

    q = (request.GET.get("q") or "").strip()
    status_filter = (request.GET.get("status") or "").strip()
    payment_filter = (request.GET.get("payment") or "").strip()
    receive_filter = (request.GET.get("receive") or "").strip()
    date_from = (request.GET.get("date_from") or "").strip()
    date_to = (request.GET.get("date_to") or "").strip()
    sort = (request.GET.get("sort") or "newest").strip()

    if q:
        orders = orders.filter(
            Q(reference__icontains=q)
            | Q(customer_name__icontains=q)
            | Q(customer_phone__icontains=q)
            | Q(customer_email__icontains=q)
        )
    if status_filter in Order.Status.values:
        orders = orders.filter(status=status_filter)
    if receive_filter in Order.ReceiveMethod.values:
        orders = orders.filter(receive_method=receive_filter)
    parsed_from = parse_date(date_from) if date_from else None
    parsed_to = parse_date(date_to) if date_to else None
    if parsed_from:
        orders = orders.filter(placed_at__date__gte=parsed_from)
    else:
        date_from = ""
    if parsed_to:
        orders = orders.filter(placed_at__date__lte=parsed_to)
    else:
        date_to = ""
    paid_filter = Q(
        payments__status=Payment.Status.PAID,
        payments__verified_at__isnull=False,
    )
    if payment_filter == "paid":
        orders = orders.filter(paid_filter).distinct()
    elif payment_filter == "pending":
        orders = (
            orders.filter(
                payments__status__in=[
                    Payment.Status.PENDING,
                    Payment.Status.INITIATED,
                ]
            )
            .exclude(paid_filter)
            .distinct()
        )
    elif payment_filter == "failed":
        orders = (
            orders.filter(payments__status=Payment.Status.FAILED)
            .exclude(paid_filter)
            .distinct()
        )
    elif payment_filter == "refunded":
        orders = orders.filter(payments__status=Payment.Status.REFUNDED).distinct()
    elif payment_filter == "unpaid":
        orders = orders.exclude(paid_filter).distinct()

    ordering = {
        "oldest": ("placed_at", "pk"),
        "total-desc": ("-total", "-placed_at"),
        "total-asc": ("total", "-placed_at"),
    }.get(sort, ("-placed_at", "-pk"))
    orders = orders.order_by(*ordering)
    paginator, page_obj, page_range = _paginate(request, orders, 25)

    summary = {
        "total": Order.objects.count(),
        "pending": Order.objects.filter(status=Order.Status.PENDING).count(),
        "paid": Order.objects.filter(
            payments__status=Payment.Status.PAID,
            payments__verified_at__isnull=False,
        )
        .distinct()
        .count(),
        "cancelled": Order.objects.filter(status=Order.Status.CANCELLED).count(),
    }
    return render(
        request,
        "admin-orders.html",
        {
            "orders": page_obj,
            "page_obj": page_obj,
            "paginator": paginator,
            "page_range": page_range,
            "summary": summary,
            "filters": {
                "q": q,
                "status": status_filter,
                "payment": payment_filter,
                "receive": receive_filter,
                "date_from": date_from,
                "date_to": date_to,
                "sort": sort,
            },
        },
    )


@_staff_permission("Otoosin.view_order")
def staff_order_detail(request, reference):
    order = get_object_or_404(
        Order.objects.select_related(
            "delivery_location", "pickup_location"
        ).prefetch_related("items", "payments", "status_events"),
        reference__iexact=reference,
    )
    can_change_status = request.user.has_perm(
        "Otoosin.change_order_status"
    ) and order.status == Order.Status.PENDING
    form = OrderStatusUpdateForm(initial={"status": order.status})
    if request.method == "POST":
        if not request.user.has_perm("Otoosin.change_order_status"):
            raise PermissionDenied
        form = OrderStatusUpdateForm(request.POST)
        if form.is_valid():
            new_status = form.cleaned_data["status"]
            reason = (form.cleaned_data.get("reason") or "").strip()
            allowed = {
                Order.Status.PENDING: {
                    Order.Status.COMPLETED,
                    Order.Status.CANCELLED,
                }
            }
            try:
                with transaction.atomic():
                    locked = Order.objects.select_for_update().get(pk=order.pk)
                    old_status = locked.status
                    if new_status not in allowed.get(old_status, set()):
                        raise CheckoutError(
                            "That status change is not allowed for this order.",
                            field="status",
                        )
                    locked.status = new_status
                    locked.status_changed_at = timezone.now()
                    if new_status == Order.Status.COMPLETED:
                        locked.completed_at = timezone.now()
                    if new_status == Order.Status.CANCELLED:
                        locked.cancelled_at = timezone.now()
                    locked.save(
                        update_fields=[
                            "status",
                            "status_changed_at",
                            "completed_at",
                            "cancelled_at",
                            "updated_at",
                        ]
                    )
                    note = reason[:300]
                    if new_status == Order.Status.CANCELLED:
                        paid = locked.payments.filter(
                            status=Payment.Status.PAID,
                            verified_at__isnull=False,
                        ).exists()
                        if paid:
                            note = (
                                f"{note} Paid order cancelled; a refund or "
                                "reconciliation requires owner review."
                            )[:300]
                        restore_stock(locked)
                    OrderStatusEvent.objects.create(
                        order=locked,
                        from_status=old_status,
                        to_status=new_status,
                        actor=request.user,
                        note=note,
                    )
                    record_audit(
                        actor=request.user,
                        action="order.status_changed",
                        target=locked,
                        summary=f"{old_status} -> {new_status}",
                    )
                messages.success(request, "Order status updated.")
                return redirect(
                    reverse(
                        "Otoosin:staff_order_detail",
                        kwargs={"reference": locked.reference},
                    )
                )
            except CheckoutError as exc:
                form.add_error("status", exc.message)
            except Exception:
                logger.exception("Staff order status update failed")
                form.add_error(None, "The order could not be updated. Try again.")
        else:
            messages.error(request, "Choose a valid order status.")
    return render(
        request,
        "admin-order.html",
        {
            "order": order,
            "payment_attempts": order.payments.all(),
            "latest_payment": order.payments.order_by("-created_at", "-pk").first(),
            "status_events": order.status_events.all(),
            "status_form": form,
            "can_change_status": can_change_status,
        },
    )
