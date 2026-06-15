#!/usr/bin/env python
"""Django's command-line utility for administrative tasks.

Run the development server with:
    python manage.py runserver

Other useful commands used in this project:
    python manage.py migrate          # create the SQLite database schema
    python manage.py seed_data        # load realistic demo data
    python manage.py createsuperuser  # create an admin account
"""
import os
import sys


def main() -> None:
    """Run administrative tasks."""
    # Point Django at our settings module before anything else happens.
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "pengueats.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:  # pragma: no cover - defensive import guard
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
