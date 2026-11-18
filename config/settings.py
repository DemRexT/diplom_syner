"""Настройки проекта ServiceDesk ПМ.

Секреты и параметры окружения читаются из файла .env (см. .env.example).
"""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def env_bool(name, default=False):
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


DEBUG = env_bool("DEBUG", True)
SECRET_KEY = os.getenv("SECRET_KEY", "")
if not SECRET_KEY:
    if not DEBUG:
        raise RuntimeError("Задайте SECRET_KEY в .env — без него сервер в боевом режиме не запустится")
    SECRET_KEY = "dev-only-insecure-key-change-me"


def env_list(name, default=""):
    return [x.strip() for x in os.getenv(name, default).split(",") if x.strip()]


ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", "127.0.0.1,localhost")
# Для HTTPS-домена: CSRF_TRUSTED_ORIGINS=https://helpdesk.example.ru
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "helpdesk",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",  # раздача CSS/JS без отдельного веб-сервера
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "helpdesk.middleware.DatabaseNotReadyMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "helpdesk.context_processors.role",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# База данных: по умолчанию SQLite (ничего не нужно устанавливать).
# Для PostgreSQL задайте DB_ENGINE=postgres и параметры подключения в .env.
if os.getenv("DB_ENGINE", "sqlite") == "postgres":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("DB_NAME", "servicedesk"),
            "USER": os.getenv("DB_USER", "postgres"),
            "PASSWORD": os.getenv("DB_PASSWORD", ""),
            "HOST": os.getenv("DB_HOST", "localhost"),
            "PORT": os.getenv("DB_PORT", "5432"),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
]

LANGUAGE_CODE = "ru-ru"
TIME_ZONE = "Europe/Moscow"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = Path(os.getenv("STATIC_ROOT", BASE_DIR / "staticfiles"))
MEDIA_URL = "media/"
MEDIA_ROOT = Path(os.getenv("MEDIA_ROOT", BASE_DIR / "media"))
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage" if DEBUG
        else "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}
DATA_UPLOAD_MAX_MEMORY_SIZE = 20 * 1024 * 1024

# --- Безопасность в боевом режиме (за обратным прокси с HTTPS) ---
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    USE_X_FORWARDED_HOST = True
    SESSION_COOKIE_SECURE = env_bool("HTTPS", True)
    CSRF_COOKIE_SECURE = env_bool("HTTPS", True)
    SESSION_COOKIE_HTTPONLY = True
    X_FRAME_OPTIONS = "DENY"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "home"
LOGOUT_REDIRECT_URL = "login"

# --- Параметры системы ---
SITE_URL = os.getenv("SITE_URL", "http://127.0.0.1:8000")
SLA_WARNING_SHARE = 0.25      # предупреждать, когда осталось < 25% времени SLA
AUTO_CLOSE_DAYS = 3           # автозакрытие решённых заявок без подтверждения

# --- Боты ---
VK_TOKEN = os.getenv("VK_TOKEN", "")
VK_GROUP_ID = os.getenv("VK_GROUP_ID", "")
VK_API_VERSION = "5.199"

MAX_TOKEN = os.getenv("MAX_TOKEN", "")
MAX_API_URL = os.getenv("MAX_API_URL", "https://platform-api.max.ru")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}
