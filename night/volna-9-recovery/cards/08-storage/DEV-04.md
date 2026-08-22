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
