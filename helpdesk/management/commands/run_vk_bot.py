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
            self.stderr.write("Впишите VK_TOKEN и VK_GROUP_ID в файл .env (см. README, раздел «Подключение ботов»).")
        except KeyboardInterrupt:
            self.stdout.write("Бот остановлен.")
