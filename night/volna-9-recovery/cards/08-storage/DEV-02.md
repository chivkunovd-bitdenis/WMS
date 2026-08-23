# 08-storage · DEV

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/docs/blockers/S-11.md`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/cards/08-storage/DEV.md`

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npx tsc --noEmit -p tsconfig.app.json` — зелёный, код выхода `0`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage && python3 scripts/ui/ui_guard.py` — красный, код выхода `1`: новые относительно его базовой линии нарушения в не относящихся к атому файлах `frontend/src/components/WbProductPickerDialog.tsx`, `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx` и `frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Эти файлы не изменялись и запрещены границами данного атома; базовая линия не обновлялась.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npm run test:unit -- src/screens/ff/FfStoragePage.test.ts` — зелёный, `6 passed`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage && pytest backend/tests/test_storage_measurement_service.py -k test_storage_api_rejects_future_month` — зелёный, `1 passed, 10 deselected`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend && npm run test:e2e -- storage.spec.ts --grep "staff sees why future storage months are unavailable"` — не запустился: среда запретила Playwright webServer слушать `127.0.0.1:18000` (`Errno 1: operation not permitted`) до выполнения сценария.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage && git diff --check` — зелёный.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage && git add docs/blockers/S-11.md night/volna-9-recovery/cards/08-storage/DEV.md && git commit -m "docs(storage): correct future month blocker"` — не выполнен: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-08-storage1/index.lock` (`Operation not permitted`), поэтому SHA отсутствует.

## Не реализовано

- Нет. В пределах этого атома поведение экрана и API не менялось: карточка блокировки приведена в соответствие уже действующему контракту, экранному ограничению и независимой серверной валидации.

## Находки

- Секции «Будущий расчётный месяц» и «Разошлись слои» обновлены: ложное утверждение о доступном будущем месяце и отсутствии объяснения удалено.
