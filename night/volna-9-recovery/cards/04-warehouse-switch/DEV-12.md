# DEV · 04-warehouse-switch · screen-dev · rework атома 12

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/fbsApi.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/FfFbsSupplyWorkspace.test.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/ui-kit/WarehouseContextSwitch.test.ts` — переименован из `WarehouseContextSwitch.test.tsx`, чтобы suite входил в маску Vitest `src/**/*.test.ts` и действительно исполнялся.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md`

Чистая функция выбора заказа и ключа повтора `resolvePickScanAttempt` перенесена из экранного модуля в разрешённый `fbsApi.ts`. Поведение сканера не менялось; unit-тест больше не загружает весь экран вместе с модулем упаковки и исполняется без зависания на сборке зависимостей.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend` — зелёный.
- `python3 scripts/ui/ui_guard.py` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch` — красный на ранее накопленном превышении базовой линии: `WbProductPickerDialog.tsx` 0 → 646, `FfFbsOrdersScreen.tsx` 1587 → 1679, `FfFbsStockSyncScreen.tsx` 1083 → 1121, `FfFbsSupplyWorkspace.tsx` 2493 → 2604 и `SellerInboundDraftScreen.tsx` 1111 → 1267. Baseline флагом `--update` не изменялся. В этом проходе размер `FfFbsSupplyWorkspace.tsx` уменьшен на 15 строк.
- `npm run test:unit -- src/screens/v2/FfFbsSupplyWorkspace.test.ts src/ui-kit/WarehouseContextSwitch.test.ts` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend` — зелёный: 2 файла, 12 тестов.
- `npx eslint src/screens/v2/fbsApi.ts src/screens/v2/FfFbsSupplyWorkspace.tsx src/screens/v2/FfFbsSupplyWorkspace.test.ts src/ui-kit/WarehouseContextSwitch.test.ts tests-e2e/ff-fbs-supply.spec.ts` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend` — зелёный.
- `npx playwright test tests-e2e/ff-fbs-supply.spec.ts --grep 'scan location then product'` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend` — красный до запуска браузерного кейса: среда запретила API webServer привязать `127.0.0.1:18000` (`operation not permitted`).
- `git diff --check` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch` — зелёный.
- `git add ...` для файлов этого атома — красный: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-04-warehouse-switch/index.lock` (`Operation not permitted`). Отдельный коммит в этой среде создать невозможно.

## Не реализовано

- Буквально не выполнен живой Playwright-прогон целевого сценария смены склада/ячейки и сетевого повтора: локальный API не смог открыть порт в этой среде. Сам сценарий сохранён в `frontend/tests-e2e/ff-fbs-supply.spec.ts`, а относящаяся к повтору чистая логика покрыта зелёными unit-тестами.
- `ui_guard.py` не доведён до зелёного: четыре из пяти нарушений находятся в соседних экранах вне файлов атома 12, а устранение оставшегося превышения потребовало бы несогласованного разбиения рабочего места на новые компоненты. Базовая линия намеренно не обновлялась.
- Находки REVIEW.md №1–5 не относятся к сканерному атому 12: это создание поставки, список поставок, упаковка, inbound API и серверное отображение ошибок. Они не исправлялись, чтобы не переходить к соседним атомам. Находка №6 исправлена в разрешённом тестовом слое: suite больше не зависит от отсутствующего пакета и теперь действительно запускается.
- Изменения локально реализованы, но не сохранены отдельным Git-коммитом из-за запрета записи в общий git-dir. До переноса/коммита из среды с доступом к `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-04-warehouse-switch` diff можно потерять.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод не читались и не изменялись.
