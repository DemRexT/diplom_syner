from datetime import timedelta
from io import BytesIO

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.validators import validate_email
from django.db.models import Avg, Count, F, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from helpdesk.forms import AssignForm, CommentForm, StatusForm, TicketForm
from helpdesk.models import Category, KBArticle, Profile, Ticket
from helpdesk.services import kb, tickets
from helpdesk.services.assignment import workload
from helpdesk.services.classifier import classify, detect_priority

R = Profile.Role


def _profile(request):
    return request.user.profile


def it_required(view):
    def wrapper(request, *args, **kwargs):
        if not _profile(request).is_staff_it:
            raise PermissionDenied
        return view(request, *args, **kwargs)
    return login_required(wrapper)


def manager_required(view):
    def wrapper(request, *args, **kwargs):
        if _profile(request).role != R.MANAGER:
            raise PermissionDenied
        return view(request, *args, **kwargs)
    return login_required(wrapper)


@login_required
def home(request):
    role = _profile(request).role
    if role == R.MANAGER:
        return redirect("dashboard")
    if role == R.SPECIALIST:
        return redirect("queue")
    return redirect("my_tickets")


# --- Сотрудник -------------------------------------------------------------

@login_required
def ticket_create(request):
    form = TicketForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        ticket = tickets.create_ticket(
            request.user, d["title"], d["description"],
            category=d["category"], priority=d["priority"], attachments=d["files"],
        )
        messages.success(request, f"Заявка #{ticket.pk} создана и назначена"
                                  + (f" на {ticket.assignee.get_full_name()}." if ticket.assignee else "."))
        return redirect("ticket_detail", pk=ticket.pk)
    return render(request, "helpdesk/ticket_create.html", {"form": form})


@login_required
def suggest(request):
    """AJAX: подсказки БЗ и предварительная классификация, пока пользователь печатает."""
    title, desc = request.GET.get("title", ""), request.GET.get("description", "")
    text = f"{title} {desc}".strip()
    if len(text) < 4:
        return JsonResponse({"articles": [], "category": None})
    result = classify(title, desc)
    priority = detect_priority(result.category, title, desc, request.user)
    sla = getattr(priority, "sla", None)
    deadline = timezone.localtime(timezone.now() + timedelta(minutes=sla.resolve_minutes)) if sla else None
    return JsonResponse({
        "articles": [{"id": a.pk, "title": a.title} for a in kb.suggest(text)],
        "category": result.category.name if result.confidence else None,
        "confidence": round(result.confidence * 100),
        "priority": priority.name,
        "deadline": deadline.strftime("%d.%m %H:%M") if deadline else None,
    })


@login_required
def my_tickets(request):
    qs = Ticket.objects.filter(author=request.user).select_related("category", "priority", "assignee")
    return render(request, "helpdesk/my_tickets.html", {"tickets": qs})


# --- Карточка заявки -------------------------------------------------------

@login_required
def ticket_detail(request, pk):
    ticket = get_object_or_404(Ticket.objects.select_related("category", "priority", "author", "assignee"), pk=pk)
    profile = _profile(request)
    is_author = ticket.author_id == request.user.id
    if not (is_author or profile.is_staff_it):
        raise PermissionDenied

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "comment":
            form = CommentForm(request.POST)
            if form.is_valid():
                tickets.add_comment(ticket, request.user, form.cleaned_data["text"])
                if profile.is_staff_it and ticket.status == Ticket.Status.ASSIGNED:
                    tickets.change_status(ticket, Ticket.Status.IN_PROGRESS, actor=request.user)
        elif action == "status" and profile.is_staff_it:
            form = StatusForm(request.POST)
            if form.is_valid():
                tickets.change_status(ticket, form.cleaned_data["status"], actor=request.user)
        elif action == "take" and profile.is_staff_it:
            tickets.reassign(ticket, request.user, actor=request.user)
            tickets.change_status(ticket, Ticket.Status.IN_PROGRESS, actor=request.user)
        elif action == "assign" and profile.role == R.MANAGER:
            form = AssignForm(request.POST)
            if form.is_valid():
                tickets.reassign(ticket, form.cleaned_data["assignee"], actor=request.user)
        elif action == "rate" and is_author and ticket.status == Ticket.Status.RESOLVED:
            tickets.rate(ticket, request.POST.get("rating", 5), request.user)
        elif action == "reopen" and is_author and ticket.status in (Ticket.Status.RESOLVED, Ticket.Status.CLOSED):
            tickets.reopen(ticket, request.user, request.POST.get("reason", ""))
        return redirect("ticket_detail", pk=pk)

    events = sorted(
        [("h", h.created_at, h) for h in ticket.history.select_related("actor")]
        + [("c", c.created_at, c) for c in ticket.comments.select_related("author")],
        key=lambda e: e[1],
    )
    return render(request, "helpdesk/ticket_detail.html", {
        "t": ticket, "events": events, "is_author": is_author,
        "comment_form": CommentForm(),
        "status_form": StatusForm(initial={"status": ticket.status}),
        "assign_form": AssignForm(initial={"assignee": ticket.assignee_id}),
    })


# --- Специалист ------------------------------------------------------------

@it_required
def queue(request):
    profile = _profile(request)
    scope = request.GET.get("scope", "mine" if profile.role == R.SPECIALIST else "all")
    status = request.GET.get("status", "open")
    category = request.GET.get("category", "")

    qs = Ticket.objects.select_related("category", "priority", "author", "assignee")
    if scope == "mine":
        qs = qs.filter(assignee=request.user)
    elif scope == "group" and profile.support_group_id:
        qs = qs.filter(category__support_group=profile.support_group)
    elif scope == "unassigned":
        qs = qs.filter(assignee__isnull=True)
    if status == "open":
        qs = qs.filter(status__in=Ticket.OPEN_STATUSES)
    elif status:
        qs = qs.filter(status=status)
    if category:
        qs = qs.filter(category_id=category)

    # просроченные и срочные сверху
    qs = qs.order_by(F("sla_deadline").asc(nulls_last=True)) if status == "open" else qs.order_by("-created_at")

    return render(request, "helpdesk/queue.html", {
        "tickets": qs[:200], "scope": scope, "status": status, "category": category,
        "categories": Category.objects.all(), "statuses": Ticket.Status.choices,
    })


# --- Руководитель ----------------------------------------------------------

def _period(request):
    days = int(request.GET.get("days", 30) or 30)
    since = timezone.now() - timedelta(days=days)
    return days, since


def _stats(since):
    qs = Ticket.objects.filter(created_at__gte=since)
    total = qs.count()
    resolved = qs.filter(resolved_at__isnull=False)
    avg_minutes = None
    if resolved.exists():
        durations = [(t.resolved_at - t.created_at).total_seconds() / 60 for t in resolved.only("created_at", "resolved_at")]
        avg_minutes = sum(durations) / len(durations)
    with_sla = resolved.filter(sla_deadline__isnull=False)
    in_sla = with_sla.filter(resolved_at__lte=F("sla_deadline")).count()
    sla_pct = round(in_sla / with_sla.count() * 100) if with_sla.exists() else None
    return {
        "total": total,
        "open": qs.filter(status__in=Ticket.OPEN_STATUSES).count(),
        "overdue": Ticket.objects.filter(status__in=Ticket.OPEN_STATUSES, sla_deadline__lt=timezone.now()).count(),
        "avg_minutes": avg_minutes,
        "sla_pct": sla_pct,
        "rating": qs.aggregate(r=Avg("rating"))["r"],
        "kb_helped": sum(KBArticle.objects.values_list("helped", flat=True)),
        "by_category": list(qs.values("category__name").annotate(c=Count("id")).order_by("-c")),
        "by_channel": list(qs.values("channel").annotate(c=Count("id")).order_by("-c")),
        "auto_accuracy": qs.filter(classifier_confidence__gte=0.6).count(),
    }


@manager_required
def dashboard(request):
    days, since = _period(request)
    stats = _stats(since)
    # динамика по дням
    by_day = {}
    for t in Ticket.objects.filter(created_at__gte=since).only("created_at"):
        d = timezone.localtime(t.created_at).date()
        by_day[d] = by_day.get(d, 0) + 1
    start = timezone.localtime(since).date()
    days_list = [start + timedelta(days=i) for i in range(days + 1)]
    channel_names = dict(Ticket.Channel.choices)
    return render(request, "helpdesk/dashboard.html", {
        "days": days, "s": stats,
        "load": workload(),
        "chart": {
            "cat_labels": [r["category__name"] for r in stats["by_category"]],
            "cat_values": [r["c"] for r in stats["by_category"]],
            "day_labels": [d.strftime("%d.%m") for d in days_list],
            "day_values": [by_day.get(d, 0) for d in days_list],
            "ch_labels": [channel_names.get(r["channel"], r["channel"]) for r in stats["by_channel"]],
            "ch_values": [r["c"] for r in stats["by_channel"]],
        },
    })


@manager_required
def export_excel(request):
    from openpyxl import Workbook
    from openpyxl.styles import Font

    days, since = _period(request)
    wb = Workbook()
    ws = wb.active
    ws.title = "Заявки"
    head = ["№", "Тема", "Категория", "Приоритет", "Статус", "Канал", "Автор", "Исполнитель",
            "Создана", "Решена", "Срок SLA", "SLA соблюдён", "Время решения, мин", "Оценка"]
    ws.append(head)
    for cell in ws[1]:
        cell.font = Font(bold=True)
    qs = Ticket.objects.filter(created_at__gte=since).select_related("category", "priority", "author", "assignee")
    loc = timezone.localtime
    for t in qs.order_by("created_at"):
        minutes = t.resolution_minutes()
        ws.append([
            t.pk, t.title, t.category.name, t.priority.name, t.get_status_display(), t.get_channel_display(),
            t.author.get_full_name(), t.assignee.get_full_name() if t.assignee else "",
            loc(t.created_at).replace(tzinfo=None), loc(t.resolved_at).replace(tzinfo=None) if t.resolved_at else None,
            loc(t.sla_deadline).replace(tzinfo=None) if t.sla_deadline else None,
            ("да" if t.resolved_at <= t.sla_deadline else "нет") if t.resolved_at and t.sla_deadline else "",
            round(minutes) if minutes else None, t.rating,
        ])
    for col, width in zip("ABCDEFGHIJKLMN", [6, 45, 18, 12, 15, 11, 22, 22, 17, 17, 17, 12, 12, 8]):
        ws.column_dimensions[col].width = width
    for row in ws.iter_rows(min_row=2, min_col=9, max_col=11):
        for c in row:
            c.number_format = "DD.MM.YYYY HH:MM"

    s = _stats(since)
    ws2 = wb.create_sheet("Сводка")
    for row in [
        ("Период, дней", days), ("Всего заявок", s["total"]), ("Открыто", s["open"]),
        ("Просрочено сейчас", s["overdue"]),
        ("Среднее время решения, мин", round(s["avg_minutes"]) if s["avg_minutes"] else "—"),
        ("Соблюдение SLA, %", s["sla_pct"] if s["sla_pct"] is not None else "—"),
        ("Средняя оценка", round(s["rating"], 2) if s["rating"] else "—"),
        ("Решено через базу знаний", s["kb_helped"]),
    ]:
        ws2.append(row)
    ws2.column_dimensions["A"].width = 32

    buf = BytesIO()
    wb.save(buf)
    resp = HttpResponse(buf.getvalue(),
                        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    resp["Content-Disposition"] = f'attachment; filename="servicedesk_report_{days}d.xlsx"'
    return resp


# --- База знаний и профиль -------------------------------------------------

@login_required
def kb_list(request):
    q = request.GET.get("q", "").strip()
    articles = kb.suggest(q, limit=20) if q else KBArticle.objects.select_related("category").order_by(
        "category__name", "title")
    return render(request, "helpdesk/kb_list.html", {"articles": articles, "q": q})


@login_required
def kb_detail(request, pk):
    article = get_object_or_404(KBArticle, pk=pk)
    KBArticle.objects.filter(pk=pk).update(views=F("views") + 1)
    return render(request, "helpdesk/kb_detail.html", {"a": article})


@require_POST
@login_required
def kb_helped(request, pk):
    KBArticle.objects.filter(pk=pk).update(helped=F("helped") + 1)
    messages.success(request, "Отлично, что статья помогла! Заявку создавать не нужно.")
    return redirect("my_tickets")


@login_required
def profile_view(request):
    profile = _profile(request)
    if request.method == "POST":
        if request.POST.get("action") == "unlink_vk":
            profile.vk_id = ""
        elif request.POST.get("action") == "unlink_max":
            profile.max_id = ""
        elif request.POST.get("action") == "new_code":
            profile.link_code = ""
        elif request.POST.get("action") == "email":
            email = request.POST.get("email", "").strip()
            try:
                validate_email(email) if email else None
            except ValidationError:
                messages.error(request, "Похоже, в адресе почты ошибка. Проверьте и сохраните ещё раз.")
                return redirect("profile")
            request.user.email = email
            request.user.save(update_fields=["email"])
            profile.notify_email = bool(request.POST.get("notify_email"))
            messages.success(request, "Настройки почты сохранены.")
        profile.save()
        return redirect("profile")
    profile.ensure_link_code()
    return render(request, "helpdesk/profile.html", {"p": profile})
