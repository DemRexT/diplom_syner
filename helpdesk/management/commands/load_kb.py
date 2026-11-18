"""Загрузка/обновление базы знаний из helpdesk/kb_data.py.

python manage.py load_kb

Статьи обновляются по заголовку, поэтому команду можно запускать повторно:
изменённые тексты обновятся, счётчики просмотров сохранятся.
Статьи, добавленные вручную через админку, не затрагиваются.
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from helpdesk.kb_data import KB_ARTICLES, SUPPORT_CONTACTS
from helpdesk.models import Category, KBArticle

# Заголовки статей из первой версии демо-данных, которые заменены новыми
OBSOLETE_TITLES = [
    "Ошибка аутентификации VPN после смены пароля",
    "Как отсканировать документ на МФУ в папку",
    "Сброс забытого пароля от учётной записи",
    "Как запросить доступ к общей папке",
    "Outlook не получает почту",
    "Не работает Wi-Fi в переговорной",
]


def load_articles(update=True):
    """update=False — только добавить недостающие статьи, не трогая существующие."""
    categories = {c.name: c for c in Category.objects.all()}
    created = updated = 0
    for title, category, keywords, body in KB_ARTICLES:
        text = body.strip()
        if "заявк" not in text.splitlines()[-1]:
            text += "\n\n" + SUPPORT_CONTACTS
        fields = {"category": categories.get(category), "keywords": keywords, "body": text}
        if update:
            _, is_new = KBArticle.objects.update_or_create(title=title, defaults=fields)
        else:
            _, is_new = KBArticle.objects.get_or_create(title=title, defaults=fields)
        created += is_new
        updated += not is_new and update
    removed, _ = KBArticle.objects.filter(title__in=OBSOLETE_TITLES).delete()
    return created, updated, removed


class Command(BaseCommand):
    help = "Загрузить или обновить статьи базы знаний"

    @transaction.atomic
    def handle(self, *args, **options):
        if not Category.objects.exists():
            self.stderr.write("Сначала создайте категории: python manage.py init_project")
            return
        created, updated, removed = load_articles()
        self.stdout.write(self.style.SUCCESS(
            f"База знаний: добавлено {created}, обновлено {updated}, удалено устаревших {removed}. "
            f"Всего статей: {KBArticle.objects.count()}."
        ))
