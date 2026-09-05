# WMS-374 — завершить второй независимый обзор, Opus 5 Max

Новая CLI-сессия claude-opus-5, effort=max, продолжение ВТОРОГО обзора.
Прочитай REVIEW_2_BRIEF_RU.md и собственный REVIEW_2_RU.md. Требования и запреты
действуют. НЕ читать REVIEW_1*, ARBITER*, SYNTHESIS*, ORCHESTRATOR_EVIDENCE* и
scratchpad/wms374/*: чужие находки или актуальные данные тебе не передаются.
Только read-only, никаких правок, тестовых прогонов, SQL/API/SSH/секретов/субагентов.

Baseline c0dfaecae5985ac7a0597dc2acf56901ee242fe4 → production target
ed72c8888a6e383f5101e0c1bd96d3793810e4fc. Чтение текущего кода допустимо после
проверки совпадения с target; поздние документы не являются кодовым релизом.

В твоём отчёте список «не открывал вовсе» включает значительную часть выпуска.
Владелец запросил полный пакет. Уже проверенную публикацию повторно не гоняй;
закончи только пропущенные рабочие пути по diff, с чтением вызывающего кода и
целевых существующих тестов:
- billing_invoice_v2_service, billing_ledger_service, billing_seller_report_service,
  billing_tariff_matrix_service, storage_statement_service, reporting_service;
- inventory_count_service, api/inventory_counts, inventory_movement_report_service,
  operation_fact_service;
- print_template_service, fbs_print_asset_service, fbs_print_asset_storage,
  действующий общий frontend-путь печати, не legacyдиалог без монтирования;
- fbs_kiz_service, fbs_marking_service, api/marking_codes, api/storage, api/reports;
- fbs_order_history_service, fbs_packing_box_service, fbs_picking_service,
  fbs_workspace_service, fbs_worklist_service, fbs_supply_service,
  fbs_supply_reconcile_service, fbs_shipment_pvz_service;
- ozon_return_service, catalog_service, scan_resolver_service,
  seller_wb_catalog_service, inbound_intake_service, warehouse_map_service;
- docker-compose.prod.yml, .github/workflows/ci.yml, остальные изменённые миграции;
- изменённые реальные frontendэкраны FBS, отчётов, хранения, инвентаризации,
  селлера и печати. Не заявлять браузерную проверку по чтению кода.

Не требуется бессмысленное чтение каждой строки generatedOpenAPI. Нужна карта
покрытия всех изменённых productionпутей. Результат — дополнение к своему отчёту:
новые доказанные находки R2-A1...; явные коррекции собственных номеров; таблица
покрытия; честные оставшиеся границы. Оригинал не редактировать, ответ stdout,
оркестратор сохранит оба ответа в одном документе и полную видимую историю.

Уточни строгость собственных выводов без новых живых проверок:
- Положительное число товаров в предложенном SQL означает достижимость сценария,
  а не доказательство принятия Ozonнулей/потерянных продаж. Применённая миграция
  не доказывает ошибку на конкретной строке без до/после. Исправь такие утверждения.
- «Прод работоспособен по WB» не может быть итогом частичного статического чтения.
- Не объединяй разные проблемы только потому, что одна усиливает другую:
  блокировка следующих batch при отклонённой строке может существовать и при
  150 корректно настроенных товарах. Проверить вывод «одной строкой исчезнет всё».
- Ограничение процента и поштучное выделение, известные ограничения, конфликты
  требований и реально доказанные регрессии держать раздельно. Не вводить новые
  навигационные блокеры или менять принятые правила.
