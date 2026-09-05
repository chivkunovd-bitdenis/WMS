# WMS-374 — независимое ревью всего боевого выпуска, Opus Max через CLI

Ты независимый ревьюер. Владелец просит проверить весь накопленный выпуск, код,
дыры и регрессии: «чтобы всё как часы работало в текущих процессах, в особенности
ФБС», «особенно что нет проблем с публикацией остатков». Нужен доказательный
разбор, а не одобрение реализации или пересказ тестов. Ответ на русском.

## Точная граница и режим

Репозиторий /Users/deniscivkunov/Projects/WMS. Старый production:
`c0dfaecae5985ac7a0597dc2acf56901ee242fe4`. Проверяемый production:
`ed72c8888a6e383f5101e0c1bd96d3793810e4fc` (PR183–187). Весь diff между этими
SHA, включая неозоновские изменения. 7734b63d — промежуточная большая сборка;
4306fa7e — последующие исправления; 4e11ce24 имеет то же дерево, что production.
Текущий HEAD может содержать только более новые документы ревью. Для кода
истина — замороженный target SHA, а не случайная текущая ветка.

Только read-only review. Не редактируй файлы, не коммить, не запускай деплой,
импорт заказов, синхронизацию остатков, резервирование, сборку или передачу.
Не вызывай внешние API, SSH, SQL, не открывай .env, секреты, токены или кабинеты
учётных данных. Не запускай фоновые агенты/другие модели. Не меняй тестовые базы.
Полный набор тестов уже прогонялся, не запускай его снова. Читай существующие
тесты и отмечай пробелы; точный необходимый воспроизводящий тест можно предложить
в отчёте. Нет браузерной сессии в этом CLI: не заявляй, что проверил UI руками.
Не делай вывод «всё работает на бою» по одному статическому ревью.

Доступны Read/Glob/Grep и разрешённые команды чтения git/rg/sed/nl/head/tail/wc.
Если инструмент недоступен, используй Read/Grep или явно укажи границу. Не
трать обзор на обход ограничений. Изучай код самостоятельно, включая неизменённые
вызываемые сервисы. Ни старый handoff, ни зелёный тест не доказывают отсутствие бага.

## Источники требований, которые нужно прочитать

1. AGENTS.md, CLAUDE.md — ограничения проекта. Новейшие прямые решения владельца
   ниже имеют приоритет над старым текстом в файлах.
2. docs/KANONICHESKIY_BACKLOG.md: WMS-374 задаёт полный разрез этого выпуска;
   обязательно целиком WMS-060 (все числовые примеры и уточнения), WMS-340..364,
   367..373 и соответствующие разделы отчётов/счетов/хранения/инвентаризации/печати.
   В файле местами остались старые «НА СТЕНДЕ», «на проде рубильник выключен» и
   старые абзацы «не написано» под уже выполненной задачей. Это исторические
   формулировки: проверяй актуальный код и приведённые здесь свежие факты.
3. docs/MVP_DECISIONS_RU.md — продуктовые границы и термины.
4. docs/HANDOFF_OZON_2026-09-05_RU.md — сначала верхнее продолжение после7d90d129,
   затем исходник. Старые утверждения о незавершённой раскладке и доверительной
   приёмке не заменяют новые решения. Старые ревью можно прочитать ПОСЛЕ своей
   проверки, чтобы не ограничиться повторением прежних находок.

## Принятые решения: не выдавать их за ошибки и не восстанавливать запрещённое

### FBS и остатки

- Текущие процессы WB должны сохраняться. Нет навигационных блокеров по подбору,
  упаковке, метаданным, стикерам и коробам. Нельзя возвращать оператора назад или
  вводить status==assembling → picking (в том числе под другим именем). Подбор,
  упаковка и галки — факты работы, а не разрешения открыть следующую вкладку.
- Проверки действительной передачи остаются на её границе: ответ маркетплейса,
  защита от повторного выполнения, единственное физическое списание, правильный
  товар/селлер/склад. Не предлагай убрать эти проверки под видом снятия блокировок.
- Нулевой/недостаточный остаток не должен скрывать заказ или сам по себе запирать
  отгрузку: принято предупреждение и подтверждение списания в минус. Проверь
  реализацию этой границы отдельно для WB и Ozon, не называй разрешённый минус
  самостоятельным дефектом. Не путать это с публикацией отрицательного или
  завышенного количества во внешнем кабинете: публиковать можно только допустимое.
- Поштучное выделение и процентный режим взаимоисключающие, проценты не заменяют
  ручные количества. Прочти WMS-060 целиком: фиксированная цифра оператора,
  доступность новым заказам, существующие резервы и физический остаток — разные
  понятия. 400 физически, 100+200 выделено: ФБО свободно100. Заказ на втором
  складе: доступно199, резерв1; сборка не списывает; передача: физически399,
  доступно199, резерв0; нельзя расходовать199 повторно. Отмена до передачи
  возвращает единицу на тот же FBS-склад; после передачи товар возвращается только
  фактическим документом возврата. Приход обычного товара сам не восполняет
  израсходованное поштучное выделение. Инвентаризация сначала тратит обычный
  свободный остаток, затем доступное выделение FBS, и сообщает это оператору.
- Старое общее правило AGENTS о min(числооператора, свободныйостаток) и более
  подробные поздние примеры WMS-060 содержат разницу терминов. Не выбирай молча
  удобный вариант и не восстанавливай исторический журнал расхода. Учитывай оба:
  публикация не превышает физически доступного, нет повторного вычитания резервов,
  история WB не «съедает» новую доступность; если остаётся противоречие требований,
  вынеси именно конфликт требований с цитатами, отдельно от доказанного бага.
- Сумма процентов/поштучных выделений проверяется по всем складам обеих площадок.
  Нельзя одновременно публиковать одно свободное количество несколько раз.
  Сохранение правила не должно включать выключенные товар/склад. Отключение,
  уменьшение, изменение привязки/режима не должны оставлять старый внешний остаток.
- Единицы оператора не уменьшаются на каждом упоминании заказа в API или обходе
  истории. Исторический регресс уже скрывал335 единиц: проверь особенно миграцию,
  старые заказы, повторные статусы, резерв/отмену/пересохранение и гонки.
- Нельзя «чинить» отмены автоматическим возвращением уже отгруженного физического
  товара. Финансовое сторно за отменённый заказ — отдельная операция WMS-361.

### Ozon: актуальные границы

- Выпускается ОБЫЧНАЯ приёмка. Доверительная приёмка явно исключена владельцем.
  Не считать отсутствие containers_count/этикеток грузовых мест невыполненной
  обязательной частью этого релиза. Чтение признака has_entrusted_acceptance из
  справочника не означает реализованный сценарий. Ozon на мобильном ТСД тоже вне.
- Физические короба WMS, упаковки заказов Ozon и грузовые места маркетплейса
  нельзя смешивать. Позиция заказа (товар+заказ) неделима и целиком в одном коробе;
  разные позиции одного заказа можно разнести по коробам; разные заказы Ozon в
  одном коробе нельзя. У WB заказ по-прежнему в одном коробе. Количество читается
  из FbsOrderProduct.quantity, не вводится вторым счётчиком.
- Сборка Ozon /ship выполняется при QR на упаковке, не повторяется при передаче.
  Дочерние номера/этикетки должны пережить ошибки/перезапуск; неподтверждённый ответ
  не успех. Передача через carriage/create/get/approve/документы. Не требовать
  обязательного set-postings: это ранее сознательно снято для обычного сценария.
- Рецепт источников списания готовится до внешней передачи, физические движения
  после подтверждения, ровно один раз. Существующий FbsShipmentReversalLedger
  здесь хранит рецепт/идемпотентность: не удалять из-за названия reversal или
  старых документов про запрещённый журнал расхода квоты.
- Каталог: один физический товар с привязками WB/Ozon. Автосвязка по однозначному
  штрихкоду/артикулу/собранному OZ+nmID+артикулу; неоднозначность (в частности размеры)
  не угадывать. Ручное объединение ровно двух карточек, одного селлера, остатки
  складываются с предупреждением. WMS-345 частична по авторазличению размеров.
- Импорт WMS-352 в автоматическом режиме по решению, зафиксированному в бэклоге,
  берёт только обслуживаемый склад и товар с включённой fbs_stock_sync_enabled.
  Сегодня владелец обнаружил, что выключенная трансляция мешает загрузить уже
  существующий заказ. Это уже известное продуктовое ограничение; он попросил
  «не переделывай пока, просто ответ». Не устраняй его и не выдавай за НОВУЮ находку.
  При этом ищи побочные ошибки текущего фильтра (состав, потери обновлений и т.д.).
- WMS-373: адресный selected_posting_numbers обходит только товарный флаг,
  сохраняет обслуживаемую привязку и точный список номеров; не включает публикацию.
  Владелец отменил ручной импорт до запуска: селлер обработал отправление в Ozon.
  Внешних мутаций по этому заказу агент не делал, был только read запроса деталей.
- Запрос существующих необработанных заказов не ограничен датой подключения:
  сейчас cutoff-окно ±30дней. Не объявляй поддержку всей истории завершённых
  заказов или всех схем Ozon — это не поставлено.

### Печать, UI, отчёты и деньги

- Frontend менять только по явным задачам; без новых колонок, бренда/шрифта или
  редизайна. Три подписи Ozon владелец отдельно одобрил; не требуй их откатить.
- Печатается фактический товарный штрихкод Ozon из ProductMarketplaceLink,
  не выдуманный OZN+SKU. Он отдельный от PDF отправления. У склеенного товара
  выбор WB/Ozon в существующем окне; WB поведение сохранено. При отсутствии
  товарного ШК смешанная ЧЗ+ШК печать должна отказать до расходования ЧЗ;
  только ЧЗ разрешён. Требования честного знака — из реального состава заказа.
- Конструктор состава этикетки WMS-210/211/часть212 вошёл в код, но на бою
  label_template_enabled=False. Это намеренно, не «забыли включить». При выключении
  шаблон не должен изменить ни один путь реальной печати.
- WMS-369 (разные формы количества/нельзя стереть0),371(пропуск одной этикетки),
  372(непонятное предупреждение WB) только записаны, не исправлены. Можно связать
  с конкретным кодом, но честно обозначить известный backlog, не новую регрессию.
- Хранение — одна суточная проводка/суточные начисления в полночь Москвы;
  экран и счета читают сохранённые начисления, не создают вторую арифметику.
  Литро-дни; ФБО/ФБС и услуги не смешивать. Упаковка тарифицируется по факту
  отгруженного количества; приход/возврат имеют свои услуги.
- В отчёте товар→движения→документ, начальный остаток на начало выбранного периода,
  фото и CSV согласованы с экраном. В счёте выбираемые операции+произвольные строки.
- WMS-010 частична (старые тарифы),011 защита двойного счёта не закрыта,
  013/025 ретроначисления не закрыты. WMS-012 исправляет даты новых начислений;
  не было доказанного пересчёта всех старых записей. WMS-021 вопрос состава раздела
  шире реализованного начисления упаковки. Не считай широкие задачи закрытыми.

## Свежие наблюдения оркестратора (не твоя собственная live-проверка)

На сервере прочитан SHA ed72c888, API/web/worker/beat запущены; health=ok.
Ozon live flag true; label template flag false. Миграции выпуска до0254 применены.
Основной пакет проверяли локальными тестами, затем отдельными адресными тестами
по найденным дефектам; это не сквозное доказательство работы всего production.
Ручная авторизованная проверка полного боевого FBS и физическая печать агентом
не завершены. Не заменяй эту границу словами «проверено тестами».
Предыдущее xhigh-review находило: публикацию выше физического остатка, зависший
pending передачи после restart, невозможность повторить ship_failed. Исправления
в4306fa7e, beat pickle lambda в734a059f. Проверь их заново независимо.
Известная граница восстановления: carriage/create мог выполниться, а ID не
сохраниться — без доказательства результата нельзя слепо повторять create.
Ручная сверка предусмотрена; оцени её практический эффект, не требуя рискованного
авторетрая. Данных для подтверждения реальной PG-конкурентности у прошлого ревью
не было. Различай доказанный кодовый баг и гипотезу, требующую воспроизведения.

## Что проследить обязательно

A. Публикация: UI сохранение → API → режим/привязка/served → единый расчёт →
   payload WB/Ozon → ответы по строкам/ошибки → повтор/нули/отключения. Несколько
   складов/площадок; отрицательный/нулевой остаток; резервы; конкурирующая правка;
   смена режима; уменьшение/отмена; округления; частичные ошибки API; stale external
   stock; миграции и фоновые задачи. Ищи завышение И необоснованное обнуление.
B. FBS: новый заказ → резерв → поставка → подбор → упаковка/QR → передача →
   списание → статус/отмена. WB и Ozon раздельно; многопозиционные заказы и quantity>1;
   транзакции/lock order; retry той же/новой idempotency key; рестарт на каждом
   внешнем шаге; внешний успех+локальный сбой; отсутствие новых навигационных
   блокировок; повторная обработка/старые заказы не расходуют доступность дважды.
C. Границы tenant/seller/warehouse/product; общие сервисы WB/Ozon/FBO; реальные
   несовпадения форм API и generatedschemas; frontend/backend contracts;
   печать/ЧЗ до необратимых действий; очереди/расписание/миграции.
D. Отчёты, счета, хранение, инвентаризация, печать из всего diff; изменения вне
   списка задач тоже обязательны. Отмечай проверенные части и непрочитанные зоны.

## Формат результата

Начни с вердикта риска для текущего production. Затем ТОЛЬКО доказанные находки
P0/P1/P2: короткий заголовок; affected file:line в target; конкретный сценарий
триггера/цифры; путь вызовов и последствие для оператора/товара/денег; нарушенное
принятое требование; новая регрессия vs уже существующий дефект (проверь baseline);
минимальное направление исправления без изменения принятых правил; нужный
адресный тест/проверка. Не фиксируй числа/причины без доказательства.
Отдельно: (1) известные ограничения/бэклог, (2) конфликты требований, (3) что
покрыто обзором, (4) что требует живой проверки, (5) какие прежние P1 подтверждённо
исправлены. Если находок нет, прямо укажи пределы; не обещай безошибочность.
Не ограничивайся первым багом, прочитай весь пакет по зонам риска. Не трать
отчёт на форматирование, вкусовщину и советы добавить новые блокеры/сущности.
Выдай полный отчёт в финальном ответе CLI; оркестратор сам сохранит его в Git.

## Полный перечень изменённых файлов целевого выпуска

```text
M	.github/workflows/ci.yml
M	.gitignore
M	AGENTS.md
M	CLAUDE.md
A	backend/alembic/versions/20260903_0249_binding_marketplace_unique.py
A	backend/alembic/versions/20260903_0250_inventory_created_containers.py
A	backend/alembic/versions/20260905_0252_fbs_available_stock.py
A	backend/alembic/versions/20260905_0253_merge_wms060_and_staging.py
A	backend/alembic/versions/20260905_0254_fbs_box_order_positions.py
M	backend/app/api/billing_invoice_v2_schemas.py
M	backend/app/api/billing_seller_report_schemas.py
M	backend/app/api/document_events.py
M	backend/app/api/fbs_errors.py
M	backend/app/api/fbs_marking.py
M	backend/app/api/fbs_orders.py
M	backend/app/api/fbs_sellers.py
M	backend/app/api/fbs_supplies.py
M	backend/app/api/inbound_intake.py
M	backend/app/api/inventory_counts.py
M	backend/app/api/marketplace_unload_requests.py
M	backend/app/api/marking_codes.py
M	backend/app/api/outbound_shipment.py
M	backend/app/api/ozon_integration.py
M	backend/app/api/ozon_returns.py
M	backend/app/api/products.py
M	backend/app/api/reports.py
M	backend/app/api/storage.py
M	backend/app/api/tenant_settings.py
M	backend/app/celery_app.py
M	backend/app/cli/reconcile_fbs_unlinked_shipments.py
M	backend/app/core/settings.py
M	backend/app/models/fbs_binding_stock_pool.py
M	backend/app/models/fbs_packing_box.py
M	backend/app/models/fbs_warehouse_binding.py
M	backend/app/models/inventory_count.py
M	backend/app/schemas/ozon_fbs_api.py
M	backend/app/services/billing_invoice_v2_service.py
M	backend/app/services/billing_ledger_service.py
M	backend/app/services/billing_seller_report_service.py
M	backend/app/services/billing_tariff_matrix_service.py
M	backend/app/services/catalog_service.py
M	backend/app/services/document_event_service.py
M	backend/app/services/fbs_autopoll_service.py
M	backend/app/services/fbs_cancellation_service.py
M	backend/app/services/fbs_cancelled_after_pack_service.py
M	backend/app/services/fbs_kiz_service.py
M	backend/app/services/fbs_marking_service.py
M	backend/app/services/fbs_order_billing_service.py
M	backend/app/services/fbs_order_history_service.py
M	backend/app/services/fbs_order_import_scope_service.py
M	backend/app/services/fbs_ozon_packaging_service.py
M	backend/app/services/fbs_packing_box_service.py
M	backend/app/services/fbs_picking_service.py
M	backend/app/services/fbs_print_asset_service.py
M	backend/app/services/fbs_print_asset_storage.py
M	backend/app/services/fbs_seller_warehouse_service.py
M	backend/app/services/fbs_shipment_pvz_service.py
M	backend/app/services/fbs_shipment_service.py
M	backend/app/services/fbs_shipment_source_service.py
M	backend/app/services/fbs_stock_availability_service.py
M	backend/app/services/fbs_stock_publish_service.py
M	backend/app/services/fbs_stock_rule_service.py
D	backend/app/services/fbs_stock_units_service.py
M	backend/app/services/fbs_supply_reconcile_service.py
M	backend/app/services/fbs_supply_service.py
M	backend/app/services/fbs_warehouse_binding_service.py
M	backend/app/services/fbs_worklist_service.py
M	backend/app/services/fbs_workspace_service.py
M	backend/app/services/inbound_intake_service.py
M	backend/app/services/inventory_count_service.py
M	backend/app/services/inventory_movement_report_service.py
M	backend/app/services/inventory_service.py
M	backend/app/services/marketplace_account_service.py
M	backend/app/services/marketplace_provider.py
A	backend/app/services/marketplace_scope.py
M	backend/app/services/marketplace_unload_service.py
M	backend/app/services/operation_fact_service.py
A	backend/app/services/ozon_box_assembly_service.py
M	backend/app/services/ozon_fbs_marking_gate_service.py
M	backend/app/services/ozon_fbs_process_service.py
M	backend/app/services/ozon_fbs_sync_service.py
A	backend/app/services/ozon_marketplace_transport.py
A	backend/app/services/ozon_product_import_service.py
A	backend/app/services/ozon_provider_factory.py
M	backend/app/services/ozon_return_service.py
M	backend/app/services/print_template_service.py
A	backend/app/services/product_merge_service.py
M	backend/app/services/reporting_service.py
M	backend/app/services/scan_resolver_service.py
M	backend/app/services/seller_wb_catalog_service.py
M	backend/app/services/stock_direction_service.py
A	backend/app/services/storage_daily_charge_service.py
M	backend/app/services/storage_statement_service.py
M	backend/app/services/warehouse_map_service.py
M	backend/app/services/wb_marketplace_orders_service.py
M	backend/app/tasks/billing_tasks.py
M	backend/scripts/backfill_billing_charges.py
A	backend/scripts/backfill_fbs_order_facts.py
M	backend/tests/conftest.py
M	backend/tests/test_billing_configuration_api.py
M	backend/tests/test_billing_invoice_v2_api.py
M	backend/tests/test_billing_seller_report_api.py
M	backend/tests/test_billing_seller_report_service.py
M	backend/tests/test_billing_storage_tariff_matrix.py
M	backend/tests/test_billing_tariff_matrix.py
A	backend/tests/test_celery_schedule_persistence.py
M	backend/tests/test_document_events.py
M	backend/tests/test_fbs_cancellations.py
M	backend/tests/test_fbs_operator_flow_models.py
M	backend/tests/test_fbs_orders_intake.py
M	backend/tests/test_fbs_ozon_lane.py
M	backend/tests/test_fbs_packing_box.py
M	backend/tests/test_fbs_pr140_shipment_write_off.py
A	backend/tests/test_fbs_print_asset_pdf_storage.py
M	backend/tests/test_fbs_review_fixes.py
M	backend/tests/test_fbs_shipment_source_service.py
M	backend/tests/test_fbs_stock_models.py
M	backend/tests/test_fbs_stock_publish_on_movement.py
M	backend/tests/test_fbs_stock_rule_service.py
M	backend/tests/test_fbs_stock_sync.py
M	backend/tests/test_fbs_supply_composition_service.py
A	backend/tests/test_fbs_supply_history.py
M	backend/tests/test_fbs_warehouse_binding.py
M	backend/tests/test_fbs_writeoff_sold_and_reversal_guard.py
M	backend/tests/test_inventory_counts.py
M	backend/tests/test_inventory_movement_actor_flows.py
M	backend/tests/test_marketplace_account_service.py
A	backend/tests/test_marketplace_scope_guards.py
M	backend/tests/test_marketplace_unload_completion.py
M	backend/tests/test_outbound_shipment.py
A	backend/tests/test_ozon_box_assembly.py
A	backend/tests/test_ozon_box_positions.py
A	backend/tests/test_ozon_cancel_posting.py
M	backend/tests/test_ozon_fbs_openapi_models.py
A	backend/tests/test_ozon_fbs_process_contract.py
M	backend/tests/test_ozon_integration_api.py
A	backend/tests/test_ozon_live_contract.py
A	backend/tests/test_ozon_marketplace_transport.py
A	backend/tests/test_ozon_operator_surfaces.py
A	backend/tests/test_ozon_posting_contract.py
A	backend/tests/test_ozon_product_import.py
M	backend/tests/test_ozon_return_service.py
M	backend/tests/test_ozon_returns_api.py
A	backend/tests/test_ozon_shipment_sources.py
M	backend/tests/test_print_templates.py
M	backend/tests/test_products_ozon_catalog.py
M	backend/tests/test_reports_csv_export.py
M	backend/tests/test_reports_inventory.py
A	backend/tests/test_reports_movements.py
M	backend/tests/test_reports_overview.py
M	backend/tests/test_stock_directions.py
A	backend/tests/test_storage_daily_charge.py
M	backend/tests/test_storage_measurement_service.py
M	backend/tests/test_storage_statement_matrix.py
M	backend/tests/test_storage_statement_service.py
M	backend/tests/test_storage_tariff_api.py
M	docker-compose.prod.yml
D	docs/ACTUAL_BACKLOG_RU.md
D	docs/BACKLOG-2026-08-19-CHAT-RU.md
D	docs/BACKLOG_EPICS_RU.md
D	docs/EXECUTION_PLAN_RU.md
D	docs/FBS_OWNER_TASKS_2026-08-31_RU.md
D	docs/FBS_TASKS_2026-08-31_REVISED_RU.md
D	docs/FBS_TASKS_BOXES_2026-08-31_RU.md
D	docs/GITHUB_ISSUES_BATCH_RU.md
A	docs/HANDOFF_OZON_2026-09-05_RU.md
D	docs/INVENTORY_OWNER_TASKS_2026-09-01_RU.md
D	docs/ITERATION_RUNBOOK.md
A	docs/KANONICHESKIY_BACKLOG.md
D	docs/MASTER_BACKLOG_RU.md
D	docs/NEXT_TASKS_RU.md
A	docs/OZON_SKVOZNAYA_REVIZIYA_2026-09-03_RU.md
A	docs/OZON_ZHIVAYA_PROVERKA_2026-09-03_RU.md
D	docs/PARALLEL_AGENT_TASKS.md
D	docs/PARALLEL_AGENT_TASKS_FBS_EMU.md
A	docs/PEREDACHA_2026-09-03_RU.md
A	docs/PEREDACHA_2026-09-04_NOCH_RU.md
A	docs/RAZBOR_KVOTA_FBS_2026-09-04_RU.md
D	docs/SVODNYY_BACKLOG_2026-09-02_RU.md
D	docs/TASKS_FOR_COMPOSER_RU.md
D	docs/WMS_ITERATION_BACKLOG_2026-08-14_FULL_RU.md
D	docs/ZADACHA_RASCHETY_I_SCHET_2026-09-02_RU.md
D	docs/ZADACHI-2026-08-21-RU.md
D	docs/ZADACHI-K-RABOTE-2026-08-21-RU.md
A	docs/ZADACHI_INVENTARIZACIYA_2026-09-03.md
D	frontend/fbs-history.html
M	frontend/src/App.tsx
M	frontend/src/components/MarkingLabelPreview.tsx
M	frontend/src/components/MarkingPrintDialog.test.ts
M	frontend/src/components/MarkingPrintDialog.tsx
M	frontend/src/components/ProductBarcodePrintButton.tsx
M	frontend/src/components/ProductBarcodePrintDialog.tsx
M	frontend/src/components/fbs/FbsChips.tsx
M	frontend/src/content/knowledge/08-tarify-raschety.md
M	frontend/src/screens/ff/FfBillingInvoiceCreate.tsx
M	frontend/src/screens/ff/FfBillingScreen.tsx
M	frontend/src/screens/ff/FfBillingSellerDetails.tsx
M	frontend/src/screens/ff/FfBillingTariffMatrixPanel.tsx
M	frontend/src/screens/ff/FfDashboard.tsx
A	frontend/src/screens/ff/FfLabelTemplatePanel.tsx
M	frontend/src/screens/ff/FfPackagingPage.tsx
M	frontend/src/screens/ff/FfReportsPage.test.tsx
M	frontend/src/screens/ff/FfReportsPage.tsx
M	frontend/src/screens/ff/FfSettingsScreen.tsx
M	frontend/src/screens/ff/FfStoragePage.test.ts
M	frontend/src/screens/ff/FfStoragePage.tsx
M	frontend/src/screens/ff/billing-sections-preview.tsx
A	frontend/src/screens/ff/inventory/FfInventoryCountScreen.test.ts
M	frontend/src/screens/ff/inventory/FfInventoryCountScreen.tsx
M	frontend/src/screens/ff/inventory/FfInventoryPage.tsx
M	frontend/src/screens/ff/inventory/InventoryCountDialog.tsx
M	frontend/src/screens/ff/inventory/InventoryTree.tsx
M	frontend/src/screens/ff/inventory/foundQueue.test.ts
M	frontend/src/screens/ff/inventory/foundQueue.ts
M	frontend/src/screens/ff/inventory/inventoryCountApi.ts
M	frontend/src/screens/ff/products-fbs/FbsStockDialog.tsx
M	frontend/src/screens/ff/products-fbs/FfProductsFbsPage.tsx
M	frontend/src/screens/ff/products-fbs/stub.ts
D	frontend/src/screens/v2/FbsOrderHistoryDialog.tsx
M	frontend/src/screens/v2/FbsPrintPreviewDialog.tsx
A	frontend/src/screens/v2/FbsSupplyHistoryDialog.tsx
M	frontend/src/screens/v2/FfFbsOrdersScreen.tsx
M	frontend/src/screens/v2/FfFbsStockSyncScreen.tsx
M	frontend/src/screens/v2/FfFbsSupplyWorkspace.test.ts
M	frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx
M	frontend/src/screens/v2/FfProductsCatalogScreen.tsx
M	frontend/src/screens/v2/SellerInboundDraftScreen.tsx
A	frontend/src/screens/v2/SellerSettingsScreen.test.ts
M	frontend/src/screens/v2/SellerSettingsScreen.tsx
D	frontend/src/screens/v2/fbs-history-preview.tsx
M	frontend/src/screens/v2/fbsApi.test.ts
M	frontend/src/screens/v2/fbsApi.ts
M	frontend/src/screens/v2/fbsUx.test.ts
M	frontend/src/screens/v2/fbsUx.ts
A	frontend/src/screens/v2/stickerCodeParts.test.ts
A	frontend/src/types/wbProductCatalog.test.ts
M	frontend/src/types/wbProductCatalog.ts
M	frontend/src/ui-kit/DataTable.tsx
M	frontend/src/utils/markingPrintPresets.test.ts
M	frontend/src/utils/markingPrintPresets.ts
M	frontend/src/utils/printMarkingCodeLabel.ts
M	frontend/src/utils/printTemplate.ts
M	frontend/src/utils/productBarcodePrint.test.ts
M	frontend/src/utils/productBarcodePrint.ts
M	frontend/src/utils/productLabelText.ts
M	frontend/src/utils/readApiErrorMessage.ts
M	frontend/src/utils/useFfProductMarkingPrint.tsx
M	frontend/vite.config.ts
A	scripts/ci/check-backlog-ref.sh
M	scripts/generate_ozon_fbs_api_md.py
M	scripts/generate_ozon_fbs_models.py
D	tasks/HANDOFF-28-08-VECHER.md
D	tasks/HANDOFF-catalog-move-20260818.md
D	tasks/KARTA-RABOT-28-08.md
D	tasks/PEREDACHA-V-NOVYY-CHAT.md
D	tasks/_zhurnal/HANDOFF-29-08-VECHER.md
D	tasks/_zhurnal/HANDOFF-30-08-DEN.md
D	tasks/_zhurnal/PEREDACHA-29-08-DEN.md
D	tasks/_zhurnal/PEREDACHA-KODEKSU.md
D	tasks/_zhurnal/REESTR-ZADACH.md
M	tasks/fbs-operator-flow/openapi/fbs-operations.openapi.json
M	tasks/ozon-integration-20260825/OZON_FBS_API.md
M	tasks/ozon-integration-20260825/OZON_FBS_OPENAPI.json
```
