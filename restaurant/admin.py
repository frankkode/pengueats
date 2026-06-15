"""
Django admin configuration.

Registering models here gives Pingu a complete back-office UI for free -- add
fish, edit recipes, view orders -- without writing a single form. Great to show
live in the oral exam as 'the management dashboard'.
"""
from django.contrib import admin

from .models import (
    Chef, Customer, CustomerPreference, Expense, Fish, Order, OrderItem,
    Recipe, RecipeIngredient, Supplier,
)


class RecipeIngredientInline(admin.TabularInline):
    """Edit a recipe's required fish right on the recipe page."""
    model = RecipeIngredient
    extra = 1


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0


@admin.register(Fish)
class FishAdmin(admin.ModelAdmin):
    list_display = ("name", "quantity_kg", "cost_per_kg", "freshness", "is_low_stock")
    list_filter = ("freshness", "supplier")
    search_fields = ("name", "species")


@admin.register(Recipe)
class RecipeAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "difficulty", "price", "is_featured", "views")
    list_filter = ("category", "difficulty", "is_featured")
    search_fields = ("name", "summary")
    prepopulated_fields = {"slug": ("name",)}  # auto-fill the slug from the name
    inlines = [RecipeIngredientInline]


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("id", "customer", "status", "total", "created_at")
    list_filter = ("status",)
    inlines = [OrderItemInline]


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("name", "species", "email", "joined_on")
    search_fields = ("name", "species")


# Simple registrations for the remaining lookup/support tables.
admin.site.register(Supplier)
admin.site.register(Chef)
admin.site.register(CustomerPreference)
admin.site.register(Expense)

# Branding the admin header is a nice touch for the demo.
admin.site.site_header = "PenguEats Management"
admin.site.site_title = "PenguEats"
admin.site.index_title = "Restaurant back-office"
