"""Пересборка сверки остатков ФБС. ТОЛЬКО ЧТЕНИЕ.

Отличие от прошлой версии: склады селлера делятся на НАШИ и ЧУЖИЕ.
Наши — это склады фулфилмента «Империя Львов» (и WMS у Loviana).
Чужой склад «Фулфилмент» (2035877) и прочие раньше молча попадали
в общую цифру по ООО «Фэшн» и давали фантомную нехватку 89 шт.
Теперь чужие склады идут отдельной колонкой и в наши итоги не входят.
"""
import asyncio, csv, uuid
from datetime import UTC, datetime
from sqlalchemy import select, text
from app.db.session import SessionLocal
from app.models.fbs_warehouse_binding import FbsWarehouseBinding
from app.models.product import Product
from app.services.fbs_stock_sync_service import _resolve_marketplace_api_token
from app.services.wildberries_client import (
    fetch_marketplace_stocks, fetch_marketplace_seller_warehouses, WildberriesClientError)
import httpx

SELLERS = [
    ("ИП Чжоу",  "bf8eea6b-eaa6-47ea-8dfc-289142372dab", {2068977, 2069067}),
    ("Loviana",  "9819f2c6-b28e-401e-a163-6ffe9e420da6", {2046998, 2088990}),
    ("ООО Фэшн", "77b66021-25e9-4127-8c01-b8408eccde37", {2103525, 2115694, 2115687}),
]
IN_WORK = ("waiting", "sorted", "ready_for_pickup")

# Приход = все положительные движения, кроме возвратов отгрузки (fbs_shipment).
SQL_PROD = text("""
select p.id, p.sku_code,
  coalesce((select sum(m.quantity_delta) from inventory_movements m
     where m.product_id=p.id and m.quantity_delta>0
       and m.movement_type <> 'fbs_shipment'),0)                            as prihod,
  coalesce((select -sum(m.quantity_delta) from inventory_movements m
     where m.product_id=p.id and m.movement_type='fbs_shipment'
       and m.quantity_delta<0),0)                                           as uehalo,
  coalesce((select -sum(m.quantity_delta) from inventory_movements m
     where m.product_id=p.id and m.movement_type='ownership_transfer_out'),0) as peredacha,
  coalesce((select sum(b.quantity) from inventory_balances b
     where b.product_id=p.id),0)                                            as ostatok
from products p where p.seller_id = :sid
""")

SQL_ORD = text("""
select o.product_id, o.wb_warehouse_id,
       count(*)                                        as v_rabote,
       count(*) filter (where o.pick_status='pending')  as trebuyut
from fbs_orders o
where o.seller_id = :sid and o.wb_status = any(:st) and o.product_id is not null
group by 1,2
""")


async def main() -> None:
    stamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    fp = open("/tmp/out-products.csv", "w", newline="", encoding="utf-8")
    fc = open("/tmp/out-cabinet.csv",  "w", newline="", encoding="utf-8")
    fo = open("/tmp/out-orders.csv",   "w", newline="", encoding="utf-8")
    wp, wc, wo = csv.writer(fp), csv.writer(fc), csv.writer(fo)
    wp.writerow(["seller", "sku", "prihod", "uehalo", "peredacha", "ostatok"])
    wc.writerow(["seller", "wid", "wh_name", "nash", "sku", "amount"])
    wo.writerow(["seller", "wid", "wh_name", "nash", "sku", "v_rabote", "trebuyut"])

    async with SessionLocal() as s, httpx.AsyncClient() as c:
        for name, sid_str, ours in SELLERS:
            sid = uuid.UUID(sid_str)
            binding = (await s.scalars(select(FbsWarehouseBinding)
                       .where(FbsWarehouseBinding.seller_id == sid))).first()
            if binding is None:
                print("нет привязки:", name); continue
            token = await _resolve_marketplace_api_token(s, binding.tenant_id, sid)

            prods = list((await s.scalars(select(Product).where(
                Product.tenant_id == binding.tenant_id, Product.seller_id == sid))).all())
            by_chrt = {int(p.wb_chrt_id): p for p in prods if p.wb_chrt_id is not None}
            by_id = {p.id: p for p in prods}

            for pid, sku, pr, ue, pe, os_ in (await s.execute(SQL_PROD, {"sid": sid})).all():
                wp.writerow([name, (sku or "").strip(), pr, ue, pe, os_])

            try:
                whs = await fetch_marketplace_seller_warehouses(c, api_token=token)
                names = {int(w["id"]): str(w.get("name") or w["id"]) for w in whs}
            except Exception as exc:                      # имя не критично
                print("склады не отдались:", name, exc); names = {}

            bound = sorted({int(b.wb_warehouse_id) for b in (await s.scalars(
                select(FbsWarehouseBinding).where(FbsWarehouseBinding.seller_id == sid))).all()})

            for pid, wid, vr, tr in (await s.execute(
                    SQL_ORD, {"sid": sid, "st": list(IN_WORK)})).all():
                p = by_id.get(pid)
                if p is None: continue
                wid = int(wid or 0)
                wo.writerow([name, wid, names.get(wid, str(wid)),
                             1 if wid in ours else 0, (p.sku_code or "").strip(), vr, tr])

            chrts = sorted(by_chrt)
            for wid in sorted(ours):
                got = 0
                for i in range(0, len(chrts), 1000):
                    batch = chrts[i:i + 1000]
                    for attempt in range(5):
                        try:
                            rows = await fetch_marketplace_stocks(
                                c, api_token=token, warehouse_id=wid, chrt_ids=batch)
                            for r in rows:
                                if int(r.amount) > 0:
                                    wc.writerow([name, wid, names.get(wid, str(wid)),
                                                 1 if wid in ours else 0,
                                                 by_chrt[int(r.chrt_id)].sku_code.strip(),
                                                 int(r.amount)])
                                    got += int(r.amount)
                            break
                        except WildberriesClientError as exc:
                            if attempt == 4:
                                print("ОШИБКА WB", name, wid, exc); break
                            await asyncio.sleep(3 * (attempt + 1))
                    await asyncio.sleep(1.5)
                print(f"  {name} склад {wid} ({names.get(wid,'?')}) "
                      f"{'НАШ' if wid in ours else 'чужой'}: {got} шт")
    for f in (fp, fc, fo): f.close()
    print("снято:", stamp)

asyncio.run(main())

# ЗАПУСК (только чтение, ничего не пишет в базу):
#   scp scripts/audit/sverka_fbs_sbor.py root@sellerfocus.pro:/tmp/
#   ssh root@sellerfocus.pro 'docker cp /tmp/sverka_fbs_sbor.py wms_prod-api-1:/tmp/ &&
#     docker exec wms_prod-api-1 sh -lc "cd /app && PYTHONPATH=/app python /tmp/sverka_fbs_sbor.py"'
#   забрать /tmp/out-products.csv, /tmp/out-cabinet.csv, /tmp/out-orders.csv
#   затем: python3 scripts/audit/sverka_fbs_excel.py
