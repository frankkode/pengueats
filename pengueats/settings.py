"""
Django settings for the PenguEats project.

PenguEats is Pingu the penguin's fish-restaurant management platform.
The configuration below is intentionally beginner-friendly: it uses SQLite
(zero setup, ships as a single file) and keeps third-party dependencies to a
minimum so the project is easy to run and easy to explain in an oral exam.

For production you would override SECRET_KEY, DEBUG and ALLOWED_HOSTS via
environment variables -- see the comments inline.
"""
from pathlib import Path
import os

# BASE_DIR is the project root (the folder containing manage.py).
BASE_DIR = Path(__file__).resolve().parent.parent

# --- Security -------------------------------------------------------------
# In a real deployment, read these from environment variables and never commit
# the real key. The default is only for local development.
SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "dev-only-key-change-me-in-production-0123456789",
)
DEBUG = os.environ.get("DJANGO_DEBUG", "True") == "True"
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")

# Railway gives each service a public domain in RAILWAY_PUBLIC_DOMAIN; trust it
# automatically so you don't have to copy it into an env var by hand.
RAILWAY_DOMAIN = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "")
if RAILWAY_DOMAIN:
    ALLOWED_HOSTS.append(RAILWAY_DOMAIN)

# CSRF needs the full https origin(s) of the deployed site. Comma-separate extra
# origins in DJANGO_CSRF_TRUSTED_ORIGINS if you add a custom domain.
CSRF_TRUSTED_ORIGINS = [
    o for o in os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if o
]
if RAILWAY_DOMAIN:
    CSRF_TRUSTED_ORIGINS.append(f"https://{RAILWAY_DOMAIN}")

# --- Applications ---------------------------------------------------------
INSTALLED_APPS = [
    "django.contrib.admin",          # built-in admin site (great for demos)
    "django.contrib.auth",           # authentication framework
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",                # exposes a small JSON API
    "restaurant",                    # our application
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # WhiteNoise serves the collected static files in production. It sits right
    # after SecurityMiddleware, as the WhiteNoise docs require.
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "pengueats.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],                 # app-level template folders are auto-discovered
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                # Makes the cart item-count available to every template (nav badge).
                "restaurant.context_processors.cart_summary",
            ],
        },
    },
]

WSGI_APPLICATION = "pengueats.wsgi.application"

# --- Database -------------------------------------------------------------
# SQLite keeps the whole database in one file (db.sqlite3). To switch to
# PostgreSQL later you only change this dict -- the rest of the code is
# database-agnostic thanks to the Django ORM.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

# In production, Railway injects a DATABASE_URL for its managed PostgreSQL.
# If present, dj-database-url parses it and replaces the SQLite default above —
# so the exact same code runs on SQLite locally and PostgreSQL in the cloud.
DATABASE_URL = os.environ.get("DATABASE_URL", "")
if DATABASE_URL:
    import dj_database_url
    DATABASES["default"] = dj_database_url.parse(DATABASE_URL, conn_max_age=600)

# --- Password validation --------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --- Internationalisation -------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# --- Static files (CSS, images, JS) ---------------------------------------
STATIC_URL = "static/"
STATICFILES_DIRS = []  # app-level static folders are auto-discovered
STATIC_ROOT = BASE_DIR / "staticfiles"  # used by `collectstatic` in production

# WhiteNoise compresses static files and serves them with far-future cache
# headers, so the app needs no separate CDN or S3 bucket in production.
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
    },
}

# --- Media files (user uploads, e.g. recipe photos) -----------------------
# Uploaded images live under MEDIA_ROOT on disk and are served from MEDIA_URL.
# Django's ImageField (used by Recipe.photo) requires the Pillow library.
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# Default primary-key type for models.
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Authentication -------------------------------------------------------
# The owner dashboard is private, so unauthenticated visitors are bounced to
# this login page. After signing in they land back on the dashboard; logging
# out returns them to the public home page.
LOGIN_URL = "restaurant:login"
LOGIN_REDIRECT_URL = "restaurant:dashboard"
LOGOUT_REDIRECT_URL = "restaurant:home"

# --- Payments (Stripe Checkout) -------------------------------------------
# Customers pay for online orders through Stripe's hosted Checkout in TEST
# mode. Put your test keys in the environment (they start with sk_test_ /
# pk_test_); with the test card 4242 4242 4242 4242 + any future expiry and CVC
# you get a successful payment without moving real money.
#   export STRIPE_SECRET_KEY=sk_test_...
#   export STRIPE_PUBLISHABLE_KEY=pk_test_...
# If no secret key is configured the checkout falls back to a clearly-labelled
# simulated payment, so the app still runs end-to-end in a demo without keys.
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_PUBLISHABLE_KEY = os.environ.get("STRIPE_PUBLISHABLE_KEY", "")
STRIPE_CURRENCY = "usd"

# --- Django REST Framework ------------------------------------------------
REST_FRAMEWORK = {
    # The browsable API is perfect for a live demo; pagination keeps payloads small.
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 10,
}
