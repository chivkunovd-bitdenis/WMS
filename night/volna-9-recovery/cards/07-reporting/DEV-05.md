# Screen-dev · 07-reporting · атом 5 · rework

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/apps/seller/SellerApp.tsx` — `is_operational` сделан обязательной частью ответа склада; отчёт селлера больше не угадывает назначение склада по имени и принимает только строки с `is_operational=true`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/apps/seller/SellerApp.test.tsx` — адресный unit-тест закрепляет, что переименованный `Архив` исключается по API-признаку, а имя с префиксом `FBS WB` само по себе не исключает операционный склад.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/tests-e2e/seller-reports.spec.ts` — сценарий `S-33-TC-003 / S-33-TC-014` возвращает один операционный склад и переименованный неоперационный `Архив`, создаёт движения двух селлеров в одном tenant и проверяет скрытие складского и селлерского фильтров, отсутствие `Архива` и отсутствие SKU другого селлера в таблице.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/night/volna-9-recovery/cards/07-reporting/DEV.md` — отчёт текущей роли.

## Гейты

- **ЗЕЛЁНЫЙ:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npx tsc --noEmit -p tsconfig.app.json` — код завершения 0.
- **КРАСНЫЙ ИЗ-ЗА НАКОПЛЕННОГО СОСТОЯНИЯ ВЕТКИ:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting && python3 scripts/ui/ui_guard.py` — код завершения 1. Сторож показал уже существующие превышения baseline в `src/App.tsx` (`3492 → 3511`), `src/components/WbProductPickerDialog.tsx` (`0 → 646`), `src/screens/v2/FfFbsSupplyWorkspace.tsx` (`2493 → 2498`) и `src/screens/v2/SellerInboundDraftScreen.tsx` (`1111 → 1169`). Текущий атом не меняет эти файлы; `SellerApp.tsx` остался длиной 542 строки до и после правки. Baseline флагом `--update` не менялась.
- **ЗЕЛЁНЫЙ:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npm run test:unit -- src/apps/seller/SellerApp.test.tsx` — 1 файл, 2 теста, `2 passed`, код завершения 0.
- **КРАСНЫЙ ИЗ-ЗА ОГРАНИЧЕНИЯ СРЕДЫ:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npx playwright test tests-e2e/seller-reports.spec.ts --grep "seller reports exclude non-operational warehouses and other seller data"` — Playwright не дошёл до сценария: тестовый API не смог открыть `127.0.0.1:18000`, `Errno 1: operation not permitted`; код завершения 1.
- **ЗЕЛЁНЫЙ, обнаружение и компиляция сценария без webServer:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npx playwright test tests-e2e/seller-reports.spec.ts --grep "seller reports exclude non-operational warehouses and other seller data" --list` — найден ровно 1 тест в 1 файле, код завершения 0.
- **ЗЕЛЁНЫЙ:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting && git diff --check` — ошибок формата diff нет, код завершения 0.
- Полный backend-регресс, полный Playwright, `ruff check .` и `mypy .` не запускались: условия атома прямо запрещают эти команды на текущем шаге.

## Не реализовано

- Пунктов контракта, не реализованных буквально в коде атома 5, нет.
- Живая браузерная проверка не состоялась: sandbox запрещает тестовому API открыть локальный порт. Сценарий обнаруживается и компилируется, но реальные действия браузера и проверка DOM в этом проходе не выполнялись.

## Блокеры

- Локальная реализация не сохранена в Git commit: команда `git add frontend/src/apps/seller/SellerApp.tsx frontend/src/apps/seller/SellerApp.test.tsx frontend/tests-e2e/seller-reports.spec.ts night/volna-9-recovery/cards/07-reporting/DEV.md && git diff --cached --check && git diff --cached --stat && git commit -m "fix(reports): filter seller warehouses by operational flag"` не смогла создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-07-reporting1/index.lock` и завершилась с `Operation not permitted`. Изменения остаются в рабочем дереве без commit SHA. Чужой `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/night/volna-9-recovery/JOURNAL.md` не индексировался и не изменялся этой ролью.

## Находки

- Новых находок по данным, утечкам, секретам или персональным данным в границах атома нет.
- Секреты, ключи, токены, `.env`, кабинеты учётных данных, production `194.87.96.144` и живой кабинет Wildberries не читались и не затрагивались.
