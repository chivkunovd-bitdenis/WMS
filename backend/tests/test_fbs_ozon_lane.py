"""S-03 provider boundaries for the existing FBS operator flow."""

from __future__ import annotations

import base64
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.fbs_orders import _run_blocked_ozon_fake
from app.db.session import SessionLocal, engine
from app.models import Base
from app.models.fbs_order import (
    FBS_ORDER_STATUS_PACKED,
    MAPPING_STATUS_MAPPED,
    RESERVE_STATUS_RESERVED,
    FbsOrder,
)
from app.models.fbs_print_asset import PRINT_ASSET_STATUS_READY
from app.models.fbs_supply import (
    FBS_DELIVERY_TYPE_WAREHOUSE_SC,
    FBS_SUPPLY_STATUS_IN_DELIVERY,
    FBS_SUPPLY_STATUS_PACKED,
    FbsSupply,
)
from app.models.marketplace_account import MarketplaceAccount
from app.models.product import Product
from app.models.seller import Seller
from app.models.tenant import Tenant
from app.models.warehouse import Warehouse
from app.services import fbs_print_asset_service as print_asset_svc
from app.services import fbs_shipment_service as shipment_svc
from app.services import fbs_supply_service as supply_svc
from app.services.fbs_print_asset_service import fetch_order_label_rows_for_marketplace
from app.services.fbs_supply_validator_service import (
    SupplyPreflightResult,
    SupplyPreflightSummary,
    validate_supply_composition,
)
from app.services.integration_fernet import encrypt_secret
from app.services.marketplace_provider import (
    FakeMarketplaceTransport,
    MarketplaceProviderError,
    OzonMarketplaceProvider,
    provider_error_message,
)


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    async with SessionLocal() as session:
        yield session
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)


@pytest.mark.asyncio
async def test_supply_preflight_rejects_mixed_marketplaces(db_session: AsyncSession) -> None:
    """TC-S03-OZON-001: a physical FBS supply belongs to exactly one marketplace."""
    tenant = Tenant(name="S-03 marketplace test", slug=f"s03-{uuid.uuid4().hex[:12]}")
    seller = Seller(tenant=tenant, name="Seller")
    warehouse = Warehouse(tenant=tenant, name="FBS", code=f"fbs-{uuid.uuid4().hex[:8]}")
    product = Product(
        tenant=tenant,
        seller=seller,
        name="Product",
        sku_code=f"sku-{uuid.uuid4().hex[:8]}",
    )
    db_session.add_all([tenant, seller, warehouse, product])
    await db_session.flush()

    now = datetime.now(UTC)
    wb_order = FbsOrder(
        tenant_id=tenant.id,
        seller_id=seller.id,
        warehouse_id=warehouse.id,
        product_id=product.id,
        marketplace="wb",
        external_order_id="wb-1",
        wb_order_id=1,
        wb_warehouse_id=11,
        mapping_status=MAPPING_STATUS_MAPPED,
        reserve_status=RESERVE_STATUS_RESERVED,
        created_at_wb=now,
        deadline_at=now + timedelta(days=1),
    )
    ozon_order = FbsOrder(
        tenant_id=tenant.id,
        seller_id=seller.id,
        warehouse_id=warehouse.id,
        product_id=product.id,
        marketplace="ozon",
        external_order_id="ozon-1",
        wb_order_id=2,
        wb_warehouse_id=11,
        mapping_status=MAPPING_STATUS_MAPPED,
        reserve_status=RESERVE_STATUS_RESERVED,
        created_at_wb=now,
        deadline_at=now + timedelta(days=1),
    )
    db_session.add_all([wb_order, ozon_order])
    await db_session.commit()

    result = await validate_supply_composition(
        db_session,
        tenant.id,
        [wb_order.id, ozon_order.id],
        planned_delivery_type="warehouse_sc",
    )

    assert {issue.code for issue in result.issues} >= {"different_marketplace"}


@pytest.mark.asyncio
async def test_order_label_dispatch_uses_only_selected_marketplace_adapter() -> None:
    wb_fetch = AsyncMock(return_value=[{"orderId": 1}])
    ozon_fetch = AsyncMock(return_value=[{"posting_number": "ozon-1"}])

    rows = await fetch_order_label_rows_for_marketplace(
        "ozon",
        external_order_ids=["ozon-1"],
        wb_fetch=wb_fetch,
        ozon_fetch=ozon_fetch,
    )

    assert rows == [{"posting_number": "ozon-1"}]
    wb_fetch.assert_not_awaited()
    ozon_fetch.assert_awaited_once_with(["ozon-1"])


@pytest.mark.asyncio
async def test_ozon_order_label_fake_creates_ready_asset_without_wb_fetch(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant = Tenant(name="Ozon print test", slug=f"ozon-print-{uuid.uuid4().hex[:8]}")
    seller = Seller(tenant=tenant, name="Seller")
    warehouse = Warehouse(
        tenant=tenant,
        name="FBS",
        code=f"ozon-print-{uuid.uuid4().hex[:8]}",
    )
    supply = FbsSupply(
        tenant=tenant,
        seller=seller,
        warehouse=warehouse,
        marketplace="ozon",
        external_supply_id="ozon-supply-1",
        wb_supply_id="ozon-supply-1",
        name="Ozon FBS",
        delivery_type=FBS_DELIVERY_TYPE_WAREHOUSE_SC,
    )
    now = datetime.now(UTC)
    order = FbsOrder(
        tenant=tenant,
        seller=seller,
        warehouse=warehouse,
        supply=supply,
        marketplace="ozon",
        external_order_id="ozon-posting-1",
        wb_order_id=1001,
        wb_warehouse_id=11,
        mapping_status=MAPPING_STATUS_MAPPED,
        reserve_status=RESERVE_STATUS_RESERVED,
        created_at_wb=now,
        deadline_at=now + timedelta(days=1),
    )
    db_session.add_all([tenant, seller, warehouse, supply, order])
    await db_session.commit()

    wb_fetch = AsyncMock(side_effect=AssertionError("WB fetch must not run for Ozon"))
    monkeypatch.setattr(print_asset_svc, "fetch_marketplace_order_stickers", wb_fetch)

    batch = await print_asset_svc.request_supply_print_batch(
        db_session,
        tenant.id,
        supply.id,
        kind="order_sticker",
        order_ids=[order.id],
        retry_missing=False,
        http_client=AsyncMock(),
    )

    assert batch.ready == 1
    assert batch.failed == 0
    assert batch.assets[0].status == PRINT_ASSET_STATUS_READY
    assert batch.assets[0].storage_path
    wb_fetch.assert_not_awaited()


@pytest.mark.asyncio
async def test_order_label_fake_preserves_human_ozon_403_code7() -> None:
    error = MarketplaceProviderError("ozon", 403, {"code": 7})
    ozon_fetch = AsyncMock(side_effect=error)

    with pytest.raises(MarketplaceProviderError) as caught:
        await fetch_order_label_rows_for_marketplace(
            "ozon",
            external_order_ids=["ozon-1"],
            wb_fetch=AsyncMock(),
            ozon_fetch=ozon_fetch,
        )

    assert provider_error_message(caught.value) == (
        "Кабинет Ozon заблокирован. Обратитесь в поддержку Ozon."
    )


@pytest.mark.asyncio
async def test_manual_sync_fake_returns_human_ozon_403_code7() -> None:
    with pytest.raises(HTTPException) as caught:
        await _run_blocked_ozon_fake()

    assert caught.value.status_code == 403
    assert caught.value.detail["code"] == "ozon_account_blocked"
    assert caught.value.detail["message"] == (
        "Кабинет Ozon заблокирован. Обратитесь в поддержку Ozon."
    )


async def _seed_ozon_supply_case(
    db_session: AsyncSession,
    *,
    packed: bool,
) -> tuple[Tenant, Seller, Warehouse, Product, FbsOrder, FbsSupply | None]:
    tenant = Tenant(name="Ozon dispatch test", slug=f"ozon-dispatch-{uuid.uuid4().hex[:8]}")
    seller = Seller(tenant=tenant, name="Seller")
    warehouse = Warehouse(
        tenant=tenant,
        name="FBS",
        code=f"ozon-dispatch-{uuid.uuid4().hex[:8]}",
    )
    product = Product(
        tenant=tenant,
        seller=seller,
        name="Product",
        sku_code=f"sku-{uuid.uuid4().hex[:8]}",
    )
    supply = (
        FbsSupply(
            tenant=tenant,
            seller=seller,
            warehouse=warehouse,
            marketplace="ozon",
            external_supply_id="ozon-supply-existing",
            wb_supply_id="ozon-supply-existing",
            name="Ozon FBS",
            status=FBS_SUPPLY_STATUS_PACKED,
            delivery_type=FBS_DELIVERY_TYPE_WAREHOUSE_SC,
        )
        if packed
        else None
    )
    now = datetime.now(UTC)
    order = FbsOrder(
        tenant=tenant,
        seller=seller,
        warehouse=warehouse,
        product=product,
        supply=supply,
        marketplace="ozon",
        external_order_id="ozon-posting-dispatch",
        wb_order_id=2001,
        wb_warehouse_id=11,
        status=FBS_ORDER_STATUS_PACKED if packed else "new",
        mapping_status=MAPPING_STATUS_MAPPED,
        reserve_status=RESERVE_STATUS_RESERVED,
        created_at_wb=now,
        deadline_at=now + timedelta(days=1),
    )
    db_session.add_all([tenant, seller, warehouse, product, order])
    if supply is not None:
        db_session.add(supply)
    await db_session.flush()
    account = MarketplaceAccount(
        tenant_id=tenant.id,
        seller_id=seller.id,
        marketplace="ozon",
        account_slot="primary",
        external_account_id="client-id",
        secret_encrypted=encrypt_secret("api-key"),
        is_active=True,
        validation_status="valid",
    )
    db_session.add(account)
    await db_session.commit()
    return tenant, seller, warehouse, product, order, supply


@pytest.mark.asyncio
async def test_ozon_supply_creation_never_calls_wb(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant, seller, warehouse, _, order, _ = await _seed_ozon_supply_case(
        db_session,
        packed=False,
    )
    summary = SupplyPreflightSummary(
        seller_id=seller.id,
        seller_name=seller.name,
        wb_warehouse_id=11,
        wb_warehouse_name="Ozon warehouse",
        wms_warehouse_id=warehouse.id,
        wms_warehouse_name=warehouse.name,
        buyer_type="individual",
        cargo_type="unknown",
        orders_count=1,
        required_marking_count=0,
        pvz_allowed_count=1,
        pvz_blocked_count=0,
        nearest_deadline_at=order.deadline_at,
    )
    preview = SupplyPreflightResult(True, summary, (), (order,))
    monkeypatch.setattr(supply_svc, "load_orders_for_validation", AsyncMock(return_value=[order]))
    monkeypatch.setattr(supply_svc, "validate_supply_composition", AsyncMock(return_value=preview))
    wb_create = AsyncMock(side_effect=AssertionError("WB create must not run for Ozon"))
    wb_add = AsyncMock(side_effect=AssertionError("WB add must not run for Ozon"))
    monkeypatch.setattr(supply_svc, "create_marketplace_supply", wb_create)
    monkeypatch.setattr(supply_svc, "_execute_wb_batch_add", wb_add)
    transport = FakeMarketplaceTransport(created_supply_id="ozon-supply-created")

    workspace = await supply_svc.create_supply_from_orders(
        db_session,
        tenant.id,
        name="Ozon supply",
        order_ids=[order.id],
        planned_delivery_type=FBS_DELIVERY_TYPE_WAREHOUSE_SC,
        planned_destination=None,
        idempotency_key=f"ozon-create-{uuid.uuid4()}",
        http_client=AsyncMock(),
        ozon_provider=OzonMarketplaceProvider(transport=transport),
    )

    assert workspace["supply"]["marketplace"] == "ozon"
    assert transport.calls == [("create_supply", "client-id")]
    wb_create.assert_not_awaited()
    wb_add.assert_not_awaited()


@pytest.mark.asyncio
async def test_ozon_supply_delivery_and_qr_never_call_wb(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant, _, _, _, _, supply = await _seed_ozon_supply_case(
        db_session,
        packed=True,
    )
    assert supply is not None
    wb_deliver = AsyncMock(side_effect=AssertionError("WB deliver must not run for Ozon"))
    wb_qr = AsyncMock(side_effect=AssertionError("WB QR must not run for Ozon"))
    wb_sync = AsyncMock(side_effect=AssertionError("WB sync must not run for Ozon"))
    monkeypatch.setattr(shipment_svc, "deliver_marketplace_supply", wb_deliver)
    monkeypatch.setattr(shipment_svc, "fetch_marketplace_supply_barcode", wb_qr)
    monkeypatch.setattr(shipment_svc, "_sync_supply_orders_from_wb", wb_sync)
    transport = FakeMarketplaceTransport(
        supply_qr=base64.b64decode(print_asset_svc._FAKE_OZON_LABEL_PNG_BASE64)
    )

    delivered = await shipment_svc.deliver_supply(
        db_session,
        tenant.id,
        supply.id,
        AsyncMock(),
        idempotency_key=f"ozon-deliver-{uuid.uuid4()}",
        ozon_provider=OzonMarketplaceProvider(transport=transport),
    )

    assert delivered.status == FBS_SUPPLY_STATUS_IN_DELIVERY
    assert [call[0] for call in transport.calls] == ["deliver_supply", "fetch_supply_qr"]
    wb_deliver.assert_not_awaited()
    wb_qr.assert_not_awaited()
    wb_sync.assert_not_awaited()
