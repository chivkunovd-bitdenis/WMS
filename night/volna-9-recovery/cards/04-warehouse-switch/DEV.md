# DEV · 04-warehouse-switch · атом 8

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/App.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/TransfersScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/TransfersScreen.test.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/tests-e2e/transfer-and-outbound.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md`

`App.tsx` добавлен к двум исходным файлам атома, потому что находка 8 в `REVIEW.md` прямо называет подключение маршрута S-25 в этом файле причиной отсутствия складского контекста и transfer-данных. Другие продуктовые экраны не менялись.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — **красный вне слоя S-25**: компилятор останавливается на `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/FbsSupplyCreateDialog.test.ts:55`, где JSX записан в файле с расширением `.ts`. Отдельная проверка `TransfersScreen.tsx` и его unit-теста с тем же `tsconfig.app.json` и исключённым чужим сломанным тестом — **зелёная**.
- `python3 scripts/ui/ui_guard.py` — **красный вне изменённых экранных файлов**: новые нарушения перечислены в `WbProductPickerDialog.tsx`, `FfFbsOrdersScreen.tsx`, `FfFbsStockSyncScreen.tsx`, `FfFbsSupplyWorkspace.tsx` и `SellerInboundDraftScreen.tsx`. Для `TransfersScreen.tsx` нового нарушения нет; `App.tsx` улучшен с 3492 до 3491 строки. Базовая линия не двигалась.
- `npm run test:unit` — **красный вне слоя S-25**: 21 файл и 152 теста зелёные, единственный failed suite — тот же `FbsSupplyCreateDialog.test.ts`, который esbuild не может разобрать как JSX. Целевая команда `npm run test:unit -- src/screens/v2/TransfersScreen.test.ts` — **зелёная**, 2/2 теста.
- `npx playwright test tests-e2e/transfer-and-outbound.spec.ts --grep "warehouse context filters transfers" --list` — **зелёный**, найден 1 сценарий. Живой запуск той же проверки **заблокирован средой**: Playwright webServer получил `Errno 1 operation not permitted` при bind `127.0.0.1:18000`. Сам сценарий добавлен: Север показывает локальную и межскладскую операции, Юг оставляет соответствующую сторону пары, раскрытие показывает обе ячейки без UUID.
- `git diff --check` — **зелёный**.
- `git add` / отдельный commit — **красный по среде**: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-04-warehouse-switch/index.lock` (`Operation not permitted`). Файлы атома не проиндексированы, commit SHA отсутствует; чужой `JOURNAL.md` не захватывался.

## Не реализовано

- Буквальная проверка на живом backend после настоящего cross-warehouse pick не завершена в роли `screen-dev`. Текущий ответ `GET /api/operations/inventory-movements` не содержит нужных экрану полей `transfer_group_id`, `warehouse_id`, `warehouse_name`, `storage_location_code` и `product_name`. S-25 теперь правильно принимает, группирует и фильтрует этот контракт, а E2E закрепляет экранное поведение через API-границу, но реальные пары не появятся до зависимого backend-атома 11, который расширит read-модель журнала.
- Общие красные гейты не исправлены, потому что их причины лежат в соседних файлах и продуктовых атомах, которые роль `screen-dev` и контракт этого атома запрещают менять «заодно».
- Результат локально реализован, но не сохранён в Git: sandbox запрещает запись в служебный каталог worktree, поэтому восстановимого commit SHA нет.

## Находки

- На экранном слое исправлена находка 8: маршрут передаёт операционные склады, выбранный сессионный склад, обработчик смены контекста и движения; при входе S-25 запрашивает свежий журнал. Технические строки с общей transfer-группой собираются в одну строку, а неполная пара не достраивается предположением.
- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались и не изменялись.
