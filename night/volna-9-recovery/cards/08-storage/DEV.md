## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/screens/ff/FfStoragePage.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/App.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/tests-e2e/storage.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/cards/08-storage/DEV.md`

Экран S-11 больше не показывает захардкоженные локальные расчёты. Сводка, формирование, ручной обмер, история, фиксация и повторная печать обращаются к API с авторизацией; при недоступности API экран показывает штатную ошибку, а не вымышленные финансовые данные. Добавлены e2e-сценарии `S-11-TC-001`, `003`—`015`, `017`, `020` с пользовательскими действиями и видимыми результатами.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend`: зелёный.
- `npm run test:unit` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend`: зелёный.
- `npx playwright test tests-e2e/storage.spec.ts --reporter=line` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend`: зелёный.
- `python3 scripts/ui/ui_guard.py` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage`: красный до правок S-11 и вне разрешённых файлов этого атома: новые нарушения в `frontend/src/components/WbProductPickerDialog.tsx`, `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`, `frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Базовая линия не обновлялась.
- `git diff --check`: зелёный.

## Не реализовано

- Буквальное сохранение тарифа не реализовано: необходимый API единого биллинга (владение карточки 09-A по `ARCH-CROSS.md`) в этой рабочей копии не опубликован. Диалог не подменяет сохранение локальным состоянием и явно сообщает о границе.
- Полная загрузка сводки требует `GET /operations/storage/statements`; в доступном backend есть только rebuild/fix/print, поэтому на фактическом текущем сервере этот запрос перейдёт в предусмотренное контрактом состояние ошибки загрузки. Экран и e2e уже используют этот контракт, но добавить backend-маршрут запрещено границами роли `screen-dev` и списком файлов S-11.

## Находки

Секреты, ключи, токены, `.env`, персональные данные и кабинеты учётных данных не открывались и не использовались.
