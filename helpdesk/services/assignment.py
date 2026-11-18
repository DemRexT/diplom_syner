"""Автоматическое назначение исполнителя.

Алгоритм: берём специалистов из группы поддержки, отвечающей за категорию
заявки, и выбираем того, у кого сейчас меньше всего открытых заявок
(балансировка нагрузки). При равенстве — того, кто дольше не получал заявок.
Если в группе никого нет — заявка остаётся без исполнителя, её распределит
руководитель.
"""
from django.contrib.auth import get_user_model
from django.db.models import Count, Max, Q

from helpdesk.models import Profile, Ticket


def pick_assignee(category):
    User = get_user_model()
    candidates = (
        User.objects.filter(
            is_active=True,
            profile__role=Profile.Role.SPECIALIST,
            profile__support_group=category.support_group,
        )
        .annotate(
            open_count=Count(
                "assigned_tickets",
                filter=Q(assigned_tickets__status__in=Ticket.OPEN_STATUSES),
            ),
            last_assigned=Max("assigned_tickets__created_at"),
        )
    )
    candidates = list(candidates)
    if not candidates:
        return None, 0
    # None (никогда не получал заявок) считается самым «давним»
    candidates.sort(key=lambda u: (u.open_count, u.last_assigned.timestamp() if u.last_assigned else 0))
    best = candidates[0]
    return best, best.open_count


def workload():
    """Открытые заявки по каждому специалисту — для дашборда."""
    User = get_user_model()
    return (
        User.objects.filter(is_active=True, profile__role=Profile.Role.SPECIALIST)
        .annotate(open_count=Count("assigned_tickets", filter=Q(assigned_tickets__status__in=Ticket.OPEN_STATUSES)))
        .order_by("-open_count", "last_name")
    )
