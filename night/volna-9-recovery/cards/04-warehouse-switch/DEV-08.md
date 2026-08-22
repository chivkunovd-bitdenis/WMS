# 04-warehouse-switch · screen-dev

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/TransfersScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md`

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` из `frontend/`: не завершился в этой рабочей копии и был остановлен после 60 секунд без вывода; локальные зависимости frontend отсутствуют.
- `python3 scripts/ui/ui_guard.py`: красный из-за новых нарушений в чужих файлах `src/components/WbProductPickerDialog.tsx`, `src/screens/v2/FfFbsOrdersScreen.tsx`, `src/screens/v2/FfFbsStockSyncScreen.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx`, `src/screens/v2/SellerInboundDraftScreen.tsx`. Нового нарушения в `TransfersScreen.tsx` не сообщено; базовую линию не менял.
- `npm run test:unit -- --run frontend/src/screens/v2/TransfersScreen.tsx`: красный, `vitest: command not found`.
- `git diff --check`: зелёный.
- Отдельный commit не создан: Git не смог создать `.git/worktrees/lane-1-04-warehouse-switch/index.lock` (`Operation not permitted`). Изменения остаются в рабочем дереве этой зарегистрированной рабочей копии.

## Не реализовано

- Буквальное живое отображение и фильтрация пары после FBS-pick не подключены: маршрут передаёт `TransfersScreen` только `locations` и `products`, а API `/operations/inventory-movements` не отдаёт `warehouse_id`, `transfer_group_id` и стороны операции. Экран подготовлен к этим входным данным (`warehouses`, текущий склад, операции пары и состояние загрузки), но их подключение потребует изменения `frontend/src/App.tsx` и backend API, которые не входят в разрешённые файлы S-25 и не были прямо названы в находке ревью для этого экранного шага.
- E2E-сценарий не расширен до кросс-складского FBS-pick: без указанного API и подключения маршрута такой тест не может пройти реальный пользовательский путь и не должен имитировать его фиктивными утверждениями.
