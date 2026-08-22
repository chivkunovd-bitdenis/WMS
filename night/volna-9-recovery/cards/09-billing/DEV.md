# 09-billing · screen-dev · атом 5

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/tests-e2e/billing-seller-profile.spec.ts`

Экран `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/v2/SellersScreen.tsx` не потребовал изменения: обязательный негативный путь реализован тестом на уже существующем UI.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — не выполнен: в checkout отсутствует `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/node_modules/.bin/tsc`; запуск через `npx` завис без вывода и был остановлен.
- `python3 scripts/ui/ui_guard.py` — красный из-за уже существующих нарушений вне затронутых файлов: `src/App.tsx`, `src/components/WbProductPickerDialog.tsx`, `src/screens/ff/FfSettingsScreen.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx`, `src/screens/v2/SellerInboundDraftScreen.tsx`.
- `npm run test:unit` — не выполнен: `vitest: command not found`.
- `git diff --check` — зелёный.

## Не реализовано

В пределах разрешённых файлов и данного атома пунктов контракта, которые не удалось реализовать буквально, нет. `S-31-TC-009` больше не пропускается: тест сохраняет корректные реквизиты, отправляет неверный ИНН, проверяет понятную ошибку и подтверждает, что сохранённые юридическое наименование и КПП не затёрты.
