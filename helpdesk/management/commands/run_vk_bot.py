from functools import partial

from django.core.management.base import BaseCommand

from helpdesk.bots import core, vk


class Command(BaseCommand):
    help = "Запуск бота ИТ-поддержки во ВКонтакте (long polling)"

    def handle(self, *args, **options):
        try:
            vk.run_forever(partial(core.handle, "vk"))
        except vk.VKError as exc:
            self.stderr.write(self.style.ERROR(f"Бот ВКонтакте не запущен: {exc}"))
            if "Не задан" in str(exc):
                self.stderr.write("Впишите VK_TOKEN и VK_GROUP_ID в файл .env (см. README, раздел «Подключение ботов»).")
            elif "longpoll" in str(exc).lower():
                self.stderr.write("Включите Long Poll API: сообщество → Управление → Работа с API → Long Poll API "
                                  "→ «Включено», версия 5.199; на вкладке «Типы событий» отметьте «Входящее сообщение».")
            else:
                self.stderr.write("Проверьте токен и настройки (см. README, раздел «Подключение ботов»).")
        except KeyboardInterrupt:
            self.stdout.write("Бот остановлен.")
