from functools import partial

from django.core.management.base import BaseCommand

from helpdesk.bots import core, vk


class Command(BaseCommand):
    help = "Запуск бота ИТ-поддержки во ВКонтакте (long polling)"

    def handle(self, *args, **options):
        vk.run_forever(partial(core.handle, "vk"))
