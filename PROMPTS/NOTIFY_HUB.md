# Промпт: подключить events-calendar к Notify Hub

**Состояние (18.09.2026):** хаб на проде. DEC на Debian шлёт в хаб (`NOTIFY_VIA_HUB=true`), канал **public**, бот `@dimkava_public_alerts_bot`. Direct Telegram не вызывается. Откат: `NOTIFY_VIA_HUB=false` или tag `pre-notify-hub`.

Контракт: `D:\CursorProjects\notify-hub\docs\INTEGRATION.md`  
Боты: `D:\CursorProjects\notify-hub\docs\CHANNELS.md`  
DEC: `D:\CursorProjects\notify-hub\docs\INTEGRATION_DEC.md`  
Откат: `docs/NOTIFY_HUB_ROLLBACK.md`

## Что есть сегодня

- Один исходящий вызов: `TelegramClient.send_message()` из `src/dec_calendar/job.py` (~строка 102).
- Текст уже готов: `format_alert_message()` в `messages.py`.
- Идемпотентность: `reminders.idempotency_key()` + JSON `IdempotencyStore`.
- `getUpdates` **нет** — только `sendMessage`. Не добавлять long-poller.

Ключ сейчас:

```text
{issue_key}|{window}|{due}           # one-shot, напр. DEC-42|t_minus_15|2026-09-15
{issue_key}|{window}|{due}|{today}   # nag_*
```

## Что сделать

1. Клиент `src/dec_calendar/notify_hub_client.py`: `POST {NOTIFY_HUB_URL}/v1/events` с `X-Api-Key`. Различать `accepted` / `duplicate`. Таймаут ~20 с. Ошибки HTTP — как `TelegramSendError` (ключ в store не писать).
2. Env (`.env.example` + `config.py`), секреты не в git:
   - `NOTIFY_HUB_URL`
   - `NOTIFY_HUB_API_KEY` (из `SERVICE_API_KEYS` хаба, **не** bot token)
   - флаг cutover, например `NOTIFY_VIA_HUB=true|false`
3. В `job.py`: при `NOTIFY_VIA_HUB=true` слать в хаб; иначе — как сейчас в Telegram. **Никогда оба** на одно событие.
4. Поля события:
   - `event_id`: `calendar-` + текущий `idem_key`
   - `type`: one-shot T−30/T−15/ДР → `calendar.event.v1`; nags `nag_*` → `calendar.reminder.v1`
   - `channels`: `["public"]`
   - `source`: `events-calendar`
   - `require_ack`: `false`
   - `title`: `issue.summary`
   - `body`: результат `format_alert_message()`
   - `targets.chat_ids`: на переход можно `[int(TELEGRAM_CHAT_ID)]`; цель — подписчики `@dimkava_public_alerts_bot` (канал `public`)
   - `data`: `jira_key`, `window`, `due_date`, `slot`, `kind`
5. Локальный JSON-store **оставить**; писать ключ после успешного `accepted` или при `duplicate`.
6. Тесты: mock HTTP, без живого Telegram/хаба.
7. Live в чат — только если пользователь явно попросил.

## Сеть (важно)

Календарь крутится на **Windows Server** (Docker one-shot). Хаб — на **Debian**, порт 8080.

`NOTIFY_HUB_URL=http://127.0.0.1:8080` с Windows **не** попадёт в хаб. Не выдумывать URL: спросить или взять достижимый адрес (VPN, публичный IP хоста хаба, прокси). С того же Debian было бы `http://127.0.0.1:8080`.

## Запрещено

- Двойная доставка (хаб + `telegram_client` на тот же `idem_key`)
- Второй `getUpdates` на токене, который поллит хаб
- `require_ack: true`
- Коммит `.env` / ключей / токенов
- Ходить в `firebird-db-proxy`

## Готово, когда

- `NOTIFY_VIA_HUB=true` → `POST /v1/events`, прямой Telegram не вызывается
- Повтор того же `event_id` не создаёт второе сообщение
- `pytest` зелёный на моках
- В README / `.env.example` описаны `NOTIFY_HUB_*`
