## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/screens/ff/FfReportsPage.tsx — отмена устаревших табличных запросов, стабильные test id для пагинации.
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/tests-e2e/ff-reports.spec.ts — обновлены проверки под текущий DataTable, группировки, пагинации, неизменности сводки и CSV.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — красный: локальный пакет `tsc` отсутствует; `npx` попытался скачать его, но сеть недоступна (`ENOTFOUND registry.npmjs.org`).
- `python3 scripts/ui/ui_guard.py` — красный из-за четырёх новых нарушений вне файлов этой карточки: `src/App.tsx`, `src/components/WbProductPickerDialog.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx`, `src/screens/v2/SellerInboundDraftScreen.tsx`. Для `FfReportsPage.tsx` guard зафиксировал улучшение: своя кнопка и своя таблица устранены.
- `npm run test:unit` — красный: `vitest: command not found`.

## Не реализовано

- Backend-находки из ревью (дневная агрегация, складская область, transfer integrity и свежесть данных) не относятся к роли `screen-dev` и к атомарной фиче 11; backend-файлы не изменялись.
- Живой Playwright-прогон невозможен в текущем окружении без установленных frontend-зависимостей; сценарий обновлён статически под текущие UI-селекторы.
