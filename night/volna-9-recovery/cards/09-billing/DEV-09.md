## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/App.tsx — передан Bearer-токен в экран расчётов.
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfBillingScreen.tsx — запросы начислений, счетов и отмены счета авторизованы; исправлена подпись пустого состояния.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — не завершён: в checkout отсутствует локальный `tsc`, а `npx` ожидал установку пакета и был остановлен без сетевой установки.
- `python3 scripts/ui/ui_guard.py` — красный из-за пяти нарушений, не созданных этой правкой: `src/App.tsx`, `src/components/WbProductPickerDialog.tsx`, `src/screens/ff/FfSettingsScreen.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx`, `src/screens/v2/SellerInboundDraftScreen.tsx`.
- `npm run test:unit` — не запущен: `vitest: command not found`.
- `git diff --check` — зелёный.

## Не реализовано

- Полный живой API-контракт `/billing/ledger` и `/billing/invoices` не расширялся: это backend-атомы, не входящие в разрешённые файлы этого экрана.
- Остальные находки ревью относятся к backend, настройкам тарифов, seller-профилю или e2e-тестам других атомов и здесь не исправлялись.

