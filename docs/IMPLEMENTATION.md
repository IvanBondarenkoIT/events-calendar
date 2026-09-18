# Implementation status (v0.1)

См. канон: [STRATEGY.md](STRATEGY.md).

## Сделано (актуально)

- Пакет `src/dec_calendar`: config, models (status), Jira/Telegram, reminders + workflow nags, idempotency
- Окна: T−30/T−15; nags 10:00/22:00 пока To Do (с T−30); finish 10:00 с T−5 пока не Done
- CLI: `check-config`, `check-jira`, `preview-import`, `import-events [--replace]`, `import-extra`, `run-once --slot morning|evening|auto`
- Notify Hub client + `NOTIFY_VIA_HUB` (default false = прямой Telegram)
- Docs: STRATEGY, JIRA_DEC_SETUP, NOTIFY_HUB_ROLLBACK (tag `pre-notify-hub`)
- Пилоты и хронологический импорт
- Docs: STRATEGY, JIRA_DEC_SETUP (колонка **В работе**), README schedule

## Нужно от человека

1. В DEC добавить колонку **В работе** (In Progress) — сейчас только «К выполнению» / «Готово».
2. Повесить Task Scheduler: 10:00 и 22:00 → `run-once --slot morning|evening`.

## Команды (из корня репо)

```powershell
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH = "src"
pytest -q
python -m dec_calendar preview-import --today 2026-08-21
```
