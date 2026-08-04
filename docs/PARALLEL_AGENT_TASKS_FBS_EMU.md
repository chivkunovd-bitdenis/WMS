# Параллельный реестр — fbs-wb-emulator

> Источник задачи: `tasks/fbs-wb-emulator/TASK.md`  
> Оркестратор: Grok. Воркеры: `composer-2.5` only. Hook: stop → continue pool.

---

## КОНТРАКТ ДЛЯ ОРКЕСТРАТОРА

1. **Не параллелить** задачи с пересечением `files`.
2. Соблюдать **`depends_on`** → runnable только если у всех предшественников есть `.cursor/state/<id>.done`.
3. **`EMU-000` — ГЕЙТ 1 (человек).** Пока нет `.done` — **код не писать**. Оркестратор ставит `.done` только после явного «ок» / `Agent` в чате и записи в `02-arch-decision.md`.
4. Одна `lane` — последовательно; разные lane — параллельно после зависимостей.
5. Worktree: `.cursor/wt/<id>`, ветка `task/<id>`, база = HEAD **integration branch**.
6. Цикл: builder → verifier → adversarial-reviewer → integration-guard → integrate → `.integrated` + `.done`.
7. **Код WMS (`backend/app/**`) не трогать** — только новый сервис + test compose/env.
8. Прод-compose (`docker-compose.prod.yml`) — **не** добавлять эмулятор.

**integration_branch:** `feat/fbs-wb-emulator`

**parallel_workers:** `3` (после EMU-010 одновременно до 3 lane: ORDERS / SUPPLIES / MEDIA+ADMIN+COMPOSE по файлам)

**Принцип продукта:** эмулятор = HTTP-сервис «как WB Marketplace API v3»; WMS переключается **только** `WILDBERRIES_MARKETPLACE_API_BASE`. Контракт = то, что читает `backend/app/services/wildberries_client.py` (1:1 поля).

---

## EMU-000 — БАРЬЕР: ГЕЙТ 1 арх + стек

- **files:** `tasks/fbs-wb-emulator/00-triage.md`, `tasks/fbs-wb-emulator/01-analysis.md`, `tasks/fbs-wb-emulator/02-arch-decision.md`, `tasks/fbs-wb-emulator/contract-from-client.md`
- **depends_on:** `—`
- **do:** Wave-0 (docs only): триаж, анализ, таблица эндпоинтов из `wildberries_client.py`, черновик арх+стек. **Код запрещён.** Оркестратор ждёт «ок» человека → пишет ✅ в `02-arch-decision.md` → `.done`.
- **gate:** в `02-arch-decision.md` статус ГЕЙТ 1 = ✅; таблица контракта покрывает все `MARKETPLACE_*_PATH` из клиента.
- **closed:** _(после ок человека)_

---

## LANE-SCAFFOLD — каркас сервиса (`wb_emulator/`)

> **files (lane):** `wb_emulator/__init__.py`, `wb_emulator/main.py`, `wb_emulator/settings.py`, `wb_emulator/auth.py`, `wb_emulator/db.py`, `wb_emulator/models.py`, `wb_emulator/Dockerfile`, `wb_emulator/requirements.txt`, `wb_emulator/README.md`

| id | depends_on | title | do | gate |
|----|-----------|-------|----|------|
| EMU-010 | EMU-000 | Scaffold + SQLite + auth | FastAPI-приложение: settings (токены TOKEN→seller_key из env/файла), SQLite на volume, middleware `Authorization` (unknown → 401), пустой router mount, health. Без бизнес-ручек WB. | `GET /health` 200; unknown token на любом `/api/v3/*` → 401; SQLite файл создаётся |

---

## LANE-ORDERS — заказы

> **files:** `wb_emulator/routes/orders.py`, `wb_emulator/services/orders_store.py`, `wb_emulator/tests/test_orders_contract.py`

| id | depends_on | title | do | gate |
|----|-----------|-------|----|------|
| EMU-020 | EMU-010 | Orders API 1:1 | Реализовать по `contract-from-client.md`: `GET /orders/new`, `GET /orders`, `POST /orders/status`, `PATCH /orders/{id}/cancel`. Поля ответа = то, что читает клиент (camelCase). | pytest контракта orders зелёный; форма как клиент |

---

## LANE-SUPPLIES — поставки + trbx

> **files:** `wb_emulator/routes/supplies.py`, `wb_emulator/services/supplies_store.py`, `wb_emulator/tests/test_supplies_contract.py`

| id | depends_on | title | do | gate |
|----|-----------|-------|----|------|
| EMU-030 | EMU-010 | Supplies + trbx | `POST/GET supplies`, add order, deliver, barcode hook-point, trbx create/patch/stickers — строго по клиенту. | pytest supplies контракта зелёный |

---

## LANE-MEDIA — стикеры / QR / meta КИЗ

> **files:** `wb_emulator/routes/media_meta.py`, `wb_emulator/services/stickers.py`, `wb_emulator/services/marking_meta.py`, `wb_emulator/tests/test_media_meta_contract.py`

| id | depends_on | title | do | gate |
|----|-----------|-------|----|------|
| EMU-040 | EMU-010 | Stickers + meta/KIZ | PNG Code128 + QR (python-barcode/qrcode); `POST /orders/stickers`, supply barcode, trbx stickers; GET/PUT meta; КИЗ с `ERR` → check_status=error; иначе ok (сразу или через N сек). | pytest: валидный PNG; ERR блокирует логику check_status |

---

## LANE-ADMIN — админ + seed

> **files:** `wb_emulator/routes/admin.py`, `wb_emulator/seed/`, `wb_emulator/tests/test_admin.py`

| id | depends_on | title | do | gate |
|----|-----------|-------|----|------|
| EMU-050 | EMU-010 | Admin + seed fixtures | `/__admin/orders`, `/__admin/orders/{id}/wb-event`, `/__admin/state`; seed JSON seller→баркоды/nmId. | POST admin создаёт заказы → видны в `/orders/new` |

---

## LANE-COMPOSE — стыковка тест-контура

> **files:** `docker-compose.emulator.yml`, `wb_emulator/.env.example` (и **только** комментарий/override в test compose; **не** `docker-compose.prod.yml`)

| id | depends_on | title | do | gate |
|----|-----------|-------|----|------|
| EMU-060 | EMU-010 | Compose + env | Сервис `wb-emulator`, volume SQLite, mount seed; для api/celery_* в **test** override: `WILDBERRIES_MARKETPLACE_API_BASE=http://wb-emulator:<port>`. Прод-файл чист. | `rg` по prod — нет эмулятора; emulator поднимается |

---

## LANE-TESTS — сборка цикла

> **files:** `wb_emulator/tests/test_full_cycle.py`, `tasks/fbs-wb-emulator/03-contract.md`, `tasks/fbs-wb-emulator/04-test-cases.md`

| id | depends_on | title | do | gate |
|----|-----------|-------|----|------|
| EMU-070 | EMU-020, EMU-030, EMU-040, EMU-050, EMU-060 | Full-cycle + TC | Интеграционный happy-path + негатив ERR/401/мультиселлер; заполнить 03/04 из TASK TC-NEW-FBS-EMU-00*. | pytest full cycle зелёный; 04-test-cases.md с TC |

---

## LANE-REVIEW — независимый проход + док

> **files:** `tasks/fbs-wb-emulator/05-review.md`, `tasks/fbs-wb-emulator/06-doc.md`, `docs/` (короткая заметка про эмулятор, если нужно)

| id | depends_on | title | do | gate |
|----|-----------|-------|----|------|
| EMU-080 | EMU-070 | Review artifacts + doc | Не писать код WMS; сверить анти-косяк чеклист TASK.md; 05-review + 06-doc. | 05 APPROVE/WARNINGS; прод чист; WMS app не изменён |
