## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/FfFbsOrdersScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`

S-03 теперь получает независимый список операционных складов, не строит варианты из текущих строк и сохраняет выбранный WMS-контекст в пределах сессии. Рабочее место показывает доступные операционные склады, меняет склад черновой поставки через существующий PATCH и блокирует смену после начала операции с объяснением.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — зелёный.
- `python3 scripts/ui/ui_guard.py` — красный: храповик сообщил новые нарушения размера монолита в `FfFbsOrdersScreen.tsx` и `FfFbsSupplyWorkspace.tsx` (также сообщил нарушения в несвязанных экранах). Базовая линия не обновлялась.
- `npm run test:unit -- --run src/screens/v2/FfFbsSupplyWorkspace.test.ts` — не запущен: в рабочей копии отсутствует исполняемый `vitest` (`vitest: command not found`).
- `git diff --check` — зелёный.

## Не реализовано

- Тесты в `/frontend/src/screens/v2/FfFbsSupplyWorkspace.test.ts` и `/frontend/tests-e2e/ff-fbs-supply.spec.ts` не расширялись: локальный unit-runner отсутствует, а атомарная правка ограничена двумя экранами из слоя screen-dev.
- Находка 13 (`docs/blockers/S-03.md`) не внесена: файл не входит в разрешённый список экранного атома и относится к документационному слою.
- Бэкенд-находки 1–8 и 11–12 не входят в роль `screen-dev` и не изменялись.
