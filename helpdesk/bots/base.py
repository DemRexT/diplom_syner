"""Общие для всех мессенджеров структуры: кнопка и ответ бота.

Логика диалога (helpdesk/bots/core.py) работает только с этими объектами
и ничего не знает о конкретной платформе. Адаптеры ВКонтакте и MAX
переводят их в формат своего API. Чтобы добавить ещё один мессенджер,
достаточно написать новый адаптер.
"""
import json
from dataclasses import dataclass, field


@dataclass
class Button:
    label: str
    payload: dict
    color: str = "secondary"  # primary | positive | negative | secondary

    def payload_json(self) -> str:
        return json.dumps(self.payload, ensure_ascii=False, separators=(",", ":"))


@dataclass
class Reply:
    text: str
    keyboard: list[list[Button]] = field(default_factory=list)


def parse_payload(raw) -> dict:
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except (TypeError, ValueError):
        return {}
