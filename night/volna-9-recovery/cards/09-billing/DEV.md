## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfBillingScreen.tsx` — очищает текущие начисления и счета перед новым запросом, чтобы ошибка не показывала старые данные как актуальные.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/tests-e2e/billing-ledger.spec.ts` — усиливает `S-31-TC-004`, `S-31-TC-005`, `S-31-TC-012` и добавляет проверку очистки устаревшей строки при ошибке обновления.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/cards/09-billing/DEV.md` — этот отчёт.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — не подтверждён: в checkout отсутствует локальный `tsc`, а `npx` не завершил выполнение в доступное время.
- `python3 scripts/ui/ui_guard.py` — FAIL из-за пяти новых/зафиксированных нарушений в чужих файлах: `src/App.tsx`, `src/components/WbProductPickerDialog.tsx`, `src/screens/ff/FfSettingsScreen.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx`, `src/screens/v2/SellerInboundDraftScreen.tsx`. Нарушений в изменённом billing-экране нет; базовую линию не обновлял.
- `npm run test:unit` — FAIL: `vitest: command not found`.
- `git diff --check` — PASS.

## Не реализовано

- GET-ручки `/api/billing/ledger` и `/api/billing/invoices` отсутствуют в `backend/app/api/billing.py`. Добавление backend-файла запрещено границами этого экранного атома; E2E сохраняет маршрутные моки, чтобы проверять пользовательские сценарии экрана.
- Остальные находки REVIEW.md относятся к backend, `FfSettingsScreen.tsx`, моделям и сервисам, которые не входят в разрешённые файлы этого атома.
- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод не читались и не затрагивались.
