## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/src/screens/v2/FfFbsOrdersScreen.tsx
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/night/volna-9-recovery/cards/05-prod-slow/DEV.md

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — не завершён: локальный процесс `tsc` завис без вывода и был остановлен.
- `python3 scripts/ui/ui_guard.py` — красный: обнаружены новые нарушения в `FfFbsOrdersScreen.tsx` (монолит/своя кнопка), а также нарушения в соседних файлах; базовую линию не обновлял.
- `npm run test:unit` — красный: `vitest: command not found`.

## Не реализовано

- Полный Playwright-набор `S-03-TC-001`–`S-03-TC-007`, `S-03-TC-010`–`S-03-TC-012` не запускался: в окружении отсутствует runner зависимостей.
- Backend- и печатные находки из REVIEW.md не менялись: они не относятся к разрешённому экранному слою этого атома.
