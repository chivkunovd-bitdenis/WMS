"""Late validation must allow only the exact explicitly selected WB reprint."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from test_fbs_kiz import _register_ff_admin, _setup_seller_warehouse

from app.models.fbs_order import (
    FBS_ORDER_STATUS_IN_DELIVERY,
    MAPPING_STATUS_MAPPED,
    MARKING_KIND_SGTIN,
    META_STATUS_ACCEPTED,
    META_STATUS_REJECTED,
    RESERVE_STATUS_RESERVED,
    FbsOrder,
    FbsOrderMarking,
)
from app.models.fbs_supply import FBS_DELIVERY_TYPE_WAREHOUSE_SC, FBS_SUPPLY_STATUS_DONE, FbsSupply
from app.models.marking_code import MarkingCode, MarkingCodeEvent
from app.models.product import Product


async def test_exact_rejected_wb_inline_reprint_is_validated_without_replacement(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_warehouse(
        async_client, headers, suffix,
    )
    product = Product(
        tenant_id=tenant_id,
        seller_id=seller_id,
        name="Exact rejected KIZ reprint",
        sku_code=f"reprint-{suffix}",
        requires_honest_sign=True,
    )
    supply = FbsSupply(
        tenant_id=tenant_id,
        seller_id=seller_id,
        warehouse_id=warehouse_id,
        wb_supply_id=f"WB-REPRINT-{suffix}",
        marketplace="wb",
        name="Completed WB supply for exact reprint",
        status=FBS_SUPPLY_STATUS_DONE,
        delivery_type=FBS_DELIVERY_TYPE_WAREHOUSE_SC,
    )
    now = datetime.now(UTC)
    order = FbsOrder(
        tenant_id=tenant_id,
        seller_id=seller_id,
        warehouse_id=warehouse_id,
        product=product,
        supply=supply,
        marketplace="wb",
        wb_order_id=700_000_000 + int(suffix[-8:], 16) % 100_000_000,
        wb_rid=f"reprint-{suffix}",
        created_at_wb=now,
        deadline_at=now + timedelta(days=1),
        mapping_status=MAPPING_STATUS_MAPPED,
        reserve_status=RESERVE_STATUS_RESERVED,
        status=FBS_ORDER_STATUS_IN_DELIVERY,
        required_meta_json=[MARKING_KIND_SGTIN],
    )
    db_session.add_all([product, supply, order])
    await db_session.flush()
    cis_code = "010460123456789021REPRINT81"
    code = MarkingCode(
        tenant_id=tenant_id,
        seller_id=seller_id,
        product_id=product.id,
        cis_code=cis_code,
        source="pool",
        status="printed",
    )
    marking = FbsOrderMarking(
        tenant_id=tenant_id,
        order_id=order.id,
        kind=MARKING_KIND_SGTIN,
        value=cis_code,
        source="pool",
        meta_status=META_STATUS_REJECTED,
        reason="damaged label; CIS remains bound",
        marking_code=code,
    )
    db_session.add(marking)
    await db_session.commit()
    order_id, supply_id = order.id, supply.id
    marking_id, code_id = marking.id, code.id

    before_codes = await db_session.scalar(
        select(func.count()).select_from(MarkingCode).where(MarkingCode.tenant_id == tenant_id)
    )
    before_markings = await db_session.scalar(
        select(func.count())
        .select_from(FbsOrderMarking)
        .where(FbsOrderMarking.order_id == order_id)
    )
    printed = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/order-print-tape",
        headers=headers,
        json={
            "order_ids": [str(order_id)],
            "include_order_qr": False,
            "reprint": True,
            "reprint_marking_ids": [str(marking_id)],
            "layout_json": {"units": [{"block": "cz", "copies": 1}]},
        },
    )
    assert printed.status_code == 200, printed.text
    result = printed.json()["orders"][0]
    assert result["codes"] == [cis_code]
    assert [row["marking_id"] for row in result["printed_codes"]] == [str(marking_id)]
    selected_binding = {
        "order_id": result["order_id"],
        "supply_id": result["printed_codes"][0]["supply_id"],
        "marking_id": result["printed_codes"][0]["marking_id"],
        "cis_code": result["printed_codes"][0]["cis_code"],
    }

    explicit_validation = await async_client.post(
        "/operations/fbs-orders/print-bindings/validate",
        headers=headers,
        json={
            "bindings": [selected_binding],
            "reprint_marking_ids": [str(marking_id)],
        },
    )
    assert explicit_validation.status_code == 204, explicit_validation.text

    ordinary_validation = await async_client.post(
        "/operations/fbs-orders/print-bindings/validate",
        headers=headers,
        json={"bindings": [selected_binding]},
    )
    assert ordinary_validation.status_code == 409

    db_session.expire_all()
    stored_code = await db_session.scalar(
        select(MarkingCode).where(MarkingCode.id == code_id)
    )
    stored_marking = await db_session.scalar(
        select(FbsOrderMarking).where(FbsOrderMarking.id == marking_id)
    )
    assert stored_code and stored_code.cis_code == cis_code and stored_code.status == "printed"
    assert stored_marking and stored_marking.meta_status == META_STATUS_REJECTED
    assert await db_session.scalar(
        select(func.count()).select_from(MarkingCode).where(MarkingCode.tenant_id == tenant_id)
    ) == before_codes
    assert await db_session.scalar(
        select(func.count())
        .select_from(FbsOrderMarking)
        .where(FbsOrderMarking.order_id == order_id)
    ) == before_markings
    assert await db_session.scalar(
        select(func.count()).select_from(MarkingCodeEvent).where(
            MarkingCodeEvent.code_id == code_id,
            MarkingCodeEvent.event_type == "reprinted",
        )
    ) == 1

    replacement = FbsOrderMarking(
        tenant_id=tenant_id,
        order_id=order_id,
        kind=MARKING_KIND_SGTIN,
        value=f"{cis_code}-replacement",
        source="pool",
        meta_status=META_STATUS_ACCEPTED,
        created_at=now + timedelta(seconds=1),
    )
    db_session.add(replacement)
    await db_session.commit()
    superseded_validation = await async_client.post(
        "/operations/fbs-orders/print-bindings/validate",
        headers=headers,
        json={
            "bindings": [selected_binding],
            "reprint_marking_ids": [str(marking_id)],
        },
    )
    assert superseded_validation.status_code == 409

    # Once the old selection is no longer attached to its prepared supply, the
    # explicit reprint context cannot override that changed binding.
    await db_session.execute(
        update(FbsOrder).where(FbsOrder.id == order_id).values(supply_id=None)
    )
    await db_session.commit()
    unlinked_validation = await async_client.post(
        "/operations/fbs-orders/print-bindings/validate",
        headers=headers,
        json={
            "bindings": [selected_binding],
            "reprint_marking_ids": [str(marking_id)],
        },
    )
    assert unlinked_validation.status_code == 409
