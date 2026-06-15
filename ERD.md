# PenguEats — Database Design (ERD)

Render this diagram at https://mermaid.live or in any Mermaid-capable viewer.

```mermaid
erDiagram
    SUPPLIER ||--o{ FISH : "supplies"
    FISH ||--o{ RECIPE_INGREDIENT : "used in"
    RECIPE ||--o{ RECIPE_INGREDIENT : "requires"
    CHEF ||--o{ RECIPE : "authors"
    CUSTOMER ||--o{ ORDER : "places"
    ORDER ||--o{ ORDER_ITEM : "contains"
    RECIPE ||--o{ ORDER_ITEM : "sold as"
    CUSTOMER ||--o{ CUSTOMER_PREFERENCE : "has learned taste"

    SUPPLIER {
        int id PK
        string name
        string contact_email
    }
    FISH {
        int id PK
        string name
        decimal quantity_kg
        decimal cost_per_kg
        string freshness
        int supplier_id FK
    }
    CHEF {
        int id PK
        string name
        string title
    }
    RECIPE {
        int id PK
        string name
        string slug
        string category
        string difficulty
        decimal price
        int prep_minutes
        int cook_minutes
        image photo
        bool is_featured
        int views
        int chef_id FK
    }
    RECIPE_INGREDIENT {
        int id PK
        int recipe_id FK
        int fish_id FK
        decimal quantity_kg
    }
    CUSTOMER {
        int id PK
        string name
        string species
        string email
    }
    CUSTOMER_PREFERENCE {
        int id PK
        int customer_id FK
        string category
        float score
    }
    ORDER {
        int id PK
        int customer_id FK
        string status
        datetime created_at
        bool is_online
        bool is_paid
        datetime paid_at
        bool seen_by_owner
        string stripe_session_id
    }
    ORDER_ITEM {
        int id PK
        int order_id FK
        int recipe_id FK
        int quantity
        decimal unit_price
    }
    EXPENSE {
        int id PK
        string category
        decimal amount
        date incurred_on
    }
```

## Relationship summary
- **Supplier → Fish** (1-to-many): each supplier provides many fish types.
- **Fish ↔ Recipe** (many-to-many via **RecipeIngredient**): the association table
  carries the *quantity in kg* each recipe needs — this is the link between the
  menu and the inventory, and it powers the "cook right now" suggestions.
- **Chef → Recipe** (1-to-many).
- **Customer → Order → OrderItem ← Recipe**: a classic order-lines model. The
  unit price is snapshotted on each OrderItem so historical totals never change.
  Web orders carry payment state on **Order** (`is_online`, `is_paid`, `paid_at`,
  `seen_by_owner`, `stripe_session_id`): an online order only counts as revenue
  and deducts inventory once `is_paid` is true, and clearing `seen_by_owner`
  drives the dashboard's new-order notification.
- **Customer ↔ Recipe.category via CustomerPreference**: a learned taste score
  that grows every time the customer orders from a category.
- **Expense** stands alone and feeds the profit calculation
  (`profit = revenue − expenses`).

> Notes: the diagram shows each table's principal columns; a few purely
> descriptive fields (e.g. `Supplier.notes`, `Chef.bio`, `Recipe.instructions`)
> are omitted for readability. Freshness-based **dynamic pricing**
> (`current_price`, `discount_pct`) is *computed* from the least-fresh linked
> fish at read time — it is not a stored column, so it doesn't appear in the
> schema.
