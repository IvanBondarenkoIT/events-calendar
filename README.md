# DimKava Event Calendar (DEC)

[![CI](https://github.com/IvanBondarenkoIT/events-calendar/actions/workflows/ci.yml/badge.svg)](https://github.com/IvanBondarenkoIT/events-calendar/actions/workflows/ci.yml)

Jira — единый источник правды (project **`DEC`**).  
Telegram — только оповещения (`@prices_monitoring_alerts_bot`, токен/чат из env).

- Стратегия: [`docs/STRATEGY.md`](docs/STRATEGY.md)
- Jira setup: [`docs/JIRA_DEC_SETUP.md`](docs/JIRA_DEC_SETUP.md)
- **Прод на Windows Server + Docker:** [`docs/WINDOWS_SERVER_DEPLOY.md`](docs/WINDOWS_SERVER_DEPLOY.md)

Образ: `ghcr.io/ivanbondarenkoit/events-calendar:latest` (publish на push в `main`).

## Возможности

| Контур | Окна | Куда |
|--------|------|------|
| Праздники / промо | T−30, T−15 (разово) | Telegram + comment |
| Праздники / промо | пока в «К выполнению», с T−30: **10:00 и 22:00** | «переведите в В работе» |
| Праздники / промо | с T−5, пока не Готово: **10:00** | «доведите до Готово» |
| Дни рождения | T−1, T−0 | тот же чат |

Пилот: **01.09.2026** «Начало осени»; **15.09.2026** «Начало учебного года».

Workflow: **К выполнению → В работе → Готово** (см. [`docs/JIRA_DEC_SETUP.md`](docs/JIRA_DEC_SETUP.md)).

## Setup

```powershell
cd D:\CursorProjects\events-calendar
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
# заполните JIRA_* и TELEGRAM_* в .env
```

`PYTHONPATH` должен включать `src` (команды ниже делают это через `-m`).

```powershell
$env:PYTHONPATH = "src"
python -m dec_calendar check-config
```

## Команды

```powershell
$env:PYTHONPATH = "src"

# Парсинг Excel + ДР без Jira
python -m dec_calendar preview-import --today 2026-08-21

# Проверка, что project DEC существует и токен валиден
python -m dec_calendar check-jira

# Импорт в Jira (идемпотентно по summary)
python -m dec_calendar import-events --dry-run
python -m dec_calendar import-events
python -m dec_calendar import-events --replace   # удалить все и залить по дате

# Job напоминаний (слоты 10:00 / 22:00 Asia/Tbilisi)
python -m dec_calendar run-once --dry-run --slot morning --today 2026-08-27
python -m dec_calendar run-once --slot morning
python -m dec_calendar run-once --slot evening
python -m dec_calendar run-once --slot auto
```

Смена бота/чата — только `TELEGRAM_BOT_TOKEN` и `TELEGRAM_CHAT_ID` в `.env`.

## Расписание (рекомендация)

Два задания Task Scheduler / cron в `Asia/Tbilisi`:

| Время | Команда |
|-------|---------|
| 10:00 | `python -m dec_calendar run-once --slot morning` |
| 22:00 | `python -m dec_calendar run-once --slot evening` |

## Перед первым импортом

1. Project **`DEC`** + колонка **В работе** (In Progress) — [`docs/JIRA_DEC_SETUP.md`](docs/JIRA_DEC_SETUP.md).
2. Тип задачи `JIRA_ISSUE_TYPE` (по умолчанию `Task`) + поля **Due date** и **Labels**.
3. Labels: `calendar-holiday`, `calendar-promo`, `calendar-birthday`, `needs-date`, `pilot-test`.

## Production (Windows Server + Docker)

См. полную инструкцию: [`docs/WINDOWS_SERVER_DEPLOY.md`](docs/WINDOWS_SERVER_DEPLOY.md).

Кратко: образ GHCR + Task Scheduler 10:00/22:00 вызывает `deploy/scripts/run-slot.ps1`.

```powershell
# на сервере после копирования scripts и .env
.\scripts\first-deploy.ps1 -DeployDir C:\events-calendar
.\scripts\install-scheduled-tasks.ps1 -DeployDir C:\events-calendar
```

## Тесты

```powershell
$env:PYTHONPATH = "src"
pytest -q
```

## Добавить событие вручную

В Jira DEC создайте Task:

- Summary: `[Праздник] …` / `[Промо] …` / `[ДР] …`
- Due date = дата события
- Label: ровно один из `calendar-holiday` | `calendar-promo` | `calendar-birthday`
- Для праздников — чеклист подготовки в Description

Правки дат и текстов — **только в Jira**. Excel больше не SSOT после импорта.
