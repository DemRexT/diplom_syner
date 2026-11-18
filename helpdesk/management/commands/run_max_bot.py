from functools import partial

from django.core.management.base import BaseCommand

from helpdesk.bots import core, max as max_bot


class Command(BaseCommand):
    help = "Запуск бота ИТ-поддержки в мессенджере MAX (long polling)"

    def handle(self, *args, **options):
        max_bot.run_forever(partial(core.handle, "max"))
