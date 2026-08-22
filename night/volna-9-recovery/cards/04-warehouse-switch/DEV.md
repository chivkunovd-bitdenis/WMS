# Screen dev · 04-warehouse-switch · атом 10 · rework

Исправлена относящаяся к S-03 находка №2 из `REVIEW.md`: список поставок теперь запрашивается у сервера сразу с `warehouse_id` выбранного операционного WMS-склада. Лимит 500 применяется уже после складского фильтра, поэтому более старая поставка выбранного склада не пропадает из-за более свежих документов другого склада. До готовности WMS-контекста общий список поставок не запрашивается. Параметры WMS-поставок отделены от параметров WB-заказов, поэтому существующий фильтр склада селлера / WB не смешан с контекстом WMS.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/FfFbsOrdersScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/fbsApi.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/fbsApi.test.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/tests-e2e/ff-fbs-supply.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md`

## Гейты

- **Зелёный:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend && npx tsc --noEmit -p tsconfig.app.json`.
- **Зелёный:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend && npm run test:unit -- src/screens/v2/fbsApi.test.ts src/ui-kit/WarehouseContextSwitch.runner.test.ts` — 2 файла, 13 тестов прошли. Новый unit-кейс проверяет точный запрос `warehouse_id=warehouse-south`; suite общего переключателя из находки №6 реально исполнен и зелёный.
- **Красный на накопленном diff ветки:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch && python3 scripts/ui/ui_guard.py` — guard сообщает прежние монолиты `WbProductPickerDialog.tsx`, `FfFbsOrdersScreen.tsx`, `FfFbsStockSyncScreen.tsx`, `FfFbsSupplyWorkspace.tsx` и `SellerInboundDraftScreen.tsx`. Базовая линия флагом `--update` не менялась. Разделение монолита S-03 не входит в контракт атома и потребовало бы правки экранной архитектуры за пределами разрешённого поведения.
- **Зелёный, сценарий собран:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend && npx playwright test tests-e2e/ff-fbs-supply.spec.ts --grep "WMS warehouse context is sent to the server" --list` — найден 1 Chromium-тест. Он проверяет видимую замену поставки «Север» на поставку «Юг», серверные запросы `warehouse_id=w-1` и `warehouse_id=w-2` и отсутствие запроса без WMS-склада.
- **Не запустился из-за ограничения среды:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend && npx playwright test tests-e2e/ff-fbs-supply.spec.ts --grep "WMS warehouse context is sent to the server"` — Playwright webServer не получил право открыть `127.0.0.1:18000` (`Errno 1 operation not permitted`); браузерные шаги не исполнялись.
- **Зелёный:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch && git diff --check`.
- Полные backend `pytest`, `ruff check .` и `mypy .` не запускались согласно запрету атомарной проверки.

## Не реализовано

- Живое браузерное подтверждение нового сценария не получено: локальный API не смог привязаться к порту до старта теста.
- `ui_guard.py` не зелёный из-за накопленных превышений базовой линии в пяти экранах ветки. Baseline не обновлялся, а несвязанный архитектурный рефакторинг не выполнялся.
- Находки №1 и №3–5 из `REVIEW.md` относятся к другим атомам или слоям (`FbsSupplyCreateDialog`, S-14 и backend/seller) и в этом проходе не менялись. Находка №6 уже закрыта существующим runner-тестом ui-kit и подтверждена зелёными `tsc` и целевым unit-запуском.

## Находки

Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод `194.87.96.144` не открывались и не изменялись. Новых находок о данных или персональных данных в разрешённом frontend-слое нет.
