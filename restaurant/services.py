"""
Business logic for PenguEats.

Why a separate `services.py`?
    Views (and API endpoints) should stay thin: receive a request, call a
    service, return a response. Putting the *rules of the business* here means
    they can be unit-tested in isolation and reused by the website, the JSON
    API and management commands alike. This separation is the single most
    important "good software practice" to point at during the oral exam.

The four headline capabilities required by the task brief live here:
    1. Manage inventory          -> restock_fish()
    2. Handle customer orders    -> place_order()
    3. Track profits & expenses  -> financial_summary()
    4. Suggest recipes & learn   -> suggest_recipes_in_stock() + learn_preference()
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from .models import (
    Customer, CustomerPreference, Expense, Fish, Order, OrderItem, Recipe,
)


# ---------------------------------------------------------------------------
# Custom exceptions make failures explicit and easy to handle in the UI/API.
# ---------------------------------------------------------------------------
class OutOfStockError(Exception):
    """Raised when an order needs more fish than is currently in inventory."""


# ---------------------------------------------------------------------------
# 1. Inventory management
# ---------------------------------------------------------------------------
def restock_fish(fish: Fish, kilograms: Decimal) -> Fish:
    """Add stock for a single fish type and save it. Returns the updated row."""
    if kilograms <= 0:
        raise ValueError("Restock amount must be positive.")
    fish.quantity_kg += Decimal(kilograms)
    fish.freshness = Fish.Freshness.FRESH  # a fresh delivery resets freshness
    fish.save(update_fields=["quantity_kg", "freshness"])
    return fish


def low_stock_report(threshold_kg: Decimal = Decimal("5")) -> list[Fish]:
    """Return every fish below the reorder threshold (a classic ops report)."""
    return list(Fish.objects.filter(quantity_kg__lt=threshold_kg).order_by("quantity_kg"))


# ---------------------------------------------------------------------------
# 4a. Recipe suggestions  (data structures on display: sets + list comprehension)
# ---------------------------------------------------------------------------
def suggest_recipes_in_stock() -> list[Recipe]:
    """Return recipes that can be cooked *right now* with the fish on hand.

    `Recipe.can_be_made()` checks every ingredient line against current stock.
    We use a list comprehension here because it reads like its intent:
    'the recipes, for each recipe in the menu, that can be made'.
    """
    return [recipe for recipe in Recipe.objects.all() if recipe.can_be_made()]


def recommend_for_customer(customer: Customer, limit: int = 3) -> list[Recipe]:
    """Personalised suggestions = in-stock recipes ranked by learned taste.

    Demonstrates combining two data structures: a dict of preference scores
    keyed by category, used to sort the list of available recipes.
    """
    # Build a {category: score} lookup -> O(1) access while sorting.
    scores = {
        pref.category: pref.score
        for pref in customer.preferences.all()
    }
    available = suggest_recipes_in_stock()
    available.sort(key=lambda r: scores.get(r.category, 0.0), reverse=True)
    return available[:limit]


# ---------------------------------------------------------------------------
# 4b. Preference learning
# ---------------------------------------------------------------------------
def learn_preference(customer: Customer, category: str, weight: float = 1.0) -> None:
    """Nudge a customer's taste score for a category upwards.

    get_or_create() is an idempotent upsert: it returns the existing row or
    makes a new one, so we never create duplicates.
    """
    pref, _created = CustomerPreference.objects.get_or_create(
        customer=customer, category=category, defaults={"score": 0.0},
    )
    pref.score += weight
    pref.save(update_fields=["score", "updated_at"])


# ---------------------------------------------------------------------------
# 2. Order handling  (wrapped in a DB transaction so it is all-or-nothing)
# ---------------------------------------------------------------------------
@dataclass
class OrderLine:
    """A lightweight request object: 'this many of this recipe'."""
    recipe: Recipe
    quantity: int = 1


@transaction.atomic
def place_order(customer: Customer, lines: list[OrderLine]) -> Order:
    """Create an order, deduct fish from inventory, and learn preferences.

    The @transaction.atomic decorator guarantees ACID behaviour: if any step
    fails (e.g. not enough fish), every change in this function is rolled back,
    so inventory can never end up in a half-updated state.
    """
    # --- Step 1: verify stock before changing anything -------------------
    # Aggregate how much of each fish the whole order needs.
    needed: dict[int, Decimal] = {}
    for line in lines:
        for ing in line.recipe.recipe_ingredients.select_related("fish"):
            needed[ing.fish_id] = needed.get(ing.fish_id, Decimal("0")) + (
                ing.quantity_kg * line.quantity
            )
    for fish_id, kg in needed.items():
        fish = Fish.objects.select_for_update().get(pk=fish_id)
        if fish.quantity_kg < kg:
            raise OutOfStockError(
                f"Not enough {fish.name}: need {kg} kg, have {fish.quantity_kg} kg."
            )

    # --- Step 2: create the order and its line items ---------------------
    order = Order.objects.create(customer=customer, status=Order.Status.PREPARING)
    for line in lines:
        OrderItem.objects.create(
            order=order,
            recipe=line.recipe,
            quantity=line.quantity,
            # Snapshot the *current* (possibly marked-down) price now, so later
            # freshness or menu changes never rewrite what the customer paid.
            unit_price=line.recipe.current_price,
        )
        # Learn the customer's taste from what they bought.
        learn_preference(customer, line.recipe.category, weight=float(line.quantity))

    # --- Step 3: deduct the fish from inventory --------------------------
    for fish_id, kg in needed.items():
        fish = Fish.objects.get(pk=fish_id)
        fish.quantity_kg -= kg
        fish.save(update_fields=["quantity_kg"])

    return order


# ---------------------------------------------------------------------------
# 2b. Online ordering — the customer-facing cart + Stripe checkout flow.
# A web order is created *unpaid* at checkout, then finalised once payment
# succeeds. We deduct inventory at payment time (not before) so an abandoned
# cart never silently eats Pingu's stock.
# ---------------------------------------------------------------------------
def get_or_create_customer(name: str, species: str = "", email: str = "") -> Customer:
    """Find a returning customer by (case-insensitive) name/email, else create.

    Reusing the same Customer row across visits is what lets the preference
    engine actually *learn* a regular's taste over time.
    """
    name = name.strip()
    email = email.strip()
    qs = Customer.objects.all()
    match = None
    if email:
        match = qs.filter(email__iexact=email).first()
    if match is None:
        match = qs.filter(name__iexact=name).first()
    if match:
        # Backfill any details we didn't have before.
        changed = []
        if species and not match.species:
            match.species = species; changed.append("species")
        if email and not match.email:
            match.email = email; changed.append("email")
        if changed:
            match.save(update_fields=changed)
        return match
    return Customer.objects.create(name=name or "Guest", species=species, email=email)


def create_pending_online_order(customer: Customer, lines: list[OrderLine]) -> Order:
    """Record a website order as PENDING + unpaid (no inventory change yet)."""
    order = Order.objects.create(
        customer=customer,
        status=Order.Status.PENDING,
        is_online=True,
        is_paid=False,
        seen_by_owner=True,  # stays hidden from the bell until it's actually paid
    )
    for line in lines:
        OrderItem.objects.create(
            order=order,
            recipe=line.recipe,
            quantity=line.quantity,
            unit_price=line.recipe.current_price,  # lock in the marked-down price
        )
    return order


@transaction.atomic
def finalize_paid_order(order: Order) -> Order:
    """Mark a web order paid: deduct inventory, learn taste, ping the dashboard.

    Idempotent — calling it twice (e.g. a refreshed success page) is a no-op.
    Raises OutOfStockError if the fish sold out between checkout and payment.
    """
    if order.is_paid:
        return order

    # Aggregate fish needed across the order's line items.
    needed: dict[int, Decimal] = {}
    for item in order.items.select_related("recipe"):
        for ing in item.recipe.recipe_ingredients.select_related("fish"):
            needed[ing.fish_id] = needed.get(ing.fish_id, Decimal("0")) + (
                ing.quantity_kg * item.quantity
            )
    for fish_id, kg in needed.items():
        fish = Fish.objects.select_for_update().get(pk=fish_id)
        if fish.quantity_kg < kg:
            raise OutOfStockError(
                f"Sold out of {fish.name} before payment cleared."
            )

    for fish_id, kg in needed.items():
        fish = Fish.objects.get(pk=fish_id)
        fish.quantity_kg -= kg
        fish.save(update_fields=["quantity_kg"])

    for item in order.items.all():
        learn_preference(order.customer, item.recipe.category, weight=float(item.quantity))

    order.is_paid = True
    order.paid_at = timezone.now()
    order.seen_by_owner = False  # <- this is what lights up the dashboard bell
    order.status = Order.Status.PREPARING
    order.save(update_fields=["is_paid", "paid_at", "seen_by_owner", "status"])
    return order


def new_order_notifications():
    """Paid online orders Pingu hasn't acknowledged yet (newest first)."""
    return (
        Order.objects.filter(is_online=True, is_paid=True, seen_by_owner=False)
        .select_related("customer")
        .prefetch_related("items__recipe")
        .order_by("-paid_at")
    )


def mark_orders_seen() -> int:
    """Acknowledge every new online order; returns how many were cleared."""
    return Order.objects.filter(
        is_online=True, is_paid=True, seen_by_owner=False
    ).update(seen_by_owner=True)


# ---------------------------------------------------------------------------
# 3. Profit & expense tracking
# ---------------------------------------------------------------------------
@dataclass
class FinancialSummary:
    """A typed result object -> self-documenting and easy to render/return."""
    revenue: Decimal
    expenses: Decimal

    @property
    def profit(self) -> Decimal:
        return self.revenue - self.expenses

    @property
    def margin_pct(self) -> float:
        if self.revenue == 0:
            return 0.0
        return float(self.profit / self.revenue * 100)


def financial_summary() -> FinancialSummary:
    """Compute total revenue (from served/preparing orders) minus expenses.

    Revenue is summed in Python from line items; expenses use a database-level
    SUM aggregate -- showing both approaches to the stakeholder.
    """
    revenue = Decimal("0")
    # Count a sale only when it's real money: never cancelled, and — for web
    # orders — actually paid. An abandoned online cart contributes nothing.
    served = (
        Order.objects.exclude(status=Order.Status.CANCELLED)
        .filter(Q(is_online=False) | Q(is_paid=True))
        .prefetch_related("items")
    )
    for order in served:
        revenue += order.total

    expenses = Expense.objects.aggregate(total=Sum("amount"))["total"] or Decimal("0")
    return FinancialSummary(revenue=revenue, expenses=Decimal(expenses))
