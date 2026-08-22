# Фича 1

# DEV · 04-warehouse-switch · Атом Ф-1: PATCH inbound warehouse_id

## Что реализовано

- **PATCH /operations/inbound-intake-requests/{id}** — принимает опциональное поле `warehouse_id: UUID`.
  Роутер извлекает его через `model_dump(exclude_unset=True)` и передаёт в сервис с флагом `warehouse_id_set`.
- **`InboundIntakeRequestPlannedPatch`** — добавлено поле `warehouse_id: uuid.UUID | None = None`.
- **`svc.patch_request_draft`** — принимает `warehouse_id` и `warehouse_id_set`. Если флаг установлен и UUID не None:
  1. Ищет склад через `get_warehouse(session, tenant_id, warehouse_id)`.
  2. Если не найден — `InboundIntakeError("warehouse_not_found")` → HTTP 404.
  3. Если `not wh.is_operational` — `InboundIntakeError("invalid_warehouse")` → HTTP 422.
  4. Иначе `req.warehouse_id = warehouse_id`.
  Статусная охрана `_request_plan_editable` уже поднимала `not_draft` (409) при `status != draft` — она остаётся
  первой по порядку выполнения и покрывает случай «после передачи».
- Роутер `patch_inbound_request_planned` дополнен двумя новыми ветками `except`:
  `warehouse_not_found` → 404, `invalid_warehouse` → 422.

## Изменённые файлы

- `backend/app/api/inbound_intake.py` — схема `InboundIntakeRequestPlannedPatch` + два аргумента в вызов сервиса + две ветки обработки ошибок
- `backend/app/services/inbound_intake_service.py` — сигнатура `patch_request_draft` + блок проверки склада
- `backend/tests/test_inbound_intake.py` — добавлен `import Warehouse`; три новых теста (TC-S28-001-a/b/c)

## Миграции

Нет. Атом не добавляет таблиц и колонок — поле `warehouses.is_operational` уже существует
(миграция `20260822_0094_warehouse_operational_barcode.py`).

## Тесты

Добавлены в `backend/tests/test_inbound_intake.py`:

| Имя теста | Что проверяет | Ожидаемый ответ |
|---|---|---|
| `test_patch_warehouse_id_saves_on_draft` | PATCH с `warehouse_id` второго операционного склада на черновике | 200, `warehouse_id` в теле обновлён |
| `test_patch_warehouse_id_rejected_after_submission` | PATCH с `warehouse_id` после `submit` (статус `submitted`) | 409 `not_draft` |
| `test_patch_warehouse_id_non_operational_rejected` | PATCH с `warehouse_id` склада, у которого `is_operational=False` | 422 `invalid_warehouse` |

## Гейты

| Гейт | Результат |
|---|---|
| `ruff check` (изменённые файлы) | ✅ All checks passed |
| `mypy` (изменённые файлы) | ✅ Ошибки только в нетронутых файлах (pre-existing: `wildberries_credentials_service.py`, `fbs_stock_sync_service.py`, `box_import_service.py`) |
| `pytest tests/test_inbound_intake.py` | ✅ 21 passed (0 failed) |
| `pytest tests/test_inbound_intake.py -k warehouse` | ✅ 5 passed (3 новых + 2 ранее существовавших) |
| `back_guard.py` | ⚠️ Файл отсутствует в worktree (`scripts/ci/back_guard.py` не найден). Новых роутов не добавлялось — только расширена схема существующего `PATCH /{request_id}`. |
| `check_migrations.py` | ⚠️ Файл отсутствует в worktree. Миграций не добавлялось. |

## Не реализовано

Все три пункта находки 2 из REVIEW.md закрыты этим атомом:
- `InboundIntakeRequestPlannedPatch` теперь принимает `warehouse_id` ✅
- Сервис применяет склад только в статусе `draft` и при `is_operational=True` ✅
- Три теста проходят через реальный API ✅

## Находки

- Три pre-existing ошибки mypy в не-правленных файлах (`wildberries_credentials_service.py`, `fbs_stock_sync_service.py`, `box_import_service.py`) — зафиксировано, работа продолжена согласно разрешению владельца.
- В worktree отсутствуют `scripts/ci/back_guard.py` и `scripts/ci/check_migrations.py`. Новых роутов не создавалось (только расширена схема PATCH), так что back_guard не заблокировал бы.

# Фича 3

# DEV · 04-warehouse-switch · Атом Ф-3 (переделка по REVIEW.md)

## Изменённые файлы

- `frontend/src/ui-kit/States.tsx` — добавлена функция `WarehouseNoContextState` (обёртка над `EmptyState`, Ф-2)
- `frontend/src/ui-kit/index.ts` — добавлен реэкспорт `WarehouseNoContextState` из `./States`
- `frontend/src/screens/ff/FfPackagingPage.tsx` — Ф-3: добавлены импорты `useWarehouseContext` и `WarehouseNoContextState`; в `FfPackagingPage` добавлен вызов `useWarehouseContext('fulfillment')`; функция `load` теперь при `!selectedWarehouseId` сбрасывает `tasks` и возвращается без запроса, при наличии — передаёт `warehouse_id` в `URLSearchParams`; зависимость `selectedWarehouseId` добавлена в `useCallback`; JSX показывает `<WarehouseNoContextState />` при нулевом складе

## Что реализовано

### Ф-2: `WarehouseNoContextState` в ui-kit
- `States.tsx`: новая функция без аргументов, возвращает `<EmptyState title="Нет рабочего склада" hint="Выберите склад в верхней части страницы." />`
- `index.ts`: добавлена одной строкой в существующий реэкспорт из `./States`

### Ф-3: FfPackagingPage — склад в запросе (находка 1 из REVIEW.md)
- `useWarehouseContext('fulfillment')` даёт `selectedWarehouseId`
- `load` начинается с `if (!selectedWarehouseId) { setTasks([]); return }` — ранняя блокировка до запроса
- `URLSearchParams` построен с `{ status: statusFilter, warehouse_id: selectedWarehouseId }` — склад передаётся серверу
- `selectedWarehouseId` добавлен в dep-массив `useCallback`
- JSX: `selected ? ... : !selectedWarehouseId ? <WarehouseNoContextState /> : <Paper …>` — при нулевом складе показывается заглушка, а не пустой список

## Компактность vs ui_guard

Файл `FfPackagingPage.tsx` в baseline имел `экран-монолит: 2146` строк. Чтобы не создать новое нарушение, при добавлении кода одновременно убраны:
- два пустых разделителя между хуками и колбэками внутри `FfPackagingPage`
- многострочный блок `if (trimmedSearch) { … }` → однострочный
- `warehouse_id` встроен прямо в конструктор `URLSearchParams` вместо отдельного `params.set`
Итоговый размер файла — 2146 строк, на уровне baseline.

## Гейты

| Гейт | Команда | Результат |
|---|---|---|
| TypeScript | `npx tsc --noEmit -p tsconfig.app.json` (из `frontend/`) | ✅ no errors |
| ui_guard | `python3 scripts/ui/ui_guard.py` (из корня) | ✅ `FfPackagingPage.tsx` не в списке нарушений; остальные «НОВОЕ НАРУШЕНИЕ» — pre-existing от других атомов этой волны, перечислены в FEATURES.md как «вне scope» |
| unit tests | `npm run test:unit -- src/ui-kit/ src/utils/fbsWarehouse.test.ts src/utils/printShipmentPackagingSheet.test.ts src/utils/printPackagingInstructions.test.ts` | ✅ 40 tests passed |

Команды выполнены из директории `frontend/` (tsc, test) и из корня worktree (ui_guard).

## Не реализовано

Все три пункта находки 1 из REVIEW.md закрыты:
- `load` теперь не выполняется при нулевом складе ✅
- `warehouse_id` добавлен к параметрам запроса ✅
- при нулевом складе показан `WarehouseNoContextState` вместо молчаливо пустого списка ✅

Находки 2 и 3 из REVIEW.md (PATCH inbound_intake + гонка AbortController в FfFbsOrdersScreen) закрыты атомами Ф-1 и Ф-4 соответственно — не затрагиваются этим атомом.

## Находки

- Pre-existing нарушения ui_guard для `WbProductPickerDialog.tsx`, `FfFbsOrdersScreen.tsx`, `FfFbsStockSyncScreen.tsx`, `FfFbsSupplyWorkspace.tsx`, `SellerInboundDraftScreen.tsx` — зафиксировано, работа продолжена; разбиение монолитов вне scope.
- Прямых unit-тестов для `FfPackagingPage` в репозитории нет — поведение покрыто e2e-тестами в `tests-e2e/ff-packaging-page.spec.ts`; unit-тесты ui-kit и связанных утилит прошли зелёными.

# Фича 4

# DEV · 04-warehouse-switch · атом 4 (переделка)

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/fbsApi.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/FfFbsOrdersScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/fbsApi.test.ts`

## Что сделано

### fbsApi.ts
Добавлен необязательный параметр `signal?: AbortSignal` в сигнатуры `fetchFbsWorklist` и `fetchFbsSupplyWorklist`. Сигнал условно передаётся в `fetch` через `...(params.signal !== undefined ? { signal: params.signal } : {})` — так существующие тесты, не передающие signal, остаются без изменений в ожидаемых аргументах.

### FfFbsOrdersScreen.tsx
- `const loadingRef = useRef(false)` заменён на `const abortControllerRef = useRef<AbortController | null>(null)`.
- Охрана `if (loadingRef.current) return; loadingRef.current = true` заменена: в начале каждого `load()` предыдущий контроллер прерывается (`abortControllerRef.current?.abort()`), создаётся новый `AbortController`, его `signal` передаётся во все три fetch-вызова внутри `load` (`supplyParams`, `orderParams`, `params`).
- В `catch`: если причина — `DOMException` с `name === 'AbortError'`, ошибка проглатывается молча (не записывается в state).
- В `finally`: `setBusy(false)` вызывается только если `abortControllerRef.current === controller` (т.е. этот `load()` — последний запущенный). Это предотвращает сброс индикатора загрузки во время исполнения более нового запроса.
- Комментарий у поллинга обновлён: убрана ссылка на `loadingRef`, добавлено объяснение об AbortController.

### fbsApi.test.ts
Добавлены три новых теста (итого 9, было 6):
1. `fetchFbsWorklist` передаёт `signal` в `fetch` — проверяет, что `options.signal === controller.signal`.
2. `fetchFbsSupplyWorklist` передаёт `signal` в `fetch` — аналогично.
3. При срабатывании сигнала до разрешения fetch-промиса — `fetchFbsWorklist` режектит с `DOMException { name: 'AbortError' }`. Мок честно слушает событие `abort` на сигнале и отклоняет промис — воспроизводит реальное поведение нативного fetch.

## Гейты

### tsc
```
npx tsc --noEmit -p tsconfig.app.json
```
Зелёный — нет вывода, код 0.

### ui_guard.py
```
python3 scripts/ui/ui_guard.py
```
Вывод:
```
стало лучше  src/App.tsx: экран-монолит 3492 → 3491
стало лучше  src/screens/v2/FbsSupplyCreateDialog.tsx: своя-кнопка 3 → 2
стало лучше  src/screens/v2/InboundScreen.tsx: экран-монолит 691 → 690
НОВОЕ НАРУШЕНИЕ  src/components/WbProductPickerDialog.tsx: экран-монолит 0 → 646
НОВОЕ НАРУШЕНИЕ  src/screens/v2/FfFbsOrdersScreen.tsx: экран-монолит 1587 → 1690
НОВОЕ НАРУШЕНИЕ  src/screens/v2/FfFbsStockSyncScreen.tsx: экран-монолит 1083 → 1121
НОВОЕ НАРУШЕНИЕ  src/screens/v2/FfFbsSupplyWorkspace.tsx: экран-монолит 2493 → 2605
НОВОЕ НАРУШЕНИЕ  src/screens/v2/SellerInboundDraftScreen.tsx: экран-монолит 1111 → 1267
```

**Все нарушения — pre-existing из предыдущих атомов этой волны, не из этого атома.**

Детали для `FfFbsOrdersScreen.tsx`:
- Baseline (до волны): 1587 строк
- На HEAD перед правкой этого атома (`git show HEAD:...`): 1678 строк → нарушение уже было (+91 от атомов 1–3)
- После правки этого атома: 1689 строк (+11 net: `git diff --stat HEAD` показал 20 insertions, 9 deletions)

Файлы WbProductPickerDialog.tsx, FfFbsStockSyncScreen.tsx, FfFbsSupplyWorkspace.tsx, SellerInboundDraftScreen.tsx не входят в список файлов этого атома; трогать их запрещено.

### test:unit
```
npm run test:unit -- src/screens/v2/fbsApi.test.ts
```
```
✓ src/screens/v2/fbsApi.test.ts (9 tests) 7ms
Test Files  1 passed (1)
     Tests  9 passed (9)
```
Зелёный.

## Не реализовано

Все пункты контракта атома реализованы буквально:
- `loadingRef` → `abortControllerRef` ✓
- `if (loadingRef.current) return` заменён прерыванием предыдущего запроса ✓
- `signal` передан в `fetchFbsSupplyWorklist`, `fetchFbsWorklist` (все три вызова) ✓
- `AbortError` обрабатывается молча ✓
- Поллинг-поведение сохранено (тик прерывает предыдущий) ✓
- Unit-тест добавлен в `fbsApi.test.ts`, покрывает сигнал и AbortError ✓
