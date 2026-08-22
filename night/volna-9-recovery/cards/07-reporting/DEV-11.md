## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/screens/ff/FfReportsPage.tsx`

Добавлены серверная группировка «По товарам / По операциям», постраничная загрузка по 50 строк, строка диапазона, переходы между страницами и скачивание серверного CSV. Переключение таблицы не перезагружает верхнюю сводку. Файл `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/tests-e2e/seller-reports.spec.ts` отсутствует в рабочей копии, поэтому не изменялся.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` (из `frontend/`) — зелёный.
- `python3 scripts/ui/ui_guard.py` (из корня) — красный: guard сообщил новые нарушения в чужих файлах `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/components/WbProductPickerDialog.tsx`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Разрешённые файлы карточки не расширял.
- `npm run test:unit` (из `frontend/`) — не запустился: `vitest: command not found`.

## Не реализовано

- E2E-проверки фичи 11 в `ff-reports.spec.ts` и `seller-reports.spec.ts` не добавлялись: роль ограничена экраном, а seller spec отсутствует; существующий FF spec не входит в текущую разрешённую карту файлов реестра.
