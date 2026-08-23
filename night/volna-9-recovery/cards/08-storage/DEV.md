# 08-storage · screen-dev · атом 1 · переделка по REVIEW.md

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/ui-kit/DataTable.tsx` — у канонической таблицы включена фиксированная раскладка; ширина задана и заголовкам, и ячейкам, а длинный текст не может расширить свою колонку.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/tests-e2e/storage.spec.ts` — сценарии истории габаритов и A4-предпросмотра теперь проверяют фактические границы заголовков и ячеек с длинной непрерывной строкой, а не только HTML-атрибуты ширины. Печатный сценарий связан с постоянным `S-11-TC-009`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/cards/08-storage/DEV.md` — артефакт выполнения.

## Гейты

- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npx tsc --noEmit -p tsconfig.app.json`.
- Красный из-за исчерпанного места на диске: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npm run test:unit -- src/screens/ff/FfStoragePage.test.ts`. Vitest не смог создать временный файл в `frontend/node_modules/.vite-temp`: `ENOSPC: no space left on device`.
- Красный вне границ атома: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage && python3 scripts/ui/ui_guard.py`. Сторож сообщает новые отступления только в `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/components/WbProductPickerDialog.tsx`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx` и `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/screens/v2/SellerInboundDraftScreen.tsx`; эти файлы не принадлежат атому и не менялись. Базовая линия не обновлялась.
- Красный из-за исчерпанного места на диске: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npx playwright test tests-e2e/storage.spec.ts --grep 'S-11-TC-007 keeps history columns|S-11-TC-008 fixes|S-11-TC-009 opens a repeat|S-11-TC-009 keeps rate and amount' --list`. Playwright не смог создать transform-cache в системном временном каталоге: `ENOSPC: no space left on device`.
- Не сохранено коммитом: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage && git add frontend/src/ui-kit/DataTable.tsx frontend/tests-e2e/storage.spec.ts night/volna-9-recovery/cards/08-storage/DEV.md && git commit -m 'fix(storage): keep fixed table columns aligned'` не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-08-storage1/index.lock`: `Operation not permitted`. Commit SHA отсутствует.

## Не реализовано

Нет. Для атома 1 выполнена фиксированная раскладка `DataTable`, а сценарии истории габаритов и A4-предпросмотра проверяют геометрию колонок при длинных непрерывных значениях. Находка `REVIEW.md` о каталоге блокировок относится к отдельному атому ограничения будущих месяцев и не менялась. Также не менялся сиротский `TC-NEW-STORAGE-REVIEW-01` того же отдельного атома; печатный сценарий этого атома переведён на `S-11-TC-009`.

## Находки

Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой прод и живой кабинет Wildberries не открывались и не использовались. Локальные unit- и E2E-проверки остановлены только недостатком свободного места на файловой системе.
