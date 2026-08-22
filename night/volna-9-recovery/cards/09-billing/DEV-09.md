## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/layouts/AuthedAppLayout.tsx` — добавлен пункт «Расчёты» только для администратора ФФ.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/App.tsx` — добавлен защищённый маршрут `/app/ff/billing`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfBillingScreen.tsx` — создан общий каркас экрана с вкладками «Начисления» и «Счета», общими фильтрами месяца и селлера.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — НЕ ПРОЙДЕН: локальный `tsc` отсутствует, `npx` попытался скачать пакет, но сеть недоступна (`ENOTFOUND registry.npmjs.org`).
- `python3 scripts/ui/ui_guard.py` — НЕ ПРОЙДЕН: обнаружены пять новых относительно базовой линии нарушений в чужих/несвязанных файлах (`src/App.tsx`, `src/components/WbProductPickerDialog.tsx`, `src/screens/ff/FfSettingsScreen.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx`, `src/screens/v2/SellerInboundDraftScreen.tsx`). Базовая линия не изменялась.
- `npm run test:unit` — НЕ ПРОЙДЕН: в `frontend` отсутствует команда `vitest` (`vitest: command not found`).

## Не реализовано

- Таблицы начислений и счетов, их API, детализация и печать не реализованы: текущий атомарный кусок FEATURES.md ограничен маршрутом, доступом и общим каркасом.
- `screens.registry.json` не изменялся, поскольку он не входит в разрешённый список файлов карточки.
- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод не читались и не затрагивались.
