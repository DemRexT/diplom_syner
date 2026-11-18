from django.urls import path

from helpdesk import views

urlpatterns = [
    path("", views.home, name="home"),
    path("tickets/new/", views.ticket_create, name="ticket_create"),
    path("tickets/suggest/", views.suggest, name="suggest"),
    path("tickets/my/", views.my_tickets, name="my_tickets"),
    path("tickets/<int:pk>/", views.ticket_detail, name="ticket_detail"),
    path("queue/", views.queue, name="queue"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("dashboard/export/", views.export_excel, name="export_excel"),
    path("kb/", views.kb_list, name="kb_list"),
    path("kb/<int:pk>/", views.kb_detail, name="kb_detail"),
    path("kb/<int:pk>/helped/", views.kb_helped, name="kb_helped"),
    path("profile/", views.profile_view, name="profile"),
]
