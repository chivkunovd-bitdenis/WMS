import asyncio
import json

from sqlalchemy import text

from app.db.session import SessionLocal


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


async def main() -> None:
    async with SessionLocal() as session:
        orders = (
            await session.execute(
                text(
                    """
                    SELECT
                        o.id::text AS local_order_id,
                        o.wb_order_id,
                        o.tenant_id::text,
                        o.seller_id::text,
                        se.name AS seller_name,
                        s.wb_supply_id,
                        o.status,
                        o.supplier_status,
                        o.sticker_code,
                        o.sticker_barcode,
                        coalesce(p.wb_vendor_code, o.wb_article) AS article,
                        p.sku_code,
                        p.wb_size,
                        p.wb_barcode,
                        p.name AS product_name
                    FROM fbs_orders o
                    LEFT JOIN sellers se ON se.id = o.seller_id
                    LEFT JOIN fbs_supplies s ON s.id = o.supply_id
                    LEFT JOIN products p ON p.id = o.product_id
                    WHERE o.wb_order_id = ANY(:order_ids)
                    ORDER BY o.wb_order_id
                    """
                ),
                {"order_ids": ORDER_IDS},
            )
        ).mappings().all()
        products = (
            await session.execute(
                text(
                    """
                    SELECT
                        p.id::text AS product_id,
                        p.tenant_id::text,
                        p.seller_id::text,
                        se.name AS seller_name,
                        p.name,
                        p.sku_code,
                        p.wb_vendor_code,
                        p.wb_size,
                        p.wb_barcode,
                        p.wb_nm_id
                    FROM products p
                    LEFT JOIN sellers se ON se.id = p.seller_id
                    WHERE p.tenant_id IN (
                        SELECT DISTINCT tenant_id
                        FROM fbs_orders
                        WHERE wb_order_id = ANY(:order_ids)
                    )
                      AND (
                          p.sku_code ILIKE ANY(:patterns)
                          OR coalesce(p.wb_vendor_code, '') ILIKE ANY(:patterns)
                      )
                    ORDER BY coalesce(p.wb_vendor_code, p.sku_code), p.wb_size
                    """
                ),
                {
                    "order_ids": ORDER_IDS,
                    "patterns": ["%6720-8%", "%6731-11%", "%6720-5%", "%6731-1%"],
                },
            )
        ).mappings().all()
    print(
        json.dumps(
            {
                "requested_order_ids": ORDER_IDS,
                "orders": [dict(row) for row in orders],
                "products": [dict(row) for row in products],
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )


asyncio.run(main())
