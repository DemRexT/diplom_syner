"""Первичная настройка: создать/обновить таблицы БД и, если база пустая, загрузить демо-данные.

python manage.py init_project            — миграции + демо-данные (если заявок ещё нет)
python manage.py init_project --no-demo  — только миграции (для боевого сервера)
"""
from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Подготовить базу данных: миграции и демо-данные"

    def add_arguments(self, parser):
        parser.add_argument("--no-demo", action="store_true", help="не загружать демо-данные")

    def handle(self, *args, no_demo=False, **options):
        self.stdout.write("Применяю миграции…")
        call_command("migrate", interactive=False, verbosity=0)
        self.stdout.write(self.style.SUCCESS("База данных готова."))

        from helpdesk.management.commands.load_kb import load_articles
        from helpdesk.models import Category, Ticket
        if no_demo:
            return
        if Ticket.objects.exists():
            if Category.objects.exists():
                created, _, removed = load_articles(update=False)
                if created or removed:
                    self.stdout.write(f"База знаний: добавлено новых статей {created}.")
            self.stdout.write("В базе уже есть заявки — демо-данные не загружаю "
                              "(пересоздать: python manage.py seed_demo --clear).")
            return
        call_command("seed_demo", stdout=self.stdout)
