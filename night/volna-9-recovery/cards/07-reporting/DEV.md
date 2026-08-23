# Фича 1

# Backend-dev · 07-reporting · атом 1 · повторная доработка

## Что реализовано

- Эндпоинты: существующие `GET /reports/overview`, `GET /reports/inventory` и `GET /reports/inventory/export.csv` отвечают `403 forbidden` сотруднику ФФ с `cells=true` и `inventory=false`; администратор ФФ, сотрудник с `inventory=true` и селлер с действующим `can_products` сохраняют доступ.
- Сервисы: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/app/api/deps.py::assert_inventory_read_access` принимает у сотрудника ФФ для отчётов только `inventory`, без права ячеек.

## Миграции

Нет.

## Тесты

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/tests/test_reports_inventory.py::test_reports_require_inventory_for_ff_staff_but_keep_allowed_roles` создаёт сотрудника ФФ с `cells=true, inventory=false` и проверяет `403` с `detail=forbidden` для сводки, строк и CSV. В том же сценарии закреплён `200` для администратора ФФ, сотрудника с `inventory=true` и селлера.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/app/api/deps.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/tests/test_reports_inventory.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/night/volna-9-recovery/cards/07-reporting/DEV.md`

## Гейты

- ЗЕЛЁНЫЙ: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend && ruff check app/api/deps.py tests/test_reports_inventory.py` — `All checks passed!`, код завершения 0.
- ЗЕЛЁНЫЙ: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend && mypy --follow-imports=silent app/api/deps.py tests/test_reports_inventory.py` — `Success: no issues found in 2 source files`, код завершения 0.
- ЗЕЛЁНЫЙ: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend && pytest -q tests/test_reports_inventory.py` — `5 passed in 18.03s`, код завершения 0.
- ЗЕЛЁНЫЙ: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting && git diff --check` — ошибок формата diff нет, код завершения 0.
- `python3 scripts/ci/back_guard.py` не запускался: новый роут не добавлялся.
- `python3 scripts/ci/check_migrations.py` не запускался: миграция не добавлялась.
- Полные `pytest`/`pytest -q` без путей, `ruff check .` и `mypy .` не запускались: границы атома запрещают полный backend-регресс.

## Не реализовано

- Нет: атом из `FEATURES.md` и серверная находка №1 из `REVIEW.md` реализованы буквально. Находка №2 относится к маршрутизации самостоятельного frontend-приложения селлера и не менялась этой backend-ролью.

## Блокеры

- Обновлённый отчёт не удалось сохранить отдельным commit: команда `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting && git add night/volna-9-recovery/cards/07-reporting/DEV.md && git diff --cached --check && git commit -m "docs(reporting): record backend atom gates"` завершилась с кодом 128, потому что sandbox запретил создание `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-07-reporting1/index.lock` (`Operation not permitted`). Реализация и тесты атома уже сохранены в commit `cb8e509aa148`; обновление `DEV.md` остаётся в рабочем дереве.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, production `194.87.96.144` и живой кабинет Wildberries не читались и не затрагивались.

# Фича 2

# Screen-dev · 07-reporting · атом 2 · повторная доработка

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/tests-e2e/ff-reports.spec.ts` — сценарий S-33-TC-015 закрепляет профиль сотрудника ФФ `cells=true, inventory=false`, прямой адрес `/app/ff/reports`, видимое состояние отказа, отсутствие пункта меню и всех блоков отчёта, а также отсутствие запросов `/api/reports/*`. Исправление уже находится в текущей ветке в commit `b4342ba84686299b315192316d2ac0bbcafab942`; в этом проходе содержимое файла не менялось повторно.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/night/volna-9-recovery/cards/07-reporting/DEV.md` — отчёт screen-dev по этому атому.

## Гейты

- ЗЕЛЁНЫЙ: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npx tsc --noEmit -p tsconfig.app.json` — код завершения 0.
- ЗЕЛЁНЫЙ: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npm run test:unit -- src/screens/ff/FfReportsPage.test.tsx` — `1 passed`, код завершения 0.
- КРАСНЫЙ, вне границ атома: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting && python3 scripts/ui/ui_guard.py` — обнаружены новые нарушения в `src/App.tsx`, `src/components/WbProductPickerDialog.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx` и `src/screens/v2/SellerInboundDraftScreen.tsx`. Все они вне разрешённого файла этого атома; базовая линия не обновлялась.
- НЕ ЗАПУЩЕН ДО КОНЦА из-за ограничений среды: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npx playwright test tests-e2e/ff-reports.spec.ts --grep 'cells access but without inventory access'` — Playwright не смог запустить API, так как bind `127.0.0.1:18000` завершился `operation not permitted`. Сам тест не начал выполнение.
- Полный `npm run test:e2e`, полный backend `pytest`, `ruff check .` и `mypy .` не запускались: они запрещены границами атомарной проверки.

## Не реализовано

- В коде нет нереализованных пунктов атома: требуемый тестовый профиль, маршрут, видимые проверки и контроль отсутствия отчётных запросов уже реализованы буквально.
- Живой e2e-прогон не подтверждён только из-за запрета среды на открытие локального порта; это не исправляется в разрешённом тестовом файле.

## Блокеры

- Отчёт не удалось сохранить отдельным commit: `git add night/volna-9-recovery/cards/07-reporting/DEV.md && git diff --cached --check && git commit -m "night(07-reporting): record screen atom gates"` завершилась ошибкой создания `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-07-reporting1/index.lock` (`Operation not permitted`). `DEV.md` сохранён в рабочем дереве, но не зафиксирован.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, production `194.87.96.144` и живой кабинет Wildberries не читались и не затрагивались.

# Фича 3

# Screen-dev · 07-reporting · атом 3 · повторная доработка

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/Dockerfile.seller.prod` — production-сборка самостоятельного кабинета селлера задаёт `VITE_SELLER_ROUTER_BASENAME=/app/seller`, поэтому канонический адрес `/app/seller/reports` сопоставляется с маршрутом `/reports` внутри `SellerApp`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/tests-e2e/seller-reports.spec.ts` — S-33-TC-016 открывает именно `/app/seller/reports`, сохраняет проверку неизменности URL, видимого отказа и отсутствия вызовов `/api/reports/*`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/night/volna-9-recovery/cards/07-reporting/DEV.md` — артефакт этого атома.

## Гейты

- ЗЕЛЁНЫЙ: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npx tsc --noEmit -p tsconfig.app.json` — код завершения 0.
- ЗЕЛЁНЫЙ: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npm run test:unit -- src/apps/seller/SellerApp.test.tsx` — `2 passed`, код завершения 0.
- ЗЕЛЁНЫЙ: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npx playwright test tests-e2e/seller-reports.spec.ts --grep 'seller staff without products access cannot open the direct reports route' --list` — один изменённый сценарий обнаружен и скомпилирован, код завершения 0.
- НЕ ЗАПУЩЕН ДО КОНЦА из-за ограничений среды: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npx playwright test tests-e2e/seller-reports.spec.ts --grep 'seller staff without products access cannot open the direct reports route'` — Playwright не начал сценарий: его API webServer не смог привязаться к `127.0.0.1:18000` (`operation not permitted`).
- НЕ ПРОВЕРЕНА СБОРКА: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting && docker build -f frontend/Dockerfile.seller.prod -t wms-seller-reports-route-check .` — Docker socket недоступен (`permission denied while trying to connect to the docker API`), образ не создан.
- КРАСНЫЙ, вне разрешённых файлов атома: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting && python3 scripts/ui/ui_guard.py` — новые нарушения в `frontend/src/App.tsx`, `frontend/src/components/WbProductPickerDialog.tsx`, `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`, `frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Они существовали до этой доработки и не относятся к двум разрешённым файлам; baseline не менялась.
- ЗЕЛЁНЫЙ: `git diff --check -- frontend/Dockerfile.seller.prod frontend/tests-e2e/seller-reports.spec.ts` — ошибок пробелов нет.
- Полный `npm run test:e2e`, полный backend `pytest`, `ruff check .` и `mypy .` не запускались: они запрещены границами атомарной проверки.

## Не реализовано

- Ни один пункт атома не оставлен нереализованным в коде: basename production-сборки и канонический маршрут e2e-сценария исправлены буквально.
- Доказательство через запущенный браузер и самостоятельный Docker-образ не получено только из-за ограничений среды на сетевой bind и Docker socket; это не исправляется в разрешённых файлах атома.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, production `194.87.96.144` и живой кабинет Wildberries не читались и не затрагивались.
