**WMS-325 остаётся частично выполненной: исправление `fd710d1e` привязывает аудит к проверенному пользователю, но остальные пользовательские изменения покрыты неоднородно. Подтверждены как отсутствующие записи, так и удаление уже существующей истории.**

Проверка выполнена только по коду `065e23267f511dedc4c2d2ded24638acca8ce34f`. Фактический HEAD рабочего дерева уже другой, поэтому исходники читал из указанного коммита. `fd710d1e` входит в его историю. Файлы, канон и Git не менял; агентов, тесты, контейнеры и БД не запускал. Ниже — текстовый протокол существующей WMS-325. Все ссылки закреплены на проверенном коммите.

Исходное требование карточки — **«каждый переход статуса и изменение данных помечать именем пользователя»**, включая статистику сотрудников. Оно шире изменений прав. Это прямо зафиксировано в [карточке WMS-325](https://github.com/chivkunovd-bitdenis/WMS/blob/065e23267f511dedc4c2d2ded24638acca8ce34f/docs/KANONICHESKIY_BACKLOG.md#L6591).

**Что уже делает существующий аудит**

После проверки пользователя `get_current_user` вызывает `bind_authenticated_document_actor(user.id)`. Обработчик запроса устанавливает начальный `system` и очищает контекст после запроса; `BackgroundTask` выполняется с `system`. Повторного разбора заголовка авторизации в аудит-механизме после `fd710d1e` нет. Это подтверждено в [deps.py](https://github.com/chivkunovd-bitdenis/WMS/blob/065e23267f511dedc4c2d2ded24638acca8ce34f/backend/app/api/deps.py#L129) и [document_event_service.py](https://github.com/chivkunovd-bitdenis/WMS/blob/065e23267f511dedc4c2d2ded24638acca8ce34f/backend/app/services/document_event_service.py#L102).

Автоматический сборщик перед сохранением ORM-объектов — объектов моделей приложения — отслеживает конкретный перечень:

| Объект | Автоматически записываемые изменения |
|---|---|
| Приёмка | `status`, `warehouse_id`, `planned_delivery_date` |
| Строка приёмки | Добавление/удаление; `expected_qty`, `actual_qty`, `defective_qty` |
| FBS-поставка | `status`, `warehouse_id`, `planned_shipment_date` |
| FBS-заказ | `status`; изменение `supply_id` отражается добавлением/удалением строки поставки |
| Поставка на маркетплейс | `status`, `warehouse_id`, `wb_mp_warehouse_id`, `planned_shipment_date` |
| Её строка | Добавление/удаление; `quantity` |

Создание и удаление самих документов, остальные поля, короба и другие модели этим перечнем не покрываются. Массовый `session.execute(update(...))` также не превращается в обход изменённых ORM-объектов. Основание — [сборщик и обработчики полей](https://github.com/chivkunovd-bitdenis/WMS/blob/065e23267f511dedc4c2d2ded24638acca8ce34f/backend/app/services/document_event_service.py#L367).

В миграциях найден один соответствующий триггер: **только изменение `fbs_supplies.status`**, с `actor_user_id=NULL`, `source=system`. При установленном признаке приложения он пропускает запись. Это не резервный аудит остальных таблиц и не доказательство пользовательского авторства: [миграция 0107](https://github.com/chivkunovd-bitdenis/WMS/blob/065e23267f511dedc4c2d2ded24638acca8ce34f/backend/alembic/versions/20260825_0107_document_event.py#L71).

`OperationFact` записывается явными вызовами для определённых операций. Его writer проверяет принадлежность автора организации и сохраняет `actor_name_snapshot` из `User.email`. Произвольные изменения справочников он не отслеживает: [operation_fact_service.py](https://github.com/chivkunovd-bitdenis/WMS/blob/065e23267f511dedc4c2d2ded24638acca8ce34f/backend/app/services/operation_fact_service.py#L319).

**Конкретная карта покрытий и пробелов**

В предложениях ниже `before/after` обозначают ожидаемую структуру события, а не полученные из БД значения. Новых таблиц или параллельного журнала для них не требуется.

1. **Сотрудники: создание, права, упаковочная ставка — явные записи есть.**

   `/auth/staff-accounts` и `/auth/seller-staff-accounts` передают `acting_user` в сервисы. Создание сотрудника пишет `staff_user_created`; изменение прав — `permissions_changed`, с состоянием прав до и после; изменение ставки — `staff_rate_changed`, с `packaging_rate_kopecks` до и после. Автор — выполняющий действие пользователь, объект события — изменяемый сотрудник. В обновлении прав FF присутствуют блокировка строки и её перечитывание.

   Подтверждение: [staff_permissions_service.py:129](https://github.com/chivkunovd-bitdenis/WMS/blob/065e23267f511dedc4c2d2ded24638acca8ce34f/backend/app/services/staff_permissions_service.py#L129), [seller_staff_permissions_service.py:126](https://github.com/chivkunovd-bitdenis/WMS/blob/065e23267f511dedc4c2d2ded24638acca8ce34f/backend/app/services/seller_staff_permissions_service.py#L126), [staff_packaging_billing_service.py:195](https://github.com/chivkunovd-bitdenis/WMS/blob/065e23267f511dedc4c2d2ded24638acca8ce34f/backend/app/services/staff_packaging_billing_service.py#L195). Это подтверждение наличия writer в коде, с общей оговоркой о сбоях записи ниже.

2. **Создание селлера и основной учётной записи — пробел остаётся.**

   `POST /sellers` → `catalog_service.create_seller`; `POST /sellers/with-account` → `auth_service.create_seller_with_account`; `POST /auth/seller-accounts` → `create_seller_user`. В последних двух сервис знает `acting_user`, но после создания объектов коммитит их без события аудита.

   Минимальное дополнение — `DocumentEvent` непосредственно в этих функциях: `before=null`, `after={seller_id, target_user_id, role}` и разрешённые реквизиты созданной записи. Пароль, его хеш и данные приглашения в событие не включать. Места записи: [catalog_service.py:667](https://github.com/chivkunovd-bitdenis/WMS/blob/065e23267f511dedc4c2d2ded24638acca8ce34f/backend/app/services/catalog_service.py#L667), [auth_service.py:123](https://github.com/chivkunovd-bitdenis/WMS/blob/065e23267f511dedc4c2d2ded24638acca8ce34f/backend/app/services/auth_service.py#L123).

   Отдельно `PUT /auth/seller-shops` → `seller_shop_service.update_enabled_shops` сохраняет включение/отключение делегированных магазинов без события. Здесь минимальный `before/after` — набор включённых `seller_id`, объект аудита — пользователь: [seller_shop_service.py:110](https://github.com/chivkunovd-bitdenis/WMS/blob/065e23267f511dedc4c2d2ded24638acca8ce34f/backend/app/services/seller_shop_service.py#L110).

3. **Каталог товаров — обычные правки без автора; габариты покрыты отдельно.**

   `POST /products`, `PATCH /products/{id}/ozon-link`, `PATCH /products/{id}/packaging-instructions`, массовый `PATCH /products/requires-honest-sign/bulk` вызывают соответствующие функции `catalog_service`. Запись товара, связи Ozon, инструкции, страны происхождения и признака маркировки не сопровождается `DocumentEvent` или `OperationFact`. Массовый признак меняется прямым `UPDATE`.

   Минимальный writer — в `create_product`, `update_ozon_product_link`, `update_packaging_instructions`, `bulk_update_products_requires_honest_sign`: отдельное событие изменённого товара, с прежними и новыми значениями разрешённых полей. Для массовой операции сначала получить прежние значения и записывать только фактические изменения. Точные места: [catalog_service.py:709](https://github.com/chivkunovd-bitdenis/WMS/blob/065e23267f511dedc4c2d2ded24638acca8ce34f/backend/app/services/catalog_service.py#L709), [851](https://github.com/chivkunovd-bitdenis/WMS/blob/065e23267f511dedc4c2d2ded24638acca8ce34f/backend/app/services/catalog_service.py#L851), [935](https://github.com/chivkunovd-bitdenis/WMS/blob/065e23267f511dedc4c2d2ded24638acca8ce34f/backend/app/services/catalog_service.py#L935), [1216](https://github.com/chivkunovd-bitdenis/WMS/blob/065e23267f511dedc4c2d2ded24638acca8ce34f/backend/app/services/catalog_service.py#L1216).

   Ручные габариты и объём тары уже получают `user.id` и сохраняются в `ProductDimensionEvent`. Однако **`POST /products/{id}/dimensions/restore-wb` теряет пользователя**: `restore_latest_wb_dimensions` явно устанавливает `dimensions_updated_by_user_id=None` и создаёт наблюдение с `author_user_id=None`. Для этого ручного восстановления нужен `DocumentEvent` с габаритами/объёмом/источником до и после и автором нажатия. Источник самих размеров может остаться `wb`: [catalog_service.py:1162](https://github.com/chivkunovd-bitdenis/WMS/blob/065e23267f511dedc4c2d2ded24638acca8ce34f/backend/app/services/catalog_service.py#L1162).

4. **Склады и ячейки — изменения справочника не покрыты.**

   `POST/PATCH/DELETE /warehouses…` → `create_warehouse`, `rename_warehouse`, `delete_warehouse`; аналогичные операции с `/locations` → `create_location*`, `rename_location`, `delete_location`. Эти функции сохраняют создание, переименование или удаление без события справочника. Передача `actor_user_id` при удалении ячейки относится к сопутствующему перемещению остатков, а не к истории самой ячейки.

   Минимальный writer — в названных функциях `catalog_service`: `before/after` для `name`, `code`, `warehouse_id`, `deleted_at`; при физическом удалении сохранить разрешённые поля до удаления, `after=null`. Основание: [catalog_service.py:327](https://github.com/chivkunovd-bitdenis/WMS/blob/065e23267f511dedc4c2d2ded24638acca8ce34f/backend/app/services/catalog_service.py#L327), [410](https://github.com/chivkunovd-bitdenis/WMS/blob/065e23267f511dedc4c2d2ded24638acca8ce34f/backend/app/services/catalog_service.py#L410).

5. **Настройки организации — автор передаётся, но настройка не аудируется.**

   `PATCH /tenant/settings` → `tenant_settings_service.update_tenant_settings`. `actor_user_id` используется при переносе адресных остатков. Сами `address_storage_enabled`, `separate_marking_print_enabled`, `fbs_shipment_cutoff_time` присваиваются и коммитятся без события.

   Минимальный writer перед `commit`: `DocumentEvent` организации с `before/after` только изменённых настроек и проверенным пользователем. [tenant_settings_service.py:61](https://github.com/chivkunovd-bitdenis/WMS/blob/065e23267f511dedc4c2d2ded24638acca8ce34f/backend/app/services/tenant_settings_service.py#L61).

6. **Реквизиты и тарифы — версии данных есть, автора изменения нет.**

   `PUT /billing/profiles/ff`, `/profiles/sellers/{seller_id}` → `billing_configuration_service.save_profile`; `POST /billing/tariffs` → `create_tariff`; `PUT /billing/tariff-matrix` → `billing_tariff_matrix_service.save_tariff_matrix`; тариф хранения проходит через `storage_statement_service.create_storage_tariff` в ту же матрицу.

   Writer профиля присваивает реквизиты; writer тарифов создаёт версии, закрывает прежний период, переключает услуги и меняет `revision`. Эти записи не сохраняют действующего пользователя.

   Минимум — `DocumentEvent` в [save_profile:64](https://github.com/chivkunovd-bitdenis/WMS/blob/065e23267f511dedc4c2d2ded24638acca8ce34f/backend/app/services/billing_configuration_service.py#L64), [create_tariff:124](https://github.com/chivkunovd-bitdenis/WMS/blob/065e23267f511dedc4c2d2ded24638acca8ce34f/backend/app/services/billing_configuration_service.py#L124), [save_tariff_matrix:214](https://github.com/chivkunovd-bitdenis/WMS/blob/065e23267f511dedc4c2d2ded24638acca8ce34f/backend/app/services/billing_tariff_matrix_service.py#L214): разрешённые реквизиты до/после; для тарифов — идентификаторы версий, ставка, единица, период, включённость услуги и изменённая дата начала расчётов. Не сериализовать весь объект или входящий запрос.

7. **Счета — создание V2 имеет автора, отмена обеих версий не имеет.**

   `POST /billing/invoices-v2` → `create_invoice_v2` сохраняет `issued_by_user_id=user.id`. В старом `form_invoice` такого присваивания нет. `POST …/cancel` в обеих версиях вызывает функцию, которая меняет `issued → cancelled` без автора отмены.

   Минимальный writer: `DocumentEvent` в `form_invoice`, `cancel_invoice`, `cancel_invoice_v2`; при формировании `before=null`, `after={status, seller_id, period, amount}`, при отмене `before.status=issued`, `after.status=cancelled`. Автор формирования V2 не должен подменять автора отмены. [Старые счета](https://github.com/chivkunovd-bitdenis/WMS/blob/065e23267f511dedc4c2d2ded24638acca8ce34f/backend/app/services/billing_invoice_service.py#L590), [создание V2](https://github.com/chivkunovd-bitdenis/WMS/blob/065e23267f511dedc4c2d2ded24638acca8ce34f/backend/app/services/billing_invoice_v2_service.py#L677), [отмена V2](https://github.com/chivkunovd-bitdenis/WMS/blob/065e23267f511dedc4c2d2ded24638acca8ce34f/backend/app/services/billing_invoice_v2_service.py#L744).

8. **Акты расхождений — автор движения не покрывает жизнь акта.**

   `/operations/discrepancy-acts` → `discrepancy_act_service.create_act/add_line/delete_line/submit_act/approve_act/reject_act`. При утверждении `actor_user_id` передаётся в складское движение. Создание акта, состав и переходы `draft → confirmed → approved/rejected` собственного события с автором не получают.

   Минимальный writer в этих функциях: `DocumentEvent` акта; `before/after.status`, а для строк — `line_id`, `product_id`, `quantity` до/после. Существующие движения оставить самостоятельным фактом. [discrepancy_act_service.py:141](https://github.com/chivkunovd-bitdenis/WMS/blob/065e23267f511dedc4c2d2ded24638acca8ce34f/backend/app/services/discrepancy_act_service.py#L141).

9. **Приёмка — количество в таре покрыто, реквизиты и действия с самой тарой частично пропущены.**

   `scan/set quantity` коробов и грузомест вызывают явный `tare_line_qty_changed` с проверенным контекстом автора, идентификатором тары и количеством до/после. Это существующее покрытие: [inbound_intake_box_service.py:634](https://github.com/chivkunovd-bitdenis/WMS/blob/065e23267f511dedc4c2d2ded24638acca8ce34f/backend/app/services/inbound_intake_box_service.py#L634), [inbound_cargo_place_service.py:100](https://github.com/chivkunovd-bitdenis/WMS/blob/065e23267f511dedc4c2d2ded24638acca8ce34f/backend/app/services/inbound_cargo_place_service.py#L100).

   Пробелы: `PATCH /operations/inbound-intake-requests/{id}` → `patch_request_draft` меняет `planned_box_count`, `waybill_number`, которые сборщик не отслеживает; `set_line_storage_location` меняет ячейку строки без события; создание/удаление документа и пустого короба, закрытие короба и отметка печати не входят в автоматический перечень. `PATCH …/boxes/{box_id}/damaged` вообще присваивает `is_damaged` непосредственно в API.

   Минимальный writer на существующий документ приёмки: `before/after` соответствующих реквизитов; для тары — `container_id`, прежние/новые `is_damaged`, `intake_closed_at`, `label_printed_at` либо `null ↔ объект`. Места: [patch_request_draft:647](https://github.com/chivkunovd-bitdenis/WMS/blob/065e23267f511dedc4c2d2ded24638acca8ce34f/backend/app/services/inbound_intake_service.py#L647), [close_box_intake:673](https://github.com/chivkunovd-bitdenis/WMS/blob/065e23267f511dedc4c2d2ded24638acca8ce34f/backend/app/services/inbound_intake_box_service.py#L673), [API damaged:1452](https://github.com/chivkunovd-bitdenis/WMS/blob/065e23267f511dedc4c2d2ded24638acca8ce34f/backend/app/api/inbound_intake.py#L1452).

10. **Поставки на маркетплейс и обычные отгрузки имеют разные границы покрытия.**

   В `/operations/marketplace-unload-requests` изменения выбранных статусов, даты, склада и строк попадают в автоматический `DocumentEvent`. Однако `create_request/delete_draft_request`, создание/удаление коробов и `close_box` отдельного аудита не имеют. Минимум — события существующего `marketplace_unload` с `before/after` документа или короба: [marketplace_unload_service.py:147](https://github.com/chivkunovd-bitdenis/WMS/blob/065e23267f511dedc4c2d2ded24638acca8ce34f/backend/app/services/marketplace_unload_service.py#L147), [marketplace_unload_box_service.py:628](https://github.com/chivkunovd-bitdenis/WMS/blob/065e23267f511dedc4c2d2ded24638acca8ce34f/backend/app/services/marketplace_unload_box_service.py#L628).

   **Обычный `OutboundShipmentRequest` вообще отсутствует в автоматическом сборщике.** API `/operations/outbound-shipment-requests` → `outbound_shipment_service` создаёт документ/строки, меняет ячейку, дату и статусы; при отгрузке передаёт автора в складскую операцию. Минимум — явный `DocumentEvent` документа в этих writers, включая `draft → submitted` и переход в `posted`, со снимками изменённых полей. [outbound_shipment_service.py:287](https://github.com/chivkunovd-bitdenis/WMS/blob/065e23267f511dedc4c2d2ded24638acca8ce34f/backend/app/services/outbound_shipment_service.py#L287). Сами списания и резервы в этом протоколе не переоценивались.

11. **FBS-короба — добавление помечается пользователем, удаление уничтожает эту связь.**

   `POST …/boxes/{box_id}/orders` → `assign_orders` сохраняет `assigned_by_user_id` в `FbsPackingBoxItem`. Но `remove_order` удаляет строки, `clear_box` выполняет массовый `DELETE`, `delete_box` удаляет короб; собственного события об этих изменениях нет.

   Минимальный writer в [fbs_packing_box_service.py:442](https://github.com/chivkunovd-bitdenis/WMS/blob/065e23267f511dedc4c2d2ded24638acca8ce34f/backend/app/services/fbs_packing_box_service.py#L442): `DocumentEvent` FBS-поставки с `box_id`, идентификаторами заказов/позиций и принадлежностью коробу до/после. Запись должна переживать удаление `FbsPackingBoxItem`.

   В `set_boxes_without_distribution` включение сохраняет автора, **отключение очищает и автора, и время**. Минимальный `before/after`: включённость и прежние/новые значения этих полей, с отдельным автором текущего действия: [тот же сервис:273](https://github.com/chivkunovd-bitdenis/WMS/blob/065e23267f511dedc4c2d2ded24638acca8ce34f/backend/app/services/fbs_packing_box_service.py#L273).

12. **FBS-печать — подтверждение нанесения имеет автора, открытие файла его отбрасывает.**

   `POST /operations/fbs-print-assets/{id}/applied` → `confirm_asset_applied` сохраняет `applied_by_user_id`, для грузоместа также `qr_applied_by_user_id`. Это авторство существует.

   **`GET …/{id}/content` → `get_asset_binary_content` меняет `print_opened_at` и `order.sticker_status`, а переданный `user_id` явно не использует (`_ = user_id`).** Минимум — `DocumentEvent` заказа/поставки в этой функции на первое изменение: `asset_id`, `print_opened_at` и `sticker_status` до/после. Открытие файла не следует называть доказательством физической печати. [fbs_print_asset_service.py:991](https://github.com/chivkunovd-bitdenis/WMS/blob/065e23267f511dedc4c2d2ded24638acca8ce34f/backend/app/services/fbs_print_asset_service.py#L991).

13. **Упаковка — большая часть действий имеет события, `confirm-packed` является конкретным исключением.**

   `/operations/packaging-tasks` передаёт действующего пользователя. `_add_task_event` сохраняет `created_by_user_id`; ручная упаковка, сканирование и отметка «пришло готовым» дополнительно создают `OperationFact`. Отмена, завершение и печать товарной этикетки имеют `PackagingTaskEvent`.

   Но `POST …/lines/{line_id}/confirm-packed` → `confirm_line_packed_from_shelf` просто заменяет `qty_confirmed_packed` и вызывает `_touch_task`; этот вызов может также поменять `draft → in_progress`. События нет. Вызов `finalize_task_billing` этого не восполняет: он сразу возвращает управление, если задача не `done`.

   Минимум — `DocumentEvent` задания в `confirm_line_packed_from_shelf`, с `line_id`, `qty_confirmed_packed` и статусом до/после. Новую оплачиваемую операцию ради аудита создавать не требуется. [packaging_task_service.py:760](https://github.com/chivkunovd-bitdenis/WMS/blob/065e23267f511dedc4c2d2ded24638acca8ce34f/backend/app/services/packaging_task_service.py#L760), [finalize_task_billing:70](https://github.com/chivkunovd-bitdenis/WMS/blob/065e23267f511dedc4c2d2ded24638acca8ce34f/backend/app/services/staff_packaging_billing_service.py#L70).

14. **Маркировка — операции с кодом уже имеют журнал; настройки пулов и удаление из приёмки требуют дополнения.**

   Импорт, печать, применение пары и операции перепечатки используют `MarkingCodeEvent.actor_user_id`; заявки перепечатки дополнительно сохраняют `requested_by_user_id` / `resolved_by_user_id`. Это нельзя объявлять полностью непокрытым: [record_event:146](https://github.com/chivkunovd-bitdenis/WMS/blob/065e23267f511dedc4c2d2ded24638acca8ce34f/backend/app/services/marking_code_service.py#L146).

   `PUT …/pools/{id}/products` → `set_pool_products` заменяет связи товаров; `/threshold` → `set_pool_threshold` меняет пороги без автора. Минимум — `DocumentEvent` пула с наборами `product_id` до/после либо прежними/новыми порогами: [marking_code_service.py:866](https://github.com/chivkunovd-bitdenis/WMS/blob/065e23267f511dedc4c2d2ded24638acca8ce34f/backend/app/services/marking_code_service.py#L866), [2398](https://github.com/chivkunovd-bitdenis/WMS/blob/065e23267f511dedc4c2d2ded24638acca8ce34f/backend/app/services/marking_code_service.py#L2398).

   **`DELETE /operations/inbound-intake-requests/{request_id}/marking-codes/{code_id}` → `inbound_marking_service.delete_code` удаляет событие привязки `MarkingCodeEvent`, а в одной ветке и сам код. Автор удаления не передаётся.** Перед удалением нужен `DocumentEvent` приёмки: `before={code_id, line_id, attached:true}`, `after={code_id, attached:false}`. Сохранять идентификаторы, без полного содержимого кода. [inbound_marking_service.py:309](https://github.com/chivkunovd-bitdenis/WMS/blob/065e23267f511dedc4c2d2ded24638acca8ce34f/backend/app/services/inbound_marking_service.py#L309).

15. **Шаблоны печати — владелец шаблона не равен автору последней правки.**

   `/operations/marking-codes/print-templates…` → `print_template_service.create_print_template/update_print_template/delete_print_template/set_seller_label_options`. Поле `user_id` задаёт область шаблона и может быть пустым у шаблона товара/селлера. Правки `name`, `layout_json`, `is_default`, смена прежнего шаблона по умолчанию и удаление не создают события с автором.

   Минимум — явный `DocumentEvent` шаблона в этих функциях: `before/after` имени, разрешённых параметров макета, области и `is_default`; при переключении значения по умолчанию учитывать также изменённый прежний шаблон. [print_template_service.py:342](https://github.com/chivkunovd-bitdenis/WMS/blob/065e23267f511dedc4c2d2ded24638acca8ce34f/backend/app/services/print_template_service.py#L342).

16. **Чат и уведомления — создание в чате атрибутировано, повторные изменения истории не имеют.**

   Создание беседы, добавление участника, сообщение и вложение сохраняют соответственно `created_by_user_id`, `added_by_user_id`, `author_user_id`, `uploader_user_id`. `PATCH /operations/chat/messages/{id}` разрешён только автору, но `edit_message` перезаписывает `text` и `edited_at`: отдельные последовательные правки не сохраняются.

   Минимальное дополнение в [chat_service.py:421](https://github.com/chivkunovd-bitdenis/WMS/blob/065e23267f511dedc4c2d2ded24638acca8ce34f/backend/app/services/chat_service.py#L421) — `DocumentEvent` сообщения с автором, `changed_fields=["text"]` и `edited_at` до/после. Свободный текст сообщения автоматически копировать в аудит не следует: он может содержать чувствительные данные.

   `POST /operations/notifications/{id}/read` и `/read-all` → `notification_service.mark_read/mark_all_read` сохраняют только `read_at`, без того, кто прочитал. Минимум — событие фактически изменённого уведомления: `read_at: null → timestamp`, автор — текущий пользователь. [notification_service.py:193](https://github.com/chivkunovd-bitdenis/WMS/blob/065e23267f511dedc4c2d2ded24638acca8ce34f/backend/app/services/notification_service.py#L193).

**Пользовательские команды и системные изменения нужно разделить**

`POST /operations/background-jobs` и запуск перерасчёта хранения вызывают `create_pending_job`. Она сохраняет тип, состояние и параметры задания, но не инициатора. Минимальное дополнение именно здесь — `DocumentEvent` задания о пользовательском запуске: `before=null`, `after={job_type, status:pending, разрешённые идентификаторы области}`. Последующие `running/done/failed` — системное исполнение, с `source=system`; автора запуска нельзя выдавать за автора каждого полученного изменения. [background_job_service.py:33](https://github.com/chivkunovd-bitdenis/WMS/blob/065e23267f511dedc4c2d2ded24638acca8ce34f/backend/app/services/background_job_service.py#L33).

Есть и системный пересчёт внутри пользовательского GET: чтение задания упаковки вызывает `sync_mp_task_packed_from_boxes`, меняет `qty_packed_in_task`, а через `_touch_task` — статус. Минимальный writer такого сохранённого изменения — `DocumentEvent` с `source=system`, причиной пересчёта и количеством/статусом до/после. **Человек, открывший документ, не становится упаковщиком этих единиц.** Цепочка подтверждена в [API packaging_tasks.py:414](https://github.com/chivkunovd-bitdenis/WMS/blob/065e23267f511dedc4c2d2ded24638acca8ce34f/backend/app/api/packaging_tasks.py#L414) и [сервисе:653](https://github.com/chivkunovd-bitdenis/WMS/blob/065e23267f511dedc4c2d2ded24638acca8ce34f/backend/app/services/packaging_task_service.py#L653).

**Общие ограничения предложенных writers**

Для непокрытых объектов достаточно расширить разрешённые `document_type` / `event_type` существующего `DocumentEvent` и список принимаемых типов в API истории. Сейчас они ограничены пятью типами. Это изменение перечня событий, без новой таблицы или нового жизненного цикла: [модель DocumentEvent](https://github.com/chivkunovd-bitdenis/WMS/blob/065e23267f511dedc4c2d2ded24638acca8ce34f/backend/app/models/document_event.py#L19), [API истории](https://github.com/chivkunovd-bitdenis/WMS/blob/065e23267f511dedc4c2d2ded24638acca8ce34f/backend/app/api/document_events.py#L68).

Каждый writer следует размещать рядом с конкретным изменением, до его `commit`: брать `before` до присваивания/удаления, `after` из фактически сохраняемых данных, пропускать отсутствие изменений. Автор — проверенный `User` либо установленный им контекст. Содержимое события — явный перечень полей; без сериализации модели пользователя, паролей, токенов, заголовков и произвольного входящего запроса.

Две границы остаются незакрытыми даже у существующих writers:

- **Сохранение имени во времени.** `DocumentEvent` хранит ссылку на пользователя, а API берёт его текущий `email`; отдельного снимка имени нет. `OperationFact` такой снимок имеет. Для новых пользовательских `DocumentEvent` минимальный вариант без новой колонки — сохранять имя автора в разрешённом поле `payload_json` и использовать его при чтении истории. Историческое имя нельзя достоверно восстановить из сегодняшней учётной записи. [Формирование ответа истории](https://github.com/chivkunovd-bitdenis/WMS/blob/065e23267f511dedc4c2d2ded24638acca8ce34f/backend/app/api/document_events.py#L43).
- **Полнота при ошибке записи.** `record_document_event_safely`, автоматический `_write_rows_safely` и SQL-триггер перехватывают ошибки аудита и позволяют основной операции продолжиться. Поэтому наличие вызова writer ещё не гарантирует буквальное «каждое изменение сохранено» при отказе журнала. Это подтверждённое свойство кода, не результат испытания отказов: [явный writer](https://github.com/chivkunovd-bitdenis/WMS/blob/065e23267f511dedc4c2d2ded24638acca8ce34f/backend/app/services/document_event_service.py#L255), [автоматический writer](https://github.com/chivkunovd-bitdenis/WMS/blob/065e23267f511dedc4c2d2ded24638acca8ce34f/backend/app/services/document_event_service.py#L766).

**Граница этого протокола**

До конкретных мест записи проверены: actor/staff fixes, каталог и габариты, справочники складов/ячеек, настройки организации, реквизиты/тарифы/счета, акты, перечисленные реквизиты документов и операции с тарой, FBS-короба/открытие печати, обычная упаковка, указанные операции маркировки, шаблоны, чат, уведомления и запуск фоновых заданий.

Полным разбором не покрыты: складские остатки/резервы/инвентаризация/перемещения и stock-публикация соседнего среза; mobile; все ветви массовых импортов и объединения товаров; весь обмен метаданными и грузоместами WB/Ozon; возвраты Ozon; подписки и платежи; регистрация/восстановление доступа и интеграционные учётные данные. Наличие их API не засчитывалось как проверка writer. WMS-111/112, другой worktree и перечисленные служебные материалы не развивал.

**Оснований закрывать всю WMS-325 нет.** Для её продолжения теперь есть конкретные места добавления событий и ожидаемые изменения до/после; исправления, проверка исполнения и выпуск этим протоколом не выполнены.

