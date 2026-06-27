# Честный Знак (CZ) — таски на исправление по код-ревью

> **Для кого:** для агента-исполнителя (композера), который будет реализовывать правки.
> **Источник:** код-ревью диапазона `4e82c6b..HEAD`. Полный отчёт — `docs/_review_cz/FINAL_REPORT.md`, детали по измерениям — `docs/_review_cz/find-*.md`.
> **Вердикт ревью:** NO-GO до устранения блокеров (P0). После P0 — GO с условиями (закрыть P1).

---

## 0. Как пользоваться этим документом

- Таски сгруппированы по приоритету: **P0 — блокеры** (без них в прод нельзя), **P1 — важное** (до релиза), **P2 — мелочи** (бэклог/попутно).
- Делай **по порядку приоритета**. Внутри приоритета можно в любом порядке, кроме явных `Зависит от`.
- **Номера строк — ориентир** (могут сместиться после первых правок). Для надёжного поиска используй имя функции/якорь из колонки «Где».
- У каждого таска: `Где`, `Проблема`, `Что сделать` (с «было/стало» где уместно), `Критерии приёмки`, `Тест`.

### Definition of Done (общее для всех тасков)
1. Правка сделана строго в указанном месте, без расширения скоупа.
2. Добавлен/обновлён тест из таска, он падал ДО правки и проходит ПОСЛЕ.
3. Гейты зелёные на затронутых файлах:
   - `cd backend && ruff check . && mypy app` — без новых ошибок;
   - `cd backend && pytest -q tests/test_marking* tests/test_notif* tests/test_print_templates.py` — 100% pass;
   - фронт (если затронут): `cd frontend && npm run typecheck && npm run test`.
4. Не ломать существующие тесты.

### Важно про окружение
- Репозиторий по пути с **пробелом на конце**: `"/Users/deniscivkunov/Desktop/WMS "`. Все команды/пути — в кавычках.
- Прод-СУБД — **PostgreSQL** (`backend/app/core/settings.py:10`), тесты — SQLite. Правки должны работать на обеих.

### Карта тасков
| ID | Приоритет | Заголовок | Файл (главный) |
|----|-----------|-----------|----------------|
| CZ-B1 | 🔴 P0 | Миграция `is_default` падает на PostgreSQL | `alembic/.../0046_print_templates.py` |
| CZ-B2 | 🔴 P0 | Prod-гейт на ключ шифрования секретов | `core/settings.py`, `services/integration_fernet.py` |
| CZ-B3 | 🔴 P0 | Убрать молчаливую автопривязку товара по GTIN (И2) | `services/marking_code_service.py` |
| CZ-B4 | 🔴 P0 | `status` query-param затеняет `fastapi.status` → 500 | `api/marking_codes.py` |
| CZ-B5 | 🔴 P0 | Атомарность `print_all_for_packaging_task` | `services/marking_code_service.py` |
| CZ-B6 | 🔴 P0 | `SKIP LOCKED` при выдаче кодов из пула + тест на гонку | `services/marking_code_service.py` |
| CZ-H1 | 🟠 P1 | Прогноз/расход считает копии, а не коды | `services/marking_code_service.py` |
| CZ-H2 | 🟠 P1 | Брак→замена: довести старый код до `replaced` | `services/marking_code_service.py` |
| CZ-H3 | 🟠 P1 | Идемпотентность `verify_pair_and_apply` | `services/marking_code_service.py` |
| CZ-H4 | 🟠 P1 | Печать/перепечатка: проверять статус задания | `services/marking_code_service.py` |
| CZ-H5 | 🟠 P1 | `approve_reprint_request`: проверять статус кода | `services/marking_code_service.py` |
| CZ-H6 | 🟠 P1 | TOCTOU превью↔выдача в `print_all`, агрегация по пулу | `services/marking_code_service.py` |
| CZ-H7 | 🟠 P1 | Идемпотентный импорт (`ON CONFLICT`) | `services/marking_code_service.py` |
| CZ-H8 | 🟠 P1 | N+1 и пагинация в `/pending-marking` | `api/marking_codes.py`, service |
| CZ-H9 | 🟠 P1 | Тест на конкурентную выдачу из пула | `tests/test_marking_print_pool.py` |
| CZ-H10 | 🟠 P1 | Тесты: replace-исход + shift-lead на мутациях | `tests/...` |
| CZ-M1 | 🟡 P2 | Верхний предел `auto_emit_limit` | `services/seller_marking_credentials_service.py` |
| CZ-M2 | 🟡 P2 | Полный маппинг ошибок credentials | `api/marking_credentials.py` |
| CZ-M3 | 🟡 P2 | Подсветка нехватки КМ в списке упаковки | `screens/ff/FfPackagingPage.tsx` |
| CZ-M4 | 🟡 P2 | Пагинация `/pools/{id}/codes` | `api/marking_codes.py` |
| CZ-M5 | 🟡 P2 | Доменная обёртка ошибки расшифровки | `services/seller_marking_credentials_service.py` |
| CZ-M6 | 🟡 P2 | Reprint на фронте: показывать нехватку | `components/MarkingPrintDialog.tsx` |
| CZ-M7 | 🟡 P2 | 201 вместо 200 на создании ресурсов | `api/marking_codes.py` |
| CZ-M8 | 🟡 P2 | Верхние пределы `units`/числа файлов | `api/marking_codes.py`, `print_template_service.py` |
| CZ-M9 | 🟡 P2 | DB-UNIQUE на пул `(tenant, seller, gtin)` | `alembic/.../0043_marking_pools.py` |
| CZ-M10 | 🟡 P2 | `tmp_alembic_test.sqlite` в `.gitignore` | `.gitignore` |
| CZ-M11 | 🟡 P2 | Зелёные ruff/mypy | (5 файлов) |
| CZ-M12 | 🟡 P2 | Усилить слабые тест-ассерты | `tests/...` |

---

# 🔴 P0 — Блокеры

## CZ-B1 — Миграция `print_templates.is_default` падает на PostgreSQL
- **Где:** `backend/alembic/versions/20260626_0046_print_templates.py:29`
- **Проблема:** boolean-колонка создаётся с `server_default=sa.text("0")`. PostgreSQL не приводит integer-литерал `0` к типу boolean в DEFAULT → `alembic upgrade` **упадёт на этой ревизии на проде** (сорванный деплой). Это единственная миграция в репо с таким стилем; соседние используют `sa.false()`.
- **Что сделать:**
  ```python
  # было
  sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("0")),
  # стало
  sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
  ```
  Проверь все остальные миграции диапазона `2026062*` на `sa.text("0")`/`sa.text("1")` для boolean-колонок — заменить на `sa.false()`/`sa.true()`.
- **Критерии приёмки:** `alembic upgrade head` проходит на PostgreSQL (а не только SQLite); `downgrade` симметричен.
- **Тест:** прогнать миграции на Postgres (docker/local). Если в проекте есть тест миграций — добавить ассерт типа дефолта; иначе зафиксировать ручную проверку в PR.

## CZ-B2 — Prod-гейт на ключ шифрования секретов (Fernet)
- **Где:** `backend/app/services/integration_fernet.py:13-19`; `backend/app/core/settings.py:14-17, 33-37`
- **Проблема:** если `wms_secrets_fernet_key` не задан, ключ шифрования = `sha256(jwt_secret_key)`, а `jwt_secret_key` имеет **публичный дефолт из репозитория** (`"change-me-in-production-use-long-random-secret"`). При дефолтном конфиге все токены ЧЗ/СУЗ/МП (`*_enc`) шифруются ключом, воспроизводимым из исходников → дамп БД = открытые токены. Enforcement отсутствует — только комментарий.
- **Что сделать:**
  1. В `settings.py` добавить поле окружения (его сейчас нет):
     ```python
     app_env: str = Field(default="development", description="development | staging | production")
     ```
  2. Добавить fail-fast валидацию (model_validator в Settings ИЛИ проверка на старте приложения в `main.py` lifespan). В проде запрещаем небезопасную конфигурацию:
     ```python
     @model_validator(mode="after")
     def _validate_prod_secrets(self) -> "Settings":
         if self.app_env == "production":
             if not self.wms_secrets_fernet_key:
                 raise ValueError("wms_secrets_fernet_key must be set in production")
             if self.jwt_secret_key == "change-me-in-production-use-long-random-secret":
                 raise ValueError("jwt_secret_key must be overridden in production")
         return self
     ```
  3. В `integration_fernet._fernet_key_material()` оставить деривацию из `jwt_secret_key` **только как dev/test fallback** (комментарий уже есть) — она теперь недостижима в проде из-за гейта.
- **Критерии приёмки:** запуск с `APP_ENV=production` без `wms_secrets_fernet_key` (или с дефолтным `jwt_secret_key`) **падает на старте** с понятной ошибкой; dev/test работают как раньше.
- **Тест:** `tests/test_settings_prod_gate.py` — параметризовать: prod+нет ключа → `ValidationError`; prod+ключ задан → ок; development без ключа → ок.

## CZ-B3 — Убрать молчаливую автопривязку товара по GTIN (нарушение инварианта И2)
- **Где:** `backend/app/services/marking_code_service.py:667-698` (`relink_unlinked_marking_codes`); вызов из `list_inventory` на `:981-982`
- **Проблема:** инвариант **И2** (см. `docs/CHESTNY_ZNAK_TASKS_RU.md`) запрещает угадывать товар по GTIN — связь товар↔код должна быть только ручной (M2M `marking_pool_products`). Здесь функция автоматически проставляет `code.product_id` по GTIN и **коммитит в БД при обычном чтении инвентаря** (`list_inventory` дёргается на каждый просмотр), без действия пользователя. Это и неверно семантически, и побочный эффект на read-пути.
- **Что сделать:**
  1. Удалить вызов в `list_inventory`:
     ```python
     # было (≈:980-982)
     if seller_id is not None:
         await relink_unlinked_marking_codes(session, tenant_id, seller_id)
     # стало — строки удалить
     ```
  2. Удалить саму функцию `relink_unlinked_marking_codes` (`:667-698`), если она больше нигде не вызывается (проверь grep `relink_unlinked_marking_codes`).
  3. Остаток/инвентарь по непривязанным кодам выводить через ручную M2M-связь, как задумано дизайном (коды без `product_id`/`pool_id` показываются «непривязанными», привязка — отдельным явным действием пользователя).
- **Критерии приёмки:** чтение инвентаря не пишет в БД; код с `product_id=NULL` НЕ привязывается к товару автоматически по совпадению GTIN.
- **Тест:** `tests/test_marking_pools.py` (или новый) — импортировать код с GTIN, совпадающим с товаром, но без явной привязки; вызвать `list_inventory`; ассертить, что `code.product_id` остался `None`.

## CZ-B4 — `status` query-param затеняет `fastapi.status` → 500 вместо 404
- **Где:** `backend/app/api/marking_codes.py:9` (импорт `status`), `:714` (параметр `status`), `:721` (использование). Функция `list_marking_pool_codes`.
- **Проблема:** параметр `status: Annotated[str | None, Query()] = None` перекрывает импортированный модуль `status`. В ветке not-found/чужой tenant вызывается `status.HTTP_404_NOT_FOUND`, где `status` — это `None` (значение параметра) → `AttributeError` → **HTTP 500 вместо 404**. Маскирует мультитенантную проверку. Подтверждено дважды (инварианты + mypy-гейт).
- **Что сделать:** переименовать параметр, сохранив внешнее имя через alias:
  ```python
  # было
  status: Annotated[str | None, Query()] = None,
  ...
  raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="pool_not_found")
  ...
  rows = await mc_svc.list_pool_codes(session, user.tenant_id, pool_id, status=status)

  # стало
  status_filter: Annotated[str | None, Query(alias="status")] = None,
  ...
  raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="pool_not_found")  # status снова модуль
  ...
  rows = await mc_svc.list_pool_codes(session, user.tenant_id, pool_id, status=status_filter)
  ```
  Прогнать grep по файлу: нет ли других эндпоинтов с тем же затенением `status`.
- **Критерии приёмки:** запрос кодов несуществующего/чужого пула возвращает **404** (а не 500); фильтр по `?status=...` продолжает работать.
- **Тест:** `tests/test_marking_pools_read.py` — (а) запрос кодов чужого пула → 404; (б) запрос с `?status=available` фильтрует корректно.

## CZ-B5 — Атомарность `print_all_for_packaging_task`
- **Где:** `backend/app/services/marking_code_service.py:1536-1567` (цикл по строкам) + `:1278` (`await session.commit()` внутри `print_codes_for_packaging_line`)
- **Проблема:** каждая строка задания коммитится отдельной транзакцией внутри `print_codes_for_packaging_line`. Ошибка/дефицит на N-й строке оставляет первые строки уже закоммиченными (коды списаны в `STATUS_PRINTED`), задание не завершено целиком; повтор упирается в `already_printed_use_reprint` → **невосстановимый частичный результат, расход/потеря КМ**.
- **Что сделать:** вынести границу транзакции на уровень `print_all`:
  1. Сделать «тихий» вариант построчной печати без внутреннего commit (флаг `commit: bool = True` у `print_codes_for_packaging_line`, либо приватная `_print_codes_for_packaging_line_nocommit`).
  2. В цикле `print_all` вызывать без commit; один `await session.commit()` после успешной обработки всех строк. При исключении — `await session.rollback()` (откатывается всё).
  3. Альтернатива при необходимости частичного успеха по строкам: оборачивать каждую строку в `session.begin_nested()` (SAVEPOINT) и общий commit в конце — но согласовать с продуктовым требованием (по дизайну `print_all` — атомарная операция).
- **Критерии приёмки:** если на какой-то строке дефицит/ошибка при `allow_partial=False` — НИ ОДНА строка задания не остаётся закоммиченной (всё откатывается); при успехе — все строки в одном commit.
- **Тест:** `tests/test_marking_print_all.py` — задание из 2+ строк, на второй строке заведомый дефицит при `allow_partial=False`; ассертить, что после вызова первая строка тоже НЕ `printed` и коды не списаны.
- **Связь:** см. CZ-H6 (TOCTOU превью) — желательно делать вместе.

## CZ-B6 — `SKIP LOCKED` при выдаче кодов из пула + тест на гонку
- **Где:** `backend/app/services/marking_code_service.py:1211-1223` (выборка в `print_codes_for_packaging_line`), тот же паттерн `:2215-2227` (`replace_reprint_request`)
- **Проблема:** `SELECT ... FOR UPDATE LIMIT n` **без `SKIP LOCKED`** под READ COMMITTED: два параллельных упаковщика берут одни и те же верхние строки; T2 блокируется на залоченных T1 и после коммита T1 недобирает N → **ложный `shortage`** при `allow_partial=False`, хотя свободные коды в пуле есть. (Двойной выдачи нет — это плюс, его не сломать.)
- **Что сделать:**
  ```python
  # было (≈:1221)
  .with_for_update()
  # стало
  .with_for_update(skip_locked=True)
  ```
  Применить в обоих местах (`:1221` и `:2225`). Учесть: на SQLite (тесты) `skip_locked` игнорируется/не поддерживается — SQLAlchemy эмитит без него; убедиться, что тесты не падают (при необходимости диалект-гард). Опционально: один retry выборки перед возвратом дефицита.
- **Критерии приёмки:** два параллельных запроса печати по одному пулу не блокируют друг друга и в сумме выдают ≤ остатка без ложного дефицита; двойной выдачи одного КМ по-прежнему нет.
- **Тест:** см. CZ-H9 (тот же тест на гонку покрывает этот таск).

---

# 🟠 P1 — Важное

## CZ-H1 — Прогноз/расход считает копии, а не коды (занижение вдвое)
- **Где:** `backend/app/services/marking_code_service.py:1652-1677` (`_pool_consumption_7d_batch`); событие печати пишется с `copies=2` (`:1267-1275`)
- **Проблема:** расход за 7 дней суммирует `MarkingCodeEvent.copies` (обычно 2 на код), поэтому `forecast_days` занижается вдвое → ложные low-stock алёрты (нарушение духа И4; сам остаток считается верно).
- **Что сделать:** считать число потреблённых кодов, а не копий:
  ```python
  # было (≈:1662)
  func.coalesce(func.sum(MarkingCodeEvent.copies), 0),
  # стало — уникальные коды
  func.count(func.distinct(MarkingCodeEvent.code_id)),
  ```
  Проверить, что у `MarkingCodeEvent` есть `code_id` (по событиям печати он заполнен). Сверить `CONSUMPTION_EVENT_TYPES` — суммируем только реальный расход (печать/выдача), не дубль-события.
- **Критерии приёмки:** для кода, напечатанного парой (copies=2), расход за период = 1 (код), а не 2.
- **Тест:** `tests/test_marking_forecast.py` — напечатать N кодов парами, ассертить `consumption_7d == N` (а не `2N`) и корректный `forecast_days`.

## CZ-H2 — Брак→замена: довести старый код до статуса `replaced`
- **Где:** `backend/app/services/marking_code_service.py:2231-2259` (`replace_reprint_request`)
- **Проблема:** при замене пишется `EVENT_REPLACED`, но `old_code.status` остаётся `STATUS_DEFECTIVE` — незавершённый переход машины статусов (DESIGN §5). Счётчик «Брак» в карточке пула завышается заменёнными кодами; рассинхрон журнала и состояния.
- **Что сделать:** после записи `EVENT_REPLACED` выставить терминальный статус:
  ```python
  # после await record_event(... event_type=EVENT_REPLACED ...)
  old_code.status = STATUS_REPLACED
  ```
  Проверить, что константа `STATUS_REPLACED` существует в `models/marking_code.py` и входит в допустимую машину статусов; если нет — добавить и учесть в местах фильтрации статусов.
- **Критерии приёмки:** после замены `old_code.status == STATUS_REPLACED`, `old_code.replaced_by_code_id` указывает на новый код, новый код `STATUS_PRINTED`; счётчик «Брак» не учитывает заменённые.
- **Тест:** `tests/test_marking_reprint_defect.py` — после `replace_reprint_request` дочитать оба кода из БД и ассертить статусы, связь и записанные события (`EVENT_DEFECTIVE`+`EVENT_REPLACED` на старом, `EVENT_PRINTED` на новом). (Перекрывается с CZ-H10а.)

## CZ-H3 — Идемпотентность `verify_pair_and_apply`
- **Где:** `backend/app/services/marking_code_service.py:2328-2360`
- **Проблема:** два параллельных скана одной пары читают `status==PRINTED`, оба пишут `STATUS_APPLIED` и два `EVENT_APPLIED` — нарушена идемпотентность применения, дубль события.
- **Что сделать:** одно из:
  - выбирать код `.with_for_update()` и перепроверять статус под локом перед применением; либо
  - условный апдейт `UPDATE marking_codes SET status='applied' WHERE id=:id AND status='printed'` с проверкой `rowcount==1` (иначе — уже применён, вернуть идемпотентный результат без второго события).
- **Критерии приёмки:** повторный/параллельный verify одной пары не создаёт второй `EVENT_APPLIED` и не меняет состояние дважды.
- **Тест:** `tests/test_marking_verify_pair.py` — вызвать применение дважды (последовательно и через `asyncio.gather`); ассертить ровно один `EVENT_APPLIED`.

## CZ-H4 — Печать/перепечатка: проверять статус упаковочного задания
- **Где:** `backend/app/services/marking_code_service.py:1113-1289` (`print_codes_for_packaging_line`), reprint-ветка `:1156-1188`
- **Проблема:** нет проверки `task.status` — можно печатать/резервировать коды для завершённого/отгруженного задания, израсходовав коды «в никуда» (искажение остатка И3). Для сравнения `list_pending_marking_lines` ограничивает `status in (draft, in_progress)`.
- **Что сделать:** после загрузки `task` добавить guard:
  ```python
  if task.status not in (TASK_STATUS_DRAFT, TASK_STATUS_IN_PROGRESS):
      raise MarkingCodeServiceError("task_not_active")
  ```
  Использовать реальные константы статусов задания из модели. Замапить новую ошибку в API на 409/422.
- **Критерии приёмки:** печать по закрытому/отгруженному заданию отклоняется доменной ошибкой, коды не списываются.
- **Тест:** `tests/test_marking_scan_print.py` — перевести задание в завершённый статус, попытаться печатать → ошибка `task_not_active`, остаток пула не изменился.

## CZ-H5 — `approve_reprint_request`: проверять статус кода
- **Где:** `backend/app/services/marking_code_service.py:2141-2180`
- **Проблема:** в отличие от `replace_reprint_request` (есть страж `STATUS_PRINTED`), здесь `EVENT_REPRINTED` пишется без проверки `code.status` — код мог стать `applied`/`shipped`/`defective` между созданием заявки и аппрувом → событие, противоречащее состоянию (DESIGN §6 «если ещё валиден»).
- **Что сделать:** симметрично добавить страж перед `record_event`:
  ```python
  if code.status != STATUS_PRINTED:
      raise MarkingCodeServiceError("code_not_printed")
  ```
- **Критерии приёмки:** аппрув перепечатки кода не в статусе `printed` отклоняется; событие не пишется.
- **Тест:** `tests/test_marking_reprint_defect.py` — создать заявку, перевести код в `applied`, апрувнуть → ошибка `code_not_printed`.

## CZ-H6 — TOCTOU превью↔выдача в `print_all`, агрегация потребности по пулу
- **Где:** `backend/app/services/marking_code_service.py:1506-1531` (превью без локов) → `:1536-1567` (выдача); `count_available_for_product` `:1100-1108` vs фильтр выдачи `:1205-1209`
- **Проблема:** превью считает доступность без локов и **без агрегации потребности по общему пулу** (две строки по 50 при 60 кодах в одном пуле обе проходят превью как «ок»); фильтр превью шире фильтра выдачи → ложное «всё хорошо» с последующим частичным коммитом.
- **Что сделать:**
  1. Агрегировать суммарную потребность по `pool_id` (несколько строк могут тянуть из одного пула) и сравнивать с доступным остатком пула, а не построчно.
  2. Согласовать фильтры превью и выдачи (одинаковый `code_filter`: pool_ids → product_id fallback).
  3. Превью + выдачу выполнять в одной транзакции с `FOR UPDATE SKIP LOCKED` (см. CZ-B6).
- **Критерии приёмки:** при двух строках, тянущих из одного пула, превью корректно показывает суммарную нехватку; нет расхождения «превью ок → выдача дефицит».
- **Тест:** `tests/test_marking_print_all.py` — две строки одного пула, суммарно больше остатка; ассертить, что превью/результат показывают нехватку согласованно.
- **Связь:** делать вместе с CZ-B5 и CZ-B6.

## CZ-H7 — Идемпотентный импорт (`ON CONFLICT`)
- **Где:** `backend/app/services/marking_code_service.py:910-937` (`import_marking_codes`); есть `uq_marking_codes_tenant_cis`
- **Проблема:** SELECT-then-INSERT без `ON CONFLICT`. Параллельный/повторный импорт одного CIS: оба проходят SELECT, второй `flush()` ловит `IntegrityError`, без savepoint **абортит весь батч** (включая уже выданный `document_number`). Импорт не идемпотентен.
- **Что сделать:** перейти на upsert по уникальному ключу (как сделано в `next_document_number`):
  ```python
  from sqlalchemy.dialects.postgresql import insert as pg_insert
  stmt = (
      pg_insert(MarkingCode)
      .values(rows)
      .on_conflict_do_nothing(index_elements=["tenant_id", "cis_code"])
      .returning(MarkingCode.id)
  )
  ```
  Учесть SQLite в тестах (там `sqlite insert(...).on_conflict_do_nothing`), либо диалект-гард. Считать «пропущенные дубли» для отчёта импорта.
- **Критерии приёмки:** повторный импорт того же CIS не падает и не плодит дублей; `document_number` не теряется; ответ содержит счётчик добавленных/пропущенных.
- **Тест:** `tests/test_marking_import_pools.py` — импортировать один и тот же CIS дважды; ассертить отсутствие исключения, один код в БД, корректный отчёт (added=…, skipped=…).

## CZ-H8 — N+1 и отсутствие пагинации в `/pending-marking`
- **Где:** `backend/app/services/marking_code_service.py:2381` (`list_pending_marking_lines`), эндпоинт `backend/app/api/marking_codes.py:1104`
- **Проблема:** `count_available_for_product` (сам ~3 запроса) вызывается в цикле по каждой строке → ~3N round-trip; эндпоинт без `limit/offset` грузит все строки всех `draft/in_progress` заданий.
- **Что сделать:**
  1. Подсчёт доступности — одним запросом `GROUP BY product_id` (или `pool_id`) для всех нужных продуктов, затем мапить в строки.
  2. Добавить пагинацию: `limit: int = Query(50, ge=1, le=200)`, `offset: int = Query(0, ge=0)`, в ответ — `total`.
- **Критерии приёмки:** число SQL-запросов не растёт линейно с числом строк; эндпоинт принимает `limit/offset` и возвращает `total`.
- **Тест:** `tests/test_marking_pending.py` — создать N строк, проверить пагинацию (limit/offset, total) и корректные `available`-значения.

## CZ-H9 — Тест на конкурентную выдачу кодов из пула
- **Где:** `backend/tests/test_marking_print_pool.py:143` (существующий «не пересекаются» тест строго последователен)
- **Проблема:** нет теста на гонку — удаление блокировки/`skip_locked` не уронит тесты, регрессия двойной выдачи под параллелью пройдёт незамеченной. Паттерн `asyncio.gather` в проекте есть (`test_document_number_service.py:104`).
- **Что сделать:** добавить тест: один пул с ограниченным остатком, две печати по одному пулу через `asyncio.gather` (каждая со своей сессией/транзакцией). Ассертить:
  - суммарно выдано ≤ остатка;
  - нет дублей CIS среди выданных;
  - при достаточном остатке обе печати успешны без ложного дефицита (проверяет CZ-B6).
- **Критерии приёмки:** тест падает на коде без `skip_locked`-фикса (ложный дефицит) и/или ловит двойную выдачу, проходит после CZ-B6.
- **Тест:** это и есть тест. Файл: `tests/test_marking_print_pool.py`.

## CZ-H10 — Усилить тесты: replace-исход и shift-lead на мутациях
- **Где:** `backend/tests/test_marking_reprint_defect.py:181`; `backend/tests/test_shift_lead.py:71`
- **Проблема:** (а) `test_replace_reprint_request_clears_queue` ассертит только `status==approved` и непустой `replacement_code_id`, но не проверяет реальный исход. (б) Негативный 403-кейс есть только на `GET /reprint-requests`; на мутирующих `replace`/`approve`/`reject` нет — если там забыли `require_shift_lead`, тесты не поймают.
- **Что сделать:**
  - (а) дочитать состояние из БД: `old_code.status == replaced` (после CZ-H2), `old_code.replaced_by_code_id`, `new_code.status == printed`, остаток пула −1, записаны нужные события.
  - (б) добавить тесты: пользователь без роли shift_lead вызывает `replace`/`approve`/`reject` → **403**.
- **Критерии приёмки:** оба пробела закрыты; тесты падают, если убрать соответствующую логику/гейт.
- **Тест:** правки в указанных файлах.

---

# 🟡 P2 — Мелочи / улучшения

## CZ-M1 — Верхний предел `auto_emit_limit`
- **Где:** `backend/app/services/seller_marking_credentials_service.py:209`; `backend/app/api/marking_credentials.py:169`
- **Проблема:** валидируется только снизу (`>=1`), без верхнего предела — лимит авто-эмиссии КМ фактически снимается опечаткой (можно прислать 10^9).
- **Что сделать:** ограничить диапазон, напр. `1 <= auto_emit_limit <= 100000` (в pydantic-схеме `Field(ge=1, le=100000)` и/или в сервисе).
- **Критерии приёмки:** значение вне диапазона → 422.
- **Тест:** `tests/test_marking_credentials_api.py` — `auto_emit_limit=10**9` → 422.

## CZ-M2 — Полный маппинг ошибок credentials
- **Где:** `backend/app/api/marking_credentials.py:204`
- **Проблема:** код ошибки `invalid_auto_introduce` не в whitelist хендлера → потенциальный 500 на клиентскую ошибку (сейчас прикрыт верхним слоем валидации — «требует подтверждения достижимости»).
- **Что сделать:** добавить код в маппинг на 422 либо обобщить правило (`invalid_*`/`*_empty` → 422). Убедиться, что все коды ошибок сервиса кредов покрыты.
- **Критерии приёмки:** ни одна доменная ошибка валидации credentials не уходит 500.
- **Тест:** спровоцировать `invalid_auto_introduce` → 422 (если достижимо), иначе зафиксировать общий маппинг.

## CZ-M3 — Подсветка нехватки КМ в списке строк упаковки
- **Где:** `frontend/src/screens/ff/FfPackagingPage.tsx:656-668`
- **Проблема:** ячейка ЧЗ показывает «дост. N» нейтрально, без сравнения с `qty_need_pack`; подсветка появляется только в диалоге печати. DESIGN (`:36/378`) требует индикатор «сразу» (в превью «печать всех» подсветка уже есть — непоследовательность).
- **Что сделать:** красить значение в `warning.main`, когда `marking_available_count < qty_need_pack` (использовать поля из текущего контракта строки; если поля нет — взять из того же источника, что и превью).
- **Критерии приёмки:** в списке строк визуально видно, где кодов не хватает, без открытия диалога.
- **Тест:** e2e `frontend/tests-e2e/ff-marking-packaging.spec.ts` — строка с нехваткой показывает warning-стиль.

## CZ-M4 — Пагинация `/pools/{id}/codes`
- **Где:** `backend/app/api/marking_codes.py:709` (`list_marking_pool_codes`), `marking_code_service.py:1830` (`list_pool_codes`)
- **Проблема:** отдаёт ВСЕ коды пула (десятки тысяч) без `limit/offset`.
- **Что сделать:** добавить `limit: int = Query(50, ge=1, le=200)`, `offset: int = Query(0, ge=0)`, `total` в ответ. (Делать после/вместе с CZ-B4 — тот же эндпоинт.)
- **Критерии приёмки:** эндпоинт пагинирует, дефолт 50.
- **Тест:** `tests/test_marking_pools_read.py` — проверить limit/offset/total.

## CZ-M5 — Доменная обёртка ошибки расшифровки
- **Где:** `backend/app/services/seller_marking_credentials_service.py:237-243`
- **Проблема:** расшифровка падает `InvalidToken` без обёртки — риск попадания cipher-text в трейс вызывающего.
- **Что сделать:** обернуть `decrypt_secret` в try/except → `SecretDecryptError` (новый доменный класс) без исходного значения в сообщении.
- **Критерии приёмки:** при битом шифртексте бросается доменная ошибка без утечки cipher-text.
- **Тест:** unit — подсунуть невалидный шифртекст, ассертить `SecretDecryptError` и отсутствие cipher-text в тексте ошибки.

## CZ-M6 — Reprint на фронте: показывать нехватку кодов
- **Где:** `frontend/src/components/MarkingPrintDialog.tsx:102-111`
- **Проблема:** для `reprint=true` `shortage` форсится в 0, кнопка не блокируется по доступности. Если перепечатка тянет коды из пула — предупреждения нет до ответа бэка. (LOW, требует подтверждения контракта бэка: тянет ли reprint из пула.)
- **Что сделать:** уточнить контракт. Если reprint расходует пул — учитывать `available` и для reprint; если использует ранее выданные коды — явно пометить в UI «коды из ранее выданных» (тогда индикатор нехватки не нужен).
- **Критерии приёмки:** поведение UI соответствует реальному контракту бэка по reprint.
- **Тест:** e2e `ff-marking-print-constructor.spec.ts` / `ff-marking-print-all.spec.ts` по итоговому решению.

## CZ-M7 — 201 вместо 200 на создании ресурсов
- **Где:** `backend/app/api/marking_codes.py:1296` (`POST /codes/{id}/defect`), `:485` (`POST /import`)
- **Проблема:** создание ресурса отвечает 200.
- **Что сделать:** проставить `status_code=status.HTTP_201_CREATED` где создаётся ресурс (как минимум `/codes/{id}/defect`; для `/import` — на усмотрение, это batch-операция).
- **Критерии приёмки:** создание дефекта → 201.
- **Тест:** обновить ассерт статуса в `tests/test_marking_reprint_defect.py`.

## CZ-M8 — Верхние пределы `units` и числа файлов импорта
- **Где:** `backend/app/api/marking_codes.py:276` (layout `units`), `print_template_service.py:80`; `marking_codes.py:451` (файлы импорта)
- **Проблема:** `copies` ограничен (1..10), но длина `units` в layout и число файлов импорта — нет (потенциальный DoS большим payload).
- **Что сделать:** добавить пределы: `len(units) <= 20` (валидация в схеме/сервисе layout), число файлов импорта `<= 20`.
- **Критерии приёмки:** превышение пределов → 422.
- **Тест:** `tests/test_print_templates.py` — layout с >20 units → 422; импорт с >20 файлами → 422.

## CZ-M9 — DB-UNIQUE на пул `(tenant_id, seller_id, gtin)`
- **Где:** `backend/alembic/versions/20260626_0043_marking_pools.py:137-142` (индекс `unique=False`)
- **Проблема:** инвариант «один пул = один GTIN» (DESIGN `:74`) не закреплён в БД; при гонке рантайм может создать дубль пула. (Бэкфилл дублей не создаёт — дедуп в памяти; вопрос только в DB-инварианте.)
- **Что сделать (если инвариант обязателен):** новая миграция — сделать индекс `ix_marking_pools_tenant_seller_gtin` уникальным (`unique=True`) ПОСЛЕ проверки/устранения дублей. Согласовать с продуктом (точно ли всегда 1 пул на GTIN на селлера).
- **Критерии приёмки:** в БД нельзя создать два пула на один `(tenant, seller, gtin)`.
- **Тест:** `tests/test_marking_pools.py` — попытка создать дубль пула → IntegrityError/доменная ошибка.

## CZ-M10 — `tmp_alembic_test.sqlite` в `.gitignore`
- **Где:** `backend/tmp_alembic_test.sqlite` (188 КБ, untracked); `.gitignore` содержит только `wms_pytest.sqlite`/`alembic_autogen.db`
- **Что сделать:** удалить файл с диска; добавить в `.gitignore` (`backend/tmp_alembic_test.sqlite` или паттерн `*.sqlite` если уместно). Проверить, что не попал в коммиты диапазона.
- **Критерии приёмки:** файл не отслеживается git и не попадёт при `git add .`.
- **Тест:** `git status` чист по этому файлу.

## CZ-M11 — Зелёные ruff/mypy
- **Где:** ruff 4 ошибки (`RUF059`; `E501` в `tests/test_marking_reprint_defect.py:166`, `tests/test_marking_verify_pair.py:63`, и др.); mypy 10 в 5 файлах (`marking_codes.py:721` — закрывается в CZ-B4; `marking_codes.py:940/942/989` — `UUID | None`; `marking_code_service.py:1209` — тип `code_filter`; `__all__`-экспорты)
- **Проблема:** CI красный.
- **Что сделать:** починить все ruff/mypy. **Особое внимание `marking_codes.py:940/942/989`** — проверить, нет ли реального None-проглатывания (а не просто аннотации). Привести типы, без `# type: ignore` где можно.
- **Критерии приёмки:** `ruff check .` и `mypy app` — без ошибок.
- **Тест:** гейты в CI зелёные.

## CZ-M12 — Усилить слабые/тавтологичные тест-ассерты
- **Где:** `tests/test_marking_print_all.py:124` (тавтология «in_order», нет проверки `layout`/`line_id`); `tests/test_marking_forecast.py:138` (`unread_count==0` под админом не доказывает видимость селлером); `tests/test_marking_code_events.py:142` (условный `if doc_number:` маскирует потерю номера)
- **Что сделать:** сопоставлять `line_id` и `layout`; проверять получателя уведомления **через API под селлером**; ассертить `document_number` безусловно (убрать `if`).
- **Критерии приёмки:** тесты проверяют user-visible исход, падают при регрессии логики.
- **Тест:** правки в указанных файлах.

---

## Рекомендуемый порядок работ
1. **P0 целиком** (CZ-B1…B6) — без них прод/мёрж невозможен. B5+B6+H6 логично делать одним заходом (транзакции/локи).
2. **P1** (CZ-H1…H10) — до релиза; H2 тянет за собой `STATUS_REPLACED`, проверь использование статуса в фильтрах.
3. **P2** (CZ-M1…M12) — попутно/бэклог; M11 (зелёный CI) — желательно закрыть до мёржа.

После каждого таска — прогон гейтов из «Definition of Done».
