"""
Unit tests for the PenguEats business logic.

These tests document the rules of the restaurant and guard against regressions.
Run them with:  python manage.py test
A passing test suite is strong evidence to show the stakeholder/examiner.
"""
from decimal import Decimal

from django.test import TestCase

from . import services
from .models import (
    Customer, Expense, Fish, Order, Recipe, RecipeIngredient,
)


class ServiceLogicTests(TestCase):
    def setUp(self):
        """Create a tiny, known world before each test."""
        self.salmon = Fish.objects.create(
            name="Salmon", quantity_kg=Decimal("10"), cost_per_kg=Decimal("8"),
        )
        self.krill = Fish.objects.create(
            name="Krill", quantity_kg=Decimal("1"), cost_per_kg=Decimal("3"),
        )
        self.sushi = Recipe.objects.create(
            name="Salmon Sushi", slug="salmon-sushi",
            category=Recipe.Category.MAIN, price=Decimal("12"),
        )
        RecipeIngredient.objects.create(
            recipe=self.sushi, fish=self.salmon, quantity_kg=Decimal("2"),
        )
        self.feast = Recipe.objects.create(
            name="Krill Feast", slug="krill-feast",
            category=Recipe.Category.MAIN, price=Decimal("9"),
        )
        RecipeIngredient.objects.create(
            recipe=self.feast, fish=self.krill, quantity_kg=Decimal("5"),
        )
        self.pingu = Customer.objects.create(name="Pingu", species="penguin")

    def test_suggestions_only_include_in_stock_recipes(self):
        """Sushi is makeable (10kg salmon); the krill feast is not (needs 5, have 1)."""
        suggestions = services.suggest_recipes_in_stock()
        self.assertIn(self.sushi, suggestions)
        self.assertNotIn(self.feast, suggestions)

    def test_place_order_deducts_inventory(self):
        """Ordering 1 sushi (2kg salmon) leaves 8kg in stock."""
        services.place_order(self.pingu, [services.OrderLine(self.sushi, 1)])
        self.salmon.refresh_from_db()
        self.assertEqual(self.salmon.quantity_kg, Decimal("8"))

    def test_place_order_records_revenue_and_learns_taste(self):
        services.place_order(self.pingu, [services.OrderLine(self.sushi, 2)])
        # Revenue = 2 * 12 = 24
        summary = services.financial_summary()
        self.assertEqual(summary.revenue, Decimal("24"))
        # Customer should now have a MAIN preference score of 2.
        pref = self.pingu.preferences.get(category=Recipe.Category.MAIN)
        self.assertEqual(pref.score, 2.0)

    def test_order_beyond_stock_is_rejected_and_rolled_back(self):
        """An impossible order raises and leaves inventory untouched (atomicity)."""
        with self.assertRaises(services.OutOfStockError):
            services.place_order(self.pingu, [services.OrderLine(self.feast, 1)])
        self.krill.refresh_from_db()
        self.assertEqual(self.krill.quantity_kg, Decimal("1"))  # unchanged
        self.assertEqual(Order.objects.count(), 0)              # nothing created

    def test_financial_summary_subtracts_expenses(self):
        services.place_order(self.pingu, [services.OrderLine(self.sushi, 1)])  # +12
        Expense.objects.create(category=Expense.Category.ICE_RENT, amount=Decimal("5"))
        summary = services.financial_summary()
        self.assertEqual(summary.profit, Decimal("7"))

    # --- Freshness-based dynamic pricing ------------------------------------
    def test_freshness_markdown_reduces_price(self):
        """A dish is marked down by its least-fresh fish: Good -15%, Use soon -30%."""
        self.salmon.freshness = Fish.Freshness.FRESH
        self.salmon.save()
        self.assertFalse(self.sushi.is_discounted)
        self.assertEqual(self.sushi.current_price, Decimal("12.00"))

        self.salmon.freshness = Fish.Freshness.GOOD
        self.salmon.save()
        self.assertEqual(self.sushi.discount_pct, 15)
        self.assertEqual(self.sushi.current_price, Decimal("10.20"))  # 12 * 0.85

        self.salmon.freshness = Fish.Freshness.USE_SOON
        self.salmon.save()
        self.assertEqual(self.sushi.discount_pct, 30)
        self.assertEqual(self.sushi.current_price, Decimal("8.40"))   # 12 * 0.70

    # --- Online order lifecycle (cart -> pay -> finalise) -------------------
    def test_online_order_only_counts_and_deducts_once_paid(self):
        """A pending web order is invisible to revenue/inventory until paid."""
        order = services.create_pending_online_order(
            self.pingu, [services.OrderLine(self.sushi, 1)]
        )
        # Before payment: no inventory change, no revenue, not a notification.
        self.salmon.refresh_from_db()
        self.assertEqual(self.salmon.quantity_kg, Decimal("10"))
        self.assertEqual(services.financial_summary().revenue, Decimal("0"))
        self.assertEqual(services.new_order_notifications().count(), 0)

        services.finalize_paid_order(order)

        # After payment: inventory deducted, revenue counted, dashboard pinged.
        self.salmon.refresh_from_db()
        self.assertEqual(self.salmon.quantity_kg, Decimal("8"))
        self.assertEqual(services.financial_summary().revenue, Decimal("12"))
        self.assertEqual(services.new_order_notifications().count(), 1)

        # Acknowledging clears the bell; finalise is idempotent (no double deduct).
        services.finalize_paid_order(order)
        self.salmon.refresh_from_db()
        self.assertEqual(self.salmon.quantity_kg, Decimal("8"))
        self.assertEqual(services.mark_orders_seen(), 1)
        self.assertEqual(services.new_order_notifications().count(), 0)
