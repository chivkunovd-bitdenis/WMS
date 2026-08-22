## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/screens/ff/FfReportsPage.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/night/volna-9-recovery/cards/07-reporting/DEV.md`

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — не подтверждён: локальный `tsc` отсутствует, `npx` завис на разрешении инструмента и был остановлен без вывода ошибки.
- `python3 scripts/ui/ui_guard.py` — красный из-за четырёх ранее существовавших нарушений в чужих файлах (`src/App.tsx`, `src/components/WbProductPickerDialog.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx`, `src/screens/v2/SellerInboundDraftScreen.tsx`). Для `FfReportsPage.tsx` guard показал улучшение: собственная кнопка `1 → 0`, собственная таблица `1 → 0`. Baseline не изменялся.
- `npm run test:unit` — не запущен: в окружении отсутствует команда `vitest` (`vitest: command not found`).

## Не реализовано

- Прошлая линия графика не подключена буквально: текущий API-ответ экрана не содержит дневную серию предыдущего периода, а backend-файлы находятся вне разрешённых файлов этого screen-dev атома.
- Backend-находки ревьюера (seller/warehouse/search scope, схема ответа, CSV, миграция, API-тесты), seller-маршрут и исправление `screens.registry.json` не менялись: они находятся за пределами разрешённых файлов этого атома.
- Полная проверка Playwright не выполнялась: задача ограничена экранным исправлением, а обязательные локальные зависимости для unit/TypeScript отсутствуют.
