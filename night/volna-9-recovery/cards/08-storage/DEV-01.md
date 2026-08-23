# DEV · 08-storage · атом 1

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/screens/ff/FfStoragePage.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/tests-e2e/storage.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/docs/blockers/S-11.md`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/cards/08-storage/DEV.md`

## Гейты

- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npx tsc --noEmit -p tsconfig.app.json`.
- Красный вне атома: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage && python3 scripts/ui/ui_guard.py` сообщил новые нарушения в `src/components/WbProductPickerDialog.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx` и `src/screens/v2/SellerInboundDraftScreen.tsx`. Эти файлы не входят в S-11; базовая линия не менялась.
- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npm run test:unit -- src/screens/ff/FfStoragePage.test.ts` — 7 passed.
- Блокировка среды: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npm run test:e2e -- tests-e2e/storage.spec.ts --grep 'S-11-TC-002 blocks a rate that rounds to zero before saving'` не стартовал, потому что песочница запретила API слушать `127.0.0.1:18000` (`Errno 1: operation not permitted`).
- Зелёный разбор целевого e2e без запуска web server: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npx playwright test tests-e2e/storage.spec.ts --grep 'S-11-TC-002 blocks a rate that rounds to zero before saving' --list` — найден 1 тест.
- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage && git diff --check`.
- Git не сохранён: `git add` не может создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-08-storage1/index.lock` из-за запрета песочницы (`Operation not permitted`), поэтому commit SHA отсутствует. Изменения лежат только в этой рабочей копии.

## Не реализовано

Нет. Атом 1 реализован буквально: общая и индивидуальная ставки `0,001` блокируются до POST с объяснением о минимально сохраняемых `0,01 ₽/л·день`; значение `0,005` остаётся допустимым, так как сервер сохраняет его как `0,01` по `ROUND_HALF_UP`. Находки ревью о повторном чтении после POST и экранных проверках других правил относятся к атомам 2–4 из `FEATURES.md` и намеренно не смешивались с этим атомом.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, production и живой кабинет Wildberries не открывались и не использовались.
