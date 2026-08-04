# 01 — Анализ + 02 арх (модератор)

## Модераторский MVP (M → узкий срез)

**In:**
1. Модель `FbsSupply` + миграция `0064`; FK `fbs_orders.supply_id` → `fbs_supplies.id`; поля `sticker_code`, `sticker_file` (Text/LargeBinary or path String — prefer Text base64 or storage path String(512) like other artifacts; look for existing sticker storage pattern — if none, `sticker_file` Text nullable for base64/data-url OR bytes as LargeBinary; prefer String path under `wms_data_dir/fbs-stickers/{order_id}.png` + optional sticker_code).
2. WB: `POST /api/v3/supplies`, `PATCH /api/v3/supplies/{sid}/orders/{oid}`, `POST /api/v3/orders/stickers?type=png&width=58&height=40`
3. API `/operations/fbs-supplies`: POST create, POST `{id}/orders` add order(s), GET `{id}`, GET `{id}/picking-list`, POST `{id}/stickers`
4. Токен: marketplace_token (required), fallback supplies for create? Prefer marketplace only for supply ops.
5. Order status `new` → `in_supply` on add; supply stays `draft` until enough orders (or auto `assembling` when ≥1 order — use draft while filling, endpoint to mark assembling optional).
6. Picking list: group by wb_article / product sku + size/color from product if available + count.

**Out / defer:**
- **packaging_task** — модель завязана на marketplace_unload; без схемы FBS не вяжем. Follow-up.
- deliver, trbx, marking, frontend, TSD.
- in_delivery/done transitions — только константы статусов; deliver в следующей задаче.

**Ок на код** (continuous moderated).
