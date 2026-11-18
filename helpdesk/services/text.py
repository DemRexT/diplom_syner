"""Простая обработка русского текста: нормализация, токены, «псевдоосновы»."""
import re

_WORD = re.compile(r"[a-zа-я0-9]+")

# Слова, которые не несут смысла для поиска
STOPWORDS = {
    "и", "в", "во", "не", "на", "с", "со", "по", "у", "к", "о", "об", "от", "до", "за", "из",
    "что", "как", "это", "а", "но", "или", "мне", "меня", "мой", "моя", "мое", "у", "же",
    "уже", "есть", "нет", "был", "была", "было", "при", "для", "так", "то", "ли", "бы",
    "пожалуйста", "очень", "почему", "просто", "можно", "нужно", "надо", "через", "после",
}


def normalize(text: str) -> str:
    return (text or "").lower().replace("ё", "е")


def tokens(text: str) -> list[str]:
    return [w for w in _WORD.findall(normalize(text)) if w not in STOPWORDS]


def stem(word: str) -> str:
    """Очень грубый стемминг: отрезаем окончание, оставляя первые 5 букв.

    Для дипломного прототипа этого достаточно («принтер», «принтера», «принтеру»
    дают одну основу). В реальной системе можно подключить pymorphy3.
    """
    return word[:5] if len(word) > 5 else word


def stems(text: str) -> set[str]:
    return {stem(w) for w in tokens(text) if len(w) >= 2}


def contains_keyword(text_norm: str, text_tokens: list[str], keyword: str) -> bool:
    """Ключевое слово из нескольких слов ищем как фразу, одиночное — как начало слова."""
    keyword = normalize(keyword).strip()
    if not keyword:
        return False
    if not keyword.isalnum():  # фраза или слово с дефисом: «не работает», «wi-fi»
        return keyword in text_norm
    return any(t.startswith(keyword) for t in text_tokens)
