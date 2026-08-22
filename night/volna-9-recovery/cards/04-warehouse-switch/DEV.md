# DEV · 04-warehouse-switch · screen-dev · rework атома 12

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/FfFbsSupplyWorkspace.test.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/tests-e2e/ff-fbs-supply.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md`

## Что проверено и закреплено

- Успешный скан склада меняет склад консолидации и оставляет `ScannerLine` в состоянии ожидания склада или ячейки.
- Скан ячейки другого склада выбирает фактическое место подбора, но не переписывает склад консолидации поставки.
- Ошибочный скан сохраняет склад, ячейку и следующий ожидаемый шаг.
- После первого успешного подбора скан другого склада показывает `Склад закреплён: подбор уже начат` и не сбрасывает ячейку.
- Сетевой повтор той же операции сохраняет `order_id` и ключ идемпотентности; вторая физическая единица одинакового SKU выбирает следующий заказ и новый ключ.
- Успешный pick показывает одну строку `Взято: Основной склад / ячейка A-01`, при этом склад консолидации остаётся `Склад Юг`.

Экранная логика для находок ревью №2 и №3 уже присутствовала в текущем `HEAD` после rework предыдущего атома. В этом проходе усилены unit- и E2E-проверки находки №12, чтобы регрессия больше не оставалась зелёной.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend` — красный до проверки изменённых сценариев: существующий `/frontend/src/ui-kit/WarehouseContextSwitch.test.tsx` не находит `@testing-library/react` и DOM-matchers. Изменённые файлы в ошибках не перечислены.
- `python3 scripts/ui/ui_guard.py` из корня — красный на существующих отклонениях базовой линии: `WbProductPickerDialog.tsx`, `FfFbsOrdersScreen.tsx`, `FfFbsStockSyncScreen.tsx`, `FfFbsSupplyWorkspace.tsx` и `SellerInboundDraftScreen.tsx` отмечены как экраны-монолиты. Базовая линия не изменялась.
- `npm run test:unit` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend` — зелёный: 22 файла, 157 тестов.
- `npm run test:unit -- src/screens/v2/FfFbsSupplyWorkspace.test.ts` — зелёный: 1 файл, 5 тестов.
- `npx eslint src/screens/v2/FfFbsSupplyWorkspace.test.ts tests-e2e/ff-fbs-supply.spec.ts` — зелёный.
- `npx playwright test tests-e2e/ff-fbs-supply.spec.ts --grep "scan location then product"` — не запущен до браузерных шагов: sandbox запретил Playwright webServer привязать локальный API к `127.0.0.1:18000` (`operation not permitted`).
- `git diff --check` — зелёный.
- Git-коммит — не создан: среда запретила создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-04-warehouse-switch/index.lock` (`Operation not permitted`). Изменения локально реализованы, но не сохранены отдельным коммитом и не опубликованы.

## Не реализовано

- Буквально не выполнен браузерный прогон целевого E2E-сценария: локальный порт запрещён средой выполнения. Сам сценарий прошёл TypeScript/ESLint-разбор в пределах доступных проверок, но это не заменяет запуск Playwright.
- Результат не сохранён в Git из-за запрета записи в общий git-dir worktree; до коммита локальный diff можно потерять.
- Красные `tsc` и `ui_guard.py` не исправлялись, потому что причины находятся в ранее изменённых общем ui-kit и соседних экранах либо требуют выноса более 126 строк из монолита; это выходит за разрешённые файлы и границы атома 12.
- `frontend/src/screens/v2/fbsApi.ts`, `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx` и `frontend/src/ui-kit/ScannerLine.tsx` не менялись: относящиеся к вердикту исправления в них уже есть, дополнительных расхождений с атомом 12 не найдено.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод не читались и не изменялись.
