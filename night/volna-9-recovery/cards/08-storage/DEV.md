# Фича 1

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

# Фича 2

# 08-storage · DEV

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/docs/blockers/S-11.md`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/cards/08-storage/DEV.md`

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npx tsc --noEmit -p tsconfig.app.json` — зелёный, код выхода `0`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage && python3 scripts/ui/ui_guard.py` — красный, код выхода `1`: новые относительно его базовой линии нарушения в не относящихся к атому файлах `frontend/src/components/WbProductPickerDialog.tsx`, `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx` и `frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Эти файлы не изменялись и запрещены границами данного атома; базовая линия не обновлялась.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npm run test:unit -- src/screens/ff/FfStoragePage.test.ts` — зелёный, `6 passed`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage && pytest backend/tests/test_storage_measurement_service.py -k test_storage_api_rejects_future_month` — зелёный, `1 passed, 10 deselected`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npm run test:e2e -- storage.spec.ts --grep "staff sees why future storage months are unavailable"` — не запустился: среда запретила Playwright webServer слушать `127.0.0.1:18000` (`Errno 1: operation not permitted`) до выполнения сценария.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage && git diff --check` — зелёный.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage && git add docs/blockers/S-11.md night/volna-9-recovery/cards/08-storage/DEV.md && git commit -m "docs(storage): correct future month blocker"` — не выполнен: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-08-storage1/index.lock` (`Operation not permitted`), поэтому SHA отсутствует.

## Не реализовано

- Нет. В пределах этого атома поведение экрана и API не менялось: карточка блокировки приведена в соответствие уже действующему контракту, экранному ограничению и независимой серверной валидации.

## Находки

- Секции «Будущий расчётный месяц» и «Разошлись слои» обновлены: ложное утверждение о доступном будущем месяце и отсутствии объяснения удалено.

# Фича 3

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
