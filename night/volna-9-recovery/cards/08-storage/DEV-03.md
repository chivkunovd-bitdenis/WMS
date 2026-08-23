# 08-storage · screen-dev · атом 3

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/tests-e2e/storage.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/cards/08-storage/CASES.md`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/tests/cases/S-11.md`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/cards/08-storage/DEV.md`

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npx tsc --noEmit -p tsconfig.app.json` — зелёный.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage && python3 scripts/ui/ui_guard.py` — красный из-за уже имеющихся нарушений вне этого атома: `frontend/src/components/WbProductPickerDialog.tsx` (экран-монолит 0 → 646), `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx` (2493 → 2498), `frontend/src/screens/v2/SellerInboundDraftScreen.tsx` (1111 → 1169). Базовая линия не менялась.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npm run test:unit -- src/screens/ff/FfStoragePage.test.ts` — зелёный: 1 файл, 6 тестов.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npx playwright test tests-e2e/storage.spec.ts --grep 'S-11-TC-022 staff sees why future storage months are unavailable|S-11-TC-009 keeps rate and amount visible beside a long seller article in print preview'` — не дошёл до сценариев: sandbox запретил API webServer слушать `127.0.0.1:18000` (`operation not permitted`). Боевой прод и внешние кабинеты не затрагивались.
- Проверка трассировки комментариев в `storage.spec.ts` — зелёная: все `S-11-TC-*` из комментариев назначены в `CASES.md`, документированы в `tests/cases/S-11.md`; `TC-NEW-STORAGE-REVIEW-01` и `TC-NEW-STORAGE-REVIEW-03` не найдены.
- `git diff --check` — зелёный.
- `git add -- frontend/tests-e2e/storage.spec.ts night/volna-9-recovery/cards/08-storage/CASES.md tests/cases/S-11.md night/volna-9-recovery/cards/08-storage/DEV.md && git commit -m 'test(storage): link e2e checks to S-11 cases'` — не выполнен: Git не может создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-08-storage1/index.lock` (`Operation not permitted`). Изменения остаются незакоммиченными.

## Не реализовано

Все пункты атома 3 реализованы буквально. Два требуемых Playwright-сценария не выполнены только из-за запрета среды на локальный порт; код тестов и их постоянная трассировка проверены статически.

## Находки

Секреты, ключи, токены, `.env`, персональные данные и кабинеты учётных данных не открывались и не использовались.
