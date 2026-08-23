## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfSettingsScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfSettingsScreen.test.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/cards/09-billing/DEV.md`

Сохранение реквизитов ФФ и ставки теперь очищает прежнее уведомление об успехе до запроса. Сетевой отказ возвращается в `ErrorNotice`, а `finally` снимает состояние загрузки, поэтому кнопку можно нажать повторно после исправления данных. Целевые тесты отклоняют оба запроса и подтверждают ошибочный, а не успешный результат.

## Гейты

- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npx tsc --noEmit -p tsconfig.app.json`.
- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend && npm run test:unit -- src/screens/ff/FfSettingsScreen.test.ts` — 1 файл, 6 тестов passed. Выполнены только тесты этого атома и связанные регрессии атома 17.
- Красный вне границ атома: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing && python3 scripts/ui/ui_guard.py`. Новые нарушения только в неразрешённых этому атому файлах: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/components/WbProductPickerDialog.tsx`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Базовая линия не изменялась; сам `FfSettingsScreen.tsx` улучшен с 701 до 698 строк.

## Не реализовано

Нет. Атом 18 реализован в указанных границах. Находки `REVIEW.md` о навигации на тарифы и допустимой единице тарифа относятся к другим атомам и в эту доработку не включались.

## Находки

Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод не читались и не изменялись.

Git-сохранение не выполнено: команда `git add` не смогла создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-09-billing1/index.lock` из-за `Operation not permitted`. Изменения остаются в этой рабочей копии без восстановимого commit SHA.
