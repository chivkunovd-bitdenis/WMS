# DEV · 04-warehouse-switch · screen-dev

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/FfFbsOrdersScreen.tsx
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — зелёный.
- `python3 scripts/ui/ui_guard.py` — зелёный.
- `npm run test:unit` — зелёный.

## Не реализовано

- Backend-находки из `REVIEW.md` не исправлялись: они находятся вне разрешённых файлов роли `screen-dev`.
- E2E-браузерный прогон не выполнялся: обязательные для этой роли проверки выполнены, а контракт требует отдельного product browser review.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод не открывались и не изменялись.
