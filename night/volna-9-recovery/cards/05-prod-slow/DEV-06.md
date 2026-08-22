# DEV · 05-prod-slow

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/src/screens/v2/FfFbsOrdersScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/tests-e2e/ff-fbs-orders.spec.ts`

`/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/src/screens/v2/fbsApi.ts` не изменялся: курсор и лимит 50 уже поддерживались его контрактом.

Исправлены контрактные тексты ошибки первой загрузки и пустого списка. E2E-сценарий теперь моделирует две страницы по 50 заказов, проверяет догрузку по `next_cursor`, сохранение выбранного заказа, отсутствие дублей и скрытие кнопки после последней страницы.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — не подтверждён: локальный TypeScript-бинарник отсутствует, `npx` завис на попытке запуска/разрешения команды и был остановлен.
- `python3 scripts/ui/ui_guard.py` — красный: скрипт сообщил о нарушениях монолитности в `src/components/MarkingPrintDialog.tsx`, `src/components/WbProductPickerDialog.tsx`, `src/screens/v2/FfFbsOrdersScreen.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx`, `src/screens/v2/SellerInboundDraftScreen.tsx`. Базовую линию через `--update` не менял.
- `npm run test:unit` — красный до запуска тестов: `sh: vitest: command not found`.

## Не реализовано

- Полный набор браузерных сценариев `S-03-TC-001`–`S-03-TC-007` и `S-03-TC-010`–`S-03-TC-012` в рамках этого прохода не запускался: в окружении отсутствуют frontend-зависимости для запуска тестов.
- `fbsApi.ts` не потребовал правки, так как `fetchFbsWorklist` уже передаёт `limit` и `cursor`.
