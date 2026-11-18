"""Уведомления пользователей: ВКонтакте, MAX и электронная почта.

Сообщение уходит во все каналы, которые есть у пользователя: в привязанные
мессенджеры и на e-mail (если он указан и письма не отключены в профиле).
Если канал не настроен или произошла ошибка — сайт продолжает работать,
ошибка только пишется в лог.
"""
import logging
import re
import threading
from contextlib import contextmanager

from django.conf import settings
from django.core.mail import send_mail

from helpdesk.bots import max as max_bot
from helpdesk.bots import vk as vk_bot
from helpdesk.bots.base import Button, Reply

log = logging.getLogger("helpdesk.notify")
_suppressed = threading.local()


@contextmanager
def suppressed():
    """Временно отключить уведомления (например, при загрузке демо-данных)."""
    _suppressed.on = True
    try:
        yield
    finally:
        _suppressed.on = False


def notify(user, text, keyboard=None):
    if user is None or getattr(_suppressed, "on", False):
        return
    profile = getattr(user, "profile", None)
    if profile is None:
        return
    reply = Reply(text, keyboard or [])
    if profile.vk_id and settings.VK_TOKEN:
        try:
            vk_bot.send(profile.vk_id, reply)
        except Exception as exc:
            log.warning("ВК: не удалось отправить %s: %s", user, exc)
    if profile.max_id and settings.MAX_TOKEN:
        try:
            max_bot.send(profile.max_id, reply)
        except Exception as exc:
            log.warning("MAX: не удалось отправить %s: %s", user, exc)
    if profile.notify_email and user.email:
        send_email(user, text)


_EMOJI = re.compile(r"^[^\wА-Яа-яЁё#]+")
_TICKET_NO = re.compile(r"#(\d+)")


def send_email(user, text):
    """Письмо с тем же текстом, что и в мессенджере, плюс ссылка на заявку."""
    first_line = _EMOJI.sub("", text.split("\n", 1)[0]).strip()
    subject = f"ServiceDesk ПМ: {first_line}"[:150]
    body = text
    match = _TICKET_NO.search(text)
    site = settings.SITE_URL.rstrip("/")
    if match and f"{site}/tickets/" not in text:
        body += f"\n\nОткрыть заявку: {site}/tickets/{match.group(1)}/"
    body += (f"\n\n—\nСлужба ИТ-поддержки ООО «Поисковая машина»\n"
             f"Отключить письма можно в профиле: {site}/profile/")

    def _send():
        try:
            send_mail(subject, body, None, [user.email], fail_silently=False)
        except Exception as exc:
            log.warning("Почта: не удалось отправить %s: %s", user.email, exc)

    if settings.EMAIL_ASYNC:
        threading.Thread(target=_send, daemon=True).start()
    else:
        _send()


def ticket_link(ticket):
    return f"{settings.SITE_URL.rstrip('/')}/tickets/{ticket.pk}/"


def reply_button(ticket):
    return [Button("💬 Ответить", {"cmd": "reply", "id": ticket.pk}, "primary")]


def rating_keyboard(ticket):
    return [
        [Button(f"{v} ⭐", {"cmd": "rate", "id": ticket.pk, "v": v}, "positive" if v >= 4 else "secondary") for v in range(1, 6)],
        [Button("🔁 Проблема не решена", {"cmd": "reopen", "id": ticket.pk}, "negative")],
    ]
