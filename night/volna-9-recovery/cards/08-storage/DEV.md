# Фича 1

# DEV · 08-storage · Атом 1: серверная ручка тарифа хранения

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/api/storage.py` — зарегистрирован `POST /operations/storage/tariffs`; доступ ограничен ролью `fulfillment_admin`, ответ — `201` с созданными версиями тарифа.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/services/storage_statement_service.py` — `create_storage_tariff()` сохраняет общую ставку склада и необязательное исключение селлера одной транзакцией; при конфликте откатывает обе записи.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/tests/test_storage_tariff_api.py` — покрыты создание общей ставки, исключение селлера с откатом при конфликте второй вставки и запрет для сотрудника с правом `inventory`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/cards/08-storage/DEV.md` — отчёт по атому.

## Гейты

Выполнены точные целевые команды:

```text
cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && pytest -q tests/test_storage_tariff_api.py
```

Результат: `3 passed in 3.70s`.

```text
cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && ruff check app/api/storage.py app/services/storage_statement_service.py tests/test_storage_tariff_api.py
```

Результат: `All checks passed!`.

```text
cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && mypy app/api/storage.py app/services/storage_statement_service.py
```

Результат: не пройден из-за пяти существующих ошибок в трёх несвязанных файлах: `app/services/wildberries_credentials_service.py`, `app/services/fbs_stock_sync_service.py`, `app/services/fbs_warehouse_binding_service.py`. В изменённых файлах этого атома ошибок не выведено.

```text
cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage && python3 scripts/ci/back_guard.py
```

Результат: неприменимый скрипт отсутствует в данной рабочей копии (`scripts/ci/back_guard.py: No such file or directory`). Маршрут покрыт новым целевым API-тестом.

Миграции не добавлялись; `check_migrations.py` для этого атома не применяется.

## Не реализовано

Нет. Реализован ровно первый атом из `FEATURES.md`; следующие frontend-атомы не затрагивались.

# Фича 3

# DEV · 08-storage · атом 3 · переделка по REVIEW

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/tests-e2e/storage.spec.ts` — `S-11-TC-002` теперь раскрывает индивидуальную ставку и проверяет ровно один POST с `seller_exception` в теле. Экран уже содержал исправленные вызов `getMoscowDateString()` и один объединённый POST; серверный маршрут из находки 1 существует по `POST /operations/storage/tariffs`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/cards/08-storage/DEV.md` — отчёт этого атома.

## Гейты

- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npx tsc --noEmit -p tsconfig.app.json`.
- Красный вне атома: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage && python3 scripts/ui/ui_guard.py` сообщил только о существующих нарушениях в `/frontend/src/components/WbProductPickerDialog.tsx`, `/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx` и `/frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Эти файлы не относятся к S-11 и не изменялись; базовая линия не обновлялась.
- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npm run test:unit -- src/utils/moscowDate.test.ts` — 4 passed.
- Не выполнен из-за среды: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npx playwright test tests-e2e/storage.spec.ts --grep 'S-11-TC-002'`. Playwright webServer не может bind `127.0.0.1:18000`: `operation not permitted`.

## Не реализовано

- Нет. Все три находки REVIEW в границах атома закрыты: маршрут существует, экран отправляет один объединённый запрос, даты тарифа получают московский календарный день. Сквозной Playwright-запуск не подтверждён только из-за запрета среды на запуск test webServer.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных и production не открывались и не использовались.
- Изменения не удалось сохранить commit: Git не может создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-08-storage1/index.lock` (`Operation not permitted`). Рабочая копия содержит незакоммиченные изменения только в указанном e2e-тесте и этом отчёте; чужой `/night/volna-9-recovery/JOURNAL.md` не затрагивался.

# Фича 4

# DEV · 08-storage · атом 4

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/tests-e2e/storage.spec.ts` — из `S-11-TC-002` удалён перехват `POST /api/operations/storage/tariffs` и связанная с ним проверка перехваченного тела; сценарий теперь использует ответ реального тестового сервера.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/cards/08-storage/DEV.md` — отчёт этого атома.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npx tsc --noEmit -p tsconfig.app.json` — зелёный.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage && python3 scripts/ui/ui_guard.py` — красный из-за трёх новых отступлений в незатронутых этим атомом файлах: `frontend/src/components/WbProductPickerDialog.tsx`, `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`, `frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Базовую линию не менял.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npx playwright test tests-e2e/storage.spec.ts --grep 'S-11-TC-002'` — не запустился: sandbox запретил test webServer bind на `127.0.0.1:18000` (`[Errno 1] operation not permitted`). Это ограничение среды, до выполнения теста дело не дошло.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && grep -n 'route.*tariffs' tests-e2e/storage.spec.ts` — 0 совпадений.
- `npm run test:unit` не запускался: в атоме меняется только Playwright-тест, а атомарная инструкция разрешает запускать только тестовые файлы и кейсы этого атома и относящиеся к нему регрессии.

## Не реализовано

- Нет. Сам кодовый результат атома реализован буквально: мок тарифного эндпоинта удалён. Адресный e2e-прогон требует среды, в которой разрешён bind тестового сервера.

## Находки

- `ui_guard.py` выявил три отступления вне файлов и слоя данного атома; они не исправлялись по границам задачи.
- Изменения не удалось сохранить commit: Git не может создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-08-storage1/index.lock` (`Operation not permitted`). В рабочей копии изменения остаются незакоммиченными; несвязанный `night/volna-9-recovery/JOURNAL.md` не затрагивался.
