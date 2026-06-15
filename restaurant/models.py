"""
Database models for PenguEats.

These classes are the single source of truth for the database schema. Django's
ORM (Object-Relational Mapper) turns each class into a SQL table and each
attribute into a column, so we never write raw SQL. The relationships between
models (ForeignKey, ManyToMany) become the connections in the ER diagram.

Domain story (so the field names make sense):
    Pingu the penguin runs a fish restaurant. He buys FISH from SUPPLIERS,
    turns them into RECIPES, sells them to animal CUSTOMERS via ORDERS, pays
    EXPENSES (ice-block rent, supplier bills), and the system LEARNS each
    customer's taste through CustomerPreference rows.
"""
from decimal import Decimal, ROUND_HALF_UP

from django.db import models
from django.core.validators import MinValueValidator
from django.templatetags.static import static
from django.utils import timezone


# Freshness-based "sell it before it turns" markdown. The least-fresh fish a
# recipe uses sets the discount, just like a grocer marking down produce that's
# near its date. FRESH = full price; the riper it gets, the cheaper the dish.
FRESHNESS_DISCOUNT_PCT = {
    "FRESH": 0,
    "GOOD": 15,
    "USE_SOON": 30,
}


# ---------------------------------------------------------------------------
# Reference / lookup tables
# ---------------------------------------------------------------------------
class Supplier(models.Model):
    """A business Pingu buys fish (or ice) from."""

    name = models.CharField(max_length=120)
    contact_email = models.EmailField(blank=True)
    phone = models.CharField(max_length=40, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Chef(models.Model):
    """A chef who authors recipes (matches the 'Recipe by ...' cards in the UI)."""

    name = models.CharField(max_length=120)
    title = models.CharField(max_length=120, default="Head Chef")
    bio = models.TextField(blank=True)
    # Stored as a path/URL string so the seed data can point at AI-generated images.
    photo = models.CharField(max_length=255, blank=True)

    def __str__(self) -> str:
        return self.name


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------
class Fish(models.Model):
    """A type of fish in Pingu's cold-storage inventory.

    Freshness is modelled as a simple text choice for clarity in the demo,
    but we also keep `caught_on` so we *could* compute freshness from age.
    """

    class Freshness(models.TextChoices):
        FRESH = "FRESH", "Fresh"
        GOOD = "GOOD", "Good"
        USE_SOON = "USE_SOON", "Use soon"

    name = models.CharField(max_length=80, unique=True)
    species = models.CharField(max_length=80, blank=True)
    # DecimalField (not FloatField) avoids rounding errors on money/weights.
    quantity_kg = models.DecimalField(
        max_digits=8, decimal_places=2, default=0,
        validators=[MinValueValidator(0)],
        help_text="Kilograms currently in stock.",
    )
    cost_per_kg = models.DecimalField(
        max_digits=8, decimal_places=2, default=0,
        validators=[MinValueValidator(0)],
        help_text="What Pingu pays the supplier per kg.",
    )
    freshness = models.CharField(
        max_length=10, choices=Freshness.choices, default=Freshness.FRESH,
    )
    supplier = models.ForeignKey(
        Supplier, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="fish_items",
    )
    caught_on = models.DateField(default=timezone.now)

    class Meta:
        verbose_name_plural = "Fish"
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.quantity_kg} kg)"

    @property
    def is_low_stock(self) -> bool:
        """Convenience flag the dashboard/admin can highlight."""
        return self.quantity_kg < 5


# ---------------------------------------------------------------------------
# Menu
# ---------------------------------------------------------------------------
class Recipe(models.Model):
    """A dish on the menu. Connected to Fish through RecipeIngredient."""

    class Category(models.TextChoices):
        APPETIZER = "APPETIZER", "Appetizers"
        MAIN = "MAIN", "Main Courses"
        SALAD = "SALAD", "Salads & Sides"
        DESSERT = "DESSERT", "Desserts & Sweets"
        HEALTHY = "HEALTHY", "Healthy Eats"

    class Difficulty(models.TextChoices):
        BEGINNER = "BEGINNER", "Beginner Friendly"
        INTERMEDIATE = "INTERMEDIATE", "Intermediate Level"
        ADVANCED = "ADVANCED", "Advanced"

    name = models.CharField(max_length=140)
    slug = models.SlugField(max_length=160, unique=True)
    summary = models.CharField(max_length=300, blank=True)
    description = models.TextField(blank=True)
    instructions = models.TextField(blank=True, help_text="One step per line.")
    category = models.CharField(
        max_length=12, choices=Category.choices, default=Category.MAIN,
    )
    difficulty = models.CharField(
        max_length=12, choices=Difficulty.choices, default=Difficulty.BEGINNER,
    )
    price = models.DecimalField(
        max_digits=8, decimal_places=2, default=0,
        validators=[MinValueValidator(0)], help_text="Menu price for customers.",
    )
    prep_minutes = models.PositiveIntegerField(default=15)
    cook_minutes = models.PositiveIntegerField(default=10)
    servings = models.PositiveIntegerField(default=2)
    # Two ways a recipe can have a picture:
    #   * `image`  — a path to a bundled static file (used by the seed data).
    #   * `photo`  — a real file the owner uploads from the dashboard. Django's
    #     ImageField needs the Pillow library and stores the file under MEDIA.
    image = models.CharField(max_length=255, blank=True)
    photo = models.ImageField(upload_to="recipes/", blank=True, null=True)
    chef = models.ForeignKey(
        Chef, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="recipes",
    )
    is_featured = models.BooleanField(default=False)
    views = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    # The ManyToMany "through" relationship is what links the menu to inventory.
    ingredients = models.ManyToManyField(
        Fish, through="RecipeIngredient", related_name="recipes",
    )

    class Meta:
        ordering = ["-is_featured", "name"]

    def __str__(self) -> str:
        return self.name

    @property
    def display_image(self) -> str:
        """The URL to show for this recipe, wherever the picture came from.

        An uploaded `photo` wins; otherwise we fall back to the bundled static
        `image` from the seed data. Centralising this here means the templates
        just write ``{{ recipe.display_image }}`` and never worry about which
        storage the picture lives in.
        """
        if self.photo:
            return self.photo.url
        if self.image:
            return static(self.image)
        return static("restaurant/img/hero.jpg")

    @property
    def total_minutes(self) -> int:
        return self.prep_minutes + self.cook_minutes

    # -- Freshness-driven dynamic pricing ---------------------------------
    # A dish is only as fresh as its least-fresh fish, so that worst case is
    # what triggers the markdown. This rewards customers for buying stock that
    # would otherwise have to be thrown away — good for Pingu's bottom line.
    @property
    def freshness_status(self) -> str | None:
        """Return the *least* fresh freshness among this recipe's fish.

        ``None`` when the recipe has no linked fish (so no markdown applies).
        """
        rank = {Fish.Freshness.FRESH: 0, Fish.Freshness.GOOD: 1, Fish.Freshness.USE_SOON: 2}
        worst = None
        worst_rank = -1
        for line in self.recipe_ingredients.select_related("fish"):
            r = rank.get(line.fish.freshness, 0)
            if r > worst_rank:
                worst_rank, worst = r, line.fish.freshness
        return worst

    @property
    def discount_pct(self) -> int:
        """Percent off, decided by the least-fresh ingredient (0 / 15 / 30)."""
        return FRESHNESS_DISCOUNT_PCT.get(self.freshness_status, 0)

    @property
    def is_discounted(self) -> bool:
        return self.discount_pct > 0

    @property
    def current_price(self) -> Decimal:
        """The price a customer actually pays right now, after any markdown."""
        pct = self.discount_pct
        if not pct:
            return self.price
        reduced = self.price * (Decimal(100 - pct) / Decimal(100))
        return reduced.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @property
    def savings(self) -> Decimal:
        """How many dollars the markdown takes off the full price."""
        return (self.price - self.current_price).quantize(Decimal("0.01"))

    @property
    def freshness_deal_label(self) -> str:
        """Short human label for the markdown badge (empty if full price)."""
        if self.freshness_status == Fish.Freshness.USE_SOON:
            return "Catch of the day — 30% off"
        if self.freshness_status == Fish.Freshness.GOOD:
            return "Fresh deal — 15% off"
        return ""

    @property
    def instruction_steps(self) -> list[str]:
        """Split the instructions text into a clean list for the template."""
        return [line.strip() for line in self.instructions.splitlines() if line.strip()]

    def can_be_made(self) -> bool:
        """True only if every required fish is in stock in sufficient quantity.

        This is the rule the recipe-suggestion service relies on.
        """
        for line in self.recipe_ingredients.select_related("fish"):
            if line.fish.quantity_kg < line.quantity_kg:
                return False
        return True


class RecipeIngredient(models.Model):
    """Association row: how much of which Fish a Recipe needs.

    Storing the quantity here (rather than on Fish or Recipe) is the textbook
    way to model a many-to-many relationship that carries extra data.
    """

    recipe = models.ForeignKey(
        Recipe, on_delete=models.CASCADE, related_name="recipe_ingredients",
    )
    fish = models.ForeignKey(
        Fish, on_delete=models.PROTECT, related_name="recipe_ingredients",
    )
    quantity_kg = models.DecimalField(
        max_digits=6, decimal_places=2, default=0.25,
        validators=[MinValueValidator(0)],
    )

    class Meta:
        # A recipe cannot list the same fish twice.
        unique_together = ("recipe", "fish")

    def __str__(self) -> str:
        return f"{self.quantity_kg} kg {self.fish.name} for {self.recipe.name}"


# ---------------------------------------------------------------------------
# Customers & preference learning
# ---------------------------------------------------------------------------
class Customer(models.Model):
    """An animal that visits PenguEats."""

    name = models.CharField(max_length=120)
    species = models.CharField(max_length=80, blank=True)
    email = models.EmailField(blank=True)
    joined_on = models.DateField(default=timezone.now)

    def __str__(self) -> str:
        return f"{self.name} the {self.species}" if self.species else self.name

    def top_categories(self, limit: int = 3):
        """Return this customer's most-loved recipe categories (learned)."""
        return self.preferences.order_by("-score")[:limit]


class CustomerPreference(models.Model):
    """A learned taste signal: how much a customer likes a recipe category.

    Every time the customer orders, the matching row's `score` goes up. This is
    a tiny, transparent 'recommendation engine' the stakeholder can understand.
    """

    customer = models.ForeignKey(
        Customer, on_delete=models.CASCADE, related_name="preferences",
    )
    category = models.CharField(max_length=12, choices=Recipe.Category.choices)
    score = models.FloatField(default=0.0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("customer", "category")
        ordering = ["-score"]

    def __str__(self) -> str:
        return f"{self.customer.name} likes {self.get_category_display()} ({self.score:.1f})"


# ---------------------------------------------------------------------------
# Orders (sales)
# ---------------------------------------------------------------------------
class Order(models.Model):
    """A customer's order, made up of one or more OrderItems."""

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        PREPARING = "PREPARING", "Preparing"
        SERVED = "SERVED", "Served"
        CANCELLED = "CANCELLED", "Cancelled"

    customer = models.ForeignKey(
        Customer, on_delete=models.PROTECT, related_name="orders",
    )
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PENDING,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    # --- Online ordering & payment (customers checking out on the website) ---
    # An order placed from the public cart is `is_online`. It only counts as a
    # real sale once `is_paid` flips true (after Stripe confirms payment), at
    # which point `seen_by_owner` is reset to False so it pings Pingu's
    # dashboard as a brand-new order notification.
    is_online = models.BooleanField(default=False)
    is_paid = models.BooleanField(default=False)
    paid_at = models.DateTimeField(null=True, blank=True)
    seen_by_owner = models.BooleanField(default=True)
    stripe_session_id = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Order #{self.pk} - {self.customer.name}"

    @property
    def total(self):
        """Sum of every line item. Computed, never stored, so it can't drift."""
        return sum((item.line_total for item in self.items.all()), start=0)

    @property
    def is_new_for_owner(self) -> bool:
        """A paid online order Pingu hasn't acknowledged yet (drives the bell)."""
        return self.is_online and self.is_paid and not self.seen_by_owner


class OrderItem(models.Model):
    """One recipe within an order, with the quantity and the price paid."""

    order = models.ForeignKey(
        Order, on_delete=models.CASCADE, related_name="items",
    )
    recipe = models.ForeignKey(
        Recipe, on_delete=models.PROTECT, related_name="order_items",
    )
    quantity = models.PositiveIntegerField(default=1)
    # We snapshot the price at order time so later menu changes don't rewrite history.
    unit_price = models.DecimalField(max_digits=8, decimal_places=2, default=0)

    def __str__(self) -> str:
        return f"{self.quantity} x {self.recipe.name}"

    @property
    def line_total(self):
        return self.quantity * self.unit_price


# ---------------------------------------------------------------------------
# Expenses (costs)
# ---------------------------------------------------------------------------
class Expense(models.Model):
    """Money going out: ice-block rent, fish supplier bills, utilities, etc."""

    class Category(models.TextChoices):
        ICE_RENT = "ICE_RENT", "Ice-block rent"
        SUPPLIES = "SUPPLIES", "Fish supplies"
        UTILITIES = "UTILITIES", "Utilities"
        WAGES = "WAGES", "Wages"
        OTHER = "OTHER", "Other"

    category = models.CharField(max_length=12, choices=Category.choices)
    description = models.CharField(max_length=200, blank=True)
    amount = models.DecimalField(
        max_digits=10, decimal_places=2, validators=[MinValueValidator(0)],
    )
    incurred_on = models.DateField(default=timezone.now)

    class Meta:
        ordering = ["-incurred_on"]

    def __str__(self) -> str:
        return f"{self.get_category_display()}: {self.amount}"
