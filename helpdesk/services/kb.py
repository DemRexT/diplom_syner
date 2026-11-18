"""Поиск подходящих статей базы знаний по тексту обращения."""
from helpdesk.models import KBArticle
from helpdesk.services.text import stems


def suggest(query: str, limit: int = 3) -> list[KBArticle]:
    """Ранжирует статьи по числу общих основ слов.

    Совпадение с заголовком или ключевыми словами статьи весит 2, с текстом — 1.
    Возвращаются статьи, у которых совпало хотя бы 2 «очка».
    """
    q = stems(query)
    if not q:
        return []
    ranked = []
    for article in KBArticle.objects.all():
        head = stems(f"{article.title} {article.keywords}")
        body = stems(article.body)
        score = 2 * len(q & head) + len(q & (body - head))
        if score >= 2:
            ranked.append((score, article))
    ranked.sort(key=lambda pair: (-pair[0], pair[1].title))
    return [a for _, a in ranked[:limit]]
