# Agent notes — events-calendar

Jira DEC = источник событий. Telegram сегодня шлётся **напрямую** (`TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID`).

Целевой канал: **Notify Hub**. Контракт: [`../notify-hub/docs/INTEGRATION.md`](../notify-hub/docs/INTEGRATION.md).  
Как внедрять доставку: [`PROMPTS/NOTIFY_HUB.md`](PROMPTS/NOTIFY_HUB.md).  
DEC-пилот: [`../notify-hub/docs/INTEGRATION_DEC.md`](../notify-hub/docs/INTEGRATION_DEC.md).

Пока миграция не сделана: не дублировать хаб + прямой `sendMessage`.  
Не поднимать `getUpdates` на токене, который поллит хаб.  
Календарь на Windows Server: `127.0.0.1:8080` — это хаб на Debian, с Windows сам не достучится.
