"""
Stripe Checkout integration (TEST mode).

Kept in its own module so the views stay thin and the payment provider can be
swapped or mocked without touching request handling.

Flow:
    1. ``create_checkout_session`` turns the order's line items into a Stripe
       hosted Checkout Session and returns its URL. The customer pays on
       Stripe's page with the test card 4242 4242 4242 4242.
    2. Stripe redirects back to our success URL with ``?session_id=...``.
    3. ``paid_order_id`` re-reads that session from Stripe and, if it really
       was paid, hands back the order id stored in the session metadata — so a
       visitor can't fake a success just by visiting the URL.

If ``STRIPE_SECRET_KEY`` is not configured, ``is_enabled()`` is False and the
views fall back to a clearly-labelled simulated payment, so the project still
demos end-to-end without keys.
"""
from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.urls import reverse

try:  # Stripe is optional at import time; only needed when keys are set.
    import stripe
except ImportError:  # pragma: no cover
    stripe = None


def is_enabled() -> bool:
    return bool(stripe and settings.STRIPE_SECRET_KEY)


def _client():
    stripe.api_key = settings.STRIPE_SECRET_KEY
    return stripe


def create_checkout_session(request, order, rows) -> str:
    """Create a Stripe Checkout Session for ``order`` and return its URL.

    ``rows`` is the cart's detailed rows ({recipe, quantity, unit_price, ...}).
    """
    s = _client()
    line_items = []
    for row in rows:
        line_items.append({
            "quantity": row["quantity"],
            "price_data": {
                "currency": settings.STRIPE_CURRENCY,
                "unit_amount": int((Decimal(row["unit_price"]) * 100).to_integral_value()),
                "product_data": {"name": row["recipe"].name},
            },
        })
    success = request.build_absolute_uri(reverse("restaurant:checkout_success"))
    cancel = request.build_absolute_uri(reverse("restaurant:checkout_cancel"))
    session = s.checkout.Session.create(
        mode="payment",
        line_items=line_items,
        success_url=success + "?session_id={CHECKOUT_SESSION_ID}",
        cancel_url=cancel,
        metadata={"order_id": str(order.pk)},
        customer_email=(order.customer.email or None),
    )
    order.stripe_session_id = session.id
    order.save(update_fields=["stripe_session_id"])
    return session.url


def paid_order_id(session_id: str):
    """Return the order id for a *paid* Stripe session, else None."""
    if not (session_id and is_enabled()):
        return None
    s = _client()
    session = s.checkout.Session.retrieve(session_id)
    if session.get("payment_status") == "paid":
        return session.get("metadata", {}).get("order_id")
    return None
