# Создание Jira project `DEC` — требования и пошагово

Документ для администратора Atlassian Cloud DimKava.  
После выполнения этого чеклиста можно запускать `python -m dec_calendar check-jira` и `import-events`.

Instance: **https://dimkavageorgia.atlassian.net/**

---

## 1. Зачем отдельный project

| | |
|--|--|
| **Key** | `DEC` |
| **Имя** | DimKava Event Calendar / Календарь событий DimKava |
| **Роль** | SSOT: здесь **создают и правят** события |
| **Не путать с** | `DG` — рабочие задачи компании, **не** календарь |
| **Не использовать key** | `CAL` (отклонён) |

Код читает/пишет только `JIRA_PROJECT_KEY` (по умолчанию `DEC`).

---

## 2. Минимальные требования (обязательно для импорта)

Импортёр (`create_issue`) шлёт:

```json
{
  "fields": {
    "project": { "key": "DEC" },
    "summary": "…",
    "issuetype": { "name": "Task" },
    "description": { "… ADF …" },
    "labels": ["calendar-holiday", …],
    "duedate": "2026-09-15"
  }
}
```

Значит в project **обязательно**:

| Требование | Детали |
|------------|--------|
| Project key | Точно **`DEC`** (латиница, 3 буквы) |
| Issue type с именем **`Task`** | Или смените `JIRA_ISSUE_TYPE` в `.env` на то имя, которое есть в DEC |
| Поле **Due date** (`duedate`) | На экране создания/редактирования Task |
| Поле **Labels** | На экране создания/редактирования Task |
| Поле **Description** | Поддержка ADF (стандарт Cloud) |
| Права API-пользователя | Create issues, Browse projects, Add comments, Edit issues (для правок людьми; API comment — Add comments) |

**Не обязательно для v1:**

- отдельные Issue Type «Holiday» / «Birthday»
- custom fields
- сложный workflow (хватает To Do → Done)
- эпики, спринты, story points
- Team Calendars / плагины календаря

---

## 3. Рекомендуемые настройки при создании

В UI: **Projects → Create project**.

### 3.1. Шаблон

Предпочтительно один из:

1. **Task management** / **Kanban** / **Company-managed business** — простой бэклог задач  
2. Или **Team-managed** (next-gen) с типом Task — тоже ок, если есть Due date + Labels

Важно: после создания **проверьте**, что у Task есть Due date и Labels. В некоторых шаблонах Due date нужно **включить в Issue layout**.

### 3.2. Поля формы создания

| Поле | Значение |
|------|----------|
| Name | `DimKava Event Calendar` |
| Key | `DEC` |
| Access | По политике компании (маркетинг + HR должны уметь править issues) |

### 3.3. Issue layout (если Due date / Labels не видны)

1. Project settings → **Issue types** → Task → **Layout** / **Fields**  
2. Добавить на экран: **Due date**, **Labels**, **Description**, **Assignee** (опционально)  
3. Сохранить

### 3.4. Workflow (обязательно для алертов)

Нужны **три** статуса:

```text
К выполнению  -->  В работе  -->  Готово
(category: To Do)  (In Progress)   (Done)
```

| Статус | Category | Смысл |
|--------|----------|--------|
| **К выполнению** | To Do (`new`) | Дефолт при создании; подготовка ещё не начата |
| **В работе** | In Progress (`indeterminate`) | Взяли событие в работу — утренние/вечерние пинги «начните» прекращаются |
| **Готово** | Done (`done`) | Подготовка закрыта до даты; job больше не алертит |

**Как добавить «В работе» (team-managed / business):**  
Доска → **⋯** / настройки колонок → добавить колонку **В работе** → категория **In Progress**.

Поведение бота (праздники/промо, не ДР):

- с T−30 до дня события: пока статус в **К выполнению** → TG в **10:00 и 22:00**;
- с T−5 до T−1: пока не **Готово** → TG раз в день в **10:00** («доведите до Готово»).

ДР: только T−1 / T−0, без workflow-пингов. Не переводите recurring ДР в Готово сразу после поздравления — лучше оставить открытым и сдвигать `duedate` на год.

---

## 4. Labels (соглашение кода)

Labels **не нужно** создавать заранее в админке — Jira создаёт их при первом использовании. Список для справки:

### Обязательные (одно на issue)

| Label | Контур | Оповещения |
|-------|--------|------------|
| `calendar-holiday` | Праздник | T−30, T−15 |
| `calendar-promo` | Промо / сезон / кофе-день | T−30, T−15 |
| `calendar-birthday` | День рождения | T−1, T−0 |

На issue должен быть **ровно один** из трёх семейных labels (код берёт первый найденный).

### Служебные

| Label | Когда |
|-------|--------|
| `needs-date` | Подвижная/размытая дата; **без** `duedate` или пока дата не утверждена; job с due date такие не алертит, если duedate пустой |
| `pilot-test` | Тестовый пилот «Начало осени» |

### Опциональные теги

`georgia`, `coffee`, `seasonal`, `commercial`, `dk-internal`, `international`

---

## 5. Права и API-токен

### 5.1. Пользователь для бота/скрипта

Создайте или используйте существующий Atlassian-аккаунт (сервисный email), который:

1. Имеет доступ к site `dimkavageorgia.atlassian.net`
2. Добавлен в project **DEC** с ролью не ниже **Member** (создание issues + комментарии)
3. Имеет [API token](https://id.atlassian.com/manage-profile/security/api-tokens)

В `.env`:

```env
JIRA_URL=https://dimkavageorgia.atlassian.net
JIRA_EMAIL=тот-же-email-что-у-токена
JIRA_API_TOKEN=…
JIRA_PROJECT_KEY=DEC
JIRA_ISSUE_TYPE=Task
```

Auth: HTTP Basic (`email` + `api_token`) — как в остальных DimKava-скриптах.

### 5.2. Люди (маркетинг / HR)

Должны уметь в UI:

- создавать/редактировать Task;
- менять Due date и Labels;
- писать в Description.

---

## 6. Ручная проверка после создания (5 минут)

1. Открыть `https://dimkavageorgia.atlassian.net/browse/DEC` (или Projects → DEC).  
2. **Create** → Issue type **Task**.  
3. Заполнить:
   - Summary: `[Праздник] Smoke test DEC`
   - Due date: любая будущая дата
   - Labels: `calendar-holiday`
   - Description: `smoke`
4. Сохранить → убедиться, что issue `DEC-1` (или следующий номер) открывается.  
5. Удалить smoke-issue или перевести в Done (чтобы не мешал).

Затем с машины разработчика:

```powershell
cd D:\CursorProjects\events-calendar
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH = "src"
python -m dec_calendar check-jira
```

Ожидаемый вывод: `authenticated_as=…` и `project=DEC — DimKava Event Calendar` (имя может чуть отличаться).

---

## 7. Что делать, если `check-jira` / импорт падает

| Ошибка | Что проверить |
|--------|----------------|
| 401 Authentication failed | Email + API token; token от того же Atlassian-аккаунта |
| 404 project | Key не `DEC`, или нет Browse permission |
| 400 issuetype | В DEC нет типа с именем `Task` → создать/переименовать или `JIRA_ISSUE_TYPE=…` |
| 400 duedate / field | Due date не на экране Task → добавить в layout |
| 400 labels | Редко; обычно labels всегда доступны в Cloud |
| SSL CERTIFICATE_VERIFY_FAILED | Временно `JIRA_SSL_VERIFY=false` (как в других локальных скриптах Windows) |

---

## 8. После успешного `check-jira`

```powershell
python -m dec_calendar import-events --dry-run
python -m dec_calendar import-events
python -m dec_calendar run-once --dry-run --today 2026-08-31
```

Подробнее: [IMPLEMENTATION.md](IMPLEMENTATION.md), стратегия: [STRATEGY.md](STRATEGY.md).

---

## 9. Краткая шпаргалка для админа

```text
Создать project:
  Key  = DEC
  Name = DimKava Event Calendar
  Type = Task management / Kanban (с Task)

На Task включить поля:
  Due date, Labels, Description

Права:
  API-user: Create + Comment + Browse
  Marketing/HR: Edit

Не нужно:
  Custom fields, Team Calendar plugin, отдельный issue type на каждый вид события
```
