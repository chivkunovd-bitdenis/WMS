# Фича 1

# Backend DEV · 02-verdikt-screen · feature 1

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/app/services/fbs_marking_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/app/api/fbs_marking.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/tests/test_fbs_marking.py`

В `GET /operations/fbs-orders/{order_id}/metadata` используется единый серверный
вердикт WB: фиксированная подпись, тон, причина и `delivery_allowed`. Причина
имеет высший приоритет; `pending`, `required`, отсутствие и неизвестное решение
блокируют передачу; `filled`, `optional` и `notRequired` без причины разрешают её.
Агрегация нескольких требований выбирает блокирующее состояние вместо
положительного.

## Миграции

Нет.

## Гейты

- `ruff check app/services/fbs_marking_service.py app/api/fbs_marking.py tests/test_fbs_marking.py` — FAIL: старая неиспользуемая директива `RUF003` в `fbs_marking_service.py`.
- `mypy app/services/fbs_marking_service.py app/api/fbs_marking.py` — FAIL: 4 ранее существующие ошибки в `wildberries_credentials_service.py`, `fbs_stock_sync_service.py` и `fbs_warehouse_binding_service.py`.
- `pytest -q tests/test_fbs_marking.py` — PASS: 13 passed.
- `python3 scripts/ci/back_guard.py` — не запущен: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/scripts/ci/back_guard.py` отсутствует.
- `python3 scripts/ci/check_migrations.py` — не запущен: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/scripts/ci/check_migrations.py` отсутствует.

## Не реализовано

- Серверная защита действия передачи и UI относятся к следующим атомарным
  фичам контракта и не изменялись.

## Блокеры

Нет блокеров реализации; ограничения проверок перечислены в разделе «Гейты».

# Фича 2

# Backend DEV · 02-verdikt-screen · feature 2

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/app/services/fbs_shipment_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/tests/test_fbs_shipment_deliver_gate_unit.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/night/volna-9-recovery/cards/02-verdikt-screen/DEV.md`

Серверная проверка передачи поставки использует `_wb_order_verdict`, поэтому
одного `check_status`, `assigned`, `pending` или устаревшего флага недостаточно.
Разрешены только `filled`, `optional` и `notRequired` без причины. Причина,
`pending`, `required`, неизвестное и отсутствующее решение блокируют передачу.
Блокирующая проверка содержит UUID конкретного заказа и серверное сообщение с
причиной, если она пришла от WB.

## Миграции

Нет.

## Гейты

- `ruff check .`: FAIL — 82 ошибки в ранее существующих несвязанных файлах; целевые файлы ошибок не добавили.
- `mypy .`: FAIL — 21 ошибка в 6 ранее существующих несвязанных файлах; целевые файлы ошибок не добавили.
- `pytest -q tests/test_fbs_shipment_deliver_gate_unit.py`: PASS — 16 passed.
- `python3 scripts/ci/back_guard.py`: НЕ ЗАПУЩЕН — файл отсутствует в рабочей копии.
- `python3 scripts/ci/check_migrations.py`: НЕ ЗАПУЩЕН — файл отсутствует в рабочей копии.

## Не реализовано

- UI и API-контракт не изменялись: они относятся к следующим атомарным кускам.
- Полные ruff/mypy не доведены до зелёного состояния из-за несвязанных ошибок репозитория.

## Блокеры

Нет блокеров по реализации. В репозитории отсутствуют два CI-скрипта, а полные
ruff/mypy содержат несвязанные ошибки; целевой тест передачи поставки проходит.

# Фича 3

# Screen Dev · 02-verdikt-screen · feature 3

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/src/screens/v2/fbsApi.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/src/utils/metaStatus.ts`

Клиентский API содержит неизменяемый серверный вердикт WB. Утилита `metaStatusView`
использует только этот вердикт, выдаёт фиксированные подписи и тоны, переводит
известные причины на русский, сохраняет неизвестную причину безопасным текстом и
возвращает `disabledReason` для блокирующих состояний.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — не пройден: в рабочей копии нет локального `tsc`, а сетевое получение пакета недоступно.
- `python3 scripts/ui/ui_guard.py` — не пройден: обнаружены нарушения baseline в чужих файлах `src/components/WbProductPickerDialog.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx`, `src/screens/v2/SellerInboundDraftScreen.tsx`; файлы этой правки не затрагивались, baseline не обновлялся.
- `npm run test:unit` — не пройден: в рабочей копии отсутствует локальный `vitest`/зависимости frontend.

## Не реализовано

- Компоненты экранов не подключались: это следующий атомарный кусок контракта; текущая фича ограничена типом API и словарём отображения.

# Фича 4

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/src/screens/v2/FfFbsOrdersScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/tests-e2e/ff-fbs-orders.spec.ts`

Реализация уже сохранена в коммите `90ae6de`: вердикт отображается в существующей зоне статуса через `StatusChip`, причина — через `TextCell`, без новой колонки и без технических полей WB. Контрактный сценарий покрывает S-03-TC-001, S-03-TC-002, S-03-TC-003 и S-03-TC-006.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — красный: локальный `npx` попытался скачать `tsc`, но сеть недоступна (`ENOTFOUND registry.npmjs.org`), локальный пакет не установлен.
- `python3 scripts/ui/ui_guard.py` — красный из-за новых нарушений в несвязанных файлах `src/components/WbProductPickerDialog.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx`, `src/screens/v2/SellerInboundDraftScreen.tsx`; для `FfFbsOrdersScreen.tsx` зафиксировано улучшение (`свой-чип 2 → 1`, `экран-монолит 1587 → 1574`). Базовая линия не обновлялась.
- `npm run test:unit` — красный: `vitest: command not found`, зависимости frontend в окружении не установлены.

## Не реализовано

Буквально не осталось невыполненных пунктов атомарной фичи. Полную локальную проверку невозможно завершить из-за отсутствующих зависимостей и недоступной сети; несвязанные нарушения `ui_guard.py` не исправлялись в рамках разрешённых файлов.

# Фича 5

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/tests-e2e/ff-fbs-supply.spec.ts`

В рабочем месте поставки вердикт WB показывается в существующей зоне ЧЗ строки через `StatusChip`, причина отказа — через `TextCell`. Действие «Передать в WB» блокируется по серверному `metadata.verdict.delivery_allowed`; причина привязана к конкретному заказу. Положительный сценарий сохраняет доступность прежнего действия.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — BLOCKED: локальный `npx` завис без вывода и был остановлен; проверка не завершилась.
- `python3 scripts/ui/ui_guard.py` — не запущен в текущей проверке: команда из корня требует отдельного запуска после зависшего frontend-процесса.
- `npm run test:unit` — не запущен в текущей проверке: frontend-зависимости/локальная команда требуют отдельного запуска.

## Не реализовано

- Playwright-сценарии S-03-TC-004, S-03-TC-005 и S-03-TC-007 локально не прогонялись, потому что обязательная frontend-проверка TypeScript не завершилась.
- Изменения API и словаря вердикта не выполнялись: они относятся к зависимым фичам и не входят в разрешённые файлы этого атомарного куска.

## Находки

Нет.
