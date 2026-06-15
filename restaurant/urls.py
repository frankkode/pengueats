"""URL routes for the public website (included under '/' in the root urls.py)."""
from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

# `app_name` namespaces these routes so templates can use {% url 'restaurant:home' %}.
app_name = "restaurant"

urlpatterns = [
    path("", views.home, name="home"),
    path("recipes/", views.recipe_list, name="recipes"),
    path("menu/", views.menu, name="menu"),
    path("recipes/<slug:slug>/", views.recipe_detail, name="recipe_detail"),
    path("about/", views.about, name="about"),
    path("blog/", views.blog, name="blog"),
    path("contact/", views.contact, name="contact"),
    # --- Customer cart & online checkout (Stripe) -------------------------
    path("cart/", views.cart_view, name="cart"),
    path("cart/add/<int:pk>/", views.add_to_cart, name="add_to_cart"),
    path("cart/update/<int:pk>/", views.update_cart, name="update_cart"),
    path("cart/remove/<int:pk>/", views.remove_from_cart, name="remove_from_cart"),
    path("checkout/", views.checkout, name="checkout"),
    path("checkout/pay/", views.checkout_simulate, name="checkout_simulate"),
    path("checkout/success/", views.checkout_success, name="checkout_success"),
    path("checkout/cancel/", views.checkout_cancel, name="checkout_cancel"),
    # --- Owner authentication ---------------------------------------------
    # Django's built-in auth views do all the heavy lifting; we only supply a
    # template. The dashboard is gated behind these by @login_required.
    path(
        "login/",
        auth_views.LoginView.as_view(template_name="restaurant/login.html"),
        name="login",
    ),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    # Pingu's private owner dashboard (inventory, orders, finance, etc.)
    path("dashboard/", views.dashboard, name="dashboard"),
    # Owner actions (POST-only) performed from the dashboard.
    path("dashboard/restock/", views.restock_fish_view, name="restock"),
    path("dashboard/freshness/", views.update_freshness_view, name="update_freshness"),
    path("dashboard/order/", views.place_order_view, name="place_order"),
    path("dashboard/expense/", views.add_expense_view, name="add_expense"),
    path("dashboard/orders/seen/", views.mark_orders_seen_view, name="mark_orders_seen"),
    path("dashboard/recipe/new/", views.create_recipe_view, name="create_recipe"),
    path("dashboard/recipe/<int:pk>/edit/", views.edit_recipe_view, name="edit_recipe"),
    path("dashboard/recipe/<int:pk>/delete/", views.delete_recipe_view, name="delete_recipe"),
]
