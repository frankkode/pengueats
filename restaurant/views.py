"""
View functions for PenguEats.

There are two audiences, kept deliberately separate:

* The **public website** (home, recipes, recipe detail, about, blog) — what a
  customer animal visiting PenguEats sees. It never exposes owner financials.
* **Pingu's owner dashboard** (`dashboard`) — a private management console that
  surfaces the five operational functions from the brief: inventory, customer
  orders, profit & expenses, recipe suggestions and learned customer
  preferences.

Each view stays deliberately thin: it gathers data (usually by delegating to
`services.py`) and hands it to a template.
"""
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import F, ProtectedError, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from . import cart, payments, services
from .forms import RecipeForm
from .models import (
    Chef, Customer, CustomerPreference, Expense, Fish, Order, Recipe,
    RecipeIngredient,
)


def home(request):
    """Landing page: hero, feature strip, featured recipe and live suggestions."""
    featured = Recipe.objects.filter(is_featured=True).first()
    context = {
        "featured": featured,
        "popular": Recipe.objects.order_by("-views")[:3],
        # 'In stock right now' uses the recipe-suggestion service.
        "in_stock": services.suggest_recipes_in_stock()[:3],
        "active": "home",
    }
    return render(request, "restaurant/home.html", context)


def recipe_list(request):
    """Recipes page with category filtering (the 'What to Cook?' chips) and
    a free-text search (the navbar search box submits its query here as ?q=)."""
    category = request.GET.get("category", "")
    query = request.GET.get("q", "").strip()
    recipes = Recipe.objects.all()
    if category:
        recipes = recipes.filter(category=category)
    if query:
        # Match the dish name or its description, case-insensitively.
        recipes = recipes.filter(
            Q(name__icontains=query) | Q(description__icontains=query)
        )
    context = {
        "recipes": recipes,
        "categories": Recipe.Category.choices,
        "selected_category": category,
        "query": query,
        "active": "recipes",
    }
    return render(request, "restaurant/recipes.html", context)


def recipe_detail(request, slug):
    """Single recipe page (ingredients, nutrition-style facts, steps)."""
    recipe = get_object_or_404(Recipe, slug=slug)
    # Count a view. F() does the increment in the database to avoid race
    # conditions between simultaneous visitors.
    Recipe.objects.filter(pk=recipe.pk).update(views=F("views") + 1)
    context = {
        "recipe": recipe,
        "can_make": recipe.can_be_made(),
        "related": Recipe.objects.filter(category=recipe.category)
        .exclude(pk=recipe.pk)[:3],
        "active": "recipes",
    }
    return render(request, "restaurant/recipe_detail.html", context)


def menu(request):
    """A printable, downloadable price menu of every dish, grouped by category.

    This is the public, customer-facing price list (only owner financials like
    profit/expenses stay private — listed prices are meant for customers). It is
    styled for print so a visitor can hit "Save as PDF" and take the menu away.
    Freshness markdowns are reflected, so today's deals show up on the printout.
    """
    groups = []
    for value, label in Recipe.Category.choices:
        items = list(
            Recipe.objects.filter(category=value).order_by("name")
        )
        if items:
            groups.append({"label": label, "items": items})
    context = {
        "groups": groups,
        "active": "menu",
    }
    return render(request, "restaurant/menu.html", context)


def about(request):
    """About page: story, (non-financial) stats and the chef team."""
    context = {
        "chefs": Chef.objects.all(),
        "recipe_count": Recipe.objects.count(),
        "fish_count": Fish.objects.count(),
        "chef_count": Chef.objects.count(),
        "active": "about",
    }
    return render(request, "restaurant/about.html", context)


def blog(request):
    """A lightweight 'Culinary Journal' page reusing recipes as articles."""
    context = {
        "articles": Recipe.objects.order_by("-created_at")[:6],
        "active": "blog",
    }
    return render(request, "restaurant/blog.html", context)


def contact(request):
    """Public 'Get in Touch' page with a simple message form.

    For this course project the form doesn't send real email — on a valid POST
    it just thanks the visitor and re-renders the page, so the flow is complete
    and demonstrable without an external mail service.
    """
    sent = False
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        email = request.POST.get("email", "").strip()
        message = request.POST.get("message", "").strip()
        if name and email and message:
            sent = True
    context = {"sent": sent, "active": "contact"}
    return render(request, "restaurant/contact.html", context)


# ---------------------------------------------------------------------------
# Customer shopping cart + checkout (the public "order online" experience).
# Animals browse the menu, drop dishes in a session cart, then pay with Stripe.
# A successful payment finalises the order — deducting fish from inventory and
# pinging Pingu's dashboard as a new-order notification.
# ---------------------------------------------------------------------------
@require_POST
def add_to_cart(request, pk):
    """Add one serving of a recipe to the session cart."""
    recipe = get_object_or_404(Recipe, pk=pk)
    try:
        qty = max(1, int(request.POST.get("quantity", "1")))
    except (ValueError, TypeError):
        qty = 1
    cart.add(request.session, recipe.pk, qty)
    messages.success(request, f"Added {qty} × {recipe.name} to your basket.")
    # Return where the customer came from, so browsing isn't interrupted.
    return redirect(request.POST.get("next") or "restaurant:cart")


def cart_view(request):
    """Show the basket with live (marked-down) prices and a checkout button."""
    context = {
        "rows": cart.detailed(request.session),
        "cart_total": cart.total(request.session),
        "active": "cart",
    }
    return render(request, "restaurant/cart.html", context)


@require_POST
def update_cart(request, pk):
    """Change a line's quantity (0 removes it)."""
    try:
        qty = int(request.POST.get("quantity", "0"))
    except (ValueError, TypeError):
        qty = 0
    cart.set_quantity(request.session, pk, qty)
    return redirect("restaurant:cart")


@require_POST
def remove_from_cart(request, pk):
    cart.remove(request.session, pk)
    return redirect("restaurant:cart")


def checkout(request):
    """Collect the customer's details and hand off to Stripe Checkout.

    GET shows the order summary + a details form. POST creates a *pending*
    online order and redirects to Stripe (or, with no keys configured, to a
    clearly-labelled simulated payment) to take the money.
    """
    rows = cart.detailed(request.session)
    if not rows:
        messages.error(request, "Your basket is empty — add a dish first.")
        return redirect("restaurant:recipes")

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        species = request.POST.get("species", "").strip()
        email = request.POST.get("email", "").strip()
        if not name:
            messages.error(request, "Please tell us your name so Pingu knows who's ordering.")
        else:
            customer = services.get_or_create_customer(name, species, email)
            order = services.create_pending_online_order(
                customer, cart.to_order_lines(request.session)
            )
            # Remember which order this checkout is for (used by simulated pay).
            request.session["pending_order_id"] = order.pk
            if payments.is_enabled():
                try:
                    url = payments.create_checkout_session(request, order, rows)
                    return redirect(url)
                except Exception as exc:  # Stripe/network error — fail gracefully.
                    messages.error(request, f"Couldn't reach the payment page: {exc}")
                    return redirect("restaurant:cart")
            # No Stripe keys: jump to the simulated payment screen.
            return redirect("restaurant:checkout_simulate")

    context = {
        "rows": rows,
        "cart_total": cart.total(request.session),
        "stripe_enabled": payments.is_enabled(),
        "active": "cart",
    }
    return render(request, "restaurant/checkout.html", context)


def checkout_simulate(request):
    """A stand-in 'pay' screen used only when Stripe keys aren't configured.

    Clearly labelled as a demo so nobody mistakes it for a real charge; the
    Pay button posts to ``checkout_success`` to finalise the pending order.
    """
    order_id = request.session.get("pending_order_id")
    if not order_id:
        return redirect("restaurant:cart")
    order = get_object_or_404(Order, pk=order_id)
    return render(request, "restaurant/checkout_simulate.html", {
        "order": order, "active": "cart",
    })


def checkout_success(request):
    """Finalise a paid order: deduct inventory, learn taste, clear the cart.

    Reached two ways:
      * Stripe redirect with ``?session_id=...`` (real test-mode payment), or
      * the simulated pay button POSTing the pending order id.
    Either way we only finalise an order we can confirm belongs to this flow.
    """
    order = None
    session_id = request.GET.get("session_id")
    if session_id:
        oid = payments.paid_order_id(session_id)
        if oid:
            order = Order.objects.filter(pk=oid).first()
    else:
        # Simulated path: trust the pending id we stashed at checkout.
        oid = request.session.get("pending_order_id")
        if oid:
            order = Order.objects.filter(pk=oid, is_online=True).first()

    if order is None:
        messages.error(request, "We couldn't confirm that payment. Nothing was charged.")
        return redirect("restaurant:cart")

    try:
        services.finalize_paid_order(order)
    except services.OutOfStockError as exc:
        order.status = Order.Status.CANCELLED
        order.save(update_fields=["status"])
        messages.error(request, f"Sorry — {exc} Your order was cancelled, no fish was taken.")
        return redirect("restaurant:cart")

    cart.clear(request.session)
    request.session.pop("pending_order_id", None)
    return render(request, "restaurant/order_confirmation.html", {
        "order": order, "active": "cart",
    })


def checkout_cancel(request):
    """Customer backed out of Stripe — keep the cart, drop the pending order."""
    oid = request.session.pop("pending_order_id", None)
    if oid:
        Order.objects.filter(pk=oid, is_online=True, is_paid=False).delete()
    messages.info(request, "Payment cancelled — your basket is still here whenever you're ready.")
    return redirect("restaurant:cart")


# ---------------------------------------------------------------------------
# Pingu's owner dashboard — the private management console.
# This single screen is where the five brief functions come together. It is
# what Pingu (the owner), not the customer, uses to run PenguEats.
# ---------------------------------------------------------------------------
def _dashboard_context():
    """Gather everything the dashboard template needs.

    Extracted into a helper so both the ``dashboard`` view and the recipe-form
    error path (which must re-render the same screen) share one source of truth.
    """
    return {
        # 1. Inventory — ordered so the lowest stock floats to the top.
        "fish": Fish.objects.select_related("supplier").order_by("quantity_kg"),
        "low_stock": services.low_stock_report(),
        # 2. Recent customer orders (prefetch items to avoid N+1 queries).
        "recent_orders": (
            Order.objects.select_related("customer")
            .prefetch_related("items__recipe")
            .order_by("-created_at")[:8]
        ),
        # 3. Profit & expenses — straight from the financial-summary service.
        "finance": services.financial_summary(),
        # 4. Recipes Pingu can make right now from what's in stock.
        "suggestions": services.suggest_recipes_in_stock(),
        # 5. Learned customer preferences, strongest taste first.
        "preferences": (
            CustomerPreference.objects.select_related("customer")
            .order_by("-score")[:8]
        ),
        "customer_count": Customer.objects.count(),
        "order_count": Order.objects.count(),
        # New paid online orders awaiting Pingu's acknowledgement (the bell).
        "new_orders": services.new_order_notifications(),
        # Data used to populate the action forms (restock / order / expense).
        "all_customers": Customer.objects.order_by("name"),
        "all_recipes": Recipe.objects.order_by("name"),
        "expense_categories": Expense.Category.choices,
        "active": "dashboard",
    }


@login_required
def dashboard(request):
    """Management console covering all five operational functions.

    Protected by ``@login_required``: PenguEats' financials and controls are
    owner-only, so an unauthenticated visitor is redirected to the login page
    (``LOGIN_URL`` in settings) and returned here once signed in.

    1. Inventory   -> every fish with quantity + freshness, low stock flagged
    2. Orders      -> the most recent customer orders and their totals
    3. Finance     -> revenue, expenses and profit (owner-only)
    4. Suggestions -> recipes that can be cooked from current stock
    5. Preferences -> what each customer has been learning to love
    """
    context = _dashboard_context()
    # Blank form for the "Add a Recipe" panel (function: manage the menu).
    context["recipe_form"] = RecipeForm()
    context["ingredient_rows"] = _ingredient_rows()
    return render(request, "restaurant/dashboard.html", context)


# ---------------------------------------------------------------------------
# Owner actions — the dashboard isn't just a display, Pingu acts on it.
# Each handler is POST-only, delegates the real work to services.py, reports
# the outcome via the messages framework, then redirects back to the
# dashboard (the Post/Redirect/Get pattern, so a refresh won't re-submit).
# ---------------------------------------------------------------------------
def _get_or_message(model, pk, request, label):
    """Look a row up by pk; on a missing/blank id, flash an error and return None.

    Keeps the action views from 500-ing on a malformed POST — defensive but
    still thin, because the heavy lifting stays in services.py.
    """
    if not pk:
        messages.error(request, f"No {label} selected.")
        return None
    try:
        return model.objects.get(pk=pk)
    except (model.DoesNotExist, ValueError, TypeError):
        messages.error(request, f"That {label} no longer exists.")
        return None


@login_required
@require_POST
def restock_fish_view(request):
    """Add kilograms to a fish's stock (function 1: manage inventory)."""
    fish = _get_or_message(Fish, request.POST.get("fish_id"), request, "fish")
    if fish is None:
        return redirect("restaurant:dashboard")
    try:
        kg = Decimal(request.POST.get("kilograms", "0"))
        services.restock_fish(fish, kg)
        messages.success(request, f"Restocked {kg} kg of {fish.name}.")
    except (InvalidOperation, ValueError) as exc:
        messages.error(request, f"Could not restock: {exc}")
    return redirect("restaurant:dashboard")


@login_required
@require_POST
def update_freshness_view(request):
    """Change a fish's freshness label (function 1: manage inventory)."""
    fish = _get_or_message(Fish, request.POST.get("fish_id"), request, "fish")
    if fish is None:
        return redirect("restaurant:dashboard")
    freshness = request.POST.get("freshness")
    if freshness in Fish.Freshness.values:
        fish.freshness = freshness
        fish.save(update_fields=["freshness"])
        messages.success(request, f"{fish.name} marked '{fish.get_freshness_display()}'.")
    else:
        messages.error(request, "Unknown freshness value.")
    return redirect("restaurant:dashboard")


@login_required
@require_POST
def place_order_view(request):
    """Take a customer order (functions 2 + 5: orders, learn preferences).

    Delegates to services.place_order, which atomically checks stock, records
    the sale, deducts inventory and nudges the customer's taste preferences.
    """
    customer = _get_or_message(Customer, request.POST.get("customer_id"), request, "customer")
    if customer is None:
        return redirect("restaurant:dashboard")
    # The form sends one or more recipe ids plus a matching quantity each.
    recipe_ids = request.POST.getlist("recipe_id")
    quantities = request.POST.getlist("quantity")
    lines = []
    for rid, qty in zip(recipe_ids, quantities):
        if not rid:
            continue
        recipe = get_object_or_404(Recipe, pk=rid)
        try:
            n = int(qty or 1)
        except ValueError:
            n = 1
        if n > 0:
            lines.append(services.OrderLine(recipe=recipe, quantity=n))

    if not lines:
        messages.error(request, "Pick at least one dish to order.")
        return redirect("restaurant:dashboard")

    try:
        order = services.place_order(customer, lines)
        messages.success(
            request,
            f"Order #{order.pk} for {customer.name} placed (${order.total}). "
            "Inventory deducted and taste preferences updated.",
        )
    except services.OutOfStockError as exc:
        # Whole order rolled back — nothing was half-applied.
        messages.error(request, f"Order rejected: {exc}")
    return redirect("restaurant:dashboard")


@login_required
@require_POST
def mark_orders_seen_view(request):
    """Acknowledge all new online-order notifications (clears the bell badge)."""
    n = services.mark_orders_seen()
    if n:
        messages.success(request, f"Marked {n} new order{'s' if n != 1 else ''} as seen.")
    return redirect("restaurant:dashboard")


@login_required
@require_POST
def add_expense_view(request):
    """Log money going out, e.g. ice-block rent or supplier costs (function 3)."""
    category = request.POST.get("category")
    try:
        amount = Decimal(request.POST.get("amount", "0"))
        if amount <= 0:
            raise ValueError("amount must be positive")
        if category not in Expense.Category.values:
            raise ValueError("unknown category")
        Expense.objects.create(
            category=category,
            amount=amount,
            description=request.POST.get("description", "").strip(),
        )
        messages.success(request, f"Logged ${amount} expense.")
    except (InvalidOperation, ValueError) as exc:
        messages.error(request, f"Could not log expense: {exc}")
    return redirect("restaurant:dashboard")


def _parse_ingredients(request):
    """Read the per-fish kilogram inputs (``ing_<fish_pk>``) from the POST.

    Returns ``{fish_pk: Decimal_kg}`` for every fish given a positive amount.
    This is what links a recipe to the inventory it consumes — without it an
    order can't know which fish to deduct.
    """
    chosen = {}
    for fish in Fish.objects.all():
        raw = (request.POST.get(f"ing_{fish.pk}", "") or "").strip()
        if not raw:
            continue
        try:
            kg = Decimal(raw)
        except InvalidOperation:
            continue
        if kg > 0:
            chosen[fish.pk] = kg
    return chosen


def _sync_ingredients(recipe, chosen):
    """Make ``recipe``'s ingredient rows match ``chosen`` ({fish_pk: kg})."""
    recipe.recipe_ingredients.exclude(fish_id__in=chosen).delete()
    for fish_pk, kg in chosen.items():
        RecipeIngredient.objects.update_or_create(
            recipe=recipe, fish_id=fish_pk, defaults={"quantity_kg": kg},
        )


def _ingredient_rows(recipe=None):
    """Build [{fish, kg}] for the form, pre-filling current amounts when editing."""
    current = {}
    if recipe is not None:
        current = {
            ri.fish_id: ri.quantity_kg
            for ri in recipe.recipe_ingredients.all()
        }
    return [
        {"fish": f, "kg": current.get(f.pk, "")}
        for f in Fish.objects.order_by("name")
    ]


@login_required
@require_POST
def create_recipe_view(request):
    """Add a new dish to the menu, linked to the fish it uses.

    Uses ``RecipeForm`` (a ModelForm) for the recipe fields, plus the per-fish
    kilogram inputs so the new dish is connected to inventory. At least one
    ingredient is required — otherwise an order of this recipe could never
    deduct any fish (the bug this guards against).
    """
    # request.FILES carries the uploaded photo (the form is multipart/form-data).
    form = RecipeForm(request.POST, request.FILES)
    chosen = _parse_ingredients(request)
    if form.is_valid() and chosen:
        recipe = form.save()
        _sync_ingredients(recipe, chosen)
        messages.success(
            request,
            f"Added “{recipe.name}” using {len(chosen)} fish — orders will now "
            "deduct it from inventory.",
        )
        return redirect("restaurant:dashboard")

    # Re-render the dashboard with the invalid form bound, so errors show.
    if not chosen:
        messages.error(request, "Pick at least one fish this recipe uses (set a kg amount).")
    else:
        messages.error(request, "Could not add recipe — please check the fields below.")
    context = _dashboard_context()
    context["recipe_form"] = form
    context["ingredient_rows"] = _ingredient_rows()
    return render(request, "restaurant/dashboard.html", context)


@login_required
def edit_recipe_view(request, pk):
    """Update a recipe — its text, photo *and* the fish it consumes (CRUD: Update).

    A GET shows the recipe's current details (and current ingredient amounts) in
    a pre-filled form; a POST saves the changes. Editing the ingredient kg values
    keeps the recipe correctly connected to inventory and the suggestion engine.
    """
    recipe = get_object_or_404(Recipe, pk=pk)
    if request.method == "POST":
        form = RecipeForm(request.POST, request.FILES, instance=recipe)
        chosen = _parse_ingredients(request)
        if form.is_valid() and chosen:
            form.save()
            _sync_ingredients(recipe, chosen)
            messages.success(request, f"Updated “{recipe.name}”.")
            return redirect("restaurant:dashboard")
        if not chosen:
            messages.error(request, "A recipe needs at least one fish (set a kg amount).")
        else:
            messages.error(request, "Could not save — please check the fields below.")
        rows = _ingredient_rows()  # reflect what's currently in the boxes
    else:
        form = RecipeForm(instance=recipe)
        rows = _ingredient_rows(recipe)
    return render(
        request, "restaurant/recipe_edit.html",
        {"form": form, "recipe": recipe, "ingredient_rows": rows},
    )


@login_required
@require_POST
def delete_recipe_view(request, pk):
    """Remove a recipe from the menu (menu CRUD: Delete).

    Recipes that have already been ordered are protected at the database level
    (``OrderItem.recipe`` uses ``on_delete=PROTECT``) so deleting one would
    rewrite sales history. We catch that and explain it rather than 500-ing.
    """
    recipe = get_object_or_404(Recipe, pk=pk)
    name = recipe.name
    try:
        recipe.delete()
        messages.success(request, f"Deleted “{name}” from the menu.")
    except ProtectedError:
        messages.error(
            request,
            f"Can't delete “{name}” — it appears on past orders. "
            "Remove it from the menu by un-featuring it instead.",
        )
    return redirect("restaurant:dashboard")
