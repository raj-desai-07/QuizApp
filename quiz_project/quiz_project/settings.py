"""Django settings for quiz_project."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
# The insecure fallback key is only allowed while DEBUG is on (local development).
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY") or ("dev-only-insecure-key-change-me" if DEBUG else None)
if not SECRET_KEY:
    from django.core.exceptions import ImproperlyConfigured

    raise ImproperlyConfigured("Set DJANGO_SECRET_KEY when DJANGO_DEBUG=0.")
ALLOWED_HOSTS = [h for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "").split(",") if h]

INSTALLED_APPS = [
    "django.contrib.sessions",
    "django.contrib.staticfiles",
    "quiz",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "quiz_project.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
            ],
        },
    },
]

WSGI_APPLICATION = "quiz_project.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Server-side (database) sessions: quiz state never leaves the server.
SESSION_ENGINE = "django.contrib.sessions.backends.db"
CSRF_FAILURE_VIEW = "quiz.views.csrf_failed"

# Quiz questions file (read on every request).
QUESTIONS_FILE = BASE_DIR / "data" / "questions.json"

# Session / CSRF hardening
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_COOKIE_AGE = 60 * 60 * 6

# Set DJANGO_HTTPS=1 behind HTTPS to send cookies over secure connections only.
if os.environ.get("DJANGO_HTTPS") == "1":
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
