# Screen-dev report · 07-reporting

## Изменённые файлы

Атом `WarningNotice` уже реализован в сохранённом состоянии рабочей копии; в рамках этой проверки новые изменения в исходных файлах не потребовались.

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/States.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/index.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/States.test.tsx`

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json`: не завершился; процесс остановлен после ожидания без вывода.
- `python3 scripts/ui/ui_guard.py`: красный из-за ранее существующих нарушений в `src/App.tsx`, `src/components/WbProductPickerDialog.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx` и `src/screens/v2/SellerInboundDraftScreen.tsx`; базовая линия не изменялась. Для `FfReportsPage.tsx` зафиксировано улучшение.
- `npm run test:unit -- --run src/ui-kit/States.test.tsx`: не запустился, локальный бинарник `vitest` отсутствует (`vitest: command not found`).

## Не реализовано

Невыполненных пунктов контракта для атома `WarningNotice` нет. Реализация использует MUI `Alert severity="warning"`, общий с `ErrorNotice` отступ `mb: 2`, пробрасывает `testId`, экспортируется из `ui-kit/index.ts`, а тест проверяет `data-testid`, роль alert, warning-класс и доступный текст.

## Находки

- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались.
