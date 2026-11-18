from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User

from helpdesk import models as m


class ProfileInline(admin.StackedInline):
    model = m.Profile
    can_delete = False
    verbose_name_plural = "Профиль ServiceDesk"


admin.site.unregister(User)


@admin.register(User)
class UserWithProfileAdmin(UserAdmin):
    inlines = [ProfileInline]
    list_display = ("username", "last_name", "first_name", "email", "get_role")

    @admin.display(description="Роль")
    def get_role(self, obj):
        return obj.profile.get_role_display() if hasattr(obj, "profile") else "—"


class CommentInline(admin.TabularInline):
    model = m.Comment
    extra = 0


class HistoryInline(admin.TabularInline):
    model = m.TicketHistory
    extra = 0
    readonly_fields = ("created_at", "action", "is_auto", "actor")


@admin.register(m.Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "status", "category", "priority", "author", "assignee", "created_at", "escalated")
    list_filter = ("status", "category", "priority", "channel", "escalated")
    search_fields = ("title", "description")
    inlines = [CommentInline, HistoryInline]


@admin.register(m.Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "support_group", "default_priority")


@admin.register(m.KBArticle)
class KBArticleAdmin(admin.ModelAdmin):
    list_display = ("title", "category", "views", "helped")
    search_fields = ("title", "keywords", "body")


admin.site.register([m.Department, m.SupportGroup, m.Priority, m.SLARule, m.BotSession])
admin.site.site_header = "ServiceDesk ПМ — администрирование"
