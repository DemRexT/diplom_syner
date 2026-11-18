from django.db.utils import OperationalError, ProgrammingError
from django.http import HttpResponse

HINT = """<!doctype html><meta charset="utf-8"><title>База данных не подготовлена</title>
<body style="font-family:system-ui;max-width:640px;margin:60px auto;line-height:1.6">
<h1>База данных ещё не подготовлена</h1>
<p>Таблицы не созданы. Выполните подготовку один раз:</p>
<ul>
<li><b>PyCharm:</b> запустите конфигурацию «1. Подготовка базы (первый запуск)»;</li>
<li><b>терминал:</b> <code>python manage.py init_project</code></li>
</ul>
<p>Затем обновите страницу.</p>
<p style="color:#888">Техническая причина: {error}</p></body>"""


class DatabaseNotReadyMiddleware:
    """Показывает понятную подсказку вместо ошибки «no such table», если забыли миграции."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_exception(self, request, exception):
        if isinstance(exception, (OperationalError, ProgrammingError)) and (
            "no such table" in str(exception) or "does not exist" in str(exception)
        ):
            return HttpResponse(HINT.format(error=exception), status=503)
        return None
