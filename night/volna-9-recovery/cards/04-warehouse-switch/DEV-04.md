# 04-warehouse-switch · screen-dev · атом 4

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/ui-kit/WarehouseContextSwitch.test.tsx` — закреплена граница находки ревью № 5: при пустом подготовленном списке переключатель не рендерится, чтобы экран показал собственный `EmptyState`; при ошибке без вариантов причина остаётся видна. Для `WarningNotice` добавлена проверка, что соседнее главное действие остаётся доступным.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md` — отчёт текущего screen-dev прохода.

Файлы реализации `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/ui-kit/WarehouseContextSwitch.tsx`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/ui-kit/WarningNotice.tsx` и экспорт из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/ui-kit/index.ts` уже соответствовали контракту, поэтому в этом проходе не изменялись.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend` — красный до проверки проекта: в рабочей копии нет локального `tsc`, а `npx` не смог получить пакет из закрытой сети (`ENOTFOUND registry.npmjs.org`).
- `python3 scripts/ui/ui_guard.py` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch` — красный на ранее изменённых, запрещённых этому атому файлах: `frontend/src/components/WbProductPickerDialog.tsx`, `frontend/src/screens/v2/FfFbsOrdersScreen.tsx`, `frontend/src/screens/v2/FfFbsStockSyncScreen.tsx`, `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`, `frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. В файлах атома нового нарушения нет; baseline не обновлялся.
- `npm run test:unit -- --run src/ui-kit/WarehouseContextSwitch.test.tsx` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend` — красный до запуска тестов: `vitest: command not found`, потому что в рабочей копии отсутствует `frontend/node_modules/.bin/vitest`.

## Не реализовано

- Находка ревью № 5 целиком не закрыта: при нуле операционных складов экран S-03 должен показать `EmptyState` и заблокировать складские действия. Это поведение относится к `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/FfFbsOrdersScreen.tsx`, который не входит в файлы атома 4. Сам `WarehouseContextSwitch` по контракту обязан скрываться при 0–1 варианте; это поведение сохранено и теперь явно защищено тестом.
- Остальные находки `REVIEW.md` относятся к backend, контексту приложения или конкретным экранам и не затрагивают разрешённые файлы этого ui-kit атома.

## Находки

Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод `194.87.96.144` не открывались и не изменялись. Новых находок по данным или персональным данным в границах атома нет.
