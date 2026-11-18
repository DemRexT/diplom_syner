"""Логика диалога бота, общая для ВКонтакте и MAX.

handle(platform, user_id, text, payload) получает входящее сообщение
и возвращает список ответов (Reply). Состояние диалога хранится в BotSession.

Состояния:
  ""                  — главное меню
  await_description   — ждём описание проблемы
  await_kb_decision   — показали статьи БЗ, ждём «помогло / создать заявку»
  await_kb_query      — ждём вопрос для поиска по базе знаний
  await_reply         — ждём ответ автора по конкретной заявке
"""
import re

from django.conf import settings
from django.db.models import F

from helpdesk.bots.base import Button, Reply
from helpdesk.models import BotSession, KBArticle, Profile, Ticket
from helpdesk.services import kb, tickets

MENU = [
    [Button("📝 Новая заявка", {"cmd": "new"}, "primary")],
    [Button("📋 Мои заявки", {"cmd": "my"}), Button("📚 База знаний", {"cmd": "kb"})],
]
CANCEL = [[Button("✖ Отмена", {"cmd": "menu"}, "negative")]]

# Текстовые команды на случай, если пользователь пишет словами, а не жмёт кнопки
TEXT_COMMANDS = {
    "начать": "start", "старт": "start", "start": "start", "/start": "start", "меню": "menu",
    "новая заявка": "new", "мои заявки": "my", "база знаний": "kb", "отмена": "menu",
}

ID_FIELD = {"vk": "vk_id", "max": "max_id"}
CHANNEL = {"vk": Ticket.Channel.VK, "max": Ticket.Channel.MAX}


def handle(platform: str, user_id: str, text: str, payload: dict) -> list[Reply]:
    session, _ = BotSession.objects.get_or_create(platform=platform, external_id=user_id)
    text = (text or "").strip()
    cmd = payload.get("cmd") or TEXT_COMMANDS.get(text.lower().lstrip("📝📋📚✖ ").strip())

    profile = Profile.objects.filter(**{ID_FIELD[platform]: user_id}).select_related("user").first()
    if profile is None:
        return _link_account(platform, user_id, text)

    user = profile.user
    if cmd in ("start", "menu"):
        _set(session, "")
        return [Reply(f"Здравствуйте, {user.first_name or user.username}! Чем помочь?", MENU)]
    if cmd == "new":
        _set(session, "await_description")
        return [Reply("Опишите проблему одним сообщением: что случилось и где.\n"
                      "Например: «Не печатает принтер в кабинете 312».", CANCEL)]
    if cmd == "my":
        _set(session, "")
        return [_my_tickets(user)]
    if cmd == "kb":
        _set(session, "await_kb_query")
        return [Reply("Что ищете? Напишите вопрос, например «как подключить VPN».", CANCEL)]
    if cmd == "kb_helped":
        return _kb_helped(session, payload)
    if cmd == "create":
        return _create_from_session(session, user, platform)
    if cmd == "rate":
        return _rate(user, payload)
    if cmd == "reopen":
        return _reopen(session, user, payload)
    if cmd == "reply":
        ticket = _own_ticket(user, payload.get("id"))
        if not ticket:
            return [Reply("Заявка не найдена.", MENU)]
        _set(session, "await_reply", {"ticket_id": ticket.pk})
        return [Reply(f"Напишите ответ по заявке #{ticket.pk}:", CANCEL)]

    # Свободный текст — смотрим, чего мы ждём от пользователя
    if not text:
        return [Reply("Выберите действие:", MENU)]
    if session.state == "await_description":
        return _got_description(session, user, platform, text)
    if session.state == "await_kb_query":
        _set(session, "")
        return [_kb_answer(text)]
    if session.state == "await_reply":
        ticket = _own_ticket(user, session.data.get("ticket_id"))
        _set(session, "")
        if ticket:
            tickets.add_comment(ticket, user, text, channel=CHANNEL[platform])
            return [Reply(f"Ответ добавлен в заявку #{ticket.pk}. Специалист получил уведомление.", MENU)]
        return [Reply("Заявка не найдена.", MENU)]
    if session.state == "await_reopen_reason":
        ticket = _own_ticket(user, session.data.get("ticket_id"))
        _set(session, "")
        if ticket:
            tickets.reopen(ticket, user, reason=text)
            return [Reply(f"Заявка #{ticket.pk} снова в работе.", MENU)]

    # Пользователь просто написал проблему без нажатия кнопки — сразу обрабатываем как заявку
    return _got_description(session, user, platform, text)


# --- сценарии ---------------------------------------------------------------

def _link_account(platform, user_id, text):
    code = re.sub(r"\D", "", text)
    if len(code) == 6:
        profile = Profile.objects.filter(link_code=code).select_related("user").first()
        if profile:
            setattr(profile, ID_FIELD[platform], user_id)
            profile.link_code = ""
            profile.save()
            return [Reply(f"Аккаунт привязан: {profile}. Теперь можно создавать заявки прямо здесь.", MENU)]
        return [Reply("Код не найден. Проверьте его в профиле на портале и отправьте ещё раз.")]
    return [Reply(
        "Здравствуйте! Я бот ИТ-поддержки ООО «Поисковая машина».\n\n"
        "Чтобы я вас узнал, привяжите аккаунт:\n"
        f"1. Откройте портал {settings.SITE_URL}/profile/\n"
        "2. Скопируйте 6-значный код привязки\n"
        "3. Отправьте его сюда одним сообщением"
    )]


def _got_description(session, user, platform, text):
    if len(text) < 5:
        return [Reply("Опишите проблему чуть подробнее, пожалуйста.", CANCEL)]
    articles = kb.suggest(text)
    if not articles:
        _set(session, "")
        return [_create(user, platform, text)]
    _set(session, "await_kb_decision", {"text": text, "articles": [a.pk for a in articles]})
    lines = ["Возможно, это поможет решить проблему сразу:\n"]
    for i, a in enumerate(articles, 1):
        lines.append(f"{i}. {a.title}\n{_short(a.body)}\n{settings.SITE_URL}/kb/{a.pk}/\n")
    lines.append("Помогло?")
    return [Reply("\n".join(lines), [
        [Button("✅ Да, помогло", {"cmd": "kb_helped"}, "positive")],
        [Button("📝 Нет, создать заявку", {"cmd": "create"}, "primary")],
    ])]


def _kb_helped(session, payload):
    ids = session.data.get("articles", [])
    if ids:
        KBArticle.objects.filter(pk=ids[0]).update(helped=F("helped") + 1)
    _set(session, "")
    return [Reply("Отлично, рад, что получилось! 🙌", MENU)]


def _create_from_session(session, user, platform):
    text = session.data.get("text")
    _set(session, "")
    if not text:
        return [Reply("Опишите проблему — нажмите «Новая заявка».", MENU)]
    return [_create(user, platform, text)]


def _create(user, platform, text):
    title = text.split("\n", 1)[0][:80]
    ticket = tickets.create_ticket(user, title, text, channel=CHANNEL[platform])
    # Уведомление о создании уходит из сервиса; здесь — только меню
    return Reply(f"Заявка #{ticket.pk} зарегистрирована. Я сообщу, когда будут новости.", MENU)


def _my_tickets(user):
    items = list(Ticket.objects.filter(author=user).exclude(status=Ticket.Status.CLOSED)[:5])
    if not items:
        return Reply("Открытых заявок нет 👍", MENU)
    lines = ["Ваши заявки:\n"]
    for t in items:
        lines.append(f"#{t.pk} {t.title}\n   {t.get_status_display()}"
                     + (f" · {t.assignee.get_full_name()}" if t.assignee else ""))
    return Reply("\n".join(lines), MENU)


def _kb_answer(text):
    articles = kb.suggest(text)
    if not articles:
        return Reply("Ничего не нашёл. Можно создать заявку — специалист поможет.", MENU)
    lines = ["Нашёл в базе знаний:\n"]
    for a in articles:
        lines.append(f"• {a.title}\n{settings.SITE_URL}/kb/{a.pk}/")
    return Reply("\n".join(lines), MENU)


def _rate(user, payload):
    ticket = _own_ticket(user, payload.get("id"))
    if not ticket:
        return [Reply("Заявка не найдена.", MENU)]
    tickets.rate(ticket, payload.get("v", 5), user)
    return [Reply(f"Спасибо за оценку! Заявка #{ticket.pk} закрыта.", MENU)]


def _reopen(session, user, payload):
    ticket = _own_ticket(user, payload.get("id"))
    if not ticket:
        return [Reply("Заявка не найдена.", MENU)]
    _set(session, "await_reopen_reason", {"ticket_id": ticket.pk})
    return [Reply("Что осталось не так? Опишите, и заявка вернётся специалисту.", CANCEL)]


# --- утилиты ---------------------------------------------------------------

def _own_ticket(user, ticket_id):
    try:
        return Ticket.objects.get(pk=int(ticket_id), author=user)
    except (Ticket.DoesNotExist, TypeError, ValueError):
        return None


def _set(session, state, data=None):
    session.state = state
    session.data = data or {}
    session.save()


def _short(text, limit=160):
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + "…"

