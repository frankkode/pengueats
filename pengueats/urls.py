"""Root URL configuration for PenguEats.

This file wires three things together:
  * the Django admin site (/admin/)
  * the public website pages (handled by the `restaurant` app)
  * the JSON REST API (/api/...)

During development Django also serves user-uploaded media and static files.
"""
from django.contrib import admin
from django.urls import include, path
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("restaurant.api.urls")),  # JSON API
    path("", include("restaurant.urls")),          # HTML website
]

# Serve static assets and user-uploaded media from the dev server
# (production uses a real web server / object store for these).
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
