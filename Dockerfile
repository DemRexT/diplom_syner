FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DJANGO_SETTINGS_MODULE=config.settings \
    DEBUG=False \
    MEDIA_ROOT=/app/media \
    STATIC_ROOT=/app/staticfiles

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
# Статика собирается при сборке образа (ключ нужен только для запуска команды)
RUN SECRET_KEY=build-only python manage.py collectstatic --noinput -v0 \
 && useradd --system --uid 1000 app && mkdir -p /app/media && chown -R app /app/media

USER app
ENTRYPOINT ["sh", "/app/deploy/docker-entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--access-logfile", "-"]
