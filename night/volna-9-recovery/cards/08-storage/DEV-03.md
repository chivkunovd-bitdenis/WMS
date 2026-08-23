# DEV · 08-storage · атом 3

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/tests-e2e/storage.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/tests/cases/S-11.md`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/cards/08-storage/CASES.md`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/cards/08-storage/DEV.md`

`S-11-TC-021` — новый постоянный номер проверки прошлой московской даты в диалоге тарифа.
`S-11-TC-018` сохранён только за отрицательным восстановленным остатком, запретом фиксации
и отсутствием частичного ledger-начисления.

## Гейты

- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npx tsc --noEmit -p tsconfig.app.json`.
- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npm run test:unit -- src/screens/ff/FfStoragePage.test.ts` — 6 passed.
- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage && git diff --check`.
- Целевые Playwright-сценарии найдены: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npx playwright test tests-e2e/storage.spec.ts --list --grep 'S-11-TC-002 blocks a rate that rounds to zero before saving|S-11-TC-021 blocks Moscow-past start dates with a visible explanation|administrator keeps a previous month without a tariff after saving a later rate'` — 3 теста.
- Запуск тех же трёх Playwright-сценариев заблокирован средой до выполнения тестов: webServer не получил право слушать `127.0.0.1:18000` (`Errno 1: operation not permitted`).
- Красный вне слоя атома: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage && python3 scripts/ui/ui_guard.py` сообщает новые нарушения только в `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/components/WbProductPickerDialog.tsx`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx` и `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Базовая линия не обновлялась.
- Git не сохранён: `git add` не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-08-storage1/index.lock` из-за запрета песочницы (`Operation not permitted`); commit SHA отсутствует, изменения остаются в этой рабочей копии.

## Не реализовано

Нет. Все пункты атома реализованы буквально. Ранее отмеченные ревьюером живые сценарии
минимальной ставки и повторного чтения прошлого месяца уже присутствуют в `storage.spec.ts`;
их фикстуры открывают пустое состояние и они включены в целевой список регрессии.

## Находки

Секреты, ключи, токены, `.env`, персональные данные и кабинеты учётных данных не открывались
и не использовались.
