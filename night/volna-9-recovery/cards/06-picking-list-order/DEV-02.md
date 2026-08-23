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
