# WMS-415: складская полоса Astra, 10.09.2026

Это протокол исполнения WMS-062/153/154/155/156/174/177, не новый бэклог.
Рабочее дерево: `/Users/deniscivkunov/Projects/WMS/.worktrees/wms062-warehouse-docs`,
ветка `feat/wms062-warehouse-docs`, исходный HEAD `ed930463ae3504e1eb1112031a98408a3ee227dd`.
Канон и handoff принадлежат координатору; исполнитель их не редактировал.

## Границы интеграции

Прежние относящиеся коммиты: `5fee5efd` (062), `63048a82` (153), `d0317649` (155),
`92e5e445` (154), `2c2ba91b` (156), `755275da` (174), `b6449102` (177).
Поздние 182/187 и WIP190 НЕ включать в принимаемый срез. Они остаются в истории
ветки; нельзя делать merge всей ветки, полагая её целиком согласованной.
Новые коммиты применять после выбранных исходных коммитов, сохраняя изменения
чата в App.tsx/FfSuppliesShipmentsPage/FfInboundRequestView.

App.tsx и FfSuppliesShipmentsPage в этом продолжении не менялись. Перед минимальными
правками FfInboundRequestView прочитан chat diff: его ChatOpenButton, chatAuthHeaders
и currentUserId находятся в других участках; не заменять файл целиком при интеграции.
Корневой checkout, frozen wms415-claude, inventory_service, mobile/история/секреты
не редактировались. Клиентские складские/денежные данные не использовались для тестов.

## Реализованные изменения

WMS-062: регистрация вызывает существующий catalog_service.create_warehouse с
commit=False. Warehouse, его штатный WH-штрихкод, сортировочное место, tenant и
user сохраняются одной транзакцией. Общий API создания склада сохраняет commit=True.

WMS-153: создание тары в выбранной ячейке сохранено. Перенос товарной строки
использует warehouse_map_service.move_object, теперь с commit=False: складское
движение и адрес строки документа сохраняются вместе. Удаление пустой складской
тары проверяет все ненулевые остатки, а не только выбранного селлера и не сумму,
которая могла бы скрыть +n/-n. Палета расформировывается существующим сервисом
в той же транзакции. InventoryContainer validation удерживает FOR SHARE на
WarehouseBox/Pallet, физическое удаление берёт эксклюзивную блокировку.

WMS-154: «Здесь пусто» доступно из основного пересчёта и диалога карты. Сервер
обнуляет все строки выбранного места, включая уже введённые, и сохраняет выбранное
место в JSON-поле empty_places существующего InventoryCount. Это факт пересчёта,
не журнал/счётчик/новая сущность/жизненный цикл. Поле необходимо для случая, когда
товарных строк вообще нет: одни nullable actual_quantity такой факт не выражают.
При повторном чтении подтверждённое место видно с нулём. При проведении удаляется
только явно подтверждённая пустая складская тара; перед удалением заново проверяются
все текущие остатки и вложения. При новом пересчёте/находке подтверждение соответствующего
места снимается. Сам по себе ноль одной строки не означает разрешения удалить тару.

Миграция `20260910_0101`, родитель `20260910_0100`: только поле empty_places с []
для существующих документов. Предыдущая 0100 добавляет is_damaged на inbound box.
Координатор обязан согласовать alembic heads с миграциями чата/других полос;
выпуска или применения миграций на клиентских данных здесь не было.

WMS-155: обе формы отправляют только изменённые этим оператором количества;
комментарий отправляется только при его изменении. expected_comment не даёт
устаревшему окну затереть новый текст другого сотрудника (409 comment_changed).
Сохранение count перечитывает статус после row lock; проведённый другим запросом
документ нельзя редактировать через старый ORM-объект. Поздние ответы не должны
возвращать закрытый документ, объединение ответа сохраняет изменения в полёте.

WMS-156: все изменения акта читают его под row lock с populate_existing; approve
берёт Product-lock в стабильном порядке и перечитывает уже загруженные balances
после ожидания. В действующую FfInboundRequestView добавлен InboundDiscrepancyActEditor:
создать связанный акт, выбрать товар этой приёмки, ввести знаковое количество,
добавить/удалить строки, передать на утверждение. Черновик можно открыть повторно
в списке актов этой приёмки. Утверждение/отклонение — существующие кнопки списка.
Ограничения явно показаны: администратор, открытая приёмка, зона сортировки её склада.
Старый picker в FfSuppliesShipmentsPage сам по себе не доказывает достижимость:
App рендерит эту страницу с pageVariant=mp-shipments, где прежний else с созданием
акта не показывается. Поэтому нужен новый вход непосредственно из приёмки.

WMS-174: checkbox повреждения расположен в строке реального короба приёмки,
PATCH использует /operations/inbound-intake-requests/{id}/boxes/{boxId}/damaged.
Обновляется только признак и ответ перечитывается; складские движения отсутствуют.
Одна серверная функция boxes_discrepancy(planned, actual) используется в detail,
list, primary_accept и complete_receiving: план задан и факт != план, включая ноль.
Прежнее исключение «ноль коробов значит россыпь без расхождения» удалено как
неподтверждённое контрактом; клиентский receivingTotals уже сравнивал с нулём.

## WMS-177 — точный остаток для владельца общих файлов

Не принимать WMS-177 по b6449102. В прочитанном App.tsx эффект восстановления
open_inbound всегда устанавливает reception, поэтому reload сортировки меняет
рабочую поверхность. Эффект не проверяет pathname/права и при смене состояния
модалки может повторно открыть старую приёмку. В MP обычный row-click, создание
документа и initialMarketplaceUnloadId до сих пор меняют только React state:
исправлено удержание входящего open_mp, но не все писатели ссылки.

Координатору/владельцу chat необходимо сделать следующие точные изменения:

1. App.openInboundDocument должен одним navigate записывать ID и рабочую поверхность
   (например open_inbound + inbound_workspace=reception|sorting|full) на разрешённый
   маршрут FF. Для sorting использовать /app/ff/sorting, для reception /app/ff/reception.
   Для full допустим явный параметр; нельзя восстанавливать full/sorting как reception.
2. Эффект восстановления читает URL только после загрузки me/token, проверяет доступ
   соответствующей поверхности и маршрут; его источник — pathname/search, а не изменения
   ffDocModal/selectedInboundId. Уход на иной маршрут или исчезновение параметра закрывает
   inbound modal и очищает selectedInboundId. Back/Forward не должны повторно открывать
   старый документ. Явное закрытие удаляет оба параметра.
3. FfSuppliesShipmentsPage: все три входа (row-click около setDocModalId(row.id),
   createAndOpenMpShipment, initialMarketplaceUnloadId effect) должны писать open_mp.
   Восстановление из URL удерживает этот параметр до закрытия; отсутствие open_mp после
   навигации закрывает MP-modal. Переход к акту/иной сущности предварительно удаляет open_mp,
   чтобы старый эффект не заменил нужный документ старой MP-отгрузкой.
4. Прежний supply_id-путь FBS не менять. Перенести WMS-156 inbound picker/callback из
   исходного 2c2ba91b лишь с учётом актуального chat diff; новый прямой вход в приёмке
   не зависит от этих общих файлов.

Требуемые ручные проверки WMS-177: открыть документ кликом из каждого рабочего
журнала, reload reception/sorting/MP, закрыть/reload, перейти на другую страницу,
Back/Forward, переключить документ, открыть ссылку чата. Проверить и отсутствие
повторного открытия прежнего окна, а не только наличие параметра в адресной строке.

## Проверки и статус

Данные тестов изолированы: локальная база `wms415_warehouse_astra_20260910` создана
этим исполнителем; PostgreSQL17, существующий драйвер psycopg. Ни одна из команд
не использовала production/staging DB. Настройки секрета/учётные данные не менялись.
Два настоящих PostgreSQL replay уже прошли: pg_blocking_pids подтвердил ожидание
блокировки, второй approve отказал без повторного движения; другой writer +3
между чтением и approve -1 дал 7 из исходных5, а не потерял +3.

Итоговые проверки (один pytest worker, без полного pytest):

- PostgreSQL, 7 относящихся файлов: `test_inventory_counts.py test_auth.py
  test_marketplace_unload_and_discrepancy_acts.py test_inbound_intake_api_be03.py
  test_wms156_discrepancy_concurrency.py test_warehouses.py test_catalog.py`:
  **108passed**, затем старое ожидание повторного создания `main` упало. WMS062
  теперь создаёт main при регистрации. Тест переведён на проверку этого склада.
- Последующий warehouse/catalog прогон: **2passed**, затем старое ожидание одного
  склада вместо default + созданного упало. Исправлено точное ожидание двух кодов.
- После исправлений `test_catalog.py test_inventory_counts.py -k
  'catalog or destination_stock or inbound_container_deletion or truly_empty_cell'`:
  **9passed,61deselected**. Оба старых неверных ожидания устранены и перепроверены.
- Финальный PG срез `test_wms156_discrepancy_concurrency.py test_inventory_counts.py
  -k 'postgres or empty or comment or stale or move'`: **31passed,36deselected**.
  Включены все три настоящих конкурирующих PG replay. Третий подтвердил, что
  удаление короба ждёт stock-writer и отказывает после поступления в него3 единиц.
- Frontend: `vitest run` трёх файлов InventoryRows, FfInventoryCountScreen,
  inboundReceivingHelpers, `--maxWorkers=1`: **17passed**. Проверки helpers не
  являются ручной проверкой экрана. После них ещё добавлена защита позднего open/
  post-ответа после «К списку»; финальные tsc/build перечитывают эту версию.
- Финальные frontend `tsc --noEmit -p tsconfig.app.json` и `npm run build`: PASS;
  build3.34s, только предупреждение о chunk>500kB.
- Backend `ruff check .`: PASS; `mypy .`: PASS,438files.
- PostgreSQL DDL миграции0101 выполнен в отдельной схеме собственной
  `wms415_warehouse_browser_20260910`: upgrade заполняет [] у существующей строки,
  новая строка получает [], downgrade убирает колонку; вся проверочная транзакция
  откатана. Ни клиентская схема, ни клиентские данные не затронуты.

Браузер: после сообщения координатора о доступном Mac исполнитель повторил попытку.
`cua.listBrowsers()` вернул []; нативный Safari открыл новую вкладку, но вставка
адреса закончилась clipboard timeout, следующий getAXState вернул
**“The Mac is locked and automatic unlock could not unlock it.”** (около09:25МСК).
Повторного вопроса владельцу не отправлено. Локальные backend18962/frontend5198
и отдельная пустая PG-база были подняты; кнопки WMS не нажимались, вход не выполнен.
Браузерная приёмка НЕ заявлена. CI, интеграция, staging/production, deploy этим
исполнителем не выполнялись. Независимое ревью, ручные проверки и принятие остаются
у координатора. Нужны реальные create/move/delete/mark-empty/post/reload на складской
таре, обе формы комментария с двумя операторами, создание/редактирование/submit/
approve акта из reception и sorting, damage checkbox с повторным чтением.

## Разбор свежего Opus5 review WMS417

Прочитан полностью `artifacts/wms417-opus5-six-20260910/warehouse-review.md` из
координатора; это старый снимок05:58UTC, а не ревью итогового commit.

1. Старый тест409 пустой тары обновлён:201, объект виден без товарных строк.
2. Found/manual/recount снимают empty confirmation, включая родительское место;
   регрессионные сценарии прошли.
3. «Пустая ячейка» включает в удаляемый набор только складские WarehouseBox/Pallet
   без inbound_request_id; историческую тару приёмки не удаляет. Direct inbound
   target отказывает до обнуления строк. Отдельный тест сохраняет inbound-короб.
4. Обнуление ранее введённых количеств соответствует явному подтверждению всего
   выбранного места: обе кнопки теперь показывают подтверждение с точным охватом,
   старый комментарий «только ещё не тронутые строки» удалён.
5. Пустая ячейка без строк хранит empty_places cell и проводится без движений.
6. Перенос в тару с остатком этого товара вне snapshot теперь отказывает под
   Product-lock. Регресс source4/target10 проверяет отсутствие движения и потерь.
7. `onDirtyChange(false)` (WMS179) находится вне принятого scope этой полосы.
   Координатору проверить актуальный App/chat diff; здесь WMS179 не закрывается.
8. expected_comment сравнивается сразу после перечитанного статуса, до мутации строк.
9. create_sorting_object не делает rollback внешней транзакции при commit=False.
10. async-тест не пропущен: pyproject имеет asyncio_mode="auto", целевые прогоны
    выполняют его. Отсутствие отдельного декоратора не означает skip.

Отдельная граница: удаление тары, принадлежащей приёмке, возвращает
container_linked_to_inbound, чтобы не уничтожать исторические строки приёмки.
Удаление непустой/имеющей вложения тары отказывает. Если владельцу требуется
снимать со склада именно историческую inbound-тару после счёта, это нельзя считать
закрытым текущим физическим удалением WarehouseBox/Pallet: требуется отдельно
согласовать сохранение исходного документа, не удалять его строки молча.

## Точные файлы нового среза

- `backend/alembic/versions/20260910_0101_wms154_empty_places.py`
- `backend/app/api/inbound_intake.py`
- `backend/app/api/inventory_counts.py`
- `backend/app/models/inventory_count.py`
- `backend/app/services/auth_service.py`
- `backend/app/services/catalog_service.py`
- `backend/app/services/discrepancy_act_service.py`
- `backend/app/services/inbound_intake_service.py`
- `backend/app/services/inventory_container_service.py`
- `backend/app/services/inventory_count_service.py`
- `backend/app/services/pallet_service.py`
- `backend/app/services/warehouse_map_service.py`
- `backend/tests/test_auth.py`
- `backend/tests/test_catalog.py`
- `backend/tests/test_inbound_intake_api_be03.py`
- `backend/tests/test_inbound_package_catalog.py`
- `backend/tests/test_inventory_counts.py`
- `backend/tests/test_warehouses.py`
- `backend/tests/test_wms156_discrepancy_concurrency.py`
- `docs/reviews/wms415-warehouse-astra-20260910.md`
- `frontend/src/screens/ff/FfInboundRequestView.tsx`
- `frontend/src/screens/ff/InboundDiscrepancyActEditor.tsx`
- `frontend/src/screens/ff/inventory/FfInventoryCountScreen.tsx`
- `frontend/src/screens/ff/inventory/FfInventoryPage.tsx`
- `frontend/src/screens/ff/inventory/InventoryCountDialog.tsx`
- `frontend/src/screens/ff/inventory/InventoryRows.test.ts`
- `frontend/src/screens/ff/inventory/InventoryRows.ts`
- `frontend/src/screens/ff/inventory/InventoryTree.tsx`
- `frontend/src/screens/ff/inventory/InventoryTypes.ts`
- `frontend/src/screens/ff/inventory/inventoryCountApi.ts`
- `frontend/src/screens/ff/warehouse-map/FfWarehouseMapPage.tsx`

Перед сохранением повторно прочитан конец координаторского takeover handoff; новых
разрешений менять общие App/MP файлы нет. `git diff --check HEAD` PASS.

## Передача координатору

Код сохранён в `1167e0606bffae033a66b5d9f9257947746e30fd` и отправлен в origin,
ветка `feat/wms062-warehouse-docs`. Этот commit меняет ровно31 перечисленный файл.
Последующий commit протокола добавляет этот SHA и финальный статус; новых изменений
кода после проверок нет. Временные локальные процессы frontend5198/backend18962
остановлены исполнителем. Отдельные синтетические базы сохранены для воспроизведения.

Для канона, который обновляет только координатор: WMS062/153/155/156/174 имеют
реализацию и целевые технические проверки, **ожидают независимого review и живой
проверки UI**, не приняты. WMS154 реализован и проверен для складской тары,
историческая inbound-тара остаётся явно описанной границей. WMS177 **не завершён**:
точные требуемые изменения переданы выше, App.tsx/FfSuppliesShipmentsPage принадлежат
chat, исполнитель их не менял. WMS182/187/190 не принимаются этим отчётом.
Ни канон, ни общие handoff-файлы исполнитель не редактировал; merge/CI/deploy не делал.
