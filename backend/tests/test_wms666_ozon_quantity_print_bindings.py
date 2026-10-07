"""The print guard must accept every current Ozon exemplar for a multi-unit position."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from test_fbs_kiz import _register_ff_admin, _setup_seller_warehouse

from app.models.fbs_order import (
    MAPPING_STATUS_MAPPED,
    RESERVE_STATUS_RESERVED,
    FbsOrder,
    FbsOrderMarking,
    FbsOrderProduct,
)
from app.models.fbs_supply import FBS_DELIVERY_TYPE_WAREHOUSE_SC, FbsSupply
from app.models.marking_code import MarkingCode
from app.models.product import Product
from app.services.fbs_print_binding_service import PrintBinding, print_bindings_current
from app.services.ozon_fbs_marking_gate_service import current_markings
from tests.test_ozon_fbs_process_contract import SKU, _seed_order


def _bindings(
    order: FbsOrder,
    supply: FbsSupply,
    markings: list[FbsOrderMarking],
) -> list[PrintBinding]:
    return [
        PrintBinding(
            order_id=order.id,
            supply_id=supply.id,
            marking_id=marking.id,
            cis_code=marking.value,
        )
        for marking in markings
    ]


async def test_ozon_quantity_three_accepts_all_current_bindings_and_rejects_replaced_generation(
    db_session: AsyncSession,
) -> None:
    order, position = await _seed_order(db_session)
    supply = FbsSupply(
        tenant_id=order.tenant_id,
        seller_id=order.seller_id,
        warehouse_id=order.warehouse_id,
        marketplace="ozon",
        name="Ozon quantity print proof",
        status="assembling",
        delivery_type=FBS_DELIVERY_TYPE_WAREHOUSE_SC,
    )
    db_session.add(supply)
    await db_session.flush()
    order.supply_id = supply.id
    first_created_at = datetime.now(UTC) - timedelta(seconds=2)
    markings = [
        FbsOrderMarking(
            tenant_id=order.tenant_id,
            order_id=order.id,
            order_product_id=position.id,
            kind="sgtin",
            value=f"010460123456789021{index:04d}",
            meta_details_json={"exemplar_id": 80 + index},
            created_at=first_created_at + timedelta(microseconds=index),
        )
        for index in range(1, 4)
    ]
    db_session.add_all(markings)
    await db_session.commit()

    order = await db_session.scalar(
        select(FbsOrder)
        .where(FbsOrder.id == order.id)
        .options(selectinload(FbsOrder.product_positions))
    )
    assert order is not None
    position = next(row for row in order.product_positions if row.id == position.id)
    assert position.quantity == 3
    current = current_markings(order, markings)
    assert {row.id for row in current} == {row.id for row in markings}
    current_bindings = _bindings(order, supply, current)
    assert await print_bindings_current(db_session, order.tenant_id, current_bindings) is True

    position_id = position.id
    replaced = markings[0]
    replaced.meta_status = "replacement_required"
    replacement = FbsOrderMarking(
        tenant_id=order.tenant_id,
        order_id=order.id,
        order_product_id=position.id,
        kind="sgtin",
        value="0104601234567890219999",
        meta_details_json={"exemplar_id": 99},
        created_at=datetime.now(UTC) + timedelta(seconds=1),
    )
    db_session.add(replacement)
    await db_session.commit()

    order = await db_session.scalar(
        select(FbsOrder)
        .where(FbsOrder.id == order.id)
        .options(selectinload(FbsOrder.product_positions))
    )
    assert order is not None
    position = next(row for row in order.product_positions if row.id == position_id)
    next_generation = current_markings(order, [*markings, replacement])
    assert len(next_generation) == position.quantity
    assert replacement in next_generation
    assert replaced not in next_generation
    stale_binding = _bindings(order, supply, [replaced])
    next_bindings = _bindings(order, supply, next_generation)
    assert await print_bindings_current(db_session, order.tenant_id, stale_binding) is False
    assert await print_bindings_current(db_session, order.tenant_id, next_bindings) is True


async def test_ozon_equal_timestamp_cutoff_keeps_every_current_binding(
    db_session: AsyncSession,
) -> None:
    order, position = await _seed_order(db_session)
    supply = FbsSupply(
        tenant_id=order.tenant_id,
        seller_id=order.seller_id,
        warehouse_id=order.warehouse_id,
        marketplace="ozon",
        name="Ozon equal-generation print proof",
        status="assembling",
        delivery_type=FBS_DELIVERY_TYPE_WAREHOUSE_SC,
    )
    db_session.add(supply)
    await db_session.flush()
    order.supply_id = supply.id

    created_at = datetime.now(UTC) - timedelta(seconds=2)
    # Deliberately make exemplar 3's UUID the smallest. A validator that sorts
    # a timestamp tie by UUID and then slices to quantity drops this still-
    # current exemplar when a newer replacement row is added.
    ids = [uuid.UUID(int=30), uuid.UUID(int=20), uuid.UUID(int=10)]
    markings = [
        FbsOrderMarking(
            id=ids[index - 1],
            tenant_id=order.tenant_id,
            order_id=order.id,
            order_product_id=position.id,
            kind="sgtin",
            value=f"010460123456789021{index:04d}",
            meta_status="accepted",
            meta_details_json={"exemplar_id": 80 + index},
            created_at=created_at,
        )
        for index in range(1, 4)
    ]
    db_session.add_all(markings)
    await db_session.commit()

    order = await db_session.scalar(
        select(FbsOrder)
        .where(FbsOrder.id == order.id)
        .options(selectinload(FbsOrder.product_positions))
    )
    assert order is not None
    position_id = position.id
    position = next(row for row in order.product_positions if row.id == position_id)
    assert position.quantity == 3

    replacement = FbsOrderMarking(
        id=uuid.UUID(int=40),
        tenant_id=order.tenant_id,
        order_id=order.id,
        order_product_id=position_id,
        kind="sgtin",
        value="0104601234567890219999",
        meta_status="accepted",
        meta_details_json={"exemplar_id": 81},
        created_at=created_at + timedelta(seconds=1),
    )
    db_session.add(replacement)
    await db_session.commit()

    order = await db_session.scalar(
        select(FbsOrder)
        .where(FbsOrder.id == order.id)
        .options(selectinload(FbsOrder.product_positions))
    )
    assert order is not None
    current = current_markings(order, [*markings, replacement])
    assert len(current) == 4  # The existing Ozon reader retains the tied cutoff.
    current_replacement = _bindings(order, supply, [replacement])
    superseded_exemplar = _bindings(order, supply, [markings[0]])
    still_current = next(row for row in current if row.meta_details_json["exemplar_id"] == 83)
    binding = _bindings(order, supply, [still_current])

    assert await print_bindings_current(db_session, order.tenant_id, current_replacement) is True
    assert await print_bindings_current(db_session, order.tenant_id, superseded_exemplar) is False
    assert await print_bindings_current(db_session, order.tenant_id, binding) is True


async def test_ozon_print_tape_output_passes_late_binding_validation(
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
        name="Ozon quantity-3 print tape",
        sku_code=f"ozon-tape-{suffix}",
        requires_honest_sign=True,
    )
    supply = FbsSupply(
        tenant_id=tenant_id,
        seller_id=seller_id,
        warehouse_id=warehouse_id,
        marketplace="ozon",
        external_supply_id=f"ozon-tape-{suffix}",
        name="Ozon quantity print tape",
        status="assembling",
        delivery_type=FBS_DELIVERY_TYPE_WAREHOUSE_SC,
    )
    now = datetime.now(UTC)
    order = FbsOrder(
        tenant_id=tenant_id,
        seller_id=seller_id,
        warehouse_id=warehouse_id,
        product=product,
        supply=supply,
        marketplace="ozon",
        external_order_id=f"ozon-tape-posting-{suffix}",
        wb_order_id=800_000_000 + int(suffix[-8:], 16) % 100_000_000,
        created_at_wb=now,
        deadline_at=now + timedelta(days=1),
        mapping_status=MAPPING_STATUS_MAPPED,
        reserve_status=RESERVE_STATUS_RESERVED,
        status="assembling",
        required_meta_json=["sgtin"],
    )
    db_session.add_all([product, supply, order])
    await db_session.flush()
    position = FbsOrderProduct(
        order_id=order.id,
        product_id=product.id,
        ozon_sku=SKU,
        offer_id=f"offer-{suffix}",
        name=product.name,
        quantity=3,
        position_index=0,
        provider_data_json={"sku": SKU, "quantity": 3},
    )
    db_session.add(position)
    await db_session.flush()

    created_at = now - timedelta(seconds=2)
    marking_specs = [
        (uuid.UUID(int=30), 81, "0001", created_at),
        (uuid.UUID(int=20), 82, "0002", created_at),
        (uuid.UUID(int=10), 83, "0003", created_at),
        (uuid.UUID(int=40), 81, "9999", created_at + timedelta(seconds=1)),
    ]
    markings: list[FbsOrderMarking] = []
    for marking_id, exemplar_id, tail, marking_created_at in marking_specs:
        cis_code = f"010460123456789021{tail}"
        code = MarkingCode(
            tenant_id=tenant_id,
            seller_id=seller_id,
            product_id=product.id,
            cis_code=cis_code,
            source="pool",
            status="printed",
        )
        marking = FbsOrderMarking(
            id=marking_id,
            tenant_id=tenant_id,
            order_id=order.id,
            order_product_id=position.id,
            kind="sgtin",
            value=cis_code,
            meta_status="accepted",
            meta_details_json={"exemplar_id": exemplar_id},
            created_at=marking_created_at,
            marking_code=code,
        )
        markings.append(marking)
    db_session.add_all(markings)
    await db_session.commit()

    prepared = await async_client.post(
        f"/operations/fbs-supplies/{supply.id}/order-print-tape",
        headers=headers,
        json={
            "order_ids": [str(order.id)],
            "include_order_qr": False,
            "reprint": False,
            "layout_json": {"units": [{"block": "cz", "copies": 1}]},
        },
    )
    assert prepared.status_code == 200, prepared.text
    order_result = prepared.json()["orders"][0]
    printed_codes = order_result["printed_codes"]
    exact_bindings = [
        {
            "order_id": order_result["order_id"],
            "supply_id": printed_code["supply_id"],
            "marking_id": printed_code["marking_id"],
            "cis_code": printed_code["cis_code"],
        }
        for printed_code in printed_codes
    ]
    # This is the same late-validation API the browser invokes immediately
    # before dispatching the already prepared Ozon tape.
    validation = await async_client.post(
        "/operations/fbs-orders/print-bindings/validate",
        headers=headers,
        json={"bindings": exact_bindings},
    )

    assert validation.status_code == 204, validation.text
    expected_marking_ids = {str(marking.id) for marking in markings[1:]}
    assert {row["marking_id"] for row in printed_codes} == expected_marking_ids
    assert len(printed_codes) == 3
