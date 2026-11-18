"""Уведомления пользователей в мессенджеры (ВКонтакте и/или MAX).

Сообщение уходит во все мессенджеры, к которым пользователь привязал аккаунт.
Если бот не настроен или произошла ошибка — сайт продолжает работать,
ошибка только пишется в лог.
"""
import logging

from django.conf import settings

from helpdesk.bots import max as max_bot
from helpdesk.bots import vk as vk_bot
from helpdesk.bots.base import Button, Reply

log = logging.getLogger("helpdesk.notify")


def notify(user, text, keyboard=None):
    if user is None:
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


def ticket_link(ticket):
    return f"{settings.SITE_URL.rstrip('/')}/tickets/{ticket.pk}/"


def reply_button(ticket):
    return [Button("💬 Ответить", {"cmd": "reply", "id": ticket.pk}, "primary")]


def rating_keyboard(ticket):
    return [
        [Button(f"{v} ⭐", {"cmd": "rate", "id": ticket.pk, "v": v}, "positive" if v >= 4 else "secondary") for v in range(1, 6)],
        [Button("🔁 Проблема не решена", {"cmd": "reopen", "id": ticket.pk}, "negative")],
    ]
