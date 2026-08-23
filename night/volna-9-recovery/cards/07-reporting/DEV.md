# Фича 1

# DEV · 07-reporting · атом 1

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/screens/ff/FfReportsPage.tsx` — пользовательское предупреждение о восстановленных исторических записях теперь говорит: «В отчёте есть исторические записи, восстановленные по доступным связям: N».
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/tests-e2e/ff-reports.spec.ts` — сценарий проверяет точный текст для `count = 3`, отсутствие «legacy-данные» и сохраняет отдельную проверку предупреждения Wildberries.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/night/volna-9-recovery/cards/07-reporting/DEV.md` — отчёт шага.

## Гейты

- ЗЕЛЁНЫЙ: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npx tsc --noEmit -p tsconfig.app.json`.
- КРАСНЫЙ вне границы атома: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting && python3 scripts/ui/ui_guard.py`. Скрипт сообщил о новых монолитах в `frontend/src/App.tsx`, `frontend/src/components/WbProductPickerDialog.tsx`, `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx` и `frontend/src/screens/v2/SellerInboundDraftScreen.tsx`; эти файлы не входят в разрешённую границу атома. Для `frontend/src/screens/ff/FfReportsPage.tsx` скрипт сообщил только улучшения: свои кнопка и таблица устранены.
- ЗЕЛЁНЫЙ: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npm run test:unit -- src/screens/ff/FfReportsPage.test.tsx` — 1 файл, 1 тест.
- ЗАПУСК НЕ СОСТОЯЛСЯ из-за изоляции среды: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npx playwright test tests-e2e/ff-reports.spec.ts --grep 'FF report upper slice updates atomically and keeps table on overview retry'`. Playwright не смог запустить свой локальный webServer: `bind 127.0.0.1:18000: operation not permitted`; до выполнения сценария браузер не дошёл.
- ЗЕЛЁНЫЙ: `git diff --check`.

## Не реализовано

Нет. Техническая проверка e2e не выполнилась только потому, что среда запретила привязку локального порта; код и сценарий не менялись за пределами атома.

## Находки

Нет.
