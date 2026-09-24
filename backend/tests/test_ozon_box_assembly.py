"""WMS-355/357: packages, durable result and retries across order boxes."""

from __future__ import annotations

import base64
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import fitz
import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.fbs_supplies import retry_fbs_packing_box_qr
from app.models.fbs_order import FbsOrder, FbsOrderProduct
from app.models.fbs_packing_box import FbsPackingBox, FbsPackingBoxItem
from app.models.fbs_supply import FbsSupply
from app.models.marketplace_account import MarketplaceAccount
from app.models.product import Product
from app.models.seller import Seller
from app.models.tenant import Tenant
from app.models.warehouse import Warehouse
from app.models.warehouse_box import WarehouseBox
from app.services import fbs_print_asset_service as print_asset_svc
from app.services import ozon_box_assembly_service as assembly_svc
from app.services.fbs_print_asset_service import combine_ozon_order_labels
from app.services.integration_fernet import encrypt_secret
from app.services.marketplace_provider import (
    FakeMarketplaceTransport,
    MarketplaceProviderError,
    OzonMarketplaceProvider,
)
from app.services.ozon_box_assembly_service import assemble_box_order, order_packages
from app.services.ozon_fbs_errors import OzonFbsProcessError


async def seed_boxes(
    session: AsyncSession, order: FbsOrder, supply: FbsSupply
) -> list[FbsPackingBox]:
    """Each position goes to one distinct physical box, with no copied quantity."""
    positions = list(
        (
            await session.scalars(
                select(FbsOrderProduct)
                .where(
                    FbsOrderProduct.order_id == order.id,
                )
                .order_by(FbsOrderProduct.position_index)
            )
        ).all()
    )
    boxes = []
    last_number = int(
        await session.scalar(
            select(func.max(FbsPackingBox.box_number)).where(
                FbsPackingBox.supply_id == supply.id,
            )
        )
        or 0
    )
    for number, position in enumerate(positions, last_number + 1):
        physical = WarehouseBox(
            tenant_id=order.tenant_id,
            warehouse_id=supply.warehouse_id,
            internal_barcode=f"ASSEMBLY-{uuid.uuid4().hex}",
        )
        session.add(physical)
        await session.flush()
        box = FbsPackingBox(
            tenant_id=order.tenant_id,
            supply_id=supply.id,
            warehouse_box_id=physical.id,
            box_number=number,
        )
        session.add(box)
        await session.flush()
        session.add(
            FbsPackingBoxItem(
                tenant_id=order.tenant_id,
                box_id=box.id,
                fbs_order_id=order.id,
                order_product_id=position.id,
            )
        )
        boxes.append(box)
    await session.commit()
    return boxes


async def _seed(session: AsyncSession) -> tuple[FbsOrder, FbsSupply, list[FbsPackingBox]]:
    tenant = Tenant(name="Assembly", slug=f"assembly-{uuid.uuid4().hex}")
    seller = Seller(tenant=tenant, name="Seller")
    warehouse = Warehouse(tenant=tenant, name="Warehouse", code="ASM")
    product = Product(tenant=tenant, seller=seller, name="Product", sku_code="ASM")
    supply = FbsSupply(
        tenant=tenant,
        seller=seller,
        warehouse=warehouse,
        marketplace="ozon",
        name="Assembly",
        status="assembling",
        delivery_type="warehouse_sc",
    )
    now = datetime.now(UTC)
    order = FbsOrder(
        tenant=tenant,
        seller=seller,
        warehouse=warehouse,
        product=product,
        supply=supply,
        marketplace="ozon",
        external_order_id="POSTING",
        wb_order_id=-123,
        mapping_status="mapped",
        reserve_status="reserved",
        created_at_wb=now,
        deadline_at=now + timedelta(days=1),
    )
    session.add_all([tenant, seller, warehouse, product, supply, order])
    await session.flush()
    for index, quantity in enumerate([2, 3]):
        session.add(
            FbsOrderProduct(
                order_id=order.id,
                product_id=product.id,
                ozon_sku=3001 + index,
                quantity=quantity,
                offer_id=f"SKU-{index}",
                name="Product",
                position_index=index,
            )
        )
    await session.commit()
    return order, supply, await seed_boxes(session, order, supply)


def _transport() -> FakeMarketplaceTransport:
    return FakeMarketplaceTransport(
        endpoint_responses={
            "/v3/posting/fbs/get": {
                "result": {"posting_number": "POSTING", "status": "awaiting_packaging"}
            },
            "/v1/posting/fbs/restrictions": {"result": {"posting_number": "POSTING"}},
            "/v4/posting/fbs/ship": {"result": ["POSTING-1", "POSTING-2"]},
        }
    )


async def test_qr_sends_every_box_and_repeat_never_ships_again(db_session: AsyncSession) -> None:
    order, supply, boxes = await _seed(db_session)
    transport = _transport()
    provider = OzonMarketplaceProvider(transport=transport)
    for box in boxes:
        assert (
            await assemble_box_order(
                db_session,
                order.tenant_id,
                supply.id,
                box.id,
                provider=provider,
                credentials=("c", "k"),
            )
            == order.id
        )
        transport.endpoint_responses["/v3/posting/fbs/get"] = {
            "result": {"posting_number": "POSTING", "status": "awaiting_deliver"}
        }
    calls = [payload for path, payload in transport.endpoint_calls if path.endswith("/ship")]
    assert calls == [
        {
            "posting_number": "POSTING",
            "packages": [
                {"products": [{"product_id": 3001, "quantity": 2}]},
                {"products": [{"product_id": 3002, "quantity": 3}]},
            ],
            "with": {"additional_data": True},
        }
    ]
    await db_session.rollback()
    await db_session.refresh(order)
    assert order.meta_details_json["ozon_assembly"]["posting_numbers"] == ["POSTING-1", "POSTING-2"]


async def test_partial_assignment_fails_before_any_external_request(
    db_session: AsyncSession,
) -> None:
    order, supply, boxes = await _seed(db_session)
    item = await db_session.scalar(
        select(FbsPackingBoxItem).where(FbsPackingBoxItem.box_id == boxes[1].id)
    )
    await db_session.delete(item)
    await db_session.commit()
    transport = _transport()
    with pytest.raises(OzonFbsProcessError, match="ozon_box_positions_incomplete"):
        await assemble_box_order(
            db_session,
            order.tenant_id,
            supply.id,
            boxes[0].id,
            provider=OzonMarketplaceProvider(transport=transport),
            credentials=("c", "k"),
        )
    assert transport.endpoint_calls == []


async def test_timeout_retries_readback_without_resending(db_session: AsyncSession) -> None:
    order, supply, boxes = await _seed(db_session)
    tenant_id, supply_id, first_box_id, second_box_id = (
        order.tenant_id,
        supply.id,
        boxes[0].id,
        boxes[1].id,
    )
    transport = _transport()
    transport.errors["/v4/posting/fbs/ship"] = MarketplaceProviderError("ozon", 503, {})
    provider = OzonMarketplaceProvider(transport=transport)
    with pytest.raises(MarketplaceProviderError):
        await assemble_box_order(
            db_session,
            tenant_id,
            supply_id,
            first_box_id,
            provider=provider,
            credentials=("c", "k"),
        )
    await db_session.rollback()
    with pytest.raises(OzonFbsProcessError, match="ozon_assembly_unconfirmed"):
        await assemble_box_order(
            db_session,
            tenant_id,
            supply_id,
            first_box_id,
            provider=provider,
            credentials=("c", "k"),
        )
    assert len([path for path, _ in transport.endpoint_calls if path.endswith("/ship")]) == 1
    transport.endpoint_responses["/v3/posting/fbs/get"] = {
        "result": {
            "posting_number": "POSTING",
            "status": "awaiting_deliver",
            "related_postings": {"related_posting_numbers": ["POSTING-1", "POSTING-2"]},
        }
    }
    await assemble_box_order(
        db_session, tenant_id, supply_id, second_box_id, provider=provider, credentials=("c", "k")
    )
    assert order.meta_details_json["ozon_assembly"]["posting_numbers"] == ["POSTING-1", "POSTING-2"]
    assert len([path for path, _ in transport.endpoint_calls if path.endswith("/ship")]) == 1


async def test_packages_take_live_quantity_only_from_position(db_session: AsyncSession) -> None:
    order, _, _ = await _seed(db_session)
    position = await db_session.scalar(
        select(FbsOrderProduct).where(
            FbsOrderProduct.order_id == order.id,
            FbsOrderProduct.position_index == 0,
        )
    )
    position.quantity = 7
    await db_session.flush()
    packages = await order_packages(db_session, order)
    assert packages[0]["products"][0]["quantity"] == 7


def test_pdf_contains_every_result_posting_label() -> None:
    rows = []
    for number in ["CHILD-1", "CHILD-2"]:
        with fitz.open() as document:
            page = document.new_page()
            page.insert_text((30, 30), number)
            rows.append(
                {
                    "posting_number": number,
                    "content_type": "application/pdf",
                    "file": base64.b64encode(document.tobytes()).decode("ascii"),
                }
            )
    combined = combine_ozon_order_labels("PARENT", ["CHILD-1", "CHILD-2"], rows)
    with fitz.open(stream=base64.b64decode(combined["file"]), filetype="pdf") as document:
        assert len(document) == 2
        assert "CHILD-1" in document[0].get_text()
        assert "CHILD-2" in document[1].get_text()


def test_one_missing_split_label_never_yields_partial_ready_pdf() -> None:
    result = combine_ozon_order_labels("PARENT", ["A", "B"], [{"posting_number": "A", "file": "x"}])
    assert result["error_code"] == "ozon_label_empty"
    assert "file" not in result


async def test_partial_ship_result_cannot_be_handed_off(db_session: AsyncSession) -> None:
    from app.services.ozon_fbs_process_service import handoff_supply

    order, supply, boxes = await _seed(db_session)
    transport = _transport()
    transport.endpoint_responses["/v4/posting/fbs/ship"] = {"result": ["POSTING-1"]}
    provider = OzonMarketplaceProvider(transport=transport)
    with pytest.raises(OzonFbsProcessError, match="ozon_assembly_unconfirmed"):
        await assemble_box_order(
            db_session,
            order.tenant_id,
            supply.id,
            boxes[0].id,
            provider=provider,
            credentials=("c", "k"),
        )
    assert order.meta_details_json["ozon_assembly"]["posting_numbers"] == ["POSTING-1"]
    transport.endpoint_calls.clear()
    with pytest.raises(OzonFbsProcessError, match="ozon_assembly_unconfirmed"):
        await handoff_supply(
            db_session,
            supply=supply,
            orders=[order],
            provider=provider,
            client_id="c",
            api_key="k",
        )
    assert transport.endpoint_calls == []


async def test_handoff_revalidates_the_complete_position_set(db_session: AsyncSession) -> None:
    from app.services.ozon_fbs_process_service import handoff_supply

    order, supply, boxes = await _seed(db_session)
    transport = _transport()
    provider = OzonMarketplaceProvider(transport=transport)
    await assemble_box_order(
        db_session,
        order.tenant_id,
        supply.id,
        boxes[0].id,
        provider=provider,
        credentials=("c", "k"),
    )
    # Simulate damaged historical data bypassing the mutation guard.
    item = await db_session.scalar(
        select(FbsPackingBoxItem).where(
            FbsPackingBoxItem.box_id == boxes[1].id,
        )
    )
    assert item is not None
    await db_session.delete(item)
    await db_session.commit()
    transport.endpoint_calls.clear()
    with pytest.raises(OzonFbsProcessError, match="ozon_box_positions_incomplete"):
        await handoff_supply(
            db_session,
            supply=supply,
            orders=[order],
            provider=provider,
            client_id="c",
            api_key="k",
        )
    assert transport.endpoint_calls == []


async def test_confirmed_ship_failure_unfreezes_contents_and_allows_retry(
    db_session: AsyncSession,
) -> None:
    order, supply, boxes = await _seed(db_session)
    transport = _transport()
    provider = OzonMarketplaceProvider(transport=transport)
    args = (db_session, order.tenant_id, supply.id, boxes[0].id)
    await assemble_box_order(*args, provider=provider, credentials=("c", "k"))
    transport.endpoint_responses["/v3/posting/fbs/get"] = {
        "result": {
            "posting_number": "POSTING", "status": "awaiting_packaging",
            "substatus": "ship_failed",
        }
    }
    with pytest.raises(OzonFbsProcessError, match="ozon_ship_failed"):
        await assemble_box_order(*args, provider=provider, credentials=("c", "k"))
    await db_session.refresh(order)
    assert "ozon_assembly" not in (order.meta_details_json or {})
    assert order.supplier_status == "ship_failed"
    assert len([p for p, _ in transport.endpoint_calls if p.endswith("/ship")]) == 1
    # A new operator action can now retry the rejected assembly.
    transport.endpoint_responses["/v3/posting/fbs/get"] = {
        "result": {"posting_number": "POSTING", "status": "awaiting_packaging"}
    }
    await assemble_box_order(*args, provider=provider, credentials=("c", "k"))
    assert len([p for p, _ in transport.endpoint_calls if p.endswith("/ship")]) == 2


async def test_retry_qr_surfaces_ozon_label_error_and_keeps_assembly(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """WMS-526 F1: retry-qr used to swallow a failed label fetch and answer 200
    with no reason, leaving the operator unable to tell why the label never
    showed up. The assembly (ozon_assembly marker + /ship) must still be kept
    and never resent, but the endpoint now surfaces the label error."""
    order, supply, boxes = await _seed(db_session)
    db_session.add(
        MarketplaceAccount(
            tenant_id=order.tenant_id,
            seller_id=order.seller_id,
            marketplace="ozon",
            account_slot="primary",
            external_account_id="ozon-client",
            secret_encrypted=encrypt_secret("ozon-key"),
            is_active=True,
            validation_status="valid",
        )
    )
    await db_session.commit()

    transport = _transport()
    transport.errors["fetch_order_labels"] = MarketplaceProviderError("ozon", 502, {})
    provider = OzonMarketplaceProvider(transport=transport)

    # The endpoint calls assemble_box_order/ozon_order_label_fetcher without a
    # provider of its own, so it resolves one through these two factory hooks
    # exactly like production does once the live-API switch is on.
    monkeypatch.setattr(assembly_svc, "ozon_live_api_enabled", lambda: True)
    monkeypatch.setattr(assembly_svc, "build_ozon_provider", lambda: provider)
    monkeypatch.setattr(print_asset_svc, "ozon_live_api_enabled", lambda: True)
    monkeypatch.setattr(print_asset_svc, "build_ozon_provider", lambda: provider)

    user = SimpleNamespace(tenant_id=order.tenant_id, id=uuid.uuid4())

    with pytest.raises(HTTPException) as first_error:
        await retry_fbs_packing_box_qr(supply.id, boxes[0].id, user, db_session)
    assert first_error.value.status_code == 502
    detail = first_error.value.detail
    assert detail["code"] == "ozon_upstream_error"
    assert detail["message"] and detail["message"] != detail["code"]

    ship_calls = [path for path, _ in transport.endpoint_calls if path.endswith("/ship")]
    assert len(ship_calls) == 1

    await db_session.refresh(order)
    assert order.meta_details_json["ozon_assembly"]["posting_numbers"] == ["POSTING-1", "POSTING-2"]

    # Ozon now reports the posting as shipped, same as the real flow: a second
    # retry-qr must not resend /ship, only re-read and re-try the label.
    transport.endpoint_responses["/v3/posting/fbs/get"] = {
        "result": {"posting_number": "POSTING", "status": "awaiting_deliver"}
    }
    with pytest.raises(HTTPException) as second_error:
        await retry_fbs_packing_box_qr(supply.id, boxes[0].id, user, db_session)
    assert second_error.value.status_code == 502
    assert second_error.value.detail["code"] == "ozon_upstream_error"

    ship_calls_after_retry = [
        path for path, _ in transport.endpoint_calls if path.endswith("/ship")
    ]
    assert len(ship_calls_after_retry) == 1
