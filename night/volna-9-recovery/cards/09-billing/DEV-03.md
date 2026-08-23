# 09-billing — screen-dev, атом 3

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfBillingScreen.tsx` — в текущем состоянии ветки режим «По исполнителям» уже использует фиксированную сетку `220 / 150 / 150 / 120 / 120 px`; длинное имя ограничено общим `TextCell`, а «Количество» и «Документов» выровнены вправо. Повторная проверка этого атома не потребовала новой правки исходника.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/tests-e2e/billing-ledger.spec.ts` — в текущем состоянии ветки уже есть `S-31-TC-005`: сценарий с длинным именем проверяет пять заголовков и ширины, многоточие, правое выравнивание чисел и отсутствие денежных колонок. Повторная проверка не потребовала новой правки теста.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/cards/09-billing/DEV.md` — восстановлен обязательный отчёт этого атома.

## Гейты

- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && task_tmp_dir=$(mktemp -d /private/tmp/wms-billing-unit.XXXXXX) && TMPDIR="$task_tmp_dir" npm run test:unit -- src/screens/ff/FfBillingScreen.test.ts --pool=threads --maxWorkers=1 --minWorkers=1` — 1 файл, 4 теста пройдены.
- Красный, существующие ошибки ветки: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npx tsc --noEmit -p tsconfig.app.json` — код возврата 2. В `FfBillingScreen.tsx` остаётся несовместимость условного `DataTable` для `LedgerEntry`/`PerformerRow` и прежние MUI-пропсы; также ошибки уже есть в `FfSettingsScreen.tsx`, `SellersScreen.tsx` и `PeriodPicker.tsx`. Фикс сетки пяти колонок новых ошибок не добавил; исправление чужих частей не входит в этот атом.
- Красный, существующий храповик: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing && python3 scripts/ui/ui_guard.py` — код возврата 1. Зафиксированы только прежние экран-монолиты `WbProductPickerDialog.tsx` (`0 → 646`), `FfSettingsScreen.tsx` (`701 → 795`), `FfFbsSupplyWorkspace.tsx` (`2493 → 2498`) и `SellerInboundDraftScreen.tsx` (`1111 → 1169`); `FfBillingScreen.tsx` в выводе отсутствует. Базовая линия флагом `--update` не менялась.
- Зелёный выбор атомарного E2E: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && task_tmp_dir=$(mktemp -d /private/tmp/wms-billing-e2e.XXXXXX) && TMPDIR="$task_tmp_dir" npx playwright test tests-e2e/billing-ledger.spec.ts --grep "billing ledger performer mode keeps fixed columns and hides money" --list` — найден ровно 1 кейс в 1 файле.
- Красный по ограничениям среды: та же команда без `--list` — Playwright не дошёл до браузерного сценария, поскольку API не смог привязаться к `127.0.0.1:18000` (`operation not permitted`). Конфигурация, порты и тестовые данные не менялись ради обхода.

Полный backend `pytest`, `ruff check .` и `mypy .` не запускались: они запрещены для атомарной проверки. Полный E2E-регресс также не запускался.

## Не реализовано

Пунктов контракта и находок `DESIGN-REVIEW.md`, относящихся к атому 3, не осталось: R-09 в таблице «По исполнителям» уже реализован буквально. Живой Playwright-прогон не выполнен только из-за запрета среды на локальный порт.

## Находки

- `FfBillingScreen.tsx` и маршрут `/app/ff/billing` отсутствуют в `frontend/screens.registry.json`; существующий `S-31` принадлежит другому экрану. Реестр не входит в разрешённые файлы атома и не изменялся.
- Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой прод `194.87.96.144` и живой кабинет Wildberries не открывались и не затрагивались.
