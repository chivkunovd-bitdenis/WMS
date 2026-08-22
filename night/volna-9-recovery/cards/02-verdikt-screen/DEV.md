# Фича 1

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/app/services/fbs_marking_service.py — единый WB-вердикт и единый признак `delivery_allowed` в metadata API.
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/tests/test_fbs_marking.py — проверки S-03-TC-001…007 и приоритета блокирующего требования.

API-роуты и модели не менялись: существующий `GET /operations/fbs-orders/{order_id}/metadata` уже возвращает `verdict`.

## Миграции

Нет.

## Гейты

- ruff: `ruff check app/services/fbs_marking_service.py tests/test_fbs_marking.py` — passed.
- mypy: targeted check выявил 4 ранее существующие ошибки в `wildberries_credentials_service.py`, `fbs_stock_sync_service.py` и `fbs_warehouse_binding_service.py`; в изменённых файлах ошибок не выявлено.
- pytest: `pytest -q tests/test_fbs_marking.py` — 21 passed.
- back_guard.py: не запущен — файл `scripts/ci/back_guard.py` отсутствует в этой рабочей копии.
- check_migrations.py: не запущен — файл `scripts/ci/check_migrations.py` отсутствует в этой рабочей копии.

## Не реализовано

- UI-части фичи и серверные изменения других карточек не реализовывались по границе атомарной backend-фичи.
- Полные корневые `ruff`, `mypy` и `pytest` не являются зелёными из-за существующих ошибок/регрессий вне изменённых файлов; исправления чужих файлов не вносились.

# Фича 2

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/app/services/fbs_shipment_service.py — gate передачи вызывает единый `_wb_order_verdict` из фичи 1; положительный `check_status`/локальный статус сам по себе не разрешает передачу.
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/tests/test_fbs_shipment_deliver_gate_unit.py — unit-покрытие разрешённых и блокирующих WB-решений, UUID заказа и причины отказа.

## Миграции

Нет.

## Гейты

- `ruff check backend/app/services/fbs_shipment_service.py backend/tests/test_fbs_shipment_deliver_gate_unit.py` — PASS.
- `mypy backend` — FAIL: 21 ранее существующая ошибка в 6 несвязанных файлах; изменённые файлы ошибок не добавили.
- `pytest -q backend/tests/test_fbs_shipment_deliver_gate_unit.py` — PASS, 16 passed.
- `ruff check backend` — FAIL: 81 ранее существующая ошибка в несвязанных файлах; целевые файлы чистые.
- `pytest -q backend` — прерван после 87 passed и 227.84 s; полный прогон не завершён.
- `python3 scripts/ci/back_guard.py` — не запущен: файл отсутствует в этой рабочей копии.
- `python3 scripts/ci/check_migrations.py` — не запущен: файл отсутствует в этой рабочей копии.

## Не реализовано

- UI и API-контракт не менялись: они относятся к другим атомарным кускам.
- Миграции не требуются.

## Блокеры

Нет блокеров по реализации; ограничения полных гейтов описаны выше.

# Фича 3

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/src/screens/v2/fbsApi.ts
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/src/utils/metaStatus.ts

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — красный: локальный `tsc` отсутствует, `npx` не смог скачать пакет из-за `ENOTFOUND` (сеть недоступна).
- `python3 scripts/ui/ui_guard.py` — красный: обнаружены новые нарушения в `WbProductPickerDialog.tsx`, `FfFbsSupplyWorkspace.tsx` и `SellerInboundDraftScreen.tsx`; эти файлы не изменялись в рамках карточки.
- `npm run test:unit` — красный: `vitest: command not found`, зависимости фронтенда не установлены.

## Не реализовано

Пунктов контракта, относящихся к этому атомарному куску, не осталось. Тип вердикта ограничен серверным словарём, поля источника истины доступны только для чтения, а отображение всех контрактных состояний и неизвестных причин централизовано в `metaStatusView`.

# Фича 4

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/src/screens/v2/FfFbsOrdersScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/tests-e2e/ff-fbs-orders.spec.ts`

Атомарная фича реализована в существующей зоне статуса: серверный вердикт отображается через `StatusChip`, причина отказа и текст недоступности — через `TextCell`. Новая колонка и заливка строки не добавлены. Сценарий покрывает S-03-TC-001, S-03-TC-002, S-03-TC-003 и S-03-TC-006.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — результат не удалось надёжно зафиксировать: команда не вывела диагностику, а окружение завершило запуск без доступного кода результата.
- `python3 scripts/ui/ui_guard.py` — красный: файл `scripts/ui/ui_guard.py` отсутствует в этой рабочей копии (ошибка `can't open file .../frontend/scripts/ui/ui_guard.py` при запуске из корня через имеющийся сценарий проверки).
- `npm run test:unit` — красный: `vitest: command not found`, зависимости frontend не установлены.

## Не реализовано

Пунктов контракта для этого атомарного куска, которые не удалось реализовать буквально, нет. Полная локальная проверка ограничена отсутствующим `ui_guard.py`, неустановленным `vitest` и недоступным надёжным результатом `tsc`; базовую линию `ui_guard.py` не изменял.

# Фича 5

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/tests-e2e/ff-fbs-supply.spec.ts — добавлены пользовательские сценарии S-03-TC-004, S-03-TC-005 и S-03-TC-007 для рабочего места поставки: ожидание и требование кода блокируют передачу, один блокирующий заказ блокирует всю поставку и объясняет причину.

Экранный код `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx` уже содержит реализацию этой атомарной части из предыдущего прохода: `StatusChip` в зоне ЧЗ и блокировку `PrimaryAction` по серверному `metadata.verdict.delivery_allowed`; в этом проходе файл не изменялся.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — не завершён: локальный `npx` запустился без вывода и был остановлен после ожидания; сеть для загрузки отсутствующих зависимостей недоступна.
- `python3 scripts/ui/ui_guard.py` — FAIL: обнаружены новые нарушения базовой линии, включая `FfFbsSupplyWorkspace.tsx: экран-монолит 2493 → 2510`; базовую линию флагом `--update` не изменял.
- `npm run test:unit` — FAIL: `vitest: command not found`, зависимости frontend не установлены.

## Не реализовано

- Пунктов контракта для этого атомарного куска, которые не удалось реализовать в коде, нет. Проверка браузером и unit-тесты локально не завершены из-за отсутствующих frontend-зависимостей.

## Находки

Нет.
