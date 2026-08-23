# DEV · 08-storage · атом 2

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/tests-e2e/storage.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/cards/08-storage/DEV.md`

## Гейты

- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npx tsc --noEmit -p tsconfig.app.json`.
- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npm run test:unit -- src/screens/ff/FfStoragePage.test.ts` — 6 passed.
- Красный вне слоя атома: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage && python3 scripts/ui/ui_guard.py` сообщает новые нарушения только в `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/components/WbProductPickerDialog.tsx`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx` и `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/screens/v2/SellerInboundDraftScreen.tsx`; базовая линия не обновлялась.
- Заблокировано средой до выполнения тестов: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npx playwright test tests-e2e/storage.spec.ts --grep 'administrator keeps a previous month without a tariff after saving a later rate|S-11-TC-017 keeps the saved tariff dialog open until statement reading recovers'` не запустился, потому что webServer не получил право слушать `127.0.0.1:18000` (`Errno 1: operation not permitted`).
- Зелёный разбор целевых сценариев без webServer: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npx playwright test tests-e2e/storage.spec.ts --list --grep 'administrator keeps a previous month without a tariff after saving a later rate|S-11-TC-017 keeps the saved tariff dialog open until statement reading recovers'` — найдены ровно 2 сценария.
- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage && git diff --check`.
- Git не сохранён: `git add` не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-08-storage1/index.lock` из-за запрета песочницы (`Operation not permitted`); commit SHA отсутствует, изменения остаются в этой рабочей копии.

## Не реализовано

Нет для атома 2. Добавлен браузерный сценарий: он открывает прошлый месяц без тарифа, сохраняет ставку с датой после окончания этого месяца, ждёт успешный повторный `GET /api/operations/storage/statements`, проверяет в его ответе `tariff_configured=false` и пустой список, а после закрытия диалога — видимые «Тариф хранения ещё не задан» и «Задать тариф». Ответ POST намеренно содержит непустые строки, поэтому локальная подмена состояния вместо GET приводит к падению сценария.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, production и живой кабинет Wildberries не открывались и не использовались.
