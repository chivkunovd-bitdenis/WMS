# DEV · 04-warehouse-switch · screen-dev · rework атома 4

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/ui-kit/WarehouseContextSwitch.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/ui-kit/WarehouseContextSwitch.test.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/ui-kit/WarehouseContextSwitch.runner.test.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md`

Находка №6 из `REVIEW.md` исправлена без добавления отсутствующей зависимости
`@testing-library/react`: контрактный TSX-suite теперь проверяет React-дерево и обработчики
компонента штатными React/Vitest-средствами. Поскольку текущий `vitest.config.ts` обнаруживает только
`src/**/*.test.ts`, добавлен минимальный `WarehouseContextSwitch.runner.test.ts`, который загружает
контрактный `WarehouseContextSwitch.test.tsx`. Теперь suite действительно запускается и проверяет
скрытие при 0–1 складе, раскрытие выбора, показ только имён, вызов `onChange`, закрытие после выбора,
загрузочное, недоступное и ошибочное состояния, а также неблокирующий `WarningNotice`.

В `WarehouseContextSwitch` меню получило производный от уже переданного `testId` стабильный
`data-testid`; видимое поведение и публичный интерфейс компонента не изменились.

## Гейты

- `npm run test:unit -- --run src/ui-kit/WarehouseContextSwitch.test.tsx` из
  `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend`
  — **красный, диагностический запуск**: Vitest сообщил `No test files found`, подтвердив замечание
  ревью о маске `src/**/*.test.ts`.
- `npx tsc --noEmit -p tsconfig.app.json` из
  `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend`
  — **зелёный**.
- `npm run test:unit -- --run src/ui-kit/WarehouseContextSwitch.runner.test.ts` из
  `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend`
  — **зелёный**: 1 файл, 7 тестов.
- `python3 scripts/ui/ui_guard.py` из
  `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch`
  — **красный на накопленных изменениях соседних атомов**: guard отмечает монолиты
  `frontend/src/components/WbProductPickerDialog.tsx`,
  `frontend/src/screens/v2/FfFbsOrdersScreen.tsx`,
  `frontend/src/screens/v2/FfFbsStockSyncScreen.tsx`,
  `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx` и
  `frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Файлы атома 4 новых нарушений не добавили;
  baseline флагом `--update` не менялась.
- `npm run build` из
  `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend`
  — **зелёный**: `tsc -b` и production-сборка Vite завершились успешно. Осталось штатное
  предупреждение Vite о размере нескольких существующих chunks.
- `git diff --check` из
  `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch`
  — **зелёный**.

Полный backend pytest, `ruff check .`, `mypy .` и полный frontend unit-набор не запускались: для этого
атомарного шага пользователь прямо разрешил только тесты данного атома и относящиеся к нему регрессии.

## Не реализовано

- Полностью зелёный `ui_guard.py` нельзя получить в границах атома 4: все пять оставшихся нарушений
  относятся к соседним экранам, которые роль `screen-dev` в этом проходе менять запрещает.
- Отдельных нереализованных пунктов контракта компонентов нет. Находка №6 из повторного ревью,
  относящаяся к разрешённым файлам и слою атома 4, закрыта и проверена целевым suite и сборкой.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, живой кабинет Wildberries и боевой прод
  `194.87.96.144` не читались и не изменялись.
