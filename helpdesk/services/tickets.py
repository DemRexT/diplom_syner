"""Бизнес-логика жизненного цикла заявки.

И сайт, и боты вызывают только эти функции, поэтому правила
(классификация, назначение, SLA, уведомления, журнал) работают одинаково
независимо от канала, через который пришла заявка.
"""
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from helpdesk.models import Comment, Profile, Ticket, TicketHistory
from helpdesk.services import notify as n
from helpdesk.services.assignment import pick_assignee
from helpdesk.services.classifier import classify, detect_priority

S = Ticket.Status


def log(ticket, action, actor=None, auto=False):
    TicketHistory.objects.create(ticket=ticket, action=action, actor=actor, is_auto=auto)


def fmt_dt(dt):
    return timezone.localtime(dt).strftime("%d.%m %H:%M")


def sla_deadline_for(priority, start):
    rule = getattr(priority, "sla", None)
    return start + timedelta(minutes=rule.resolve_minutes) if rule else None


@transaction.atomic
def create_ticket(author, title, description, channel=Ticket.Channel.PORTAL,
                  category=None, priority=None, attachments=()):
    """Создание заявки со всей автоматикой: категория → приоритет → SLA → исполнитель."""
    now = timezone.now()
    result = classify(title, description)
    auto_category = category is None
    category = category or result.category
    auto_priority = priority is None
    priority = priority or detect_priority(category, title, description, author)

    ticket = Ticket.objects.create(
        title=title.strip()[:200], description=description.strip(), channel=channel,
        category=category, priority=priority, author=author,
        classifier_confidence=result.confidence if auto_category else 1.0,
        created_at=now, sla_deadline=sla_deadline_for(priority, now),
    )
    for f in attachments:
        ticket.attachments.create(file=f)

    log(ticket, f"Заявка создана ({ticket.get_channel_display()}).", actor=author)
    if auto_category:
        log(ticket, f"Категория «{category}» определена автоматически "
                    f"(уверенность {round(result.confidence * 100)}%).", auto=True)
    if auto_priority:
        log(ticket, f"Приоритет «{priority}» назначен автоматически.", auto=True)
    if ticket.sla_deadline:
        log(ticket, f"Срок решения по SLA: {fmt_dt(ticket.sla_deadline)}.", auto=True)

    assignee, load = pick_assignee(category)
    if assignee:
        ticket.assignee = assignee
        ticket.status = S.ASSIGNED
        ticket.save(update_fields=["assignee", "status"])
        log(ticket, f"Назначена на {assignee.get_full_name()} — группа «{category.support_group}», "
                    f"наименьшая загрузка ({load} откр. заявок).", auto=True)
    else:
        log(ticket, f"В группе «{category.support_group}» нет специалистов — требуется ручное назначение.", auto=True)

    transaction.on_commit(lambda: _notify_created(ticket))
    return ticket


def _notify_created(ticket):
    deadline = f"\nСрок: до {fmt_dt(ticket.sla_deadline)}" if ticket.sla_deadline else ""
    who = ticket.assignee.get_full_name() if ticket.assignee else "будет назначен"
    n.notify(ticket.author, f"✅ Заявка #{ticket.pk} создана.\nКатегория: {ticket.category}\n"
                            f"Исполнитель: {who}{deadline}")
    if ticket.assignee:
        n.notify(ticket.assignee, f"🆕 Вам назначена заявка #{ticket.pk} ({ticket.priority}):\n"
                                  f"{ticket.title}\n{n.ticket_link(ticket)}")


def add_comment(ticket, author, text, channel=Ticket.Channel.PORTAL):
    text = text.strip()
    if not text:
        return None
    comment = Comment.objects.create(ticket=ticket, author=author, text=text, channel=channel)
    is_it = author != ticket.author

    if is_it and ticket.first_response_at is None:
        ticket.first_response_at = comment.created_at
        ticket.save(update_fields=["first_response_at"])

    if is_it:
        n.notify(ticket.author, f"💬 {author.get_full_name()} по заявке #{ticket.pk}:\n{text}",
                 [n.reply_button(ticket)])
    else:
        # ответ автора возвращает заявку из «ожидания» в работу
        if ticket.status == S.WAITING:
            change_status(ticket, S.IN_PROGRESS, actor=None, auto_reason="получен ответ автора")
        n.notify(ticket.assignee, f"💬 Ответ автора по заявке #{ticket.pk}:\n{text}\n{n.ticket_link(ticket)}")
    return comment


def change_status(ticket, new_status, actor=None, auto_reason=None):
    old = ticket.get_status_display()
    if ticket.status == new_status:
        return ticket
    now = timezone.now()
    ticket.status = new_status
    fields = ["status"]
    if new_status == S.RESOLVED:
        ticket.resolved_at = now
        fields.append("resolved_at")
    if new_status == S.CLOSED:
        ticket.closed_at = now
        fields.append("closed_at")
    if new_status in Ticket.OPEN_STATUSES:
        ticket.resolved_at = None
        ticket.closed_at = None
        fields += ["resolved_at", "closed_at"]
    if actor and actor != ticket.author and ticket.first_response_at is None:
        ticket.first_response_at = now
        fields.append("first_response_at")
    ticket.save(update_fields=fields)

    reason = f" ({auto_reason})" if auto_reason else ""
    log(ticket, f"Статус: «{old}» → «{ticket.get_status_display()}»{reason}.", actor=actor, auto=actor is None)

    if new_status == S.RESOLVED:
        n.notify(ticket.author, f"🎉 Заявка #{ticket.pk} «{ticket.title}» решена.\n"
                                f"Оцените работу или сообщите, если проблема осталась:",
                 n.rating_keyboard(ticket))
    elif new_status == S.WAITING:
        n.notify(ticket.author, f"⏳ По заявке #{ticket.pk} специалисту нужен ваш ответ.", [n.reply_button(ticket)])
    elif actor is not None or new_status == S.CLOSED:
        n.notify(ticket.author, f"ℹ️ Заявка #{ticket.pk}: статус «{ticket.get_status_display()}».")
    return ticket


def reassign(ticket, assignee, actor):
    ticket.assignee = assignee
    if ticket.status == S.NEW:
        ticket.status = S.ASSIGNED
    ticket.save(update_fields=["assignee", "status"])
    log(ticket, f"Исполнитель изменён на {assignee.get_full_name()}.", actor=actor)
    n.notify(assignee, f"🆕 Вам передана заявка #{ticket.pk}: {ticket.title}\n{n.ticket_link(ticket)}")


def rate(ticket, value, actor):
    ticket.rating = max(1, min(5, int(value)))
    ticket.save(update_fields=["rating"])
    log(ticket, f"Автор оценил решение: {ticket.rating} из 5.", actor=actor)
    if ticket.status == S.RESOLVED:
        change_status(ticket, S.CLOSED, actor=actor)


def reopen(ticket, actor, reason=""):
    change_status(ticket, S.IN_PROGRESS, actor=actor)
    if reason:
        add_comment(ticket, actor, reason)
    n.notify(ticket.assignee, f"🔁 Автор вернул заявку #{ticket.pk} в работу.\n{n.ticket_link(ticket)}")


def check_sla(now=None):
    """Периодическая проверка (запускается командой check_sla по расписанию).

    1. Предупреждает исполнителя, когда осталось < 25% времени SLA.
    2. Эскалирует просроченные заявки руководителям ИТ.
    3. Закрывает решённые заявки, которые автор не подтвердил за N дней.
    """
    now = now or timezone.now()
    stats = {"warned": 0, "escalated": 0, "closed": 0}
    managers = list(get_user_model().objects.filter(profile__role=Profile.Role.MANAGER, is_active=True))

    for t in Ticket.objects.filter(status__in=Ticket.OPEN_STATUSES, sla_deadline__isnull=False):
        state = t.sla_state(now)
        if state == "warning" and not t.sla_warned:
            t.sla_warned = True
            t.save(update_fields=["sla_warned"])
            log(t, "До окончания SLA осталось меньше 25% времени. Исполнитель уведомлён.", auto=True)
            n.notify(t.assignee, f"⚠️ Заявка #{t.pk} «{t.title}»: срок SLA истекает в "
                                 f"{fmt_dt(t.sla_deadline)}.\n{n.ticket_link(t)}")
            stats["warned"] += 1
        elif state == "overdue" and not t.escalated:
            t.escalated = True
            t.sla_warned = True
            t.save(update_fields=["escalated", "sla_warned"])
            log(t, "Срок SLA истёк. Заявка эскалирована руководителю ИТ.", auto=True)
            for m in managers:
                n.notify(m, f"🚨 Просрочена заявка #{t.pk} «{t.title}».\n"
                            f"Исполнитель: {t.assignee.get_full_name() if t.assignee else 'не назначен'}\n"
                            f"{n.ticket_link(t)}")
            stats["escalated"] += 1

    limit = now - timedelta(days=settings.AUTO_CLOSE_DAYS)
    for t in Ticket.objects.filter(status=S.RESOLVED, resolved_at__lt=limit):
        change_status(t, S.CLOSED, actor=None,
                      auto_reason=f"автор не ответил {settings.AUTO_CLOSE_DAYS} дн.")
        stats["closed"] += 1
    return stats
