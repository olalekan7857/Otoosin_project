from django.conf import settings
from django.conf.urls.static import static
from django.urls import path

from . import views

app_name = "Otoosin"

urlpatterns = [
    path("", views.index, name="index"),
    path("about/", views.about, name="about"),
    path("contact/", views.contact, name="contact"),
    path("shop/", views.product, name="product"),
    path("category/", views.product_category, name="product_category"),
    path("product-details/", views.product_details, name="product_details"),
    path("cart/", views.cart, name="cart"),
    path("api/cart/validate/", views.cart_validate, name="cart_validate"),
    path(
        "api/cart/checkout/",
        views.checkout_validate,
        name="checkout_validate",
    ),
    path("checkout/", views.checkout, name="checkout"),
    path(
        "order-confirmation/",
        views.order_confirmation,
        name="order_confirmation",
    ),
    path("privacy/", views.privacy, name="privacy"),
    path("terms/", views.terms, name="terms"),
    path(
        "staff/login/",
        views.StaffLoginView.as_view(),
        name="staff_login",
    ),
    path(
        "staff/logout/",
        views.StaffLogoutView.as_view(),
        name="staff_logout",
    ),
    path(
        "staff/password-reset/",
        views.staff_password_reset,
        name="staff_password_reset",
    ),
    path(
        "staff/password-reset/done/",
        views.staff_password_reset_done,
        name="staff_password_reset_done",
    ),
    path(
        "staff/password-reset/<uidb64>/<token>/",
        views.StaffPasswordResetConfirmView.as_view(),
        name="staff_password_reset_confirm",
    ),
    path(
        "staff/password-reset/complete/",
        views.staff_password_reset_complete,
        name="staff_password_reset_complete",
    ),
    path(
        "staff/activate/<uidb64>/<token>/",
        views.staff_activate,
        name="staff_activate",
    ),
    path("staff/", views.staff_dashboard, name="staff_dashboard"),
    path("staff/team/", views.staff_team, name="staff_team"),
    path("staff/messages/", views.staff_messages, name="staff_messages"),
    path(
        "staff/messages/<int:pk>/",
        views.staff_message_detail,
        name="staff_message_detail",
    ),
    path(
        "staff/delivery/",
        views.staff_delivery_locations,
        name="staff_delivery",
    ),
    path("staff/settings/", views.staff_settings, name="staff_settings"),
    path(
        "staff/products/",
        views.staff_product_list,
        name="staff_products",
    ),
    path(
        "staff/products/new/",
        views.staff_product_create,
        name="staff_product_create",
    ),
    path(
        "staff/products/<int:pk>/edit/",
        views.staff_product_edit,
        name="staff_product_edit",
    ),
    path(
        "staff/categories/",
        views.staff_categories,
        name="staff_categories",
    ),
    path(
        "staff/inventory/",
        views.staff_inventory,
        name="staff_inventory",
    ),
]

handler404 = "Otoosin.views.not_found"

if settings.DEBUG:
    urlpatterns += static(
        settings.MEDIA_URL, document_root=settings.MEDIA_ROOT
    )
