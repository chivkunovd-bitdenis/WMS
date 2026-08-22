# Screen Dev · 07-reporting · WarningNotice

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/States.tsx` — добавлен `WarningNotice` на базе MUI `Alert` с `severity="warning"` и теми же отступами, что у `ErrorNotice`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/index.ts` — экспортирован `WarningNotice`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/States.test.tsx` — добавлен unit-тест доступного текста, `testId` и warning-класса MUI Alert.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — GREEN, exit 0.
- `python3 scripts/ui/ui_guard.py` — RED из-за трёх нарушений в несвязанных файлах: `src/components/WbProductPickerDialog.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx`, `src/screens/v2/SellerInboundDraftScreen.tsx`. Базовая линия не обновлялась.
- `npm run test:unit` — НЕ ЗАПУЩЕН: в рабочей копии отсутствует локальный бинарник `vitest` (`vitest: command not found`, exit 127).

## Не реализовано

- Пункты экрана отчётности не реализовывались: эта карточка ограничена атомом `WarningNotice`.
- Проверка unit-теста фактическим запуском не выполнена из-за отсутствия установленного `vitest`; сам тест добавлен в разрешённый файл.

## Находки

- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались.
- В рабочей копии обнаружены несвязанные изменения `night/volna-9-recovery/JOURNAL.md`; файл не изменялся.
