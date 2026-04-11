# Следующие задачи (очередь)

Короткий бэклог после текущего среза. Отмечайте в issues; e2e — обязательны для UI.

## Сделано в последнем срезе

- E5 закрыт: селлер приёмка/outbound draft, фильтр outbound по селлеру (e2e `seller-outbound-filter.spec.ts`), миграция `seller_id` на заявках.
- E2e: `seller-cabinet` — после `form.reset()` при втором товаре снова заполнять габариты; `transfer-and-outbound` — `waitForGetOk` для журнала движений в `Promise.all` с кликом «Обновить», иначе гонка и таймаут.
- Celery + Redis: `CELERY_BROKER_URL`, worker в compose, без брокера — `BackgroundTasks`.
- Фоновые задачи: `POST /operations/background-jobs` (`movements_digest`), опрос `GET .../{id}`, UI с кнопкой и статусом.
- Селлеры: `GET/POST /sellers`, привязка `seller_id` при создании товара, блок в каталоге.
- Pytest: общий SQLite-файл для HTTP и фоновых задач (`tests/conftest.py`).

## P0 — инфраструктура джоб

- ~~**Celery + Redis**~~: `CELERY_BROKER_URL`, `app/celery_app.py`, `app/tasks/`, сервис `celery_worker` и `redis` в `docker-compose.yml`. Без брокера — `BackgroundTasks` (pytest/e2e без Redis).
- Ретраи / мониторинг (Flower, dead-letter) — по необходимости.

## P1 — операции и кабинет

- ~~Частичная отгрузка по строке~~: `shipped_qty`, `POST .../lines/{id}/ship`, «Провести весь остаток», e2e в `transfer-and-outbound.spec.ts`.
- Резервирование остатков под заказ.
- ~~Кабинет селлера (MVP)~~: роль `fulfillment_seller`, `POST /auth/seller-accounts`, фильтр по `seller_id` (товары, селлеры, приёмка/отгрузка/движения/остатки), мутации только `fulfillment_admin`; UI и e2e `seller-cabinet.spec.ts`.

### ~~Следующие issues (E5 после MVP)~~ — сделано (в GitHub закрыты #9, #10, #11)

1. ~~[#9 — Селлер: приёмка draft](https://github.com/chivkunovd-bitdenis/WMS/issues/9)~~ — `seller_id` на заявке, UI + pytest + e2e `seller-cabinet`.
2. ~~[#10 — Селлер: отгрузка draft](https://github.com/chivkunovd-bitdenis/WMS/issues/10)~~ — то же для outbound.
3. ~~[#11 — E2E фильтр отгрузок по селлеру](https://github.com/chivkunovd-bitdenis/WMS/issues/11)~~ — `seller-outbound-filter.spec.ts`, `test_seller_outbound_list_filter.py`.

Эпик-обёртка: [#7](https://github.com/chivkunovd-bitdenis/WMS/issues/7).

**Модель изоляции:** у заявок приёмки/отгрузки колонка `seller_id` (владелец); список/`GET` для `fulfillment_seller` только по своему `seller_id`.

## P2 — интеграции и биллинг

- Wildberries импорт с моками в CI (E4) — по срезам:
  1. ~~**Токены селлера**~~: таблица `seller_wildberries_credentials`, Fernet (`integration_fernet.py`), `GET/PATCH /integrations/wildberries/sellers/{id}/tokens` (только `fulfillment_admin`; в ответе — только флаги наличия, не значения). Миграция `0011`.
  2. **Sync job**: Celery/BackgroundTasks, вызов `wildberries_client` с сохранённым токеном, идемпотентность.
  3. **UI**: кабинет/админка — «Сохранить токены», «Обновить из WB», e2e.
  4. **Маппинг**: `nmID` / `vendorCode` к SKU, список импортированных поставок (read-only).
- Уже есть: `wildberries_client.fetch_cards_list`, `GET /integrations/wildberries/status`, pytest с `httpx.MockTransport`.
- Биллинг литр‑день (E3), события от проведённых операций.

## P3 — качество e2e

- Сценарии с **явной проверкой**: экран виден, кнопка не disabled, после действия — ожидаемый текст/строка в списке.
- Для фоновых задач: `expect(...).toPass()` / таймаут до `done`.
- Не полагаться только на HTTP 200 без проверки DOM.
- Аудит спеков: везде, где после `click()` идёт `waitForResponse`, заменить на `Promise.all([wait..., click])` (см. `tests-e2e/api-waits.ts` и `AGENTS.md`).
