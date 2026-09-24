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
from app.db.session import SessionLocal
from app.models.fbs_order import FbsOrder, FbsOrderProduct
from app.models.fbs_packing_box import FbsPackingBox, FbsPackingBoxItem
from app.models.fbs_print_asset import (
    PRINT_ASSET_KIND_ORDER_STICKER,
    PRINT_ASSET_STATUS_READY,
    FbsPrintAsset,
)
from app.models.fbs_supply import FbsSupply
from app.models.fbs_trbx import FbsTrbx
from app.models.marketplace_account import MarketplaceAccount
from app.models.product import Product
from app.models.seller import Seller
from app.models.tenant import Tenant
from app.models.user import User
from app.models.warehouse import Warehouse
from app.models.warehouse_box import WarehouseBox
from app.services import fbs_packing_box_service as boxes_svc
from app.services import fbs_print_asset_service as print_asset_svc
from app.services import ozon_box_assembly_service as assembly_svc
from app.services.fbs_print_asset_service import combine_ozon_order_labels
from app.services.fbs_workspace_service import get_supply_workspace
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


def _pdf_label_row(posting_number: str) -> dict[str, str]:
    with fitz.open() as document:
        page = document.new_page()
        page.insert_text((30, 30), posting_number)
        content = document.tobytes()
    return {
        "posting_number": posting_number,
        "file": base64.b64encode(content).decode("ascii"),
        "content_type": "application/pdf",
    }


async def _workspace_box_rows(
    db_session: AsyncSession, tenant_id: uuid.UUID, supply_id: uuid.UUID
) -> dict[str, dict[str, object]]:
    workspace = await get_supply_workspace(db_session, tenant_id, supply_id)
    return {row["id"]: row for row in workspace["boxes"]}


async def test_label_error_persists_on_every_box_of_the_order_until_a_label_succeeds(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """WMS-526 R12: a failed label attempt shows a reason on every box row of
    that order, survives a fresh read of the supply (a page reload — not
    just the HTTP response of the failing call), and clears once a label
    actually comes back, without resending the already-confirmed /ship."""
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
    monkeypatch.setattr(assembly_svc, "ozon_live_api_enabled", lambda: True)
    monkeypatch.setattr(assembly_svc, "build_ozon_provider", lambda: provider)
    monkeypatch.setattr(print_asset_svc, "ozon_live_api_enabled", lambda: True)
    monkeypatch.setattr(print_asset_svc, "build_ozon_provider", lambda: provider)
    user = SimpleNamespace(tenant_id=order.tenant_id, id=uuid.uuid4())

    with pytest.raises(HTTPException):
        await retry_fbs_packing_box_qr(supply.id, boxes[0].id, user, db_session)

    expected_error = {"code": "ozon_upstream_error", "message": "Ozon временно недоступен."}
    box_rows = await _workspace_box_rows(db_session, order.tenant_id, supply.id)
    for box in boxes:
        assert box_rows[str(box.id)]["ozon_label_error"] == expected_error

    # Ozon now reports the posting as shipped, same as the real flow: the
    # retry below must not resend /ship.
    transport.endpoint_responses["/v3/posting/fbs/get"] = {
        "result": {"posting_number": "POSTING", "status": "awaiting_deliver"}
    }
    del transport.errors["fetch_order_labels"]
    transport.order_labels = [_pdf_label_row("POSTING-1"), _pdf_label_row("POSTING-2")]

    await retry_fbs_packing_box_qr(supply.id, boxes[1].id, user, db_session)

    box_rows = await _workspace_box_rows(db_session, order.tenant_id, supply.id)
    for box in boxes:
        assert box_rows[str(box.id)]["ozon_label_error"] is None

    ship_calls = [path for path, _ in transport.endpoint_calls if path.endswith("/ship")]
    assert len(ship_calls) == 1


async def test_assembly_failure_with_a_real_session_user_returns_the_original_error(
    db_session: AsyncSession,
) -> None:
    """WMS-526 F3 (Astra round 2): a SimpleNamespace stand-in for `user`
    hides a real bug — require_fbs_operator_access loads an actual ORM
    `User` into the same request session, and the handler's `session.rollback()`
    (needed so the R12 write below is a clean transaction) expires it exactly
    like every other object in that session. Before the fix, the very next
    `user.tenant_id` tried an implicit sync refresh and crashed with
    MissingGreenlet -> bare 500, and no reason was ever saved. This seeds a
    real, committed `User` in the same session `retry_fbs_packing_box_qr`
    runs against (the live-API switch being off is the exact failure the
    stand hit) and checks both the original 503 and the saved reason survive."""
    order, supply, boxes = await _seed(db_session)
    user = User(
        tenant_id=order.tenant_id,
        email=f"retry-qr-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="unused-test-password",
        role="fulfillment_staff",
    )
    db_session.add(user)
    await db_session.commit()
    # Captured before the call: the handler's own rollback (needed so the
    # R12 write is a clean transaction, not tangled with the failed attempt)
    # expires every attribute on every ORM object this test already holds,
    # `user` included — that is exactly the bug this test guards against.
    tenant_id, supply_id, order_id = order.tenant_id, supply.id, order.id
    box_ids = [box.id for box in boxes]

    with pytest.raises(HTTPException) as error:
        await retry_fbs_packing_box_qr(supply_id, box_ids[0], user, db_session)
    assert error.value.status_code == 503
    assert error.value.detail["code"] == "ozon_live_handoff_blocked"

    expected_error = {
        "code": "ozon_live_handoff_blocked",
        "message": "Обмен с Ozon выключен настройкой.",
    }
    box_rows = await _workspace_box_rows(db_session, tenant_id, supply_id)
    for box_id in box_ids:
        assert box_rows[str(box_id)]["ozon_label_error"] == expected_error
    # No assembly was ever attempted, so there is nothing to protect against
    # a resend — the box's own retry button remains the normal way forward.
    refreshed_order = await db_session.get(FbsOrder, order_id)
    assert refreshed_order is not None
    assert (refreshed_order.meta_details_json or {}).get("ozon_assembly") is None


async def test_wb_box_rows_never_carry_an_ozon_label_error(db_session: AsyncSession) -> None:
    """WMS-526 R12: the field is Ozon-only — a WB box (which always has a
    cargo place / trbx) never gets it, regardless of order state."""
    tenant = Tenant(name="WB label field", slug=f"wb-label-{uuid.uuid4().hex}")
    seller = Seller(tenant=tenant, name="Seller")
    warehouse = Warehouse(tenant=tenant, name="Warehouse", code="WBL")
    product = Product(tenant=tenant, seller=seller, name="Product", sku_code="WBL")
    supply = FbsSupply(
        tenant=tenant,
        seller=seller,
        warehouse=warehouse,
        marketplace="wb",
        name="WB label field",
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
        marketplace="wb",
        wb_order_id=-321,
        mapping_status="mapped",
        reserve_status="reserved",
        created_at_wb=now,
        deadline_at=now + timedelta(days=1),
    )
    session = db_session
    session.add_all([tenant, seller, warehouse, product, supply, order])
    await session.flush()
    physical = WarehouseBox(
        tenant_id=tenant.id, warehouse_id=warehouse.id, internal_barcode=f"WBL-{uuid.uuid4().hex}"
    )
    session.add(physical)
    await session.flush()
    trbx = FbsTrbx(supply_id=supply.id, wb_trbx_id="WBL-TRBX-1", packaging_box_id=physical.id)
    session.add(trbx)
    await session.flush()
    box = FbsPackingBox(
        tenant_id=tenant.id,
        supply_id=supply.id,
        warehouse_box_id=physical.id,
        box_number=1,
        trbx_id=trbx.id,
    )
    session.add(box)
    await session.flush()
    session.add(
        FbsPackingBoxItem(tenant_id=tenant.id, box_id=box.id, fbs_order_id=order.id)
    )
    await session.commit()

    box_rows = await _workspace_box_rows(session, tenant.id, supply.id)
    assert box_rows[str(box.id)]["ozon_label_error"] is None


async def test_ready_label_hides_a_stale_remembered_error(db_session: AsyncSession) -> None:
    """WMS-526 D2: a ready label always wins, even if meta_details_json still
    has a reason from an earlier failed attempt (e.g. clear_order_label_error
    has not run for this exact asset yet) — the operator has something to
    print, so the red line must not show."""
    order, supply, boxes = await _seed(db_session)
    order.meta_details_json = {
        **(order.meta_details_json or {}),
        assembly_svc.LABEL_ERROR_KEY: {"code": "stale", "message": "Устаревшая причина"},
    }
    db_session.add(
        FbsPrintAsset(
            tenant_id=order.tenant_id,
            seller_id=order.seller_id,
            kind=PRINT_ASSET_KIND_ORDER_STICKER,
            status=PRINT_ASSET_STATUS_READY,
            fbs_order_id=order.id,
        )
    )
    await db_session.commit()

    box_rows = await _workspace_box_rows(db_session, order.tenant_id, supply.id)
    for box in boxes:
        assert box_rows[str(box.id)]["ozon_label_error"] is None


async def test_label_error_write_never_clobbers_a_concurrently_saved_assembly_marker(
    db_session: AsyncSession,
) -> None:
    """WMS-526 F4 (Astra round 2): set_order_label_error/clear_order_label_error
    must read the order's meta_details_json fresh (locked + populate_existing),
    not spread a stale in-memory copy back over the column — otherwise they
    silently drop whatever another transaction committed to it meanwhile,
    most importantly ASSEMBLY_KEY (the guard against resending /ship)."""
    order, _supply, _boxes = await _seed(db_session)
    order.meta_details_json = {"other": "keep"}
    await db_session.commit()
    order_id, tenant_id = order.id, order.tenant_id

    # set_order_label_error: session A holds a stale snapshot loaded before
    # session B commits a new assembly marker to the same row.
    async with SessionLocal() as session_a:
        stale = await session_a.get(FbsOrder, order_id)
        assert stale is not None and stale.meta_details_json == {"other": "keep"}

        async with SessionLocal() as session_b:
            fresh = await session_b.get(FbsOrder, order_id)
            assert fresh is not None
            fresh.meta_details_json = {
                "other": "keep",
                assembly_svc.ASSEMBLY_KEY: {"posting_numbers": ["NEW"]},
            }
            await session_b.commit()

        # Session A never re-reads `stale` itself — it only calls the
        # helper, which must fetch the current row on its own.
        await assembly_svc.set_order_label_error(
            session_a, tenant_id, order_id, code="failed", message="failed"
        )
        await session_a.commit()

    async with SessionLocal() as check:
        reread = await check.get(FbsOrder, order_id)
        assert reread is not None
        assert reread.meta_details_json["other"] == "keep"
        assert reread.meta_details_json[assembly_svc.ASSEMBLY_KEY] == {
            "posting_numbers": ["NEW"]
        }
        assert reread.meta_details_json[assembly_svc.LABEL_ERROR_KEY] == {
            "code": "failed",
            "message": "failed",
        }

    # clear_order_label_error: same reproduction, a newer marker from
    # session B must survive session A's clear.
    async with SessionLocal() as session_a2:
        stale2 = await session_a2.get(FbsOrder, order_id)
        assert stale2 is not None

        async with SessionLocal() as session_b2:
            fresh2 = await session_b2.get(FbsOrder, order_id)
            assert fresh2 is not None
            fresh2.meta_details_json = {
                **(fresh2.meta_details_json or {}),
                assembly_svc.ASSEMBLY_KEY: {"posting_numbers": ["NEWER"]},
            }
            await session_b2.commit()

        await assembly_svc.clear_order_label_error(session_a2, tenant_id, order_id)
        await session_a2.commit()

    async with SessionLocal() as check2:
        reread2 = await check2.get(FbsOrder, order_id)
        assert reread2 is not None
        assert assembly_svc.LABEL_ERROR_KEY not in reread2.meta_details_json
        assert reread2.meta_details_json[assembly_svc.ASSEMBLY_KEY] == {
            "posting_numbers": ["NEWER"]
        }
        assert reread2.meta_details_json["other"] == "keep"


async def _second_ozon_supply_same_tenant(
    session: AsyncSession, order_a: FbsOrder
) -> tuple[FbsOrder, FbsSupply, list[FbsPackingBox]]:
    """A second, independent Ozon supply for the same tenant/seller/warehouse
    as order_a's — for proving a box from one supply never leaks into the
    other's order state."""
    supply = FbsSupply(
        tenant_id=order_a.tenant_id,
        seller_id=order_a.seller_id,
        warehouse_id=order_a.warehouse_id,
        marketplace="ozon",
        name="Second supply",
        status="assembling",
        delivery_type="warehouse_sc",
    )
    now = datetime.now(UTC)
    order = FbsOrder(
        tenant_id=order_a.tenant_id,
        seller_id=order_a.seller_id,
        warehouse_id=order_a.warehouse_id,
        product_id=order_a.product_id,
        supply=supply,
        marketplace="ozon",
        external_order_id="POSTING-B",
        wb_order_id=-456,
        mapping_status="mapped",
        reserve_status="reserved",
        created_at_wb=now,
        deadline_at=now + timedelta(days=1),
    )
    session.add_all([supply, order])
    await session.flush()
    session.add(
        FbsOrderProduct(
            order_id=order.id,
            product_id=order_a.product_id,
            ozon_sku=4001,
            quantity=1,
            offer_id="SKU-B",
            name="Product B",
            position_index=0,
        )
    )
    await session.commit()
    return order, supply, await seed_boxes(session, order, supply)


async def test_error_is_never_saved_to_a_different_supplys_order(
    db_session: AsyncSession,
) -> None:
    """WMS-526 F5 (Astra round 2): supply_id and box_id must belong together.
    A box_id from a different Ozon supply of the same tenant must not get
    its order blamed for a request that was actually scoped to another
    supply — the resolved order is None, so no write happens at all."""
    order_a, supply_a, _boxes_a = await _seed(db_session)
    order_b, supply_b, boxes_b = await _second_ozon_supply_same_tenant(db_session, order_a)
    tenant_id = order_a.tenant_id
    supply_a_id, supply_b_id = supply_a.id, supply_b.id
    order_b_id = order_b.id
    box_b_ids = [box.id for box in boxes_b]
    user = SimpleNamespace(tenant_id=tenant_id, id=uuid.uuid4())

    # supply_a's id combined with a box that actually belongs to supply_b.
    with pytest.raises(HTTPException) as error:
        await retry_fbs_packing_box_qr(supply_a_id, box_b_ids[0], user, db_session)
    assert error.value.status_code == 404
    assert error.value.detail["code"] == "box_not_found"

    refreshed_order_b = await db_session.get(FbsOrder, order_b_id)
    assert refreshed_order_b is not None
    assert not (refreshed_order_b.meta_details_json or {})
    box_rows_b = await _workspace_box_rows(db_session, tenant_id, supply_b_id)
    for box_id in box_b_ids:
        assert box_rows_b[str(box_id)]["ozon_label_error"] is None


async def _extra_order_in_same_supply(
    session: AsyncSession, order_a: FbsOrder, supply_id: uuid.UUID
) -> FbsOrderProduct:
    """A second order (B) in order_a's own supply, with one free position
    not yet placed in any box."""
    order_b = FbsOrder(
        tenant_id=order_a.tenant_id,
        seller_id=order_a.seller_id,
        warehouse_id=order_a.warehouse_id,
        product_id=order_a.product_id,
        supply_id=supply_id,
        marketplace="ozon",
        external_order_id="POSTING-B",
        wb_order_id=-654,
        mapping_status="mapped",
        reserve_status="reserved",
        created_at_wb=datetime.now(UTC),
        deadline_at=datetime.now(UTC) + timedelta(days=1),
    )
    session.add(order_b)
    await session.flush()
    position_b = FbsOrderProduct(
        order_id=order_b.id,
        product_id=order_a.product_id,
        ozon_sku=9001,
        quantity=1,
        offer_id="SKU-B",
        name="Product B",
        position_index=0,
    )
    session.add(position_b)
    await session.commit()
    return position_b


async def test_error_follows_the_order_actually_locked_after_box_contents_change(
    db_session: AsyncSession,
) -> None:
    """WMS-526 F5, remainder (Astra round 3): assemble_box_order determines
    the order strictly under its own supply/order lock, and retry-qr no
    longer reads the box's order beforehand at all — there is nothing left
    to go stale between a pre-lock read and the lock, because that read is
    gone. Reproduces the review's exact interleaving: another operator
    clears the box that held order A's first position and puts order B's
    (same supply) position there instead, using the same clear_box/
    assign_orders the box screen itself uses, each in its own committed
    session, before the handler even starts. The failure (live API off)
    must be attributed to B — the order the box actually held when
    assemble_box_order ran — never to A."""
    order_a, supply, boxes_a = await _seed(db_session)
    position_b = await _extra_order_in_same_supply(db_session, order_a, supply.id)
    tenant_id, supply_id = order_a.tenant_id, supply.id
    changed_box_id = boxes_a[0].id

    async with SessionLocal() as clearing_session:
        await boxes_svc.clear_box(clearing_session, tenant_id, supply_id, changed_box_id)
        await clearing_session.commit()
    async with SessionLocal() as assigning_session:
        await boxes_svc.assign_orders(
            assigning_session,
            tenant_id,
            supply_id,
            changed_box_id,
            [],
            actor_user_id=None,
            order_product_ids=[position_b.id],
        )
        await assigning_session.commit()

    user = SimpleNamespace(tenant_id=tenant_id, id=uuid.uuid4())
    with pytest.raises(HTTPException) as error:
        await retry_fbs_packing_box_qr(supply_id, changed_box_id, user, db_session)
    assert error.value.status_code == 503
    assert error.value.detail["code"] == "ozon_live_handoff_blocked"

    expected_error = {
        "code": "ozon_live_handoff_blocked",
        "message": "Обмен с Ozon выключен настройкой.",
    }
    box_rows = await _workspace_box_rows(db_session, tenant_id, supply_id)
    assert box_rows[str(changed_box_id)]["ozon_label_error"] == expected_error
    refreshed_a = await db_session.get(FbsOrder, order_a.id)
    assert refreshed_a is not None
    assert (refreshed_a.meta_details_json or {}).get(assembly_svc.LABEL_ERROR_KEY) is None
    refreshed_b = await db_session.get(FbsOrder, position_b.order_id)
    assert refreshed_b is not None
    assert (refreshed_b.meta_details_json or {}).get(assembly_svc.LABEL_ERROR_KEY) == (
        expected_error
    )


async def test_error_on_a_box_assigned_after_being_empty_follows_the_new_order(
    db_session: AsyncSession,
) -> None:
    """WMS-526 F5, remainder: same fix, starting from a box that was empty
    (never held any order) rather than one cleared of a previous order."""
    order_a, supply, _boxes_a = await _seed(db_session)
    position_b = await _extra_order_in_same_supply(db_session, order_a, supply.id)
    tenant_id, supply_id = order_a.tenant_id, supply.id

    async with SessionLocal() as create_session:
        new_boxes = await boxes_svc.create_boxes(
            create_session, tenant_id, supply_id, 1, f"extra-{uuid.uuid4()}", actor_user_id=None
        )
        empty_box_id = new_boxes[-1].id
        await create_session.commit()
    async with SessionLocal() as assigning_session:
        await boxes_svc.assign_orders(
            assigning_session,
            tenant_id,
            supply_id,
            empty_box_id,
            [],
            actor_user_id=None,
            order_product_ids=[position_b.id],
        )
        await assigning_session.commit()

    user = SimpleNamespace(tenant_id=tenant_id, id=uuid.uuid4())
    with pytest.raises(HTTPException) as error:
        await retry_fbs_packing_box_qr(supply_id, empty_box_id, user, db_session)
    assert error.value.status_code == 503

    box_rows = await _workspace_box_rows(db_session, tenant_id, supply_id)
    assert box_rows[str(empty_box_id)]["ozon_label_error"] == {
        "code": "ozon_live_handoff_blocked",
        "message": "Обмен с Ozon выключен настройкой.",
    }
    refreshed_a = await db_session.get(FbsOrder, order_a.id)
    assert refreshed_a is not None
    assert (refreshed_a.meta_details_json or {}).get(assembly_svc.LABEL_ERROR_KEY) is None
