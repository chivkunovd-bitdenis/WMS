# Фича 1

# DEV · 08-storage

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/screens/ff/FfStoragePage.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/tests-e2e/storage.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/playwright.config.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/cards/08-storage/DEV.md`

Экран вычисляет прошлый месяц по московской календарной дате. В E2E фиксирован браузерный часовой пояс `Europe/Moscow`; два целевых сценария используют пограничный момент `2026-08-31T21:30:00Z` и проверяют видимое значение `2026-08` до сохранения тарифа и повторного GET.

## Гейты

- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npx tsc --noEmit -p tsconfig.app.json`.
- Красный, не относится к этому атому: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage && python3 scripts/ui/ui_guard.py` сообщил новые нарушения в `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/components/WbProductPickerDialog.tsx`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx` и `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Эти файлы вне разрешённых границ атома; базовая линия не изменялась.
- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npm run test:unit -- --run src/screens/ff/FfStoragePage.test.ts` — 6 tests passed.
- Разбор целевого E2E зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npx playwright test tests-e2e/storage.spec.ts --grep 'S-11-TC-001|administrator keeps a previous month without a tariff after saving a later rate' --list` — найдены 2 сценария.
- Исполнение тех же двух E2E-сценариев не стартовало: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npx playwright test tests-e2e/storage.spec.ts --grep 'S-11-TC-001|administrator keeps a previous month without a tariff after saving a later rate'`. Среда запретила bind `127.0.0.1:18000` (`operation not permitted`) до запуска браузерных тестов.
- Зелёный: `git diff --check`.
- Не сохранено коммитом: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage && git add frontend/src/screens/ff/FfStoragePage.tsx frontend/tests-e2e/storage.spec.ts frontend/playwright.config.ts night/volna-9-recovery/cards/08-storage/DEV.md` не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-08-storage1/index.lock`: `Operation not permitted`. Commit SHA отсутствует.

## Не реализовано

Нет. Кодовая часть атома реализована буквально. Полный запуск двух целевых Playwright-сценариев не выполнен только из-за запрета среды на локальный порт; это не менялось в конфигурации и не обходилось.

## Находки

`ui_guard.py` выявил новые нарушения в трёх чужих файлах, не относящихся к экрану S-11 и не входящих в разрешённые файлы атома.
