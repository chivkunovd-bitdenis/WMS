# 08-storage · screen-dev · атом 2

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/screens/ff/FfStoragePage.tsx` — всем пяти колонкам `DataTable` диалога «История габаритов» заданы явные ширины: 170, 140, 250, 180 и 140 px.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/tests-e2e/storage.spec.ts` — сценарий S-11-TC-007 открывает историю через UI, с длинным именем автора проверяет порядок всех заголовков, объявленные ширины и видимый статус «Действует».
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/cards/08-storage/DEV.md` — этот артефакт выполнения.

## Гейты

- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npx tsc --noEmit -p tsconfig.app.json`.
- Красный вне границ атома: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage && python3 scripts/ui/ui_guard.py` сообщает о трёх уже существующих отступлениях в чужих файлах: `frontend/src/components/WbProductPickerDialog.tsx`, `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`, `frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Файлы не принадлежат S-11 и не менялись.
- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npm run test:unit -- src/screens/ff/FfStoragePage.test.ts` — 6 tests passed.
- Playwright-сценарий найден: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npx playwright test storage.spec.ts --grep 'S-11-TC-007 opens dimension history' --list` — 1 test.
- Полный запуск только этого сценария: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npx playwright test storage.spec.ts --grep 'S-11-TC-007 opens dimension history'` — не стартовал: sandbox запретил API webServer привязать `127.0.0.1:18000` (`operation not permitted`). Код сценария проверен командой `--list`.
- Не сохранено коммитом: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage && git add frontend/src/screens/ff/FfStoragePage.tsx frontend/tests-e2e/storage.spec.ts night/volna-9-recovery/cards/08-storage/DEV.md` не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-08-storage1/index.lock`: `Operation not permitted`. Commit SHA отсутствует.

## Не реализовано

Все пункты второго атома из `FEATURES.md` реализованы буквально. Находки про объяснение будущих месяцев и печатную SKU-таблицу намеренно не трогались: это первый и третий атомы соответственно.

## Находки

Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод не открывались и не использовались. Полный Playwright-прогон ограничен запретом среды на локальный порт 18000.
