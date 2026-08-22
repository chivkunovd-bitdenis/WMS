## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/apps/seller/SellerApp.tsx` — добавлен защищённый маршрут `/app/seller/reports` для селлера с `can_products`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/apps/seller/SellerLayout.tsx` — пункт «Отчёты» показывается только при праве `products`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/screens/ff/FfReportsPage.tsx` — колонка «Селлер» скрыта в seller-портале, где список селлеров пуст.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/screens.registry.json` — `S-33` дополнен фактически изменяемым экранным файлом.

## Гейты

- `python3 -m json.tool frontend/screens.registry.json` — зелёный.
- `git diff --check` — зелёный.
- `npx tsc --noEmit -p tsconfig.app.json` — не подтверждён: локальный бинарник `tsc` отсутствует, загрузка через `npx` недоступна.
- `npm run test:unit` — не подтверждён: локальный бинарник `vitest` отсутствует.
- `python3 scripts/ui/ui_guard.py` — красный из-за нарушений в несвязанных `src/App.tsx`, `src/components/WbProductPickerDialog.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx` и `src/screens/v2/SellerInboundDraftScreen.tsx`; для `FfReportsPage.tsx` guard зафиксировал улучшение (`своя-кнопка` и `своя-таблица`: 1 → 0). Базовая линия не изменялась.

## Не реализовано

- Полный Playwright-прогон не выполнен: в окружении отсутствуют локальные frontend-зависимости; маршруты и условия доступа проверены по коду.
- Остальные находки `REVIEW.md` относятся к backend/API или другим атомам и в этот screen-dev проход не входят.

## Находки

- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались.
