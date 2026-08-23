# DEV · 06-picking-list-order · атом 1

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/ui-kit/ModalFrame.tsx` — в состоянии `busy` отключено закрытие по Escape; существующий обработчик по-прежнему не вызывает `onClose` ни для Escape, ни для запроса закрытия фона.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/ui-kit/FilterBar.tsx` — у `ChoiceFilter` добавлен заметный фокус клавиатуры, выбранное значение остаётся единственным изменяемым значением.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/ui-kit/PickingListPrimitives.test.ts` — добавлены проверки блокировки Escape/закрытия при `busy`, доступности кнопки фильтра для клавиатурного фокуса и единственного вызова смены выбранного значения.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/night/volna-9-recovery/cards/06-picking-list-order/DEV.md` — отчёт роли.

## Гейты

- ЗЕЛЁНЫЙ: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend && npx tsc --noEmit -p tsconfig.app.json`.
- КРАСНЫЙ, вне слоя атома: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order && python3 scripts/ui/ui_guard.py`. Скрипт сообщил новые нарушения только в `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/components/WbProductPickerDialog.tsx` и `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/screens/v2/SellerInboundDraftScreen.tsx`; эти файлы не входят в данный атом и не менялись.
- КРАСНЫЙ, инфраструктура: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend && npm run test:unit -- src/ui-kit/PickingListPrimitives.test.ts` не стартовала: `sh: vitest: command not found`. Полный backend-регресс, `ruff` и `mypy` намеренно не запускались по атомарному ограничению.
- ЗЕЛЁНЫЙ: `git diff --check`.
- КРАСНЫЙ, ограничение рабочей среды: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order && git add -- frontend/src/ui-kit/ModalFrame.tsx frontend/src/ui-kit/FilterBar.tsx frontend/src/ui-kit/PickingListPrimitives.test.ts night/volna-9-recovery/cards/06-picking-list-order/DEV.md && git diff --cached --check && git commit -m "fix(ui-kit): harden picking list primitives"` не запустил staging: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-06-picking-list-order/index.lock` (`Operation not permitted`). Несвязанные изменения не добавлялись; SHA отсутствует.

## Не реализовано

Пункты контракта атома реализованы буквально. Живой browser/clicker-прогон и снимки из находки `JUDGE.md` не создавались: это отдельный последующий слой проверки экрана, а не изменение разрешённых файлов ui-kit-атома.

## Находки

- Вердикт `JUDGE.md` заблокирован отсутствием живого стенда и снимков всех `S-03-TC-001`…`S-03-TC-013`; кодовых находок в `ModalFrame` или `ChoiceFilter` там не указано.
- Локальный frontend не содержит установленного исполняемого `vitest`, поэтому целевой unit-тест требует восстановления зависимостей перед повторным прогоном.
