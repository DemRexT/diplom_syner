#!/bin/sh
# Ждём базу данных, применяем миграции и запускаем переданную команду.
set -e

python - <<'PY'
import time, django
from django.db import connection
django.setup()
for attempt in range(60):
    try:
        connection.ensure_connection()
        break
    except Exception as exc:
        print(f"Жду базу данных… ({exc.__class__.__name__})", flush=True)
        time.sleep(2)
else:
    raise SystemExit("База данных недоступна")
PY

if [ "${RUN_MIGRATIONS:-0}" = "1" ]; then
    python manage.py migrate --noinput
fi

exec "$@"
