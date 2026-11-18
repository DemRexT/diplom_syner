from django import template
from django.utils import timezone
from django.utils.html import format_html

register = template.Library()

STATUS_COLORS = {
    "new": "secondary", "assigned": "info", "in_progress": "primary",
    "waiting": "warning", "resolved": "success", "closed": "dark",
}


@register.filter
def status_badge(t):
    return format_html('<span class="badge text-bg-{}">{}</span>', STATUS_COLORS.get(t.status, "secondary"),
                       t.get_status_display())


@register.filter
def priority_badge(t):
    return format_html('<span class="badge text-bg-{}">{}</span>', t.priority.color, t.priority.name)


def _fmt_delta(seconds):
    seconds = abs(int(seconds))
    d, rem = divmod(seconds, 86400)
    h, rem = divmod(rem, 3600)
    m = rem // 60
    if d:
        return f"{d} д {h} ч"
    return f"{h}:{m:02d}"


@register.filter
def sla_badge(t):
    state = t.sla_state()
    if state == "done" or not t.sla_deadline:
        return format_html('<span class="text-body-secondary">—</span>')
    left = (t.sla_deadline - timezone.now()).total_seconds()
    color = {"ok": "success", "warning": "warning", "overdue": "danger"}[state]
    sign = "−" if left < 0 else ""
    return format_html('<span class="badge rounded-pill text-bg-{}" title="Срок: {}">{}{}</span>',
                       color, timezone.localtime(t.sla_deadline).strftime("%d.%m %H:%M"), sign, _fmt_delta(left))


@register.filter
def minutes_human(value):
    if value is None:
        return "—"
    value = int(value)
    h, m = divmod(value, 60)
    return f"{h} ч {m} мин" if h else f"{m} мин"
