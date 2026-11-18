# Установка ServiceDesk ПМ на сервер

На сервере запускаются пять контейнеров:

| Контейнер | Назначение |
|---|---|
| `web` | сайт (Django и gunicorn); при каждом старте сам применяет миграции БД |
| `db` | PostgreSQL 16, данные хранятся в томе `pgdata` |
| `sla` | контроль SLA раз в минуту |
| `vk_bot`, `max_bot` | боты, включаются по желанию |
| `caddy` | принимает запросы на портах 80 и 443, сам получает и продлевает HTTPS-сертификат |

## 1. Что нужно

- **VPS с Linux** (Ubuntu 22.04 или 24.04): 1 vCPU, 1–2 ГБ RAM, 15 ГБ диска. Подойдёт любой хостинг: Timeweb Cloud, Selectel, REG.RU, Beget и т. п.
- **Домен** (желательно), например `helpdesk.example.ru`. В панели DNS создайте **A-запись** на IP сервера.
  Без домена тоже можно, но тогда сайт будет работать по IP и без HTTPS.

## 2. Установка Docker на сервер

Подключитесь к серверу по SSH (`ssh root@IP_сервера`) и выполните:

```bash
curl -fsSL https://get.docker.com | sh
```

Проверка:

```bash
docker compose version
```

## 3. Загрузка проекта

```bash
git clone https://github.com/DemRexT/diplom_syner.git /opt/servicedesk
```

```bash
cd /opt/servicedesk
```

## 4. Настройка

```bash
cp .env.server.example .env
```

Сгенерируйте два секрета и сохраните их, они понадобятся ниже:

```bash
openssl rand -base64 48
```

```bash
openssl rand -hex 24
```

Откройте настройки в редакторе (`nano .env`; сохранение: Ctrl+O, Enter, выход: Ctrl+X) и заполните:

- `SECRET_KEY`: первая строка;
- `POSTGRES_PASSWORD`: вторая строка;
- `DOMAIN`, `SITE_URL`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`: ваш домен (или IP-адрес, вариант Б в файле);
- `COMPOSE_PROFILES=vk` и `VK_TOKEN`, `VK_GROUP_ID`, если нужен бот ВКонтакте (`vk,max`, если нужны оба бота).

## 5. Запуск

```bash
docker compose up -d --build
```

Первая сборка занимает 2–4 минуты. Проверьте, что всё запустилось:

```bash
docker compose ps
```

У `web` и `db` должно быть написано `healthy`. Откройте в браузере `https://ваш-домен`.

## 6. Первый пользователь

Создайте администратора:

```bash
docker compose exec web python manage.py createsuperuser
```

Войдите в `/admin/`, заведите сотрудников и в профиле каждого укажите роль.
Справочники (категории, приоритеты, SLA) проще всего создать, загрузив демо-данные, а потом удалить
лишние заявки и пользователей. Для демонстрации на защите можно загрузить всё:

```bash
docker compose exec web python manage.py seed_demo
```

## Повседневные команды

| Задача | Команда |
|---|---|
| Посмотреть логи сайта | `docker compose logs -f web` |
| Логи бота | `docker compose logs -f vk_bot` |
| Перезапустить всё | `docker compose restart` |
| Остановить | `docker compose down` (данные сохраняются) |
| Обновить после изменений в GitHub | `git pull && docker compose up -d --build` |
| Резервная копия БД | `docker compose exec db pg_dump -U servicedesk servicedesk > backup_$(date +%F).sql` |
| Восстановить из копии | `docker compose exec -T db psql -U servicedesk servicedesk < backup.sql` |

## Если что-то не работает

- **Сайт не открывается по домену.** Проверьте A-запись DNS (`ping ваш-домен` должен показывать IP сервера)
  и то, что порты 80 и 443 открыты в файрволе хостинга. Ошибки получения сертификата видны в `docker compose logs caddy`.
- **Ошибка 400 Bad Request.** Домен или IP не указан в `ALLOWED_HOSTS`.
- **Ошибка 403 CSRF при входе.** Проверьте `CSRF_TRUSTED_ORIGINS` (с `https://`). Если работаете без HTTPS, поставьте `HTTPS=False`.
- **Бот молчит.** Посмотрите `docker compose logs vk_bot`: там будет причина, например неверный токен.
