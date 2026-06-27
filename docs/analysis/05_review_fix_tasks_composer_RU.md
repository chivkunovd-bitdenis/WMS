# Задачи по итогам release review — для Composer

> **Источник:** `docs/analysis/04_release_implementation_review.md` (final 2026-06-27), `04_release_manifest.md`  
> **Вердикт ревью:** NOT READY — 2 блокера (упаковка auto-done, batch-короба closed)  
> **Аудитория:** Composer / builder — выполнять **строго по порядку**, одна задача за раз

---

## Правило выполнения (обязательно)

```text
1. Взять одну задачу (следующую по списку с учётом «Зависит от»).
2. Сделать минимальный diff только по scope задачи.
3. Прогнать указанный тест (pytest и/или e2e) — задача НЕ закрыта, пока тест не зелёный.
4. Локальные ворота перед следующей задачей:
   - backend: ruff check . && mypy . && pytest <указанный файл или suite>
   - frontend (если трогали UI): npm run build && npm run test:e2e <указанный spec>
5. Только после зелёного теста — следующая задача.
```

**Не объединять** несколько задач в один PR/commit без явного запроса владельца.

---

## Продуктовые решения владельца (перекрывают старый spec)

| ID | Было в spec/review | Стало (2026-06-27) |
|----|-------------------|---------------------|
| **DEC-019** | Блокировать выключение «Адресное хранение», если на ячейках есть остаток | **Не блокировать.** При выключении — **мигрировать весь остаток с ячеек на виртуальную ячейку** (зона сортировки / DEC-018). Задача **REV-FIX-003**. |
| DEC-012 | — | Уже реализовано (ship с ack при недопоставке). В этот список не входит. |

Обновить `01_normalized_process_spec.md` / `MVP_DECISIONS_RU.md` — **отдельно**, после REV-FIX-003 (задача **REV-FIX-020**).

---

## Фаза A — Блокеры релиза (P0)

Без этих двух задач сценарий «N коробов → модалка → ship с полным планом» не проходим.

### REV-FIX-001 — Убрать авто-завершение упаковки в `_touch_task`

| Поле | Значение |
|------|----------|
| **Приоритет** | P0 блокер |
| **Сценарий** | S04 |
| **Требование** | REQ-005, DEC-014 |
| **Проблема** | После pack всех строк `_touch_task` ставит `STATUS_DONE` без кнопки «Завершить упаковку» и без ЧЗ-gate в `complete_task`. |
| **Файлы** | `backend/app/services/packaging_task_service.py` (~142–143, `_touch_task`) |
| **Сделать** | Удалить/не вызывать переход в `STATUS_DONE` из `_touch_task`. Статус `done` — **только** через `complete_task` (с `acknowledge_all_packed` и `_assert_marking_done_for_task`). После pack строк задача остаётся `in_progress` (или текущий рабочий статус), пока оператор явно не завершит. |
| **Не ломать** | Reopen при смене плана (DEC-013); gate `assert_unload_packaging_done` на короба/ship. |
| **Тест (обязательно)** | pytest: дописать в `backend/tests/test_packaging_tasks.py` — после полного pack **без** `POST .../complete` статус **не** `done`; `POST .../complete` с ack → `done`. Прогон: `pytest backend/tests/test_packaging_tasks.py -q` |
| **Зависит от** | — |
| **Готово когда** | S04 критерий «завершение только явное» выполнен; существующие packaging-тесты зелёные. |

---

### REV-FIX-002 — Batch create: открытые короба (`closed_at = NULL`)

| Поле | Значение |
|------|----------|
| **Приоритет** | P0 блокер |
| **Сценарий** | S05 |
| **Требование** | REQ-007, REQ-008 |
| **Проблема** | `create_boxes_batch` создаёт короба с `closed_at=now` → scan/manual-line → `box_closed`; кнопка «Добавить товары» disabled. |
| **Файлы** | `backend/app/services/marketplace_unload_box_service.py` (`create_boxes_batch`, ~167–179); проверить `FfSuppliesShipmentsPage.tsx` (~1048, `boxClosed` / `renderBoxActions`) |
| **Сделать** | Batch-короба создавать **открытыми** (`closed_at=NULL`). Закрытие короба — отдельное явное действие (если есть в продукте), не при create. UI: «Добавить товары» активна для batch-коробов. |
| **Не ломать** | Gate упаковки; delete empty; copy box (copy может оставаться closed — см. REV-FIX-015). |
| **Тест (обязательно)** | pytest: в `backend/tests/test_marketplace_unload_and_discrepancy_acts.py` или отдельный тест — `POST .../boxes/batch` с count=3 → у каждого `closed_at is None`; `POST .../boxes/{id}/manual-line` или scan **не** 422 `box_closed`. Прогон: `pytest backend/tests/test_marketplace_unload_and_discrepancy_acts.py -k batch -q` |
| **Зависит от** | REV-FIX-001 (чтобы gate «упаковка done» можно было пройти осознанно в e2e) |
| **Готово когда** | Backend batch → open; pytest зелёный. |

---

### REV-FIX-002a — E2E: N≥2 короба + модалка «Добавить товары»

| Поле | Значение |
|------|----------|
| **Приоритет** | P0 (подтверждение блокера) |
| **Сценарий** | S05 |
| **Файлы** | `frontend/tests-e2e/ff-mp-box-add-modal.spec.ts` (новый test или расширение) |
| **Сделать** | E2e: confirm → complete packaging → создать **3** короба → у **второго** короба «Добавить товары» → модалка → добавить qty → в UI виден состав. Комментарий с **TC-NEW-MP-006** или **TC-NEW-MP-021**. |
| **Тест (обязательно)** | `npm run test:e2e -- ff-mp-box-add-modal.spec.ts` |
| **Зависит от** | REV-FIX-001, REV-FIX-002 |
| **Готово когда** | E2e зелёный; S05 можно перевести в `works` при повторном прогоне. |

---

## Фаза B — Важные несоответствия (P1)

### REV-FIX-003 — DEC-019 (новое): миграция остатков на виртуальную ячейку при выключении адресного хранения

| Поле | Значение |
|------|----------|
| **Приоритет** | P1 |
| **Сценарий** | S03 |
| **Требование** | REQ-001, DEC-018 (зона сортировки = виртуальная `StorageLocation`) |
| **Проблема** | Сейчас PATCH `address_storage_enabled=false` не меняет остатки — учёт «висит» на ячейках при выключенном режиме. |
| **Файлы** | `backend/app/services/tenant_settings_service.py`; `inventory_service.py` или сервис миграции; при необходимости `get_or_create_sorting_location` |
| **Сделать** | При переходе `address_storage_enabled: true → false`: для tenant найти все ненулевые остатки на **адресных** ячейках (не виртуальная зона); **атомарно** перенести qty на виртуальную ячейку сортировки (DEC-018); обнулить остатки на исходных ячейках. При `false → true` — **не** автомигрировать обратно (out of scope, unless already specified). UI: короткое info при сохранении «остатки перенесены на зону сортировки». |
| **Тест (обязательно)** | pytest в `backend/tests/test_tenant_settings.py` или `test_marketplace_unload_address_storage.py`: Given stock on cell A; When PATCH flag false; Then cell A qty=0, sorting location qty=sum, flag false. Negative: concurrent toggle — один winner или clear error. |
| **Зависит от** | — (можно параллельно с фазой A, но **после** REV-FIX-001 если один developer) |
| **Готово когда** | Миграция и pytest зелёные; S03 → `works` после UI copy (REV-FIX-004). |

---

### REV-FIX-004 — Настройки ФФ: сообщение при выключении адресного хранения

| Поле | Значение |
|------|----------|
| **Приоритет** | P1 |
| **Сценарий** | S03 |
| **Файлы** | `frontend/src/screens/ff/FfSettingsScreen.tsx` |
| **Сделать** | При успешном выключении — Alert/info: «Остатки с ячеек перенесены на зону сортировки» (или текст ошибки, если миграция не удалась). Не показывать старый текст про «блокировку при остатках». |
| **Тест (обязательно)** | Расширить `frontend/tests-e2e/ff-address-storage-setting.spec.ts` — после toggle off виден success/info (data-testid). |
| **Зависит от** | REV-FIX-003 |
| **Готово когда** | E2e setting green. |

---

### REV-FIX-005 — pytest: `marking_not_done` на `POST .../packaging-tasks/{id}/complete`

| Поле | Значение |
|------|----------|
| **Приоритет** | P1 |
| **Сценарий** | S04 |
| **Требование** | DEC-014 |
| **Проблема** | ЧЗ-gate в коде есть, отдельного негативного теста на complete нет. |
| **Файлы** | `backend/tests/test_packaging_tasks.py` |
| **Сделать** | Given маркированная строка без напечатанных кодов; When complete с `acknowledge_all_packed=true`; Then 422 `marking_not_done` (или актуальный код из API). |
| **Тест (обязательно)** | `pytest backend/tests/test_packaging_tasks.py -k marking_not_done -q` |
| **Зависит от** | REV-FIX-001 |
| **Готово когда** | Тест зелёный. |

---

### REV-FIX-006 — Вкладка «Упаковка» доступна при наличии `linked_packaging_task` (не только после confirm)

| Поле | Значение |
|------|----------|
| **Приоритет** | P1 |
| **Сценарий** | S02, S04 |
| **Требование** | DEC-003, REQ-004 |
| **Проблема** | `PackagingTask` создаётся при create draft, но Tab disabled до `status=confirmed`. |
| **Файлы** | `frontend/src/screens/ff/FfSuppliesShipmentsPage.tsx` (~1927–1934, условие `disabled={!mpConfirmed}`) |
| **Сделать** | Вкладка «Упаковка» enabled, если `linked_packaging_task != null` (draft/submitted/confirmed). Вкладки «Короба» и «Финальная отгрузка» — **оставить** gated по confirm (или по отдельному правилу ниже — не смешивать в этой задаче). Встроить `FfPackagingTaskPanel` на draft. |
| **Тест (обязательно)** | `frontend/tests-e2e/ff-mp-tabs.spec.ts` — на **draft** после create FF отгрузки вкладка «Упаковка» кликабельна, панель видна (`data-testid` packaging). |
| **Зависит от** | REV-FIX-001 |
| **Готово когда** | E2e green; оператор видит упаковку на черновике. |

---

### REV-FIX-007 — Убрать misleading copy «упаковка появится после подтверждения»

| Поле | Значение |
|------|----------|
| **Приоритет** | P1 |
| **Сценарий** | S02, S04 |
| **Файлы** | `frontend/src/screens/ff/FfSuppliesShipmentsPage.tsx` (~2107–2109) |
| **Сделать** | Заменить placeholder: если есть `linked_packaging_task` — показать панель/текст «Задание упаковки создано»; если нет — нейтральный empty state. Удалить фразу «появится после подтверждения». |
| **Тест (обязательно)** | Assert в `ff-mp-tabs.spec.ts`: на draft **нет** текста «после подтверждения» (или regex из copy). |
| **Зависит от** | REV-FIX-006 |
| **Готово когда** | E2e green. |

---

### REV-FIX-008 — Индикатор прогресса упаковки на draft/submitted

| Поле | Значение |
|------|----------|
| **Приоритет** | P1 |
| **Сценарий** | S02 |
| **Файлы** | `frontend/src/screens/ff/FfSuppliesShipmentsPage.tsx` (~1875–1877, `ff-mp-packaging-progress`) |
| **Сделать** | Показывать `ff-mp-packaging-progress`, когда есть `linked_packaging_task`, не только при `mpConfirmed`. |
| **Тест (обязательно)** | `ff-mp-tabs.spec.ts` — на draft виден progress testid. |
| **Зависит от** | REV-FIX-006 |
| **Готово когда** | E2e green. |

---

### REV-FIX-009 — Убрать legacy «один открытый короб» при count=1 в batch UI

| Поле | Значение |
|------|----------|
| **Приоритет** | P1 |
| **Сценарий** | S05 |
| **Проблема** | count=1 идёт в `create_open_box`; `open_box_exists` блокирует второй — не модель «N независимых коробов». |
| **Файлы** | `frontend/src/screens/ff/FfSuppliesShipmentsPage.tsx` (~705–729); `marketplace_unload_box_service.py` |
| **Сделать** | Единый путь: count≥1 → `create_boxes_batch` (открытые короба). Deprecate или ограничить `create_open_box` только если нужен для миграции старых данных — в UI не вызывать. |
| **Тест (обязательно)** | pytest: два последовательных batch create по 1 коробу — оба успешны, без `open_box_exists`. E2e: создать 1, потом ещё 1 через batch — оба с «Добавить товары». |
| **Зависит от** | REV-FIX-002 |
| **Готово когда** | Pytest + e2e green. |

---

### REV-FIX-010 — Alert на вкладке «Короба» при packaging gate

| Поле | Значение |
|------|----------|
| **Приоритет** | P1 |
| **Сценарий** | S05 |
| **Файлы** | `frontend/src/screens/ff/FfSuppliesShipmentsPage.tsx` (вкладка «Короба») |
| **Сделать** | Когда `mpPackagingGateActive` — `Alert` на вкладке (не только disabled-кнопки): «Сначала завершите упаковку товара» (`data-testid="ff-mp-packaging-gate-alert"`). |
| **Тест (обязательно)** | `frontend/tests-e2e/ff-mp-packaging-gate.spec.ts` — assert alert visible на tab «Короба». |
| **Зависит от** | REV-FIX-001 |
| **Готово когда** | E2e green. |

---

## Фаза C — UX и copy (P2, после P0/P1)

### REV-FIX-011 — Описание страницы «Отгрузки на МП»: убрать «подбор по ячейкам»

| Поле | Значение |
|------|----------|
| **Приоритет** | P2 |
| **Сценарий** | S02, S07 |
| **Файлы** | `frontend/src/screens/ff/FfSuppliesShipmentsPage.tsx` (~1616) |
| **Сделать** | Обновить subtitle/description: план → упаковка → короба → финал; без «общего подбора» и «подбор по ячейкам». |
| **Тест (обязательно)** | `ff-mp-tabs.spec.ts` или snapshot текста — нет фразы «подбор по ячейкам». |
| **Зависит от** | — |
| **Готово когда** | E2e/assert green. |

---

### REV-FIX-012 — Селлер: подсказка после «Запланировано»

| Поле | Значение |
|------|----------|
| **Приоритет** | P2 |
| **Сценарий** | S01 |
| **Файлы** | `frontend/src/components/SellerMarketplaceUnloadDialog.tsx` (~671–674) |
| **Сделать** | После submit в статус «Запланировано» — `Alert` или вторичный текст: «Дальше заявку обрабатывает фулфилмент». |
| **Тест (обязательно)** | `frontend/tests-e2e/seller-mp-unload.spec.ts` — после plan visible hint (`data-testid="seller-mp-ff-handoff-hint"`). |
| **Зависит от** | — |
| **Готово когда** | E2e green. |

---

### REV-FIX-013 — Сводка «план / распределено» на черновике или вкладке «Товары»

| Поле | Значение |
|------|----------|
| **Приоритет** | P2 |
| **Сценарий** | S02, S08, DEC-010 |
| **Файлы** | `frontend/src/screens/ff/FfSuppliesShipmentsPage.tsx` (`mpCollectSummary`, вкладка «Товары») |
| **Сделать** | Показать aggregate «План N шт» на draft (вкладка «Товары»); опционально «Распределено» если confirm + короба (может оставаться 0 на draft). |
| **Тест (обязательно)** | `ff-mp-tabs.spec.ts` — на draft виден `ff-mp-plan-total` или существующий summary с plan count. |
| **Зависит от** | REV-FIX-006 (желательно) |
| **Готово когда** | E2e green. |

---

### REV-FIX-014 — Сводка/warning «Короба» только после confirm — документировать или смягчить

| Поле | Значение |
|------|----------|
| **Приоритет** | P2 |
| **Сценарий** | S08, S09 |
| **Проблема** | `mpCollectSummary` и `ff-mp-collect-warning` только при `confirmed` — до confirm оператор не видит прогресс распределения. |
| **Файлы** | `FfSuppliesShipmentsPage.tsx` |
| **Сделать** | **Вариант MVP:** после REV-FIX-013 на «Товары» показывать plan total; на «Короба» summary оставить после confirm. Если вкладка «Короба» открыта после confirm — без изменений. Задача — только если продукт хочет summary до confirm на «Короба» (тогда enabled tab «Короба» read-only на draft — **отдельное решение, не делать без запроса**). |
| **Тест (обязательно)** | Регрессия `ff-mp-tabs.spec.ts` — warning при partial distribution после confirm без изменений. |
| **Зависит от** | REV-FIX-013 |
| **Готово когда** | Регрессия green. |

---

### REV-FIX-015 — Copy box: closed короб — зафиксировать поведение (без изменения или doc)

| Поле | Значение |
|------|----------|
| **Приоритет** | P2 |
| **Сценарий** | S08 |
| **Проблема** | `copy_box` создаёт closed короб — add заблокирован; для copy сценария приемлемо. |
| **Сделать** | **Минимум:** комментарий в коде + строка в `docs/DATA_FLOW.md`. **Опционально:** copy → open box — только если продукт попросит. |
| **Тест (обязательно)** | Существующий pytest `test_marketplace_unload_box_copy*` — убедиться green после REV-FIX-002 (batch open не сломал copy). |
| **Зависит от** | REV-FIX-002 |
| **Готово когда** | Pytest green; doc обновлён если меняли поведение. |

---

### REV-FIX-016 — Legacy API `PUT .../pick-allocations` — deprecated

| Поле | Значение |
|------|----------|
| **Приоритет** | P2 |
| **Сценарий** | S07 |
| **Файлы** | `backend/app/api/marketplace_unload_requests.py` (~1065–1094); OpenAPI/description |
| **Сделать** | Пометить endpoint `deprecated=True` в FastAPI; docstring «admin-only, обход коробов; не использовать в UI». **Не удалять** в этом релизе без отдельного решения. |
| **Тест (обязательно)** | Существующий `test_marketplace_unload_pick_allocations_admin_only` — green. |
| **Зависит от** | — |
| **Готово когда** | Pytest green. |

---

### REV-FIX-017 — Cancel: откат в sorting zone — зафиксировать в DATA_FLOW

| Поле | Значение |
|------|----------|
| **Приоритет** | P2 |
| **Сценарий** | S06 |
| **Файлы** | `docs/DATA_FLOW.md`; ссылка на `marketplace_unload_collect_service.py:469–505` |
| **Сделать** | Явно описать: cancel возвращает qty в **зону сортировки**, не в исходную ячейку collect; total stock восстанавливается. |
| **Тест (обязательно)** | `pytest backend/tests/test_marketplace_unload_and_discrepancy_acts.py -k cancel -q` — без изменения поведения. |
| **Зависит от** | — |
| **Готово когда** | Doc + pytest green. |

---

### REV-FIX-018 — UI feedback «остаток уменьшен» после add в короб (optional MVP)

| Поле | Значение |
|------|----------|
| **Приоритет** | P2 (можно отложить) |
| **Сценарий** | S06 |
| **Файлы** | `FfMarketplaceUnloadBoxAddDialog.tsx`, `FfSuppliesShipmentsPage.tsx` |
| **Сделать** | После успешного add — Snackbar «Добавлено N шт» (уже может быть) + опционально «Доступно на складе: X» если API отдаёт. **Skip**, если API не отдаёт available без лишнего запроса. |
| **Тест (обязательно)** | E2e `ff-mp-box-add-modal.spec.ts` — после add виден success snackbar testid. |
| **Зависит от** | REV-FIX-002a |
| **Готово когда** | E2e green или задача явно skipped в TASKLOG. |

---

### REV-FIX-019 — E2E сквозной: seller plan → FF confirm → N коробов → ship

| Поле | Значение |
|------|----------|
| **Приоритет** | P2 (рекомендуется после P0) |
| **Сценарий** | S01→S09 |
| **Файлы** | новый `frontend/tests-e2e/ff-mp-full-flow.spec.ts` или расширение существующих |
| **Сделать** | Один spec: seller создаёт plan → FF confirm → packaging complete → batch 2 короба → fill both → final tab → ship (full plan). TC-ID в комментарии. |
| **Тест (обязательно)** | `npm run test:e2e -- ff-mp-full-flow.spec.ts` |
| **Зависит от** | REV-FIX-001, REV-FIX-002a, REV-FIX-006 |
| **Готово когда** | E2e green. |

---

### REV-FIX-020 — Обновить spec: DEC-019 → миграция на виртуальную ячейку

| Поле | Значение |
|------|----------|
| **Приоритет** | P2 (docs) |
| **Файлы** | `docs/analysis/01_normalized_process_spec.md`, `docs/MVP_DECISIONS_RU.md`, строка S03 в `04_release_manifest.md` |
| **Сделать** | Заменить формулировку DEC-019: не block toggle, а migrate to sorting virtual location. |
| **Тест (обязательно)** | N/A (docs); sanity: grep DEC-019 — одна каноническая формулировка. |
| **Зависит от** | REV-FIX-003 |
| **Готово когда** | Docs согласованы с TASKLOG TASK-021. |

---

## Фаза D — Не входит в этот релиз (backlog)

| ID | Тема | Примечание |
|----|------|------------|
| REV-BACKLOG-001 | Inline «Сборка в короба» vs только модалка | S07 — UX polish, не блокер REQ-003 |
| REV-BACKLOG-002 | Удалить `PUT pick-allocations` полностью | После периода deprecated |
| REV-BACKLOG-003 | Вкладка «Финал» до confirm (prefill даты/склада) | S09 — nice-to-have |
| REV-BACKLOG-004 | Имя папки репозитория `WMS ` (trailing space) | R-12 из independent review |

---

## Рекомендуемый порядок для Composer (очередь)

```text
REV-FIX-001 → тест
REV-FIX-002 → тест
REV-FIX-002a → e2e
REV-FIX-005 → тест
REV-FIX-006 → e2e
REV-FIX-007 → e2e
REV-FIX-008 → e2e
REV-FIX-010 → e2e
REV-FIX-009 → pytest + e2e
REV-FIX-003 → pytest
REV-FIX-004 → e2e
REV-FIX-020 → docs
REV-FIX-011 … REV-FIX-019 — по приоритету P2
```

**Критерий «можно выкатывать» (повтор release review):**

- S04 → `works` (после 001, 005, 006–008)
- S05 → `works` (после 001, 002, 002a, 009, 010)
- S03 → `works` (после 003, 004, 020)
- Полный pytest unload suite + e2e mp-* green

---

## Чеклист для PR (каждая задача)

- [ ] Scope одной REV-FIX-* 
- [ ] Указанный тест добавлен/обновлён с TC-ID в комментарии
- [ ] `ruff` + `mypy` + pytest (и build/e2e если UI)
- [ ] TASKLOG.md — строка «What changed» для задачи
- [ ] Не смешивать DEC-019 block guard (отменено) с миграцией (REV-FIX-003)

---

## Ссылки

- Release review: `docs/analysis/04_release_implementation_review.md`
- Manifest сценариев: `docs/analysis/04_release_manifest.md`
- TASKLOG DEC-019: `TASKLOG.md` (TASK-021)
- E2e правила: `AGENTS.md` (waitForResponse parallel, data-testid)
