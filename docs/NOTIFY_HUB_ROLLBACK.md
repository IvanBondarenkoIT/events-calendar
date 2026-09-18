# Откат Notify Hub → прямой Telegram

Календарь **до cutover** шлёт алерты сам: `job.py` → `TelegramClient.send_message` (`TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID`). Long-poll `getUpdates` нет.

Целевой бот хаба: [`@dimkava_public_alerts_bot`](https://t.me/dimkava_public_alerts_bot) (канал `public`).  
Контракт хаба: [`../notify-hub/docs/INTEGRATION.md`](../../notify-hub/docs/INTEGRATION.md).  
Пилот DEC: [`../notify-hub/docs/INTEGRATION_DEC.md`](../../notify-hub/docs/INTEGRATION_DEC.md).

## Baseline (зафиксировано перед кодом хаба)

| Что | Значение |
|-----|----------|
| Git tag | `pre-notify-hub` (`aac8f23`) |
| Ветка-копия | `backup/direct-telegram` |
| origin/main на момент freeze | `17c9296` (`Fix first-deploy.ps1 quoting…`) |
| Прод-путь алертов | прямой Telegram, один `TELEGRAM_CHAT_ID` |
| Подписки | нет (не в этом репо) |

На теге есть extra-events (`import-extra`), чеклист, `jira_client.update_issue_fields`. Клиента `notify_hub_client.py` ещё нет.

Проверить тег:

```powershell
git show pre-notify-hub --stat
git log -1 --oneline pre-notify-hub
```

## Мягкий откат (после внедрения хаба)

Не откатывает git. Job снова шлёт только `sendMessage`.

1. В `.env` на хосте календаря: `NOTIFY_VIA_HUB=false`
2. Redeploy / следующий `run-once` (cron или Task Scheduler)
3. Убедиться, что **не** осталось `NOTIFY_VIA_HUB=true` на другом хосте (Debian `~/apps/events-calendar` и Windows `C:\Projects\events-calendar`)

Прямой `sendMessage` на токене хаба допустим, пока миграция не завершена. Второй `getUpdates` на том же токене — нет.

## Жёсткий откат

Вернуть код без хаб-клиента:

```powershell
cd D:\CursorProjects\events-calendar
git checkout pre-notify-hub
# либо: git checkout backup/direct-telegram
```

Затем redeploy образа/файлов на сервер (хаб `07-deploy-events-calendar.py` или Windows `update.ps1`).

После жёсткого отката переменные `NOTIFY_HUB_*` не используются.

## Запрещено

- Одновременно `NOTIFY_VIA_HUB=true` и прямой `sendMessage` на тот же `idem_key`
- Второй long-poller `getUpdates` на токене, который поллит notify-hub
- `NOTIFY_HUB_URL=http://127.0.0.1:8080` с **Windows**, если хаб на Debian
