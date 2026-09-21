# WMS-501 · Аудит границ организаций, селлеров и ролей

> Первичный этап. Ограничения охвата и уровня доказательств ниже уточнены продолжением от21.09.2026: [nested-ID и production](isolation-completion.md). Актуальный сводный вывод — [REPORT](REPORT.md). Старое правило остановки из-за обнаружения пароля отменено.

Дата: 21.09.2026. Продуктовый baseline: `3e125074`; каталог аудита: `.worktrees/wms501-performance-isolation-audit`. Прочитаны AGENTS.md и постановка `docs/requirements/WMS-501.md`. Продукт, миграции и рабочие данные не изменялись; внешние кабинеты, `.env`, действующие ключи и production не открывались. Все данные воспроизведений синтетические. Авторизационные запросы используют подписанные тестовые JWT, без подмены `get_current_user`; транспорт ASGI вызывает настоящий FastAPI in-process, а не внешний HTTP-сервер.

## Что установлено

На корректно связанных тестовых данных **новой доступной через API межорганизационной утечки товаров не найдено**. Это ограниченный результат проведённых проверок, а не гарантия отсутствия всех утечек. Каталог, скан, выбранные документы, инвентаризация, печать и отрицательные контроли чужого tenant отказывают или отфильтровывают чужое.

**Общую изоляцию селлеров считать закрытой нельзя.** Подтверждён доступ обычного селлера к чужим фоновым заданиям внутри своей организации, если организация не имеет точного slug `avpack-9uczh`. Исправление WMS-488 защищает этот путь только для AVpack. Отдельно подтверждён обход отключённых прав чтения складских движений. Это две различные границы: организация, селлер и право сотрудника не взаимозаменяемы.

База не обеспечивает универсальную проверку совместимости tenant всех связанных строк. В контролируемом опыте PostgreSQL разрешил связать движение организации A с товаром B; чтение движений A затем вернуло артикул B. Некорректную связь создал сам тест прямой записью в тестовую БД. **HTTP-путь создания такой связи не найден, наличие таких данных в production не проверено.** Это воспроизведённый недостаток дополнительной защиты от ошибок записывающего кода, а не заявленная удалённая уязвимость.

## Подтверждённые находки

### ISO-01 · P1 · Чужие задания доступны обычному селлеру вне AVpack

**Условие:** пользователь с ролью `fulfillment_seller`, без `can_manage_seller_shops` и без делегирования, знает UUID задания другого селлера своей организации либо общего задания организации. UUID случайный и сам по себе не позволяет перечислить задания; знание идентификатора является предусловием опыта. Между двумя организациями этот путь закрыт.

**Путь:** `GET /operations/background-jobs/{job_id}` → `backend/app/api/background_jobs.py:231` → `background_job_service.get_job` (`backend/app/services/background_job_service.py:53`) проверяет только tenant → проверка seller на `backend/app/api/background_jobs.py:252` выполняется только при `uses_home_seller_scope` → `backend/app/services/seller_shop_service.py:42` возвращает true лишь для точного `Tenant.slug == "avpack-9uczh"` → остальные пользователи доходят до `return _job_out(job)` на строке 280.

**Фактический результат:** для обычного tenant два запроса с подписанным тестовым токеном вернули 200: чужой `wildberries_cards_sync` и общий `movements_digest`. Ответ содержит `payload_json`, `result_json`, исходный `error_message`. У другого tenant те же UUID дали 404. После изменения только тестового slug на точный AVpack общий job дал 404. Результат и диагностика синтетические; реальное наличие чувствительной информации в конкретных производственных заданиях не исследовалось. Код worker действительно формирует общие счётчики движений (`background_job_service.py:77–89`) и сохраняет `str(exc)` при ошибках.

**Ожидание:** обычный селлер видит только разрешённый ему результат; общие складские задания не становятся доступны из-за известного UUID. Наличие имени AVpack не должно быть условием общей seller-защиты.

**Доказательство:** `isolation-probes.py::test_non_avpack_seller_can_read_another_sellers_job`, `isolation-jobs-repro.json`, `isolation-probes-results.txt`. Проверка утверждает текущее нежелательное поведение; её PASS означает успешное воспроизведение дефекта.

**Рекомендация для отдельного исправления:** проверять seller-владение для любого seller-role. Для допустимого менеджера использовать повторно проверенную эффективную область магазина. Типы общих/неизвестных задач разрешать по конкретной роли/праву, не по произвольному полю `seller_id` в JSON. Сохранить законное делегирование других организаций и AVpack home-only. Добавить отрицательные тесты для обычного tenant, а не только AVpack.

### ISO-02 · P2 · Отключённое право не закрывает список складских движений

**Условие:** FF staff без прав или сотрудник селлера с `can_products=false` имеет действующий токен. Знание чужого ID не требуется.

**Путь:** `GET /operations/inventory-movements` → `backend/app/api/inventory_movements.py:45` использует `get_current_user` и `seller_line_product_scope`, но не вызывает `assert_inventory_read_access`, в отличие от `/summary` (`inventory_movements.py:113`) и `/inventory-balances/summary` (`inventory_balances.py:108`). Сервис `backend/app/services/inventory_service.py:1835` ограничивает tenant и, для селлера, владельца продукта, но не проверяет право.

**Фактический результат:** у FF staff запрос остатков дал 403, а список движений — 200 и движения двух селлеров своей организации. У seller staff Products=false остатки дали 403, движения — 200 и собственный товар. Ответ раскрывает ID/артикул, количество, тип и дату движения, ID автора и, при адресном хранении, ID ячейки. Чужого tenant в этом опыте нет; для селлера чужого магазина тоже нет.

**Доказательство:** `isolation-probes.py::test_permission_bypass_recent_movements`, `isolation-permission-repro.json`.

**Рекомендация:** применять общий существующий guard чтения остатков/движений; не вводить новую роль. Перепроверить FF staff с разрешённым Inventory и seller staff с разрешённым Products как положительные контроли.

### ISO-G1 · Риск дополнительной защиты: согласованность tenant связанных строк

**Условие опыта:** ошибочный код, импорт или прямой SQL уже записал движение tenant A с `product_id` товара tenant B. Доступный пользователю HTTP-способ сделать это не установлен.

`backend/app/models/inventory_movement.py:65–86` содержит отдельные FK на tenant/product/seller/location/warehouse. Составного FK `(tenant_id, product_id)` здесь нет. Сервис чтения `backend/app/services/inventory_service.py:1843–1846` ограничивает tenant движения, но присоединяет продукт только по product_id. Изолированный PostgreSQL принял некорректную связь; настоящий обработчик вернул чужой SKU админу A.

`backend/app/db/session.py:16–24` создаёт обычные AsyncSession; общего tenant-фильтра запросов здесь нет. Поиск `ROW LEVEL`, `row_level`, `with_loader_criteria` по `backend/app`/`backend/alembic` не нашёл общего механизма RLS (построчного контроля самой БД). Отдельные составные FK присутствуют в billing-моделях; утверждение «составных FK вообще нет» было бы неверным. Производственная DB-role/RLS отдельно не проверялась.

**Доказательство:** `isolation-probes.py::test_database_allows_mismatched_tenant_product_reference`, `isolation-corrupt-reference-repro.json`. Это не повод объявлять, что сегодня FF может подставить произвольный product_id через API.

**Следующая проверка:** read-only сверка фактических связей tenant у product/seller/warehouse/location/document/stock/marketplace account по отдельному доступу к нужному окружению. После этого выбрать минимум защиты в записывающих сервисах и критических FK. Глобальную RLS без проекта миграции и проверки worker вводить нельзя.

## Реестр поверхности и сила проверки

Скрипт `isolation-inventory.py` без импорта приложения перечисляет **416 деклараций методов маршрутов в 45 API-модулях**, включая оба `contract_router`, импортированный reset-router и условные тестовые маршруты. `isolation-route-inventory.json` сохраняет файл, строку, путь, метод, handler, явные зависимости и вызываемые функции для каждой декларации.

Runtime-инвентарь `isolation-runtime-route-inventory.json` содержит **414 установленных методов маршрутов / те же 45 модулей**. Два условных E2E-маршрута не включены. Контрактные `/fbs/*`, `/fbs-sellers/*` и reset-legacy-limits реально установлены через `router.routes.extend`, поэтому включены. У всех **407 защищённых регистраций** запрос без авторизации дал **401**; 7 публичных маршрутов отмечены и не вызывались. Это полный контроль наличия входной авторизации, но не полный перебор комбинаций объектов/ролей/параметров. Стандартные `/docs`, `/redoc`, `/openapi.json` FastAPI описывают схему; это не бизнес-маршруты, в 414 не входят.

Ниже `S` означает чтение маршрута, видимого guard и основного сервисного scope; это не ручная проверка каждой ветки каждой функции. `T` означает выполненные адресные регрессионные тесты; `P` — новое воспроизведение. У всех строк кроме public действует общий runtime-контроль авторизации. Количество — регистраций HTTP-методов, не файлов/SQL-запросов.

| API-модуль (`backend/app/api/`) | Методов | Прослеженный доступ и сервисная граница | Проверка / оставшийся пробел |
|---|---:|---|---|
| auth.py | 11 | JWT sub+tenant проверяются по текущему User; login/reset проверяют пароль/ссылку; switch-seller — `can_act_as_seller` и tenant Seller | S/T/P: auth + WMS-488; подмена tenant в подписанном тестовом JWT даёт 403. Реальный production-вход/доставка писем не проверены |
| staff_accounts.py | 5 | `can_manage_ff_staff`; список/правка через `tenant_id=actor.tenant_id`, staff permissions service | S/T: staff_users. Не перебраны все сочетания прав/саморедактирования |
| seller_staff_accounts.py | 4 | actor tenant + home seller; `can_manage_seller_staff`, целевой сотрудник в этой же области | S/T: seller_staff_and_delete_drafts; делегированный магазин не автоматически становится областью управления персоналом |
| sellers.py | 4 | `list_sellers` tenant+effective seller; WB-catalog admin проверяет Seller.tenant; создание от actor tenant | S/T: WMS-488 catalog. Не каждый вариант account-create повторён отрицательно |
| tenant_settings.py | 2 | FF admin и `user.tenant_id` → tenant_settings_service | S; произвольного tenant_id параметра нет, все варианты переключений настроек не исполнялись |
| subscription.py | 3 | Текущий tenant из User; pay только admin, sync авторизованный user | S; внешняя оплата и callback инфраструктура не вызывались |
| products.py | 29 | Catalog root tenant, seller permission + effective seller; bulk проверяет каждый product, OZ link-owner и product-owner | S/T: WMS-488 direct/mixed read/write matrix, import idempotency. Не каждый формат файла/битые исторические связи |
| fbs_stock_rule_reset.py | 1 | `_assert_reset_access` для каждого product и effective seller, затем tenant bulk service | S/T: WMS-488 product matrix; явный imported router учтён |
| warehouses.py | 20 | FF permission/admin; catalog warehouse tenant; map/containers валидируют tenant/warehouse, ячейка принадлежит складу | S/T: warehouse_map_api; полный перебор смешанных container-kind/ID не выполнен |
| inbound_intake.py | 44 | Reception либо seller draft; `get_request` tenant+seller; строки проверяют product tenant/owner, вложенные IDs — принадлежность request | S/T: seller_isolation, WMS-488 document-line negative. Не все 44 mutations перебраны с чужими nested IDs |
| inbound_marking.py | 5 | Reception; `_request` по tenant+id, code/event/product tenant и seller; worker выводит tenant из persisted job | S; дополнительные ветки ЧЗ-внешнего провайдера в этом пакете не запускались |
| kiz_reprints.py | 5 | Reception; история/claim/release по tenant и id | S/T: wms489_kiz_reprints, в том числе foreign tenant. Физическая печать не проверена |
| inbound_package_catalog.py | 2 | Cells/Inventory; сервис ограничивает короб и parent-request tenant; lookup использует ту же область | S/T: SQLite 4 tests; PG 2 теста прерываются на предположениях о datetime/SQL диалекте, подробнее ниже |
| inventory_balances.py | 5 | Inventory / Products permission; seller override только admin; tenant Product/Balance/Location и seller scope | S/T/P: WMS-488 inventory, отрицательный контроль ISO-02 |
| inventory_movements.py | 2 | tenant движений, seller через Product; `/summary` имеет permission guard, простой list — нет | S/T/P: ISO-02 и условный ISO-G1; это открытые замечания |
| inventory_counts.py | 12 | FF Inventory; count tenant, склад/ячейки/товары/контейнеры валидируются относительно count | S/T: весь test_inventory_counts.py, foreign count/cell. Полный сценарий каждой ошибки счётчика не переносится на production |
| stock_transfer.py | 1 | Cells; tenant, исходная/целевая локации и product в inventory_service | S; отдельная новая матрица tenant/seller transfer не выполнялась |
| outbound_shipment.py | 10 | list/get seller scope, создание от effective seller; lines owner, admin операции tenant root | S/T: seller_isolation и WMS-488 foreign line. Не все вложенные storage mutations |
| marketplace_unload_requests.py | 32 | `_get_visible_request` tenant + `assert_request_visible`; seller draft effective scope; warehouse operations FF permission | S/T: marketplace_unload_and_discrepancy_acts, WMS-488 foreign line. Не все box/line/allocation комбинации |
| packaging_tasks.py | 13 | FF Packaging; task tenant, связанные inbound/unload/order проверяются сервисами | S; часть пути покрывается print/warehouse suites, полной собственной cross-tenant матрицы не было |
| marking_codes.py | 33 | Router-level seller HonestSign; pool/product/template seller guards; tenant catalog; FF печать с Packaging | S/T: WMS-488 marking, marking_pools_read/pool_products. Все 33 сценария загрузки/экспорта/шаблонов не перебраны |
| marking_credentials.py | 4 | FF admin либо seller Settings, effective seller; сервис проверяет Seller.tenant; ответы статуса без значений секретов | S; проверялся исходный код, действующие секреты/кабинеты не открывались; реальный provider не вызывался |
| reports.py | 4 | Inventory/Products guard; seller_scope имеет приоритет над query seller_id; tenant reporting services, CSV тот же scope | S/T: WMS-488 reports/export; все grouping/timezone/старые данные не покрыты |
| billing.py | 17 | Role-specific billing guards; tenant profiles/tariffs/ledger/invoices; seller self-filter | S/T: configuration_api, invoice_api. Все варианты ledger/details не перебраны |
| billing_invoices_v2.py | 5 | Все FF admin; tenant-bound selected source documents и invoice getter | S/T: invoice_v2_api; все invoice source unions/исторические миграции отдельно не исследовались |
| storage.py | 5 | Storage access; tenant measurements/statements; seller ограничен home seller, print проверяет statement owner | S; delegated-shop UX семантика home/effective не объявлена утечкой; отдельная новая cross-tenant матрица не выполнена |
| discrepancy_acts.py | 8 | FF admin; act tenant; add_line product tenant и optional inbound line принадлежит linked request | S/T: marketplace_unload_and_discrepancy_acts; отдельные исторические несогласованные seller связи не проверены |
| document_events.py | 1 | FF admin; tenant+document_type+document_id в document_event_service | S; raw payload исторических событий производственной БД не проверялся |
| background_jobs.py | 3 | Create admin / self-settings; GET tenant; ограничение seller только exact AVpack | S/T/P: ISO-01; остальные классы результата не интерпретировать как доказанно безопасные |
| notifications.py | 3 | tenant AND получатель user/effective seller/FF role; mark-read те же условия | S/T: notifications; тестовый seed выключен в runtime |
| scan_resolver.py | 1 | Product permission; tenant всех классов; seller получает только свои product matches, до ambiguity/fallback | S/T: WMS-488 SKU/WB/OZ/OZN, foreign tenant, collisions, warehouse object denial |
| wb_mp_warehouses.py | 1 | FF shipping access; tenant cache, явного tenant от клиента нет | S; ответы реального WB/refresh из нескольких организаций не вызывались |
| fbs_orders.py | 8 | FF Packaging/admin; worklist/history/cancel/getters tenant, seller/account constrained; contract router включён | S; выбранные guards/основные queries прочитаны, новая полная FBS object matrix не исполнялась |
| fbs_supplies.py | 48 | FF Packaging/admin; supply tenant root перед nested orders/trbx/picks/print/dispatch | S/T: print suites частично проходят supply endpoints. Все 48 nested mutations и внешняя сдача не проверены |
| fbs_sellers.py | 12 | FF operator/admin; Seller+Binding+Warehouse tenant; marketplace account supplier scope | S; contract router включён; все внешние WB/Ozon операции не исполнялись |
| fbs_marking.py | 3 | FF Packaging, `get_order_metadata/list_order_markings/sync` с tenant; seller code mismatch проверяется сервисом | S; внешний ЧЗ/маркетплейс не вызывался |
| fbs_kiz.py | 4 | FF Packaging; supply/order tenant, MarkingCode tenant+order seller; commit idempotency scoped | S; все разновидности Ozon multiproduct/киз не исполнены в новом пакете |
| fbs_print_assets.py | 2 | FF Packaging; `_load_asset` tenant+ID до чтения бинарных данных, root supply/order guards | S/T: print_assets с cross-tenant 404. S3/права bucket не проверялись |
| fbs_print_jobs.py | 6 | FF Packaging; tenant job/type, warehouse/asset tenant; intent сравнивает tenant+requester+asset/warehouse | S/T: print_job_delivery. Физический printer не проверен |
| warehouse_print.py | 11 | Employee Reception/admin; отдельный PC token digest, pairing TTL, tenant+warehouse+connection у agent jobs | S/T: sorting_print_wms442, foreign pairing/scope/employee API denial. Реальный PC не подключался |
| wildberries_integration.py | 9 | Admin или self Settings; Seller.tenant, effective seller; sync передаёт оба tenant/seller | S/T: WMS-488 self sync mock; реальные запросы WB не выполнялись |
| ozon_integration.py | 5 | Self Settings, effective seller; account service tenant+seller, public_status без секретов | S/T: WMS-488 direct sync mock; live Ozon не вызывался |
| ozon_returns.py | 9 | Reception; Inbound request tenant до giveout/groups/pass/barcode/provider | S; реальные provider pass/refresh не вызывались и не прочитаны |
| client_errors.py | 1 | `get_current_user`, диагностический приём ошибки от текущего пользователя | S; не API чтения чужих ошибок; инфраструктура сборщика логов не проверялась |
| health.py | 1 | Публичный health, нет tenant-данных | S, публичный маршрут не нагружался |

## Вне обычного API

**Файлы и печать.** Прямого `StaticFiles`/mount каталога WMS data в `main.py` нет. `frontend/deploy/Caddyfile` отдаёт собранные файлы `/srv` и проксирует `/api`, не содержит публикации `/data`. Доступ к FBS-байтам идёт через `fbs_print_asset_service._load_asset` с tenant (`:338–353`) и защищённый handler; paths нормализуются с запретом выхода за разрешённый каталог (`fbs_print_asset_storage.py:78–108`). Исходные PDF маркировки получают ключ `marking-imports/<tenant>/<batch>/...` (`marking_import_storage_service.py:31–39`), но пространство имён само по себе не авторизация. У S3 storage backend нет встроенного tenant guard: он полагается на серверный выбор ключа. Реальные bucket policies, CDN, подписанные URL и содержимое volume не проверены.

**Worker и очередь.** `tasks/background_jobs.py` принимает job_id либо server-scheduled tenant/seller; `background_job_service.py` загружает persisted job и берёт его tenant. Autopoll перечисляет пары Seller.tenant+Seller.id и account tenant/seller, затем передаёт их сервисам (`fbs_autopoll_service.py:123–203`). Необластьный `session.get(BackgroundJob, job_id)` внутри worker не является HTTP-утечкой: клиент сам не получает worker-ответ и не задаёт job tenant при создании. Доступ к результату оценивается отдельно и имеет ISO-01. Redis в репозитории используется для Celery; доказательств универсального tenant-aware response cache не найдено. Реальные ACL брокера, возможность прямой отправки заданий, очередь/retry/dead-letter с нескольких tenant не проверены.

**Cache.** Tenant WB warehouse cache использует tenant predicates (`wb_mp_warehouse_service.py:221–271`). Печатные кеши привязаны к server-side asset/supply ID после tenant-getter. Локальный `pool_ids_cache` маркировки живёт в пределах одного вызова, а не глобально между пользователями. Это не исключает непроверенные кеши вне backend (reverse proxy, browser/service worker, production CDN).

**Websocket.** Поиск `websocket` в `backend/app` не обнаружил установленного websocket endpoint; текущие уведомления — HTTP. Отсутствующий транспорт не оценивался как PASS изоляции какого-либо внешнего websocket-сервиса.

**Браузерная сессия.** По исходнику `frontend/src/hooks/useAuth.ts` WMS-488 добавил синхронизацию localStorage, сброс profile при смене токена и отсечение запоздалого `/auth/me` по токену вкладки и текущему storage (`:72–128`, `:147–236`). Это не новый браузерный прогон; смена пользователя при уже открытых документах, возврат браузером назад, service worker/cache и все ответы экранов не перепроверялись этой веткой аудита. Историческая WMS-488 acceptance не перенесена автоматически на новый production-сеанс.

**Мобильный ТСД.** В этом worktree mobile отсутствует. Его auth/cache/offline sync и защита от смены tenant относятся к отдельному мобильному обследованию в общем WMS-501; backend-набор не доказывает безопасность локально сохранённых данных ТСД.

## Выполненные тесты и воспроизводимость

Использован `/Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python`, чистое окружение через `env -i`; текущий каталог — audit-worktree. В новых probes до app imports стоит обязательная проверка точного WMS_TEST_DATABASE_URL; другой адрес либо отсутствие переменной прерывает сбор тестов до fixture очистки схемы. `.env` отсутствует в этом worktree и не читался. PostgreSQL — новый отдельный loopback сервер `127.0.0.1:55451`, одноразовая БД `wms501_isolation`, пользователь `deniscivkunov`; внешняя БД не используется. `conftest.py` очищает всю схему, поэтому **команды допустимы только для этой одноразовой БД**. Все PostgreSQL-прогоны последовательные, без xdist. Не нужны рабочие секреты.

| Набор | Результат | Файл доказательства |
|---|---|---|
| WMS-488 catalog/home/product matrix + seller-isolation/catalog/WB-import, SQLite | 121 passed, 31.98 s | isolation-regression-tests.txt |
| Те же 6 файлов + print-assets, print-job-delivery, sorting-print-WMS442, warehouse-map, inventory-counts, WMS489 KIZ; PostgreSQL | 232 passed, 90.46 s | isolation-postgres-tests.txt |
| Notifications/jobs/staff/seller-staff/billing/marking/inbound-packages/unload-discrepancy/auth/product-import; PostgreSQL | 82 passed, 2 failed, 84.83 s | isolation-secondary-postgres-tests.txt |
| Новые WMS-501 probes: permissions, JWT mismatch, все protected routes без auth, corrupt FK, non-AVpack jobs; PostgreSQL | 5 passed, 2.50 s — PASS воспроизведения, не исправления ISO-01/02 | isolation-probes-results.txt |

Два падения дополнительного PostgreSQL-прогона нельзя скрывать. `test_inbound_package_catalog.py:310` сравнивает дату с naive SQLite-строкой `2026-08-23T10:15:00`, тогда как PG возвращает эквивалент `2026-08-23T14:15:00+04:00`; `:441` требует SQLite-placeholder `status != ?`, вместо реального PG `status != %(status_1)s::VARCHAR`. Оба теста до падения получили корректный список кодов коробов. Первый падает **до** оставшихся проверок lookup/foreign tenant, поэтому весь тест не считается PG PASS изоляции. Отдельный повтор файла на SQLite дал **4 passed, 5.08 s** и сохранён в `isolation-secondary-sqlite-check.txt`. Продукт и тесты репозитория ради PASS не менялись.

Точная команда новых probes (из audit-worktree):

```sh
env -i PATH=/usr/bin:/bin:/usr/sbin:/sbin \
  PYTHONPATH=backend:backend/tests \
  WMS_ALLOW_PUBLIC_REGISTRATION=true APP_ENV=development \
  JWT_SECRET_KEY=wms501-isolated-test-secret-at-least-32-characters \
  WMS_TEST_DATABASE_URL=postgresql+psycopg_async://deniscivkunov@127.0.0.1:55451/wms501_isolation \
  WMS_TEST_DATA_DIR=/Users/deniscivkunov/Projects/WMS/.worktrees/wms501-performance-isolation-audit/.audit-runtime/isolation-data \
  /Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python -m pytest \
  -q -o asyncio_mode=auto -p conftest docs/evidence/WMS-501/isolation-probes.py
```

Первые два regression-набора запускаются тем же Python с `PYTHONPATH=backend`, обычным `pytest -q` и явным списком файлов, записанным в `isolation-test-commands.sh`. Для SQLite переменные `WMS_TEST_DATABASE_URL` и `WMS_TEST_DATA_DIR` не задаются: conftest создаёт собственную уникальную БД. Runtime-инвентарь рекурсивно обходит `original_router`: установленная FastAPI использует ленивые `_IncludedRouter`, поэтому простой цикл `isinstance(app.routes, APIRoute)` ошибочно дал бы нулевое покрытие. В сохранённом probe есть assert `len(inventory) > 400`, исключающий такой ложный PASS.

## Что необходимо до заявления о полной изоляции

1. Исправить ISO-01 и ISO-02 отдельными задачами и повторить отрицательные/положительные проверки. Для ISO-01 обязательно обычная организация, AVpack, seller A/B, разрешённый менеджер и FF-контроль.
2. Превратить реестр 414 методов в отрицательную матрицу вложенных ID для **каждой** mutation: чужой tenant, чужой seller, разрешённый parent + чужая line/box/product, смешанный batch, replay/idempotency. Текущая проверка 407 no-auth запросов не заменяет этот шаг.
3. На фактическом окружении отдельно проверить состав файлов релиза/SHA, внешнюю DB роль/RLS, непротиворечивость исторических FK, настройки reverse proxy/data/S3/broker и два настоящих входа разных FF. Ни один из этих внешних фактов из тестовой БД не выводится.
4. Браузером и на ТСД повторить смену учётки при запросе в полёте/открытом каталоге/документе, shared-login на двух устройствах, logout/relogin и восстановление страницы. Подтверждение серверной области данных не доказывает очистку ранее показанных данных устройства.

Итог этой ветки — карта всех API-модулей и установленных авторизационных точек, адресные доказательства корректных tenant-границ и два воспроизведённых дефекта доступа внутри организации. Полный security sign-off, product fixes и production acceptance в рамках этого отчёта не выполнены.
