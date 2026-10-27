from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth import views as auth_views
from django.urls import path

from . import views
from .forms import StaffLoginForm

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
        auth_views.LoginView.as_view(
            template_name="admin-login.html",
            authentication_form=StaffLoginForm,
            redirect_authenticated_user=True,
        ),
        name="staff_login",
    ),
    path(
        "staff/logout/",
        auth_views.LogoutView.as_view(next_page="Otoosin:staff_login"),
        name="staff_logout",
    ),
    path("staff/", views.staff_dashboard, name="staff_dashboard"),
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
