# Фича 1

# DEV · 08-storage · календарно устойчивый прошлый месяц

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/tests-e2e/storage.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/cards/08-storage/DEV.md`

В `storage.spec.ts` проверка прошлого месяца теперь вычисляет предшествующий календарный месяц в часовом поясе `Europe/Moscow`; январь отдельно проверен как переход к декабрю предыдущего года. Целевой сценарий по-прежнему проверяет позднюю ставку, единственный повторный GET и видимое пустое состояние.

## Гейты

- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npx tsc --noEmit -p tsconfig.app.json`.
- Красный вне этого атома: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage && python3 scripts/ui/ui_guard.py`. Новые нарушения указаны только в не затронутых атомом файлах: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/components/WbProductPickerDialog.tsx`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Базовая линия не изменялась.
- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npm run test:unit -- src/screens/ff/FfStoragePage.test.ts` — 1 файл, 6 тестов passed.
- Не выполнен средой до запуска тестов: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npx playwright test tests-e2e/storage.spec.ts --grep 'S-11-TC-002 blocks a rate that rounds to zero|S-11-TC-021 blocks Moscow-past start dates|TC-NEW-STORAGE-REFRESH-01|administrator keeps a previous month without a tariff'`. Playwright webServer не смог привязаться к `127.0.0.1:18000`: `operation not permitted`.
- Зелёный разбор набора без webServer: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npx playwright test tests-e2e/storage.spec.ts --list --grep 'S-11-TC-002 blocks a rate that rounds to zero|S-11-TC-021 blocks Moscow-past start dates|TC-NEW-STORAGE-REFRESH-01|administrator keeps a previous month without a tariff'` — найдены 4 целевых теста.
- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage && git diff --check`.
- Не сохранено коммитом: `git add` не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-08-storage1/index.lock` из-за запрета песочницы (`Operation not permitted`). Commit SHA отсутствует.

## Не реализовано

Нет. Единственный пункт повторного вердикта реализован буквально. Целевой Playwright-сценарий невозможно выполнить в этой песочнице из-за запрета на локальный порт, а не из-за результата сценария.

## Находки

Секреты, ключи, токены, `.env` и кабинеты учётных данных не открывались и не использовались.
