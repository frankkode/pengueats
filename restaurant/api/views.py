"""
JSON API endpoints built with Django REST Framework.

ReadOnlyModelViewSet gives list + detail endpoints with pagination and a
browsable UI out of the box. The custom @action exposes the recipe-suggestion
service over HTTP so a future mobile app (the 'Get Our Mobile App' button in
the design) could call it.
"""
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from restaurant import services
from restaurant.models import Fish, Recipe

from .serializers import FishSerializer, RecipeSerializer


class FishViewSet(viewsets.ReadOnlyModelViewSet):
    """GET /api/fish/  and  GET /api/fish/{id}/"""
    queryset = Fish.objects.all()
    serializer_class = FishSerializer

    @action(detail=False, methods=["get"])
    def low_stock(self, request):
        """GET /api/fish/low_stock/ -> fish that need reordering."""
        data = FishSerializer(services.low_stock_report(), many=True).data
        return Response(data)


class RecipeViewSet(viewsets.ReadOnlyModelViewSet):
    """GET /api/recipes/  and  GET /api/recipes/{id}/"""
    queryset = Recipe.objects.all()
    serializer_class = RecipeSerializer

    @action(detail=False, methods=["get"])
    def in_stock(self, request):
        """GET /api/recipes/in_stock/ -> recipes cookable with current inventory."""
        data = RecipeSerializer(services.suggest_recipes_in_stock(), many=True).data
        return Response(data)
