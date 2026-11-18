from functools import partial

from django.core.management.base import BaseCommand

from helpdesk.bots import core, max as max_bot


class Command(BaseCommand):
    help = "Запуск бота ИТ-поддержки в мессенджере MAX (long polling)"

    def handle(self, *args, **options):
        try:
            max_bot.run_forever(partial(core.handle, "max"))
        except max_bot.MaxError as exc:
            self.stderr.write(self.style.ERROR(f"Бот MAX не запущен: {exc}"))
            if "Не задан" in str(exc):
                self.stderr.write("Впишите MAX_TOKEN в файл .env (см. README, раздел «Подключение ботов»).")
            else:
                self.stderr.write("Проверьте токен и настройки (см. README, раздел «Подключение ботов»).")
        except KeyboardInterrupt:
            self.stdout.write("Бот остановлен.")
