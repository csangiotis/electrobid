"""
Ρυθμίσεις Django για το subcontractor.gr.

Για παραγωγή ορίστε τις μεταβλητές περιβάλλοντος:
  DJANGO_SECRET_KEY, DJANGO_DEBUG=0, DJANGO_ALLOWED_HOSTS
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY", "dev-only-insecure-key-change-me-in-production"
)
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
# Το domain της πλατφόρμας (και www.) γίνεται πάντα δεκτό
SITE_DOMAIN = os.environ.get("SITE_DOMAIN", "subcontractor.gr")
ALLOWED_HOSTS += [SITE_DOMAIN, f"www.{SITE_DOMAIN}"]
CSRF_TRUSTED_ORIGINS = [
    f"https://{h.lstrip('.')}" if not h.startswith(".") else f"https://*{h}"
    for h in ALLOWED_HOSTS if h not in ("localhost", "127.0.0.1") and h
]

# GitHub Codespaces: η εφαρμογή ανοίγει σε https://<όνομα>-8000.app.github.dev
if os.environ.get("CODESPACES") == "true":
    ALLOWED_HOSTS.append(".app.github.dev")
    CSRF_TRUSTED_ORIGINS.append("https://*.app.github.dev")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework.authtoken",
    "accounts",
    "tenders",
    "notify",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "notify.middleware.ScheduledTasksMiddleware",
]

# Σερβίρισμα static αρχείων σε παραγωγή (αν είναι εγκατεστημένο το whitenoise)
try:
    import whitenoise  # noqa: F401

    MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")
except ImportError:
    pass

if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = os.environ.get("DJANGO_SSL_REDIRECT", "1") == "1"

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "frontend"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}
# Σε server: DATABASE_URL=postgres://... (π.χ. από το Render)
if os.environ.get("DATABASE_URL"):
    import dj_database_url

    DATABASES["default"] = dj_database_url.parse(os.environ["DATABASE_URL"], conn_max_age=600)

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
     "OPTIONS": {"min_length": 8}},
]

LANGUAGE_CODE = "el"
TIME_ZONE = "Europe/Athens"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "frontend" / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "media/"
# Σε server με persistent disk (π.χ. Render Disk): MEDIA_ROOT=/var/data/media
MEDIA_ROOT = Path(os.environ.get("MEDIA_ROOT", BASE_DIR / "media"))

# ---- Αποθήκευση αρχείων σε S3 / Cloudflare R2 ----
# Αν οριστεί AWS_STORAGE_BUCKET_NAME, σχέδια, φωτογραφίες και συνημμένα αποθηκεύονται εκεί
# (ιδιωτικό bucket· η λήψη περνά πάντα από το API με έλεγχο δικαιωμάτων).
if os.environ.get("AWS_STORAGE_BUCKET_NAME"):
    STORAGES = {
        "default": {"BACKEND": "storages.backends.s3.S3Storage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
    AWS_STORAGE_BUCKET_NAME = os.environ["AWS_STORAGE_BUCKET_NAME"]
    AWS_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY")
    AWS_S3_ENDPOINT_URL = os.environ.get("AWS_S3_ENDPOINT_URL") or None  # R2: https://<account>.r2.cloudflarestorage.com
    AWS_S3_REGION_NAME = os.environ.get("AWS_S3_REGION_NAME", "auto")
    AWS_DEFAULT_ACL = None
    AWS_QUERYSTRING_AUTH = True
    AWS_S3_FILE_OVERWRITE = False

# Μέγιστο μέγεθος ανεβασμένου αρχείου (σχέδια μπορεί να είναι μεγάλα)
DATA_UPLOAD_MAX_MEMORY_SIZE = 50 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024
MAX_DOCUMENT_SIZE = 50 * 1024 * 1024
ALLOWED_DOCUMENT_EXTENSIONS = {
    ".pdf", ".dwg", ".dxf", ".xlsx", ".xls", ".csv", ".docx", ".doc",
    ".png", ".jpg", ".jpeg", ".zip",
}

# ---- Email ----
# Χωρίς EMAIL_HOST τα email εμφανίζονται στο terminal (ανάπτυξη).
# Για παραγωγή: EMAIL_HOST, EMAIL_PORT (587), EMAIL_HOST_USER, EMAIL_HOST_PASSWORD
# (π.χ. Brevo: smtp-relay.brevo.com, Microsoft 365: smtp.office365.com).
SITE_URL = os.environ.get("SITE_URL", "https://subcontractor.gr" if not DEBUG else "http://127.0.0.1:8000")
SITE_NAME = "subcontractor.gr"
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "subcontractor.gr <no-reply@subcontractor.gr>")
if os.environ.get("EMAIL_HOST"):
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST = os.environ["EMAIL_HOST"]
    EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
    EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
    EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
    EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", "1") == "1"
    EMAIL_TIMEOUT = 15
else:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
# Η επιβεβαίωση email απαιτείται (για δημοσίευση/υποβολή) μόνο όταν στέλνονται πραγματικά email
REQUIRE_EMAIL_VERIFICATION = os.environ.get(
    "REQUIRE_EMAIL_VERIFICATION", "1" if os.environ.get("EMAIL_HOST") else "0") == "1"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.TokenAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"]
    + (["rest_framework.renderers.BrowsableAPIRenderer"] if DEBUG else []),
    "COERCE_DECIMAL_TO_STRING": False,
}
