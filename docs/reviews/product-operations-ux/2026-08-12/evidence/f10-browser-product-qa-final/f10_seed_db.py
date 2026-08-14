from __future__ import annotations

import argparse
import asyncio
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select

from app.db.session import SessionLocal
from app.models.fbs_order import FbsOrder, FbsOrderReservation
from app.models.fbs_stock_sync_item import FbsStockSyncItem
from app.models.fbs_warehouse_binding import FbsWarehouseBinding
from app.models.inventory_balance import InventoryBalance
from app.models.product import Product
from app.models.seller_wildberries_credentials import SellerWildberriesCredentials
from app.models.stock_direction import StockDirection
from app.services.integration_fernet import encrypt_secret


def _uuid(value: str) -> uuid.UUID:
    return uuid.UUID(value)


async def _ensure_binding(
    *,
    session,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    wb_warehouse_id: int,
    wms_warehouse_id: uuid.UUID,
) -> str:
    existing = await session.scalar(
        select(FbsWarehouseBinding).where(
            FbsWarehouseBinding.seller_id == seller_id,
            FbsWarehouseBinding.wb_warehouse_id == wb_warehouse_id,
        )
    )
    if existing is None:
        existing = FbsWarehouseBinding(
            tenant_id=tenant_id,
            seller_id=seller_id,
            wb_warehouse_id=wb_warehouse_id,
            wms_warehouse_id=wms_warehouse_id,
            is_active=True,
            stock_sync_enabled=True,
        )
        session.add(existing)
        await session.flush()
    else:
        existing.tenant_id = tenant_id
        existing.wms_warehouse_id = wms_warehouse_id
        existing.is_active = True
        existing.stock_sync_enabled = True
        existing.lease_until = None
    return str(existing.id)


async def _main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--payload", required=True)
    args = parser.parse_args()
    payload: dict[str, Any] = json.loads(args.payload)

    seller_id = _uuid(payload["seller_id"])
    product_id = _uuid(payload["product_id"])
    warehouse_id = _uuid(payload["warehouse_id"])
    location_id = _uuid(payload["location_id"])
    chrt_id = int(payload["chrt_id"])
    wb_warehouse_id = int(payload["wb_warehouse_id"])
    nm_id = int(payload["nm_id"])
    barcode = str(payload["barcode"])
    token = str(payload["marketplace_token"])

    async with SessionLocal() as session:
        product = await session.get(Product, product_id)
        if product is None:
            raise RuntimeError(f"product not found: {product_id}")
        tenant_id = product.tenant_id
        if product.seller_id != seller_id:
            raise RuntimeError("product seller mismatch")

        product.wb_nm_id = nm_id
        product.wb_chrt_id = chrt_id
        product.wb_barcode = barcode
        product.wb_vendor_code = payload.get("vendor_code") or product.wb_vendor_code
        product.wb_size = payload.get("wb_size") or product.wb_size
        product.fbs_stock_sync_enabled = True

        creds = await session.get(SellerWildberriesCredentials, seller_id)
        if creds is None:
            creds = SellerWildberriesCredentials(seller_id=seller_id)
            session.add(creds)
        encrypted = encrypt_secret(token)
        creds.marketplace_token_encrypted = encrypted
        creds.supplies_token_encrypted = encrypted

        await session.execute(
            delete(FbsStockSyncItem).where(FbsStockSyncItem.product_id == product_id)
        )
        await session.execute(
            delete(StockDirection).where(
                StockDirection.tenant_id == tenant_id,
                StockDirection.product_id == product_id,
            )
        )
        await session.execute(
            delete(FbsOrderReservation).where(
                FbsOrderReservation.tenant_id == tenant_id,
                FbsOrderReservation.product_id == product_id,
            )
        )
        await session.execute(
            delete(FbsOrder).where(
                FbsOrder.tenant_id == tenant_id,
                FbsOrder.product_id == product_id,
            )
        )

        balance = await session.scalar(
            select(InventoryBalance).where(
                InventoryBalance.tenant_id == tenant_id,
                InventoryBalance.product_id == product_id,
                InventoryBalance.storage_location_id == location_id,
            )
        )
        if balance is None:
            balance = InventoryBalance(
                tenant_id=tenant_id,
                product_id=product_id,
                storage_location_id=location_id,
                quantity=int(payload["physical_stock"]),
                quantity_unpacked=int(payload["physical_stock"]),
                quantity_packed=0,
            )
            session.add(balance)
        else:
            balance.quantity = int(payload["physical_stock"])
            balance.quantity_unpacked = int(payload["physical_stock"])
            balance.quantity_packed = 0

        session.add(
            StockDirection(
                tenant_id=tenant_id,
                product_id=product_id,
                name=str(payload.get("fbs_direction_name") or "F10 FBS pool"),
                quantity=int(payload["fbs_pool"]),
                is_fbs=True,
            )
        )
        reserve_pool = int(payload.get("reserve_pool") or 0)
        if reserve_pool > 0:
            session.add(
                StockDirection(
                    tenant_id=tenant_id,
                    product_id=product_id,
                    name=str(payload.get("reserve_direction_name") or "F10 non-FBS reserve"),
                    quantity=reserve_pool,
                    is_fbs=False,
                )
            )

        binding_ids = [
            await _ensure_binding(
                session=session,
                tenant_id=tenant_id,
                seller_id=seller_id,
                wb_warehouse_id=wb_warehouse_id,
                wms_warehouse_id=warehouse_id,
            )
        ]
        second_warehouse = payload.get("second_warehouse_id")
        second_wb = payload.get("second_wb_warehouse_id")
        if second_warehouse and second_wb:
            binding_ids.append(
                await _ensure_binding(
                    session=session,
                    tenant_id=tenant_id,
                    seller_id=seller_id,
                    wb_warehouse_id=int(second_wb),
                    wms_warehouse_id=_uuid(str(second_warehouse)),
                )
            )

        active_reservation = int(payload.get("active_fbs_reservation") or 0)
        order_id: str | None = None
        if active_reservation > 0:
            order = FbsOrder(
                tenant_id=tenant_id,
                seller_id=seller_id,
                warehouse_id=warehouse_id,
                product_id=product_id,
                wb_order_id=int(payload["wb_order_id"]),
                wb_nm_id=nm_id,
                wb_chrt_id=chrt_id,
                wb_barcode=barcode,
                created_at_wb=datetime.now(UTC),
                deadline_at=datetime.now(UTC),
                mapping_status="mapped",
                reserve_status="reserved",
            )
            session.add(order)
            await session.flush()
            order_id = str(order.id)
            session.add(
                FbsOrderReservation(
                    tenant_id=tenant_id,
                    fbs_order_id=order.id,
                    product_id=product_id,
                    warehouse_id=warehouse_id,
                    quantity=active_reservation,
                )
            )

        await session.commit()

    print(
        json.dumps(
            {
                "tenant_id": str(tenant_id),
                "seller_id": str(seller_id),
                "product_id": str(product_id),
                "warehouse_id": str(warehouse_id),
                "location_id": str(location_id),
                "binding_ids": binding_ids,
                "order_id": order_id,
                "chrt_id": chrt_id,
                "wb_warehouse_id": wb_warehouse_id,
                "physical_stock": int(payload["physical_stock"]),
                "fbs_pool": int(payload["fbs_pool"]),
                "reserve_pool": reserve_pool,
                "active_fbs_reservation": active_reservation,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    asyncio.run(_main())
