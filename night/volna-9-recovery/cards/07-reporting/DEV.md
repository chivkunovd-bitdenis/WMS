# DEV · 07-reporting · атом 9

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/App.tsx` — обе зарегистрированные точки маршрутизации отчёта передают экрану доступные склады, поэтому фильтр склада получает фактический список и в FF-, и в совместимом seller-маршруте.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/apps/seller/SellerApp.tsx` — основной seller-маршрут `/reports` передаёт экрану доступные склады; доступ и отсутствие селектора чужого селлера сохранены.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/night/volna-9-recovery/cards/07-reporting/DEV.md` — отчёт этого атома.

## Гейты

- В `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting`: `git diff --check` — зелёный.
- В `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend`: `npx tsc --noEmit -p tsconfig.app.json` — не запущен: локального `tsc` нет, а `npx` не смог скачать пакет из-за недоступности `registry.npmjs.org` (`ENOTFOUND`).
- В `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting`: `python3 scripts/ui/ui_guard.py` — красный только по существующим отступлениям вне файлов атома: `frontend/src/App.tsx`, `frontend/src/components/WbProductPickerDialog.tsx`, `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`, `frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Для `frontend/src/screens/ff/FfReportsPage.tsx` guard отмечает улучшение; базовая линия не менялась.
- В `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend`: `npm run test:unit` — не запущен: `vitest: command not found`.
- В `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend`: `npx playwright test tests-e2e/ff-reports.spec.ts` — не запущен: локального Playwright нет, загрузка пакета невозможна из-за недоступности `registry.npmjs.org` (`ENOTFOUND`).

## Не реализовано

- В рамках атома 9 не менялись состояния, даты, API, CSV и таблица отчёта: это соседние атомы и отдельные находки `REVIEW.md`.
- Автоматические проверки не подтверждены из-за отсутствующих frontend-зависимостей и закрытой сети. Ручная проверка кода подтверждает, что маршруты остаются защищены прежними условиями `inventory` для ФФ и `products` для селлера, а seller-экран получает пустой список селлеров.

## Находки

- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались.
