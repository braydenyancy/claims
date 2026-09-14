"""Django settings. Every environment-specific value comes from the
environment with a development default; nothing secret lives here."""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-insecure-key-change-me")
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "claims",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]

ROOT_URLCONF = "config.urls"
STATIC_URL = "static/"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "claims"),
        "USER": os.environ.get("POSTGRES_USER", "claims"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", "claims"),
        "HOST": os.environ.get("POSTGRES_HOST", "localhost"),
        "PORT": os.environ.get("POSTGRES_PORT", "5433"),
    }
}

AUTH_USER_MODEL = "claims.User"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
    "EXCEPTION_HANDLER": "claims.api.exceptions.exception_handler",
}

# Session cookie is the credential; CSRF cookie is readable so the SPA
# can echo it in the X-CSRFToken header.
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_HTTPONLY = False
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_TRUSTED_ORIGINS = os.environ.get(
    "CSRF_TRUSTED_ORIGINS", "http://localhost:5173,http://localhost:8000"
).split(",")

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

CLEARINGHOUSE = {
    "GATEWAY": os.environ.get("CLEARINGHOUSE_GATEWAY", "claims.clearinghouse.gateway.VendorGateway"),
    "MAX_ATTEMPTS": int(os.environ.get("CLEARINGHOUSE_MAX_ATTEMPTS", "5")),
    "LEASE_SECONDS": int(os.environ.get("CLEARINGHOUSE_LEASE_SECONDS", "60")),
    "POLL_SECONDS": float(os.environ.get("CLEARINGHOUSE_POLL_SECONDS", "1.0")),
    # A local wait limit, not a cancellation of the vendor call. An expired
    # lease becomes UNCERTAIN and is never automatically resubmitted.
    "CALL_TIMEOUT_SECONDS": float(os.environ.get("CLEARINGHOUSE_CALL_TIMEOUT_SECONDS", "20")),
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"plain": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "plain"}},
    "loggers": {"claims": {"handlers": ["console"], "level": "INFO", "propagate": False}},
}
