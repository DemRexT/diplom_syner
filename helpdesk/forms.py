from django import forms
from django.contrib.auth import get_user_model

from helpdesk.models import Category, Priority, Profile, Ticket


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput())
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        single = super().clean
        if isinstance(data, (list, tuple)):
            return [single(d, initial) for d in data]
        return [single(data, initial)] if data else []


class TicketForm(forms.Form):
    title = forms.CharField(label="Тема", max_length=200,
                            widget=forms.TextInput(attrs={"placeholder": "Кратко: что не работает", "autocomplete": "off"}))
    description = forms.CharField(label="Описание", widget=forms.Textarea(attrs={"rows": 5,
                                  "placeholder": "Подробности: где, когда началось, текст ошибки"}))
    category = forms.ModelChoiceField(label="Категория", queryset=Category.objects.all(), required=False,
                                      empty_label="Определить автоматически")
    priority = forms.ModelChoiceField(label="Приоритет", queryset=Priority.objects.all(), required=False,
                                      empty_label="Определить автоматически")
    files = MultipleFileField(label="Вложения", required=False)


class CommentForm(forms.Form):
    text = forms.CharField(label="", widget=forms.Textarea(attrs={"rows": 3, "placeholder": "Написать ответ…"}))


class StatusForm(forms.Form):
    status = forms.ChoiceField(label="Статус", choices=Ticket.Status.choices)


class UserChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, user):
        group = user.profile.support_group
        return f"{user.get_full_name()} ({group})" if group else user.get_full_name()


class AssignForm(forms.Form):
    assignee = UserChoiceField(
        label="Исполнитель",
        queryset=get_user_model().objects.filter(profile__role=Profile.Role.SPECIALIST, is_active=True),
    )
