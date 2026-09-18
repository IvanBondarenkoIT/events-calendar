# Windows Server deploy — DimKava Event Calendar (DEC)

Production model (как **dimkava-big-book** Docker/GHCR + **prices-monitoring** Task Scheduler):

- Образ: `ghcr.io/ivanbondarenkoit/events-calendar:latest`
- Не always-on web: два раза в сутки `docker run --rm` в **10:00** и **22:00** `Asia/Tbilisi`
- Секреты только в `.env` на сервере (не в git)

Репозиторий: https://github.com/IvanBondarenkoIT/events-calendar

---

## 0. Требования на сервере

1. Windows Server / Windows 10+ с **Docker Desktop** (Linux containers) или Docker Engine.
2. Часовой пояс хоста **`(UTC+04:00) Tbilisi`** — иначе поправьте время задач в `install-scheduled-tasks.ps1`.
3. Доступ в интернет к `ghcr.io`, `dimkavageorgia.atlassian.net`, `api.telegram.org`.
4. GitHub account с правом читать package (public package или PAT `read:packages`).

---

## 1. Каталог на сервере

Рекомендуемый layout:

```text
C:\Projects\events-calendar\
  .env                 # секреты (создать из .env.example)
  data\                # volume: alert_state.json
  logs\                # логи run-slot
  docker-compose.prod.yml
  .env.example
  scripts\             # копия deploy/scripts/*.ps1
    run-slot.ps1
    install-scheduled-tasks.ps1
    first-deploy.ps1
    update.ps1
```

С рабочей машины (после клона репо):

```powershell
$dst = "C:\Projects\events-calendar"   # или \\SERVER\c$\events-calendar
New-Item -ItemType Directory -Force -Path $dst, "$dst\data", "$dst\logs", "$dst\scripts" | Out-Null
Copy-Item docker-compose.prod.yml, .env.example $dst -Force
Copy-Item deploy\scripts\*.ps1 $dst\scripts -Force
```

---

## 2. Секреты `.env`

```powershell
cd C:\Projects\events-calendar
Copy-Item .env.example .env
notepad .env
```

Обязательно заполнить:

| Переменная | Значение |
|------------|----------|
| `JIRA_EMAIL` | email Atlassian |
| `JIRA_API_TOKEN` | API token |
| `JIRA_PROJECT_KEY` | `DEC` |
| `TELEGRAM_BOT_TOKEN` | токен бота |
| `TELEGRAM_CHAT_ID` | chat id (seed для хаба на переход) |
| `NOTIFY_VIA_HUB` | `false` = прямой Telegram; `true` = только Notify Hub |
| `NOTIFY_HUB_URL` | URL хаба (с Debian: `http://127.0.0.1:8080`; с Windows — не localhost) |
| `NOTIFY_HUB_API_KEY` | ключ из `SERVICE_API_KEYS` хаба |
| `IDEMPOTENCY_PATH` | `/app/data/alert_state.json` |
| `JIRA_SSL_VERIFY` | `true` на чистом сервере; `false` при SSL MITM |

---

## 3. Первый деплой (pull образа)

Package на GHCR появляется после первого успешного workflow **Docker publish** на `main`.

Если package **private**: Settings → Packages → Package settings → Add user/token; на сервере:

```powershell
# GitHub → Settings → Developer settings → PAT: read:packages
echo YOUR_PAT | docker login ghcr.io -u YOUR_GITHUB_USER --password-stdin
```

Если **public**: можно pull без login (или login всё равно).

```powershell
cd C:\Projects\events-calendar
powershell -ExecutionPolicy Bypass -File .\scripts\first-deploy.ps1 -DeployDir C:\Projects\events-calendar
```

Скрипт: `docker pull`, smoke `check-config` и `check-jira`.

Ручной smoke:

```powershell
docker pull ghcr.io/ivanbondarenkoit/events-calendar:latest

docker run --rm --env-file C:\Projects\events-calendar\.env `
  -e TZ=Asia/Tbilisi -e PYTHONPATH=/app/src `
  -v C:\Projects\events-calendar\data:/app/data `
  ghcr.io/ivanbondarenkoit/events-calendar:latest `
  python -m dec_calendar check-jira
```

---

## 4. Расписание (Task Scheduler)

От **Administrator**:

```powershell
powershell -ExecutionPolicy Bypass -File C:\Projects\events-calendar\scripts\install-scheduled-tasks.ps1 `
  -DeployDir C:\Projects\events-calendar `
  -MorningAt "10:00" `
  -EveningAt "22:00"
```

Создаёт задачи:

| Task | Время | Slot |
|------|-------|------|
| `DecCalendarMorning` | 10:00 | morning |
| `DecCalendarEvening` | 22:00 | evening |

Проверка вручную:

```powershell
powershell -ExecutionPolicy Bypass -File C:\Projects\events-calendar\scripts\run-slot.ps1 -Slot morning -DeployDir C:\Projects\events-calendar
```

Логи: `C:\Projects\events-calendar\logs\dec-morning-*.log`

---

## 5. Обновление после CI

После push в `main` CI гоняет pytest; Docker publish кладёт новый `:latest` в GHCR.

На сервере:

```powershell
powershell -ExecutionPolicy Bypass -File C:\Projects\events-calendar\scripts\update.ps1 -DeployDir C:\Projects\events-calendar
```

Следующий scheduled run подхватит новый образ.

---

## 6. Troubleshooting

| Симптом | Действие |
|---------|----------|
| `unauthorized` GHCR | `docker login ghcr.io` + package visibility / PAT |
| SSL to Jira | `JIRA_SSL_VERIFY=false` в `.env` |
| Нет алертов | Проверить Task Scheduler History; логи `logs\`; `DRY_RUN=false` |
| Дубли алертов | Не удаляйте `data\alert_state.json` без нужды |
| Неверное время | TZ хоста → Tbilisi или сдвиньте `-MorningAt`/`-EveningAt` |

---

## 7. Чеклист «сделать на сервере»

1. Установить Docker Desktop (Linux containers).  
2. Выставить TZ **Tbilisi**.  
3. Создать `C:\Projects\events-calendar\` и скопировать `.env.example`, `docker-compose.prod.yml`, `scripts\*.ps1`.  
4. Заполнить `.env` (Jira + Telegram).  
5. Дождаться первого GHCR image после push `main` (или собрать локально и tag/push).  
6. `docker login ghcr.io` при необходимости.  
7. Запустить `first-deploy.ps1`.  
8. Установить scheduled tasks 10:00 / 22:00.  
9. Один раз вручную `run-slot.ps1 -Slot morning` и проверить Telegram / логи.  
10. В Jira DEC должна быть колонка **В работе** (см. [JIRA_DEC_SETUP.md](JIRA_DEC_SETUP.md)).
