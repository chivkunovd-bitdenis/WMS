# Screen dev · 04-warehouse-switch · атом 9 · rework

Исправлена относящаяся к preflight находка №1 из `REVIEW.md`: диалог теперь читает точную серверную разбивку `source_warehouses[]` и показывает оператору каждый склад с исполнимым количеством. Для ответа «Юг — 6, Север — 4» больше не выводится безымянный остаток «другие склады — 4».

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/fbsApi.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/FbsSupplyCreateDialog.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/FbsSupplyCreateDialog.test.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/tests-e2e/ff-fbs-supply.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md`

## Гейты

- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend && npx tsc --noEmit -p tsconfig.app.json`.
- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend && npm run test:unit -- src/screens/v2/FbsSupplyCreateDialog.test.ts` — 1 файл, 3 теста прошли.
- Красный из-за чужой базовой линии: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch && python3 scripts/ui/ui_guard.py` — новые нарушения только в `WbProductPickerDialog.tsx`, `FfFbsOrdersScreen.tsx`, `FfFbsStockSyncScreen.tsx`, `FfFbsSupplyWorkspace.tsx`, `SellerInboundDraftScreen.tsx`; в затронутом `FbsSupplyCreateDialog.tsx` результат улучшился: `своя-кнопка 3 → 2`. Базовая линия не обновлялась.
- Не запустился из-за ограничения окружения: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend && npx playwright test tests-e2e/ff-fbs-supply.spec.ts --grep "fbs orders: create supply from selected orders"` — тестовый API не смог привязаться к `127.0.0.1:18000`, `operation not permitted`; сценарий не исполнялся.
- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend && git diff --check`.
- Не сохранено в Git из-за прав среды: точечный `git add` пяти файлов атома и `git commit -m "fix(fbs): show exact preflight source warehouses"` остановились на создании `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-04-warehouse-switch/index.lock` с `Operation not permitted`. Чужой `night/volna-9-recovery/JOURNAL.md` не добавлялся.

Полный backend `pytest`, `ruff check .` и `mypy .` не запускались согласно ограничению атомарной проверки.

## Не реализовано

- Буквально не подтверждён браузером целевой E2E-сценарий: запуск остановлен системным запретом bind до старта браузерного теста. Сам mock и видимые ожидания переведены на фактический серверный контракт `source_warehouse: null` + два элемента `source_warehouses[]`.
- Находка №2 из `REVIEW.md` относится к соседнему атому списка поставок S-03 и требует изменения `FfFbsOrdersScreen.tsx`, которого нет в файлах атома 9; она здесь не исправлялась. Находки №3–6 также относятся к другим экранам и слоям.
- Других пунктов контракта этого rework, которые не удалось реализовать буквально, нет.
- Отдельный commit SHA не получен из-за запрета записи в служебный Git-каталог worktree; изменения существуют только в рабочем дереве и требуют сохранения оркестратором.

## Находки

- Новых находок по данным, секретам или персональным данным нет.
