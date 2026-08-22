## Изменённые файлы

Изменений в исходных файлах атома нет: `MovementFlowChart` уже реализован в соответствии с контрактом, экспортирован через ui-kit и покрыт требуемыми unit-сценариями.

Проверенные файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/MovementFlowChart.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/index.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/MovementFlowChart.test.tsx`

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — зелёный.
- `python3 scripts/ui/ui_guard.py` — красный из-за четырёх новых нарушений в несвязанных файлах: `frontend/src/App.tsx`, `frontend/src/components/WbProductPickerDialog.tsx`, `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`, `frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Базовую линию не обновлял.
- `npm run test:unit -- --run frontend/src/ui-kit/MovementFlowChart.test.tsx` — не запущен: в `frontend` отсутствует локальный исполняемый `vitest` (`node_modules` не установлен).

Проверены сценарии контракта: видимая легенда и доступное описание серий, отсутствие пунктирной серии при выключенном сравнении, сообщение «За выбранный период движений нет» и отдельный скелет при загрузке.

## Не реализовано

- Замечание ревью о том, что экран/API не передают предыдущую дневную серию, не исправлялось: оно относится к `FfReportsPage` и backend, а не к разрешённым файлам атома `MovementFlowChart`.
- Полный зелёный `ui_guard.py` невозможен без правок четырёх чужих экранов или обновления базовой линии; оба действия выходят за границы атома.
- Unit-тест не подтверждён запуском из-за отсутствующего `vitest`; установка зависимостей не выполнялась.

