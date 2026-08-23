# 08-storage · screen-dev · атом 3

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/screens/ff/FfStoragePage.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/tests-e2e/storage.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/cards/08-storage/DEV.md`

В A4-предпросмотре у всех семи колонок заданы явные ширины. Между «Литро-дни» и «Сумма, ₽» добавлена числовая правая колонка «Ставка, ₽/л·день», показывающая `rate_snapshot`. E2E-сценарий открывает предпросмотр кнопкой печати у зафиксированной строки, проверяет полный набор заголовков, ширины, длинный артикул, снимок ставки и итог.

## Гейты

- ЗЕЛЁНЫЙ: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npx tsc --noEmit -p tsconfig.app.json`
- ЗЕЛЁНЫЙ: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npm run test:unit -- src/screens/ff/FfStoragePage.test.ts` — 1 файл, 6 тестов.
- КРАСНЫЙ вне границ S-11: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage && python3 scripts/ui/ui_guard.py`. Сторож сообщил о новых экран-монолитах только в `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/components/WbProductPickerDialog.tsx`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx` и `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Эти файлы не относятся к карточке и не менялись; дизайн-вердикт фиксирует те же три посторонние находки.
- НЕ ЗАПУЩЕНЫ: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npx playwright test tests-e2e/storage.spec.ts --grep 'S-11-TC-008|S-11-TC-009|fixed storage print preview shows the rate snapshot'`. Playwright остановился до выполнения тестов: webServer не смог привязать `127.0.0.1:18000` (`operation not permitted`).
- НЕ СОХРАНЕНО КОММИТОМ: `git add frontend/src/screens/ff/FfStoragePage.tsx frontend/tests-e2e/storage.spec.ts night/volna-9-recovery/cards/08-storage/DEV.md` не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-08-storage1/index.lock` (`Operation not permitted`). SHA отсутствует.

## Не реализовано

Нет. Все пункты атома 3 реализованы буквально. Проверка E2E в этой среде не выполнена из-за запрета локального bind, а не из-за продуктового расхождения.

## Находки

Секреты, ключи, токены, `.env` и кабинеты учётных данных не открывались и не использовались.
