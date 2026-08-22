## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/src/screens/v2/FfFbsOrdersScreen.tsx
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/src/screens/v2/fbsApi.ts
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/tests-e2e/ff-fbs-orders.spec.ts

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — зелёный.
- `python3 scripts/ui/ui_guard.py` — красный: обнаружены нарушения-монолиты в `FfFbsOrdersScreen.tsx` и трёх ранее затронутых экранах; базовая линия не обновлялась.
- `npm run test:unit` — красный: `vitest: command not found` в окружении.

## Не реализовано

- Полный Playwright-набор `S-03-TC-001`–`S-03-TC-007`, `S-03-TC-010`–`S-03-TC-012` не запускался: в доступных обязательных командах отсутствует unit runner, а браузерный стенд не поднимался в рамках этой роли.
- `fbsApi.ts` не потребовал изменения: функция `fetchFbsWorklist` уже поддерживала `cursor` и `next_cursor`.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой прод `194.87.96.144` и живой кабинет Wildberries не читались и не затрагивались.
