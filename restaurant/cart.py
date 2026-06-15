"""
A tiny session-backed shopping cart.

The cart lives entirely in the visitor's session (``request.session["cart"]``)
as a plain ``{recipe_id: quantity}`` dict — no database row until the customer
actually checks out. That keeps anonymous browsing cheap and means an abandoned
cart leaves nothing behind to clean up.

All pricing reads from ``Recipe.current_price`` so the freshness markdown is
always reflected live in the cart totals.
"""
from __future__ import annotations

from decimal import Decimal

from .models import Recipe
from . import services

CART_SESSION_KEY = "cart"


def _get_raw(session) -> dict:
    return session.get(CART_SESSION_KEY, {})


def _save(session, cart: dict) -> None:
    session[CART_SESSION_KEY] = cart
    session.modified = True


def add(session, recipe_id: int, quantity: int = 1) -> None:
    """Add ``quantity`` of a recipe to the cart (stacking onto any existing)."""
    cart = _get_raw(session)
    key = str(recipe_id)
    cart[key] = max(1, cart.get(key, 0) + quantity)
    _save(session, cart)


def set_quantity(session, recipe_id: int, quantity: int) -> None:
    """Set an exact quantity; a quantity of 0 (or less) removes the line."""
    cart = _get_raw(session)
    key = str(recipe_id)
    if quantity <= 0:
        cart.pop(key, None)
    else:
        cart[key] = quantity
    _save(session, cart)


def remove(session, recipe_id: int) -> None:
    cart = _get_raw(session)
    if cart.pop(str(recipe_id), None) is not None:
        _save(session, cart)


def clear(session) -> None:
    _save(session, {})


def count(session) -> int:
    """Total number of items in the cart (sum of quantities) — for the badge."""
    return sum(_get_raw(session).values())


def detailed(session) -> list[dict]:
    """Resolve the cart into rich rows for templates and checkout.

    Each row: {recipe, quantity, unit_price, line_total}. Silently drops any
    recipe that has since been deleted so a stale session can't 500 the page.
    """
    cart = _get_raw(session)
    if not cart:
        return []
    recipes = {r.pk: r for r in Recipe.objects.filter(pk__in=[int(k) for k in cart])}
    rows = []
    for key, qty in cart.items():
        recipe = recipes.get(int(key))
        if recipe is None:
            continue
        unit = recipe.current_price
        rows.append({
            "recipe": recipe,
            "quantity": qty,
            "unit_price": unit,
            "line_total": (unit * qty),
        })
    return rows


def total(session) -> Decimal:
    return sum((row["line_total"] for row in detailed(session)), start=Decimal("0"))


def to_order_lines(session) -> list[services.OrderLine]:
    """Convert the cart into the OrderLine objects the services layer expects."""
    return [
        services.OrderLine(recipe=row["recipe"], quantity=row["quantity"])
        for row in detailed(session)
    ]
