## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/src/components/MarkingPrintDialog.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/docs/blockers/S-03.md`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/night/volna-9-recovery/cards/05-prod-slow/DEV.md`

Исправлен несуществующий setter состояния, добавлена защита от завершения старого polling после закрытия или смены контекста диалога, а истечение подготовленного PDF сохраняет отдельное операторское состояние. В журнал блокировок добавлено правило запрета повторной печати активной/готовой ленты.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — зелёный.
- `python3 scripts/ui/ui_guard.py` — красный: сообщает о новых baseline-отклонениях в `src/components/MarkingPrintDialog.tsx`, `src/components/WbProductPickerDialog.tsx`, `src/screens/v2/FfFbsOrdersScreen.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx`, `src/screens/v2/SellerInboundDraftScreen.tsx`. Базовую линию не обновлял.
- `npm run test:unit -- --runInBand` — красный: `vitest: command not found` в этой рабочей копии.
- `npm run test:e2e -- --grep "S-03-TC-008|S-03-TC-009|S-03-TC-014|S-03-TC-015"` — команда завершилась без совпавших тестов; в разрешённых спецификациях нет сценариев с этими TC-ID, поэтому перечисленные Playwright-пути не подтверждены.
- `git commit` — не выполнен: Git не разрешил создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-05-prod-slow/index.lock` (`Operation not permitted`). Изменения не сохранены коммитом.

## Не реализовано

- Находки ревью о backend-задачах и `FfFbsOrdersScreen.tsx` не исправлялись: они находятся вне файлов и слоя данного атома.
- В `frontend/tests-e2e/ff-marking-print-constructor.spec.ts` и `frontend/tests-e2e/ff-separate-marking-print.spec.ts` отсутствуют требуемые сценарии `S-03-TC-008`, `S-03-TC-009`, `S-03-TC-014`, `S-03-TC-015`; их нельзя выдать за пройденные без отдельной реализации тестов.
