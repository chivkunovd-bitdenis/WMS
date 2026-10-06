# WMS-675: адресный аудит доступа и текущего инцидента, 06.10.2026

Этот проход выполняет только порученное расследование. Изменяется только этот отчёт. Ветка `codex/wms662-663-priority`; начало чтения на `7d9e9a63c98e654b688687a3bb2c60782469fbc5`. Правила AGENTS.md и обновлённого origin/etalon прочитаны. Навыки и дочерние агенты не запускались по прямому поручению. Продуктовый код, production business rows, секреты, авторизация, Telegram и внешние операции не менялись. Разрешённая техническая подготовка ограниченных SQL-ролей выполнена штатным SellerDirectory; это отдельное действие доступа, а не чистый SELECT.

## Результат доступа

Предыдущий [handoff](analysis.md) содержал busy/lock timeout. В 06:10–06:12 UTC один новый запуск неизменённого `scoped_access_probe.py` успешно выполнил exact `ensure_tenant(b80a893b-ab87-42b6-8fd7-6d41502c900f)` и SELECT через `wms_agent_t_b80a893bab8742b68fd76d41502c900f`. Обхода legacy read-only/admin нет; повторов после успеха нет. Лимиты probe: 30 секунд, 60 строк, дата от 01.10 и исторический supply ID.

В локальном state.db через SQLite mode=ro перечитана привязка чата -5515853898: tenant Бамбук `b80a893b-ab87-42b6-8fd7-6d41502c900f`, level=tenant, bound_by=689889703, seller пустой. Source236/TG65, author519853067 и source241/TG66, author689889703 перечитаны адресно. Source236 действительно сообщает о черновике, отменённом заказе и31 штуке, но не содержит supply ID.

AVpack: штатный exact `ensure_seller(0b8da5d8-f43a-42f5-a2ec-43173ea844bd)` также успешен; SELECT только через seller-role `wms_agent_s_0b8da5d8f43a42f5a2ec43173ea844bd`. Результат identity: ИП Горячкина Т.И., tenant `d6e1ad21-8afa-4acf-8d0b-907b9f2adcfe`, совпадает с поручением владельца. Сохранённой AVpack chat_binding адресный поиск не обнаружил; новая привязка не создавалась, использована явно заданная владельцем seller scope. Это доказывает gateway SELECT, а не доступ браузера оператора.

## Свежие поставки Бамбука и новый кандидат

Все пять октябрьских строк относятся к Ozon, source=wms, seller `cf6d31c5-944b-4382-af34-636ca9aa8cc3` (МОВСЕСЯН ЗВАРД ГАРНИКОВНА), warehouse `2d968c65-4a8d-414e-9076-0f201c2dba63`.

| Supply | Название | Статус WMS | External ID | Orders/units | Ledger rows | Shipment movements |
|---|---|---|---|---|---|---|
| 5d3d4508-26f5-4e3b-a399-1c1e1f000e11 | FBS 05.10.2026 | in_delivery | 122917391 | 25/25 | 25 | 25 |
| 6e2e6297-d9d2-4467-bb7e-ca1166dfc8c1 | FBS 04.10.2026 | in_delivery | 122820180 | 15/15 | 15 | 15 |
| 6e5c40d1-21ba-4af1-ad07-b314f4aa4c37 | FBS 03.10.2026 | in_delivery | 122779705 | 36/36 | 36 | 36 |
| b82d1e9a-30d2-4d7b-b52d-9775c3d266e3 | FBS 02.10.2026 | draft | NULL | 31/31 | 31 | 0 |
| 9f479e17-1723-49a1-a836-97eeff3d4ea2 | FBS 01.10.2026 | in_delivery | NULL | 28/28 | 28 | 28 |

Чтение 06:12:07 UTC. Единственный октябрьский черновик `b82d1e9a-30d2-4d7b-b52d-9775c3d266e3`, временный номер `PENDING-720eff4f-ad78-4bf1-b16c-bde4506b5ed9`, содержит ровно31 позицию/единицу и31 ledger row без shipment_movement_id. Это сильный конкретный кандидат сообщения236, но совпадение числа и статуса ещё не доказывает ссылку из голосового сообщения. Исторический October ID не подставляется вместо него. Старые postings `0181745532-0045-3` и `0148656673-0134-1` сейчас принадлежат именно этому черновику.

В снимке 31 заказа: 4 cancelled/cancelled, 8 done/delivered, 18 in_delivery/delivering и1 in_supply/awaiting_packaging. Отменённые postings: `0181745532-0045-3`, `0282817049-0013-1`, `80034639-0273-1`, `99185584-1963-5`. Awaiting-packaging: `0148656673-0134-1`. Даже локальный снимок не допускает слепое списание31. Cached positive candidates максимум26 единиц; это не разрешение и не свежий внешний proof. У18 delivering последнее last_wb_sync_at=2026-10-06 06:07:15.669762+00; done/cancelled обновлялись ранее. Raw API Ozon в этом проходе не вызывался.

## AVpack: текущий ограниченный снимок

На 06:12 UTC Ozon supply `151b087c-50b1-4041-a5e7-59e6be83fd34` / FBS 05.10.2026 — assembling, external ID NULL, `PENDING-928f0a01-fd02-4acd-8400-4c3e0cc93920`. WB supplies: `cf461de1-b34d-410e-ba76-ea059d315f90` / WB-GI-288317046, `201a9446-e583-433f-9513-29ff137cd99a` / WB-GI-286786083, `b2b8721a-b16b-47bb-8b8c-8f5d9c55511a` / WB-GI-286722960 и `c73d2573-73c9-422e-ad22-6f310fd955dc` / WB-GI-286237409 имеют local done и delivered_at. Это WMS readback, не новая проверка статусов WB.

## FullHuman: идентичность остаётся недоказанной

В сохранённых chat_bindings отсутствует совпадение Full/Human/Фул. Адресный поиск сообщений владельца также не дал исходного сообщения. Штатные directory find_tenants и find для `Full Human`, `FullHuman`, `Full`, `Human`, `Фулхьюман` вернули []. Для `Фул` и `Фул Хьюман` find_tenants вернул единственное нечёткое совпадение «Фулфёдор», tenant `db45d56c-ecec-4575-b247-dacbdaca052f`, sellers=0. Нет первичного источника, связывающего его с FullHuman; ensure/read для этого кандидата не выполнялись. Нельзя выдавать его за установленного клиента. Нужен exact source/chat или подтверждённый tenant/seller FullHuman.

## Дополнительное адресное доказательство

Ниже повторное bounded чтение состава черновика, двух видов резерва, рецепта ledger и фактических связанных движений. Рецепт может существовать до расхода: наличие31 ledger row само по себе не подтверждает списание. Результаты разных SELECT не объявляются единым транзакционным snapshot; рабочая система продолжает обновляться.

### Exact orders and reserves / 2026-10-06T06:13:34.471990+00:00

```sql
SELECT o.id,o.external_order_id,o.status,o.wb_status,p.product_id,p.ozon_sku,p.quantity,p.reserved_quantity,coalesce((SELECT sum(r.quantity) FROM fbs_order_reservations r WHERE r.fbs_order_id=o.id AND r.tenant_id=o.tenant_id),0) AS legacy_reserved,coalesce((SELECT sum(r.quantity) FROM fbs_order_product_reservations r WHERE r.order_product_id=p.id AND r.tenant_id=o.tenant_id),0) AS position_reserved FROM fbs_orders o JOIN fbs_order_products p ON p.order_id=o.id WHERE o.tenant_id='b80a893b-ab87-42b6-8fd7-6d41502c900f' AND o.supply_id='b82d1e9a-30d2-4d7b-b52d-9775c3d266e3' ORDER BY o.external_order_id LIMIT 60
```

```csv
id,external_order_id,status,wb_status,product_id,ozon_sku,quantity,reserved_quantity,legacy_reserved,position_reserved
8bf9d518-2702-4c29-89ab-4ed002c0f416,0113371235-0054-3,in_delivery,delivering,2ccde129-ed49-44fd-8dcc-4dd092581e26,1697770458,1,1,0,1
b05ef83a-01c3-4f14-bafd-41669614d4c1,0144953533-0124-1,in_delivery,delivering,80fa2a1e-1974-4e6e-8497-2defd0176bd5,1589998415,1,1,0,1
0e9251a4-b8ab-4b65-8cdc-500146e58cd3,0148656673-0134-1,in_supply,awaiting_packaging,605bdc71-baae-43dd-9ed4-fb37e07906c0,1695134284,1,1,0,1
3470f8fc-008d-4fe3-8a72-d9c73a46af42,0153677007-0258-1,in_delivery,delivering,80fa2a1e-1974-4e6e-8497-2defd0176bd5,1589998415,1,1,0,1
eaabb48b-0174-414e-96b9-518f9220400e,0164033835-0039-1,in_delivery,delivering,80fa2a1e-1974-4e6e-8497-2defd0176bd5,1589998415,1,1,0,1
64a9b26b-3e27-48f7-ae18-c4d2c10ad5a1,0172663629-0081-1,in_delivery,delivering,80fa2a1e-1974-4e6e-8497-2defd0176bd5,1589998415,1,1,0,1
27da526e-9e2c-4798-a978-ec15582183f1,0181745532-0045-3,cancelled,cancelled,2ccde129-ed49-44fd-8dcc-4dd092581e26,1697770458,1,0,0,0
558f8beb-a0b6-489a-a8b6-5dd3a5a494b5,0187441457-0073-1,in_delivery,delivering,2ccde129-ed49-44fd-8dcc-4dd092581e26,1697770458,1,1,0,1
32427a22-b4dd-4c8a-9278-76a067ab41d2,0190055173-0461-1,in_delivery,delivering,1a99998b-1576-4e7f-9f9a-cf9eaf14907e,1586484429,1,1,0,1
2c6241b2-dc71-4b21-bc9d-534c63b8d4ba,0236443586-0012-1,in_delivery,delivering,4d7e4a3d-954e-48f6-94a3-45729f2654d0,1586466682,1,1,0,1
c2d7a754-f334-431f-89ed-5e47d3e0c7a4,0249035122-0351-1,in_delivery,delivering,80fa2a1e-1974-4e6e-8497-2defd0176bd5,1589998415,1,1,0,1
66f61455-fea9-42a2-b52a-b7a754bb660d,0282817049-0013-1,cancelled,cancelled,2ccde129-ed49-44fd-8dcc-4dd092581e26,1697770458,1,0,0,0
e203f00e-db36-46c0-aa1b-192539ab88b8,06383353-1897-1,done,delivered,80fa2a1e-1974-4e6e-8497-2defd0176bd5,1589998415,1,0,0,0
b7216c03-b13d-49d8-a3e8-a7c99c29bda6,21052558-0445-1,done,delivered,2ccde129-ed49-44fd-8dcc-4dd092581e26,1697770458,1,0,0,0
958ac70f-79b5-4d9c-b0b1-dc2f5237cd25,23388119-0163-1,in_delivery,delivering,1a99998b-1576-4e7f-9f9a-cf9eaf14907e,1586484429,1,1,0,1
ccdd5eaf-cd9b-456c-8415-0868a52fa0af,28508065-0594-1,done,delivered,1a99998b-1576-4e7f-9f9a-cf9eaf14907e,1586484429,1,0,0,0
0d45ad7d-956e-4625-9dc5-f10c2e5b453a,31853470-0198-1,done,delivered,4d7e4a3d-954e-48f6-94a3-45729f2654d0,1586466682,1,0,0,0
6c283f46-7f5b-4620-a322-096f37027c8c,45035035-0211-1,done,delivered,2ccde129-ed49-44fd-8dcc-4dd092581e26,1697770458,1,0,0,0
c5177e7d-9db8-437a-ae64-9504275b6bad,50261136-0017-1,in_delivery,delivering,2ccde129-ed49-44fd-8dcc-4dd092581e26,1697770458,1,1,0,1
78de0390-f016-4d31-ac4e-7d6de97a20ac,55322493-0272-1,in_delivery,delivering,2ccde129-ed49-44fd-8dcc-4dd092581e26,1697770458,1,1,0,1
6fc67946-d062-49ba-ad8e-9c061a1177e1,56845110-0045-1,in_delivery,delivering,2ccde129-ed49-44fd-8dcc-4dd092581e26,1697770458,1,1,0,1
870e99a1-6435-4291-ac7d-cf0a81ab0572,56907807-0024-1,done,delivered,1a99998b-1576-4e7f-9f9a-cf9eaf14907e,1586484429,1,0,0,0
4c9f0057-d363-4ec3-9c9b-4006c7f50516,59814512-0364-3,in_delivery,delivering,2ccde129-ed49-44fd-8dcc-4dd092581e26,1697770458,1,1,0,1
6444a2d9-23e0-4ddf-aa43-87abd03f27a7,62035277-0532-1,in_delivery,delivering,4d7e4a3d-954e-48f6-94a3-45729f2654d0,1586466682,1,1,0,1
89d0cf5c-8811-4ef7-8420-6aa7037b21c6,66144885-0156-18,done,delivered,7e159b28-72f7-4f3c-8f92-ebca10e054db,1695128938,1,0,0,0
c614ec4d-3c05-49f4-a986-fb6048642456,80034639-0273-1,cancelled,cancelled,1a99998b-1576-4e7f-9f9a-cf9eaf14907e,1586484429,1,0,0,0
d46f4e6a-c28c-4ec6-a8b7-3c9734528f53,81035721-0742-1,done,delivered,4d7e4a3d-954e-48f6-94a3-45729f2654d0,1586466682,1,0,0,0
a8e915f1-3a6f-45de-9cfb-f9f5cae5acde,83893932-0680-2,in_delivery,delivering,80fa2a1e-1974-4e6e-8497-2defd0176bd5,1589998415,1,1,0,1
cfc68d5f-0694-486e-84b0-136e51ce2532,85257535-0274-1,in_delivery,delivering,4d7e4a3d-954e-48f6-94a3-45729f2654d0,1586466682,1,1,0,1
e014ba26-8cbc-4480-8ad5-581f9f500f51,99185584-1963-5,cancelled,cancelled,2ccde129-ed49-44fd-8dcc-4dd092581e26,1697770458,1,0,0,0
604b0a9f-910c-42ba-8c14-88b459ef6d12,99630148-0017-1,in_delivery,delivering,7e159b28-72f7-4f3c-8f92-ebca10e054db,1695128938,1,1,0,1

```

### Ledger recipe summary / 2026-10-06T06:13:36.001749+00:00

```sql
SELECT o.status,o.wb_status,count(l.id) AS ledgers,count(l.shipment_movement_id) AS movement_refs,count(l.reversed_at) AS reversed,count(l.ozon_positions_json) AS recipe_present,count(l.written_off_at) AS written_off FROM fbs_orders o JOIN fbs_shipment_reversal_ledger l ON l.fbs_order_id=o.id AND l.tenant_id=o.tenant_id WHERE o.tenant_id='b80a893b-ab87-42b6-8fd7-6d41502c900f' AND o.supply_id='b82d1e9a-30d2-4d7b-b52d-9775c3d266e3' GROUP BY o.status,o.wb_status LIMIT 20
```

```csv
status,wb_status,ledgers,movement_refs,reversed,recipe_present,written_off
cancelled,cancelled,4,0,0,4,0
done,delivered,8,0,0,8,0
in_delivery,delivering,18,0,0,18,0
in_supply,awaiting_packaging,1,0,0,1,0

```

### Linked inventory movements / 2026-10-06T06:13:37.525993+00:00

```sql
SELECT m.id,m.product_id,m.quantity_delta,m.movement_type,m.created_at FROM inventory_movements m JOIN fbs_shipment_reversal_ledger l ON m.id=l.shipment_movement_id OR m.id=l.reversal_movement_id JOIN fbs_orders o ON o.id=l.fbs_order_id WHERE o.tenant_id='b80a893b-ab87-42b6-8fd7-6d41502c900f' AND o.supply_id='b82d1e9a-30d2-4d7b-b52d-9775c3d266e3' AND m.tenant_id=o.tenant_id LIMIT 60
```

```csv
id,product_id,quantity_delta,movement_type,created_at

```

### Recipe movement references / 2026-10-06T06:14:13.830901+00:00

```sql
SELECT o.external_order_id,x.value ->> 'product_id' AS product_id,x.value ->> 'quantity' AS quantity,x.value ->> 'storage_location_id' AS storage_location_id,x.value ->> 'movement_id' AS recipe_movement_id FROM fbs_shipment_reversal_ledger l JOIN fbs_orders o ON o.id=l.fbs_order_id CROSS JOIN LATERAL json_array_elements(l.ozon_positions_json::json) x(value) WHERE o.tenant_id='b80a893b-ab87-42b6-8fd7-6d41502c900f' AND l.tenant_id=o.tenant_id AND o.supply_id='b82d1e9a-30d2-4d7b-b52d-9775c3d266e3' ORDER BY o.external_order_id LIMIT 60
```

```csv
external_order_id,product_id,quantity,storage_location_id,recipe_movement_id
0113371235-0054-3,2ccde129-ed49-44fd-8dcc-4dd092581e26,1,7d44fbc9-9c82-4ef1-bac7-4e47fe5de3c1,
0144953533-0124-1,80fa2a1e-1974-4e6e-8497-2defd0176bd5,1,7d44fbc9-9c82-4ef1-bac7-4e47fe5de3c1,
0148656673-0134-1,605bdc71-baae-43dd-9ed4-fb37e07906c0,1,7d44fbc9-9c82-4ef1-bac7-4e47fe5de3c1,
0153677007-0258-1,80fa2a1e-1974-4e6e-8497-2defd0176bd5,1,7d44fbc9-9c82-4ef1-bac7-4e47fe5de3c1,
0164033835-0039-1,80fa2a1e-1974-4e6e-8497-2defd0176bd5,1,7d44fbc9-9c82-4ef1-bac7-4e47fe5de3c1,
0172663629-0081-1,80fa2a1e-1974-4e6e-8497-2defd0176bd5,1,7d44fbc9-9c82-4ef1-bac7-4e47fe5de3c1,
0181745532-0045-3,2ccde129-ed49-44fd-8dcc-4dd092581e26,1,7d44fbc9-9c82-4ef1-bac7-4e47fe5de3c1,
0187441457-0073-1,2ccde129-ed49-44fd-8dcc-4dd092581e26,1,7d44fbc9-9c82-4ef1-bac7-4e47fe5de3c1,
0190055173-0461-1,1a99998b-1576-4e7f-9f9a-cf9eaf14907e,1,7d44fbc9-9c82-4ef1-bac7-4e47fe5de3c1,
0236443586-0012-1,4d7e4a3d-954e-48f6-94a3-45729f2654d0,1,7d44fbc9-9c82-4ef1-bac7-4e47fe5de3c1,
0249035122-0351-1,80fa2a1e-1974-4e6e-8497-2defd0176bd5,1,7d44fbc9-9c82-4ef1-bac7-4e47fe5de3c1,
0282817049-0013-1,2ccde129-ed49-44fd-8dcc-4dd092581e26,1,7d44fbc9-9c82-4ef1-bac7-4e47fe5de3c1,
06383353-1897-1,80fa2a1e-1974-4e6e-8497-2defd0176bd5,1,7d44fbc9-9c82-4ef1-bac7-4e47fe5de3c1,
21052558-0445-1,2ccde129-ed49-44fd-8dcc-4dd092581e26,1,7d44fbc9-9c82-4ef1-bac7-4e47fe5de3c1,
23388119-0163-1,1a99998b-1576-4e7f-9f9a-cf9eaf14907e,1,7d44fbc9-9c82-4ef1-bac7-4e47fe5de3c1,
28508065-0594-1,1a99998b-1576-4e7f-9f9a-cf9eaf14907e,1,7d44fbc9-9c82-4ef1-bac7-4e47fe5de3c1,
31853470-0198-1,4d7e4a3d-954e-48f6-94a3-45729f2654d0,1,7d44fbc9-9c82-4ef1-bac7-4e47fe5de3c1,
45035035-0211-1,2ccde129-ed49-44fd-8dcc-4dd092581e26,1,7d44fbc9-9c82-4ef1-bac7-4e47fe5de3c1,
50261136-0017-1,2ccde129-ed49-44fd-8dcc-4dd092581e26,1,7d44fbc9-9c82-4ef1-bac7-4e47fe5de3c1,
55322493-0272-1,2ccde129-ed49-44fd-8dcc-4dd092581e26,1,7d44fbc9-9c82-4ef1-bac7-4e47fe5de3c1,
56845110-0045-1,2ccde129-ed49-44fd-8dcc-4dd092581e26,1,7d44fbc9-9c82-4ef1-bac7-4e47fe5de3c1,
56907807-0024-1,1a99998b-1576-4e7f-9f9a-cf9eaf14907e,1,7d44fbc9-9c82-4ef1-bac7-4e47fe5de3c1,
59814512-0364-3,2ccde129-ed49-44fd-8dcc-4dd092581e26,1,7d44fbc9-9c82-4ef1-bac7-4e47fe5de3c1,
62035277-0532-1,4d7e4a3d-954e-48f6-94a3-45729f2654d0,1,7d44fbc9-9c82-4ef1-bac7-4e47fe5de3c1,
66144885-0156-18,7e159b28-72f7-4f3c-8f92-ebca10e054db,1,7d44fbc9-9c82-4ef1-bac7-4e47fe5de3c1,
80034639-0273-1,1a99998b-1576-4e7f-9f9a-cf9eaf14907e,1,7d44fbc9-9c82-4ef1-bac7-4e47fe5de3c1,
81035721-0742-1,4d7e4a3d-954e-48f6-94a3-45729f2654d0,1,7d44fbc9-9c82-4ef1-bac7-4e47fe5de3c1,
83893932-0680-2,80fa2a1e-1974-4e6e-8497-2defd0176bd5,1,7d44fbc9-9c82-4ef1-bac7-4e47fe5de3c1,
85257535-0274-1,4d7e4a3d-954e-48f6-94a3-45729f2654d0,1,7d44fbc9-9c82-4ef1-bac7-4e47fe5de3c1,
99185584-1963-5,2ccde129-ed49-44fd-8dcc-4dd092581e26,1,7d44fbc9-9c82-4ef1-bac7-4e47fe5de3c1,
99630148-0017-1,7e159b28-72f7-4f3c-8f92-ebca10e054db,1,7d44fbc9-9c82-4ef1-bac7-4e47fe5de3c1,

```

## Проверки, ограничения и передача

Адресные чтения завершены без broad suite и без параллельных тестовых workers. Неизменённый probe прошёл. Дополнительные SELECT дали полный состав31 заказа без усечения, 19 position-reserve units (18 delivering +1 awaiting_packaging), 0 legacy-reserve units; done8 и cancelled4 имеют reserve0. Ledger summary: у всех31 есть рецепт, но нет written_off_at, shipment_movement_id и reversed_at. Связанный по ledger inventory_movement SELECT пуст. Это доказательство отсутствующих ссылок проведения в текущем journal, а не исключение любого возможного несвязанного/исторического расхода.

Один первоначальный reserve SELECT получил SQLSTATE42703 `column r.order_id does not exist`. Поле сверено с моделью (правильное `fbs_order_id`), последующий адресный SELECT успешно выполнен; ошибка не является оставшимся блокером доступа. Прочие выполненные текущие gateway queries успешны. `python3 scripts/ci/check_task_documents.py HEAD` до коммита прошёл; AGENTS.md/CLAUDE.md совпадают. Проверка с включением нового WMS-675 commit (`python3 scripts/ci/check_task_documents.py 2e1b30036e3cb4c16b561a3637e791cd80e6984c^`) завершилась exit1: «WMS-675: В таблице с колонкой „Класс“ нет колонки „Тест“». Причина — существующая таблица в docs/requirements/WMS-675.md; этот файл вне ownership и не изменён. Значит, проверка итогового документа НЕ зелёная. CI публикуемого SHA не проверен. Продуктовые тесты не запускались, поскольку изменён только этот отчёт; независимое Astra high ревью и приёмка не выполнены этим investigator. Чужой изменённый test_wms663_customs_documents_contract.py и wms663-developer-result.txt не включаются в коммит.

Блокер SQL-доступа Bambook/AVpack снят штатным техническим механизмом. Остаются: (1) явное соответствие supply236 найденному31-unit черновику; (2) fresh read-only Ozon proof состава/статуса exact postings, включая split children; (3) исключение ранее проведённого расхода вне отсутствующих ledger links и адресная сверка stock/location; (4) исходный bound client FullHuman. Production SHA и браузер оператора не проверены. Никакие внешние ship/withdraw/sign/save вызовы не выполнялись и Telegram сообщения не отправлялись.

Следующий допустимый шаг — точная внешняя read-only сверка26 cached positive candidates и существующих источников расхода, с отдельным исключением четырёх cancelled и одного awaiting_packaging. Только после этого можно составить план идемпотентного транзакционного восстановления недостающих единиц с повторным чтением cancel/ledger под штатным lock. Здесь нет исполняемого ремонта и нет разрешения на списание31. Остаток, резерв и расположение остаются отдельными доказательствами.

Итоговая проверка диапазона от начального `7d9e9a63c98e654b688687a3bb2c60782469fbc5` дополнительно обнаружила незаполненные вердикты WMS-663 C1–C19 в общем рабочем состоянии. Параллельные исполнители сохраняют свои тесты в этой же ветке; это не изменения данного investigator. Собственные коммиты затрагивают исключительно access-audit-0609.md. Проверка пробелов своего отчёта прошла. Независимое ревью/CI остаются не подтверждены.
