"""Адаптер мессенджера MAX: Bot API (long polling, метод GET /updates).

Настройка:
  1. Создайте бота через @MasterBot в MAX (или на платформе для партнёров MAX)
     и получите токен.
  2. Укажите его в .env (MAX_TOKEN). Адрес API — MAX_API_URL
     (по умолчанию https://platform-api.max.ru).

Формат запросов взят из документации dev.max.ru. API у MAX новый и меняется,
поэтому если что-то не работает, сверьтесь с актуальной документацией:
все обращения к API собраны в функциях call/send/answer_callback ниже.
"""
import logging
import time

import requests
from django.conf import settings

from helpdesk.bots.base import Reply, parse_payload

log = logging.getLogger("helpdesk.max")


class MaxError(RuntimeError):
    pass


def call(http_method: str, path: str, params=None, json=None, timeout=35):
    headers = {"Authorization": settings.MAX_TOKEN}
    params = dict(params or {})
    resp = requests.request(
        http_method, settings.MAX_API_URL.rstrip("/") + path,
        params=params, json=json, headers=headers, timeout=timeout,
    )
    if resp.status_code >= 400:
        raise MaxError(f"{http_method} {path}: {resp.status_code} {resp.text[:300]}")
    return resp.json() if resp.content else {}


def build_attachments(reply: Reply):
    if not reply.keyboard:
        return []
    buttons = [
        [{"type": "callback", "text": b.label[:64], "payload": b.payload_json()} for b in row]
        for row in reply.keyboard
    ]
    return [{"type": "inline_keyboard", "payload": {"buttons": buttons}}]


def send(user_id, reply: Reply):
    call("POST", "/messages", params={"user_id": user_id},
         json={"text": reply.text, "attachments": build_attachments(reply)})


def answer_callback(callback_id):
    try:
        call("POST", "/answers", params={"callback_id": callback_id}, json={"notification": "Принято"})
    except MaxError as exc:
        log.debug("answer_callback: %s", exc)


def run_forever(handle):
    """Цикл long polling. handle(user_id, text, payload) -> list[Reply]."""
    if not settings.MAX_TOKEN:
        raise MaxError("Не задан MAX_TOKEN в файле .env")

    me = call("GET", "/me")
    log.info("Бот MAX «%s» запущен, жду сообщений…", me.get("name") or me.get("username"))
    marker = None
    while True:
        params = {"timeout": 30, "types": "message_created,message_callback,bot_started"}
        if marker is not None:
            params["marker"] = marker
        try:
            data = call("GET", "/updates", params=params, timeout=40)
        except (requests.RequestException, MaxError) as exc:
            log.warning("Ошибка получения обновлений: %s, повтор через 3 с", exc)
            time.sleep(3)
            continue

        marker = data.get("marker", marker)
        for update in data.get("updates", []):
            try:
                _dispatch(update, handle)
            except Exception:
                log.exception("Ошибка обработки обновления")


def _dispatch(update, handle):
    kind = update.get("update_type")
    if kind == "message_created":
        msg = update["message"]
        if msg.get("recipient", {}).get("chat_type") not in (None, "dialog"):
            return  # только личные сообщения
        user_id = str(msg["sender"]["user_id"])
        text = (msg.get("body") or {}).get("text") or ""
        payload = {}
    elif kind == "message_callback":
        cb = update["callback"]
        user_id = str(cb["user"]["user_id"])
        text, payload = "", parse_payload(cb.get("payload"))
        answer_callback(cb.get("callback_id"))
    elif kind == "bot_started":
        user_id = str(update["user"]["user_id"])
        text, payload = "", {"cmd": "start"}
    else:
        return

    for reply in handle(user_id, text, payload):
        send(user_id, reply)
