import asyncio, json, uuid
from app.db.session import SessionLocal
from app.services.catalog_service import resolve_warehouse_scan
from app.services.scan_resolver_service import resolve_any_scan

T = uuid.UUID("82b36645-8662-497f-9631-a0743994632c")
cells = json.load(open("/tmp/wms539_prod_out.json", encoding="utf-8"))

async def main():
    ok1 = ok2 = 0
    bad = []
    async with SessionLocal() as s:
        for c in cells:
            kind, item = await resolve_warehouse_scan(s, T, c["barcode"])
            m = await resolve_any_scan(s, T, c["barcode"])
            if kind == "location" and item.code == c["code"]:
                ok1 += 1
            else:
                bad.append(("warehouses/resolve", c))
            if m.type == "cell" and m.name == f"Ячейка {c['code']}":
                ok2 += 1
            else:
                bad.append(("operations/scan/resolve", c, m))
        await s.rollback()
    print("resolve_warehouse_scan ok", ok1, "/", len(cells))
    print("resolve_any_scan ok", ok2, "/", len(cells))
    print("bad", bad[:3])

asyncio.run(main())
