"""
DRF serializers translate model instances <-> JSON.

They are the API equivalent of Django forms: they validate incoming data and
shape outgoing data. Keeping them small and explicit makes the API easy to read.
"""
from rest_framework import serializers

from restaurant.models import Fish, Recipe


class FishSerializer(serializers.ModelSerializer):
    is_low_stock = serializers.BooleanField(read_only=True)

    class Meta:
        model = Fish
        fields = ["id", "name", "species", "quantity_kg", "cost_per_kg",
                  "freshness", "is_low_stock"]


class RecipeSerializer(serializers.ModelSerializer):
    chef_name = serializers.CharField(source="chef.name", default="", read_only=True)
    can_be_made = serializers.SerializerMethodField()

    class Meta:
        model = Recipe
        fields = ["id", "name", "slug", "category", "difficulty", "price",
                  "total_minutes", "chef_name", "is_featured", "can_be_made"]

    def get_can_be_made(self, obj: Recipe) -> bool:
        return obj.can_be_made()
