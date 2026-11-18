import time

from django.core.management.base import BaseCommand

from helpdesk.services.tickets import check_sla


class Command(BaseCommand):
    help = "Проверка SLA: предупреждения, эскалация, автозакрытие. --loop N — повторять каждые N секунд."

    def add_arguments(self, parser):
        parser.add_argument("--loop", type=int, default=0, help="интервал повтора в секундах (0 — один раз)")

    def handle(self, *args, loop=0, **options):
        while True:
            stats = check_sla()
            self.stdout.write(
                f"SLA: предупреждений {stats['warned']}, эскалаций {stats['escalated']}, "
                f"автозакрыто {stats['closed']}"
            )
            if not loop:
                break
            time.sleep(loop)
