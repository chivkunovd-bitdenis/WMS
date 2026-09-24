"""Explicitly authorized AVpack repair. Dry-run by default; run in API environment.

Only attach already imported codes to per-upload/product/GTIN pools. Never issue,
print, change a status, modify a PDF or call a marketplace. Document events retain
the exact code IDs and original null pool assignment for an auditable rollback.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import uuid
from collections import defaultdict

from sqlalchemy import text

from app.db.session import SessionLocal
from app.models.document_event import DOCUMENT_TYPE_MARKING_POOL, EVENT_DATA_CHANGED
from app.services.document_event_service import record_document_mutation
from app.services.marking_code_service import count_available_for_products_batch

TENANT = uuid.UUID("d6e1ad21-8afa-4acf-8d0b-907b9f2adcfe")
SCOPE = """
SELECT mc.id, mc.seller_id, mc.product_id, mc.import_batch_id, mc.gtin,
       mc.status, mc.source, mc.created_at, p.sku_code, b.filename,
       p.tenant_id AS product_tenant, p.seller_id AS product_seller,
       b.tenant_id AS batch_tenant, b.seller_id AS batch_seller,
       md5((to_jsonb(mc) - 'pool_id')::text) AS unchanged_fingerprint
FROM marking_codes mc
LEFT JOIN products p ON p.id=mc.product_id
LEFT JOIN marking_code_imports b ON b.id=mc.import_batch_id
WHERE mc.tenant_id=:tenant AND mc.pool_id IS NULL
ORDER BY mc.id
"""


async def main(apply: bool, expected_count: int, expected_groups: int) -> None:
    async with SessionLocal() as session:
        async with session.begin():
            await session.execute(text("SET LOCAL lock_timeout='2s'"))
            await session.execute(text("SET LOCAL statement_timeout='20s'"))
            if not apply:
                await session.execute(text("SET TRANSACTION READ ONLY"))
            tenant_name = await session.scalar(
                text("SELECT name FROM tenants WHERE id=:tenant"), {"tenant": TENANT}
            )
            assert tenant_name == "AVpack", "Unexpected tenant"
            rows = list((await session.execute(
                text(SCOPE + (" FOR UPDATE OF mc" if apply else "")),
                {"tenant": TENANT},
            )).mappings())
            groups = defaultdict(list)
            for row in rows:
                assert row["source"] == "pool" and row["status"] == "available"
                assert row["product_id"] and row["import_batch_id"] and row["gtin"]
                assert row["product_tenant"] == row["batch_tenant"] == TENANT
                assert row["product_seller"] == row["batch_seller"] == row["seller_id"]
                key = (row["seller_id"], row["import_batch_id"], row["product_id"], row["gtin"])
                groups[key].append(row)
            print(json.dumps({"mode": "apply" if apply else "dry-run", "codes": len(rows),
                              "groups": len(groups), "products": len({r['product_id'] for r in rows})}))
            if not rows:
                return
            assert len(rows) == expected_count, "Scope changed: inspect before applying"
            assert len(groups) == expected_groups, "Grouping changed: inspect before applying"
            products = {row["product_id"] for row in rows}
            before = await count_available_for_products_batch(session, TENANT, products)
            if not apply:
                print(json.dumps([{"sku": items[0]["sku_code"], "import": str(key[1]),
                                   "count": len(items)} for key, items in groups.items()], ensure_ascii=False))
                return
            for key, items in groups.items():
                seller, batch, product, gtin = key
                pool = uuid.uuid5(uuid.NAMESPACE_URL, "WMS-523/" + "/".join(map(str, (TENANT, *key))))
                title = f"{items[0]['sku_code']} — {items[0]['filename']}"[:512]
                await session.execute(text("""
                    INSERT INTO marking_pools(id,tenant_id,seller_id,gtin,title,created_at)
                    VALUES(:id,:tenant,:seller,:gtin,:title,:created)
                """), {"id": pool, "tenant": TENANT, "seller": seller, "gtin": gtin,
                        "title": title, "created": min(r["created_at"] for r in items)})
                await session.execute(text("""
                    INSERT INTO marking_pool_products(id,tenant_id,pool_id,product_id)
                    VALUES(:id,:tenant,:pool,:product)
                """), {"id": uuid.uuid4(), "tenant": TENANT, "pool": pool, "product": product})
                code_ids = [r["id"] for r in items]
                result = await session.execute(text("""
                    UPDATE marking_codes SET pool_id=:pool
                    WHERE tenant_id=:tenant AND id=ANY(:ids) AND pool_id IS NULL
                """), {"pool": pool, "tenant": TENANT, "ids": code_ids})
                assert result.rowcount == len(items)
                recorded = await record_document_mutation(
                    session, tenant_id=TENANT, document_type=DOCUMENT_TYPE_MARKING_POOL,
                    document_id=pool, event_type=EVENT_DATA_CHANGED, product_id=product,
                    qty=len(items),
                    before={"pool_id": None, "code_ids": [str(x) for x in code_ids]},
                    after={"pool_id": str(pool), "import_batch_id": str(batch),
                           "task": "WMS-523", "reason": "Owner-authorized AVpack pool repair"},
                )
                assert recorded, "Audit record must be persisted with the repair"
            check = (await session.execute(text("""
                SELECT id, md5((to_jsonb(mc) - 'pool_id')::text) AS fingerprint
                FROM marking_codes mc WHERE tenant_id=:tenant AND id=ANY(:ids)
            """), {"tenant": TENANT, "ids": [r["id"] for r in rows]})).mappings()
            assert {r["id"]: r["fingerprint"] for r in check} == {
                r["id"]: r["unchanged_fingerprint"] for r in rows
            }, "A field other than pool_id changed"
            after = await count_available_for_products_batch(session, TENANT, products)
            print(json.dumps({"catalog_before": {str(k): v for k, v in before.items()},
                              "catalog_after": {str(k): v for k, v in after.items()}}))
        print("COMMITTED: only pool assignments, new pools/product links and audit events")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--expected-count", type=int, default=408)
    parser.add_argument("--expected-groups", type=int, default=27)
    args = parser.parse_args()
    asyncio.run(main(args.apply, args.expected_count, args.expected_groups))
