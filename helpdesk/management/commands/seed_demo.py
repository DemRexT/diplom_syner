"""Заполнение базы демонстрационными данными для показа и скриншотов.

python manage.py seed_demo          — справочники, пользователи, база знаний, ~250 заявок за 60 дней
python manage.py seed_demo --clear  — сначала удалить все заявки и демо-данные
"""
import random
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from helpdesk.models import (
    BotSession, Category, Department, KBArticle, Priority, Profile, SLARule, SupportGroup, Ticket, TicketHistory,
)
from helpdesk.services import tickets as svc

PASSWORD = "demo12345"

PRIORITIES = [  # имя, уровень, цвет, реакция (мин), решение (мин)
    ("Низкий", 1, "secondary", 240, 3 * 24 * 60),
    ("Средний", 2, "info", 60, 8 * 60),
    ("Высокий", 3, "warning", 30, 4 * 60),
    ("Критический", 4, "danger", 10, 60),
]

GROUPS = ["Рабочие места", "Сеть и связь", "Серверы и 1С", "Доступы и учётные записи"]

CATEGORIES = [  # имя, группа, приоритет, ключевые слова
    ("Оборудование", "Рабочие места", "Низкий",
     "принтер, печат, мфу, сканер, картридж, монитор, мышь, клавиатур, ноутбук, компьютер, гарнитур, наушник, бумаг"),
    ("Программное обеспечение", "Рабочие места", "Низкий",
     "установ, программ, лицензи, обновлени, office, excel, word, figma, браузер, антивирус, приложени"),
    ("Сеть / VPN", "Сеть и связь", "Средний",
     "vpn, впн, интернет, сеть, wi-fi, wifi, вайфай, forticlient, подключ, роутер, кабель"),
    ("Почта и телефония", "Сеть и связь", "Средний",
     "почт, outlook, письм, ящик, телефон, звонк, ip-телефон, рассылк"),
    ("Серверы и 1С", "Серверы и 1С", "Высокий",
     "сервер, 1с, база, бэкап, резервн, сайт, портал, виртуальн"),
    ("Доступы и учётные записи", "Доступы и учётные записи", "Средний",
     "доступ, пароль, учетн, учётн, логин, заблокир, папк, права, войти, вход, аккаунт"),
    ("Прочее", "Рабочие места", "Низкий", ""),
]

DEPARTMENTS = ["Бухгалтерия", "Отдел продаж", "Маркетинг", "Разработка", "HR", "Администрация"]

STAFF = [  # логин, фамилия, имя, роль, группа
    ("manager", "Соколов", "Андрей", "manager", None),
    ("kuznetsov", "Кузнецов", "Максим", "specialist", "Сеть и связь"),
    ("volkov", "Волков", "Сергей", "specialist", "Рабочие места"),
    ("novikova", "Новикова", "Елена", "specialist", "Серверы и 1С"),
    ("zaitsev", "Зайцев", "Павел", "specialist", "Доступы и учётные записи"),
    ("lebedev", "Лебедев", "Илья", "specialist", "Рабочие места"),
]

EMPLOYEES = [
    ("petrova", "Петрова", "Ирина", "Отдел продаж", "Менеджер по продажам", False),
    ("smirnov", "Смирнов", "Алексей", "Маркетинг", "Маркетолог", False),
    ("orlov", "Орлов", "Дмитрий", "Разработка", "Дизайнер", False),
    ("ivanova", "Иванова", "Ольга", "Бухгалтерия", "Главный бухгалтер", False),
    ("fedorov", "Фёдоров", "Николай", "Администрация", "Генеральный директор", True),
    ("morozova", "Морозова", "Анна", "HR", "HR-менеджер", False),
    ("pavlov", "Павлов", "Кирилл", "Разработка", "Программист", False),
    ("egorova", "Егорова", "Мария", "Отдел продаж", "Руководитель отдела продаж", False),
]

KB = [
    ("Как подключиться к VPN через FortiClient", "Сеть / VPN", "vpn, впн, удалённая работа, forticlient, из дома",
     "1. Установите FortiClient VPN с портала software.poisk.local.\n2. Создайте подключение: сервер vpn.poisk.ru, порт 443.\n"
     "3. Введите доменный логин и пароль.\n4. Подтвердите вход кодом из приложения-аутентификатора.\n\n"
     "Если появляется ошибка «Сертификат недействителен» — проверьте дату и время на компьютере."),
    ("Ошибка аутентификации VPN после смены пароля", "Сеть / VPN", "vpn, пароль, ошибка, аутентификац",
     "После смены доменного пароля FortiClient хранит старый. Откройте подключение → «Изменить» → удалите сохранённый пароль "
     "и войдите заново. Если учётная запись заблокирована после нескольких попыток — подождите 15 минут."),
    ("Принтер в очереди, но не печатает", "Оборудование", "принтер, печать, не печатает, очередь",
     "1. Проверьте, что принтер включён и на нём нет ошибки (замятие, нет бумаги).\n"
     "2. Откройте «Параметры → Принтеры», выберите принтер → «Открыть очередь» → «Отменить все документы».\n"
     "3. Выключите принтер на 30 секунд и включите снова.\n4. Отправьте документ ещё раз."),
    ("Как отсканировать документ на МФУ в папку", "Оборудование", "сканер, сканировать, мфу, скан",
     "На МФУ нажмите «Сканирование → В сетевую папку», выберите себя в адресной книге. "
     "Файл появится в \\\\fs\\scan\\<ваш логин> через минуту."),
    ("Сброс забытого пароля от учётной записи", "Доступы и учётные записи", "пароль, забыл, сброс, вход, учетная запись, заблокирована",
     "Пароль можно сбросить самостоятельно на портале passwd.poisk.local: введите логин и код из SMS. "
     "Требования: не менее 10 символов, буквы разного регистра и цифры."),
    ("Как запросить доступ к общей папке", "Доступы и учётные записи", "доступ, папка, права, общая папка",
     "Создайте заявку в категории «Доступы», укажите путь к папке и нужные права (чтение или запись). "
     "Доступ выдаётся после согласования с владельцем папки — обычно в течение рабочего дня."),
    ("Outlook не получает почту", "Почта и телефония", "почта, outlook, письма, не приходят",
     "Проверьте значок подключения в правом нижнем углу Outlook. Если «Отключено» — нажмите «Отправить/получить → "
     "Автономная работа», чтобы снять режим. Проверьте, не переполнен ли ящик (лимит 10 ГБ)."),
    ("Как установить программу из каталога ПО", "Программное обеспечение", "установить, программа, по, приложение",
     "Откройте «Центр программного обеспечения» в меню Пуск, найдите программу и нажмите «Установить». "
     "Если программы нет в каталоге — создайте заявку, указав название и зачем она нужна."),
    ("Не работает Wi-Fi в переговорной", "Сеть / VPN", "wi-fi, wifi, вайфай, переговорная, гостевая сеть",
     "Сотрудники подключаются к сети PM-Corp с доменным логином. Для гостей — сеть PM-Guest, пароль у администратора на ресепшене."),
]

SAMPLES = [  # тема, описание
    ("Не подключается VPN из дома", "После обновления Windows FortiClient пишет ошибка аутентификации. Пароль верный."),
    ("Не печатает принтер на 3 этаже", "Документы уходят в очередь, но принтер ничего не печатает."),
    ("Выдать доступ к папке Маркетинг", "Нужен доступ на запись к общей папке \\\\fs\\marketing для нового сотрудника."),
    ("Установить Figma", "Нужна Figma для работы над макетами сайта."),
    ("Забыл пароль", "Не могу войти в компьютер, учётная запись заблокирована."),
    ("Не приходят письма в Outlook", "С утра не получаю почту, отправка работает."),
    ("Не работает 1С", "1С не открывается у всего отдела бухгалтерии, пишет что сервер недоступен."),
    ("Сломалась мышь", "Мышь перестала работать, нужна замена."),
    ("Медленный интернет", "Очень медленно грузятся сайты, видеозвонки обрываются."),
    ("Не работает IP-телефон", "Телефон на столе не включается, нет гудка."),
    ("Монитор мерцает", "Второй монитор мерцает и иногда гаснет."),
    ("Обновить Office", "Excel просит обновление и не открывает файлы с макросами."),
    ("Нужен доступ к CRM", "Новому менеджеру нужен логин в CRM-систему."),
    ("Wi-Fi в переговорной", "Гости не могут подключиться к Wi-Fi в переговорной."),
    ("Не сканирует МФУ", "Сканер МФУ на 2 этаже не отправляет сканы в папку."),
    ("Ошибка при входе на портал", "Корпоративный портал выдаёт ошибку 502."),
    ("Подключить второй монитор", "Прошу выдать и подключить второй монитор."),
    ("Заблокирован аккаунт", "После отпуска не могу войти, пишет что учётная запись заблокирована."),
    ("Кончился картридж", "В принтере бухгалтерии закончился картридж."),
    ("Пропал интернет", "Пропал интернет у всех в отделе продаж."),
    ("Вопрос по ноутбуку", "Ноутбук сильно греется и шумит."),
    ("Не открывается сайт", "Не открывается внешний сайт поставщика, у коллег тоже."),
]

COMMENTS_IT = [
    "Добрый день! Посмотрю в течение часа.",
    "Пришлите, пожалуйста, скриншот ошибки.",
    "Подключился удалённо, проверяю.",
    "Готово, проверьте, пожалуйста.",
]


class Command(BaseCommand):
    help = "Заполнить базу демонстрационными данными"

    def add_arguments(self, parser):
        parser.add_argument("--clear", action="store_true", help="удалить существующие заявки и справочники")
        parser.add_argument("--tickets", type=int, default=250)
        parser.add_argument("--days", type=int, default=60)

    @transaction.atomic
    def handle(self, *args, clear=False, tickets=250, days=60, **opts):
        random.seed(42)
        User = get_user_model()
        if clear:
            Ticket.objects.all().delete()
            KBArticle.objects.all().delete()
            BotSession.objects.all().delete()
            Category.objects.all().delete()
            SLARule.objects.all().delete()
            Priority.objects.all().delete()
            User.objects.filter(is_superuser=False).delete()
            SupportGroup.objects.all().delete()
            Department.objects.all().delete()

        prio = {}
        for name, level, color, react, resolve in PRIORITIES:
            p, _ = Priority.objects.update_or_create(name=name, defaults={"level": level, "color": color})
            SLARule.objects.update_or_create(priority=p, defaults={"reaction_minutes": react, "resolve_minutes": resolve})
            prio[name] = p

        groups = {g: SupportGroup.objects.get_or_create(name=g)[0] for g in GROUPS}
        for name, group, p, kw in CATEGORIES:
            Category.objects.update_or_create(name=name, defaults={
                "support_group": groups[group], "default_priority": prio[p], "keywords": kw})
        deps = {d: Department.objects.get_or_create(name=d)[0] for d in DEPARTMENTS}
        it_dep, _ = Department.objects.get_or_create(name="ИТ-отдел")

        def make_user(login, last, first, role, **profile):
            u, created = User.objects.get_or_create(username=login, defaults={"first_name": first, "last_name": last})
            if created:
                u.set_password(PASSWORD)
                u.save()
            Profile.objects.filter(user=u).update(role=role, **profile)
            u.refresh_from_db()
            return u

        if not User.objects.filter(username="admin").exists():
            User.objects.create_superuser("admin", "", PASSWORD, first_name="Админ", last_name="Системный")
        Profile.objects.filter(user__username="admin").update(role="manager", department=it_dep)

        for login, last, first, role, group in STAFF:
            make_user(login, last, first, role, department=it_dep,
                      position="Руководитель ИТ-отдела" if role == "manager" else "Специалист техподдержки",
                      support_group=groups.get(group))
        employees = [
            make_user(login, last, first, "employee", department=deps[dep], position=pos, is_vip=vip)
            for login, last, first, dep, pos, vip in EMPLOYEES
        ]

        for title, cat, kw, body in KB:
            KBArticle.objects.update_or_create(title=title, defaults={
                "category": Category.objects.get(name=cat), "keywords": kw, "body": body,
                "views": random.randint(10, 120), "helped": random.randint(3, 30)})

        self._make_tickets(employees, tickets, days)
        self.stdout.write(self.style.SUCCESS(
            f"Готово. Заявок в базе: {Ticket.objects.count()}.\n"
            f"Пароль у всех демо-пользователей: {PASSWORD}\n"
            "  admin      — администратор (+ дашборд)\n"
            "  manager    — руководитель ИТ (дашборд, переназначение)\n"
            "  kuznetsov, volkov, novikova, zaitsev, lebedev — специалисты\n"
            "  petrova, smirnov, orlov, ivanova, fedorov ... — сотрудники"
        ))

    def _make_tickets(self, employees, count, days):
        now = timezone.now()
        starts = sorted(
            now - timedelta(days=days) + timedelta(minutes=random.randint(0, days * 24 * 60))
            for _ in range(count)
        )
        # Оставляем немного «живых» открытых заявок в последние сутки
        for i, created in enumerate(starts):
            # рабочее время 9–18
            local = timezone.localtime(created)
            created = local.replace(hour=random.randint(9, 17), minute=random.randint(0, 59))
            if created > now - timedelta(minutes=5):
                created = now - timedelta(minutes=random.randint(5, 300))
            title, desc = random.choice(SAMPLES)
            author = random.choice(employees)
            channel = random.choices(["portal", "vk", "max"], weights=[60, 25, 15])[0]
            t = svc.create_ticket(author, title, desc, channel=channel)

            shift = created - t.created_at
            t.created_at = created
            t.sla_deadline = t.sla_deadline + shift if t.sla_deadline else None
            t.save(update_fields=["created_at", "sla_deadline"])
            TicketHistory.objects.filter(ticket=t).update(created_at=created)
            if t.sla_deadline:
                TicketHistory.objects.filter(ticket=t, action__startswith="Срок решения").update(
                    action=f"Срок решения по SLA: {svc.fmt_dt(t.sla_deadline)}.")

            age_h = (now - created).total_seconds() / 3600
            if age_h < 30 and random.random() < 0.7:
                # свежая заявка — оставить открытой
                if t.assignee and random.random() < 0.5:
                    t.status = Ticket.Status.IN_PROGRESS
                    t.save(update_fields=["status"])
                continue

            sla_minutes = t.priority.sla.resolve_minutes
            # «до внедрения» (старые заявки) решались медленнее — это видно на графике
            factor = random.uniform(0.15, 1.3) if age_h < days * 24 / 2 else random.uniform(0.3, 1.8)
            resolve_delta = timedelta(minutes=max(10, sla_minutes * factor))
            resolved = min(created + resolve_delta, now - timedelta(minutes=5))
            if t.assignee:
                svc.Comment.objects.create(ticket=t, author=t.assignee, text=random.choice(COMMENTS_IT),
                                           created_at=created + resolve_delta / 4)
                t.first_response_at = created + resolve_delta / 4
            t.resolved_at = resolved
            t.status = Ticket.Status.CLOSED if random.random() < 0.85 else Ticket.Status.RESOLVED
            if t.status == Ticket.Status.CLOSED:
                t.closed_at = resolved + timedelta(hours=random.randint(1, 30))
                t.rating = random.choices([5, 4, 3, 2], weights=[60, 25, 10, 5])[0]
            t.save()
            TicketHistory.objects.create(ticket=t, action="Статус: «В работе» → «Решена».", actor=t.assignee,
                                         created_at=resolved)
