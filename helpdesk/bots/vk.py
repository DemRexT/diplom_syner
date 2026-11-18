"""Адаптер ВКонтакте: Bots Long Poll API сообщества.

Настройка в сообществе ВК:
  Управление → Работа с API → Ключи доступа → создать ключ (права: сообщения сообщества).
  Работа с API → Long Poll API → включить, версия API 5.199,
  типы событий: «Входящее сообщение».
  Сообщения → включить сообщения сообщества; Настройки для бота → включить возможности ботов.
Токен и ID сообщества укажите в .env (VK_TOKEN, VK_GROUP_ID).
"""
import json
import logging
import random
import time

import requests
from django.conf import settings

from helpdesk.bots.base import Reply, parse_payload

log = logging.getLogger("helpdesk.vk")
API = "https://api.vk.com/method/"


class VKError(RuntimeError):
    pass


def call(method: str, **params):
    params.update(access_token=settings.VK_TOKEN, v=settings.VK_API_VERSION)
    resp = requests.post(API + method, data=params, timeout=35)
    data = resp.json()
    if "error" in data:
        raise VKError(f"{method}: {data['error'].get('error_msg')}")
    return data["response"]


def build_keyboard(reply: Reply) -> str:
    if not reply.keyboard:
        return json.dumps({"buttons": [], "one_time": True})
    rows = []
    for row in reply.keyboard[:10]:
        rows.append([
            {
                "action": {"type": "text", "label": b.label[:40], "payload": b.payload_json()},
                "color": b.color,
            }
            for b in row[:5]
        ])
    return json.dumps({"one_time": False, "inline": False, "buttons": rows}, ensure_ascii=False)


_keyboard_warned = False


def send(peer_id, reply: Reply):
    params = dict(peer_id=peer_id, random_id=random.randint(1, 2**31 - 1), message=reply.text)
    try:
        call("messages.send", keyboard=build_keyboard(reply), **params)
    except VKError as exc:
        # Кнопки доступны, только если в сообществе включены «Возможности ботов».
        # Если выключены — отвечаем без кнопок, чтобы бот не молчал.
        if "chat bot feature" not in str(exc).lower() and "keyboard" not in str(exc).lower():
            raise
        global _keyboard_warned
        if not _keyboard_warned:
            log.warning("Кнопки не работают: включите в сообществе «Управление → Сообщения → "
                        "Настройки для бота → Возможности ботов». Пока отвечаю без кнопок.")
            _keyboard_warned = True
        if reply.keyboard:
            hints = [b.label for row in reply.keyboard for b in row]
            params["message"] += "\n\nНапишите: " + " / ".join(hints)
        params["random_id"] = random.randint(1, 2**31 - 1)
        call("messages.send", **params)


def run_forever(handle):
    """Цикл Long Poll. handle(user_id, text, payload) -> list[Reply]."""
    if not settings.VK_TOKEN or not settings.VK_GROUP_ID:
        raise VKError("Не заданы VK_TOKEN и VK_GROUP_ID в файле .env")

    server = call("groups.getLongPollServer", group_id=settings.VK_GROUP_ID)
    log.info("Бот ВКонтакте запущен, жду сообщений…")
    while True:
        try:
            resp = requests.get(
                server["server"],
                params={"act": "a_check", "key": server["key"], "ts": server["ts"], "wait": 25},
                timeout=35,
            ).json()
        except requests.RequestException as exc:
            log.warning("Ошибка сети: %s, повтор через 3 с", exc)
            time.sleep(3)
            continue

        if "failed" in resp:
            # 1 — устарел ts, 2/3 — устарел ключ: получаем сервер заново
            if resp["failed"] == 1:
                server["ts"] = resp["ts"]
            else:
                server = call("groups.getLongPollServer", group_id=settings.VK_GROUP_ID)
            continue

        server["ts"] = resp["ts"]
        for update in resp.get("updates", []):
            if update.get("type") != "message_new":
                continue
            msg = update["object"]["message"]
            if msg.get("peer_id") != msg.get("from_id"):
                continue  # отвечаем только в личных сообщениях
            try:
                for reply in handle(str(msg["from_id"]), msg.get("text", ""), parse_payload(msg.get("payload"))):
                    send(msg["peer_id"], reply)
            except Exception:  # бот не должен падать из-за одной ошибки
                log.exception("Ошибка обработки сообщения")
