"""WMS-531 · «Остатки и движения»: каждое движение по документу строкой,
уравнение было+приход-расход=стало, без фильтра склада, постраничность и Excel.

Стиль соответствует остальным test_reports_*.py: движения и документы
конструируются прямыми вставками ORM, как и в существующих файлах — отчёт
читает только сохранённые связи (inbound_intake_line_id и т. п.), поэтому
проходить через сервисы-писатели (discrepancy_act_service,
ownership_transfer_service…) не нужно ни для одного из типов, кроме старого
fbs_order_pick — там сама связь идёт через FbsOrderPick/FbsOrderPickEvent.
"""

from __future__ import annotations

import io
import time
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from openpyxl import load_workbook

from app.db.session import SessionLocal
from app.models.discrepancy_act import DiscrepancyAct  # noqa: F401  (см. докстринг)
from app.models.fbs_order import FbsOrder
from app.models.fbs_order_pick import FbsOrderPick, FbsOrderPickEvent
from app.models.fbs_shipment_reversal_ledger import FbsShipmentReversalLedger
from app.models.fbs_supply import FBS_DELIVERY_TYPE_WAREHOUSE_SC, FbsSupply
from app.models.inbound_intake import InboundIntakeLine, InboundIntakeRequest
from app.models.inventory_balance import InventoryBalance
from app.models.inventory_count import InventoryCount, InventoryCountLine
from app.models.inventory_movement import InventoryMovement
from app.models.marketplace_unload import MarketplaceUnloadRequest
from app.models.outbound_shipment import OutboundShipmentLine, OutboundShipmentRequest
from app.models.product import Product
from app.services.ownership_transfer_service import (
    MOVEMENT_TYPE_OWNERSHIP_IN,
    MOVEMENT_TYPE_OWNERSHIP_OUT,
    MOVEMENT_TYPE_OWNERSHIP_RECEIPT,
)
from app.services.tokens import decode_access_token

MSK_NOON = 12  # UTC-час, заведомо внутри «дня» и по МСК, и по UTC.


async def _org(
    async_client: AsyncClient, *, name: str
) -> tuple[dict[str, str], uuid.UUID, uuid.UUID]:
    suffix = str(time.time_ns())
    registered = await async_client.post("/auth/register", json={
        "organization_name": name, "slug": f"{name.lower()}-{suffix}",
        "admin_email": f"{name.lower()}-{suffix}@example.com", "password": "password123",
    })
    assert registered.status_code == 200, registered.text
    token = str(registered.json()["access_token"])
    headers = {"Authorization": f"Bearer {token}"}
    claims = decode_access_token(token)
    return headers, uuid.UUID(str(claims["tenant_id"])), uuid.UUID(str(claims["sub"]))


async def _seller(async_client: AsyncClient, headers: dict[str, str], name: str) -> uuid.UUID:
    resp = await async_client.post("/sellers", headers=headers, json={"name": name})
    assert resp.status_code in (200, 201), resp.text
    return uuid.UUID(resp.json()["id"])


async def _warehouse_location(
    async_client: AsyncClient, headers: dict[str, str], *, name: str
) -> tuple[uuid.UUID, uuid.UUID]:
    suffix = str(time.time_ns())
    warehouse = await async_client.post(
        "/warehouses", headers=headers, json={"name": name, "code": f"{name}-{suffix}"}
    )
    assert warehouse.status_code == 200, warehouse.text
    warehouse_id = uuid.UUID(warehouse.json()["id"])
    location = await async_client.post(
        f"/warehouses/{warehouse_id}/locations", headers=headers, json={"code": f"A-{suffix}"}
    )
    assert location.status_code == 200, location.text
    return warehouse_id, uuid.UUID(location.json()["id"])


async def _product(
    session, *, tenant_id: uuid.UUID, seller_id: uuid.UUID, name: str, sku: str
) -> uuid.UUID:
    product_id = uuid.uuid4()
    session.add(Product(
        id=product_id, tenant_id=tenant_id, seller_id=seller_id, name=name, sku_code=sku,
    ))
    await session.flush()
    return product_id


def _movement(
    *, tenant_id, product_id, seller_id, warehouse_id, location_id, quantity_delta,
    movement_type="inbound_intake", created_at=None, movement_id=None,
    inbound_intake_line_id=None, marketplace_unload_request_id=None,
    outbound_shipment_line_id=None, inventory_count_line_id=None, transfer_group_id=None,
) -> InventoryMovement:
    return InventoryMovement(
        id=movement_id or uuid.uuid4(), tenant_id=tenant_id, product_id=product_id,
        seller_id=seller_id, warehouse_id=warehouse_id, storage_location_id=location_id,
        quantity_delta=quantity_delta, movement_type=movement_type,
        created_at=created_at or datetime(2026, 9, 10, MSK_NOON, tzinfo=UTC),
        inbound_intake_line_id=inbound_intake_line_id,
        marketplace_unload_request_id=marketplace_unload_request_id,
        outbound_shipment_line_id=outbound_shipment_line_id,
        inventory_count_line_id=inventory_count_line_id,
        transfer_group_id=transfer_group_id,
    )


PERIOD = {"date_from": "2026-09-01T00:00:00Z", "date_to": "2026-09-30T00:00:00Z"}


@pytest.mark.asyncio
async def test_all_movement_types_get_correct_label_document_and_group(
    async_client: AsyncClient,
) -> None:
    """WMS-531 C1: каждый вид движения — своя строка, своя подпись, свой
    документ (или «без документа») и своя группа «По операциям»; расположение
    не видно ни строкой, ни в какой группе."""
    headers, tenant_id, user_id = await _org(async_client, name="Wms531c1")
    seller_id = await _seller(async_client, headers, "S1")
    other_seller_id = await _seller(async_client, headers, "S2")
    warehouse_id, location_id = await _warehouse_location(async_client, headers, name="wh1")

    async with SessionLocal() as session:
        product_id = await _product(
            session, tenant_id=tenant_id, seller_id=seller_id, name="P1", sku="SKU-1"
        )
        other_product_id = await _product(
            session, tenant_id=tenant_id, seller_id=other_seller_id, name="P2", sku="SKU-2"
        )

        # --- Приёмка + отмена + повтор через «Редактировать» ---
        intake = InboundIntakeRequest(
            tenant_id=tenant_id, seller_id=seller_id, warehouse_id=warehouse_id,
            status="done", operation_type="inbound", document_number="IN-1",
            display_number="№000001",
        )
        session.add(intake)
        await session.flush()
        intake_line = InboundIntakeLine(
            request_id=intake.id, product_id=product_id, expected_qty=10
        )
        session.add(intake_line)
        await session.flush()
        session.add(_movement(
            tenant_id=tenant_id, product_id=product_id, seller_id=seller_id,
            warehouse_id=warehouse_id, location_id=location_id, quantity_delta=10,
            movement_type="inbound_intake", inbound_intake_line_id=intake_line.id,
        ))

        # --- Возврат ---
        return_request = InboundIntakeRequest(
            tenant_id=tenant_id, seller_id=seller_id, warehouse_id=warehouse_id,
            status="done", operation_type="return", document_number="RET-1",
            display_number="№000002",
        )
        session.add(return_request)
        await session.flush()
        return_line = InboundIntakeLine(
            request_id=return_request.id, product_id=product_id, expected_qty=2
        )
        session.add(return_line)
        await session.flush()
        session.add(_movement(
            tenant_id=tenant_id, product_id=product_id, seller_id=seller_id,
            warehouse_id=warehouse_id, location_id=location_id, quantity_delta=2,
            movement_type="inbound_intake", inbound_intake_line_id=return_line.id,
        ))

        # --- Акт расхождений к строке приёмки ---
        session.add(_movement(
            tenant_id=tenant_id, product_id=product_id, seller_id=seller_id,
            warehouse_id=warehouse_id, location_id=location_id, quantity_delta=1,
            movement_type="discrepancy_act", inbound_intake_line_id=intake_line.id,
        ))

        # --- Отгрузка на МП: сбор в короб, снятие ---
        unload = MarketplaceUnloadRequest(
            tenant_id=tenant_id, seller_id=seller_id, warehouse_id=warehouse_id,
            status="collecting", document_number="MP-1", display_number="№5",
        )
        session.add(unload)
        await session.flush()
        session.add(_movement(
            tenant_id=tenant_id, product_id=product_id, seller_id=seller_id,
            warehouse_id=warehouse_id, location_id=location_id, quantity_delta=-3,
            movement_type="marketplace_unload", marketplace_unload_request_id=unload.id,
        ))
        session.add(_movement(
            tenant_id=tenant_id, product_id=product_id, seller_id=seller_id,
            warehouse_id=warehouse_id, location_id=location_id, quantity_delta=1,
            movement_type="marketplace_unload", marketplace_unload_request_id=unload.id,
        ))

        # --- FBS WB: списание одной строкой ---
        wb_order = FbsOrder(
            tenant_id=tenant_id, seller_id=seller_id, marketplace="wb", wb_order_id=555111,
            product_id=product_id, warehouse_id=warehouse_id,
            created_at_wb=datetime(2026, 9, 1, tzinfo=UTC),
            deadline_at=datetime(2026, 9, 5, tzinfo=UTC),
            mapping_status="mapped", reserve_status="no_stock",
        )
        session.add(wb_order)
        await session.flush()
        wb_shipment = _movement(
            tenant_id=tenant_id, product_id=product_id, seller_id=seller_id,
            warehouse_id=warehouse_id, location_id=location_id, quantity_delta=-1,
            movement_type="fbs_shipment",
        )
        session.add(wb_shipment)
        await session.flush()
        session.add(FbsShipmentReversalLedger(
            tenant_id=tenant_id, fbs_order_id=wb_order.id, product_id=product_id,
            storage_location_id=location_id, quantity=1, shipment_movement_id=wb_shipment.id,
        ))

        # --- FBS Ozon: списание, разделённое на 2 строки одним transfer_group_id ---
        ozon_order = FbsOrder(
            tenant_id=tenant_id, seller_id=seller_id, marketplace="ozon", wb_order_id=-99887766,
            external_order_id="OZ-777", product_id=product_id, warehouse_id=warehouse_id,
            created_at_wb=datetime(2026, 9, 1, tzinfo=UTC),
            deadline_at=datetime(2026, 9, 5, tzinfo=UTC),
            mapping_status="mapped", reserve_status="no_stock",
        )
        session.add(ozon_order)
        await session.flush()
        ozon_group = uuid.uuid4()
        ozon_first = _movement(
            tenant_id=tenant_id, product_id=product_id, seller_id=seller_id,
            warehouse_id=warehouse_id, location_id=location_id, quantity_delta=-1,
            movement_type="fbs_shipment", transfer_group_id=ozon_group,
        )
        ozon_second = _movement(
            tenant_id=tenant_id, product_id=product_id, seller_id=seller_id,
            warehouse_id=warehouse_id, location_id=location_id, quantity_delta=-1,
            movement_type="fbs_shipment", transfer_group_id=ozon_group,
        )
        session.add_all([ozon_first, ozon_second])
        await session.flush()
        session.add(FbsShipmentReversalLedger(
            tenant_id=tenant_id, fbs_order_id=ozon_order.id, product_id=product_id,
            storage_location_id=location_id, quantity=2, shipment_movement_id=ozon_first.id,
        ))

        # --- Историческое сторно FBS (до 05.09.2026): «+», reversal_movement_id ---
        reversal_order = FbsOrder(
            tenant_id=tenant_id, seller_id=seller_id, marketplace="wb", wb_order_id=555222,
            product_id=product_id, warehouse_id=warehouse_id,
            created_at_wb=datetime(2026, 8, 20, tzinfo=UTC),
            deadline_at=datetime(2026, 8, 25, tzinfo=UTC),
            mapping_status="mapped", reserve_status="no_stock",
        )
        session.add(reversal_order)
        await session.flush()
        original_shipment = _movement(
            tenant_id=tenant_id, product_id=product_id, seller_id=seller_id,
            warehouse_id=warehouse_id, location_id=location_id, quantity_delta=-1,
            movement_type="fbs_shipment", created_at=datetime(2026, 8, 20, MSK_NOON, tzinfo=UTC),
        )
        reversal_movement = _movement(
            tenant_id=tenant_id, product_id=product_id, seller_id=seller_id,
            warehouse_id=warehouse_id, location_id=location_id, quantity_delta=1,
            movement_type="fbs_shipment",
        )
        session.add_all([original_shipment, reversal_movement])
        await session.flush()
        session.add(FbsShipmentReversalLedger(
            tenant_id=tenant_id, fbs_order_id=reversal_order.id, product_id=product_id,
            storage_location_id=location_id, quantity=1,
            shipment_movement_id=original_shipment.id, reversal_movement_id=reversal_movement.id,
        ))

        # --- Старое fbs_order_pick + отмена, с записью подбора ---
        pick_order = FbsOrder(
            tenant_id=tenant_id, seller_id=seller_id, marketplace="wb", wb_order_id=555333,
            product_id=product_id, warehouse_id=warehouse_id,
            created_at_wb=datetime(2026, 9, 1, tzinfo=UTC),
            deadline_at=datetime(2026, 9, 5, tzinfo=UTC),
            mapping_status="mapped", reserve_status="no_stock",
        )
        session.add(pick_order)
        await session.flush()
        supply = FbsSupply(
            tenant_id=tenant_id, seller_id=seller_id, warehouse_id=warehouse_id,
            name="Supply 1", delivery_type=FBS_DELIVERY_TYPE_WAREHOUSE_SC,
        )
        session.add(supply)
        await session.flush()
        old_pick_movement = _movement(
            tenant_id=tenant_id, product_id=product_id, seller_id=seller_id,
            warehouse_id=warehouse_id, location_id=location_id, quantity_delta=1,
            movement_type="fbs_order_pick",
        )
        session.add(old_pick_movement)
        await session.flush()
        pick = FbsOrderPick(
            tenant_id=tenant_id, fbs_order_id=pick_order.id, fbs_supply_id=supply.id,
            source_storage_location_id=location_id, sorting_storage_location_id=location_id,
            product_id=product_id, picked_at=datetime(2026, 9, 10, MSK_NOON, tzinfo=UTC),
            inventory_movement_id=old_pick_movement.id, scan_idempotency_key="pick-1",
        )
        session.add(pick)
        await session.flush()
        session.add(FbsOrderPickEvent(
            pick_id=pick.id, event_type="picked", source_storage_location_id=location_id,
            sorting_storage_location_id=location_id, inventory_movement_id=old_pick_movement.id,
        ))

        # --- Инвентаризация: списание и находка ---
        count = InventoryCount(
            tenant_id=tenant_id, status="posted", source="all", created_by_user_id=user_id,
        )
        session.add(count)
        await session.flush()
        count_line = InventoryCountLine(
            count_id=count.id, product_id=product_id, storage_location_id=location_id,
            expected_quantity=5, actual_quantity=3, posted_delta=-2,
        )
        session.add(count_line)
        await session.flush()
        session.add(_movement(
            tenant_id=tenant_id, product_id=product_id, seller_id=seller_id,
            warehouse_id=warehouse_id, location_id=location_id, quantity_delta=-2,
            movement_type="inventory_count", inventory_count_line_id=count_line.id,
        ))
        found_line = InventoryCountLine(
            count_id=count.id, product_id=other_product_id, storage_location_id=location_id,
            expected_quantity=0, actual_quantity=1, posted_delta=1,
        )
        session.add(found_line)
        await session.flush()
        session.add(_movement(
            tenant_id=tenant_id, product_id=other_product_id, seller_id=other_seller_id,
            warehouse_id=warehouse_id, location_id=location_id, quantity_delta=1,
            movement_type="inventory_count", inventory_count_line_id=found_line.id,
        ))

        # --- Передача между селлерами: S1 -> S2, плюс служебная приёмка ---
        transfer_group = uuid.uuid4()
        session.add(_movement(
            tenant_id=tenant_id, product_id=product_id, seller_id=seller_id,
            warehouse_id=warehouse_id, location_id=location_id, quantity_delta=-5,
            movement_type=MOVEMENT_TYPE_OWNERSHIP_OUT, transfer_group_id=transfer_group,
        ))
        session.add(_movement(
            tenant_id=tenant_id, product_id=other_product_id, seller_id=other_seller_id,
            warehouse_id=warehouse_id, location_id=location_id, quantity_delta=5,
            movement_type=MOVEMENT_TYPE_OWNERSHIP_IN, transfer_group_id=transfer_group,
        ))
        service_intake = InboundIntakeRequest(
            tenant_id=tenant_id, seller_id=other_seller_id, warehouse_id=warehouse_id,
            status="done", operation_type="inbound", document_number="IN-9",
            display_number="№000009",
        )
        session.add(service_intake)
        await session.flush()
        service_line = InboundIntakeLine(
            request_id=service_intake.id, product_id=other_product_id, expected_qty=3
        )
        session.add(service_line)
        await session.flush()
        session.add(_movement(
            tenant_id=tenant_id, product_id=other_product_id, seller_id=other_seller_id,
            warehouse_id=warehouse_id, location_id=location_id, quantity_delta=3,
            movement_type=MOVEMENT_TYPE_OWNERSHIP_RECEIPT, inbound_intake_line_id=service_line.id,
        ))

        # --- Загрузка ТЗ и корректировка — без документа ---
        session.add(_movement(
            tenant_id=tenant_id, product_id=product_id, seller_id=seller_id,
            warehouse_id=warehouse_id, location_id=location_id, quantity_delta=7,
            movement_type="product_tz_import",
        ))
        session.add(_movement(
            tenant_id=tenant_id, product_id=product_id, seller_id=seller_id,
            warehouse_id=warehouse_id, location_id=location_id, quantity_delta=-1,
            movement_type="correction_phantom_return",
        ))

        # --- Старая отгрузка ---
        outbound_request = OutboundShipmentRequest(
            tenant_id=tenant_id, warehouse_id=warehouse_id, seller_id=seller_id, status="posted",
        )
        session.add(outbound_request)
        await session.flush()
        outbound_line = OutboundShipmentLine(
            request_id=outbound_request.id, product_id=product_id, quantity=1, shipped_qty=1,
        )
        session.add(outbound_line)
        await session.flush()
        session.add(_movement(
            tenant_id=tenant_id, product_id=product_id, seller_id=seller_id,
            warehouse_id=warehouse_id, location_id=location_id, quantity_delta=-1,
            movement_type="outbound_shipment", outbound_shipment_line_id=outbound_line.id,
        ))

        # --- Расположение: не должно попасть НИКУДА ---
        second_warehouse_id = uuid.uuid4()
        from app.models.warehouse import Warehouse
        session.add(Warehouse(
            id=second_warehouse_id, tenant_id=tenant_id, name="WH2",
            code=f"wh2-{uuid.uuid4().hex[:8]}",
        ))
        await session.flush()
        from app.models.storage_location import StorageLocation
        second_location = StorageLocation(
            tenant_id=tenant_id, warehouse_id=second_warehouse_id, code="B-01",
            barcode=f"loc-{uuid.uuid4().hex[:8]}",
        )
        session.add(second_location)
        await session.flush()
        for movement_type, first_wh, first_loc, second_wh, second_loc in (
            (
                "stock_transfer_out", warehouse_id, location_id,
                second_warehouse_id, second_location.id,
            ),
        ):
            group = uuid.uuid4()
            session.add(_movement(
                tenant_id=tenant_id, product_id=product_id, seller_id=seller_id,
                warehouse_id=first_wh, location_id=first_loc, quantity_delta=-6,
                movement_type=movement_type, transfer_group_id=group,
            ))
            session.add(_movement(
                tenant_id=tenant_id, product_id=product_id, seller_id=seller_id,
                warehouse_id=second_wh, location_id=second_loc, quantity_delta=6,
                movement_type="stock_transfer_in", transfer_group_id=group,
            ))
        for solo_type in ("warehouse_map_move", "container_reattach", "transfer"):
            group = uuid.uuid4()
            session.add(_movement(
                tenant_id=tenant_id, product_id=product_id, seller_id=seller_id,
                warehouse_id=warehouse_id, location_id=location_id, quantity_delta=-4,
                movement_type=solo_type, transfer_group_id=group,
            ))
            session.add(_movement(
                tenant_id=tenant_id, product_id=product_id, seller_id=seller_id,
                warehouse_id=warehouse_id, location_id=location_id, quantity_delta=4,
                movement_type=solo_type, transfer_group_id=group,
            ))

        await session.commit()

    # По операциям: ни одно расположение не появилось строкой/группой.
    operations = await async_client.get(
        "/reports/inventory", headers=headers,
        params={**PERIOD, "group_by": "operation"},
    )
    assert operations.status_code == 200, operations.text
    group_labels = {row["operation"] for row in operations.json()["rows"]}
    assert "Прочее" not in group_labels
    assert group_labels == {
        "Приёмка", "Возврат", "Корректировка", "Отгрузка на МП", "FBS",
        "Инвентаризация", "Передача между селлерами", "Загрузка ТЗ", "Отгрузка",
    }

    async def _movements_for(operation: str) -> list[dict[str, object]]:
        resp = await async_client.get(
            "/reports/inventory/movements", headers=headers,
            params={**PERIOD, "operation": operation},
        )
        assert resp.status_code == 200, resp.text
        return list(resp.json()["rows"])

    intake_rows = await _movements_for("Приёмка")
    assert {row["quantity"] for row in intake_rows} == {10}
    assert intake_rows[0]["document"] == {
        "kind": "inbound", "id": str(intake.id), "number": "№000001",
    }

    return_rows = await _movements_for("Возврат")
    assert len(return_rows) == 1
    assert return_rows[0]["document"]["number"] == "№000002"

    unload_rows = await _movements_for("Отгрузка на МП")
    assert {row["quantity"] for row in unload_rows} == {-3, 1}
    for row in unload_rows:
        assert row["document"] == {
            "kind": "marketplace_unload", "id": str(unload.id), "number": "№5",
        }

    fbs_rows = await _movements_for("FBS")
    fbs_by_qty: dict[int, list[dict[str, object]]] = {}
    for row in fbs_rows:
        fbs_by_qty.setdefault(row["quantity"], []).append(row)
    # Оригинал сторно-списания создан в августе (created_at) — вне периода
    # сентября, поэтому в -1 остаются только wb и обе строки ozon-сплита.
    assert len(fbs_by_qty[-1]) == 3  # wb + 2x ozon-split
    assert len(fbs_by_qty[1]) == 2  # сторно(+1) и старый pick(+1)
    wb_doc = next(row for row in fbs_by_qty[-1] if row["document"]["number"] == "Заказ WB №555111")
    assert wb_doc["operation"] == "FBS"
    ozon_docs = [row for row in fbs_by_qty[-1] if row["document"]["number"] == "Заказ Ozon №OZ-777"]
    assert len(ozon_docs) == 2  # обе строки разделённого списания получили один и тот же заказ
    reversal_plus = next(
        row for row in fbs_by_qty[1]
        if row["document"] is not None and row["document"]["number"] == "Заказ WB №555222"
    )
    assert reversal_plus["operation"] == "FBS, сторно"
    old_pick_row = next(
        row for row in fbs_by_qty[1]
        if row["document"] is not None and row["document"]["number"] == "Заказ WB №555333"
    )
    assert old_pick_row["operation"] == "FBS"

    inventory_rows = await _movements_for("Инвентаризация")
    assert {row["quantity"] for row in inventory_rows} == {-2, 1}
    for row in inventory_rows:
        assert row["document"]["kind"] == "inventory_count"
        assert row["document"]["number"] == f"ИНВ-{str(count.id).split('-')[0].upper()}"

    transfer_rows = await _movements_for("Передача между селлерами")
    assert len(transfer_rows) == 3
    by_qty = {row["quantity"]: row for row in transfer_rows}
    assert by_qty[-5]["operation"] == "Передано селлеру «S2»"
    assert by_qty[-5]["document"] is None
    assert by_qty[5]["operation"] == "Получено от селлера «S1»"
    assert by_qty[5]["document"] is None
    assert by_qty[3]["operation"] == "Приёмка при передаче между селлерами"
    assert by_qty[3]["document"]["number"] == "№000009"

    tz_rows = await _movements_for("Загрузка ТЗ")
    assert len(tz_rows) == 1 and tz_rows[0]["document"] is None

    correction_rows = await _movements_for("Корректировка")
    assert {row["quantity"] for row in correction_rows} == {1, -1}
    phantom_row = next(row for row in correction_rows if row["quantity"] == -1)
    assert phantom_row["document"] is None
    assert phantom_row["operation"] == "Корректировка"
    discrepancy_row = next(row for row in correction_rows if row["quantity"] == 1)
    assert discrepancy_row["operation"] == "Корректировка по акту расхождений"
    assert discrepancy_row["document"] == {
        "kind": "inbound", "id": str(intake.id), "number": "№000001",
    }

    outbound_rows = await _movements_for("Отгрузка")
    assert len(outbound_rows) == 1
    assert outbound_rows[0]["document"] == {
        "kind": "outbound_shipment", "id": str(outbound_request.id), "number": "без номера",
    }


@pytest.mark.asyncio
async def test_equation_holds_across_periods_products_seller_and_overview(
    async_client: AsyncClient,
) -> None:
    """WMS-531 C2/C3/C4/C7/C8/C9(частично R7-R10): было+приход-расход=стало на
    товаре, на селлере (сумма товаров) и на плитках (сумма по всем товарам) —
    и для прошлого месяца (факт на дату), и для текущего («Остаток сейчас»).
    Товар без движений в периоде виден, если у него ненулевое было/стало;
    товар без движений НИКОГДА не виден, если и то и другое ноль (R9)."""
    headers, tenant_id, _user_id = await _org(async_client, name="Wms531eq")
    seller_id = await _seller(async_client, headers, "Equation seller")
    warehouse_id, location_id = await _warehouse_location(async_client, headers, name="eqwh")

    async with SessionLocal() as session:
        product_p = await _product(
            session, tenant_id=tenant_id, seller_id=seller_id, name="P", sku="EQ-P"
        )
        product_q = await _product(
            session, tenant_id=tenant_id, seller_id=seller_id, name="Q", sku="EQ-Q"
        )
        moves = [
            (product_p, 20, datetime(2026, 8, 5, MSK_NOON, tzinfo=UTC), "inbound_intake"),
            (product_p, -5, datetime(2026, 8, 20, MSK_NOON, tzinfo=UTC), "fbs_shipment"),
            (product_p, 8, datetime(2026, 9, 10, MSK_NOON, tzinfo=UTC), "inbound_intake"),
            (product_p, -3, datetime(2026, 9, 15, MSK_NOON, tzinfo=UTC), "marketplace_unload"),
            (product_q, 5, datetime(2026, 9, 20, MSK_NOON, tzinfo=UTC), "inbound_intake"),
        ]
        for product_id, delta, created_at, movement_type in moves:
            session.add(_movement(
                tenant_id=tenant_id, product_id=product_id, seller_id=seller_id,
                warehouse_id=warehouse_id, location_id=location_id, quantity_delta=delta,
                created_at=created_at, movement_type=movement_type,
            ))
        session.add(InventoryBalance(
            tenant_id=tenant_id, product_id=product_p, storage_location_id=location_id, quantity=20,
        ))
        session.add(InventoryBalance(
            tenant_id=tenant_id, product_id=product_q, storage_location_id=location_id, quantity=5,
        ))
        await session.commit()

    async def _product_row(date_from: str, date_to: str, sku: str) -> dict[str, object]:
        resp = await async_client.get("/reports/inventory", headers=headers, params={
            "date_from": date_from, "date_to": date_to, "group_by": "product", "sort_by": "sku",
        })
        assert resp.status_code == 200, resp.text
        rows = {row["sku_code"]: row for row in resp.json()["rows"]}
        return rows.get(sku, {})

    def _assert_balances(
        row: dict[str, object], *, opening: int, in_qty: int, out_qty: int, closing: int
    ) -> None:
        assert row["opening_balance"] == opening, row
        assert row["total_in"] == in_qty, row
        assert row["total_out"] == out_qty, row
        assert row["closing_balance"] == closing, row
        assert row["opening_balance"] + row["total_in"] - row["total_out"] == row["closing_balance"]

    # --- Август (прошлый, полностью законченный месяц) ---
    august = ("2026-08-01T00:00:00", "2026-09-01T00:00:00")
    p_august = await _product_row(*august, sku="EQ-P")
    _assert_balances(p_august, opening=0, in_qty=20, out_qty=5, closing=15)
    # Q ничего не делала в августе и на тот момент ничего не «стало» — не видна.
    assert await _product_row(*august, sku="EQ-Q") == {}

    overview_august = await async_client.get(
        "/reports/overview", headers=headers,
        params={"date_from": august[0], "date_to": august[1]},
    )
    assert overview_august.status_code == 200, overview_august.text
    ov_august = overview_august.json()
    assert ov_august["opening_balance"] == 0
    assert ov_august["in_qty"] == 20 and ov_august["out_qty"] == 5
    assert ov_august["closing_balance"] == 15
    assert ov_august["closing_balance_is_current"] is False

    seller_august = await async_client.get(
        "/reports/inventory", headers=headers,
        params={"date_from": august[0], "date_to": august[1], "group_by": "seller"},
    )
    seller_row_august = seller_august.json()["rows"][0]
    assert seller_row_august["product_count"] == 1  # только P
    _assert_balances(seller_row_august, opening=0, in_qty=20, out_qty=5, closing=15)

    # --- Сентябрь (текущий месяц — "сегодня" внутри периода) ---
    september = ("2026-09-01T00:00:00", "2026-10-01T00:00:00")
    p_september = await _product_row(*september, sku="EQ-P")
    # «Было на начало» сентября обязано совпасть с «стало» августа (C3).
    _assert_balances(p_september, opening=15, in_qty=8, out_qty=3, closing=20)
    q_september = await _product_row(*september, sku="EQ-Q")
    _assert_balances(q_september, opening=0, in_qty=5, out_qty=0, closing=5)

    overview_september = await async_client.get(
        "/reports/overview", headers=headers,
        params={"date_from": september[0], "date_to": september[1]},
    )
    ov_september = overview_september.json()
    # Сумма «было» по товарам: P(15) + Q(0).
    assert ov_september["opening_balance"] == 15
    assert ov_september["in_qty"] == 13 and ov_september["out_qty"] == 3
    assert ov_september["closing_balance"] == 25
    assert ov_september["closing_balance_is_current"] is True
    # R8: «Остаток сейчас» суммарно равен каталогу (сумме InventoryBalance).
    assert ov_september["closing_balance"] == 20 + 5

    seller_september = await async_client.get(
        "/reports/inventory", headers=headers,
        params={"date_from": september[0], "date_to": september[1], "group_by": "seller"},
    )
    seller_row_september = seller_september.json()["rows"][0]
    assert seller_row_september["product_count"] == 2
    _assert_balances(seller_row_september, opening=15, in_qty=13, out_qty=3, closing=25)


@pytest.mark.asyncio
async def test_product_with_balance_never_moved_is_shown(async_client: AsyncClient) -> None:
    """WMS-531 R9: товар, у которого вообще никогда не было движений, но есть
    остаток (например, стартовая выгрузка остатков без движения), всё равно
    виден — иначе плитка «Остаток сейчас» не совпадёт с каталогом (R8)."""
    headers, tenant_id, _user_id = await _org(async_client, name="Wms531r9")
    seller_id = await _seller(async_client, headers, "R9 seller")
    _warehouse_id, location_id = await _warehouse_location(async_client, headers, name="r9wh")
    async with SessionLocal() as session:
        product_id = await _product(
            session, tenant_id=tenant_id, seller_id=seller_id, name="Dormant", sku="R9-DORM"
        )
        session.add(InventoryBalance(
            tenant_id=tenant_id, product_id=product_id,
            storage_location_id=location_id, quantity=42,
        ))
        await session.commit()

    resp = await async_client.get(
        "/reports/inventory", headers=headers, params={**PERIOD, "group_by": "product"}
    )
    assert resp.status_code == 200, resp.text
    rows = {row["sku_code"]: row for row in resp.json()["rows"]}
    assert "R9-DORM" in rows
    row = rows["R9-DORM"]
    assert row["total_in"] == 0 and row["total_out"] == 0
    assert row["opening_balance"] == 42 == row["closing_balance"]

    overview = await async_client.get("/reports/overview", headers=headers, params=PERIOD)
    assert overview.json()["closing_balance"] == 42


@pytest.mark.asyncio
async def test_warehouse_id_is_fully_ignored(async_client: AsyncClient) -> None:
    """WMS-531 R5/C6: склада в отчёте больше нет — перенос между складами не
    виден ни в одном из трёх эндпоинтов, а параметр warehouse_id старого
    клиента не меняет ни одного числа."""
    headers, tenant_id, _user_id = await _org(async_client, name="Wms531r5")
    seller_id = await _seller(async_client, headers, "R5 seller")
    warehouse_a, location_a = await _warehouse_location(async_client, headers, name="r5wha")
    warehouse_b, location_b = await _warehouse_location(async_client, headers, name="r5whb")

    async with SessionLocal() as session:
        product_id = await _product(
            session, tenant_id=tenant_id, seller_id=seller_id, name="Moved", sku="R5-MOVED"
        )
        session.add(_movement(
            tenant_id=tenant_id, product_id=product_id, seller_id=seller_id,
            warehouse_id=warehouse_a, location_id=location_a, quantity_delta=10,
            movement_type="inbound_intake",
        ))
        group = uuid.uuid4()
        session.add(_movement(
            tenant_id=tenant_id, product_id=product_id, seller_id=seller_id,
            warehouse_id=warehouse_a, location_id=location_a, quantity_delta=-4,
            movement_type="stock_transfer_out", transfer_group_id=group,
        ))
        session.add(_movement(
            tenant_id=tenant_id, product_id=product_id, seller_id=seller_id,
            warehouse_id=warehouse_b, location_id=location_b, quantity_delta=4,
            movement_type="stock_transfer_in", transfer_group_id=group,
        ))
        session.add(InventoryBalance(
            tenant_id=tenant_id, product_id=product_id, storage_location_id=location_b, quantity=10,
        ))
        await session.commit()

    # «Прямо сейчас» тикает между тремя вызовами независимо от warehouse_id —
    # это не про склад, исключаем из сравнения.
    volatile_keys = {"generated_at", "closing_balance_as_of"}

    def _stable(payload: dict[str, object]) -> dict[str, object]:
        return {k: v for k, v in payload.items() if k not in volatile_keys}

    for path, extra_params in (
        ("/reports/inventory", {"group_by": "product"}),
        ("/reports/inventory", {"group_by": "seller"}),
        ("/reports/inventory", {"group_by": "operation"}),
        ("/reports/overview", {}),
    ):
        without = await async_client.get(path, headers=headers, params={**PERIOD, **extra_params})
        with_a = await async_client.get(
            path, headers=headers,
            params={**PERIOD, **extra_params, "warehouse_id": str(warehouse_a)},
        )
        with_b = await async_client.get(
            path, headers=headers,
            params={**PERIOD, **extra_params, "warehouse_id": str(warehouse_b)},
        )
        assert without.status_code == with_a.status_code == with_b.status_code == 200
        assert _stable(without.json()) == _stable(with_a.json()) == _stable(with_b.json()), path

    # Перемещение не видно нигде: ни строкой, ни в приходе/расходе.
    operation_rows = await async_client.get(
        "/reports/inventory", headers=headers, params={**PERIOD, "group_by": "operation"}
    )
    assert [row["operation"] for row in operation_rows.json()["rows"]] == ["Приёмка"]
    product_row = (await async_client.get(
        "/reports/inventory", headers=headers, params={**PERIOD, "group_by": "product"}
    )).json()["rows"][0]
    assert product_row["total_in"] == 10 and product_row["total_out"] == 0
    assert product_row["closing_balance"] == 10

    movements = await async_client.get(
        "/reports/inventory/movements", headers=headers,
        params={**PERIOD, "product_id": str(product_id), "warehouse_id": str(warehouse_a)},
    )
    assert [row["operation"] for row in movements.json()["rows"]] == ["Приёмка"]


@pytest.mark.asyncio
async def test_load_more_reaches_every_product_and_every_movement(
    async_client: AsyncClient,
) -> None:
    """WMS-531 R11/C7: больше 50 товаров у селлера и больше 200 движений у
    одного товара — «Загрузить ещё» (постраничность) обязана добраться до
    последней строки, а сумма показанных движений — совпасть с приходом и
    расходом строки товара."""
    headers, tenant_id, _user_id = await _org(async_client, name="Wms531r11")
    seller_id = await _seller(async_client, headers, "R11 seller")
    warehouse_id, location_id = await _warehouse_location(async_client, headers, name="r11wh")

    async with SessionLocal() as session:
        many_product_ids = []
        for i in range(65):
            pid = await _product(
                session, tenant_id=tenant_id, seller_id=seller_id,
                name=f"Bulk {i:03}", sku=f"R11-{i:03}"
            )
            many_product_ids.append(pid)
            session.add(_movement(
                tenant_id=tenant_id, product_id=pid, seller_id=seller_id,
                warehouse_id=warehouse_id, location_id=location_id, quantity_delta=1,
                movement_type="inbound_intake",
            ))
        heavy_product_id = await _product(
            session, tenant_id=tenant_id, seller_id=seller_id, name="Heavy", sku="R11-HEAVY"
        )
        for i in range(210):
            delta = 1 if i % 2 == 0 else -1
            session.add(_movement(
                tenant_id=tenant_id, product_id=heavy_product_id, seller_id=seller_id,
                warehouse_id=warehouse_id, location_id=location_id, quantity_delta=delta,
                movement_type="inbound_intake" if delta > 0 else "marketplace_unload",
                created_at=datetime(2026, 9, 10, 0, 0, tzinfo=UTC) + timedelta(minutes=i),
            ))
        session.add(InventoryBalance(
            tenant_id=tenant_id, product_id=heavy_product_id,
            storage_location_id=location_id, quantity=105,
        ))
        await session.commit()

    seen_skus: set[str] = set()
    page = 1
    total_declared = None
    while True:
        resp = await async_client.get("/reports/inventory", headers=headers, params={
            **PERIOD, "group_by": "product", "page": page, "sort_by": "sku",
        })
        assert resp.status_code == 200, resp.text
        payload = resp.json()
        total_declared = payload["total"]
        for row in payload["rows"]:
            seen_skus.add(row["sku_code"])
        if page * payload["page_size"] >= total_declared:
            break
        page += 1
    assert total_declared == 66  # 65 bulk + heavy
    assert len(seen_skus) == 66
    assert "R11-HEAVY" in seen_skus

    seen_movement_ids: set[str] = set()
    page = 1
    total_movements = None
    while True:
        resp = await async_client.get("/reports/inventory/movements", headers=headers, params={
            **PERIOD, "product_id": str(heavy_product_id), "page": page,
        })
        assert resp.status_code == 200, resp.text
        payload = resp.json()
        total_movements = payload["total"]
        for row in payload["rows"]:
            seen_movement_ids.add(row["id"])
        if not payload["truncated"]:
            break
        page += 1
    assert total_movements == 210
    assert len(seen_movement_ids) == 210

    product_row = (await async_client.get(
        "/reports/inventory", headers=headers,
        params={**PERIOD, "group_by": "product", "search": "R11-HEAVY"},
    )).json()["rows"][0]
    assert product_row["total_in"] == 105 and product_row["total_out"] == 105


@pytest.mark.asyncio
async def test_split_fbs_writeoff_is_not_flagged_as_incomplete_transfer(
    async_client: AsyncClient,
) -> None:
    """Разделённое списание FBS (несколько строк одним transfer_group_id, но
    ОДНИМ и тем же movement_type — не парой вход/выход) не должно путаться с
    неполным перемещением: обе строки — реальный расход, полностью законный."""
    headers, tenant_id, _user_id = await _org(async_client, name="Wms531splitfbs")
    seller_id = await _seller(async_client, headers, "Split seller")
    warehouse_id, location_id = await _warehouse_location(async_client, headers, name="splitwh")
    async with SessionLocal() as session:
        product_id = await _product(
            session, tenant_id=tenant_id, seller_id=seller_id, name="Split", sku="SPLIT-1"
        )
        group = uuid.uuid4()
        session.add(_movement(
            tenant_id=tenant_id, product_id=product_id, seller_id=seller_id,
            warehouse_id=warehouse_id, location_id=location_id, quantity_delta=-2,
            movement_type="fbs_shipment", transfer_group_id=group,
        ))
        session.add(_movement(
            tenant_id=tenant_id, product_id=product_id, seller_id=seller_id,
            warehouse_id=warehouse_id, location_id=location_id, quantity_delta=-1,
            movement_type="fbs_shipment", transfer_group_id=group,
        ))
        session.add(InventoryBalance(
            tenant_id=tenant_id, product_id=product_id, storage_location_id=location_id, quantity=0,
        ))
        await session.commit()

    resp = await async_client.get(
        "/reports/inventory", headers=headers, params={**PERIOD, "group_by": "product"}
    )
    row = resp.json()["rows"][0]
    assert row["integrity_error"] is False
    assert row["total_out"] == 3


@pytest.mark.asyncio
async def test_incomplete_location_pair_marks_product_without_warehouse_filter(
    async_client: AsyncClient,
) -> None:
    """WMS-531 R7: неполное перемещение (одна сторона потеряна) помечает
    товар даже без выбора склада — сейчас склада вообще нет в отчёте. Работает
    и для парного stock_transfer_in/out, и для одностороннего типа
    (warehouse_map_move и т. п.), где обе стороны пишутся одним movement_type."""
    headers, tenant_id, _user_id = await _org(async_client, name="Wms531incomplete")
    seller_id = await _seller(async_client, headers, "Incomplete seller")
    warehouse_id, location_id = await _warehouse_location(async_client, headers, name="incwh")
    async with SessionLocal() as session:
        broken_transfer_id = await _product(
            session, tenant_id=tenant_id, seller_id=seller_id, name="Broken transfer", sku="INC-1"
        )
        session.add(_movement(
            tenant_id=tenant_id, product_id=broken_transfer_id, seller_id=seller_id,
            warehouse_id=warehouse_id, location_id=location_id, quantity_delta=-3,
            movement_type="stock_transfer_out", transfer_group_id=uuid.uuid4(),
        ))
        broken_map_id = await _product(
            session, tenant_id=tenant_id, seller_id=seller_id, name="Broken map", sku="INC-2"
        )
        session.add(_movement(
            tenant_id=tenant_id, product_id=broken_map_id, seller_id=seller_id,
            warehouse_id=warehouse_id, location_id=location_id, quantity_delta=-2,
            movement_type="warehouse_map_move", transfer_group_id=uuid.uuid4(),
        ))
        healthy_id = await _product(
            session, tenant_id=tenant_id, seller_id=seller_id, name="Healthy", sku="INC-3"
        )
        session.add(_movement(
            tenant_id=tenant_id, product_id=healthy_id, seller_id=seller_id,
            warehouse_id=warehouse_id, location_id=location_id, quantity_delta=1,
            movement_type="inbound_intake",
        ))
        for pid in (broken_transfer_id, broken_map_id, healthy_id):
            session.add(InventoryBalance(
                tenant_id=tenant_id, product_id=pid, storage_location_id=location_id, quantity=0,
            ))
        await session.commit()

    resp = await async_client.get(
        "/reports/inventory", headers=headers,
        params={**PERIOD, "group_by": "product", "sort_by": "sku"}
    )
    rows = {row["sku_code"]: row for row in resp.json()["rows"]}
    assert rows["INC-1"]["integrity_error"] is True
    assert rows["INC-2"]["integrity_error"] is True
    assert rows["INC-3"]["integrity_error"] is False

    overview = await async_client.get("/reports/overview", headers=headers, params=PERIOD)
    assert overview.json()["has_incomplete_transfer"] is True


@pytest.mark.asyncio
async def test_ozon_positions_lookup_is_scoped_to_the_requested_period(
    async_client: AsyncClient,
) -> None:
    """WMS-531 R15: раньше запрос к FbsShipmentReversalLedger читал вообще все
    строки с ozon_positions_json по арендатору — на годовом объёме это
    означало загрузку всего исторического журнала в память при каждом
    открытии отчёта. Проверяем, что позиции ИЗ ДРУГОГО периода не тянутся
    и не портят числа текущего запроса (испорченный movement_id из чужого
    периода не должен найтись и не должен уронить запрос)."""
    headers, tenant_id, _user_id = await _org(async_client, name="Wms531r15")
    seller_id = await _seller(async_client, headers, "R15 seller")
    warehouse_id, location_id = await _warehouse_location(async_client, headers, name="r15wh")
    async with SessionLocal() as session:
        product_id = await _product(
            session, tenant_id=tenant_id, seller_id=seller_id, name="R15", sku="R15-1"
        )
        order = FbsOrder(
            tenant_id=tenant_id, seller_id=seller_id, marketplace="ozon", wb_order_id=-1,
            external_order_id="OLD-OZON-ORDER", product_id=product_id, warehouse_id=warehouse_id,
            created_at_wb=datetime(2025, 1, 1, tzinfo=UTC),
            deadline_at=datetime(2025, 1, 2, tzinfo=UTC),
            mapping_status="mapped", reserve_status="no_stock",
        )
        session.add(order)
        await session.flush()
        old_movement = _movement(
            tenant_id=tenant_id, product_id=product_id, seller_id=seller_id,
            warehouse_id=warehouse_id, location_id=location_id, quantity_delta=-1,
            movement_type="fbs_shipment", created_at=datetime(2025, 1, 1, MSK_NOON, tzinfo=UTC),
        )
        session.add(old_movement)
        await session.flush()
        # Старая запись журнала — далеко за пределами запрашиваемого периода.
        session.add(FbsShipmentReversalLedger(
            tenant_id=tenant_id, fbs_order_id=order.id, product_id=product_id,
            storage_location_id=location_id, quantity=1,
            ozon_positions_json=[
                {"product_id": str(product_id), "movement_id": str(old_movement.id)}
            ],
        ))
        # Текущее движение в запрашиваемом периоде — без документа вовсе.
        current_movement = _movement(
            tenant_id=tenant_id, product_id=product_id, seller_id=seller_id,
            warehouse_id=warehouse_id, location_id=location_id, quantity_delta=-1,
            movement_type="fbs_shipment",
        )
        session.add(current_movement)
        await session.commit()

    resp = await async_client.get(
        "/reports/inventory/movements", headers=headers,
        params={**PERIOD, "operation": "FBS"},
    )
    assert resp.status_code == 200, resp.text
    rows = {row["id"]: row for row in resp.json()["rows"]}
    assert str(current_movement.id) in rows
    assert rows[str(current_movement.id)]["document"] is None


async def _seed_excel_scenario(
    async_client: AsyncClient, headers: dict[str, str], *, tenant_id: uuid.UUID,
) -> tuple[uuid.UUID, uuid.UUID]:
    seller_id = await _seller(async_client, headers, "Excel seller")
    warehouse_id, location_id = await _warehouse_location(async_client, headers, name="xlswh")
    async with SessionLocal() as session:
        product_id = await _product(
            session, tenant_id=tenant_id, seller_id=seller_id, name="Excel product", sku="XLS-1"
        )
        intake = InboundIntakeRequest(
            tenant_id=tenant_id, seller_id=seller_id, warehouse_id=warehouse_id,
            status="done", operation_type="inbound", display_number="№000042",
        )
        session.add(intake)
        await session.flush()
        line = InboundIntakeLine(request_id=intake.id, product_id=product_id, expected_qty=9)
        session.add(line)
        await session.flush()
        session.add(_movement(
            tenant_id=tenant_id, product_id=product_id, seller_id=seller_id,
            warehouse_id=warehouse_id, location_id=location_id, quantity_delta=9,
            movement_type="inbound_intake", inbound_intake_line_id=line.id,
            created_at=datetime(2026, 9, 5, MSK_NOON, tzinfo=UTC),
        ))
        session.add(_movement(
            tenant_id=tenant_id, product_id=product_id, seller_id=seller_id,
            warehouse_id=warehouse_id, location_id=location_id, quantity_delta=-2,
            movement_type="marketplace_unload",
            created_at=datetime(2026, 9, 12, MSK_NOON, tzinfo=UTC),
        ))
        session.add(InventoryBalance(
            tenant_id=tenant_id, product_id=product_id, storage_location_id=location_id, quantity=7,
        ))
        await session.commit()
    return seller_id, product_id


@pytest.mark.asyncio
async def test_excel_export_by_product_matches_screen_with_outline_and_totals(
    async_client: AsyncClient,
) -> None:
    """WMS-531 R12/R13: файл «По товарам» — та же иерархия, что на экране,
    с уровнями группировки, числовыми ячейками и «Итого», равным плиткам."""
    headers, tenant_id, _user_id = await _org(async_client, name="Wms531xlsx")
    _seller_id, _product_id = await _seed_excel_scenario(async_client, headers, tenant_id=tenant_id)

    overview = await async_client.get("/reports/overview", headers=headers, params=PERIOD)
    ov = overview.json()

    response = await async_client.get(
        "/reports/inventory/export.xlsx", headers=headers,
        params={**PERIOD, "group_by": "product"},
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    disposition = response.headers["content-disposition"]
    assert "filename*=UTF-8''" in disposition
    assert "01.09.2026" in disposition and "30.09.2026" in disposition

    workbook = load_workbook(io.BytesIO(response.content))
    sheet = workbook.active
    assert sheet is not None
    header_row = [cell.value for cell in sheet[1]]
    assert header_row == [
        "Селлер", "Товар", "Артикул продавца", "ШК", "Дата", "Движение", "Документ",
        "Было на начало", "Приход", "Расход", "Остаток на конец",
    ]
    assert sheet.freeze_panes == "A2"

    rows = list(sheet.iter_rows(min_row=2, values_only=False))
    seller_row = rows[0]
    assert seller_row[0].value == "Excel seller"
    assert sheet.row_dimensions[seller_row[0].row].outlineLevel == 0
    product_row = rows[1]
    assert product_row[1].value == "Excel product"
    assert sheet.row_dimensions[product_row[1].row].outlineLevel == 1
    movement_rows = [r for r in rows[2:] if r[4].value is not None]
    assert len(movement_rows) == 2
    for movement_row in movement_rows:
        assert sheet.row_dimensions[movement_row[4].row].outlineLevel == 2
        assert isinstance(movement_row[8].value, int) or isinstance(movement_row[9].value, int)
    documents = {cell.value for row in movement_rows for cell in [row[6]]}
    # WMS-531 ревью Astra, F9: ячейка «Документ» несёт подпись вида, а не
    # голый номер — «Приёмка №000042», а не «№000042».
    assert "Приёмка №000042" in documents
    assert "без документа" in documents

    total_row = [cell.value for cell in sheet[sheet.max_row]]
    assert total_row[0] == "Итого"
    assert total_row[7] == ov["opening_balance"]
    assert total_row[8] == ov["in_qty"]
    assert total_row[9] == ov["out_qty"]
    assert total_row[10] == ov["closing_balance"]


@pytest.mark.asyncio
async def test_excel_export_by_operation_fills_product_column_on_movement_rows(
    async_client: AsyncClient,
) -> None:
    """WMS-531 R12.5: в группировке «По операциям» строка движения обязана
    показывать товар — под одним видом лежат разные товары."""
    headers, tenant_id, _user_id = await _org(async_client, name="Wms531xlsxop")
    _seller_id, _product_id = await _seed_excel_scenario(async_client, headers, tenant_id=tenant_id)

    response = await async_client.get(
        "/reports/inventory/export.xlsx", headers=headers,
        params={**PERIOD, "group_by": "operation"},
    )
    assert response.status_code == 200, response.text
    workbook = load_workbook(io.BytesIO(response.content))
    sheet = workbook.active
    assert sheet is not None
    rows = list(sheet.iter_rows(min_row=2, values_only=True))
    product_names_on_movement_rows = [row[1] for row in rows if row[4] is not None and row[1]]
    assert "Excel product" in product_names_on_movement_rows


@pytest.mark.asyncio
async def test_excel_export_for_seller_cabinet_has_no_seller_column_or_level(
    async_client: AsyncClient,
) -> None:
    """WMS-531 R12.9: в кабинете селлера файл — без колонки и уровня «Селлер»."""
    headers, tenant_id, _user_id = await _org(async_client, name="Wms531xlsxseller")
    seller_id, _product_id = await _seed_excel_scenario(async_client, headers, tenant_id=tenant_id)
    email = f"xlsx-seller-{uuid.uuid4().hex[:10]}@example.com"
    created = await async_client.post(
        "/auth/seller-accounts", headers=headers,
        json={"seller_id": str(seller_id), "email": email, "password": "password123"},
    )
    assert created.status_code in (200, 201), created.text
    login = await async_client.post("/auth/login", json={"email": email, "password": "password123"})
    assert login.status_code == 200, login.text
    seller_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    response = await async_client.get(
        "/reports/inventory/export.xlsx", headers=seller_headers,
        params={**PERIOD, "group_by": "product"},
    )
    assert response.status_code == 200, response.text
    workbook = load_workbook(io.BytesIO(response.content))
    sheet = workbook.active
    assert sheet is not None
    header_row = [cell.value for cell in sheet[1]]
    assert header_row == [
        "Товар", "Артикул продавца", "ШК", "Дата", "Движение", "Документ",
        "Было на начало", "Приход", "Расход", "Остаток на конец",
    ]
    all_values = [cell.value for row in sheet.iter_rows() for cell in row]
    assert "Excel seller" not in all_values


@pytest.mark.asyncio
async def test_excel_export_rejects_empty_period(async_client: AsyncClient) -> None:
    """WMS-531 R14: нечего выгружать — понятная ошибка, а не пустой/битый файл."""
    headers, _tenant_id, _user_id = await _org(async_client, name="Wms531xlsxempty")
    response = await async_client.get(
        "/reports/inventory/export.xlsx", headers=headers, params=PERIOD,
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "nothing to export for the selected period"
