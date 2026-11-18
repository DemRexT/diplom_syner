"""Автоматическая классификация заявки и определение приоритета.

Алгоритм (для главы 2 диплома):
1. Текст заявки (тема + описание) приводится к нижнему регистру и разбивается на слова.
2. Для каждой категории считается «вес» — сколько её ключевых слов встретилось
   в тексте. Совпадение в теме считается вдвое ценнее, чем в описании.
3. Выбирается категория с максимальным весом. Уверенность = доля веса лучшей
   категории в сумме весов всех категорий.
4. Если ни одно слово не совпало — категория «Прочее».
5. Приоритет берётся из категории; повышается до «Критического» при словах-маркерах
   массового сбоя и на один уровень — для заявок от руководства компании.
"""
from dataclasses import dataclass

from helpdesk.models import Category, Priority
from helpdesk.services.text import contains_keyword, normalize, tokens

FALLBACK_CATEGORY = "Прочее"

CRITICAL_MARKERS = [
    "не работает сервер", "сервер упал", "сервер недоступ", "у всех", "весь отдел",
    "никто не может", "не работает интернет", "пропал интернет", "не работает 1с",
    "вирус", "шифровальщик", "утечка",
]


@dataclass
class Classification:
    category: Category
    confidence: float
    scores: dict


def classify(title: str, description: str) -> Classification:
    title_norm, desc_norm = normalize(title), normalize(description)
    title_tokens, desc_tokens = tokens(title), tokens(description)

    scores = {}
    categories = list(Category.objects.select_related("default_priority", "support_group"))
    for cat in categories:
        score = 0
        for kw in cat.keyword_list():
            if contains_keyword(title_norm, title_tokens, kw):
                score += 2
            if contains_keyword(desc_norm, desc_tokens, kw):
                score += 1
        if score:
            scores[cat.name] = score

    if not scores:
        fallback = next((c for c in categories if c.name == FALLBACK_CATEGORY), categories[0])
        return Classification(fallback, 0.0, {})

    best_name = max(scores, key=scores.get)
    best = next(c for c in categories if c.name == best_name)
    confidence = scores[best_name] / sum(scores.values())
    return Classification(best, round(confidence, 2), scores)


def detect_priority(category: Category, title: str, description: str, author) -> Priority:
    text = normalize(f"{title} {description}")
    priorities = list(Priority.objects.order_by("level"))
    top = priorities[-1]

    if any(marker in text for marker in CRITICAL_MARKERS):
        return top

    priority = category.default_priority
    profile = getattr(author, "profile", None)
    if profile and profile.is_vip and priority.level < top.level:
        priority = next(p for p in priorities if p.level > priority.level)
    return priority
