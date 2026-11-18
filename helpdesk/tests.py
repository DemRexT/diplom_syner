"""Автотесты. Запуск: python manage.py test helpdesk"""
from datetime import timedelta
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from helpdesk.bots import core
from helpdesk.models import Category, KBArticle, Profile, Ticket
from helpdesk.services import tickets as svc
from helpdesk.services.classifier import classify
from helpdesk.services.kb import suggest

User = get_user_model()


class BaseCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", tickets=0, stdout=StringIO())
        cls.author = User.objects.get(username="petrova")
        cls.vip = User.objects.get(username="fedorov")


class ClassifierTests(BaseCase):
    def test_categories(self):
        cases = {
            "Не печатает принтер": "Оборудование",
            "Не подключается VPN": "Сеть / VPN",
            "Забыл пароль от учётной записи": "Доступы и учётные записи",
            "Не работает 1С": "Серверы и 1С",
            "Не приходят письма в Outlook": "Почта и телефония",
            "Установить Figma": "Программное обеспечение",
            "Wi-Fi в переговорной": "Сеть / VPN",
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(classify(text, "").category.name, expected)

    def test_unknown_goes_to_other(self):
        r = classify("Абракадабра", "Непонятный текст")
        self.assertEqual(r.category.name, "Прочее")
        self.assertEqual(r.confidence, 0)


class TicketFlowTests(BaseCase):
    def test_create_assigns_least_loaded_specialist(self):
        t1 = svc.create_ticket(self.author, "Не печатает принтер", "Принтер в кабинете 312")
        t2 = svc.create_ticket(self.author, "Сломалась мышь", "Нужна новая мышь")
        group = Category.objects.get(name="Оборудование").support_group
        self.assertEqual(t1.assignee.profile.support_group, group)
        self.assertEqual(t1.status, Ticket.Status.ASSIGNED)
        # в группе «Рабочие места» два специалиста — вторая заявка уходит другому
        self.assertNotEqual(t1.assignee, t2.assignee)
        self.assertIsNotNone(t1.sla_deadline)
        self.assertTrue(t1.history.filter(is_auto=True).exists())

    def test_critical_marker_raises_priority(self):
        t = svc.create_ticket(self.author, "Пропал интернет", "Не работает интернет у всех в отделе")
        self.assertEqual(t.priority.name, "Критический")

    def test_vip_priority_bump(self):
        normal = svc.create_ticket(self.author, "Сломалась мышь", "Нужна замена")
        vip = svc.create_ticket(self.vip, "Сломалась мышь", "Нужна замена")
        self.assertGreater(vip.priority.level, normal.priority.level)

    def test_sla_warning_and_escalation(self):
        t = svc.create_ticket(self.author, "Сломалась мышь", "Нужна замена")
        total = t.sla_deadline - t.created_at
        svc.check_sla(now=t.created_at + total * 0.8)
        t.refresh_from_db()
        self.assertTrue(t.sla_warned)
        self.assertFalse(t.escalated)
        svc.check_sla(now=t.sla_deadline + timedelta(minutes=1))
        t.refresh_from_db()
        self.assertTrue(t.escalated)

    def test_auto_close_resolved(self):
        t = svc.create_ticket(self.author, "Сломалась мышь", "Нужна замена")
        svc.change_status(t, Ticket.Status.RESOLVED, actor=t.assignee)
        Ticket.objects.filter(pk=t.pk).update(resolved_at=timezone.now() - timedelta(days=4))
        svc.check_sla()
        t.refresh_from_db()
        self.assertEqual(t.status, Ticket.Status.CLOSED)

    def test_rating_closes_ticket(self):
        t = svc.create_ticket(self.author, "Сломалась мышь", "Нужна замена")
        svc.change_status(t, Ticket.Status.RESOLVED, actor=t.assignee)
        svc.rate(t, 5, self.author)
        t.refresh_from_db()
        self.assertEqual((t.status, t.rating), (Ticket.Status.CLOSED, 5))


class KnowledgeBaseTests(BaseCase):
    def test_suggest(self):
        titles = [a.title for a in suggest("не подключается vpn из дома")]
        self.assertIn("Как подключиться к VPN через FortiClient", titles)
        self.assertEqual(suggest("абракадабра"), [])


class BotTests(BaseCase):
    def say(self, text="", **payload):
        return core.handle("vk", "1001", text, payload)

    def test_full_dialog(self):
        # 1. неизвестный пользователь — просим код
        self.assertIn("привяжите", self.say("Привет")[0].text)
        # 2. привязка по коду
        code = self.author.profile.ensure_link_code()
        self.assertIn("привязан", self.say(code)[0].text)
        self.assertEqual(Profile.objects.get(user=self.author).vk_id, "1001")
        # 3. новая заявка → бот предлагает статью БЗ
        self.say(cmd="new")
        reply = self.say("Не печатает принтер, документы висят в очереди")[0]
        self.assertIn("Принтер в очереди", reply.text)
        # 4. не помогло → создаём заявку
        reply = self.say(cmd="create")[0]
        t = Ticket.objects.get(author=self.author)
        self.assertEqual(t.channel, Ticket.Channel.VK)
        self.assertIn(f"#{t.pk}", reply.text)
        # 5. ответ по заявке через бота
        self.say(cmd="reply", id=t.pk)
        self.say("Принтер HP на 3 этаже")
        self.assertEqual(t.comments.get().text, "Принтер HP на 3 этаже")
        # 6. оценка после решения
        svc.change_status(t, Ticket.Status.RESOLVED, actor=t.assignee)
        self.say(cmd="rate", id=t.pk, v=4)
        t.refresh_from_db()
        self.assertEqual((t.status, t.rating), (Ticket.Status.CLOSED, 4))

    def test_kb_helped_counter(self):
        self.author.profile.vk_id = "1001"
        self.author.profile.save()
        article = KBArticle.objects.get(title="Принтер в очереди, но не печатает")
        before = article.helped
        self.say(cmd="new")
        self.say("Не печатает принтер, документы висят в очереди")
        self.say(cmd="kb_helped")
        article.refresh_from_db()
        self.assertEqual(article.helped, before + 1)
        self.assertFalse(Ticket.objects.exists())


class WebTests(BaseCase):
    def test_pages_by_role(self):
        call_command("seed_demo", tickets=20, stdout=StringIO())
        for login, urls in {
            "petrova": ["/tickets/new/", "/tickets/my/", "/kb/", "/profile/"],
            "volkov": ["/queue/", "/queue/?scope=all&status="],
            "manager": ["/dashboard/", "/dashboard/export/", f"/tickets/{Ticket.objects.first().pk}/"],
        }.items():
            self.client.force_login(User.objects.get(username=login))
            for url in urls:
                with self.subTest(user=login, url=url):
                    self.assertEqual(self.client.get(url).status_code, 200)
        self.client.force_login(User.objects.get(username="petrova"))
        self.assertEqual(self.client.get("/dashboard/").status_code, 403)

    def test_create_via_portal(self):
        self.client.force_login(self.author)
        r = self.client.post("/tickets/new/", {"title": "Не печатает принтер", "description": "Кабинет 312"})
        t = Ticket.objects.get()
        self.assertRedirects(r, f"/tickets/{t.pk}/")
        self.assertEqual(t.category.name, "Оборудование")
