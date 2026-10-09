"""Read-only FBS order counts derived from the complete list selections."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, or_, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fbs_order import FbsOrder
from app.models.fbs_supply import FbsSupply
from app.models.seller import Seller
from app.services.fbs_supply_service import select_worklist_supplies, supply_worklist_statement
from app.services.fbs_worklist_service import STATUS_GROUP_MAP, orders_worklist_statement


async def fetch_fbs_counts(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    seller_id: uuid.UUID | None = None,
    effective_seller_id: uuid.UUID | None = None,
    marketplace: str | None = None,
    status_group: str = "new",
    wb_warehouse_id: int | None = None,
    search: str | None = None,
) -> dict[str, dict[str, int]]:
    if status_group not in STATUS_GROUP_MAP:
        raise ValueError("invalid_status_group")
    seller_stmt = select(Seller.id).where(Seller.tenant_id == tenant_id)
    if effective_seller_id is not None:
        seller_stmt = seller_stmt.where(Seller.id == effective_seller_id)
    seller_ids = list((await session.scalars(seller_stmt)).all())
    now = datetime.now(tz=UTC)
    counts: dict[str, dict[uuid.UUID, int]] = {}
    for group in dict.fromkeys(("new", "active", "delivery", status_group)):
        orders = orders_worklist_statement(
            tenant_id, seller_id=effective_seller_id, marketplace=marketplace,
            status_group=group, search=search, server_now=now,
            wb_warehouse_id=wb_warehouse_id if group == "new" and status_group == "new" else None,
        )
        members = orders.with_only_columns(FbsOrder.id, FbsOrder.seller_id)
        if group in {"active", "delivery", "done"}:
            supplies = supply_worklist_statement(
                tenant_id, seller_id=effective_seller_id, marketplace=marketplace,
                status_group=group, search=search,
            ).where(FbsSupply.marketplace != "ozon").with_only_columns(FbsSupply.id).subquery()
            # WMS-721: the tab of an Ozon supply follows its postings, so the
            # same derived selection as the list rows picks the Ozon supplies.
            ozon_matched, _ = await select_worklist_supplies(
                session,
                supply_worklist_statement(
                    tenant_id, seller_id=effective_seller_id, marketplace=marketplace,
                    status_group=group, search=search, ozon_candidates=True,
                ).where(FbsSupply.marketplace == "ozon"),
                status_group=group, limit=None, stop_at_limit=False, with_details=False,
            )
            ozon_ids = [supply.id for supply in ozon_matched]
            # Every linked order is counted, just as orders_count on a matched
            # supply row. Only unlinked orders use the order-level selection.
            linked = select(FbsOrder.id, FbsSupply.seller_id).join(
                FbsSupply, FbsOrder.supply_id == FbsSupply.id
            ).where(
                or_(FbsSupply.id.in_(select(supplies.c.id)), FbsSupply.id.in_(ozon_ids)),
                FbsOrder.tenant_id == tenant_id,
            )
            rows = union_all(linked, members.where(FbsOrder.supply_id.is_(None))).subquery()
        else:
            rows = members.subquery()
        counted = await session.execute(
            select(rows.c.seller_id, func.count(rows.c.id)).group_by(rows.c.seller_id)
        )
        counts[group] = {identifier: int(total) for identifier, total in counted.all()}
    selected_seller = effective_seller_id if effective_seller_id is not None else seller_id
    return {
        "tabs": {
            group: counts[group].get(selected_seller, 0)
            if selected_seller is not None else sum(counts[group].values())
            for group in ("new", "active", "delivery")
        },
        "sellers": {
            str(identifier): counts[status_group].get(identifier, 0) for identifier in seller_ids
        },
    }
