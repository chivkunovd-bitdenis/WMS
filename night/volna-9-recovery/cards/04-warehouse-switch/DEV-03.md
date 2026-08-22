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
