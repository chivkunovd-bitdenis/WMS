# DEV · 06-picking-list-order · атом 6 · rework DESIGN-REVIEW

Роль: `screen-dev`.

Все три находки `DESIGN-REVIEW.md` в текущей ветке реализованы буквально и сохранены в коммите `b6d7142dc2f86b5bf813a1b5b58cbe79edcd600b`: действия листа подбора объединены через `ActionGroup`, а в предпросмотре ленты закрытие и печать переведены на `SecondaryAction` и `PrintAction` с типом `стикеры заказов`. Канонические диапазоны, локальные отметки и полный состав печати не изменялись.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/screens/v2/FfFbsPickList.tsx` — исправление R-32 находится в проверенном коммите `b6d7142dc2f86b5bf813a1b5b58cbe79edcd600b`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/screens/v2/FbsPrintPreviewDialog.tsx` — исправления R-31 и R-33 находятся в проверенном коммите `b6d7142dc2f86b5bf813a1b5b58cbe79edcd600b`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/tests-e2e/ff-fbs-supply.spec.ts` — целевые сценарии атома и связанная проверка действия печати находятся в том же коммите.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/night/volna-9-recovery/cards/06-picking-list-order/DEV.md` — создан заново для текущего прохода атома 6.

## Гейты

- Зелёный — `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend && npx tsc --noEmit -p tsconfig.app.json` (exit 0).
- Красный только вне границы атома — `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order && python3 scripts/ui/ui_guard.py` (exit 1). Guard сообщил `src/components/WbProductPickerDialog.tsx: экран-монолит 0 → 646` и `src/screens/v2/SellerInboundDraftScreen.tsx: экран-монолит 1111 → 1169`; оба файла не входят в `files` экрана `S-03` и прямо отмечены в `DESIGN-REVIEW.md` как нарушения вне карточки. Baseline не обновлялся. Для файлов атома guard сообщил только улучшения: `FbsPrintPreviewDialog.tsx` — собственные кнопки `4 → 2`; `FfFbsPickList.tsx` — собственный чип `1 → 0`, собственные кнопки `2 → 0`, собственная таблица `1 → 0`.
- Зелёный — `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend && npm run test:unit -- src/screens/v2/FfFbsPickList.test.ts` (1 файл, 5 тестов, exit 0).
- Зелёный — `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend && npm run test:unit -- src/screens/v2/FbsPrintPreviewDialog.test.ts src/screens/v2/FfFbsPickList.test.ts` (2 файла, 11 тестов, exit 0).
- Не стартовал из-за ограничения среды — `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend && npx playwright test tests-e2e/ff-fbs-supply.spec.ts --grep 'S-03-TC-00(1|2|3|6|7)'`. Playwright webServer получил `[Errno 1] operation not permitted` при попытке слушать `127.0.0.1:18000`; сценарии до браузера не дошли, тестовых падений не зафиксировано.

## Не реализовано

Пунктов контракта или находок `DESIGN-REVIEW.md`, которые не удалось реализовать буквально, нет. Непроверенными в браузере остались `S-03-TC-001`, `S-03-TC-002`, `S-03-TC-003`, `S-03-TC-006` и `S-03-TC-007`, потому что песочница запретила запуск локального webServer. Два чужих нарушения `ui_guard.py` не исправлялись: их файлы находятся вне границы экрана `S-03` и роли `screen-dev`.

## Находки

Новых находок по данным, персональным данным или секретам нет.
