# Screen-dev · 07-reporting · атом 4 · rework

## Что реализовано

- Тип склада в клиенте теперь требует обязательный булев признак `is_operational`, который публикует уже выполненный атом 3.
- В отчёт ФФ передаются только склады с `is_operational=true`; эвристика по префиксу `FBS WB ` удалена.
- Playwright-сценарий `S-33-TC-003 / S-33-TC-014` подменяет `/api/warehouses` ровно двумя складами: одним операционным и переименованным `Архив` с `is_operational=false`; проверяет, что `Архив` не доступен, а селектор одного оставшегося склада скрыт.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/App.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/tests-e2e/ff-reports.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/night/volna-9-recovery/cards/07-reporting/DEV.md`

## Гейты

- **ЗЕЛЁНЫЙ:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npx tsc --noEmit -p tsconfig.app.json` — код завершения 0.
- **КРАСНЫЙ ИЗ-ЗА НАКОПЛЕННОГО СОСТОЯНИЯ ВЕТКИ:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting && python3 scripts/ui/ui_guard.py` — код завершения 1. Сторож показал уже существовавшие до атома превышения общей baseline: `src/App.tsx: экран-монолит 3492 → 3511`, `src/components/WbProductPickerDialog.tsx: 0 → 646`, `src/screens/v2/FfFbsSupplyWorkspace.tsx: 2493 → 2498`, `src/screens/v2/SellerInboundDraftScreen.tsx: 1111 → 1169`. Текущий diff атома не добавляет строк в `App.tsx`: и в `HEAD`, и после правки файл имеет 3510 строк по `wc -l`. Три других файла не входят в границы атома. Baseline флагом `--update` не двигалась.
- **ЗЕЛЁНЫЙ:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npm run test:unit -- src/screens/ff/FfReportsPage.test.tsx` — 1 файл, 1 тест, `1 passed`, код завершения 0.
- **КРАСНЫЙ ИЗ-ЗА ОГРАНИЧЕНИЯ СРЕДЫ:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npx playwright test tests-e2e/ff-reports.spec.ts --grep "FF reports exclude non-operational warehouses from the warehouse filter"` — Playwright не дошёл до браузерного теста: тестовый API не смог открыть `127.0.0.1:18000`, `Errno 1: operation not permitted`; код завершения 1.
- **ЗЕЛЁНЫЙ, обнаружение и компиляция сценария без webServer:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npx playwright test tests-e2e/ff-reports.spec.ts --grep "FF reports exclude non-operational warehouses from the warehouse filter" --list` — найден 1 тест в 1 файле, код завершения 0.
- **ЗЕЛЁНЫЙ:** `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting && git diff --check` — ошибок формата diff нет, код завершения 0.
- Полные backend-прогоны и полный Playwright не запускались: текущий шаг разрешает только атомарную проверку.

## Не реализовано

- Пунктов контракта, не получивших буквальной реализации в границах атома 4, нет.
- Не завершена только живая браузерная проверка: sandbox запретил поднять локальный API. Сценарий обнаруживается и компилируется, но фактический клик и проверка DOM в этом проходе не состоялись.

## Находки

- Новых находок по данным или видимому поведению в границах атома нет.
- Секреты, ключи, токены, `.env`, кабинеты учётных данных, production `194.87.96.144` и живой кабинет Wildberries не читались и не затрагивались.
