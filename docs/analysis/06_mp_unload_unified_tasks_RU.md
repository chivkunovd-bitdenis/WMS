# Единый реестр задач: отгрузка на маркетплейс (rework)

> **Версия:** 2026-06-27 (финальная итерация обсуждения с владельцем)  
> **Источник истины по продукту:** `docs/analysis/01_normalized_process_spec.md`  
> **Аудитория:** builder / Composer — выполнять **по одной задаче**, зелёный тест перед следующей  
> **Этот документ заменяет** как рабочий backlog: `02_technical_builder_plan.md` (TASK-001…018), очередь `05_review_fix_tasks_composer_RU.md` (REV-FIX-001…020) — там, где указано «ОТМЕНЕНО» или «ПЕРЕОПРЕДЕЛЕНО».

---

## 1. Зачем этот документ

В ходе нескольких итераций накопились **три слоя** артефактов:

| Документ | Что в нём | Статус |
|----------|-----------|--------|
| `01_normalized_process_spec.md` | Актуальные требования владельца (2026-06-27) | **Канон** |
| `02_technical_builder_plan.md` | TASK-001…018 под **старый** процесс | **Устарел** (частично реализован, частично противоречит 01) |
| `05_review_fix_tasks_composer_RU.md` | REV-FIX после release review **старой** модели | **Частично устарел** (gate упаковки, упаковка на draft и т.д.) |

Здесь — **один нарезанный список** с ID `MP-xxx`, зависимостями, файлами, критериями «готово» и тестами.

---

## 2. Целевая модель (краткая справка)

### 2.1. Статусы документа `MarketplaceUnloadRequest`

| Код | Подпись в UI | Когда |
|-----|--------------|-------|
| `draft` | Черновик | Создан, редактируется |
| `submitted` | **На утверждении** | Селлер отправил план ФФ |
| `confirmed` | **Утверждено** | ФФ нажал «Утвердить»; если отгрузку создал ФФ — сразу после утверждения |
| `collecting` | **На сборке** | **Новый.** Первый короб отгрузки **или** первый добавленный товар (что раньше) |
| `shipped` | **Отгружено** | Финальный ship, остаток списан |
| `cancelled` | Отменено | Без изменений |

Отдельного статуса «упаковка» на документе **нет**.

### 2.2. Два параллельных потока (порядок не важен)

```text
┌─────────────────────┐     ┌─────────────────────┐
│  Сборка в короба    │     │  Упаковка (задание) │
│  ячейки только тут  │     │  без ячеек/«полки»  │
│  WHB scan на        │     │  прогресс = счётчик │
│  вкладке «Товары»   │     │  в PackagingTask    │
└──────────┬──────────┘     └──────────┬──────────┘
           │                           │
           └───────────┬───────────────┘
                       ▼
              «Отгружено» (ship)
              упаковка done + ЧЗ + короба*
```

\* Короба: см. допущение **A-003** — ship по-прежнему требует распределение по коробам, если не скажете иначе.

### 2.3. UI документа

| Элемент | Целевое поведение |
|---------|-------------------|
| Вкладки | Только **«Товары»** и **«Упаковка»**. Вкладки **«Короба»** и **«Финальная отгрузка»** — **убрать** |
| Шапка | Склад FF + дата отгрузки — с момента создания |
| Footer | **«Утвердить»** / **«Отгружено»** — как у других документов (не на отдельной вкладке) |
| Плашка прогресса упаковки | **Не на черновике** (до сохранения/утверждения) |
| «Продолжить упаковку» | **Не в общем баннере** — только контекст вкладки «Упаковка» |
| Короба | Списки, создание, печать ШК — на вкладке **«Товары»** |

### 2.4. Упаковка

- `PackagingTask` создаётся **только при `confirmed`**, на **весь план** (все строки).
- Можно упаковывать **до / во время / после** сборки коробов.
- **Незавершённая упаковка не блокирует** создание и наполнение коробов.
- Колонку **«На полке упак.»** — **убрать**.
- «Упаковать» = **прогресс в задании**, **без** `apply_packaging_convert` и **без** `insufficient_unpacked` по ячейкам.
- Ship — только при **завершённом** задании упаковки + ЧЗ где нужно.

### 2.5. Сборка и scan

| Зона | Что понимает scan |
|------|-------------------|
| **Вкладка «Товары»** (главная строка) | **Только короб** (WHB) — добавить готовый короб в отгрузку |
| **Большая модалка** наполнения короба | **Ячейка**, **товар**, **готовый короб**; ручной pick «ячейка → товар → qty» |

**Attach готового короба (цепочка приёмки ячейка → короб → товар):**

1. Модалка: «Весь короб будет добавлен в отгрузку» — OK / Отмена.
2. Если в коробе **больше плана** — второе предупреждение; при **OK** весь товар **включая сверх плана**.
3. Результат **неотличим** от короба, наполненного вручную.

### 2.6. Печать (только вкладка «Упаковка»)

- Иконка печати → **всегда умный конструктор** (`MarkingPrintDialog`), не `ProductBarcodePrintDialog`.
- Блок **ЧЗ** — только если у товара признак ЧЗ.
- Поле **«сколько этикеток на каждый товар»** (число).
- После OK — **полная лента** по layout конструктора × qty к упаковке × этикеток на товар.

---

## 3. Что устарело — не делать / откатить

Следующие пункты **противоречат** `01_normalized_process_spec.md`. Если уже в коде — **переделать** в рамках задач MP-003…MP-006.

| Старый ID | Было | Стало (2026-06-27) | Действие |
|-----------|------|---------------------|----------|
| TASK-006 / DEC-003 / DEC-008 | Task упаковки при create draft + sync строк | Task **только при confirm** | **MP-003**, **MP-004** |
| TASK-008 / REV-FIX-010 | Gate: короба только после упаковки done | Упаковка **не блокирует** короба | **MP-005**, **MP-006** |
| REV-FIX-006, 007, 008 | Вкладка упаковки и прогресс **на draft** | Плашка **не на draft**; упаковка после confirm | **MP-004**, **MP-012** |
| TASK-012 (часть) | 4 вкладки включая «Короба» и «Финал» | 2 вкладки | **MP-010…MP-014** |
| `record_pack_progress` + «На полке» | Списание unpacked по ячейке | Счётчик в task | **MP-007**, **MP-008** |
| `plan_limit_exceeded` hard reject | Attach короба обрезается | OK → **весь короб** | **MP-019** |
| ProductBarcodePrint на упаковке | Простая печать 58×40 | Единый конструктор | **MP-021…MP-023** |

**Сохраняется из REV-FIX (актуально):**

| REV-FIX | Тема | Новый ID |
|---------|------|----------|
| REV-FIX-001 | Нет auto-done в `_touch_task` | **MP-002** |
| REV-FIX-002 | Batch короба открытые (`closed_at=NULL`) | **MP-015** |
| REV-FIX-002a | E2E N≥2 короба + модалка | **MP-016** (обновить сценарий: **без** gate упаковки) |
| REV-FIX-005 | pytest marking_not_done на complete | **MP-009** |
| REV-FIX-003, 004 | DEC-019 миграция на зону сортировки | **MP-024**, **MP-025** |
| REV-FIX-009 | Единый batch path (не один open box) | **MP-017** |
| REV-FIX-011…012, 015…020 | Copy, docs, seller hint, e2e full flow | **MP-026…MP-032** (с правками flow) |

**Явно отменено:**

| ID | Причина |
|----|---------|
| REV-FIX-010 | Gate alert на «Короба» — gate **снимается** |
| REV-FIX-006, 007, 008 | Упаковка/progress на draft — **наоборот**, не показывать на draft |

---

## 4. Матрица требований → задачи

| REQ из 01 | Кратко | Задачи MP |
|-----------|--------|-----------|
| REQ-001 | Статус `collecting` | MP-001 |
| REQ-002 | UI: 2 вкладки, footer | MP-010…MP-014 |
| REQ-003 | Плашка не на draft | MP-012 |
| REQ-004 | Task только после confirm | MP-003, MP-004 |
| REQ-005 | Упаковка без ячеек | MP-007, MP-008 |
| REQ-006 | Короба без gate | MP-005, MP-006 |
| REQ-007 | Модалка pick/scan | MP-018 |
| REQ-008 | Scan WHB на «Товарах» | MP-020 |
| REQ-009 | Attach готового короба | MP-019 |
| REQ-010 | Переполнение плана OK | MP-019 |
| REQ-011 | Конструктор печати | MP-021…MP-023 |
| REQ-012 | Ship + упаковка + ЧЗ | MP-033 (регрессия) |

---

## 5. Правило выполнения

```text
1. Одна задача MP-xxx за раз (минимальный diff).
2. Указанный тест — зелёный до следующей задачи.
3. Backend: ruff check . && mypy . && pytest <scope>
4. Frontend: npm run build && npm run test:e2e <spec>
5. TASKLOG.md — строка на задачу (поведение, не «галочка»).
6. PR: блок ### Test coverage с TC-ID (AGENTS.md).
```

---

## 6. Фаза A — Backend: статусы и упаковка (P0)

### MP-001 — Статус `collecting` («На сборке»)

| Поле | Значение |
|------|----------|
| **Приоритет** | P0 |
| **Требование** | REQ-001, BR из Step 3 |
| **Проблема** | В коде нет `collecting`; переход не выполняется |
| **Файлы** | `backend/app/models/marketplace_unload.py` (enum/constraint если есть); `backend/app/services/marketplace_unload_service.py`; `backend/app/services/marketplace_unload_box_service.py`; `backend/app/services/marketplace_unload_collect_service.py`; миграция Alembic если status — CHECK/enum в БД; `frontend/src/screens/ff/FfSuppliesShipmentsPage.tsx` (label) |
| **Сделать** | 1) Добавить статус `collecting`. 2) При **первом** `MarketplaceUnloadBox` create **или** первом успешном add line / attach — если status был `confirmed`, перевести в `collecting`. 3) UI: chip/label «На сборке». 4) Ship из `collecting` и `confirmed` (если уже собирали) — по текущим правилам ship. |
| **Не ломать** | Переходы `submitted`→`confirmed`; cancel; shipped terminal |
| **Тест** | pytest: confirm → create box → status `collecting`; confirm → attach line без box → `collecting`. Обновить API schema tests. |
| **Зависит от** | — |
| **Готово когда** | pytest green; в UI виден статус после первого короба/товара |

---

### MP-002 — Явное завершение упаковки (не auto-done)

| Поле | Значение |
|------|----------|
| **Приоритет** | P0 |
| **Источник** | REV-FIX-001 |
| **Требование** | REQ-012, ship gate |
| **Проблема** | `_touch_task` ставит `STATUS_DONE` после pack всех строк |
| **Файлы** | `backend/app/services/packaging_task_service.py` (`_touch_task`, ~142–143) |
| **Сделать** | Убрать переход в `done` из `_touch_task`. `done` — **только** через `complete_task` (`acknowledge_all_packed` + ЧЗ gate). |
| **Не ломать** | Reopen при смене плана; `assert_unload_packaging_done` на **ship** (не на короба) |
| **Тест** | `pytest backend/tests/test_packaging_tasks.py` — full pack без complete → status **не** `done`; complete с ack → `done` |
| **Зависит от** | — |
| **Готово когда** | pytest green |

---

### MP-003 — Убрать sync упаковки на draft (task только при confirm)

| Поле | Значение |
|------|----------|
| **Приоритет** | P0 |
| **Требование** | REQ-004, BR-008, GAP-003 |
| **Проблема** | `_sync_packaging_task_for_unload` при create/edit draft |
| **Файлы** | `backend/app/services/marketplace_unload_service.py`; `packaging_task_service.py` (`ensure_task_for_unload`) |
| **Сделать** | 1) Не создавать `PackagingTask` на draft/submitted. 2) Создавать/пересобирать строки task **только** в `confirm_request` (на полный план). 3) При изменении плана **после** confirm — существующая логика reopen/sync (DEC-013) сохраняется. |
| **Тест** | pytest: draft create → **нет** `linked_packaging_task`; confirm → task есть, lines = plan qty |
| **Зависит от** | MP-002 |
| **Готово когда** | pytest green; draft без task в API detail |

---

### MP-004 — Backend: упаковка для MP-unload без ячеек

| Поле | Значение |
|------|----------|
| **Приоритет** | P0 |
| **Требование** | REQ-005, BR-002, GAP-002 |
| **Проблема** | `record_pack_progress` → `apply_packaging_convert` по `storage_location_id`; ошибки `insufficient_unpacked` |
| **Файлы** | `backend/app/services/packaging_task_service.py` (`record_pack_progress`, `_touch_task`); возможно ветка по `task.source == marketplace_unload` |
| **Сделать** | Для заданий, привязанных к `MarketplaceUnloadRequest`: «Упаковать» увеличивает `qty_packed` на строке **без** движения `InventoryBalance` / без требования ячейки. Валидация: `qty_packed <= qty_planned` на строке. |
| **Не ломать** | Обычная упаковка **не** MP-linked (если есть) — поведение отдельно или явно тот же счётчик по решению |
| **Тест** | pytest: MP task pack без location → 200; qty_packed растёт; inventory unchanged |
| **Зависит от** | MP-003 |
| **Готово когда** | pytest green |

---

### MP-005 — Снять gate упаковки с create/collect коробов (backend)

| Поле | Значение |
|------|----------|
| **Приоритет** | P0 |
| **Требование** | REQ-006, BR-001, GAP-001 |
| **Проблема** | `assert_unload_packaging_done` в box/collect |
| **Файлы** | `backend/app/services/marketplace_unload_box_service.py`; `backend/app/services/marketplace_unload_collect_service.py` |
| **Сделать** | Удалить вызовы `assert_unload_packaging_done` из create box, batch, collect, attach, manual-line. **Оставить** на `ship_request` только. |
| **Тест** | pytest: confirmed + packaging `in_progress` → create box OK; collect OK; ship → 422 until done |
| **Зависит от** | MP-003 |
| **Готово когда** | pytest green; тесты `ff-mp-packaging-gate` backend inverted |

---

### MP-006 — Снять gate упаковки в UI коробов

| Поле | Значение |
|------|----------|
| **Приоритет** | P0 |
| **Требование** | REQ-006, BR-001 |
| **Проблема** | `mpPackagingGateActive` disables кнопки; REV-FIX-010 alert |
| **Файлы** | `frontend/src/screens/ff/FfSuppliesShipmentsPage.tsx`; `frontend/src/screens/ff/FfMarketplaceUnloadBoxAddDialog.tsx`; удалить/переписать `frontend/tests-e2e/ff-mp-packaging-gate.spec.ts` |
| **Сделать** | 1) Убрать блокировку create/add при незавершённой упаковке. 2) Удалить alert «Сначала завершите упаковку» на коробах. 3) E2e: короба доступны **до** complete packaging. |
| **Тест** | e2e: confirm → create box **без** complete packaging → success |
| **Зависит от** | MP-005 |
| **Готово когда** | e2e green |

---

### MP-007 — UI: убрать колонку «На полке упак.»

| Поле | Значение |
|------|----------|
| **Приоритет** | P0 |
| **Требование** | REQ-005, BR-002 |
| **Файлы** | `frontend/src/screens/ff/FfPackagingPage.tsx`; `FfSuppliesShipmentsPage.tsx` (embedded panel если есть); API response mapping `qty_suggested_packed` — можно оставить в API, не показывать |
| **Сделать** | Убрать колонку и любые подсказки про «полку» для MP-unload packaging |
| **Тест** | e2e `ff-mp-tabs.spec.ts`: на вкладке упаковки нет текста «На полке» |
| **Зависит от** | MP-004 |
| **Готово когда** | e2e green |

---

### MP-008 — UI: «Упаковать» без выбора ячейки (MP task)

| Поле | Значение |
|------|----------|
| **Приоритет** | P0 |
| **Требование** | REQ-005 |
| **Файлы** | `FfPackagingPage.tsx` / panel в shipments |
| **Сделать** | Кнопка «Упаковать» не требует `storage_location_id`; POST pack с qty только |
| **Тест** | e2e: pack строки без location → прогресс растёт |
| **Зависит от** | MP-004, MP-007 |
| **Готово когда** | e2e green |

---

### MP-009 — pytest: ЧЗ gate на complete

| Поле | Значение |
|------|----------|
| **Приоритет** | P1 |
| **Источник** | REV-FIX-005 |
| **Файлы** | `backend/tests/test_packaging_tasks.py` |
| **Сделать** | Негатив: marked line без codes → complete 422 `marking_not_done` |
| **Зависит от** | MP-002 |
| **Готово когда** | pytest -k marking_not_done green |

---

## 7. Фаза B — UI структура документа (P0)

### MP-010 — Убрать вкладки «Короба» и «Финальная отгрузка»

| Поле | Значение |
|------|----------|
| **Приоритет** | P0 |
| **Требование** | REQ-002 |
| **Файлы** | `frontend/src/screens/ff/FfSuppliesShipmentsPage.tsx` |
| **Сделать** | Tab list: только `ff-mp-tab-products`, `ff-mp-tab-packaging`. Удалить `ff-mp-tab-boxes`, `ff-mp-tab-final` и их panel content — **перенести** содержимое коробов на «Товары» (MP-011). |
| **Тест** | e2e: нет testid boxes/final tabs |
| **Зависит от** | — |
| **Готово когда** | e2e green |

---

### MP-011 — Короба на вкладке «Товары»

| Поле | Значение |
|------|----------|
| **Приоритет** | P0 |
| **Требование** | REQ-002 |
| **Файлы** | `FfSuppliesShipmentsPage.tsx` |
| **Сделать** | Блок коробов (список, batch create, print WHB, actions) — под таблицей плана или отдельной секцией на «Товарах». Сохранить все `data-testid` коробов или обновить e2e. |
| **Тест** | e2e `ff-mp-box-add-modal.spec.ts` — сценарий с вкладки «Товары» |
| **Зависит от** | MP-010 |
| **Готово когда** | e2e green |

---

### MP-012 — Плашка упаковки: не на draft; без global «Продолжить»

| Поле | Значение |
|------|----------|
| **Приоритет** | P0 |
| **Требование** | REQ-003 |
| **Файлы** | `FfSuppliesShipmentsPage.tsx` |
| **Сделать** | 1) `ff-mp-packaging-progress` — только если status ≥ confirmed **и** есть task. 2) Убрать глобальный баннер с «Продолжить упаковку»; кнопка перехода — только внутри вкладки «Упаковка». |
| **Тест** | e2e: draft **нет** progress testid; confirmed **есть** |
| **Зависит от** | MP-003, MP-010 |
| **Готово когда** | e2e green |

---

### MP-013 — Footer: «Утвердить» / «Отгружено»

| Поле | Значение |
|------|----------|
| **Приоритет** | P0 |
| **Требование** | REQ-002, Step 2/5 |
| **Файлы** | `FfSuppliesShipmentsPage.tsx` |
| **Сделать** | Sticky/footer bar: «Утвердить» для submitted/draft (по роли); «Отгружено» для confirmed/collecting при выполнении условий ship. Логику с вкладки «Финал» перенести сюда. |
| **Тест** | e2e: ship с footer без tab final |
| **Зависит от** | MP-010, MP-033 |
| **Готово когда** | e2e green |

---

### MP-014 — Шапка: склад FF + дата отгрузки

| Поле | Значение |
|------|----------|
| **Приоритет** | P1 |
| **Требование** | Source req п.5 |
| **Файлы** | `FfSuppliesShipmentsPage.tsx`, `SellerMarketplaceUnloadDialog.tsx` (read-only для FF view) |
| **Сделать** | Поля видны в header с create; editable только до confirm (как сейчас или по DEC) |
| **Тест** | e2e: видны warehouse + ship date testid |
| **Зависит от** | MP-010 |
| **Готово когда** | e2e green |

---

## 8. Фаза C — Короба и scan (P0–P1)

### MP-015 — Batch короба открытые

| Поле | Значение |
|------|----------|
| **Приоритет** | P0 |
| **Источник** | REV-FIX-002 |
| **Файлы** | `marketplace_unload_box_service.py` (`create_boxes_batch`) |
| **Сделать** | `closed_at=NULL` при batch create |
| **Тест** | pytest -k batch |
| **Зависит от** | MP-005 |
| **Готово когда** | pytest green |

---

### MP-016 — E2E: N≥2 короба + модалка (без gate упаковки)

| Поле | Значение |
|------|----------|
| **Приоритет** | P0 |
| **Источник** | REV-FIX-002a (переопределено) |
| **Файлы** | `frontend/tests-e2e/ff-mp-box-add-modal.spec.ts` |
| **Сделать** | confirm → **сразу** 3 короба (packaging **не** complete) → второй короб «Добавить товары» → модалка → qty. TC-NEW-MP-006 |
| **Зависит от** | MP-006, MP-015 |
| **Готово когда** | e2e green |

---

### MP-017 — Единый batch path (не legacy open_box)

| Поле | Значение |
|------|----------|
| **Приоритет** | P1 |
| **Источник** | REV-FIX-009 |
| **Файлы** | `FfSuppliesShipmentsPage.tsx`, `marketplace_unload_box_service.py` |
| **Сделать** | count≥1 → batch; два batch по 1 — оба OK |
| **Зависит от** | MP-015 |
| **Готово когда** | pytest + e2e green |

---

### MP-018 — Большая модалка: pick + scan cell/product/box

| Поле | Значение |
|------|----------|
| **Приоритет** | P0 |
| **Требование** | REQ-007, BR-003 |
| **Файлы** | `FfMarketplaceUnloadBoxAddDialog.tsx`; backend collect/attach если нужны доработки |
| **Сделать** | 1) Ручной выбор ячейки + товар + qty. 2) Scan: cell → context; product → add с context; WHB ready box → attach flow (MP-019). 3) Placeholder тексты по зонам. |
| **Тест** | e2e + pytest collect with location |
| **Зависит от** | MP-015 |
| **Готово когда** | scan cell → product → line in box |

---

### MP-019 — Attach готового короба: confirm + over-plan OK

| Поле | Значение |
|------|----------|
| **Приоритет** | P0 |
| **Требование** | REQ-009, REQ-010, BR-004, BR-005, GAP-004 |
| **Файлы** | `marketplace_unload_box_service.py` (`attach_existing_box_by_barcode`); `marketplace_unload_collect_service.py`; `FfMarketplaceUnloadBoxAddDialog.tsx` / shipments scan |
| **Сделать** | 1) UI: confirm «Весь короб…»; второй confirm если qty > plan remaining. 2) Backend: флаг `allow_over_plan=true` или отдельный endpoint после confirm; **не** резать qty до плана. 3) Разворот `InboundIntakeDistributionLine` без изменений по смыслу. 4) Trigger MP-001 collecting. |
| **Тест** | pytest: attach box qty 15, plan remaining 10, allow → lines 15; e2e modals |
| **Зависит от** | MP-018 |
| **Готово когда** | over-plan после OK принят |

---

### MP-020 — Scan на «Товарах»: только WHB

| Поле | Значение |
|------|----------|
| **Приоритет** | P0 |
| **Требование** | REQ-008, BR-006 |
| **Файлы** | `FfSuppliesShipmentsPage.tsx` |
| **Сделать** | Inline scan на «Товарах» → только attach box by WHB; SKU/cell игнор или сообщение «используйте модалку короба» |
| **Тест** | e2e: WHB ok; product barcode no add on main scan |
| **Зависит от** | MP-011, MP-019 |
| **Готово когда** | e2e green |

---

## 9. Фаза D — Печать конструктор (P1)

### MP-021 — Единая точка входа: MarkingPrintDialog на упаковке

| Поле | Значение |
|------|----------|
| **Приоритет** | P1 |
| **Требование** | REQ-011, GAP-006 |
| **Файлы** | `FfPackagingPage.tsx`, `FfProductLineCells.tsx`, убрать `ProductBarcodePrintButton` для MP-unload lines |
| **Сделать** | Иконка печати → всегда `MarkingPrintDialog` |
| **Зависит от** | MP-008 |
| **Готово когда** | нет простого 58×40 dialog на MP packaging |

---

### MP-022 — Поле «этикеток на каждый товар» + ЧЗ block conditional

| Поле | Значение |
|------|----------|
| **Приоритет** | P1 |
| **Требование** | REQ-011 п.22–23 |
| **Файлы** | `MarkingPrintDialog.tsx`, `markingPrintPresets.ts` |
| **Сделать** | Число labels per product; скрыть cz block если !product.honest_sign |
| **Тест** | unit/e2e: non-ЧЗ product — нет cz block |
| **Зависит от** | MP-021 |
| **Готово когда** | UI + tape preview ok |

---

### MP-023 — Генерация полной ленты по layout

| Поле | Значение |
|------|----------|
| **Приоритет** | P1 |
| **Требование** | REQ-011, BR-009, A-002 |
| **Файлы** | `MarkingPrintDialog.tsx`, `expandLayoutTape`, backend marking batch если нужно |
| **Сделать** | `tape = expandLayout(layout) × qty_to_pack × labels_per_product` (уточнить A-002 для cz vs label blocks). Пример: 3×cz + 2×label на 1 unit × 5 units × 2 labels = … |
| **Тест** | pytest или frontend unit: layout [cz×3, label×2], qty 5, lpp 2 → count blocks |
| **Зависит от** | MP-022 |
| **Готово когда** | printed tape matches constructor |

---

## 10. Фаза E — Адресное хранение DEC-019 (P1)

### MP-024 — Миграция остатков на зону сортировки при выкл. флага

| Поле | Значение |
|------|----------|
| **Приоритет** | P1 |
| **Источник** | REV-FIX-003 |
| **Файлы** | `tenant_settings_service.py`, inventory migration helper |
| **Сделать** | true→false: все qty с адресных ячеек → virtual sorting location atomically |
| **Тест** | pytest tenant settings |
| **Зависит от** | — (параллельно с фазой A) |
| **Готово когда** | pytest green |

---

### MP-025 — UI settings: сообщение после миграции

| Поле | Значение |
|------|----------|
| **Приоритет** | P1 |
| **Источник** | REV-FIX-004 |
| **Файлы** | `FfSettingsScreen.tsx`, `ff-address-storage-setting.spec.ts` |
| **Зависит от** | MP-024 |
| **Готово когда** | e2e green |

---

## 11. Фаза F — UX, docs, регрессия (P2)

### MP-026 — Copy страницы: без «подбор по ячейкам»

| Источник REV-FIX-011 | `FfSuppliesShipmentsPage.tsx` subtitle |

### MP-027 — Селлер: hint после «Запланировано»

| Источник REV-FIX-012 | `SellerMarketplaceUnloadDialog.tsx`, `seller-mp-unload.spec.ts` |

### MP-028 — Сводка «План / Распределено» на «Товарах»

| Источник REV-FIX-013 | `mpCollectSummary` на draft — plan total |

### MP-029 — Copy box closed — doc + pytest

| Источник REV-FIX-015 | `DATA_FLOW.md`, copy остаётся closed |

### MP-030 — Deprecate PUT pick-allocations

| Источник REV-FIX-016 | OpenAPI deprecated=True |

### MP-031 — DATA_FLOW: cancel → sorting zone

| Источник REV-FIX-017 | docs only + pytest cancel |

### MP-032 — E2E full flow (обновлённый)

| Источник REV-FIX-019 | seller plan → FF confirm → **parallel** boxes + packaging → ship footer |
| **Зависит от** | MP-013, MP-016, MP-008, MP-033 |
| **TC** | TC-NEW-MP-FULL-001 |

### MP-033 — Ship: упаковка done + ЧЗ + короба (регрессия)

| **Требование** | REQ-012, A-003 |
| **Сделать** | Убедиться ship gate только на ship; e2e ship blocked until packaging complete; distribution warning DEC-010 если актуально |
| **Зависит от** | MP-002, MP-005, MP-013 |

### MP-034 — Обновить канонические docs

| **Файлы** | `01_normalized_process_spec.md` (DEC-019), `MVP_DECISIONS_RU.md`, `IMPLEMENTED_PRODUCT_SCENARIOS_*`, `DATA_FLOW.md` |
| **Сделать** | Одна формулировка DEC-019; сценарии S01–S09 под новую модель; пометить 02/03 как superseded by 06 |
| **Зависит от** | MP-024, основные MP P0 |

---

## 12. Рекомендуемая очередь (Composer)

```text
P0 backend core:
  MP-002 → MP-003 → MP-004 → MP-005 → MP-001 → MP-009

P0 frontend unblock:
  MP-006 → MP-007 → MP-008

P0 UI structure:
  MP-010 → MP-011 → MP-012 → MP-014

P0 boxes:
  MP-015 → MP-017 → MP-016 → MP-018 → MP-019 → MP-020

P0 ship footer:
  MP-013 → MP-033

P1 print:
  MP-021 → MP-022 → MP-023

P1 settings:
  MP-024 → MP-025

P2 polish:
  MP-026 … MP-032 → MP-034
```

**Параллельно допустимо:** MP-024 с backend P0; MP-026–031 с P1 print.

---

## 13. Test coverage (черновик для PR)

| TC-ID | Title | Applies | Notes |
|-------|-------|---------|-------|
| TC-NEW-MP-001 | Address storage toggle | Y | Given admin, When toggle, Then PATCH ok |
| TC-NEW-MP-006 | Box add modal N≥2 | Y | Given confirm, When 3 boxes without packaging done, Then add products in modal — **parallel flow** |
| TC-NEW-MP-010 | Status collecting | Y | Given confirm, When first box, Then UI «На сборке» |
| TC-NEW-MP-011 | No packaging on draft | Y | Given draft, Then no packaging progress banner |
| TC-NEW-MP-012 | Pack without shelf | Y | When Упаковать, Then progress++, no cell error |
| TC-NEW-MP-013 | Attach whole box confirm | Y | When scan ready box, Then confirm modals; OK → full qty |
| TC-NEW-MP-014 | Over plan attach | Y | When box qty > plan, Then warn; OK → all qty in shipment |
| TC-NEW-MP-015 | Main scan WHB only | Y | When product scan on Products tab, Then no collect |
| TC-NEW-MP-016 | Print constructor tape | Y | Given custom layout, When print, Then tape = layout × qty × lpp |
| TC-NEW-MP-FULL-001 | Full flow parallel | Y | packaging ∥ boxes → ship from footer |

---

## 14. Допущения (явно)

| ID | Допущение | Риск |
|----|-----------|------|
| A-001 | OK сверх плана увеличивает факт отгрузки | Нужен ff_modified / trim если продукт передумает |
| A-002 | «Этикеток на товар» умножает блоки `label` в layout; для `cz` — уточнить при MP-023 | Неверный count ленты |
| A-003 | Ship требует распределение по коробам как сейчас | Ship без коробов при done упаковке |

---

## 15. Связь со старыми TASK / REV-FIX

| Старый | Новый / статус |
|--------|----------------|
| TASK-001 | ✅ готово (address storage flag) |
| TASK-002, 003 | ✅ готово |
| TASK-004 | ⏳ collect inventory — **остаётся**, не отменяется |
| TASK-005 | ✅ legacy pick UI removed — регрессия MP-033 |
| TASK-006 | ❌ **отменено** → MP-003 |
| TASK-007 | ✅ частично → MP-002 |
| TASK-008 | ❌ **отменено** → MP-005, MP-006 |
| TASK-009 | → MP-015, MP-017 |
| TASK-010, 011 | ✅ база есть → MP-018, MP-016 |
| TASK-012 | ❌ **переопределено** → MP-010…MP-014 |
| TASK-013 | → MP-028, MP-033 |
| TASK-014 | ❌ финал tab → MP-013 footer |
| TASK-015, 019 | ⏳ ship/cancel — регрессия MP-033 |
| TASK-018 | ✅ TSD API |
| REV-FIX-001…002a | → MP-002, MP-015, MP-016 |
| REV-FIX-003…004 | → MP-024, MP-025 |
| REV-FIX-005 | → MP-009 |
| REV-FIX-006…008, 010 | ❌ **отменено** |
| REV-FIX-009 | → MP-017 |
| REV-FIX-011…020 | → MP-026…MP-034 |

---

## 16. Критерий «готово к релизу»

- [x] Все **P0** MP-001…MP-020, MP-013, MP-033 — зелёные тесты
- [x] Нет gate упаковки на коробах (ни backend, ни UI, ни e2e gate spec)
- [x] 2 вкладки; ship/confirm в footer
- [x] Draft без task и без packaging banner
- [x] Parallel e2e: boxes before packaging complete (`TC-NEW-MP-FULL-001`)
- [x] `01_normalized_process_spec.md` и этот документ не противоречат друг другу
- [x] `ruff` + `mypy` + pytest + `npm run build` + mp-* e2e green (локально на срезе MP-032…034)

---

## 17. Ссылки

- Канон требований: [`01_normalized_process_spec.md`](./01_normalized_process_spec.md)
- Release audit (исторический): [`04_release_implementation_review.md`](./04_release_implementation_review.md)
- Старый план (не выполнять слепо): [`02_technical_builder_plan.md`](./02_technical_builder_plan.md)
- Старый REV-FIX список: [`05_review_fix_tasks_composer_RU.md`](./05_review_fix_tasks_composer_RU.md)
- E2e правила: [`AGENTS.md`](../../AGENTS.md)
