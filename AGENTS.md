# Agent notes — events-calendar

Jira DEC = источник событий. Telegram по умолчанию шлётся **напрямую** (`TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID`).

Целевой канал: **Notify Hub**, бот календаря `@dimkava_public_alerts_bot` (канал `public`).  
Контракт: [`../notify-hub/docs/INTEGRATION.md`](../notify-hub/docs/INTEGRATION.md). Боты: [`../notify-hub/docs/CHANNELS.md`](../notify-hub/docs/CHANNELS.md).  
Клиент: `src/dec_calendar/notify_hub_client.py`. Cutover: `NOTIFY_VIA_HUB=true|false`. На Debian-проде сейчас **true**.  
Как внедряли: [`PROMPTS/NOTIFY_HUB.md`](PROMPTS/NOTIFY_HUB.md).  
Пилот: [`../notify-hub/docs/INTEGRATION_DEC.md`](../notify-hub/docs/INTEGRATION_DEC.md).  
Откат: [`docs/NOTIFY_HUB_ROLLBACK.md`](docs/NOTIFY_HUB_ROLLBACK.md), tag `pre-notify-hub`.

Никогда хаб + прямой `sendMessage` на один idem_key.  
Не поднимать `getUpdates` на токене, который поллит хаб.  
Календарь на Windows Server: `127.0.0.1:8080` — это хаб на Debian, с Windows сам не достучится.
