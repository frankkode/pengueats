"""ASGI entry-point for async-capable servers (e.g. Uvicorn, Daphne)."""
import os
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "pengueats.settings")
application = get_asgi_application()
