# WMS-375 — Git-манифест полного выпуска на production

Дата среза: 06.09.2026. Приложение к [полному хэндоффу](HANDOFF_WMS375_PRODUCTION_2026-09-06_RU.md).
Это снимок Git, не отдельный бэклог и не утверждение о проверке каждого файла.

База: `c0dfaecae5985ac7a0597dc2acf56901ee242fe4`.
Итоговая версия приложения: `1491fcb31ebe30516bf77044dea01a3a8e90aef3`.
Всего **309 изменённых путей** и **162 коммита** в диапазоне.
Документация PR #190, включая это приложение, находится после итогового application SHA.

## Как воспроизвести

```sh
git diff --name-status c0dfaecae5985ac7a0597dc2acf56901ee242fe4 1491fcb31ebe30516bf77044dea01a3a8e90aef3
git rev-list --count c0dfaecae5985ac7a0597dc2acf56901ee242fe4..1491fcb31ebe30516bf77044dea01a3a8e90aef3
git log --reverse --format='%H %s' c0dfaecae5985ac7a0597dc2acf56901ee242fe4..1491fcb31ebe30516bf77044dea01a3a8e90aef3
```

## Все изменённые пути

A — добавлен, M — изменён, D — удалён. Удаления старых документов не являются
удалением одноимённых пользовательских функций. Для содержания читать сам diff.

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
M	backend/app/models/product.py
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
M	backend/app/services/fbs_order_tape_print_service.py
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
M	backend/tests/test_fbs_order_tape_qr_only.py
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
A	backend/tests/test_ozon_delivery_confirmation.py
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
A	backend/tests/test_ozon_stock_binding_cleanup.py
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
A	docs/reviews/2026-09-05-opus-max-release/A08_RECONCILIATION_METHOD_RU.md
A	docs/reviews/2026-09-05-opus-max-release/A08_RESULT.json
A	docs/reviews/2026-09-05-opus-max-release/A29_CHECK_RU.md
A	docs/reviews/2026-09-05-opus-max-release/ARBITER_BRIEF_RU.md
A	docs/reviews/2026-09-05-opus-max-release/ARBITER_HISTORY.jsonl
A	docs/reviews/2026-09-05-opus-max-release/ARBITER_METADATA.json
A	docs/reviews/2026-09-05-opus-max-release/ARBITER_VERDICT_RU.md
A	docs/reviews/2026-09-05-opus-max-release/BRIEF_RU.md
A	docs/reviews/2026-09-05-opus-max-release/FIX_VALIDATION_RU.md
A	docs/reviews/2026-09-05-opus-max-release/ORCHESTRATOR_EVIDENCE_RU.md
A	docs/reviews/2026-09-05-opus-max-release/OZON_BROWSER_RESULT.json
A	docs/reviews/2026-09-05-opus-max-release/PRODUCTION_VERIFICATION.json
A	docs/reviews/2026-09-05-opus-max-release/REVIEW_1_CONTINUATION_BRIEF_RU.md
A	docs/reviews/2026-09-05-opus-max-release/REVIEW_1_HISTORY.jsonl
A	docs/reviews/2026-09-05-opus-max-release/REVIEW_1_METADATA.json
A	docs/reviews/2026-09-05-opus-max-release/REVIEW_1_RU.md
A	docs/reviews/2026-09-05-opus-max-release/REVIEW_2_BRIEF_RU.md
A	docs/reviews/2026-09-05-opus-max-release/REVIEW_2_CONTINUATION_BRIEF_RU.md
A	docs/reviews/2026-09-05-opus-max-release/REVIEW_2_HISTORY.jsonl
A	docs/reviews/2026-09-05-opus-max-release/REVIEW_2_METADATA.json
A	docs/reviews/2026-09-05-opus-max-release/REVIEW_2_OUTPUTS.json
A	docs/reviews/2026-09-05-opus-max-release/REVIEW_2_OUTPUTS/1e10c9a9fa40-ba7i9jw3o.txt
A	docs/reviews/2026-09-05-opus-max-release/REVIEW_2_OUTPUTS/4f17986acd97-bptw7akyq.txt
A	docs/reviews/2026-09-05-opus-max-release/REVIEW_2_OUTPUTS/9cc3611b8a04-bs9nn1v1a.txt
A	docs/reviews/2026-09-05-opus-max-release/REVIEW_2_OUTPUTS/cc63e8c5c28c-bxqkgv6qn.txt
A	docs/reviews/2026-09-05-opus-max-release/REVIEW_2_OUTPUTS/e130ab7e3520-bcbxzlhou.txt
A	docs/reviews/2026-09-05-opus-max-release/REVIEW_2_RU.md
A	docs/reviews/2026-09-05-opus-max-release/SYNTHESIS_RU.md
A	docs/reviews/2026-09-05-opus-max-release/a08_reconcile_snapshot.py
A	docs/reviews/2026-09-05-opus-max-release/a29_probe.py
A	docs/reviews/2026-09-05-opus-max-release/local_ozon_browser.py
A	docs/reviews/2026-09-05-opus-max-release/printing/PROTOCOL_RU.md
A	docs/reviews/2026-09-05-opus-max-release/printing/generate-print-evidence.ts
A	docs/reviews/2026-09-05-opus-max-release/printing/wms371-product.html
A	docs/reviews/2026-09-05-opus-max-release/printing/wms371-product.pdf
A	docs/reviews/2026-09-05-opus-max-release/printing/wms371-tape.html
A	docs/reviews/2026-09-05-opus-max-release/printing/wms371-tape.pdf
D	frontend/fbs-history.html
M	frontend/src/App.tsx
M	frontend/src/components/MarkingLabelPreview.tsx
M	frontend/src/components/MarkingPrintDialog.test.ts
M	frontend/src/components/MarkingPrintDialog.tsx
A	frontend/src/components/PrintQuantityField.test.tsx
A	frontend/src/components/PrintQuantityField.tsx
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
A	frontend/src/screens/ff/products-fbs/fbsWarehouseRuleKeys.test.ts
A	frontend/src/screens/ff/products-fbs/fbsWarehouseRuleKeys.ts
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

## Полная история диапазона, от ранних коммитов к поздним

Сюда включены merge-коммиты и промежуточные реализации. Формулировка старого
коммита не заменяет итоговый код: некоторые ранние подходы позднее заменены.
Часть старых коммитов не содержала WMS-NNN; их файлы всё равно включены в область
релиза и проверки.

```text
4920e7fa8801a9e3b6d2bf89c4b044ffad313384 feat(фбс): история заказа открывается из состава поставки
a1f647f46dc3be02de9302f74f6ba9e33a5dd051 fix(расчёты): в разделе FBS только заказы
1de65b650829a4af4ed95691a6a6ba039fe305b3 fix(фбс): в истории заказа только его собственные события
88a2d40e38bc69d927440b31953a134c5ee45531 feat(фбс): история поставки вместо истории заказа
08168504183a3493ea9f124e1954d31d0ce95b41 chore(fbs): снимок OpenAPI знает про историю поставки
fbd16f650e1247c8b21eeb4021535d99557189ba fix(фбс): событие без подробностей больше не гасит экран
fa35404d021b6761d1b69db778f5449a9990e45d feat(биллинг): упаковка начисляется по факту отгрузки товара
f34d83bda96d508662f2ee27d9763baaf15f544e feat(биллинг): возврат начисляется по своей услуге, а не как приёмка
b2a72e9aa0e8905185d909c48fffdc9708f0e5d1 fix(фбс): в истории поставки нет технических слов и повторов
48b21f44e21d77d3aa520e13d0a10dfd3fe2c973 feat(тарифы): убрана единица «за документ» — считаем штуки
3a81bf799d235fe9b943d1047cd89d2857e8b1cb feat(отчёты): движение товара видно до документа
098a9e9ce847c82318743588747c1891d236bb2e feat(хранение): ночное начисление литро-дней вместо ручного месяца
b64c75a4b4dfc6d7997f725a8978237989d72993 fix(отчёты): «Нетто» ушло и из верхней панели
0e293466cbb7e977b285f513779176f6038c85c4 feat(хранение): убраны ручные «Сформировать за месяц» и «Зафиксировать»
84498b069d006e4d9cfa24dbcdd35aa6c0a2f75b fix(отчёты): плашка убрана, цифры сходятся, колонки не слипаются
b880caac46ba6db92f67ac605637369c6f5fedb8 test(тарифы): тесты матрицы переведены со «за документ» на «за штуку»
479797e72b328d1afe9ccea831167822c84b9151 fix(отчёты): у списания FBS виден заказ, а не пустая клетка
bc43d9797fecba6634ecafe54b00cb607b45f4e2 feat(фбс): кнопка «История поставки» на любом этапе
bde9e6600c0a0184426ffaac79f7932cc2df0ae7 fix(хранение): подзаголовок экрана больше не обещает фиксацию месяца
b901cb37ffaf71394828b05192d8bfc0e03d5b00 Merge branch 'worktree-agent-aac1121ec92f0bb12' into fix/inventory-scan-scroll-container
d7be16b50d80bca4216df6489f101f15256c1f5b fix(отчёты): фильтры «Склад» и «Селлер» перестали быть огрызками
748fc93dc4c75f4fb8e13c2b30e4df94463d4205 feat(хранение): один источник правды — ночное начисление
936189896e3bee2e950a60d348de8eefc5b31ae5 chore(тесты): убран импорт, осиротевший после перехода на ночное начисление
f9a95c16fbe54a4247243712d0b096b32a6db721 feat(хранение): экран показывает ночные начисления, а не считает сам
74de44ff7835c186b789065145513b1e03a8a031 test(хранение): проверяем экран через ночь, а не через снесённый расчёт
82d3b1eede24af6d787883d89d4a27ef67ad8bff fix(хранение): экран принимает прочерк там, где ночь ещё не начисляла
8a763eab197f806e0260f4245100ae64b65ff03e test(отчёты): панель без «Нетто» и с начальным остатком
bdcce653af524436cab7dea7bd012cdc927c8cc9 docs: передача по сессии 03.09.2026
9fa78f688f42e3e29beccdd3e9877cbcf3f951e3 fix(расчёты, отчёты): двенадцать дыр изолированного ревью
6689bdd5f99eda957719deb1bd5e84fba41e349f docs(ozon): живая проверка кабинета боевым ключом
5cc87477869cecf98d7ca5bd4a3bbea35094c4f7 fix(расчёты): правки по второму изолированному ревью
af9b157ac5ce813c1c9201a736fc32b1decbaf5e fix(ozon): модели не собирались с настоящей датой — проверено живым кабинетом
7615f151ef10e8537e2b00538e4c450a1b497638 docs(ozon): сквозная ревизия системы и вычистка ключей из передачи
5bc09a9e6110a5dcd56e5a7b49c1565841673034 feat(ozon): боевой транспорт и один выключатель вместо десяти фейков
a67e75f6a7a904ba1eb1d04f4bab1df11a60a30c fix(ozon): разбор отправления по спецификации, а не по тестовой фикстуре
dbe4c4e1610587139c3f341b3022811d89dfd7a4 feat(ozon): каталог, сканер, деньги и подписи — то, чего у товара Ozon не было
13ddb20b9fb6babce3d1a4540e662dca536361fa fix(ozon): границы и подписи, которые на озоновской ветке врали оператору
7ada36ce0a1fbd3f9b066d58c23c223d8732a12e feat(ozon): привязку склада Ozon наконец есть откуда завести
a9953f41cb0d48fd818186675e3559f55d692e37 fix(fbs): числовой ключ склада перестал быть уникальным сам по себе
f5352f3df6bfbe27291ad88e168b6a2dd3a90b36 test(ozon): привязка и разбор отправления проверены как одно целое
39925146c2d4a4fc10bc6738d284960d7bb30e96 fix(fbs): операция над документом Ozon больше не уходит в кабинет WB
6ff31991444929871a14926e1989a9c5f2488d65 merge: боевой транспорт Ozon, каталог, разбор отправления и привязка склада
0067039db0857d52f22742dd65083bdb109555a1 feat(счёт): к выбранным операциям можно дописать свою строку
d8e7edb85cfd2e9fbde9761e25f5d3dbd3b14821 feat(фбс): номер стикера видно на упаковке, хвост — крупно
10adfd9c1a1c8592ee0d6f3cccb3f002fb2b8ebe test(честный знак): лента расхода Ozon показывает номер упаковки, не wb_order_id
a75e01442adb522a7a3ebbfea8911c7401c8f6c7 fix(отгрузка): убрать мусорную подпись «Wildberries» у заявки на списание
9f6e72b507acde53dc2217ee0dcc8ad2de054ecd feat(ozon): публикация остатков уходит в кабинет, а не отказывает
598974e6d8914b2825eddcc2ebb460755c3d1faa fix(инвентаризация): кнопка «Создать короб» кладёт тару в документ
436e6a4b3229679313a55458198f7b93b154c949 merge: лента ЧЗ проверена, мусорная подпись маркетплейса убрана
7af7f0beed32c3dc2345d5e1f2724cca1f7a5cfd feat(ozon): этикетка отправления доезжает до оператора документом PDF
69bfddb95c9fb02b8fd509cd9c6a023369d4536b feat(ozon): отмена отправления уходит в кабинет Ozon, а не отказывает
d2079e73bb95069ec7102ef10efaa0928471e6d5 feat(инвентаризация): выделение строки — «мы сейчас здесь»
df509949d2945dc40b87d057cbfeb0f02396ba1d feat(инвентаризация): кнопка «Добавить товар» — ручное добавление по каталогу
ff5b308bcab3900019dfb257ec671a3243c7b8f8 fix(ozon): отгрузка на маркетплейс завершается, а не висит в «собирается»
1fc9f707a51b81c5e3f07cb2d0e6b4093b3338c6 fix(ozon): печать этикеток не выдаёт молчание фейка за ответ Ozon
ebd7a0d75d143b3b7ad43b67942abae33dde65e9 chore: убрать из гита symlink на общее окружение Python
0cc6ef195cec936e09d8221b4d21d69282f8c804 feat(ozon): экран синхронизации называет причину отказа Ozon по остаткам
00bf09155026e46a1ed832b990968a8ad92656e9 merge: инвентаризация — своя тара, выделение строки и добавление товара
d0e9a498a5039cdf7a12117e1c3a470fc0218556 feat(печать): состав этикетки закрепляется за селлером
f118ca682efae1812ed170e873730d6363e67977 fix(тесты): убрать отставший аргумент ozon_provider у завершения отгрузки
9d798c4f2966a35624e2bdf6a839f798e869d9be merge: Ozon доведён до включаемого состояния
7bb63267e2637a106d3d3c92081c9599ad83968a feat(печать): экран, где состав этикетки закрепляют за продавцом
62700cc579c86be5163c5ac2fe19d89ce45769b6 fix(печать): две регрессии по Wildberries, найденные ревью
3a74658c6482901b7f771e8279001b7bc6a66f67 feat(печать): каталог печатает этикетку по настройке продавца
f7fffd4eae0a26d5a358866aad3079d05798df33 fix(ozon): передача поставки запоминает уже сделанное в кабинете
3ed546404f619245611ce0961374a297d4320ade fix(ozon): остаток считается опубликованным только по строке ответа Ozon
50bbf4c8d63ef0b4c307951ebafc008988e2509d fix(ozon): отмена не расходится с кабинетом и берёт причину из вызова
bb544124c2d24c0af0fe8f24bf8a14355c37bf33 fix(ozon): опрос статусов берёт порцию живых заказов, а не всю историю
e528d0f03d6adbd7544359309a4b0553550bf05a fix(ozon): повтор передачи не запирается статусом ушедшего вперёд отправления
49f510c0da8ddd4d689a370077a7eee7fdfdc9a3 merge: четыре находки ревью по Ozon, включая два критичных
4b5edcc022fa7c7a26c428ed01f5221ed14984e4 docs(инвентаризация): постановка владельца по трём доработкам экрана
e2a603306a7ac903673a6b602a7c453a9122f33b fix(печать, хранение): пять находок полного ревью
0fd56c5ee71aabaffba97499040685101ce09da9 fix(инвентаризация): скан больше не стирает введённое и не уходит в чужой документ
28607f3e6d9e74a188faef24813b6e546e90627f fix(печать, хранение, инвентаризация): находки изолированного ревью
b737b465f6c9f25117af2e0677f0e57af7e66120 fix(печать): шаблон состава не распоряжается лентой печати
bd30b884c041c3285311cf7648d2bd156ee3d9b5 fix(печать, счёт, ФБС): восемь находок финального ревью
b329168927aca70cdff4aa1ab4b3b7c9349d6c96 docs: передача по ночной работе 04.09.2026
89b0c62d4aad8126ed01536297e88a8c15dea22e feat(печать): рубильник сборки для состава этикетки, по умолчанию выключен
21a7b96397880328099cf6a0e3b0e6eaddab87ad fix(печать): с выключенным рубильником состав не применяется ни одним путём
1d24feca609eb7245470ac45496b0dcfb5e7e371 fix(расчёты): откат моей самодеятельности с подбором и две правки по отчёту
df2b2f90ccd4c997c7c931d3775722ed8cffce63 docs: второе главное правило — никакого оверинжиниринга
81779bfbad7f86f024eb9b9d6a4bae180b194920 fix(фбс, остатки): число оператора — потолок, а не счётчик
6a1a4a45ff250d48872b9494572ba32484ab917a docs(бэклог): единый канонический список задач вместо 29 разрозненных
c6fdfbdbfa7e3889ba130a6dcd4a73e068833399 docs(бэклог): назвать список каноническим, чтобы агенты не искали другой
4cf13725a36227673c7effeab940f1190dee8bc9 docs(ci): поправить имя бэклога в комментарии гейта
b8c88baf68a87046688aeb6ab887743ddf17577e docs(бэклог): снять ложный пункт про упаковку в WMS-122
97058c5f22e7d694a42fba5b133bdacde166b3f0 docs(бэклог): снять WMS-017 — карточка не может сменить продавца
36141e9c7049934849f3a5afccdc9806e50f5f28 fix(фбс, остатки): расход числа считаем по заказу, а не по упоминанию от WB
017da79e04cef045fe85ae2b661538fabab645d2 docs(бэклог): WMS-133 — прятать пустые поставки, а не черновики
afb285a82c8724237a4c7e9ac39974296ff74358 docs: add WB supply visibility investigation [WMS-326]
ef7bdbbe814e809816324b409fe56263207414a4 docs: record WB order visibility findings [WMS-326]
021b8c5082ef6da7e5b34c15bb5598ebbfd09f9e docs: record Fadin order age audit [WMS-327]
1b7d3fd3e3c47bbdbbe4adf8505839943ed8dd63 docs: record per-order Fadin audit [WMS-327]
c7b5ed95ef44729b1dff50b371a6f1e8a05680f7 docs(бэклог): WMS-328 — в отгруженных дата плановая вместо реальной
9108ce2e0ee214b4131eddb1e96cef58c78272cb docs(бэклог): причесать по итогам сверки тремя агентами
418432b880406473be944d07370ab4932f84d6ab docs(бэклог): вписать квоту остатков ФБС, раздел 13
5bd647a5d6be75c9add47d353eabdd33c2a96a9b docs(бэклог): исправить WMS-111 — возврат Wildberries есть
d21a6dfe58e44c8a48022b0184a352525f6c5602 docs: WMS-060 record owner requirements for FBS allocation and percentages
f50b48ec252d91130c3f17be765f73fce60d2a47 docs(бэклог): WMS-339 — мобилка под процессы, дизайн вместо «1С»
ff204fe44da7cc868b9f23d8933175d60103d9fc docs(бэклог): подсветка при проведении инвентаризации в WMS-060
0487aa49f6ef9d87e4d417dc7ca62b3f3c8a1ed8 docs(бэклог): семь задач по склейке карточек WB и Ozon [WMS-340..WMS-346]
9ebe49d30350c237bc3f1eb2f8cbf3bd243af125 docs(бэклог): постановка владельца по Ozon целиком [WMS-347..WMS-354]
8a2eeb1bbe6158b1975dfac15494b117f8154db7 docs(бэклог): у Ozon нельзя класть разные заказы в одну коробку [WMS-354]
03eb057ae7e4a46f344eba0eee6c0e847e4d9399 docs(бэклог): ТЗ на выделение ФБС по модели владельца
fb691a01d5e34d586493a5539f683af417e892aa docs(бэклог): заказ Ozon нельзя разложить по коробкам [WMS-355]
8220f1950985b1633ed80fbf2c551826598a5f7a WMS-060: unify FBS allocation and order reservation operations
7deaa194b9942bb633649f70c744cec2e631a7e5 docs(бэклог): короба, количество и порядок этапов для Ozon [WMS-355]
03991332dc86cdc82926ce9f4c31593d3c42a551 docs(бэклог): у Ozon есть короба — доверительная приёмка [WMS-356]
9e1fc1434775ffd8500057cf2144cb45b06d0e43 docs(бэклог): модалка коробов по заказам и Честный Знак Ozon [WMS-355, WMS-356]
4fbc83e5ff9d6142e6b9566f86cf3abaae07d451 WMS-060: complete inventory deduction feedback and FBO stock display
4cf3d0d9c6bbbad8e775ade186d5858fee07016d docs(бэклог): требования владельца к модалке раскладки по коробам [WMS-355]
3e3d9255c11b517263c50ee152182ab5675e39c2 docs(бэклог): перенос сборки на упаковку и маршруты сдачи Ozon [WMS-357, WMS-358]
a49a81aa721ee83157db7d7d760fc79f30046da3 merge(ozon): свести ветку остатков WMS-060 и линию стенда
8ad47eccc551336f95edf219309c7a9894b7dba5 docs(бэклог): шесть задач из аудита и добора спеки, четыре поправки
d910e972fe4f8aba92b01bf2e2b93f50299222a2 feat(ozon): честный статус подключения и сторно за отменённый заказ
11ce694965b4baf24d42bf6fabe720e5f2850b89 docs(бэклог): WMS-346 и WMS-361 выполнены
cf0411f2cc5918f81ee710d09edcddd973b2b616 fix(ozon): снять навигационные блокеры, оставшиеся живыми только для Ozon
ae68544e2f3c9ba4e364c8f8d1d8f1204ff0d356 feat(каталог): значки площадок и ручное объединение двух карточек
45d73842908bb16e16e965b6ed7cc7ad6c8dfc82 feat(ozon): каталог приезжает сам, карточки связываются по трём признакам
450c6f8d850b0c28d249e4fe792133ba44a58a57 docs(бэклог): статусы по принятым дорожкам
6f9af13e609385fab7410de80a4780e0b731225e feat(остатки): второй ползунок Ozon и общий потолок в сто процентов
eb666d5073ccc986eb7f8a9b45a393109b287cc5 feat(ozon): опрос по выставленному остатку, маршруты сдачи и кнопка отмены
d7c11a188b35c3872a7fafb25f3108b2452074db feat(ozon): фото озоновского товара доехало до экранов
c2a855c1d075f7c3b7f29aec409598b59729a488 feat(ozon): справочник складов кабинета и признак доверительной приёмки
3afc564571763bbc5ecbc1e5626782a87b21e11e docs(бэклог): статусы остатков, фото и справочника складов
0f48a7b77e0fc161d90ea64f62a6ef42507e8422 docs(бэклог): WMS-355 переписана по уточнению владельца
12a3d87f3f191a294c88c76c2c9df26ff53afeae feat(ozon): склад кабинета включается из окна, без двойника на Wildberries
5d89a663b6b9a3418099d93e7f8832edf433fc0c fix(фбс): в отчёте по отменённым видны все короба заказа, а не последний
7d90d129c3f35512a84581e914bc5cd3096eae07 docs: передача по работе над Ozon 05.09.2026
7734b63de4d2e81ef633cb4a907b4d727ff3c8a0 feat(ozon): WMS-355 WMS-357 сборка по коробам и безопасная передача; WMS-365 WMS-366 проверки
856cf6395ced1be69d86153d576beeee73521b76 docs: WMS-355 WMS-357 WMS-365 результаты проверок и SHA стенда
b98e8948a1f00e60effa2c41c934c4832bc99f5d docs: WMS-367 изолированное ревью общего выпуска и обычная приёмка
2b95fe51380bed8779d5ef0911b333b45aa5e6d8 docs: WMS-368 проверка товарной печати Ozon
4306fa7e137a86a3b06c9ae98a00cf0296f2c8da fix(ozon): WMS-368 товарная печать; WMS-367 восстановление передачи и предел остатков
606d792410bd45499af2056fafb1337835ce3c56 merge: WMS-367 согласовать выпуск с etalon без возврата старого журнала квоты
94271fff04c8c7e4acacc5c4048b4a7fb192b05f Merge pull request #183 from chivkunovd-bitdenis/feat/ozon-merge-staging-20260905
734a059f25794db01d6e53fbd68d729f21336a84 fix: WMS-367 сохранять расписание Celery beat без lambda
cafbf3c5ca6c6e1e02ea553a7e68295bbaa6a574 Merge pull request #184 from chivkunovd-bitdenis/feat/ozon-merge-staging-20260905
87efb8b0704b2785444330a8c5865d36dcccf55b docs: WMS-367 WMS-368 подтвердить production и границу подключения Ozon
93850a4e259997ab3cace10f182f286f45c4acfe Merge pull request #185 from chivkunovd-bitdenis/feat/ozon-merge-staging-20260905
4b142c86d5a0510c1d327e98111ac228aa816833 docs: WMS-369 различие форм печати и редактирование количества
ec071e1cf0ecad7d9cad6ef5931952a685d7487f fix: WMS-370 фактический статус обмена Ozon; docs WMS-371 пропуск этикетки
af2130bcbbd795599af8ee3296c99d9b983e69f5 docs: WMS-372 переписать предупреждение передачи на WB
c32140c85111213f5d5163712d10e808a4b46ce6 Merge pull request #186 from chivkunovd-bitdenis/feat/ozon-merge-staging-20260905
4e11ce243565e9fc580c7e0baf9a16d083219e04 fix: WMS-373 explicit Ozon posting import without stock publication
ed72c8888a6e383f5101e0c1bd96d3793810e4fc Merge pull request #187 from chivkunovd-bitdenis/feat/ozon-merge-staging-20260905
14a08dde34491dd9e6ddacaf8351080b8ee2b121 docs: WMS-373 record deployment and cancelled manual import
282cde226cf64ac28fff80d460c44bd292d91887 docs: WMS-374 brief for full production Opus Max CLI review
c34f5bd5b2ec09036d67e2692348b38946028ea9 docs: WMS-374 independent Opus 5 review and Astra arbitration briefs
08b6d57cebe07791f74fc9c41d5c076962025edf docs: WMS-374 preserve first review and request missing coverage
b0427c33c363a0226a6be8fc23bf2e311f4e0860 docs: WMS-374 preserve Opus 5 review and production scope evidence
6e186b1b2d20f4b96bee3e0673b0541b61145d7b docs: WMS-374 preserve first review continuation and arbitration gaps
2a9cba7269a8221389fd676b6972555de14f9c3c docs(бэклог): сверка 05.09.2026 — 41 статус обновлён, 0 задач заведено
5763dbb7ac8b403453a0f997ce99f4f8ba827793 docs: WMS-374 preserve interrupted cross-review and launch arbitration
582f23206cf2e9aa31a4d13a6a85a05b77eca9d9 docs: WMS-374 save Astra verdict and final release review synthesis
31b26d00a33eaed698a4db9bdd9b732167a17da3 docs: WMS-375 record review fixes and production acceptance scope
3470b969818d54fd7516cac7c12174af0c01554c fix: WMS-375 protect Ozon publication and handoff; restore report accuracy
cf42d6d51deba75100fcad3e79d4396fe2fc9e69 fix: WMS-375 isolate marketplace allocations; WMS-369 WMS-372 restore FBS printing and clear warnings
2bca33913df601db655ff7bb94914cc18fb4ce22 test: WMS-375 verify served identity and preserve Ozon browser handoff evidence
9b34f3f7f99ed025ef07a59fe698682290836344 Merge pull request #188 from chivkunovd-bitdenis/feat/ozon-merge-staging-20260905
23de655c50c16850b3cc7ee0cdec395a1227df84 fix: WMS-375 commit inventory containers with their document link
1491fcb31ebe30516bf77044dea01a3a8e90aef3 Merge pull request #189 from chivkunovd-bitdenis/fix/wms375-inventory-atomicity
```
