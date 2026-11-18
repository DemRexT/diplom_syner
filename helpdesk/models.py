"""Модель данных системы ServiceDesk ПМ."""
import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone


class Department(models.Model):
    name = models.CharField("Название", max_length=120, unique=True)

    class Meta:
        verbose_name = "Отдел"
        verbose_name_plural = "Отделы"
        ordering = ["name"]

    def __str__(self):
        return self.name


class SupportGroup(models.Model):
    """Группа специалистов ИТ-отдела (сеть, рабочие места, серверы...)."""
    name = models.CharField("Название", max_length=120, unique=True)

    class Meta:
        verbose_name = "Группа поддержки"
        verbose_name_plural = "Группы поддержки"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Priority(models.Model):
    name = models.CharField("Название", max_length=50, unique=True)
    level = models.PositiveSmallIntegerField("Уровень (1 — низкий)", unique=True)
    color = models.CharField("Цвет Bootstrap", max_length=20, default="secondary")

    class Meta:
        verbose_name = "Приоритет"
        verbose_name_plural = "Приоритеты"
        ordering = ["level"]

    def __str__(self):
        return self.name


class SLARule(models.Model):
    priority = models.OneToOneField(Priority, on_delete=models.CASCADE, related_name="sla", verbose_name="Приоритет")
    reaction_minutes = models.PositiveIntegerField("Время реакции, мин")
    resolve_minutes = models.PositiveIntegerField("Время решения, мин")

    class Meta:
        verbose_name = "Правило SLA"
        verbose_name_plural = "Правила SLA"

    def __str__(self):
        return f"{self.priority}: решение за {self.resolve_minutes} мин"


class Category(models.Model):
    name = models.CharField("Название", max_length=120, unique=True)
    support_group = models.ForeignKey(SupportGroup, on_delete=models.PROTECT, verbose_name="Группа поддержки")
    default_priority = models.ForeignKey(Priority, on_delete=models.PROTECT, verbose_name="Приоритет по умолчанию")
    keywords = models.TextField(
        "Ключевые слова",
        blank=True,
        help_text="Через запятую. Можно писать начало слова: «принтер», «печат», «vpn».",
    )

    class Meta:
        verbose_name = "Категория"
        verbose_name_plural = "Категории"
        ordering = ["name"]

    def __str__(self):
        return self.name

    def keyword_list(self):
        return [k.strip().lower() for k in self.keywords.split(",") if k.strip()]


class Profile(models.Model):
    class Role(models.TextChoices):
        EMPLOYEE = "employee", "Сотрудник"
        SPECIALIST = "specialist", "Специалист ИТ"
        MANAGER = "manager", "Руководитель ИТ"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    role = models.CharField("Роль", max_length=20, choices=Role.choices, default=Role.EMPLOYEE)
    department = models.ForeignKey(Department, null=True, blank=True, on_delete=models.SET_NULL, verbose_name="Отдел")
    position = models.CharField("Должность", max_length=120, blank=True)
    is_vip = models.BooleanField("Руководитель компании (повышенный приоритет)", default=False)
    support_group = models.ForeignKey(
        SupportGroup, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="specialists", verbose_name="Группа поддержки (для специалистов)",
    )
    vk_id = models.CharField("ID ВКонтакте", max_length=32, blank=True)
    max_id = models.CharField("ID в MAX", max_length=32, blank=True)
    link_code = models.CharField("Код привязки бота", max_length=6, blank=True)

    class Meta:
        verbose_name = "Профиль"
        verbose_name_plural = "Профили"

    def __str__(self):
        return self.user.get_full_name() or self.user.username

    def ensure_link_code(self):
        if not self.link_code:
            self.link_code = f"{secrets.randbelow(900000) + 100000}"
            self.save(update_fields=["link_code"])
        return self.link_code

    @property
    def is_staff_it(self):
        return self.role in (self.Role.SPECIALIST, self.Role.MANAGER)


class Ticket(models.Model):
    class Status(models.TextChoices):
        NEW = "new", "Новая"
        ASSIGNED = "assigned", "Назначена"
        IN_PROGRESS = "in_progress", "В работе"
        WAITING = "waiting", "Ожидает ответа"
        RESOLVED = "resolved", "Решена"
        CLOSED = "closed", "Закрыта"

    OPEN_STATUSES = [Status.NEW, Status.ASSIGNED, Status.IN_PROGRESS, Status.WAITING]

    class Channel(models.TextChoices):
        PORTAL = "portal", "Портал"
        VK = "vk", "ВКонтакте"
        MAX = "max", "MAX"

    title = models.CharField("Тема", max_length=200)
    description = models.TextField("Описание")
    status = models.CharField("Статус", max_length=20, choices=Status.choices, default=Status.NEW)
    channel = models.CharField("Канал", max_length=10, choices=Channel.choices, default=Channel.PORTAL)
    category = models.ForeignKey(Category, on_delete=models.PROTECT, verbose_name="Категория")
    priority = models.ForeignKey(Priority, on_delete=models.PROTECT, verbose_name="Приоритет")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="tickets", verbose_name="Автор")
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="assigned_tickets", verbose_name="Исполнитель",
    )
    classifier_confidence = models.FloatField("Уверенность классификатора", default=0)
    created_at = models.DateTimeField("Создана", default=timezone.now)
    first_response_at = models.DateTimeField("Первая реакция", null=True, blank=True)
    sla_deadline = models.DateTimeField("Срок по SLA", null=True, blank=True)
    resolved_at = models.DateTimeField("Решена", null=True, blank=True)
    closed_at = models.DateTimeField("Закрыта", null=True, blank=True)
    sla_warned = models.BooleanField("Предупреждение SLA отправлено", default=False)
    escalated = models.BooleanField("Эскалирована", default=False)
    rating = models.PositiveSmallIntegerField("Оценка", null=True, blank=True)

    class Meta:
        verbose_name = "Заявка"
        verbose_name_plural = "Заявки"
        ordering = ["-created_at"]

    def __str__(self):
        return f"#{self.pk} {self.title}"

    @property
    def is_open(self):
        return self.status in self.OPEN_STATUSES

    def sla_state(self, now=None):
        """'ok' | 'warning' | 'overdue' | 'done' — для цветовой индикации."""
        if not self.is_open or not self.sla_deadline:
            return "done"
        now = now or timezone.now()
        if now >= self.sla_deadline:
            return "overdue"
        total = (self.sla_deadline - self.created_at).total_seconds() or 1
        left = (self.sla_deadline - now).total_seconds()
        return "warning" if left / total < settings.SLA_WARNING_SHARE else "ok"

    def sla_used_percent(self, now=None):
        if not self.sla_deadline:
            return 0
        now = now or timezone.now()
        end = self.resolved_at or now
        total = (self.sla_deadline - self.created_at).total_seconds() or 1
        return max(0, min(100, round((end - self.created_at).total_seconds() / total * 100)))

    def resolution_minutes(self):
        if self.resolved_at:
            return (self.resolved_at - self.created_at).total_seconds() / 60
        return None


class Comment(models.Model):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    text = models.TextField("Текст")
    channel = models.CharField(max_length=10, choices=Ticket.Channel.choices, default=Ticket.Channel.PORTAL)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["created_at"]
        verbose_name = "Комментарий"
        verbose_name_plural = "Комментарии"


class Attachment(models.Model):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="attachments")
    file = models.FileField("Файл", upload_to="attachments/%Y/%m/")
    uploaded_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = "Вложение"
        verbose_name_plural = "Вложения"

    def filename(self):
        return self.file.name.rsplit("/", 1)[-1]


class TicketHistory(models.Model):
    """Журнал событий заявки. is_auto=True — действие выполнила система."""
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="history")
    action = models.TextField("Событие")
    is_auto = models.BooleanField("Автоматически", default=False)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["created_at"]
        verbose_name = "Событие заявки"
        verbose_name_plural = "История заявок"


class KBArticle(models.Model):
    title = models.CharField("Заголовок", max_length=200)
    category = models.ForeignKey(Category, null=True, blank=True, on_delete=models.SET_NULL, verbose_name="Категория")
    keywords = models.CharField("Ключевые слова", max_length=300, blank=True)
    body = models.TextField("Текст статьи")
    views = models.PositiveIntegerField("Просмотры", default=0)
    helped = models.PositiveIntegerField("Помогла (раз)", default=0)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = "Статья базы знаний"
        verbose_name_plural = "База знаний"
        ordering = ["title"]

    def __str__(self):
        return self.title


class BotSession(models.Model):
    """Состояние диалога пользователя с ботом (хранится в БД, переживает перезапуск)."""
    platform = models.CharField(max_length=10)
    external_id = models.CharField(max_length=32)
    state = models.CharField(max_length=40, default="")
    data = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("platform", "external_id")
        verbose_name = "Сессия бота"
        verbose_name_plural = "Сессии бота"
