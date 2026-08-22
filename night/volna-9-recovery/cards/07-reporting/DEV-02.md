# DEV · 07-reporting · атом 2

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/screens/ff/FfReportsPage.tsx` — проверена реализация атома: пагинация использует `SecondaryAction`, то есть MUI `Button` с `variant="outlined"`; сохранены `data-testid` и `disabledReason`. Изменение уже содержится в commit `d610b961165a47a3c8706b59c5c52f26ea825b84`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/night/volna-9-recovery/cards/07-reporting/DEV.md` — артефакт данного шага.

## Гейты

- ЗЕЛЁНЫЙ: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npx tsc --noEmit -p tsconfig.app.json`.
- КРАСНЫЙ вне границ атома: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting && python3 scripts/ui/ui_guard.py`. Новые нарушения только в `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/App.tsx`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/components/WbProductPickerDialog.tsx`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx` и `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/screens/v2/SellerInboundDraftScreen.tsx`; их менять запрещено границей S-33. Для `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/screens/ff/FfReportsPage.tsx` guard сообщает улучшение: «своя-кнопка 1 → 0».
- ЗЕЛЁНЫЙ, адресный запуск: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npm run test:unit -- --passWithNoTests src/screens/ff/FfReportsPage.test.tsx`. У экрана нет unit-файла, поэтому Vitest завершился с `No test files found, exiting with code 0`; посторонние unit-тесты не запускались согласно правилу атомарной проверки.
- КРАСНЫЙ по ограничению sandbox: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npx playwright test tests-e2e/ff-reports.spec.ts --grep "FF reports: section opens and shows movement summary for a product with intake" --workers=1`. Playwright не смог запустить webServer: `127.0.0.1:18000: operation not permitted`.

## Не реализовано

- Нет. Атом 2 уже реализован буквально: «Скачать CSV» остаётся `PrimaryAction`, а «Назад» и «Вперёд» — outlined `SecondaryAction` с неизменными `data-testid` и подсказками недоступности.
