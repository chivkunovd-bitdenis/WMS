# Фича 1

# DEV · 04-warehouse-switch · атом 1

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/tests/test_warehouses.py` — добавлены регрессии resolver-а для legacy-коллизии штрихкодов и изоляции чужого tenant.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md` — этот отчёт.

## Что реализовано

- `GET /warehouses/resolve` — существующее разрешение сканов подтверждено тестом: коллизия склада и ячейки возвращает `409 barcode_ambiguous`, а штрихкод другого tenant возвращает `404 barcode_unknown`.
- `catalog_service.resolve_warehouse_scan` — при исторической межсущностной коллизии не выбирает объект по приоритету; это покрыто прямой регрессией на сохранённых данных.

## Миграции

- Нет новых миграций: миграция `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/alembic/versions/20260822_0094_warehouse_operational_barcode.py` уже добавляет `is_operational` и `barcode`, а также помечает `fbs-wb-*` / `FBS WB *` служебными.

## Тесты

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/tests/test_warehouses.py` — складской штрихкод → `warehouse`, штрихкод ячейки → `location`, legacy-коллизия → понятный `409`, чужой tenant → `404` без раскрытия данных.

## Гейты

- `ruff check .` — не пройден: 80 существующих нарушений вне изменённого файла; `ruff check tests/test_warehouses.py` пройден.
- `mypy .` — не пройден: 21 существующая ошибка в шести других файлах; изменённый тест типовых ошибок не добавил.
- `pytest` — остановлен после 118 passed на двух существующих регрессиях вне атома: `test_document_number_service.py::test_inbound_and_unload_api_assign_document_number` (`product seller not found`) и `test_fbs_manual_pick.py::test_manual_pick_rejects_wrong_cell_product_and_packed_order` (ожидается 404, получен 200). Целевой `pytest tests/test_warehouses.py` — пройден, 1 passed.
- `python3 scripts/ci/back_guard.py` — не запущен: файла `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/scripts/ci/back_guard.py` нет в рабочей копии.
- `python3 scripts/ci/check_migrations.py` — не запущен: файла `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/scripts/ci/check_migrations.py` нет в рабочей копии.
- `git diff --check` — пройден.

## Не реализовано

- Находка review №3 о переносе старых FBS-binding/заказов при маркировке legacy-складов относится к следующему атому 3 (`fbs_supply_service.py`) и не затронута: этот проход ограничен атомом 1 и его файлами.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод не открывались и не изменялись.

# Фича 2

# Backend dev · 04-warehouse-switch · атом 2

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/services/fbs_supply_validator_service.py` — рекомендация склада считает покрытые единицы, а предупреждение возвращает доступное количество на складе-источнике.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/services/fbs_supply_service.py` — выбранный склад участвует в обеих проверках перед созданием; без явного выбора поставка берёт рассчитанный операционный рекомендованный склад, а не legacy-склад заказа.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/tests/test_fbs_stock_availability.py` — регрессия для агрегирования остатков только по операционным складам и точного количества у источника подбора.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md` — отчёт backend-dev.

## Гейты

- `ruff check` по затронутому backend-набору: пройдено.
- `mypy .`: не пройдено из-за 21 существующей ошибки вне атома; в частности, в неизменённом `fbs_warehouse_binding_service.py` уже есть два нарушения generic-типов.
- `pytest tests/test_fbs_stock_availability.py -q`: пройдено.
- `pytest`: пройдено, 822 теста собраны; процесс завершился с кодом 0.
- `ruff check .`: не пройдено из-за 80 существующих нарушений вне затронутых файлов.
- `back_guard.py`: не запущен — файл `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/scripts/ci/back_guard.py` отсутствует в рабочей копии.
- `check_migrations.py`: не запущен по той же причине: файл отсутствует.
- `git diff --check`: пройдено.
- `git commit`: не выполнен — среда запретила создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-04-warehouse-switch/index.lock` (`Operation not permitted`). Изменения остаются незакоммиченными в этой рабочей копии.

## Не реализовано

- Миграций нет: для атома 2 они не требуются.
- Остальные находки `REVIEW.md` относятся к соседним атомам или frontend-слою и в этом проходе не менялись.

# Фича 3

# DEV · 04-warehouse-switch · атом 3

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/tests/test_fbs_supply_from_orders.py` — добавлен регрессионный API-сценарий: если старый клиент не передал `selected_warehouse_id`, создание использует рассчитанный рекомендуемый операционный склад, а не склад исходного заказа.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md` — отчёт backend-dev.

## Гейты

- `ruff check .` — не пройден: 80 ранее существовавших нарушений вне атома; изменённый тест проходит проверку стиля.
- `mypy .` — не пройден: 21 ранее существовавшая ошибка в шести сторонних файлах; изменённый тест не добавил ошибок.
- `pytest -q tests/test_fbs_supply_from_orders.py -k 'warehouse_switch or selected_operational or without_selection'` — пройдено, 3 passed, 17 deselected.
- `pytest` — запуск начат, но среда завершила вывод до итогового результата после старта 823 тестов; финальный статус не получен.
- `python3 scripts/ci/back_guard.py` — не запущен: файла `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/scripts/ci/back_guard.py` в рабочей копии нет.
- `python3 scripts/ci/check_migrations.py` — не запущен: файла `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/scripts/ci/check_migrations.py` в рабочей копии нет.
- `git diff --check` — пройден.
- `git commit` — не выполнен: Git отказал в создании `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-04-warehouse-switch/index.lock` с ошибкой `Operation not permitted`; изменения остались в рабочем дереве.

## Не реализовано

- Сервис и роут уже содержат нужный контракт этого атома: `selected_warehouse_id`, смену склада до первого действия, запрет после старта и выбор `recommended_warehouse_id` без явного поля. Изменения кода не потребовались; добавлена защита от регрессии замечания ревью №3.
- Находка ревью №1 относится к frontend-совместимости формы ответа; она не изменялась в рамках роли backend-dev и заданного атомарного backend-слоя.
- Находки ревью №2 и №4–15 относятся к другим атомам, файлам либо frontend-слою и не менялись.

## Блокеры

Полные repo-гейты зафиксировали существующие нарушения и отсутствующие CI-скрипты; целевой регрессионный набор пройден. Сохранение в Git не завершено из-за запрета записи lock-файла вне разрешённой рабочей копии.

# Фича 4

# 04-warehouse-switch · screen-dev

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/ui-kit/WarehouseContextSwitch.test.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md`

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend` — зелёный.
- `npm run test:unit` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend` — зелёный. Добавлена проверка `WarningNotice` и подтверждено, что в раскрытом переключателе видны только имена складов, без их ID.
- `python3 scripts/ui/ui_guard.py` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch` — красный из-за новых нарушений в неразрешённых этим атомом файлах: `frontend/src/components/WbProductPickerDialog.tsx`, `frontend/src/screens/v2/FfFbsOrdersScreen.tsx`, `frontend/src/screens/v2/FfFbsStockSyncScreen.tsx`, `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`, `frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Базовая линия не менялась.

## Не реализовано

Все пункты атома реализованы буквально: `WarehouseContextSwitch` скрывается при 0–1 варианте, открывает список имён и закрывает его после выбора; loading, disabled и error состояния не позволяют совершить действие и показывают причину. `WarningNotice` показывает неблокирующее предупреждение.

## Находки

Ревью `REVIEW.md` содержит 15 замечаний к серверному коду и экранным срезам. Прямых замечаний к файлам этого ui-kit атома нет; их исправление выходит за разрешённые границы данного шага.

Git-коммит не создан: среда запретила создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-04-warehouse-switch/index.lock` (`Operation not permitted`). Изменения остаются в рабочем дереве и требуют коммита из среды с доступом к Git metadata.

# Фича 5

# DEV · 04-warehouse-switch · feature 5

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/utils/fbsWarehouse.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/utils/fbsWarehouse.test.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/contexts/WarehouseContext.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/App.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/apps/seller/SellerApp.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md`

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` из `frontend/` — зелёный.
- `python3 scripts/ui/ui_guard.py` из корня — красный: новые нарушения уже находятся в не затронутых этим атомом `src/components/WbProductPickerDialog.tsx`, `src/screens/v2/FfFbsOrdersScreen.tsx`, `src/screens/v2/FfFbsStockSyncScreen.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx`, `src/screens/v2/SellerInboundDraftScreen.tsx`. Базовая линия не менялась.
- `npm run test:unit -- fbsWarehouse.test.ts` из `frontend/` — не запущен: `vitest: command not found` (в рабочей копии отсутствуют установленные frontend-зависимости).
- `git diff --check` — зелёный.
- Commit не создан: Git не имеет права создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-04-warehouse-switch/index.lock` (`Operation not permitted`). Изменения остаются в рабочем дереве.

## Не реализовано

- Находки REVIEW №1–15, кроме границ общего сессионного контекста, относятся к следующим атомам и их экранным/серверным файлам. В этом атоме устранены неявный выбор первого операционного склада, наследование контекста между разными пользователями и применение контекста ФФ как глобального фильтра портала селлера.
- Полный запуск unit-тестов невозможен без `vitest` в `frontend/node_modules`; новый тест `fbsWarehouse.test.ts` добавлен, но не выполнен в этой рабочей копии.

# Фича 6

# DEV · 04-warehouse-switch · атом 6

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/FfFbsStockSyncScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md`

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` (каталог `frontend/`) — зелёный.
- `python3 scripts/ui/ui_guard.py` (корень) — красный: базовая линия уже отстаёт в пяти экранах; для S-04 показано `экран-монолит 1083 → 1133`. Базовую линию не обновлял.
- `npm run test:unit` (каталог `frontend/`) — не запустился: `sh: vitest: command not found`.
- `git diff --check` — зелёный. Commit не создан: Git запретил создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-04-warehouse-switch/index.lock` (`Operation not permitted`).

## Не реализовано

- S-01 буквально не реализован. В реестре экран S-01 — `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/ProductsScreen.tsx`, а исходный список атома называет `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/sections/CatalogSection.tsx`, который является администрированием складов и ячеек. Находка review №12 требует ещё и передачу данных из `App.tsx`; этот файл не разрешён для данного атома и роли.
- E2E-сценарий не менялся: имеющийся сценарий работает через значение авторизации из `localStorage`; профиль роли запрещает читать токены.

## Находки

- S-04: при нуле операционных складов остаётся только `EmptyState` с просьбой добавить рабочий склад; фильтры, таблица и действия публикации не показываются. При выбранном складе таблица и кнопка синхронизации ограничены только его активными привязками. Смена контекста не вызывает публикацию.

# Фича 7

# DEV · 04-warehouse-switch · атом 7

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/tests-e2e/inbound-intake.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/tests-e2e/outbound-submit-storage.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md`

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` (каталог `frontend/`) — зелёный.
- `python3 scripts/ui/ui_guard.py` (корень) — красный из-за пяти уже существующих отклонений вне разрешённых файлов атома: `src/components/WbProductPickerDialog.tsx`, `src/screens/v2/FfFbsOrdersScreen.tsx`, `src/screens/v2/FfFbsStockSyncScreen.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx`, `src/screens/v2/SellerInboundDraftScreen.tsx`. Базовую линию не обновлял.
- `npm run test:unit -- --run` (каталог `frontend/`) — не запустился: `sh: vitest: command not found`.
- `npx playwright test tests-e2e/inbound-intake.spec.ts tests-e2e/outbound-submit-storage.spec.ts --workers=1` (каталог `frontend/`) — зелёный.
- `git diff --check` — зелёный.
- Commit не создан: Git не разрешил создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-04-warehouse-switch/index.lock` (`Operation not permitted`). Результат остаётся локальным незакоммиченным diff.

## Не реализовано

- Нет. Экраны S-22 и S-24 уже получают склад нового документа из сессионного контекста и показывают ячейки открытого документа; ревью-пункт №15 закрыт проверками для двух складов. Остальные находки вердикта относятся к другим экранам либо серверному слою и не входят в этот атом.

## Находки

- В этой рабочей копии unit-зависимость `vitest` отсутствует, поэтому обязательный unit-гейт нельзя выполнить до восстановления зависимостей.

# Фича 8

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

# Фича 9

# DEV · 04-warehouse-switch · атом 9

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/fbsApi.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/FbsSupplyCreateDialog.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/FbsSupplyCreateDialog.test.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/tests-e2e/ff-fbs-supply.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md`

Исправлено чтение реального ответа preflight: `stock_preflight`, варианты и рекомендация склада, а также строки остатков теперь берутся из верхнего уровня API. При локальной нехватке показано одно неблокирующее предупреждение с разбивкой; общая нехватка показывает блокирующую ошибку и отдельные колонки `Нужно / Всего / Не хватает`. До ответа на актуальный preflight после смены склада или типа сдачи создание заблокировано, поэтому устаревший ответ не может создать поставку.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend` — зелёный.
- `python3 scripts/ui/ui_guard.py` из корня — красный только по уже затронутым другими карточками экранам: `WbProductPickerDialog.tsx`, `FfFbsOrdersScreen.tsx`, `FfFbsStockSyncScreen.tsx`, `FfFbsSupplyWorkspace.tsx`, `SellerInboundDraftScreen.tsx`. Изменённый здесь `FbsSupplyCreateDialog.tsx` отмечен как улучшение (`своя-кнопка 3 → 2`); базовая линия не менялась.
- `npm run test:unit -- FbsSupplyCreateDialog.test.ts` из frontend — не запущен: `sh: vitest: command not found`; в рабочей копии отсутствует исполняемый `frontend/node_modules/.bin/vitest`.

## Не реализовано

- Нахождение 2 из `REVIEW.md` (распределение дефицита по нескольким исходным складам и расчёт рекомендации в единицах) относится к backend-слою `fbs_supply_validator_service.py`, который не входит в файлы атома 9. Фронтенд отображает реальные строки текущего API и не подменяет складские количества.
- E2E не запускался по той же причине отсутствующей локальной установки frontend-зависимостей; сценарий обновлён под реальный верхнеуровневый ответ API.

# Фича 10

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/FfFbsOrdersScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/tests-e2e/ff-fbs-supply.spec.ts`

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` (из `frontend/`) — зелёный.
- `python3 scripts/ui/ui_guard.py` (из корня) — красный: храповик фиксирует новые уже существующие превышения размера экранов, в том числе `FfFbsOrdersScreen.tsx` (1587 → 1664) и `FfFbsSupplyWorkspace.tsx` (2493 → 2605). Базовую линию не обновлял.
- `npm run test:unit -- --run src/screens/v2/FfFbsSupplyWorkspace.test.ts` (из `frontend/`) — не запустился: `vitest: command not found` в данной рабочей копии.
- `git diff --check` — зелёный.

## Не реализовано

- Серверная фильтрация FBS-worklist по WMS-складу не добавлена: текущий API принимает только WB-склад. Экран дочитывает все страницы при выбранном WMS-контексте и фильтрует по физическому складу, поэтому записи за первой страницей не скрываются, но параметр на сервере должен добавить backend-атом.

## Находки

- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались.

# Фича 11

# DEV · 04-warehouse-switch · backend-dev

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/services/fbs_picking_service.py
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/services/inventory_service.py
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/models/inventory_movement.py
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/alembic/versions/20260822_0095_inventory_movement_dimensions.py
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/tests/test_fbs_picking.py
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md

## Что реализовано

- `scan_pick_product` повторно проверяет ключ идемпотентности после блокировки поставки; кросс-складской FBS-pick и его undo явно разрешают только свой специализированный путь переноса.
- `transfer_on_hand_between_locations` снова запрещает перемещение между разными складами по умолчанию; товар без `seller_id` можно принять и записать в журнал, без постановки задачи публикации WB.

## Миграции

- `20260822_0095_inventory_movement_dimensions`: `seller_id` в движениях остаётся nullable, чтобы не ломать исторические и обычные FF-товары без селлера; `warehouse_id` остаётся обязательным.

## Тесты

- `test_generic_inventory_transfer_rejects_another_warehouse`: общий writer отклоняет межскладской перенос.
- `test_fbs_picking.py`: 9 passed, включая идемпотентность и undo полной пары.
- `test_fbs_packaging_integration.py`: 15 passed, включая запрет списания из чужой сортировки и отсутствие обхода.

## Гейты

- ruff: целевые изменённые файлы — `All checks passed`; полный `ruff check .` не прошёл из-за 80 существующих ошибок вне этого атома.
- mypy: не прошёл из-за 4 существующих ошибок в `wildberries_credentials_service.py`, `fbs_stock_sync_service.py` и `fbs_warehouse_binding_service.py`; изменённые файлы не перечислены среди ошибок.
- pytest: целевые `test_fbs_picking.py` и `test_fbs_packaging_integration.py` — 24 passed (прогнаны отдельными группами).
- back_guard.py: не запущен — файла `scripts/ci/back_guard.py` в этой рабочей копии нет.
- check_migrations.py: не запущен — файла `scripts/ci/check_migrations.py` в этой рабочей копии нет.
- git diff --check: пройден.

## Не реализовано

- Не добавлялись API и UI-пункты из соседних атомов. Файл `fbs_packaging_integration_service.py` не менялся: запрет списания из чужой сортировки уже реализован и покрыт тестом.

## Блокеры

Нет. Секреты, токены, `.env` и кабинеты учётных данных не читались.

# Фича 12

# DEV · 04-warehouse-switch · backend-dev

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/services/fbs_picking_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/services/inventory_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/models/inventory_movement.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/alembic/versions/20260822_0095_inventory_movement_dimensions.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/tests/test_fbs_picking.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md`

## Что реализовано

- `scan_pick_product` повторно проверяет ключ идемпотентности после блокировки поставки; кросс-складской FBS-pick и его undo явно разрешают только свой специализированный путь переноса.
- `transfer_on_hand_between_locations` снова запрещает перемещение между разными складами по умолчанию; товар без `seller_id` можно принять и записать в журнал, без постановки задачи публикации WB.

## Миграции

- `20260822_0095_inventory_movement_dimensions`: `seller_id` в движениях остаётся nullable, чтобы не ломать исторические и обычные FF-товары без селлера; `warehouse_id` остаётся обязательным.

## Тесты

- `test_generic_inventory_transfer_rejects_another_warehouse`: общий writer отклоняет межскладской перенос.
- `test_fbs_picking.py`: 9 passed, включая идемпотентность и undo полной пары.
- `test_fbs_packaging_integration.py`: 15 passed, включая запрет списания из чужой сортировки и отсутствие обхода.

## Гейты

- ruff: целевые изменённые файлы — `All checks passed`; полный `ruff check .` не прошёл из-за 80 существующих ошибок вне этого атома.
- mypy: не прошёл из-за 4 существующих ошибок в `wildberries_credentials_service.py`, `fbs_stock_sync_service.py` и `fbs_warehouse_binding_service.py`; изменённые файлы не перечислены среди ошибок.
- pytest: целевые `test_fbs_picking.py` и `test_fbs_packaging_integration.py` — 24 passed (прогнаны отдельными группами).
- back_guard.py: не запущен — файла `scripts/ci/back_guard.py` в этой рабочей копии нет.
- check_migrations.py: не запущен — файла `scripts/ci/check_migrations.py` в этой рабочей копии нет.
- git diff --check: пройден.

## Не реализовано

- Не добавлялись API и UI-пункты из соседних атомов. Файл `fbs_packaging_integration_service.py` не менялся: запрет списания из чужой сортировки уже реализован и покрыт тестом.

## Блокеры

Нет. Секреты, токены, `.env` и кабинеты учётных данных не читались.

# DEV · 04-warehouse-switch · screen-dev · атом 12

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/tests-e2e/ff-fbs-supply.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md`

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` (каталог `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend`) — не выполнен: в рабочей копии отсутствует `node_modules/.bin/tsc`; `npx` ожидает внешнюю установку пакета.
- `python3 scripts/ui/ui_guard.py` (корень рабочей копии) — красный. Храповик сообщает уже имеющиеся новые нарушения базовой линии, в том числе `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx: экран-монолит 2493 → 2605`; базовую линию флагом `--update` не менял.
- `npm run test:unit` (каталог `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend`) — не выполнен: в рабочей копии отсутствует `node_modules/.bin/vitest`.
- Целевой Playwright-сценарий `ff-fbs-supply.spec.ts` — не выполнен по той же причине: отсутствует `node_modules/.bin/playwright`.
- `git diff --check` — зелёный.
- Отдельный Git-коммит не создан: Git не разрешил создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-04-warehouse-switch/index.lock` (`Operation not permitted`).

## Не реализовано

- Изменение экранной логики не потребовалось: в `FfFbsSupplyWorkspace.tsx` скан склада после начала подбора уже показывает `Склад закреплён: подбор уже начат` до любого сброса `pickLocation`. Исправлен пробел в проверке: E2E теперь сначала выбирает ячейку, затем сканирует другой склад и подтверждает, что следующий ожидаемый скан всё ещё товар, то есть выбранная ячейка сохранена.
- Автоматический запуск сценария не подтверждён из-за отсутствующих зависимостей frontend в этой рабочей копии.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод не открывались и не изменялись.

# Фича 13

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/SellerInboundDraftScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/src/screens/v2/sellerInboundDocumentUi.test.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/frontend/tests-e2e/seller-cabinet.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md`

Экран теперь принимает смену склада черновика только когда ответ API возвращает именно
выбранный `warehouse_id`; иначе селектор возвращается к исходному состоянию и показывает
понятную ошибку. E2E-сценарий проверяет два доступных операционных склада, отсутствие их
технических кодов в выборе, сохранение выбранного склада при создании черновика и отсутствие
глобального переключателя в S-26.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — зелёный.
- `python3 scripts/ui/ui_guard.py` — красный. Новые относительно его baseline нарушения:
  `src/components/WbProductPickerDialog.tsx` (0 → 646),
  `src/screens/v2/FfFbsOrdersScreen.tsx` (1587 → 1664),
  `src/screens/v2/FfFbsStockSyncScreen.tsx` (1083 → 1133),
  `src/screens/v2/FfFbsSupplyWorkspace.tsx` (2493 → 2605),
  `src/screens/v2/SellerInboundDraftScreen.tsx` (1111 → 1267). Baseline не обновлялся.
- `npm run test:unit` — красный: `sh: vitest: command not found`; зависимости этой рабочей
  копии не содержат исполняемый `vitest`.
- `npx playwright test tests-e2e/seller-cabinet.spec.ts --grep 'admin creates seller user; seller sees filtered catalog and inbound'` — зелёный.

## Не реализовано

- Контракт S-28 требует сохранять смену склада уже созданного черновика. Экран отправляет
  `warehouse_id` и теперь проверяет ответ, но текущая серверная схема PATCH не принимает это
  поле и молча возвращает прежний склад. Исправление схемы и сервисной операции относится к
  backend-слою и не входит в разрешённые файлы роли `screen-dev`; экран не выдаёт ложный успех.

## Находки

- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались и не изменялись.
