"""Persist Wildberries FBW supply list snapshots."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.seller import Seller
from app.models.seller_wildberries_imported_supply import SellerWildberriesImportedSupply


def external_key_from_supply_row(row: dict[str, Any]) -> str | None:
    sid = row.get("supplyID")
    if sid is not None and sid != "":
        try:
            return f"s:{int(sid)}"
        except (TypeError, ValueError):
            return None
    pid = row.get("preorderID")
    if pid is not None and pid != "":
        try:
            return f"p:{int(pid)}"
        except (TypeError, ValueError):
            return None
    return None


def _int_or_none(val: object) -> int | None:
    if val is None or val == "":
        return None
    if isinstance(val, bool):
        return None
    if isinstance(val, int):
        return val
    if isinstance(val, float) and val.is_integer():
        return int(val)
    if isinstance(val, str) and val.strip().isdigit():
        return int(val.strip())
    return None


async def upsert_imported_supplies(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    rows: list[Any],
) -> int:
    seller = await session.get(Seller, seller_id)
    if seller is None or seller.tenant_id != tenant_id:
        return 0
    now = datetime.now(tz=UTC)
    n = 0
    for item in rows:
        if not isinstance(item, dict):
            continue
        ext = external_key_from_supply_row(item)
        if ext is None:
            continue
        supply_id = _int_or_none(item.get("supplyID"))
        preorder_id = _int_or_none(item.get("preorderID"))
        status_id = _int_or_none(item.get("statusID"))
        stmt = select(SellerWildberriesImportedSupply).where(
            SellerWildberriesImportedSupply.seller_id == seller_id,
            SellerWildberriesImportedSupply.external_key == ext,
        )
        res = await session.execute(stmt)
        row = res.scalar_one_or_none()
        raw: dict[str, Any] = item
        if row is None:
            session.add(
                SellerWildberriesImportedSupply(
                    tenant_id=tenant_id,
                    seller_id=seller_id,
                    external_key=ext,
                    wb_supply_id=supply_id,
                    wb_preorder_id=preorder_id,
                    status_id=status_id,
                    raw_json=raw,
                    updated_at=now,
                )
            )
        else:
            row.wb_supply_id = supply_id
            row.wb_preorder_id = preorder_id
            row.status_id = status_id
            row.raw_json = raw
            row.updated_at = now
        n += 1
    await session.flush()
    return n


async def list_imported_supplies_for_seller(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
) -> list[SellerWildberriesImportedSupply] | None:
    seller = await session.get(Seller, seller_id)
    if seller is None or seller.tenant_id != tenant_id:
        return None
    stmt = (
        select(SellerWildberriesImportedSupply)
        .where(SellerWildberriesImportedSupply.seller_id == seller_id)
        .order_by(SellerWildberriesImportedSupply.external_key)
    )
    res = await session.execute(stmt)
    return list(res.scalars().all())
