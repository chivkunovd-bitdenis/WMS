# Autopilot backlog

> **Контракт (читает orchestrator):**
> - Задача = строка таблицы; **id — первая ячейка**.
> - **Закрыто** = файл `.cursor/state/<id>.done` (создаёт orchestrator после verifier). **Таблицу не редактируем.**
> - **Заблокировано** = `.cursor/state/<id>.blocked` (3 фейла подряд).
> - **depends_on** — id-предшественники; задача runnable, когда все они `.done`.
> - **files** — что задача правит; две задачи с пересечением `files` **не** идут параллельно.
> - **gate** — команда проверки (зелёная = задача готова к `.done`).
> - Изоляция: каждый builder в `git worktree .cursor/wt/<id>`, коммит там.

## Активная задача: `tasks/fbs-kiz-manual-binding/TASK.md`

**Читать ТЗ целиком перед первой правкой.** Ветка `feat/fbs-kiz-manual-binding`.
Фронтенд (`frontend/`) в бэклог НЕ входит — его делает владелец сам. Ничего в `frontend/` не трогать.

Общий гейт бэка: `cd backend && ruff check . && mypy . && pytest`

## Задачи

| id | depends_on | files | gate | task |
|----|-----------|-------|------|------|
| KIZ-01 | - | backend/alembic/versions,backend/app/models/fbs_order.py,backend/app/models/marking_code.py,backend/app/models/packaging_task.py | cd backend && ruff check . && mypy . && pytest | Миграция по §4.1–4.3 ТЗ: в `fbs_order_markings` добавить `tenant_id` (FK, NOT NULL, backfill из `fbs_orders`), `source` (default `operator`), `created_by_user_id`, `created_at`; партиальный уникальный индекс `(tenant_id, kind, value) WHERE meta_status <> 'rejected'`; в `marking_codes` — `source` (default `pool`); в `packaging_task_lines` — `qty_marking_external` (int, default 0). Проверить upgrade и downgrade. |
| KIZ-02 | KIZ-01 | backend/app/services/fbs_kiz_service.py,backend/app/api/fbs_kiz.py | cd backend && ruff check . && mypy . && pytest | Новый сервис + роутер. `GET /operations/fbs-orders/kiz/lookup` по §5.1: толерантный матч стикера (`sticker_code` → `wb_barcode` → `partA+partB`), ограничение по `supply_id`, ответ с `current_kiz` и `needs_confirmation`, 404 `sticker_not_found`, 409 `order_frozen`. Тесты в `backend/tests/test_fbs_kiz.py`. |
| KIZ-03 | KIZ-02 | backend/app/services/fbs_kiz_service.py,backend/app/api/fbs_kiz.py | cd backend && ruff check . && mypy . && pytest | `POST /kiz/validate` по §5.2 — проверка пары без сохранения: дубль по `fbs_order_markings` и `marking_codes`, заморозка заказа. Ничего не пишет в БД (покрыть тестом). |
| KIZ-04 | KIZ-03 | backend/app/services/fbs_kiz_service.py,backend/app/api/fbs_kiz.py | cd backend && ruff check . && mypy . && pytest | `POST /kiz/commit` по §5.3: каждая пара своей транзакцией, построчный результат; без `confirmed` на заказе с КИЗ → `needs_confirmation`; создание `MarkingCode(source='external_fbs', status='applied', packaging_task_line_id=…)` + событие `applied`; `FbsOrderMarking(source='operator')`; отправка в WB и синк статусов переиспользуют логику `scan_order_metadata`; инкремент `qty_marking_external`. Тест частичного успеха обязателен. |
| KIZ-05 | KIZ-04 | backend/app/services/fbs_kiz_service.py,backend/app/api/fbs_kiz.py | cd backend && ruff check . && mypy . && pytest | `DELETE /operations/fbs-orders/{order_id}/kiz` по §5.4: WB `delete_marketplace_order_meta` → гашение `FbsOrderMarking` → `MarkingCode.status='void'` + событие `voided` → декремент `qty_marking_external`. При ошибке WB не менять ничего (покрыть тестом). |
| KIZ-06 | KIZ-01 | backend/app/services/marking_code_service.py,backend/app/services/packaging_task_service.py,backend/app/services/fbs_workspace_service.py | cd backend && ruff check . && mypy . && pytest | **Принцип §1.4 ТЗ.** `assert_packaging_line_marking_done` сравнивает `qty_marking_printed + qty_marking_external` с `qty_done(line)`; `_lines_needing_marking` и печать-всего вычитают `qty_marking_external`; `_build_marking_pool` исключает заказы с уже привязанным sgtin. Обязательный тест — сценарий 150/100/50 из §1.4. |
| KIZ-07 | KIZ-04,KIZ-06 | backend/app/services/marking_code_service.py,backend/app/api/marking_codes.py | cd backend && ruff check . && mypy . && pytest | Аудит по §4.3: найти все выборки `marking_codes`, показывающие инвентарь/разбивку по статусам, и добавить фильтр `source = 'pool'`, чтобы внешние коды не искажали отчётность пула. В PR — список проверенных мест файл:строка, правки только там, где нужно. |
