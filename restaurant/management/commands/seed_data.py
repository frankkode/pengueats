"""
Management command:  python manage.py seed_data

Populates the database with a realistic, demo-ready PenguEats world: suppliers,
chefs, fish inventory, recipes (with ingredient links), customers, a few orders
(which exercise the real order pipeline) and some expenses.

Running this gives you a fully populated site to present, every time, from a
clean database. It is idempotent: it clears existing demo rows first.
"""
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils.text import slugify

from restaurant import services
from restaurant.models import (
    Chef, Customer, Expense, Fish, Order, OrderItem, Recipe,
    RecipeIngredient, Supplier,
)


class Command(BaseCommand):
    help = "Load realistic demo data for PenguEats."

    def handle(self, *args, **options):
        self.stdout.write("Clearing old demo data...")
        for model in (OrderItem, Order, RecipeIngredient, Recipe, Fish,
                      Customer, Chef, Supplier, Expense):
            model.objects.all().delete()

        # --- Suppliers ---------------------------------------------------
        antarctic = Supplier.objects.create(
            name="Antarctic Fresh Co.", contact_email="sales@antarcticfresh.ex")
        deep_blue = Supplier.objects.create(
            name="Deep Blue Wholesalers", contact_email="orders@deepblue.ex")

        # --- Chefs (match the 'Recipe by' cards) -------------------------
        maria = Chef.objects.create(
            name="Chef Maria Rodriguez", title="Head Chef",
            photo="restaurant/img/chef_maria.jpg",
            bio="Twenty years turning the daily catch into delicacies.")
        emily = Chef.objects.create(
            name="Chef Emily Parker", title="Sous Chef",
            photo="restaurant/img/chef_emily.jpg")

        # --- Fish inventory ---------------------------------------------
        # (name, kg in stock, cost/kg, supplier)
        fish_rows = [
            ("Salmon", "24", "9.50", antarctic),
            ("Herring", "40", "4.20", antarctic),
            ("Krill", "60", "2.10", deep_blue),
            ("Cod", "18", "7.80", deep_blue),
            ("Mackerel", "30", "5.00", antarctic),
            ("Anchovy", "3", "3.30", deep_blue),   # deliberately low stock
        ]
        fish = {}
        for name, kg, cost, sup in fish_rows:
            fish[name] = Fish.objects.create(
                name=name, species=name, quantity_kg=Decimal(kg),
                cost_per_kg=Decimal(cost), supplier=sup,
            )

        # --- Recipes (with the fish each one needs) ----------------------
        def make_recipe(name, category, difficulty, price, prep, cook, summary,
                        steps, chef, featured, ingredients, image):
            recipe = Recipe.objects.create(
                name=name, slug=slugify(name), category=category,
                difficulty=difficulty, price=Decimal(price), prep_minutes=prep,
                cook_minutes=cook, summary=summary, description=summary,
                instructions="\n".join(steps), chef=chef, is_featured=featured,
                image=image, views=0,
            )
            for fish_name, qty in ingredients:
                RecipeIngredient.objects.create(
                    recipe=recipe, fish=fish[fish_name], quantity_kg=Decimal(qty))
            return recipe

        r1 = make_recipe(
            "Mediterranean Grilled Salmon", Recipe.Category.MAIN,
            Recipe.Difficulty.INTERMEDIATE, "16.00", 15, 20,
            "Succulent salmon marinated in aromatic herbs, served with creamy "
            "tzatziki for an exquisite experience.",
            ["Pat the salmon dry and season with herbs, salt and pepper.",
             "Grill skin-side down over medium-high heat for 6 minutes.",
             "Flip and cook a further 4 minutes until opaque.",
             "Rest for 2 minutes, then serve with tzatziki and lemon."],
            maria, True, [("Salmon", "0.30")],
            "restaurant/img/recipe_salmon.jpg")

        r2 = make_recipe(
            "Spicy Herring Vermicelli Salad", Recipe.Category.SALAD,
            Recipe.Difficulty.BEGINNER, "11.00", 20, 0,
            "Layers of spicy goodness and savoury herring -- a refreshing "
            "timeless favourite.",
            ["Soak the vermicelli until soft, then drain.",
             "Flake the cured herring into bite-size pieces.",
             "Toss with chilli, lime and fresh herbs.",
             "Chill for 10 minutes and serve cold."],
            emily, False, [("Herring", "0.20")],
            "restaurant/img/recipe_salad.jpg")

        r3 = make_recipe(
            "Krill Tempura Bites", Recipe.Category.APPETIZER,
            Recipe.Difficulty.BEGINNER, "8.50", 10, 8,
            "Crispy, golden krill tempura -- the perfect shareable starter.",
            ["Whisk a light tempura batter with ice-cold water.",
             "Dip the krill and fry at 180C until golden.",
             "Drain and season with sea salt.",
             "Serve with a citrus dipping sauce."],
            maria, False, [("Krill", "0.25")],
            "restaurant/img/recipe_tempura.jpg")

        r4 = make_recipe(
            "Classic Cod & Mackerel Stew", Recipe.Category.MAIN,
            Recipe.Difficulty.INTERMEDIATE, "14.50", 15, 30,
            "A hearty, warming stew of flaky cod and rich mackerel.",
            ["Sweat aromatics in a deep pot.",
             "Add stock and simmer for 15 minutes.",
             "Add the cod and mackerel; poach gently for 8 minutes.",
             "Finish with herbs and serve with crusty bread."],
            emily, False, [("Cod", "0.30"), ("Mackerel", "0.20")],
            "restaurant/img/recipe_stew.jpg")

        r5 = make_recipe(
            "Healthy Anchovy Power Bowl", Recipe.Category.HEALTHY,
            Recipe.Difficulty.BEGINNER, "12.00", 12, 5,
            "A nutrient-packed bowl topped with omega-rich anchovies.",
            ["Build a base of greens and grains.",
             "Add roasted vegetables.",
             "Top with seared anchovies.",
             "Drizzle with citrus dressing."],
            maria, False, [("Anchovy", "0.50")],  # needs more than is in stock
            "restaurant/img/recipe_bowl.jpg")

        # --- Customers ---------------------------------------------------
        customers = [
            Customer.objects.create(name="Wally", species="walrus",
                                    email="wally@ice.ex"),
            Customer.objects.create(name="Ola", species="orca",
                                    email="ola@ocean.ex"),
            Customer.objects.create(name="Sandy", species="seal",
                                    email="sandy@shore.ex"),
        ]

        # --- Orders (run through the REAL pipeline so stock & taste update) -
        services.place_order(customers[0], [
            services.OrderLine(r1, 2), services.OrderLine(r3, 1)])
        services.place_order(customers[1], [
            services.OrderLine(r2, 1), services.OrderLine(r1, 1)])
        services.place_order(customers[2], [
            services.OrderLine(r4, 1)])
        services.place_order(customers[0], [
            services.OrderLine(r2, 2), services.OrderLine(r3, 2)])
        services.place_order(customers[1], [
            services.OrderLine(r1, 1), services.OrderLine(r4, 1)])
        services.place_order(customers[2], [
            services.OrderLine(r3, 3)])

        # --- Expenses ----------------------------------------------------
        Expense.objects.create(category=Expense.Category.ICE_RENT,
                               description="Daily ice-block rent", amount=Decimal("22"))
        Expense.objects.create(category=Expense.Category.SUPPLIES,
                               description="Daily fish supplies", amount=Decimal("60"))
        Expense.objects.create(category=Expense.Category.UTILITIES,
                               description="Cold-storage power", amount=Decimal("18"))

        # --- Report ------------------------------------------------------
        summary = services.financial_summary()
        self.stdout.write(self.style.SUCCESS(
            f"Seeded {Recipe.objects.count()} recipes, {Fish.objects.count()} fish, "
            f"{Customer.objects.count()} customers, {Order.objects.count()} orders."))
        self.stdout.write(self.style.SUCCESS(
            f"Revenue {summary.revenue} - Expenses {summary.expenses} "
            f"= Profit {summary.profit} ({summary.margin_pct:.0f}% margin)."))
