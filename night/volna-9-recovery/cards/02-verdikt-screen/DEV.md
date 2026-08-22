# Фича 1

# Backend DEV · 02-verdikt-screen

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/app/services/fbs_marking_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/app/api/fbs_marking.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/tests/test_fbs_marking.py`

Реализован единый серверный вердикт WB в ответе `GET /operations/fbs-orders/{order_id}/metadata`: подпись, тон, причина и разрешение передачи. Добавлены все контрактные решения `filled`, `optional`, `notRequired`, `pending`, `required`, неизвестный и отсутствующий ответ; причина имеет приоритет, блокер перевешивает положительный ответ.

## Гейты

- `ruff`: целевые файлы прошли; полный запуск заблокирован существующими ошибками в несвязанных файлах репозитория.
- `mypy`: целевые импорты проверены; полный запуск выявил 4 существующие ошибки в `wildberries_credentials_service.py`, `fbs_stock_sync_service.py` и `fbs_warehouse_binding_service.py`.
- `pytest`: `13 passed` (`backend/tests/test_fbs_marking.py`).
- `back_guard.py`: не запущен — файл отсутствует в рабочей копии по `scripts/ci/back_guard.py`.
- `check_migrations.py`: не запущен — файл отсутствует в рабочей копии по `scripts/ci/check_migrations.py`.

## Не реализовано

- Серверная защита действия передачи и UI находятся в следующих атомарных фичах контракта и не изменялись.
- Миграции не нужны.

## Блокеры

Нет блокеров по реализации; технические ограничения гейтов описаны выше.

# Фича 2

# Backend DEV · 02-verdikt-screen · feature 2

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/app/services/fbs_shipment_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/tests/test_fbs_shipment_deliver_gate_unit.py`

Серверная передача поставки теперь использует единый WB-вердикт заказа из
`fbs_marking_service`: `reason`, `pending`, `required`, неизвестное решение и
отсутствующий ответ блокируют передачу. Разрешённые `filled`, `optional` и
`notRequired` проходят. Блокирующая проверка содержит `order_id` и понятное
сообщение с причиной, если она пришла от WB.

## Миграции

Нет.

## Гейты

- `ruff`: целевые файлы — PASS; полный `ruff check .` — FAIL на 82 ранее существующих ошибках в других файлах.
- `mypy`: целевые файлы — PASS; полный `mypy .` — FAIL на 21 ранее существующей ошибке в 6 других файлах.
- `pytest`: целевой `tests/test_fbs_shipment_deliver_gate_unit.py` — 16 passed; полный прогон остановлен после начала общего набора (в логе 3% без итогового результата).
- `back_guard.py`: PASS, без вывода.
- `check_migrations.py`: PASS, без вывода.

## Не реализовано

- UI и API-контракт не изменялись: это следующий слой карточки и не входит в атомарную backend-фичу 2.

## Блокеры

Нет блокеров по реализации; полные ruff/mypy имеют только несвязанные ошибки репозитория, полный pytest не завершился в доступное время.

# Фича 3

# Screen Dev · 02-verdikt-screen · feature 3

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/src/screens/v2/fbsApi.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/src/utils/metaStatus.ts`

Добавлен тип неизменяемого серверного вердикта WB и единый словарь его показа:
фиксированные подписи и тоны, русские переводы известных причин, безопасный показ
неизвестной причины и `disabledReason` для блокирующих состояний.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — FAIL: локальные зависимости отсутствуют, `npx` попытался скачать пакет `tsc`, но сеть недоступна (`ENOTFOUND registry.npmjs.org`). Ошибок компиляции получить не удалось.
- `python3 scripts/ui/ui_guard.py` — FAIL: три новые относительно baseline записи в чужих/смежных файлах: `src/components/WbProductPickerDialog.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx`, `src/screens/v2/SellerInboundDraftScreen.tsx`. Файлы этой атомарной правки не затрагивались; baseline не обновлялся.
- `npm run test:unit` — FAIL: `vitest: command not found`, локальные зависимости frontend не установлены.

## Не реализовано

- Компоненты экранов не подключались: это следующий атомарный кусок контракта, а текущая карточка ограничена типом API и словарём отображения.
- Полная проверка TypeScript и unit-тесты требуют установленных зависимостей; установка из сети невозможна в текущем окружении.

# Фича 4

# Screen Dev · 02-verdikt-screen · feature 4

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/src/screens/v2/FfFbsOrdersScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/tests-e2e/ff-fbs-orders.spec.ts`

Старый локальный признак `Отклонено WB` удалён из существующей зоны статуса. Экран использует серверный `metadata.verdict`, `StatusChip` и `TextCell`; новой колонки, заливки строки и отдельного состояния загрузки не добавлено. В e2e добавлен UI-сценарий для принятого, необязательного, отклонённого и недоступного ответа WB, включая русскую причину и текст `Сдача пока недоступна`.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — FAIL/BLOCKED: локальный `frontend/node_modules` отсутствует, бинарник `tsc` недоступен; скачивание зависимостей не выполнялось.
- `python3 scripts/ui/ui_guard.py` — FAIL по существующей baseline-ситуации: новые нарушения обнаружены только в несвязанных файлах `src/components/WbProductPickerDialog.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx`, `src/screens/v2/SellerInboundDraftScreen.tsx`. Для целевого `FfFbsOrdersScreen.tsx` guard показал улучшение: `свой-чип 2 → 1`, `экран-монолит 1587 → 1577`.
- `npm run test:unit` — FAIL/BLOCKED: `vitest: command not found`, локальные зависимости frontend отсутствуют.

## Не реализовано

- Полный запуск TypeScript и unit-тестов невозможен без локально установленных зависимостей; сеть для их установки не использовалась.
- Browser e2e локально не запускался по той же причине; тест добавлен с пользовательскими действиями и проверками видимого результата.

## Находки

Нет.

# Фича 5

# Screen Dev · 02-verdikt-screen · feature 5

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/tests-e2e/ff-fbs-supply.spec.ts`

В рабочем месте поставки в существующей зоне ЧЗ строки добавлен серверный вердикт WB через `StatusChip`; причина отказа и недоступность сдачи отображаются рядом через `TextCell`. Главное действие `Передать в WB` использует `PrimaryAction` и блокируется по первому заказу с `metadata.verdict.delivery_allowed === false`, с объяснением конкретного заказа. Позитивный e2e-fixture дополнен серверным вердиктом `WB: принято`, чтобы прежний сценарий передачи продолжал проверять доступное действие.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — BLOCKED: локальный запуск `npx` не завершился; зависимости frontend отсутствуют, установка не выполнялась.
- `python3 scripts/ui/ui_guard.py` — FAIL: новые нарушения обнаружены в `src/components/WbProductPickerDialog.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx` и `src/screens/v2/SellerInboundDraftScreen.tsx`; для целевого экрана guard также показал рост `экран-монолит 2493 → 2510`.
- `npm run test:unit` — FAIL/BLOCKED: `vitest: command not found`, зависимости frontend отсутствуют.

## Не реализовано

- Полный Playwright-прогон S-03-TC-004, S-03-TC-005 и S-03-TC-007 локально не запускался из-за отсутствующих frontend-зависимостей.
- Контрактные изменения в серверном API и утилите вердикта не выполнялись: они относятся к зависимым фичам и не входят в разрешённые файлы этого атомарного куска.

## Находки

Нет.
