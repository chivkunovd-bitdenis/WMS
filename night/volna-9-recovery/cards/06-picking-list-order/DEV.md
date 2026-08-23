# Фича 1

# DEV · 06-picking-list-order · атом 1

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/app/services/fbs_order_tape_print_service.py` — полная лента использует общий безопасный ключ порядка; выборочная и строковая печать не менялись.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/app/services/fbs_supply_service.py` — ключ групп листа подбора нормализует `None` только для сравнения, сохраняя исходные значения в ответе; общий ключ добавляет числовой `wb_order_id` и `id`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/tests/test_fbs_packaging_integration.py` — добавлены проверки смешанного отсутствующего/строкового размера, групп, числового `8 → 12 → 100`, привязки различимых PNG к `orderId` и относительного порядка при неполном ответе WB.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/night/volna-9-recovery/cards/06-picking-list-order/DEV.md` — отчёт этого атома.

## Миграции

Нет.

## Гейты

- `git diff --check` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order` — пройден.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend && ruff check app/services/fbs_order_tape_print_service.py app/services/fbs_supply_service.py tests/test_fbs_packaging_integration.py` — пройден, `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend && mypy app/services/fbs_order_tape_print_service.py app/services/fbs_supply_service.py` — в изменённых модулях ошибок нет, но команда завершилась с четырьмя уже существующими ошибками зависимостей вне атома: `app/services/wildberries_credentials_service.py:167`, `app/services/fbs_stock_sync_service.py:617`, `app/services/fbs_warehouse_binding_service.py:23,291`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend && pytest tests/test_fbs_packaging_integration.py` — пройдено, `19 passed in 25.36s`.
- `python3 scripts/ci/back_guard.py` и `python3 scripts/ci/check_migrations.py` не запускались: этот атом не добавляет route или миграцию.

## Находки

- В рабочем дереве до атома уже были несвязанные изменения и удалённые артефакты; они не изменялись.

## Не реализовано

- Существующий partial-путь `wb_stickers_incomplete` / `order_qr_missing`, включая число и тексты его ошибок, не менялся: это явно сохранённое поведение данного атома, а не результат новой сортировки.
- Замечание ревью о расхождении frontend-предпросмотра и ленты не менялось: фронтенд не входит в allowlist атома и его переделка запрещена текущим scope-контрактом.

# Фича 2

# DEV · 06-picking-list-order · атом 2

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx` — «Печать всего» передаёт в существующий диалог полной ленты заказы в порядке `article → sku_code → size → product_name → wb_order_id → id`; строковая и выборочная печать используют свои прежние входные массивы.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/tests-e2e/ff-fbs-supply.spec.ts` — добавлен `TC-NEW-006`: preview с «Яблоко»/`AAA` идёт до «Альфа»/`ZZZ`, и этот же порядок попадает в `order_ids` запроса полной ленты.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/night/volna-9-recovery/cards/06-picking-list-order/DEV.md` — отчёт screen-dev.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend && npx tsc --noEmit -p tsconfig.app.json` — зелёный.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order && python3 scripts/ui/ui_guard.py` — красный только из-за двух унаследованных нарушений вне allowlist: `src/components/WbProductPickerDialog.tsx` и `src/screens/v2/SellerInboundDraftScreen.tsx`. Для изменённого `src/screens/v2/FfFbsSupplyWorkspace.tsx` новых нарушений нет; baseline не обновлялся.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend && npm run test:unit` — зелёный, `19 passed`, `138 passed`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend && pytest /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/tests/test_fbs_packaging_integration.py` — зелёный, `19 passed in 18.87s`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend && npm run test:e2e -- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/tests-e2e/ff-fbs-supply.spec.ts` — не стартовал: sandbox запретил тестовому API bind на `127.0.0.1:18000` (`[Errno 1] operation not permitted`). После `npm ci --ignore-scripts` команда дошла до запуска webServer; ошибка не относится к сценарию.
- `git diff --check` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order` — зелёный.
- `git add -- … && git commit -m "fix(fbs): align full tape preview order"` — не выполнен: sandbox не даёт создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-06-picking-list-order1/index.lock` (`Operation not permitted`). Изменения остаются в рабочем дереве и требуют коммита в среде с доступом к Git metadata worktree.

## Находки

- Прочитаны `DEV-01.md` и замороженный `REVIEW.md`; общий целевой backend-набор атома 1 зелёный. Новых находок о данных, секретах или персональных данных нет.

## Не реализовано

- Визуальный состав существующего диалога, тексты и кнопки не менялись по контракту.
- Целевой Playwright e2e не смог выполниться в этой sandbox-среде из-за запрета на сетевой bind; сценарий добавлен, но его выполнение требует среды, где разрешён локальный `127.0.0.1:18000`.
