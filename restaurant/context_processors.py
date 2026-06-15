"""
Template context processors — values injected into *every* template render.

``cart_summary`` exposes the live cart item count so the navbar badge can show
how many dishes the visitor has lined up, on whatever page they're on.
"""
from . import cart


def cart_summary(request):
    return {"cart_count": cart.count(request.session)}
