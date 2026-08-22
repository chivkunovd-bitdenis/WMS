# screen-dev · 08-storage · атом 1

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/ui-kit/Actions.test.tsx` — тест закрепляет «Печать накладной» для `row` и `panel`, а также сохранение прежних подписей и disabled-подсказок в обоих размещениях.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/ui-kit/Actions.tsx` — проверен в рамках атома: закрытый словарь `PrintAction` уже содержит внутреннее правило `накладную → накладной`; публичный интерфейс компонента не изменён.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/cards/08-storage/DEV.md` — артефакт выполнения атома.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend` — зелёный.
- `python3 ../scripts/ui/ui_guard.py` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend` — зелёный.
- `npm run test:unit` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend` — зелёный.

## Не реализовано

Пунктов контракта, которые не удалось реализовать буквально в этом атоме, нет. Находки `REVIEW.md` относятся к серверному хранению и экрану S-11; они не затрагивают разрешённые файлы UI-kit атома 1.

Git-коммит не создан: среда запрещает Git создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-08-storage1/index.lock` (`Operation not permitted`). Поэтому результат реализован локально, но не сохранён коммитом.
