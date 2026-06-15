"""API routing via DRF's DefaultRouter (auto-generates RESTful URLs)."""
from rest_framework.routers import DefaultRouter

from .views import FishViewSet, RecipeViewSet

router = DefaultRouter()
router.register("fish", FishViewSet, basename="fish")
router.register("recipes", RecipeViewSet, basename="recipe")

urlpatterns = router.urls
