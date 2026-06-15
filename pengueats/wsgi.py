"""WSGI entry-point used by production servers such as Gunicorn or uWSGI."""
import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "pengueats.settings")
application = get_wsgi_application()
