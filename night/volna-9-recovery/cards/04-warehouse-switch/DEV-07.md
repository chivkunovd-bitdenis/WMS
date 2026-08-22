# DEV · 04-warehouse-switch · atom 7 · screen-dev

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/InboundScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/OutboundScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/tests-e2e/inbound-intake.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/tests-e2e/outbound-submit-storage.spec.ts`

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — PASS, команда завершилась без ошибок.
- `python3 scripts/ui/ui_guard.py` — FAIL: новые нарушения обнаружены в чужих файлах `src/components/WbProductPickerDialog.tsx`, `src/screens/v2/FfFbsStockSyncScreen.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx` и `src/screens/v2/SellerInboundDraftScreen.tsx`; `InboundScreen.tsx` улучшен. Эти файлы не входят в атом и не изменялись.
- `npm run test:unit` — FAIL до запуска тестов: `vitest: command not found`.

## Не реализовано

- Полное переключение контекста из строки S-22/S-24 не подключено на уровне родительского состояния: текущие экранные пропсы не передают callback выбора склада, а изменение файлов вне реестра этого атома запрещено. Переключатель подключён к существующему ui-kit и принимает опциональный `onWarehouseChange`; при одном складе строка и второй выбор полностью отсутствуют.
- Сценарий с двумя складами и записью выбранного склада в новый документ не добавлялся: для этого требуется передать callback из родительского контейнера и отдельная E2E-фикстура с двумя операционными складами, что выходит за список файлов атома.
