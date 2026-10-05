# Исторические результаты инструментов: первоисточники

Это сохранённые результаты прежних расследований, не текущие SELECT и не действия данного задания. Никакой старый запрос или исправление повторно не запускались. Даты — UTC из журналов.

## rollout-2026-10-02T00-48-59-01a0f93a-3e98-7f81-ab1e-c384cc01a3ef.jsonl:99

Время: 2026-10-01T20:50:40.707Z

```text
Script completed
Wall time 1.5 seconds
Output:

BEGIN
id\tsupply_id\texternal_order_id\tstatus\twb_status\tsupplier_status\treserve_status\tpick_status\tpack_status\tsticker_status\tsticker_code\thas_sticker_file\tlast_wb_sync_at\tupdated_at\tmeta_details_json
0e9251a4-b8ab-4b65-8cdc-500146e58cd3\t9f479e17-1723-49a1-a836-97eeff3d4ea2\t0148656673-0134-1\tin_supply\tawaiting_packaging\tnew\treserved\tpending\tpending\tnot_requested\t\tf\t2026-10-01 20:46:47.190321+00\t2026-10-01 20:46:16.923347+00\t{"ozon_products": [{"imei": [], "is_blr_traceable": false, "is_marketplace_buyout": false, "name": "\u0412\u0438\u0434\u0435\u043e\u043d\u044f\u043d\u044f \u0431\u0435\u0441\u043f\u0440\u043e\u0432\u043e\u0434\u043d\u0430\u044f. \u0420\u0430\u0434\u0438\u043e\u043d\u044f\u043d\u044f. \u0412\u0438\u0434\u0435\u043e\u043d\u044f\u043d\u044f \u0441 \u043c\u043e\u043d\u0438\u0442\u043e\u0440\u043e\u043c. \u0420\u0430\u0434\u0438\u043e-\u043d\u044f\u043d\u044f MC 632", "offer_id": "video.nanny3", "price": {"amount": "7690", "currency": "RUB"}, "product_color": "\u0431\u0435\u043b\u044b\u0439", "quantity": 1, "sku": 1695134284, "weight": 0.44}], "ozon_delivery_method_id": "1020005029530200", "ozon_delivery_method_name": "\u0414\u043e\u0441\u0442\u0430\u0432\u043a\u0430 Ozon \u0441\u0430\u043c\u043e\u0441\u0442\u043e\u044f\u0442\u0435\u043b\u044c\u043d\u043e, \u041c\u043e\u0441\u043a\u0432\u0430", "ozon_requirements": {"kinds": [], "by_sku": {"sgtin": [], "uin": [], "imei": []}}, "ozon_label_error": {"code": "ozon_invalid_response", "message": "Ozon \u0432\u0435\u0440\u043d\u0443\u043b \u043e\u0442\u0432\u0435\u0442 \u043d\u0435\u0438\u0437\u0432\u0435\u0441\u0442\u043d\u043e\u0433\u043e \u0444\u043e\u0440\u043c\u0430\u0442\u0430."}}
27da526e-9e2c-4798-a978-ec15582183f1\t9f479e17-1723-49a1-a836-97eeff3d4ea2\t0181745532-0045-3\tin_supply\tawaiting_packaging\tnew\treserved\tpending\tpending\tnot_requested\t\tf\t2026-10-01 20:46:47.190321+00\t2026-10-01 20:46:16.923347+00\t{"ozon_products": [{"imei": [], "is_blr_traceable": false, "is_marketplace_buyout": false, "name": "\u041e\u043f\u043e\u0432\u0435\u0449\u0430\u0442\u0435\u043b\u044c \u043e \u0432\u0445\u043e\u0434\u0435 \u043f\u043e\u0441\u0435\u0442\u0438\u0442\u0435\u043b\u0435\u0439, \u0437\u0432\u0443\u043a\u043e\u0432\u043e\u0439 \u043e\u043f\u043e\u0432\u0435\u0449\u0430\u0442\u0435\u043b\u044c c \u0434\u0430\u0442\u0447\u0438\u043a\u043e\u043c \u0434\u0432\u0438\u0436\u0435\u043d\u0438\u044f.", "offer_id": "doorBell", "price": {"amount": "2900", "currency": "RUB"}, "product_color": "\u0431\u0435\u043b\u044b\u0439", "quantity": 1, "sku": 1697770458, "weight": 0.25}], "ozon_delivery_method_id": "1020005029530200", "ozon_delivery_method_name": "\u0414\u043e\u0441\u0442\u0430\u0432\u043a\u0430 Ozon \u0441\u0430\u043c\u043e\u0441\u0442\u043e\u044f\u0442\u0435\u043b\u044c\u043d\u043e, \u041c\u043e\u0441\u043a\u0432\u0430", "ozon_requirements": {"kinds": [], "by_sku": {"sgtin": [], "uin": [], "imei": []}}, "ozon_label_error": {"code": "ozon_invalid_response", "message": "Ozon \u0432\u0435\u0440\u043d\u0443\u043b \u043e\u0442\u0432\u0435\u0442 \u043d\u0435\u0438\u0437\u0432\u0435\u0441\u0442\u043d\u043e\u0433\u043e \u0444\u043e\u0440\u043c\u0430\u0442\u0430."}}
(2 rows)
id\tfbs_order_id\texternal_order_id\tkind\tstatus\tcontent_type\thas_storage\terror_code\terror_message\twb_fetched_at\tcreated_at\tupdated_at
(0 rows)
external_order_id\tbox_id\tbox_number\torder_product_id\tpack_status\tsticker_status\tozon_assembly
0148656673-0134-1\t759af5ec-ce15-4288-9506-fdb4dcd8ca5e\t4\te73d0d92-41c3-435d-abc6-4e1bf95ee5d9\tpending\tnot_requested\t
0181745532-0045-3\t2776d23b-86ef-4a60-acc4-e9d85f2cc8e5\t11\t9ed595e4-81cb-4272-92fd-dc89f13df672\tpending\tnot_requested\t
(2 rows)
sticker_status\torders
not_requested\t2
print_opened\t28
(2 rows)
ROLLBACK

```

## rollout-2026-10-02T00-48-59-01a0f93a-3e98-7f81-ab1e-c384cc01a3ef.jsonl:194

Время: 2026-10-01T20:52:17.870Z

```text
Script completed
Wall time 6.9 seconds
Output:

{"posting_number": "0148656673-0134-1", "top_type": "dict", "top_keys": ["result"], "result_type": "dict", "result_keys": ["additional_data", "addressee", "analytics_data", "available_actions", "barcodes", "cancellation", "container", "container_sort_type", "courier", "customer", "delivering_date", "delivery_method", "delivery_price", "destination_place_id", "destination_place_name", "external_order", "fact_delivery_date", "financial_data", "in_process_at", "integration_type_flow", "is_click_and_collect", "is_express", "is_multibox", "is_presortable", "legal_info", "multi_box_qty", "optional", "order_id", "order_number", "parent_posting_number", "pickup_code_verified_at", "posting_number", "previous_substatus", "product_exemplars", "products", "provider_status", "prr_option", "received_at_sorting_center", "related_postings", "related_weight_postings", "require_blr_traceable_attrs", "requirements", "scanit", "shipment_date", "shipment_date_without_delay", "sla_discount", "sorting_center", "status", "substatus", "tariffication", "tariffication_fact", "tariffication_steps", "tpl_integration_type", "tracking_number"], "status": "awaiting_packaging", "substatus": "posting_created", "available_actions": ["cancel", "has_barcode_for_printing", "product_cancel", "ship", "ship_async", "ship_with_additional_info"], "related_postings_type": "dict", "schema_valid": false, "validation_errors": [{"loc": ["result", "requirements", "products_requiring_gtd", "0"], "type": "string_type", "msg": "Input should be a valid string", "input_type": "int"}]}
{"posting_number": "0181745532-0045-3", "top_type": "dict", "top_keys": ["result"], "result_type": "dict", "result_keys": ["additional_data", "addressee", "analytics_data", "available_actions", "barcodes", "cancellation", "container", "container_sort_type", "courier", "customer", "delivering_date", "delivery_method", "delivery_price", "destination_place_id", "destination_place_name", "external_order", "fact_delivery_date", "financial_data", "in_process_at", "integration_type_flow", "is_click_and_collect", "is_express", "is_multibox", "is_presortable", "legal_info", "multi_box_qty", "optional", "order_id", "order_number", "parent_posting_number", "pickup_code_verified_at", "posting_number", "previous_substatus", "product_exemplars", "products", "provider_status", "prr_option", "received_at_sorting_center", "related_postings", "related_weight_postings", "require_blr_traceable_attrs", "requirements", "scanit", "shipment_date", "shipment_date_without_delay", "sla_discount", "sorting_center", "status", "substatus", "tariffication", "tariffication_fact", "tariffication_steps", "tpl_integration_type", "tracking_number"], "status": "awaiting_packaging", "substatus": "posting_created", "available_actions": ["cancel", "has_barcode_for_printing", "product_cancel", "ship", "ship_async", "ship_with_additional_info"], "related_postings_type": "dict", "schema_valid": false, "validation_errors": [{"loc": ["result", "requirements", "products_requiring_gtd", "0"], "type": "string_type", "msg": "Input should be a valid string", "input_type": "int"}]}

```

## rollout-2026-10-02T00-48-59-01a0f93a-3e98-7f81-ab1e-c384cc01a3ef.jsonl:280

Время: 2026-10-01T20:54:20.811Z

```text
Script completed
Wall time 4.6 seconds
Output:

{"posting_number": "0148656673-0134-1", "status": "awaiting_packaging", "substatus": "posting_created", "requirements": {"products_requiring_gtd": [1695134284]}}
{"posting_number": "0181745532-0045-3", "status": "awaiting_packaging", "substatus": "posting_created", "requirements": {"products_requiring_gtd": [1697770458]}}

```

## rollout-2026-09-30T13-11-13-01a0f195-1278-7f50-9667-c4b8dbd23461.jsonl:423

Время: 2026-09-30T09:44:13.785Z

```text
Script completed
Wall time 0.0 seconds
Output:

warning: The `fitz` API is deprecated and will be removed in future. Use `import pymupdf` instead.
{"supply_id": "0dcea766-b769-4fbd-a0a9-84e95e1cb186", "from": "assembling", "to": "in_delivery", "orders": 33, "units": 34, "boxes": 34, "audit_recorded": true}
{"supply_id": "d5e630d2-a387-4bfa-afb9-982a2561dca0", "from": "packed", "to": "done", "orders": 1, "units": 1, "boxes": 0, "audit_recorded": true}
COMMITTED
{"readback_group": "active", "target_supplies": []}
{"readback_group": "delivery", "target_supplies": [{"id": "0dcea766-b769-4fbd-a0a9-84e95e1cb186", "marketplace": "ozon", "wb_supply_id": "PENDING-5725fe79-bf85-4dc0-ada3-1257e8bd43b3", "name": "FBS 24.09.2026", "delivery_type": "warehouse_sc", "delivery_route": "Доставка Ozon самостоятельно, Москва", "status": "in_delivery", "seller": {"id": "cf6d31c5-944b-4382-af34-636ca9aa8cc3", "name": "МОВСЕСЯН ЗВАРД ГАРНИКОВНА"}, "wb_warehouse": {"id": 1020005029530200, "name": null}, "wms_warehouse": {"id": "2d968c65-4a8d-414e-9076-0f201c2dba63", "name": "Бамбук"}, "orders_count": 33, "units_count": 34, "picked_units_count": 0, "boxes_count": 34, "planned_shipment_date": null, "can_add_orders": false}]}
{"readback_group": "done", "target_supplies": [{"id": "d5e630d2-a387-4bfa-afb9-982a2561dca0", "marketplace": "ozon", "wb_supply_id": "PENDING-1ffe7a82-dfaa-4677-8896-5a3237f27d2f", "name": "FBS 24.09.2026", "delivery_type": "warehouse_sc", "delivery_route": "Доставка Ozon самостоятельно, Москва", "status": "done", "seller": {"id": "cf6d31c5-944b-4382-af34-636ca9aa8cc3", "name": "МОВСЕСЯН ЗВАРД ГАРНИКОВНА"}, "wb_warehouse": {"id": 1020005029530200, "name": null}, "wms_warehouse": {"id": "2d968c65-4a8d-414e-9076-0f201c2dba63", "name": "Бамбук"}, "orders_count": 1, "units_count": 1, "picked_units_count": 1, "boxes_count": 0, "planned_shipment_date": null, "can_add_orders": false}]}

```

## rollout-2026-09-30T13-11-13-01a0f195-1278-7f50-9667-c4b8dbd23461.jsonl:410 — состав сентябрьских поставок

Время: 2026-09-30T09:43:16.555Z

```text
BEGIN
              supply_id               |   status    | wb_status  |     supplier_status     | count |           last_sync
--------------------------------------+-------------+------------+-------------------------+-------+-------------------------------
 0dcea766-b769-4fbd-a0a9-84e95e1cb186 | cancelled   | cancelled  | posting_canceled        |     4 | 2026-09-28 16:41:39.441673+00
 0dcea766-b769-4fbd-a0a9-84e95e1cb186 | done        | delivered  | posting_received        |    17 | 2026-09-29 16:19:06.292823+00
 0dcea766-b769-4fbd-a0a9-84e95e1cb186 | in_delivery | delivering | posting_in_pickup_point |    10 | 2026-09-30 09:35:54.087538+00
 0dcea766-b769-4fbd-a0a9-84e95e1cb186 | in_delivery | delivering | posting_on_way_to_city  |     2 | 2026-09-30 09:35:54.087538+00
 d5e630d2-a387-4bfa-afb9-982a2561dca0 | done        | delivered  | posting_received        |     1 | 2026-09-26 15:28:20.150543+00
(5 rows)

           table_name
---------------------------------
 marketplace_unload_reservations
 inventory_reservations
 fbs_order_reservations
 fbs_order_product_reservations
 zz_bak20260831_reservations
 fbs_shipment_reversal_ledger
(6 rows)

ROLLBACK

```
