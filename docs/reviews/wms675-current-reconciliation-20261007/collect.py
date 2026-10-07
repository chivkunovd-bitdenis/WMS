"""Read-only Bamboo reconciliation, run inside the configured production backend.

Only SELECT and Ozon information endpoints. Outputs business evidence only.
No synchronization, stock publication, credentials output, or database commit.
"""
import asyncio
import json
import uuid
from datetime import datetime, timezone

import httpx
from sqlalchemy import text

from app.core.settings import settings
from app.db.session import SessionLocal
from app.services.marketplace_account_service import MarketplaceAccountService
from app.services.ozon_marketplace_transport import HttpxOzonMarketplaceTransport
from app.services.ozon_provider_factory import build_ozon_provider, ozon_live_api_enabled

TENANT = uuid.UUID("b80a893b-ab87-42b6-8fd7-6d41502c900f")
SELLER = uuid.UUID("cf6d31c5-944b-4382-af34-636ca9aa8cc3")
COUNT = "47368c8f-96dc-4955-a8ea-030b88cd6cb3"


async def collect():
    assert ozon_live_api_enabled()
    assert settings.ozon_seller_api_base.rstrip("/") == "https://api-seller.ozon.ru"
    evidence = {"started_at": datetime.now(timezone.utc).isoformat(), "tenant": str(TENANT), "seller": str(SELLER), "mutations": 0}
    async with SessionLocal() as session:
        await session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
        queries = {
            "counts": "SELECT c.id,c.status,c.posted_at,c.created_at,c.comment,c.created_by_user_id,c.posted_by_user_id,p.sku_code,l.id AS line_id,l.product_id,l.expected_quantity,l.actual_quantity,l.posted_delta,l.storage_location_id FROM inventory_counts c JOIN inventory_count_lines l ON l.count_id=c.id JOIN products p ON p.id=l.product_id WHERE c.tenant_id=:tenant AND p.seller_id=:seller ORDER BY c.created_at,p.sku_code",
            "products": "SELECT p.id,p.sku_code,p.name,l.external_product_id,l.external_sku,l.external_offer_id FROM products p JOIN product_marketplace_links l ON l.product_id=p.id AND l.marketplace='ozon' AND l.is_active WHERE p.tenant_id=:tenant AND p.seller_id=:seller ORDER BY p.sku_code",
            "balances": "SELECT b.id,b.product_id,b.storage_location_id,b.container_kind,b.container_id,b.quantity,b.quantity_unpacked,b.quantity_packed,b.updated_at FROM inventory_balances b JOIN products p ON p.id=b.product_id WHERE b.tenant_id=:tenant AND p.seller_id=:seller ORDER BY b.product_id,b.id",
            "movements": "SELECT m.id,m.product_id,m.quantity_delta,m.movement_type,m.created_at,m.storage_location_id,m.warehouse_id,m.inbound_intake_line_id,m.inventory_count_line_id,m.outbound_shipment_line_id FROM inventory_movements m JOIN products p ON p.id=m.product_id WHERE m.tenant_id=:tenant AND p.seller_id=:seller ORDER BY m.created_at,m.id",
            "orders": "SELECT o.id,o.external_order_id,o.status,o.wb_status,o.reserve_status,o.supply_id,o.warehouse_id,o.created_at,o.created_at_wb,op.id AS position_id,op.product_id,op.ozon_sku,op.offer_id,op.quantity,op.reserved_quantity,op.picked_quantity FROM fbs_orders o JOIN fbs_order_products op ON op.order_id=o.id WHERE o.tenant_id=:tenant AND o.seller_id=:seller AND o.marketplace='ozon' ORDER BY o.external_order_id,op.id",
            "supplies": "SELECT id,name,source,status,warehouse_id,created_at,delivered_at,external_supply_id FROM fbs_supplies WHERE tenant_id=:tenant AND seller_id=:seller ORDER BY created_at",
            "ledgers": "SELECT l.id,l.fbs_order_id,l.product_id,l.quantity,l.ozon_positions_json,l.shipment_movement_id,l.written_off_at,l.reversed_at,l.reversal_movement_id,l.wb_operation_id FROM fbs_shipment_reversal_ledger l JOIN fbs_orders o ON o.id=l.fbs_order_id WHERE o.tenant_id=:tenant AND o.seller_id=:seller ORDER BY o.id,l.id",
            "reservations": "SELECT r.id,r.order_product_id,r.warehouse_id,r.quantity FROM fbs_order_product_reservations r JOIN fbs_order_products op ON op.id=r.order_product_id JOIN fbs_orders o ON o.id=op.order_id WHERE o.tenant_id=:tenant AND o.seller_id=:seller ORDER BY r.id",
            "legacy_reservations": "SELECT r.id,r.fbs_order_id,r.warehouse_id,r.quantity FROM fbs_order_reservations r JOIN fbs_orders o ON o.id=r.fbs_order_id WHERE o.tenant_id=:tenant AND o.seller_id=:seller ORDER BY r.id",
        }
        for name, query in queries.items():
            try:
                rows = (await session.execute(text(query), {"tenant": TENANT, "seller": SELLER})).mappings().all()
            except Exception as exc:
                raise RuntimeError("query_" + name) from exc
            assert len(rows) < 5000, name
            evidence[name] = [dict(row) for row in rows]
        client_id, api_key = await MarketplaceAccountService(session).stored_credentials(TENANT, SELLER)
        await session.rollback()
    cutoff = next(row["posted_at"] for row in evidence["counts"] if str(row["id"]) == COUNT)
    movements = {row["id"]: row for row in evidence["movements"]}
    late_orders = set()
    for ledger in evidence["ledgers"]:
        ids = {ledger["shipment_movement_id"]}
        ids.update(uuid.UUID(row["movement_id"]) for row in ledger["ozon_positions_json"] or [] if row.get("movement_id"))
        if any(mid in movements and movements[mid]["created_at"] > cutoff for mid in ids):
            late_orders.add(ledger["fbs_order_id"])
    orders = {row["id"]: row for row in evidence["orders"]}
    candidates = [row for oid, row in orders.items() if (oid in late_orders and (row["created_at_wb"] or row["created_at"]) < cutoff) or (row["supply_id"] is None and row["reserved_quantity"] > 0 and row["status"] == "in_delivery")]
    assert len(candidates) < 150
    evidence["cards"] = []
    evidence["stocks"] = []
    async with httpx.AsyncClient(timeout=30) as client:
        provider = build_ozon_provider()
        assert isinstance(provider.transport, HttpxOzonMarketplaceTransport)
        provider.transport = HttpxOzonMarketplaceTransport(client=client)
        for order in candidates:
            entry = {"order_id": str(order["id"]), "posting_number": order["external_order_id"]}
            try:
                raw = await provider.call(client_id=client_id, api_key=api_key, path="/v3/posting/fbs/get", payload={"posting_number": order["external_order_id"], "with": {"analytics_data": False, "financial_data": False}})
                card = raw["result"]
                entry["card"] = {key: card.get(key) for key in ("posting_number", "status", "substatus", "in_process_at", "shipment_date", "delivering_date", "fact_delivery_date", "related_postings", "related_weight_postings")}
                entry["card"]["warehouse_id"] = card.get("delivery_method", {}).get("warehouse_id")
                entry["card"]["products"] = [{key: product.get(key) for key in ("sku", "offer_id", "quantity")} for product in card.get("products", [])]
            except Exception as exc:
                entry["error_type"] = type(exc).__name__
            evidence["cards"].append(entry)
        cursor = ""
        for _ in range(5):
            raw = await provider.call(client_id=client_id, api_key=api_key, path="/v2/product/info/stocks-by-warehouse/fbs", payload={"sku": [row["external_sku"] for row in evidence["products"]], "limit": 100, "cursor": cursor})
            evidence["stocks"].extend(raw["products"])
            if not raw.get("has_next"):
                break
            cursor = raw["cursor"]
        else:
            raise RuntimeError("pagination_incomplete")
    evidence["finished_at"] = datetime.now(timezone.utc).isoformat()
    print(json.dumps(evidence, ensure_ascii=False, default=str))


if __name__ == "__main__":
    try:
        asyncio.run(collect())
    except Exception as exc:
        print(json.dumps({"error_type": type(exc).__name__, "query": str(exc) if isinstance(exc, RuntimeError) else None, "details_suppressed": True}))
        raise SystemExit(2)
