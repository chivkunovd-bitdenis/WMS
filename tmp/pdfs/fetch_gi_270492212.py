import asyncio
import hashlib
import json
import uuid

import httpx
from sqlalchemy import text

from app.db.session import SessionLocal
from app.services.wildberries_client import fetch_marketplace_order_stickers
from app.services.wildberries_credentials_service import get_decrypted_marketplace_token


ORDER_IDS = [
    5602024577,
    5601375601,
    5602705945,
    5599586243,
    5600128772,
    5600556583,
    5599374172,
    5599567593,
]
TENANT_ID = uuid.UUID("7b98a8aa-c03c-4649-9677-a645be45c622")
SELLER_ID = uuid.UUID("bf8eea6b-eaa6-47ea-8dfc-289142372dab")


async def main() -> None:
    async with SessionLocal() as session:
        rows = (
            await session.execute(
                text(
                    """
                    SELECT
                        o.wb_order_id,
                        coalesce(p.wb_vendor_code, o.wb_article) AS article,
                        p.sku_code,
                        p.wb_size,
                        p.wb_barcode,
                        p.name AS product_name,
                        s.wb_supply_id,
                        se.name AS seller_name
                    FROM fbs_orders o
                    JOIN fbs_supplies s ON s.id = o.supply_id
                    JOIN sellers se ON se.id = o.seller_id
                    LEFT JOIN products p ON p.id = o.product_id
                    WHERE o.tenant_id = :tenant_id
                      AND o.seller_id = :seller_id
                      AND o.wb_order_id = ANY(:order_ids)
                    ORDER BY o.wb_order_id
                    """
                ),
                {
                    "tenant_id": TENANT_ID,
                    "seller_id": SELLER_ID,
                    "order_ids": ORDER_IDS,
                },
            )
        ).mappings().all()
        token = await get_decrypted_marketplace_token(session, TENANT_ID, SELLER_ID)
        if not token:
            raise RuntimeError("marketplace_token_missing")

    by_order = {int(row["wb_order_id"]): dict(row) for row in rows}
    missing_db = [order_id for order_id in ORDER_IDS if order_id not in by_order]
    if missing_db:
        raise RuntimeError(f"orders_missing_in_db:{missing_db}")
    if {row["wb_supply_id"] for row in by_order.values()} != {"WB-GI-270492212"}:
        raise RuntimeError("supply_scope_mismatch")

    async with httpx.AsyncClient(timeout=30.0) as client:
        sticker_rows = await fetch_marketplace_order_stickers(
            client,
            api_token=token,
            order_ids=ORDER_IDS,
            width=58,
            height=40,
        )

    stickers = {}
    for row in sticker_rows:
        order_id = int(row.get("orderId") or row.get("order_id"))
        file_payload = row.get("file")
        if not isinstance(file_payload, str) or not file_payload:
            raise RuntimeError(f"sticker_file_missing:{order_id}")
        stickers[order_id] = {
            "partA": row.get("partA") or row.get("part_a"),
            "partB": row.get("partB") or row.get("part_b"),
            "barcode": row.get("barcode") or row.get("sticker_barcode"),
            "png_base64": file_payload,
            "png_base64_sha256": hashlib.sha256(file_payload.encode("ascii")).hexdigest(),
        }
    missing_api = [order_id for order_id in ORDER_IDS if order_id not in stickers]
    if missing_api:
        raise RuntimeError(f"orders_missing_in_wb_api:{missing_api}")

    output = {
        "source": "WB Marketplace API POST /api/v3/orders/stickers",
        "supply": "WB-GI-270492212",
        "tenant_id": str(TENANT_ID),
        "seller_id": str(SELLER_ID),
        "seller_name": next(iter(by_order.values()))["seller_name"],
        "orders": [
            {**by_order[order_id], "sticker": stickers[order_id]}
            for order_id in ORDER_IDS
        ],
    }
    with open("/tmp/gi_270492212_payload.json", "w", encoding="utf-8") as stream:
        json.dump(output, stream, ensure_ascii=False, indent=2)
    print(
        json.dumps(
            {
                "supply": output["supply"],
                "seller_name": output["seller_name"],
                "requested": len(ORDER_IDS),
                "returned": len(stickers),
                "order_ids": ORDER_IDS,
                "png_sha256": {
                    str(order_id): stickers[order_id]["png_base64_sha256"]
                    for order_id in ORDER_IDS
                },
            },
            ensure_ascii=False,
            indent=2,
        )
    )


asyncio.run(main())
