from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.db import connection
from django.http import HttpResponse
from django.urls import include, path


def healthz(request):
    """Проверка работоспособности для Docker и мониторинга."""
    connection.ensure_connection()
    return HttpResponse("ok", content_type="text/plain")


urlpatterns = [
    path("healthz/", healthz),
    path("admin/", admin.site.urls),
    path("login/", auth_views.LoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("", include("helpdesk.urls")),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
