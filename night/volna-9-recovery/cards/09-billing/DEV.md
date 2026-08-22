# 09-billing · screen-dev · атом 5

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/v2/SellersScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/tests-e2e/billing-seller-profile.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/cards/09-billing/DEV.md`

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — не выполнен: в `frontend/node_modules/.bin` отсутствует `tsc`; `npx` не завершился в доступное время.
- `python3 scripts/ui/ui_guard.py` — красный из-за пяти существующих нарушений в соседних файлах: `src/App.tsx`, `src/components/WbProductPickerDialog.tsx`, `src/screens/ff/FfSettingsScreen.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx`, `src/screens/v2/SellerInboundDraftScreen.tsx`. Изменённый `SellersScreen.tsx` новым нарушением не отмечен.
- `npm run test:unit` — не выполнен: `vitest: command not found`.
- `git diff --check` — зелёный.

## Не реализовано

- Пунктов контракта в пределах атома 5, которые не удалось реализовать буквально, нет. Исправлены загрузка сохранённого профиля при раскрытии блока и негативный сценарий `S-31-TC-009`: после ошибочного ИНН success скрывается, а повторное открытие подтверждает ранее сохранённый ИНН.
