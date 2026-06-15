"""
Forms for PenguEats.

Using Django's ModelForm keeps validation rules next to the model: the form
automatically enforces field types, max lengths and the unique `slug`
constraint, so the view stays thin and we never hand-write HTML inputs.
"""
from django import forms
from django.utils.text import slugify

from .models import Recipe


class RecipeForm(forms.ModelForm):
    """Create a new menu recipe from the owner dashboard.

    The slug is optional in the UI: if Pingu leaves it blank we derive a clean,
    URL-safe slug from the recipe name automatically.
    """

    class Meta:
        model = Recipe
        fields = [
            "name", "slug", "category", "difficulty", "price",
            "summary", "prep_minutes", "cook_minutes", "servings",
            "photo", "is_featured",
        ]
        widgets = {
            "summary": forms.TextInput(attrs={"placeholder": "One-line description"}),
            "price": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
            "photo": forms.ClearableFileInput(attrs={"accept": "image/*"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # The slug can be auto-generated, so it is not required in the form.
        self.fields["slug"].required = False
        self.fields["slug"].help_text = "Leave blank to generate from the name."

    def clean_slug(self):
        """Fall back to a slug derived from the name when one isn't supplied."""
        slug = self.cleaned_data.get("slug")
        if not slug:
            slug = slugify(self.cleaned_data.get("name", ""))
        return slug
