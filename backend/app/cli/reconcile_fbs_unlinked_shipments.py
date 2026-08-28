"""Link proven delivered FBS orders to missing physical write-off movements."""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict, dataclass

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.fbs_order import FbsOrder
from app.models.fbs_shipment_reversal_ledger import FbsShipmentReversalLedger
from app.models.fbs_supply import FbsSupply
from app.models.product import Product
from app.models.seller import Seller
from app.services import inventory_service
from app.services.wb_marketplace_orders_service import _release_reservation


@dataclass(frozen=True)
class MissingShipment:
    order_id: str
    wb_order_id: int
    sku_code: str
    quantity: int


async def reconcile(
    *,
    seller_name: str,
    apply: bool,
    allow_negative: bool,
    expected_count: int | None,
) -> dict[str, object]:
    if apply and not allow_negative:
        raise ValueError("--apply requires explicit --allow-negative")
    if apply and expected_count is None:
        raise ValueError("--apply requires --expected-count")

    async with SessionLocal() as session:
        seller_ids = list(
            (
                await session.execute(select(Seller.id).where(Seller.name == seller_name))
            ).scalars()
        )
        if len(seller_ids) != 1:
            raise ValueError(
                f"seller name must resolve to exactly one row, found {len(seller_ids)}"
            )
        seller_id = seller_ids[0]
        rows = list(
            (
                await session.execute(
                    select(
                        FbsShipmentReversalLedger,
                        FbsOrder,
                        Product.sku_code,
                    )
                    .join(
                        FbsOrder,
                        FbsOrder.id == FbsShipmentReversalLedger.fbs_order_id,
                    )
                    .join(FbsSupply, FbsSupply.id == FbsOrder.supply_id)
                    .join(Product, Product.id == FbsShipmentReversalLedger.product_id)
                    .where(
                        Product.seller_id == seller_id,
                        FbsSupply.delivered_at.is_not(None),
                        FbsOrder.status.notin_(("cancelled", "defect")),
                        FbsShipmentReversalLedger.reversed_at.is_(None),
                        FbsShipmentReversalLedger.shipment_movement_id.is_(None),
                    )
                    .order_by(FbsOrder.wb_order_id)
                    .with_for_update()
                )
            ).all()
        )
        if apply and len(rows) != expected_count:
            raise ValueError(
                f"expected {expected_count} unlinked orders, found {len(rows)}"
            )

        result_rows = [
            MissingShipment(
                order_id=str(order.id),
                wb_order_id=int(order.wb_order_id),
                sku_code=sku_code,
                quantity=int(ledger.quantity),
            )
            for ledger, order, sku_code in rows
        ]
        if apply:
            for ledger, order, _sku_code in rows:
                movement = await inventory_service.apply_fbs_supply_write_off(
                    session,
                    tenant_id=ledger.tenant_id,
                    product_id=ledger.product_id,
                    storage_location_id=ledger.storage_location_id,
                    quantity=int(ledger.quantity),
                    # Сверочный скрипт запускают из консоли: пользователя системы
                    # здесь нет, и выдумывать автора движению нельзя.
                    actor_user_id=None,
                )
                await session.flush()
                ledger.shipment_movement_id = movement.id
                await _release_reservation(session, order)
            await session.commit()
        else:
            await session.rollback()

    return {
        "mode": "apply" if apply else "check",
        "seller_name": seller_name,
        "seller_id": str(seller_id),
        "orders": len(result_rows),
        "units": sum(row.quantity for row in result_rows),
        "rows": [asdict(row) for row in result_rows],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seller-name", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--allow-negative",
        action="store_true",
        help="allow balances to become negative for proven delivered units",
    )
    parser.add_argument("--expected-count", type=int)
    args = parser.parse_args()
    result = asyncio.run(
        reconcile(
            seller_name=args.seller_name,
            apply=args.apply,
            allow_negative=args.allow_negative,
            expected_count=args.expected_count,
        )
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
