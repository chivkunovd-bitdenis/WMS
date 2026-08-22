# DEV · 06-picking-list-order · атом 5 · rework DESIGN-REVIEW

Роль: `screen-dev`.

Исправлены все три находки `DESIGN-REVIEW.md`, относящиеся к слою этого атома: действия в «Листе подбора» объединены через `ActionGroup`, а в предпросмотре закрытие и печать переведены на `SecondaryAction` и `PrintAction`. Логика серверного порядка, полного набора ID и пар `WB → WMS № K` не изменялась.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/screens/v2/FfFbsPickList.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/screens/v2/FbsPrintPreviewDialog.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/tests-e2e/ff-fbs-supply.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/night/volna-9-recovery/cards/06-picking-list-order/DEV.md`

## Гейты

- Зелёный — `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend && npx tsc --noEmit -p tsconfig.app.json` (exit 0).
- Красный вне границы атома — `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order && python3 scripts/ui/ui_guard.py` (exit 1). Новые нарушения: `src/components/WbProductPickerDialog.tsx: экран-монолит 0 → 646` и `src/screens/v2/SellerInboundDraftScreen.tsx: экран-монолит 1111 → 1169`. Оба файла не входят в разрешённую границу экрана и уже перечислены в `DESIGN-REVIEW.md`; baseline не обновлялся. Для файлов атома guard сообщил только улучшения: у `FbsPrintPreviewDialog.tsx` число собственных кнопок уменьшилось `4 → 2`, у `FfFbsPickList.tsx` собственные кнопки уменьшились `2 → 0`.
- Зелёный — `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend && npm run test:unit -- src/screens/v2/FbsPrintPreviewDialog.test.ts src/screens/v2/FfFbsPickList.test.ts` (2 файла, 11 тестов, exit 0).
- Не стартовал из-за ограничения среды — `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend && npx playwright test tests-e2e/ff-fbs-supply.spec.ts --grep 'S-03-TC-004 S-03-TC-005'`. WebServer получил `operation not permitted` при попытке слушать `127.0.0.1:18000`; продуктовый сценарий до браузера не дошёл.
- Зелёный — `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order && git diff --check` (exit 0).
- Не выполнено из-за прав файловой системы — `git add frontend/src/screens/v2/FfFbsPickList.tsx frontend/src/screens/v2/FbsPrintPreviewDialog.tsx frontend/tests-e2e/ff-fbs-supply.spec.ts night/volna-9-recovery/cards/06-picking-list-order/DEV.md && git commit -m "fix(fbs): align picking print actions with ui kit"`. Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-06-picking-list-order/index.lock`: `Operation not permitted`. Commit SHA отсутствует.

## Не реализовано

Все три находки `DESIGN-REVIEW.md` реализованы буквально. Непроверенным остался браузерный прогон `S-03-TC-004/S-03-TC-005`: локальный webServer запрещён средой выполнения. Два чужих нарушения `ui_guard.py` не исправлялись, потому что их файлы находятся вне границы этого атома и роли `screen-dev`. Изменения локально записаны, но не сохранены Git-коммитом из-за запрета записи в metadata-каталог worktree.

## Находки

Новых находок по данным, персональным данным или секретам нет.
