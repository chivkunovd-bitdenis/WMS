# DEV · 04-warehouse-switch · атом 7

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/tests-e2e/inbound-intake.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/tests-e2e/outbound-submit-storage.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md`

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` (каталог `frontend/`) — зелёный.
- `python3 scripts/ui/ui_guard.py` (корень) — красный из-за пяти уже существующих отклонений вне разрешённых файлов атома: `src/components/WbProductPickerDialog.tsx`, `src/screens/v2/FfFbsOrdersScreen.tsx`, `src/screens/v2/FfFbsStockSyncScreen.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx`, `src/screens/v2/SellerInboundDraftScreen.tsx`. Базовую линию не обновлял.
- `npm run test:unit -- --run` (каталог `frontend/`) — не запустился: `sh: vitest: command not found`.
- `npx playwright test tests-e2e/inbound-intake.spec.ts tests-e2e/outbound-submit-storage.spec.ts --workers=1` (каталог `frontend/`) — зелёный.
- `git diff --check` — зелёный.
- Commit не создан: Git не разрешил создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-04-warehouse-switch/index.lock` (`Operation not permitted`). Результат остаётся локальным незакоммиченным diff.

## Не реализовано

- Нет. Экраны S-22 и S-24 уже получают склад нового документа из сессионного контекста и показывают ячейки открытого документа; ревью-пункт №15 закрыт проверками для двух складов. Остальные находки вердикта относятся к другим экранам либо серверному слою и не входят в этот атом.

## Находки

- В этой рабочей копии unit-зависимость `vitest` отсутствует, поэтому обязательный unit-гейт нельзя выполнить до восстановления зависимостей.
