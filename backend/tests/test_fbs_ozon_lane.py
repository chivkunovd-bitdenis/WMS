"""S-03 provider boundaries for the existing FBS operator flow."""

from __future__ import annotations

import base64
import json
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.fbs_orders import _run_blocked_ozon_fake
from app.core.settings import settings
from app.db.session import SessionLocal
from app.models.fbs_binding_stock_pool import FbsBindingStockPool
from app.models.fbs_order import (
    CHECK_STATUS_ERROR,
    CHECK_STATUS_OK,
    FBS_ORDER_STATUS_CANCELLED,
    FBS_ORDER_STATUS_PACKED,
    MAPPING_STATUS_MAPPED,
    META_STATUS_ACCEPTED,
    META_STATUS_REJECTED,
    RESERVE_STATUS_RESERVED,
    STICKER_STATUS_ERROR,
    FbsOrder,
    FbsOrderMarking,
    FbsOrderProduct,
    FbsOrderProductReservation,
)
from app.models.fbs_packaging_fulfillment import FbsPackagingFulfillment
from app.models.fbs_supply import (
    FBS_DELIVERY_TYPE_PVZ,
    FBS_DELIVERY_TYPE_WAREHOUSE_SC,
    FBS_SUPPLY_STATUS_ASSEMBLING,
    FBS_SUPPLY_STATUS_IN_DELIVERY,
    FBS_SUPPLY_STATUS_PACKED,
    FbsSupply,
)
from app.models.fbs_warehouse_binding import FbsWarehouseBinding
from app.models.fbs_wb_operation import FbsWbOperation
from app.models.inventory_balance import InventoryBalance
from app.models.marketplace_account import MarketplaceAccount
from app.models.marking_code import MarkingCodeEvent
from app.models.packaging_task import PackagingTask, PackagingTaskLine
from app.models.product import Product
from app.models.product_marketplace_link import ProductMarketplaceLink
from app.models.seller import Seller
from app.models.storage_location import StorageLocation
from app.models.tenant import Tenant
from app.models.warehouse import Warehouse
from app.services import fbs_cancellation_service as cancellation_svc
from app.services import fbs_kiz_service as kiz_svc
from app.services import fbs_marking_service as marking_svc
from app.services import fbs_packing_box_service as box_svc
from app.services import fbs_print_asset_service as print_asset_svc
from app.services import fbs_shipment_service as shipment_svc
from app.services import fbs_supply_service as supply_svc
from app.services import fbs_tracking_service as tracking_svc
from app.services import fbs_worklist_service as worklist_svc
from app.services import fbs_workspace_service as workspace_svc
from app.services import inventory_service
from app.services import ozon_fbs_sync_service as ozon_sync_svc
from app.services import ozon_kiz_service as ozon_kiz_svc
from app.services.fbs_autopoll_service import (
    SellerPollTarget,
    poll_marketplace_orders_for_target,
    sync_marketplace_order_statuses_for_target,
    sync_marketplace_stocks_for_target,
    sync_marking_statuses_for_assembling_supplies,
)
from app.services.fbs_print_asset_service import fetch_order_label_rows_for_marketplace
from app.services.fbs_supply_validator_service import (
    SupplyPreflightResult,
    SupplyPreflightSummary,
    validate_supply_composition,
)
from app.services.fbs_warehouse_binding_service import (
    FbsWarehouseBindingError,
    set_binding_stock_pool_quantity,
)
from app.services.integration_fernet import encrypt_secret
from app.services.marketplace_provider import (
    FakeMarketplaceTransport,
    MarketplaceProviderError,
    OzonMarketplaceProvider,
    provider_error_message,
)
from app.services.ozon_box_assembly_service import assemble_box_order
from app.services.ozon_fbs_errors import OzonFbsProcessError
from app.services.ozon_fbs_process_service import submit_marking
from tests.inventory_actor_helpers import resolve_test_actor_user_id
from tests.test_ozon_box_assembly import seed_boxes


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


async def _ozon_supply_with_one_order(
    db_session: AsyncSession,
) -> tuple[Tenant, FbsSupply, FbsOrder]:
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
    await db_session.flush()
    db_session.add(
        MarketplaceAccount(
            tenant_id=tenant.id,
            seller_id=seller.id,
            marketplace="ozon",
            account_slot="primary",
            external_account_id="ozon-client",
            secret_encrypted=encrypt_secret("ozon-key"),
            is_active=True,
            validation_status="valid",
        )
    )
    await db_session.commit()
    return tenant, supply, order


@pytest.mark.asyncio
async def test_ozon_pdf_label_is_stored_and_served_as_a_pdf(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Этикетка Ozon доезжает до оператора документом, а не заглушкой.

    Раньше здесь сохранялся однопиксельный PNG и заказу ставилось «стикер
    готов»: оператор получал пустой лист. Потом заглушку заменили честным
    отказом, потому что хранилище принимало только PNG. Теперь хранилище знает
    формат, и путь работает целиком: PDF от Ozon кладётся на диск как PDF и
    отдаётся ручкой печати с тем же типом содержимого.
    """
    monkeypatch.setattr(settings, "ozon_live_api_enabled", True)
    tenant, supply, order = await _ozon_supply_with_one_order(db_session)
    wb_fetch = AsyncMock(side_effect=AssertionError("WB fetch must not run for Ozon"))
    monkeypatch.setattr(print_asset_svc, "fetch_marketplace_order_stickers", wb_fetch)
    transport = FakeMarketplaceTransport(
        order_labels=[
            {
                "posting_number": "ozon-posting-1",
                "file": base64.b64encode(b"%PDF-1.7 ozon label").decode("ascii"),
                "content_type": "application/pdf",
            }
        ]
    )
    monkeypatch.setattr(
        print_asset_svc,
        "build_ozon_provider",
        lambda **kwargs: OzonMarketplaceProvider(transport=transport),
    )

    batch = await print_asset_svc.request_supply_print_batch(
        db_session,
        tenant.id,
        supply.id,
        kind="order_sticker",
        order_ids=[order.id],
        retry_missing=False,
        http_client=AsyncMock(),
    )

    assert batch.failed == 0
    assert batch.ready == 1
    asset = batch.assets[0]
    assert asset.content_type == "application/pdf"
    assert asset.storage_path is not None and asset.storage_path.endswith(".pdf")
    # Рулон 58x40 — свойство вайлдберрисовского PNG. У PDF Ozon страница своя,
    # и подписывать её нашим размером нельзя: по этим полям верстается лист.
    assert asset.width_mm is None and asset.height_mm is None

    payload, content_type, _asset = await print_asset_svc.get_asset_binary_content(
        db_session,
        tenant.id,
        asset.id,
        user_id=uuid.uuid4(),
    )
    assert payload == b"%PDF-1.7 ozon label"
    assert content_type == "application/pdf"
    wb_fetch.assert_not_awaited()


@pytest.mark.asyncio
async def test_ozon_label_before_handoff_explains_itself_instead_of_failing_blankly(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Отказ Ozon по одному отправлению — это причина, а не тишина.

    Спецификация `/v2/posting/fbs/package-label`: этикетки выдаются для
    отправлений в статусе «Ожидает отгрузки» — `awaiting_deliver`. До передачи
    поставки их нет, и оператор должен прочитать именно это, а не «этикетка не
    найдена в ответе Ozon».
    """
    monkeypatch.setattr(settings, "ozon_live_api_enabled", True)
    tenant, supply, order = await _ozon_supply_with_one_order(db_session)
    monkeypatch.setattr(
        print_asset_svc,
        "fetch_marketplace_order_stickers",
        AsyncMock(side_effect=AssertionError("WB fetch must not run for Ozon")),
    )
    transport = FakeMarketplaceTransport(
        order_labels=[
            {
                "posting_number": "ozon-posting-1",
                "error_code": "ozon_label_400",
                "error_message": "posting is not ready",
            }
        ]
    )
    monkeypatch.setattr(
        print_asset_svc,
        "build_ozon_provider",
        lambda **kwargs: OzonMarketplaceProvider(transport=transport),
    )

    batch = await print_asset_svc.request_supply_print_batch(
        db_session,
        tenant.id,
        supply.id,
        kind="order_sticker",
        order_ids=[order.id],
        retry_missing=False,
        http_client=AsyncMock(),
    )

    assert batch.ready == 0
    assert batch.failed == 1
    assert batch.order_errors[0].code == "ozon_label_400"
    assert "после передачи" in batch.order_errors[0].message
    await db_session.refresh(order)
    assert order.sticker_status == STICKER_STATUS_ERROR
    assert order.sticker_file is None


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


@pytest.mark.asyncio
async def test_ozon_autopoll_positive_fake_upserts_shared_order_and_status(
    db_session: AsyncSession,
) -> None:
    tenant = Tenant(name="Ozon poll test", slug=f"ozon-poll-{uuid.uuid4().hex[:8]}")
    seller = Seller(tenant=tenant, name="Seller")
    warehouse = Warehouse(
        tenant=tenant,
        name="FBS",
        code=f"ozon-poll-{uuid.uuid4().hex[:8]}",
    )
    product = Product(
        tenant=tenant,
        seller=seller,
        name="Product",
        sku_code=f"sku-{uuid.uuid4().hex[:8]}",
        # WMS-352: опрос забирает только те заказы, по чьим товарам и складам
        # остаток выставлен нами.
        fbs_stock_sync_enabled=True,
    )
    db_session.add_all([tenant, seller, warehouse, product])
    await db_session.flush()
    db_session.add_all(
        [
            MarketplaceAccount(
                tenant_id=tenant.id,
                seller_id=seller.id,
                marketplace="ozon",
                account_slot="primary",
                external_account_id="client-id",
                secret_encrypted=encrypt_secret("api-key"),
                is_active=True,
                validation_status="valid",
            ),
            ProductMarketplaceLink(
                tenant_id=tenant.id,
                seller_id=seller.id,
                product_id=product.id,
                marketplace="ozon",
                external_sku="ozon-sku-1",
            ),
        ]
    )
    from app.models.fbs_warehouse_binding import FbsWarehouseBinding

    db_session.add(
        FbsWarehouseBinding(
            tenant_id=tenant.id,
            seller_id=seller.id,
            marketplace="ozon",
            external_warehouse_id="ozon-wh-1",
            wb_warehouse_id=-101,
            wms_warehouse_id=warehouse.id,
        )
    )
    await db_session.commit()

    transport = FakeMarketplaceTransport(
        orders=[
            {
                "posting_number": "ozon-posting-1",
                "status": "awaiting_packaging",
                "sku": "ozon-sku-1",
                "warehouse_id": "ozon-wh-1",
                "created_at": datetime.now(UTC).isoformat(),
            }
        ],
        statuses=[{"posting_number": "ozon-posting-1", "status": "delivering"}],
    )
    provider = OzonMarketplaceProvider(transport=transport)
    target = SellerPollTarget(tenant.id, seller.id, "ozon")

    result = await poll_marketplace_orders_for_target(
        db_session,
        target,
        AsyncMock(),
        ozon_provider=provider,
    )
    statuses_updated = await sync_marketplace_order_statuses_for_target(
        db_session,
        target,
        AsyncMock(),
        ozon_provider=provider,
    )

    order = (
        await db_session.execute(
            select(FbsOrder).where(FbsOrder.external_order_id == "ozon-posting-1")
        )
    ).scalar_one()
    assert result["orders_created"] == 1
    assert statuses_updated == 1
    assert order.marketplace == "ozon"
    assert order.product_id == product.id
    assert order.warehouse_id == warehouse.id
    assert order.status == "in_delivery"
    assert [call[0] for call in transport.calls] == ["fetch_orders", "fetch_statuses"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "units_mode, publish, expected", [(True, True, 2), (True, False, 0), (False, True, 10)]
)
async def test_ozon_stock_dispatch_uses_binding_pool_with_fake_transport(
    db_session: AsyncSession,
    units_mode: bool,
    publish: bool,
    expected: int,
) -> None:
    """TC-S04-OZON-030: the shared action dispatches Ozon stock only to a fake provider."""
    tenant = Tenant(name="Ozon stock dispatch", slug=f"ozon-stock-{uuid.uuid4().hex[:8]}")
    seller = Seller(tenant=tenant, name="Seller")
    warehouse = Warehouse(tenant=tenant, name="FBS", code=f"fbs-{uuid.uuid4().hex[:8]}")
    product = Product(
        tenant=tenant,
        seller=seller,
        name="Product",
        sku_code=f"sku-{uuid.uuid4().hex[:8]}",
        fbs_stock_limit=3,
    )
    db_session.add_all([tenant, seller, warehouse, product])
    await db_session.flush()
    account = MarketplaceAccount(
        tenant_id=tenant.id,
        seller_id=seller.id,
        marketplace="ozon",
        account_slot="primary",
        external_account_id="ozon-client",
        secret_encrypted=encrypt_secret("ozon-key"),
        is_active=True,
        validation_status="valid",
    )
    binding = FbsWarehouseBinding(
        tenant_id=tenant.id,
        seller_id=seller.id,
        marketplace="ozon",
        external_warehouse_id="900001",
        wb_warehouse_id=-900001,
        wms_warehouse_id=warehouse.id,
        is_active=True,
        stock_sync_enabled=True,
    )
    link = ProductMarketplaceLink(
        tenant_id=tenant.id,
        seller_id=seller.id,
        product_id=product.id,
        marketplace="ozon",
        external_offer_id="offer-1",
        # У Ozon `product_id` и `sku` — разные числа: живой ответ
        # /v4/product/info/stocks по одной карточке отдаёт
        # {"product_id": 6204279711, "sku": 5680762790}.
        external_product_id="6001",
        external_sku="3001",
        is_active=True,
    )
    db_session.add_all([account, binding, link])
    await db_session.flush()
    pool = FbsBindingStockPool(
        tenant_id=tenant.id,
        binding_id=binding.id,
        product_id=product.id,
        quantity=2,
    )
    if units_mode:
        db_session.add(pool)
    location = StorageLocation(
        tenant_id=tenant.id, warehouse_id=warehouse.id, code="stock", barcode="stock"
    )
    db_session.add(location)
    await db_session.flush()
    db_session.add(
        InventoryBalance(
            tenant_id=tenant.id,
            product_id=product.id,
            storage_location_id=location.id,
            quantity=20,
            quantity_unpacked=20,
        )
    )
    product.fbs_units_mode = units_mode
    product.fbs_stock_sync_enabled = publish
    product.fbs_percent = 50
    product.fbs_same_everywhere = True
    await db_session.commit()
    transport = FakeMarketplaceTransport()

    result = await sync_marketplace_stocks_for_target(
        db_session,
        SellerPollTarget(tenant.id, seller.id, "ozon"),
        AsyncMock(),
        ozon_provider=OzonMarketplaceProvider(transport=transport),
    )

    assert result.bindings_processed == 1
    assert result.products_targeted == 1
    assert result.products_confirmed == 1
    assert transport.calls == [("publish_stocks", "ozon-client")]
    # В поле `product_id` уходит именно product_id Ozon, а не SKU: раньше туда
    # клали SKU и остаток подписывался чужим идентификатором.
    assert transport.published_stocks == [
        {
            "warehouse_id": 900001,
            "offer_id": "offer-1",
            "product_id": 6001,
            "stock": expected,
        }
    ]


@pytest.mark.asyncio
async def test_ozon_partial_stock_confirmation_counts_only_what_ozon_confirmed(
    db_session: AsyncSession,
) -> None:
    """Ozon подтвердил одну строку из двух — второй остаток не «опубликован».

    Раньше сервис прибавлял к подтверждённым весь отправленный пакет, и
    пропущенный ноль выглядел бы опубликованным, хотя в кабинете остался
    прежний положительный остаток.
    """
    tenant = Tenant(name="Ozon partial stock", slug=f"ozon-partial-{uuid.uuid4().hex[:8]}")
    seller = Seller(tenant=tenant, name="Seller")
    warehouse = Warehouse(tenant=tenant, name="FBS", code=f"fbs-{uuid.uuid4().hex[:8]}")
    products = [
        Product(
            tenant=tenant,
            seller=seller,
            name=f"Product {index}",
            sku_code=f"sku-{uuid.uuid4().hex[:8]}",
        )
        for index in range(2)
    ]
    db_session.add_all([tenant, seller, warehouse, *products])
    await db_session.flush()
    binding = FbsWarehouseBinding(
        tenant_id=tenant.id,
        seller_id=seller.id,
        marketplace="ozon",
        external_warehouse_id="900002",
        wb_warehouse_id=-900002,
        wms_warehouse_id=warehouse.id,
        is_active=True,
        stock_sync_enabled=True,
    )
    db_session.add_all(
        [
            MarketplaceAccount(
                tenant_id=tenant.id,
                seller_id=seller.id,
                marketplace="ozon",
                account_slot="primary",
                external_account_id="ozon-client",
                secret_encrypted=encrypt_secret("ozon-key"),
                is_active=True,
                validation_status="valid",
            ),
            binding,
            *[
                ProductMarketplaceLink(
                    tenant_id=tenant.id,
                    seller_id=seller.id,
                    product_id=product.id,
                    marketplace="ozon",
                    external_offer_id=f"offer-{index}",
                    external_product_id=str(7000 + index),
                    is_active=True,
                )
                for index, product in enumerate(products)
            ],
        ]
    )
    await db_session.flush()
    db_session.add_all(
        [
            FbsBindingStockPool(
                tenant_id=tenant.id,
                binding_id=binding.id,
                product_id=product.id,
                quantity=0,
            )
            for product in products
        ]
    )
    await db_session.commit()

    transport = FakeMarketplaceTransport(
        errors={
            "publish_stocks": MarketplaceProviderError(
                "ozon",
                None,
                {"sent": 2, "confirmed": 1, "failed": [{"codes": ["OZON_ROW_MISSING"]}]},
                code="ozon_stock_rejected",
            )
        }
    )

    result = await ozon_sync_svc.sync_ozon_stocks(
        db_session,
        tenant.id,
        seller.id,
        OzonMarketplaceProvider(transport=transport),
    )

    assert result.products_targeted == 2
    assert result.products_confirmed == 1
    assert result.errors == 1
    assert result.binding_errors == 1
    await db_session.refresh(binding)
    assert binding.last_sync_status == "error"
    assert binding.last_error_code == "ozon_stock_rejected"


@pytest.mark.asyncio
async def test_wb_and_ozon_cannot_allocate_the_same_last_physical_unit(
    db_session: AsyncSession,
) -> None:
    """TC-S04-OZON-031: one physical unit can belong to only one provider binding."""
    tenant = Tenant(name="Shared FBS stock", slug=f"shared-stock-{uuid.uuid4().hex[:8]}")
    seller = Seller(tenant=tenant, name="Seller")
    warehouse = Warehouse(tenant=tenant, name="FBS", code=f"fbs-{uuid.uuid4().hex[:8]}")
    product = Product(
        tenant=tenant,
        seller=seller,
        name="Last unit",
        sku_code=f"last-{uuid.uuid4().hex[:8]}",
        fbs_stock_limit=1,
    )
    db_session.add_all([tenant, seller, warehouse, product])
    await db_session.flush()
    wb_binding = FbsWarehouseBinding(
        tenant_id=tenant.id,
        seller_id=seller.id,
        marketplace="wb",
        external_warehouse_id="101",
        wb_warehouse_id=101,
        wms_warehouse_id=warehouse.id,
    )
    ozon_binding = FbsWarehouseBinding(
        tenant_id=tenant.id,
        seller_id=seller.id,
        marketplace="ozon",
        external_warehouse_id="202",
        wb_warehouse_id=-202,
        wms_warehouse_id=warehouse.id,
    )
    db_session.add_all([wb_binding, ozon_binding])
    await db_session.commit()

    await set_binding_stock_pool_quantity(
        db_session,
        tenant.id,
        seller.id,
        wb_binding.id,
        product.id,
        1,
    )
    with pytest.raises(FbsWarehouseBindingError, match="pool_quota_exceeded"):
        await set_binding_stock_pool_quantity(
            db_session,
            tenant.id,
            seller.id,
            ozon_binding.id,
            product.id,
            1,
        )


async def _sync_ozon_posting_with_products(
    db_session: AsyncSession,
    *,
    positions: list[dict[str, object]],
) -> tuple[FbsOrder, list[Product]]:
    tenant = Tenant(name="Ozon positions", slug=f"ozon-positions-{uuid.uuid4().hex[:8]}")
    seller = Seller(tenant=tenant, name="Seller")
    warehouse = Warehouse(tenant=tenant, name="FBS", code=f"fbs-{uuid.uuid4().hex[:8]}")
    products = [
        Product(
            tenant=tenant,
            seller=seller,
            name=str(position["name"]),
            sku_code=f"sku-{position['sku']}",
            wb_barcode=(str(position["barcode"]) if position.get("barcode") else None),
            # WMS-352: опрос забирает только те заказы, по чьим товарам и складам
            # остаток выставлен нами.
            fbs_stock_sync_enabled=True,
        )
        for position in positions
    ]
    db_session.add_all([tenant, seller, warehouse, *products])
    await db_session.flush()
    db_session.add_all(
        [
            MarketplaceAccount(
                tenant_id=tenant.id,
                seller_id=seller.id,
                marketplace="ozon",
                account_slot="primary",
                external_account_id="client-id",
                secret_encrypted=encrypt_secret("api-key"),
                is_active=True,
                validation_status="valid",
            ),
            *[
                ProductMarketplaceLink(
                    tenant_id=tenant.id,
                    seller_id=seller.id,
                    product_id=product.id,
                    marketplace="ozon",
                    external_sku=str(position["sku"]),
                    external_offer_id=str(position["offer_id"]),
                )
                for product, position in zip(products, positions, strict=True)
            ],
        ]
    )
    from app.models.fbs_warehouse_binding import FbsWarehouseBinding

    db_session.add(
        FbsWarehouseBinding(
            tenant_id=tenant.id,
            seller_id=seller.id,
            marketplace="ozon",
            external_warehouse_id="ozon-wh-1",
            wb_warehouse_id=-101,
            wms_warehouse_id=warehouse.id,
        )
    )
    await db_session.commit()

    provider = OzonMarketplaceProvider(
        transport=FakeMarketplaceTransport(
            orders=[
                {
                    "posting_number": "ozon-posting-products",
                    "status": "awaiting_packaging",
                    "warehouse_id": "ozon-wh-1",
                    "created_at": datetime.now(UTC).isoformat(),
                    "products": positions,
                }
            ]
        )
    )
    await ozon_sync_svc.sync_ozon_orders(
        db_session,
        tenant.id,
        seller.id,
        provider,
        AsyncMock(),
    )
    order = (
        await db_session.execute(
            select(FbsOrder).where(FbsOrder.external_order_id == "ozon-posting-products")
        )
    ).scalar_one()
    await db_session.refresh(order, attribute_names=["product_positions"])
    return order, products


@pytest.mark.asyncio
async def test_ozon_import_persists_single_product_position(db_session: AsyncSession) -> None:
    """TC-S03-OZON-021: one Ozon posting retains its sole imported position."""
    order, products = await _sync_ozon_posting_with_products(
        db_session,
        positions=[{"sku": 4001, "offer_id": "offer-1", "name": "Футболка", "quantity": 1}],
    )

    assert order.product_id == products[0].id
    assert [
        (position.ozon_sku, position.product_id, position.quantity, position.name)
        for position in order.product_positions
    ] == [(4001, products[0].id, 1, "Футболка")]


@pytest.mark.asyncio
async def test_ozon_import_persists_all_product_positions(db_session: AsyncSession) -> None:
    """TC-S03-OZON-022: no position is lost when Ozon posting has several products."""
    order, products = await _sync_ozon_posting_with_products(
        db_session,
        positions=[
            {"sku": 4001, "offer_id": "offer-1", "name": "Футболка", "quantity": 1},
            {"sku": 4002, "offer_id": "offer-2", "name": "Носки", "quantity": 1},
        ],
    )

    assert [
        (position.ozon_sku, position.product_id, position.quantity)
        for position in order.product_positions
    ] == [(4001, products[0].id, 1), (4002, products[1].id, 1)]
    worklist = await worklist_svc.build_worklist_items(db_session, order.tenant_id, [order])
    assert [(row["name"], row["quantity"]) for row in worklist[0]["positions"]] == [
        ("Футболка", 1),
        ("Носки", 1),
    ]


@pytest.mark.asyncio
async def test_ozon_repeat_sync_replaces_changed_quantity_and_rereserves(
    db_session: AsyncSession,
) -> None:
    """TC-S03-OZON-026: changed Ozon composition replaces its exact reserve without duplicates."""
    order, products = await _sync_ozon_posting_with_products(
        db_session,
        positions=[{"sku": 4001, "offer_id": "offer-1", "name": "Футболка", "quantity": 1}],
    )
    await db_session.refresh(order, attribute_names=["product_positions"])
    assert order.warehouse_id is not None
    location = StorageLocation(
        tenant_id=order.tenant_id,
        warehouse_id=order.warehouse_id,
        code="A-01",
        barcode="LOC-OZON-RERESERVE",
    )
    db_session.add(location)
    await db_session.flush()
    await inventory_service.record_movement_and_adjust_balance(
        db_session,
        tenant_id=order.tenant_id,
        product_id=products[0].id,
        storage_location_id=location.id,
        quantity_delta=10,
        movement_type="inbound_intake",
        actor_user_id=await resolve_test_actor_user_id(db_session, order.tenant_id),
    )
    await ozon_sync_svc._try_reserve_order(db_session, order)
    await db_session.commit()
    assert order.reserve_status == "reserved"
    changed_provider = OzonMarketplaceProvider(
        transport=FakeMarketplaceTransport(
            orders=[
                {
                    "posting_number": "ozon-posting-products",
                    "status": "awaiting_packaging",
                    "warehouse_id": "ozon-wh-1",
                    "created_at": datetime.now(UTC).isoformat(),
                    "products": [
                        {
                            "sku": 4001,
                            "offer_id": "offer-1",
                            "name": "Футболка",
                            "quantity": 3,
                        }
                    ],
                }
            ]
        )
    )

    await ozon_sync_svc.sync_ozon_orders(
        db_session,
        order.tenant_id,
        order.seller_id,
        changed_provider,
        AsyncMock(),
    )
    await ozon_sync_svc.sync_ozon_orders(
        db_session,
        order.tenant_id,
        order.seller_id,
        changed_provider,
        AsyncMock(),
    )

    await db_session.refresh(order, attribute_names=["product_positions"])
    reservations = list(
        (
            await db_session.execute(
                select(FbsOrderProductReservation)
                .join(
                    FbsOrderProduct,
                    FbsOrderProduct.id == FbsOrderProductReservation.order_product_id,
                )
                .where(FbsOrderProduct.order_id == order.id)
            )
        )
        .scalars()
        .all()
    )
    assert [(position.ozon_sku, position.quantity) for position in order.product_positions] == [
        (4001, 3)
    ]
    assert [reservation.quantity for reservation in reservations] == [3]
    assert order.reserve_status == "reserved"


async def _seed_physical_ozon_packaging(
    session: AsyncSession,
    order: FbsOrder,
    supply: FbsSupply,
    product_quantities: list[tuple[Product, int]],
) -> None:
    """Give provider-contract tests the physical packing state delivery requires."""
    now = datetime.now(UTC)
    task = PackagingTask(
        tenant_id=order.tenant_id,
        warehouse_id=supply.warehouse_id,
        status="done",
    )
    session.add(task)
    await session.flush()
    supply.packaging_task_id = task.id
    packed_units: list[dict[str, str]] = []
    first_line: PackagingTaskLine | None = None
    for index, (product, quantity) in enumerate(product_quantities):
        location = StorageLocation(
            tenant_id=order.tenant_id,
            warehouse_id=supply.warehouse_id,
            code=f"OZON-PACK-{uuid.uuid4().hex[:8]}",
            barcode=f"OZON-PACK-BC-{uuid.uuid4().hex[:8]}",
        )
        session.add(location)
        await session.flush()
        line = PackagingTaskLine(
            task_id=task.id,
            product_id=product.id,
            storage_location_id=location.id,
            qty_total=quantity,
            qty_packed_in_task=quantity,
        )
        session.add_all(
            [
                line,
                InventoryBalance(
                    tenant_id=order.tenant_id,
                    product_id=product.id,
                    storage_location_id=location.id,
                    quantity=quantity,
                    quantity_unpacked=0,
                    quantity_packed=quantity,
                ),
            ]
        )
        await session.flush()
        first_line = first_line or line
        packed_units.extend(
            {
                "product_id": str(product.id),
                "packaging_task_line_id": str(line.id),
                "storage_location_id": str(location.id),
                "idempotency_key": f"ozon-provider-pack-{index}-{unit}",
                "packed_at": now.isoformat(),
            }
            for unit in range(quantity)
        )
    assert first_line is not None
    session.add(
        FbsPackagingFulfillment(
            tenant_id=order.tenant_id,
            fbs_order_id=order.id,
            packaging_task_id=task.id,
            packaging_task_line_id=first_line.id,
            fulfilled_at=now,
            pack_idempotency_key=f"ozon-provider-pack-{uuid.uuid4()}",
            ozon_packed_units_json=packed_units,
        )
    )
    await session.commit()


async def _seed_ready_for_handoff(
    session: AsyncSession,
    order: FbsOrder,
    supply: FbsSupply,
    product: Product,
) -> None:
    session.add(
        FbsOrderProduct(
            order_id=order.id,
            product_id=product.id,
            ozon_sku=3001,
            quantity=1,
            offer_id="offer-1",
            name="Product",
            position_index=0,
        )
    )
    await session.commit()
    await seed_boxes(session, order, supply)
    await _seed_physical_ozon_packaging(session, order, supply, [(product, 1)])


async def _assemble_test_order(
    session: AsyncSession,
    order: FbsOrder,
    supply: FbsSupply,
    transport: FakeMarketplaceTransport,
) -> None:
    details = dict(order.meta_details_json or {})
    details.pop("ozon_assembly", None)
    order.meta_details_json = details
    positions = list(
        (
            await session.scalars(
                select(FbsOrderProduct).where(
                    FbsOrderProduct.order_id == order.id,
                )
            )
        ).all()
    )
    if not positions:
        session.add(
            FbsOrderProduct(
                order_id=order.id,
                product_id=order.product_id,
                ozon_sku=3001,
                quantity=1,
                offer_id="offer-1",
                name="Product",
                position_index=0,
            )
        )
    await session.commit()
    boxes = await seed_boxes(session, order, supply)
    transport.endpoint_responses["/v4/posting/fbs/ship"] = {
        "result": [f"{order.external_order_id}-{index}" for index in range(len(boxes))]
    }
    response = transport.endpoint_responses.get("/v3/posting/fbs/get")
    if isinstance(response, dict):
        response["result"]["status"] = "awaiting_packaging"
    await assemble_box_order(
        session,
        order.tenant_id,
        supply.id,
        boxes[0].id,
        provider=OzonMarketplaceProvider(transport=transport),
        credentials=("c", "k"),
    )


@pytest.mark.asyncio
async def test_ozon_ship_keeps_quantity_above_one(db_session: AsyncSession) -> None:
    """TC-S03-OZON-023: /ship receives quantity from the imported Ozon composition."""
    _tenant, _, _, product, order, supply = await _seed_ozon_supply_case(db_session, packed=True)
    assert supply is not None
    db_session.add(
        FbsOrderProduct(
            order_id=order.id,
            product_id=product.id,
            ozon_sku=3001,
            offer_id="offer-1",
            name="Product",
            quantity=2,
            position_index=0,
            provider_data_json={"sku": 3001, "quantity": 2},
        )
    )
    await db_session.commit()
    await _seed_physical_ozon_packaging(db_session, order, supply, [(product, 2)])
    transport = FakeMarketplaceTransport(endpoint_responses=_ozon_handoff_responses())

    await _assemble_test_order(db_session, order, supply, transport)

    ship_payload = next(
        payload for path, payload in transport.endpoint_calls if path == "/v4/posting/fbs/ship"
    )
    assert ship_payload["packages"] == [{"products": [{"product_id": 3001, "quantity": 2}]}]


@pytest.mark.asyncio
async def test_ozon_multi_position_ship_keeps_complete_posting_composition(
    db_session: AsyncSession,
) -> None:
    """TC-S03-OZON-027: /ship receives every position rather than only the first one."""
    tenant, _, _, product, order, supply = await _seed_ozon_supply_case(db_session, packed=True)
    assert supply is not None
    second_product = Product(
        tenant_id=tenant.id,
        seller_id=order.seller_id,
        name="Second product",
        sku_code=f"ozon-second-{uuid.uuid4().hex[:8]}",
    )
    db_session.add(second_product)
    await db_session.flush()
    db_session.add_all(
        [
            FbsOrderProduct(
                order_id=order.id,
                product_id=product.id,
                ozon_sku=3001,
                offer_id="offer-1",
                name="Product",
                quantity=1,
                position_index=0,
                provider_data_json={"sku": 3001, "quantity": 1},
            ),
            FbsOrderProduct(
                order_id=order.id,
                product_id=second_product.id,
                ozon_sku=3002,
                offer_id="offer-2",
                name="Second product",
                quantity=3,
                position_index=1,
                provider_data_json={"sku": 3002, "quantity": 3},
            ),
        ]
    )
    await db_session.commit()
    await _seed_physical_ozon_packaging(
        db_session,
        order,
        supply,
        [(product, 1), (second_product, 3)],
    )
    transport = FakeMarketplaceTransport(endpoint_responses=_ozon_handoff_responses())

    await _assemble_test_order(db_session, order, supply, transport)

    ship_payload = next(
        payload for path, payload in transport.endpoint_calls if path == "/v4/posting/fbs/ship"
    )
    assert ship_payload["packages"] == [
        {"products": [{"product_id": 3001, "quantity": 1}]},
        {"products": [{"product_id": 3002, "quantity": 3}]},
    ]


@pytest.mark.asyncio
async def test_ozon_handoff_sets_required_product_country_before_ship(
    db_session: AsyncSession,
) -> None:
    """TC-S03-OZON-028: a required country is set and read back before /ship."""
    _tenant, _, _, product, order, supply = await _seed_ozon_supply_case(db_session, packed=True)
    assert supply is not None
    product.country_of_origin_iso_code = "RU"
    db_session.add(
        FbsOrderProduct(
            order_id=order.id,
            product_id=product.id,
            ozon_sku=3001,
            offer_id="offer-1",
            name="Product",
            quantity=1,
            position_index=0,
            provider_data_json={"sku": 3001, "quantity": 1},
        )
    )
    await db_session.commit()
    await _seed_physical_ozon_packaging(db_session, order, supply, [(product, 1)])
    responses = _ozon_handoff_responses()
    responses["/v2/posting/fbs/product/country/list"] = {
        "result": [{"name": "Россия", "country_iso_code": "RU"}]
    }
    responses["/v2/posting/fbs/product/country/set"] = {
        "product_id": 3001,
        "is_gtd_needed": False,
    }
    transport = FakeMarketplaceTransport(
        endpoint_responses=responses,
        endpoint_response_queues={
            "/v3/posting/fbs/get": [
                {
                    "result": {
                        "posting_number": order.external_order_id,
                        "status": "awaiting_packaging",
                        "requirements": {"products_requiring_country": ["3001"]},
                    }
                },
                {
                    "result": {
                        "posting_number": order.external_order_id,
                        "status": "awaiting_packaging",
                        "requirements": {"products_requiring_country": []},
                    }
                },
                responses["/v3/posting/fbs/get"],
            ]
        },
    )

    await _assemble_test_order(db_session, order, supply, transport)

    paths = [path for path, _ in transport.endpoint_calls]
    assert (
        paths.index("/v2/posting/fbs/product/country/list")
        < paths.index("/v2/posting/fbs/product/country/set")
        < paths.index("/v4/posting/fbs/ship")
    )
    country_payload = next(
        payload
        for path, payload in transport.endpoint_calls
        if path == "/v2/posting/fbs/product/country/set"
    )
    assert country_payload == {
        "posting_number": order.external_order_id,
        "product_id": 3001,
        "country_iso_code": "RU",
    }


@pytest.mark.asyncio
async def test_ozon_handoff_blocks_when_required_product_country_is_missing(
    db_session: AsyncSession,
) -> None:
    """TC-S03-OZON-029: missing catalog country is explicit and /ship is not called."""
    _tenant, _, _, product, order, supply = await _seed_ozon_supply_case(db_session, packed=True)
    assert supply is not None
    db_session.add(
        FbsOrderProduct(
            order_id=order.id,
            product_id=product.id,
            ozon_sku=3001,
            offer_id="offer-1",
            name="Product",
            quantity=1,
            position_index=0,
            provider_data_json={"sku": 3001, "quantity": 1},
        )
    )
    await db_session.commit()
    responses = _ozon_handoff_responses()
    responses["/v2/posting/fbs/product/country/list"] = {
        "result": [{"name": "Россия", "country_iso_code": "RU"}]
    }
    transport = FakeMarketplaceTransport(
        endpoint_responses=responses,
        endpoint_response_queues={
            "/v3/posting/fbs/get": [
                {
                    "result": {
                        "posting_number": order.external_order_id,
                        "status": "awaiting_packaging",
                        "requirements": {"products_requiring_country": ["3001"]},
                    }
                }
            ]
        },
    )

    with pytest.raises(OzonFbsProcessError, match="ozon_country_required") as caught:
        await _assemble_test_order(db_session, order, supply, transport)

    assert caught.value.message == "Для Ozon SKU 3001 укажите страну изготовления в каталоге."
    assert all(path != "/v4/posting/fbs/ship" for path, _ in transport.endpoint_calls)


@pytest.mark.asyncio
async def test_ozon_handoff_blocks_when_posting_exceeds_the_drop_off_limits(
    db_session: AsyncSession,
) -> None:
    """TC-S03-OZON-031: превышение лимита пункта приёма останавливает сборку.

    Останавливает именно превышение, а не наличие лимита: метод
    `/v1/posting/fbs/restrictions` возвращает ограничения пункта приёма всегда,
    и раньше сам факт их наличия валил передачу в 409 — на живом пункте приёма
    отгрузка не прошла бы никогда.
    """
    _tenant, _, _, _, order, supply = await _seed_ozon_supply_case(db_session, packed=True)
    assert supply is not None
    order.price = 60_000_000  # 600 000 ₽ в копейках
    await db_session.commit()
    responses = _ozon_handoff_responses()
    responses["/v1/posting/fbs/restrictions"] = {
        "result": {
            "posting_number": "ozon-posting-dispatch",
            "max_posting_price": 500000,
        }
    }
    transport = FakeMarketplaceTransport(endpoint_responses=responses)

    with pytest.raises(OzonFbsProcessError, match="ozon_posting_restricted") as caught:
        await _assemble_test_order(db_session, order, supply, transport)

    assert caught.value.message == (
        "Отправление Ozon не проходит ограничения пункта приёма "
        "(стоимость 600000 ₽ больше допустимых 500000 ₽); "
        "проверьте состав в кабинете Ozon до сборки."
    )
    assert all(path != "/v4/posting/fbs/ship" for path, _ in transport.endpoint_calls)


@pytest.mark.asyncio
async def test_ozon_handoff_passes_a_posting_that_fits_the_drop_off_limits(
    db_session: AsyncSession,
) -> None:
    """Обычные лимиты живого пункта приёма передаче не мешают."""
    _tenant, _, _, _, order, supply = await _seed_ozon_supply_case(db_session, packed=True)
    assert supply is not None
    order.price = 250000  # 2500 ₽
    await db_session.commit()
    responses = _ozon_handoff_responses()
    responses["/v1/posting/fbs/restrictions"] = {
        "result": {
            "posting_number": "ozon-posting-dispatch",
            "max_posting_weight": 40000,
            "min_posting_weight": 0,
            "width": 500,
            "height": 500,
            "length": 500,
            "max_posting_price": 500000,
            "min_posting_price": 0,
        }
    }
    transport = FakeMarketplaceTransport(endpoint_responses=responses)

    await _assemble_test_order(db_session, order, supply, transport)

    assert any(path == "/v4/posting/fbs/ship" for path, _ in transport.endpoint_calls)


@pytest.mark.asyncio
async def test_wb_order_keeps_legacy_single_product_shape(db_session: AsyncSession) -> None:
    """TC-S03-OZON-025: the additive Ozon relation does not change WB orders."""
    tenant = Tenant(name="WB regression", slug=f"wb-regression-{uuid.uuid4().hex[:8]}")
    seller = Seller(tenant=tenant, name="Seller")
    warehouse = Warehouse(tenant=tenant, name="FBS", code=f"fbs-{uuid.uuid4().hex[:8]}")
    product = Product(tenant=tenant, seller=seller, name="Product", sku_code="wb-product")
    db_session.add_all([tenant, seller, warehouse, product])
    await db_session.flush()
    now = datetime.now(UTC)
    order = FbsOrder(
        tenant_id=tenant.id,
        seller_id=seller.id,
        warehouse_id=warehouse.id,
        product_id=product.id,
        marketplace="wb",
        wb_order_id=7001,
        mapping_status=MAPPING_STATUS_MAPPED,
        reserve_status=RESERVE_STATUS_RESERVED,
        created_at_wb=now,
        deadline_at=now + timedelta(days=1),
    )
    db_session.add(order)
    await db_session.commit()
    await db_session.refresh(order, attribute_names=["product_positions"])

    assert order.product_id == product.id
    assert order.product_positions == []


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
            external_supply_id=None,
            wb_supply_id=None,
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
        wb_nm_id=3001,
        wb_warehouse_id=11,
        status=FBS_ORDER_STATUS_PACKED if packed else "new",
        mapping_status=MAPPING_STATUS_MAPPED,
        reserve_status=RESERVE_STATUS_RESERVED,
        created_at_wb=now,
        deadline_at=now + timedelta(days=1),
        # Ozon ответил по требованиям и сказал, что маркировка не нужна. Без
        # этого признака гейт выпуска честно не знает, нужна она или нет, и
        # передачу не разрешает — это его новое и намеренное поведение.
        meta_details_json={
            "ozon_requirements": {"kinds": []},
            **({"ozon_assembly": {"posting_numbers": ["ozon-posting-dispatch"]}} if packed else {}),
        },
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
    transport = FakeMarketplaceTransport()

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
    assert transport.calls == []
    assert str(workspace["supply"]["wb_supply_id"]).startswith("PENDING-")
    assert workspace["supply"]["external_supply_id"] is None
    assert workspace["supply"]["boxes_without_distribution"] is False
    wb_create.assert_not_awaited()
    wb_add.assert_not_awaited()


@pytest.mark.asyncio
async def test_ozon_boxes_are_local_and_require_distribution(
    db_session: AsyncSession,
) -> None:
    tenant, _, _, _, _, supply = await _seed_ozon_supply_case(db_session, packed=True)
    assert supply is not None
    boxes = await box_svc.create_boxes(
        db_session,
        tenant.id,
        supply.id,
        1,
        "ozon-box",
        actor_user_id=None,
    )
    assert len(boxes) == 1
    assert boxes[0].trbx_id is None
    with pytest.raises(box_svc.FbsPackingBoxError, match="ozon_box_distribution_required"):
        await box_svc.set_boxes_without_distribution(
            db_session,
            tenant.id,
            supply.id,
            True,
            actor_user_id=None,
        )
    assert (
        await box_svc.set_boxes_without_distribution(
            db_session,
            tenant.id,
            supply.id,
            False,
            actor_user_id=None,
        )
        is False
    )


def test_without_distribution_stage_does_not_create_navigation_blockers() -> None:
    supply = SimpleNamespace(
        status=FBS_SUPPLY_STATUS_PACKED,
        delivery_type=FBS_DELIVERY_TYPE_WAREHOUSE_SC,
        trbxes=[],
    )
    progress = workspace_svc.WorkspaceProgress(
        picked=1,
        packed=1,
        metadata_ready=1,
        stickers_ready=1,
        total=1,
    )

    stage = workspace_svc._compute_stage(
        supply,
        [SimpleNamespace()],
        progress,
        has_physical_boxes=False,
        without_distribution=True,
    )
    blockers = workspace_svc._compute_workspace_blockers(
        supply,
        [],
        stage,
        progress,
        has_physical_boxes=False,
        without_distribution=True,
    )

    # Режим «без раскладки» сразу открывает подготовку к передаче: физические
    # короба не нужны. Раньше здесь ждали "delivery", но этот этап выдавался
    # хвостом `_compute_stage`, который проверял стикеры и статус поставки и
    # тем самым управлял навигацией. Хвост снят, оба значения фронт показывает
    # одной и той же вкладкой «Короба».
    assert stage == "handoff_prep"
    assert all(item["code"] != "physical_boxes_required" for item in blockers)

    supply.delivery_type = FBS_DELIVERY_TYPE_PVZ
    pvz_stage = workspace_svc._compute_stage(
        supply,
        [SimpleNamespace()],
        progress,
        has_physical_boxes=False,
        without_distribution=True,
    )
    pvz_blockers = workspace_svc._compute_workspace_blockers(
        supply,
        [],
        pvz_stage,
        progress,
        has_physical_boxes=False,
        without_distribution=True,
    )
    assert pvz_stage == "handoff_prep"
    assert all(item["code"] != "cargo_places_required" for item in pvz_blockers)


# Однопиксельный PNG: минимальный корректный файл, чтобы хранилище печатных
# активов приняло штрихкод перевозки. В боевом коде такой заглушки больше нет.
_ONE_PIXEL_PNG_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAE"
    "hQGAhKmMIQAAAABJRU5ErkJggg=="
)


def _ozon_handoff_responses(*, substatus: str = "posting_in_carriage") -> dict[str, object]:
    png = _ONE_PIXEL_PNG_BASE64
    return {
        "/v1/posting/fbs/restrictions": {"result": {"posting_number": "ozon-posting-dispatch"}},
        "/v4/posting/fbs/ship": {"result": ["ozon-posting-dispatch"]},
        "/v3/posting/fbs/get": {
            "result": {
                "posting_number": "ozon-posting-dispatch",
                "status": "awaiting_deliver",
                "substatus": substatus,
                "related_postings": {"related_posting_numbers": []},
            }
        },
        "/v2/posting/fbs/package-label/create": {
            "result": {"tasks": [{"task_id": 71, "task_type": "big_label"}]}
        },
        "/v1/posting/fbs/package-label/get": {
            "result": {"status": "completed", "file_url": "https://example.invalid/labels"}
        },
        "/v2/posting/fbs/package-label": {
            "file_content": png,
            "file_name": "labels.pdf",
            "content_type": "application/pdf",
        },
        "/v1/carriage/create": {"carriage_id": 901},
        "/v1/carriage/set-postings": {
            "result": [{"posting_number": "ozon-posting-dispatch", "result": True}]
        },
        "/v1/carriage/approve": {},
        "/v1/carriage/get": {"carriage_id": 901, "status": "sended"},
        "/v2/posting/fbs/act/get-barcode": {
            "file_content": png,
            "file_name": "barcode.png",
            "content_type": "image/png",
        },
        "/v2/posting/fbs/act/get-barcode/text": {"result": "OZON-ACT-901"},
        # Живой метод листа отгрузки: старый `digital/act/get-pdf` Ozon отключил
        "/v2/posting/fbs/act/get-pdf": {
            "file_content": png,
            "file_name": "shipping-list.pdf",
            "content_type": "application/pdf",
        },
    }


@pytest.mark.asyncio
async def test_ozon_supply_handoff_ships_rechecks_and_creates_carriage_without_wb(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant, _, _, product, order, supply = await _seed_ozon_supply_case(
        db_session,
        packed=True,
    )
    assert supply is not None
    await _seed_ready_for_handoff(db_session, order, supply, product)
    wb_deliver = AsyncMock(side_effect=AssertionError("WB deliver must not run for Ozon"))
    wb_qr = AsyncMock(side_effect=AssertionError("WB QR must not run for Ozon"))
    wb_sync = AsyncMock(side_effect=AssertionError("WB sync must not run for Ozon"))
    monkeypatch.setattr(shipment_svc, "deliver_marketplace_supply", wb_deliver)
    monkeypatch.setattr(shipment_svc, "fetch_marketplace_supply_barcode", wb_qr)
    monkeypatch.setattr(shipment_svc, "_sync_supply_orders_from_wb", wb_sync)
    transport = FakeMarketplaceTransport(endpoint_responses=_ozon_handoff_responses())

    delivered = await shipment_svc.deliver_supply(
        db_session,
        tenant.id,
        supply.id,
        AsyncMock(),
        idempotency_key=f"ozon-deliver-{uuid.uuid4()}",
        actor_user_id=None,
        ozon_provider=OzonMarketplaceProvider(transport=transport),
    )

    assert delivered.status == FBS_SUPPLY_STATUS_IN_DELIVERY
    assert delivered.external_supply_id == "901"
    assert [call[0] for call in transport.endpoint_calls] == [
        "/v3/posting/fbs/get",
        "/v1/carriage/create",
        "/v1/carriage/get",
        "/v1/carriage/approve",
        "/v1/carriage/get",
        "/v2/posting/fbs/act/get-barcode",
        "/v2/posting/fbs/act/get-barcode/text",
        "/v2/posting/fbs/act/get-pdf",
    ]
    wb_deliver.assert_not_awaited()
    wb_qr.assert_not_awaited()
    wb_sync.assert_not_awaited()


@pytest.mark.asyncio
async def test_ozon_live_handoff_never_falls_back_to_fake_success(
    db_session: AsyncSession,
) -> None:
    tenant, _, _, _, _, supply = await _seed_ozon_supply_case(db_session, packed=True)
    assert supply is not None

    with pytest.raises(shipment_svc.FbsShipmentError, match="ozon_live_handoff_blocked"):
        await shipment_svc.deliver_supply(
            db_session,
            tenant.id,
            supply.id,
            AsyncMock(),
            idempotency_key=f"ozon-live-blocked-{uuid.uuid4()}",
            actor_user_id=None,
        )

    assert supply.status != FBS_SUPPLY_STATUS_IN_DELIVERY
    assert supply.external_supply_id is None


@pytest.mark.asyncio
async def test_ozon_ship_failed_readback_stays_visible_and_blocks_handoff(
    db_session: AsyncSession,
) -> None:
    tenant, _, _, product, order, supply = await _seed_ozon_supply_case(db_session, packed=True)
    assert supply is not None
    await _seed_ready_for_handoff(db_session, order, supply, product)
    responses = _ozon_handoff_responses(substatus="ship_failed")
    transport = FakeMarketplaceTransport(endpoint_responses=responses)

    with pytest.raises(shipment_svc.FbsShipmentError, match="ozon_ship_failed"):
        await shipment_svc.deliver_supply(
            db_session,
            tenant.id,
            supply.id,
            AsyncMock(),
            idempotency_key=f"ozon-failed-{uuid.uuid4()}",
            actor_user_id=None,
            ozon_provider=OzonMarketplaceProvider(transport=transport),
        )

    assert order.supplier_status == "ship_failed"
    assert order.meta_details_json is not None
    assert "сборка" in str(order.meta_details_json).lower()
    assert [call[0] for call in transport.endpoint_calls] == [
        "/v3/posting/fbs/get",
    ]


async def _ozon_deliver_operation(idempotency_key: str) -> FbsWbOperation:
    """Прочитать журнал передачи из отдельной сессии — то есть только то,
    что действительно закоммичено, а не то, что живёт в открытой транзакции."""
    async with SessionLocal() as reader:
        return (
            await reader.execute(
                select(FbsWbOperation).where(
                    FbsWbOperation.operation_kind == "supply_deliver",
                    FbsWbOperation.idempotency_key == idempotency_key,
                )
            )
        ).scalar_one()


@pytest.mark.asyncio
async def test_ozon_partial_handoff_is_journalled_and_the_retry_resumes(
    db_session: AsyncSession,
) -> None:
    """Первое отправление уехало, второе упало — повтор не собирает первое заново.

    Это ровно тот сценарий, ради которого заведена точка сохранения: `/ship`
    необратим, а локальная транзакция при ошибке откатывается целиком.
    """
    tenant, seller, warehouse, product, first, supply = await _seed_ozon_supply_case(
        db_session,
        packed=True,
    )
    assert supply is not None
    await _seed_ready_for_handoff(db_session, first, supply, product)
    now = datetime.now(UTC)
    second = FbsOrder(
        tenant_id=tenant.id,
        seller_id=seller.id,
        warehouse_id=warehouse.id,
        product_id=product.id,
        supply_id=supply.id,
        marketplace="ozon",
        external_order_id="ozon-posting-second",
        wb_order_id=2002,
        wb_nm_id=3002,
        wb_warehouse_id=11,
        status=FBS_ORDER_STATUS_PACKED,
        mapping_status=MAPPING_STATUS_MAPPED,
        reserve_status=RESERVE_STATUS_RESERVED,
        created_at_wb=now,
        deadline_at=now + timedelta(days=1),
        meta_details_json={"ozon_requirements": {"kinds": []}},
    )
    db_session.add(second)
    await db_session.commit()
    await _seed_ready_for_handoff(db_session, second, supply, product)

    failing = FakeMarketplaceTransport(endpoint_responses=_ozon_handoff_responses())
    with pytest.raises(shipment_svc.FbsShipmentError, match="ozon_order_not_assembled"):
        await shipment_svc.deliver_supply(
            db_session,
            tenant.id,
            supply.id,
            AsyncMock(),
            idempotency_key="ozon-partial-first",
            actor_user_id=None,
            ozon_provider=OzonMarketplaceProvider(transport=failing),
        )
    assert all(
        path not in {"/v4/posting/fbs/ship", "/v1/carriage/create"}
        for path, _ in failing.endpoint_calls
    )
    assert (await _ozon_deliver_operation("ozon-partial-first")).state == "failed"
    second.meta_details_json = {
        **(second.meta_details_json or {}),
        "ozon_assembly": {"posting_numbers": ["ozon-posting-second"]},
    }
    await db_session.commit()

    healthy = FakeMarketplaceTransport(endpoint_responses=_ozon_handoff_responses())
    delivered = await shipment_svc.deliver_supply(
        db_session,
        tenant.id,
        supply.id,
        AsyncMock(),
        idempotency_key="ozon-partial-retry",
        actor_user_id=None,
        ozon_provider=OzonMarketplaceProvider(transport=healthy),
    )

    paths = [path for path, _ in healthy.endpoint_calls]
    assert "/v4/posting/fbs/ship" not in paths
    assert "/v1/carriage/set-postings" not in paths
    progress = (await _ozon_deliver_operation("ozon-partial-retry")).request_summary_json[
        "ozon_handoff_progress"
    ]
    assert set(progress["posting_numbers"]) == {"ozon-posting-dispatch", "ozon-posting-second"}
    assert delivered.status == FBS_SUPPLY_STATUS_IN_DELIVERY
    assert (await _ozon_deliver_operation("ozon-partial-retry")).state == "confirmed"
    assert first.status == "in_delivery"
    assert second.status == "in_delivery"


@pytest.mark.asyncio
async def test_ozon_handoff_after_approved_carriage_does_not_approve_twice(
    db_session: AsyncSession,
) -> None:
    """Перевозка подтверждена, а штрихкод акта не пришёл — повтор идёт за документами.

    Второй `/v1/carriage/approve` по уже подтверждённой перевозке — это
    повторная мутация в кабинете; снимок обязан её предотвратить.
    """
    tenant, _, _, product, order, supply = await _seed_ozon_supply_case(db_session, packed=True)
    assert supply is not None
    await _seed_ready_for_handoff(db_session, order, supply, product)
    responses = _ozon_handoff_responses()
    failing = FakeMarketplaceTransport(
        endpoint_responses=responses,
        errors={
            "/v2/posting/fbs/act/get-barcode": MarketplaceProviderError(
                "ozon", 503, {"message": "later"}
            )
        },
    )

    with pytest.raises(shipment_svc.FbsShipmentError):
        await shipment_svc.deliver_supply(
            db_session,
            tenant.id,
            supply.id,
            AsyncMock(),
            idempotency_key="ozon-barcode-first",
            actor_user_id=None,
            ozon_provider=OzonMarketplaceProvider(transport=failing),
        )

    progress = (await _ozon_deliver_operation("ozon-barcode-first")).request_summary_json[
        "ozon_handoff_progress"
    ]
    assert progress["carriage_id"] == 901
    assert progress["carriage_approved"] is True

    # За время между попытками отправление ушло дальше по жизни: перевозку
    # забрали, Ozon показывает приёмку. Гейт «должно быть awaiting_deliver»
    # относится к сборке, и на повторе он не имеет права запирать документы.
    retry_responses = _ozon_handoff_responses()
    retry_responses["/v3/posting/fbs/get"] = {
        "result": {
            "posting_number": "ozon-posting-dispatch",
            "status": "acceptance_in_progress",
            "substatus": "posting_in_carriage",
            "related_postings": {"related_posting_numbers": []},
        }
    }
    healthy = FakeMarketplaceTransport(endpoint_responses=retry_responses)
    delivered = await shipment_svc.deliver_supply(
        db_session,
        tenant.id,
        supply.id,
        AsyncMock(),
        idempotency_key="ozon-barcode-retry",
        actor_user_id=None,
        ozon_provider=OzonMarketplaceProvider(transport=healthy),
    )

    paths = [path for path, _ in healthy.endpoint_calls]
    assert "/v4/posting/fbs/ship" not in paths
    assert "/v1/carriage/create" not in paths
    assert "/v1/carriage/set-postings" not in paths
    assert "/v1/carriage/approve" not in paths
    assert "/v2/posting/fbs/act/get-barcode" in paths
    assert delivered.status == FBS_SUPPLY_STATUS_IN_DELIVERY
    assert delivered.external_supply_id == "901"


@dataclass
class _RecordingStatusTransport(FakeMarketplaceTransport):
    """Фейк, который помнит, по каким именно отправлениям его спросили."""

    requested: list[list[str]] = field(default_factory=list)

    async def fetch_statuses(
        self,
        *,
        client_id: str,
        api_key: str,
        order_ids: Sequence[str],
    ) -> list[dict[str, Any]]:
        self.requested.append(list(order_ids))
        return await super().fetch_statuses(
            client_id=client_id,
            api_key=api_key,
            order_ids=order_ids,
        )


@pytest.mark.asyncio
async def test_ozon_status_sync_skips_finished_orders_and_polls_the_rest_in_turns(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Опрос берёт порцию живых заказов по кругу, а не всю историю продавца.

    Подстатус Ozon отдаёт только карточкой по одному номеру, поэтому размер
    выборки — это ровно число последовательных запросов за круг автоопроса.
    """
    tenant, seller, warehouse, product, live_old, _ = await _seed_ozon_supply_case(
        db_session,
        packed=False,
    )
    now = datetime.now(UTC)
    live_old.last_wb_sync_at = now - timedelta(hours=2)
    extra = []
    for index, status in enumerate(("done", "cancelled", "new"), start=1):
        extra.append(
            FbsOrder(
                tenant_id=tenant.id,
                seller_id=seller.id,
                warehouse_id=warehouse.id,
                product_id=product.id,
                marketplace="ozon",
                external_order_id=f"ozon-posting-{status}",
                wb_order_id=9000 + index,
                status=status,
                mapping_status=MAPPING_STATUS_MAPPED,
                reserve_status=RESERVE_STATUS_RESERVED,
                created_at_wb=now,
                deadline_at=now + timedelta(days=1),
                last_wb_sync_at=now - timedelta(hours=1),
            )
        )
    db_session.add_all(extra)
    await db_session.commit()
    monkeypatch.setattr(ozon_sync_svc, "OZON_STATUS_SYNC_BATCH_LIMIT", 1)
    transport = _RecordingStatusTransport()

    await ozon_sync_svc.sync_ozon_order_statuses(
        db_session,
        tenant.id,
        seller.id,
        OzonMarketplaceProvider(transport=transport),
        AsyncMock(),
    )
    await ozon_sync_svc.sync_ozon_order_statuses(
        db_session,
        tenant.id,
        seller.id,
        OzonMarketplaceProvider(transport=transport),
        AsyncMock(),
    )

    # Завершённый и отменённый не спрашиваются вовсе; живые идут по кругу,
    # первым — тот, кого дольше не опрашивали.
    assert transport.requested == [
        ["ozon-posting-dispatch"],
        ["ozon-posting-new"],
    ]


def _ozon_cancel_transport() -> FakeMarketplaceTransport:
    return FakeMarketplaceTransport(
        endpoint_responses={
            "/v1/posting/fbs/cancel-reason": {
                "result": [
                    {
                        "posting_number": "ozon-posting-dispatch",
                        "reasons": [
                            {"id": 352, "title": "нет товара", "type_id": "seller"},
                            {"id": 402, "title": "другое", "type_id": "seller"},
                        ],
                    }
                ]
            },
            "/v2/posting/fbs/cancel": {"result": True},
        }
    )


@pytest.mark.asyncio
async def test_ozon_cancellation_is_journalled_before_the_local_part(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ozon отменил, локальная часть упала — повтор не отменяет в кабинете второй раз.

    Отмена у Ozon необратима, а локальное сторнирование может упасть после неё.
    Без отметки об отмене WMS считал бы заказ активным, а повтор ушёл бы в
    кабинет ещё раз.
    """
    tenant, _, _, _, order, _ = await _seed_ozon_supply_case(db_session, packed=False)
    monkeypatch.setattr(settings, "ozon_live_api_enabled", True)
    transport = _ozon_cancel_transport()
    monkeypatch.setattr(
        cancellation_svc,
        "build_ozon_provider",
        lambda: OzonMarketplaceProvider(transport=transport),
    )

    async def _boom(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("локальная часть отмены упала")

    monkeypatch.setattr(cancellation_svc, "_release_reservation", _boom)

    with pytest.raises(RuntimeError):
        await cancellation_svc.cancel_order(
            db_session,
            tenant.id,
            order.id,
            AsyncMock(),
            actor_user_id=None,
        )

    async with SessionLocal() as reader:
        stored = await reader.get(FbsOrder, order.id)
        assert stored is not None
        assert stored.status != FBS_ORDER_STATUS_CANCELLED
        journal = (stored.meta_details_json or {})["ozon_cancellation"]
        assert journal["reason_id"] == 352
        assert journal["posting_number"] == "ozon-posting-dispatch"

    monkeypatch.undo()
    monkeypatch.setattr(settings, "ozon_live_api_enabled", True)
    retry_transport = _ozon_cancel_transport()
    monkeypatch.setattr(
        cancellation_svc,
        "build_ozon_provider",
        lambda: OzonMarketplaceProvider(transport=retry_transport),
    )

    cancelled = await cancellation_svc.cancel_order(
        db_session,
        tenant.id,
        order.id,
        AsyncMock(),
        actor_user_id=None,
    )
    await db_session.commit()

    assert cancelled.status == FBS_ORDER_STATUS_CANCELLED
    assert retry_transport.endpoint_calls == []


@pytest.mark.asyncio
async def test_ozon_cancellation_reason_comes_from_the_caller(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Причина — параметр, а не зашитое «товар закончился».

    Упакованный заказ с браком отменяется по своей причине; раньше в кабинет
    всегда уезжала 352, и в отчётах продавца брак выглядел как нехватка товара.
    """
    tenant, _, _, _, order, _ = await _seed_ozon_supply_case(db_session, packed=False)
    monkeypatch.setattr(settings, "ozon_live_api_enabled", True)
    transport = _ozon_cancel_transport()
    monkeypatch.setattr(
        cancellation_svc,
        "build_ozon_provider",
        lambda: OzonMarketplaceProvider(transport=transport),
    )

    await cancellation_svc.cancel_order(
        db_session,
        tenant.id,
        order.id,
        AsyncMock(),
        actor_user_id=None,
        reason_id=402,
        reason_message="Брак упаковки",
    )
    await db_session.commit()

    cancel_payload = next(
        payload for path, payload in transport.endpoint_calls if path == "/v2/posting/fbs/cancel"
    )
    assert cancel_payload == {
        "posting_number": "ozon-posting-dispatch",
        "cancel_reason_id": 402,
        "cancel_reason_message": "Брак упаковки",
    }


@pytest.mark.asyncio
async def test_ozon_marking_uses_exemplar_flow_and_preserves_gs(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant, _, _, _, order, _ = await _seed_ozon_supply_case(db_session, packed=True)
    marking = FbsOrderMarking(
        tenant_id=tenant.id,
        order_id=order.id,
        kind="sgtin",
        value="010460123456789021ABC\x1d91XYZ",
    )
    db_session.add(marking)
    await db_session.flush()
    wb_put = AsyncMock(side_effect=AssertionError("WB marking must not run for Ozon"))
    monkeypatch.setattr(marking_svc, "put_marketplace_order_meta", wb_put)
    transport = FakeMarketplaceTransport(
        endpoint_responses={
            "/v6/fbs/posting/product/exemplar/create-or-get": {
                "posting_number": order.external_order_id,
                "products": [{"product_id": 3001, "exemplars": [{"exemplar_id": 81}]}],
            },
            "/v5/fbs/posting/product/exemplar/validate": {
                "products": [{"product_id": 3001, "valid": True, "exemplars": []}]
            },
            "/v6/fbs/posting/product/exemplar/set": {},
            "/v5/fbs/posting/product/exemplar/status": {
                "posting_number": order.external_order_id,
                "status": "ship_available",
                "products": [],
            },
        }
    )

    rows = await marking_svc.attach_order_meta_to_wb_and_sync(
        db_session,
        tenant.id,
        order,
        marking,
        AsyncMock(),
        actor_user_id=None,
        ozon_provider=OzonMarketplaceProvider(transport=transport),
    )

    assert rows[0].meta_status == META_STATUS_ACCEPTED
    assert rows[0].check_status == CHECK_STATUS_OK
    validate_payload = transport.endpoint_calls[1][1]
    sent_mark = validate_payload["products"][0]["exemplars"][0]["marks"][0]["mark"]
    assert "\x1d" in sent_mark
    assert "\\u001d" in json.dumps(validate_payload)
    wb_put.assert_not_awaited()


@pytest.mark.asyncio
async def test_ozon_marking_targets_its_exact_multi_product_position(
    db_session: AsyncSession,
) -> None:
    """TC-S03-OZON-032: a code for position two is never sent as position one."""
    order, _ = await _sync_ozon_posting_with_products(
        db_session,
        positions=[
            {"sku": 4001, "offer_id": "offer-1", "name": "Футболка", "quantity": 1},
            {"sku": 4002, "offer_id": "offer-2", "name": "Носки", "quantity": 1},
        ],
    )
    second_position = order.product_positions[1]
    marking = FbsOrderMarking(
        tenant_id=order.tenant_id,
        order_id=order.id,
        order_product_id=second_position.id,
        kind="sgtin",
        value="010460123456789021SECOND",
    )
    db_session.add(marking)
    await db_session.flush()
    transport = FakeMarketplaceTransport(
        endpoint_responses={
            "/v6/fbs/posting/product/exemplar/create-or-get": {
                "posting_number": order.external_order_id,
                "products": [
                    {"product_id": 4001, "exemplars": [{"exemplar_id": 81}]},
                    {"product_id": 4002, "exemplars": [{"exemplar_id": 82}]},
                ],
            },
            "/v5/fbs/posting/product/exemplar/validate": {
                "products": [{"product_id": 4002, "valid": True, "exemplars": []}]
            },
            "/v6/fbs/posting/product/exemplar/set": {},
            "/v5/fbs/posting/product/exemplar/status": {
                "posting_number": order.external_order_id,
                "status": "ship_available",
                "products": [],
            },
        }
    )

    await submit_marking(
        db_session,
        order=order,
        marking=marking,
        provider=OzonMarketplaceProvider(transport=transport),
        client_id="client-id",
        api_key="api-key",
    )

    validate_payload = transport.endpoint_calls[1][1]
    set_payload = transport.endpoint_calls[2][1]
    assert validate_payload["products"][0]["product_id"] == 4002
    assert set_payload["products"][0]["product_id"] == 4002


@pytest.mark.asyncio
async def test_ozon_scanner_binds_every_required_code_without_wb_path(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """TC-S03-OZON-033: scanner maps positions and quantity while WB stays untouched."""
    first_gtin = "04601234567890"
    second_gtin = "04601234567801"
    order, products = await _sync_ozon_posting_with_products(
        db_session,
        positions=[
            {
                "sku": 4001,
                "offer_id": "offer-1",
                "name": "Футболка",
                "quantity": 1,
                "barcode": first_gtin,
            },
            {
                "sku": 4002,
                "offer_id": "offer-2",
                "name": "Носки",
                "quantity": 2,
                "barcode": second_gtin,
            },
        ],
    )
    assert order.warehouse_id is not None
    location = StorageLocation(
        tenant_id=order.tenant_id,
        warehouse_id=order.warehouse_id,
        code="PACK-OZON",
        barcode="PACK-OZON",
    )
    task = PackagingTask(
        tenant_id=order.tenant_id,
        warehouse_id=order.warehouse_id,
        status="in_progress",
        document_number="PK-OZON-1",
    )
    supply = FbsSupply(
        tenant_id=order.tenant_id,
        seller_id=order.seller_id,
        warehouse_id=order.warehouse_id,
        marketplace="ozon",
        name="Ozon marking",
        status=FBS_SUPPLY_STATUS_ASSEMBLING,
        delivery_type=FBS_DELIVERY_TYPE_WAREHOUSE_SC,
    )
    db_session.add_all([location, task, supply])
    await db_session.flush()
    lines = [
        PackagingTaskLine(
            task_id=task.id,
            product_id=product.id,
            storage_location_id=location.id,
            qty_total=quantity,
        )
        for product, quantity in zip(products, [1, 2], strict=True)
    ]
    db_session.add_all(lines)
    supply.packaging_task_id = task.id
    order.supply_id = supply.id
    order.required_meta_json = ["sgtin"]
    await db_session.commit()

    transport = FakeMarketplaceTransport(
        endpoint_responses={
            "/v6/fbs/posting/product/exemplar/create-or-get": {
                "posting_number": order.external_order_id,
                "products": [
                    {"product_id": 4001, "exemplars": [{"exemplar_id": 81}]},
                    {
                        "product_id": 4002,
                        "exemplars": [{"exemplar_id": 82}, {"exemplar_id": 83}],
                    },
                ],
            },
            "/v5/fbs/posting/product/exemplar/validate": {
                "products": [
                    {"product_id": 4001, "valid": True, "exemplars": []},
                    {"product_id": 4002, "valid": True, "exemplars": []},
                ]
            },
            "/v6/fbs/posting/product/exemplar/set": {},
            "/v5/fbs/posting/product/exemplar/status": {
                "posting_number": order.external_order_id,
                "status": "ship_available",
                "products": [],
            },
        }
    )
    provider = OzonMarketplaceProvider(transport=transport)
    real_commit = ozon_kiz_svc.commit_ozon_kiz

    async def injected_commit(*args: object) -> None:
        await real_commit(*args, provider=provider)  # type: ignore[arg-type]

    monkeypatch.setattr(kiz_svc, "commit_ozon", injected_commit)
    wb_token = AsyncMock(side_effect=AssertionError("WB token must not be read for Ozon"))
    wb_delete = AsyncMock(side_effect=AssertionError("WB marking must not be deleted for Ozon"))
    monkeypatch.setattr(marking_svc, "require_marketplace_token", wb_token)
    monkeypatch.setattr(kiz_svc, "_delete_sgtin_from_wb", wb_delete)
    values = [
        f"01{first_gtin}21FIRST",
        f"01{second_gtin}21SECOND-A",
        f"01{second_gtin}21SECOND-B",
    ]
    for value in values:
        await kiz_svc._commit_one_kiz_pair(
            db_session,
            order.tenant_id,
            None,
            kiz_svc.FbsKizCommitPair(order.id, value, False),
            AsyncMock(),
        )

    markings = list(
        (
            await db_session.execute(
                select(FbsOrderMarking)
                .where(FbsOrderMarking.order_id == order.id)
                .order_by(FbsOrderMarking.created_at, FbsOrderMarking.id)
            )
        )
        .scalars()
        .all()
    )
    assert {
        position.id: sum(marking.order_product_id == position.id for marking in markings)
        for position in order.product_positions
    } == {
        order.product_positions[0].id: 1,
        order.product_positions[1].id: 2,
    }
    assert sorted(marking.meta_details_json["exemplar_id"] for marking in markings) == [81, 82, 83]
    assert [line.qty_marking_external for line in lines] == [1, 2]
    assert order.metadata_delivery_allowed is True

    # TC-S03-OZON-034: лента расхода КМ должна показывать номер упаковочного
    # документа, а не `wb_order_id` — у заказа Ozon это синтезированный
    # отрицательный хеш номера отправления, а не читаемый номер документа.
    events = list(
        (
            await db_session.execute(
                select(MarkingCodeEvent).where(
                    MarkingCodeEvent.code_id.in_([marking.marking_code_id for marking in markings])
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(events) == 3
    assert all(event.document_number == task.document_number for event in events)
    assert all(event.document_number != str(order.wb_order_id) for event in events)

    supply.status = FBS_SUPPLY_STATUS_PACKED
    order.status = FBS_ORDER_STATUS_PACKED
    tenant_id = order.tenant_id
    supply_id = supply.id
    await db_session.commit()
    async with SessionLocal() as preflight_session:
        preflight = await shipment_svc.preflight_delivery(
            preflight_session,
            tenant_id,
            supply_id,
            AsyncMock(),
            actor_user_id=None,
        )
    assert preflight.can_deliver is True
    assert all(check.code != "marking_not_allowed" for check in preflight.checks)

    first_position_id = markings[0].order_product_id
    markings[0].order_product_id = None
    await db_session.commit()
    async with SessionLocal() as preflight_session:
        incomplete = await shipment_svc.preflight_delivery(
            preflight_session,
            tenant_id,
            supply_id,
            AsyncMock(),
            actor_user_id=None,
        )
    assert incomplete.can_deliver is True
    assert any(
        check.code == "marking_not_allowed" and not check.ok and check.severity == "warning"
        for check in incomplete.checks
    )

    markings[0].order_product_id = first_position_id
    first_details = dict(markings[0].meta_details_json or {})
    markings[0].meta_details_json = {**first_details, "status": "ship_not_available"}
    await db_session.commit()
    async with SessionLocal() as preflight_session:
        blocked = await shipment_svc.preflight_delivery(
            preflight_session,
            tenant_id,
            supply_id,
            AsyncMock(),
            actor_user_id=None,
        )
    assert blocked.can_deliver is True
    assert any(
        check.code == "marking_not_allowed" and not check.ok and check.severity == "warning"
        for check in blocked.checks
    )
    wb_token.assert_not_awaited()
    wb_delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_ozon_preflight_warns_about_required_marking_without_product_positions(
    db_session: AsyncSession,
) -> None:
    tenant, _, _, _, order, supply = await _seed_ozon_supply_case(db_session, packed=True)
    assert supply is not None
    order.required_meta_json = ["sgtin"]
    db_session.add(
        FbsOrderMarking(
            tenant_id=tenant.id,
            order_id=order.id,
            kind="sgtin",
            value="legacy-code",
            meta_status=META_STATUS_ACCEPTED,
            check_status=CHECK_STATUS_OK,
            meta_details_json={"status": "ship_available", "exemplar_id": 81},
        )
    )
    await db_session.commit()

    result = await shipment_svc.preflight_delivery(
        db_session,
        tenant.id,
        supply.id,
        AsyncMock(),
        actor_user_id=None,
    )

    assert result.can_deliver is True
    assert any(
        check.code == "marking_not_allowed" and not check.ok and check.severity == "warning"
        for check in result.checks
    )


@pytest.mark.asyncio
async def test_ozon_gate_requires_each_kind_and_rejects_duplicate_exemplar(
    db_session: AsyncSession,
) -> None:
    order, _ = await _sync_ozon_posting_with_products(
        db_session,
        positions=[{"sku": 4001, "offer_id": "offer-1", "name": "Товар", "quantity": 2}],
    )
    position = order.product_positions[0]
    order.required_meta_json = ["sgtin", "imei"]
    current_created_at = datetime.now(UTC)
    markings = [
        FbsOrderMarking(
            tenant_id=order.tenant_id,
            order_id=order.id,
            order_product_id=position.id,
            kind=kind,
            value=value,
            meta_status=META_STATUS_ACCEPTED,
            check_status=CHECK_STATUS_OK,
            meta_details_json={"status": "ship_available", "exemplar_id": 81},
            created_at=current_created_at,
        )
        for kind, value in [
            ("sgtin", "code-1"),
            ("sgtin", "code-2"),
            ("imei", "imei-1"),
            ("imei", "imei-2"),
        ]
    ]
    for index, marking in enumerate(markings):
        marking.meta_details_json = {
            "status": "ship_available",
            "exemplar_id": 81 + index % 2,
        }
    db_session.add_all(markings)
    await db_session.flush()
    assert marking_svc.compute_delivery_allowed(order, markings) is True

    duplicate = FbsOrderMarking(
        tenant_id=order.tenant_id,
        order_id=order.id,
        order_product_id=position.id,
        kind="sgtin",
        value="code-duplicate",
        meta_status=META_STATUS_ACCEPTED,
        check_status=CHECK_STATUS_OK,
        meta_details_json={"status": "ship_available", "exemplar_id": 82},
        created_at=current_created_at,
    )
    db_session.add(duplicate)
    await db_session.flush()
    assert marking_svc.compute_delivery_allowed(order, [*markings, duplicate]) is False


@pytest.mark.asyncio
async def test_ozon_status_sync_updates_only_current_rows_and_preserves_exemplars(
    db_session: AsyncSession,
) -> None:
    order, _ = await _sync_ozon_posting_with_products(
        db_session,
        positions=[{"sku": 4001, "offer_id": "offer-1", "name": "Товар", "quantity": 2}],
    )
    position = order.product_positions[0]
    order.required_meta_json = ["sgtin"]
    now = datetime.now(UTC)

    def marking(
        value: str,
        exemplar_id: int,
        *,
        created_at: datetime,
        meta_status: str = META_STATUS_ACCEPTED,
    ) -> FbsOrderMarking:
        return FbsOrderMarking(
            tenant_id=order.tenant_id,
            order_id=order.id,
            order_product_id=position.id,
            kind="sgtin",
            value=value,
            meta_status=meta_status,
            check_status=CHECK_STATUS_ERROR,
            meta_details_json={"status": "validation_in_process", "exemplar_id": exemplar_id},
            created_at=created_at,
        )

    historical = marking("old", 80, created_at=now - timedelta(minutes=2))
    current = [
        marking("current-1", 81, created_at=now - timedelta(seconds=2)),
        marking("current-2", 82, created_at=now - timedelta(seconds=1)),
    ]
    rejected = marking(
        "rejected",
        79,
        created_at=now - timedelta(minutes=3),
        meta_status=META_STATUS_REJECTED,
    )
    db_session.add_all([historical, *current, rejected])
    await db_session.commit()
    provider = OzonMarketplaceProvider(
        transport=FakeMarketplaceTransport(
            endpoint_responses={
                "/v5/fbs/posting/product/exemplar/status": {
                    "posting_number": order.external_order_id,
                    "status": "ship_available",
                    "products": [],
                }
            }
        )
    )

    await marking_svc.sync_order_marking_statuses(
        db_session,
        order.tenant_id,
        order.id,
        AsyncMock(),
        actor_user_id=None,
        ozon_provider=provider,
    )

    assert [row.meta_details_json["exemplar_id"] for row in current] == [81, 82]
    assert all(row.meta_details_json["status"] == "ship_available" for row in current)
    assert historical.meta_details_json == {
        "status": "validation_in_process",
        "exemplar_id": 80,
    }
    assert rejected.meta_status == META_STATUS_REJECTED
    assert rejected.meta_details_json == {
        "status": "validation_in_process",
        "exemplar_id": 79,
    }
    assert order.metadata_delivery_allowed is True


@pytest.mark.asyncio
async def test_ozon_negative_sync_does_not_fall_back_to_accepted_history(
    db_session: AsyncSession,
) -> None:
    order, _ = await _sync_ozon_posting_with_products(
        db_session,
        positions=[{"sku": 4001, "offer_id": "offer-1", "name": "Товар", "quantity": 1}],
    )
    position = order.product_positions[0]
    supply = FbsSupply(
        tenant_id=order.tenant_id,
        seller_id=order.seller_id,
        warehouse_id=order.warehouse_id,
        marketplace="ozon",
        name="Ozon negative sync",
        status=FBS_SUPPLY_STATUS_PACKED,
        delivery_type=FBS_DELIVERY_TYPE_WAREHOUSE_SC,
    )
    db_session.add(supply)
    await db_session.flush()
    order.supply_id = supply.id
    order.status = FBS_ORDER_STATUS_PACKED
    order.required_meta_json = ["sgtin"]
    now = datetime.now(UTC)
    historical = FbsOrderMarking(
        tenant_id=order.tenant_id,
        order_id=order.id,
        order_product_id=position.id,
        kind="sgtin",
        value="historical-accepted",
        meta_status=META_STATUS_ACCEPTED,
        check_status=CHECK_STATUS_OK,
        meta_details_json={"status": "ship_available", "exemplar_id": 80},
        created_at=now - timedelta(minutes=1),
    )
    current = FbsOrderMarking(
        tenant_id=order.tenant_id,
        order_id=order.id,
        order_product_id=position.id,
        kind="sgtin",
        value="current-negative",
        meta_status=META_STATUS_ACCEPTED,
        check_status=CHECK_STATUS_OK,
        meta_details_json={"status": "validation_in_process", "exemplar_id": 81},
        created_at=now,
    )
    db_session.add_all([historical, current])
    await db_session.commit()
    provider = OzonMarketplaceProvider(
        transport=FakeMarketplaceTransport(
            endpoint_responses={
                "/v5/fbs/posting/product/exemplar/status": {
                    "posting_number": order.external_order_id,
                    "status": "ship_not_available",
                    "products": [],
                }
            }
        )
    )

    for _ in range(2):
        await marking_svc.sync_order_marking_statuses(
            db_session,
            order.tenant_id,
            order.id,
            AsyncMock(),
            actor_user_id=None,
            ozon_provider=provider,
        )
        assert current.meta_status == META_STATUS_REJECTED
        assert current.meta_details_json == {
            "status": "ship_not_available",
            "exemplar_id": 81,
        }
        assert historical.meta_status == META_STATUS_ACCEPTED
        assert historical.meta_details_json == {
            "status": "ship_available",
            "exemplar_id": 80,
        }
        assert order.metadata_delivery_allowed is False

    await db_session.commit()
    async with SessionLocal() as preflight_session:
        preflight = await shipment_svc.preflight_delivery(
            preflight_session,
            order.tenant_id,
            supply.id,
            AsyncMock(),
            actor_user_id=None,
        )
    assert preflight.can_deliver is True
    assert any(
        check.code == "marking_not_allowed" and not check.ok and check.severity == "warning"
        for check in preflight.checks
    )


@pytest.mark.asyncio
async def test_ozon_marking_rejection_uses_existing_visible_status(
    db_session: AsyncSession,
) -> None:
    tenant, _, _, _, order, _ = await _seed_ozon_supply_case(db_session, packed=True)
    marking = FbsOrderMarking(
        tenant_id=tenant.id,
        order_id=order.id,
        kind="sgtin",
        value="bad-code",
    )
    db_session.add(marking)
    await db_session.flush()
    transport = FakeMarketplaceTransport(
        endpoint_responses={
            "/v6/fbs/posting/product/exemplar/create-or-get": {
                "posting_number": order.external_order_id,
                "products": [{"product_id": 3001, "exemplars": [{"exemplar_id": 82}]}],
            },
            "/v5/fbs/posting/product/exemplar/validate": {
                "products": [
                    {
                        "product_id": 3001,
                        "valid": False,
                        "error": "not_in_circulation",
                        "exemplars": [{"valid": False, "errors": ["not_in_circulation"]}],
                    }
                ]
            },
        }
    )

    with pytest.raises(marking_svc.FbsMarkingError, match="meta_validation_fail"):
        await marking_svc.attach_order_meta_to_wb_and_sync(
            db_session,
            tenant.id,
            order,
            marking,
            AsyncMock(),
            actor_user_id=None,
            ozon_provider=OzonMarketplaceProvider(transport=transport),
        )

    assert marking.meta_status == META_STATUS_REJECTED
    assert marking.check_status == CHECK_STATUS_ERROR
    assert "not_in_circulation" in (marking.reason or "")
    assert [call[0] for call in transport.endpoint_calls] == [
        "/v6/fbs/posting/product/exemplar/create-or-get",
        "/v5/fbs/posting/product/exemplar/validate",
    ]


@pytest.mark.asyncio
async def test_wb_background_marking_ignores_ozon_orders(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant, seller, _, _, order, supply = await _seed_ozon_supply_case(
        db_session,
        packed=True,
    )
    assert supply is not None
    supply.status = FBS_SUPPLY_STATUS_ASSEMBLING
    order.status = "assembling"
    await db_session.commit()
    forbidden = AsyncMock(side_effect=AssertionError("WB marking fetch must not receive Ozon"))
    monkeypatch.setattr(
        "app.services.wildberries_fbs_client.fetch_marketplace_orders_meta_batch",
        forbidden,
    )

    synced = await sync_marking_statuses_for_assembling_supplies(
        db_session,
        SellerPollTarget(tenant.id, seller.id, "wb"),
        AsyncMock(),
    )

    assert synced == 0
    forbidden.assert_not_awaited()


@pytest.mark.asyncio
async def test_wb_background_tracking_ignores_ozon_supplies(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant, seller, _, _, _, supply = await _seed_ozon_supply_case(
        db_session,
        packed=True,
    )
    assert supply is not None
    supply.status = FBS_SUPPLY_STATUS_IN_DELIVERY
    await db_session.commit()
    forbidden = AsyncMock(side_effect=AssertionError("WB tracking must not receive Ozon"))
    monkeypatch.setattr(tracking_svc, "sync_supply_tracking", forbidden)

    result = await tracking_svc.sync_in_delivery_supplies(
        db_session,
        tenant.id,
        seller.id,
        AsyncMock(),
    )

    assert result.supplies_synced == 0
    assert result.orders_updated == 0
    forbidden.assert_not_awaited()


@pytest.mark.asyncio
async def test_ozon_labels_are_not_requested_while_the_live_transport_is_off(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Выключенный транспорт — это отказ, а не «этикетка не найдена в ответе Ozon».

    На локальном фейке список этикеток пуст, и без явной проверки рубильника
    оператор прочитал бы, что Ozon чего-то не вернул, — про Ozon, которого никто
    не спрашивал.
    """
    monkeypatch.setattr(settings, "ozon_live_api_enabled", False)
    tenant, supply, order = await _ozon_supply_with_one_order(db_session)
    monkeypatch.setattr(
        print_asset_svc,
        "fetch_marketplace_order_stickers",
        AsyncMock(side_effect=AssertionError("WB fetch must not run for Ozon")),
    )
    monkeypatch.setattr(
        print_asset_svc,
        "build_ozon_provider",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("provider must not be built")),
    )

    batch = await print_asset_svc.request_supply_print_batch(
        db_session,
        tenant.id,
        supply.id,
        kind="order_sticker",
        order_ids=[order.id],
        retry_missing=False,
        http_client=AsyncMock(),
    )

    assert batch.ready == 0
    assert batch.failed == 1
    assert batch.order_errors[0].code == "ozon_live_labels_blocked"
    assert "не включён" in batch.order_errors[0].message
    await db_session.refresh(order)
    assert order.sticker_status == STICKER_STATUS_ERROR


async def _seed_ozon_scope_case(
    db_session: AsyncSession,
    *,
    published: bool,
    served: bool,
    delivery_method: dict[str, object] | None = None,
) -> tuple[Tenant, Seller, Warehouse, OzonMarketplaceProvider]:
    """Один продавец Ozon, один товар, один склад и одно отправление на него."""
    tenant = Tenant(name="Ozon scope", slug=f"ozon-scope-{uuid.uuid4().hex[:8]}")
    seller = Seller(tenant=tenant, name="Seller")
    warehouse = Warehouse(tenant=tenant, name="FBS", code=f"ozon-scope-{uuid.uuid4().hex[:8]}")
    product = Product(
        tenant=tenant,
        seller=seller,
        name="Product",
        sku_code=f"sku-{uuid.uuid4().hex[:8]}",
        fbs_stock_sync_enabled=published,
    )
    db_session.add_all([tenant, seller, warehouse, product])
    await db_session.flush()
    db_session.add_all(
        [
            MarketplaceAccount(
                tenant_id=tenant.id,
                seller_id=seller.id,
                marketplace="ozon",
                account_slot="primary",
                external_account_id="client-id",
                secret_encrypted=encrypt_secret("api-key"),
                is_active=True,
                validation_status="valid",
            ),
            ProductMarketplaceLink(
                tenant_id=tenant.id,
                seller_id=seller.id,
                product_id=product.id,
                marketplace="ozon",
                external_sku="ozon-sku-scope",
            ),
            FbsWarehouseBinding(
                tenant_id=tenant.id,
                seller_id=seller.id,
                marketplace="ozon",
                external_warehouse_id="1020005028840530",
                wb_warehouse_id=-4242,
                wms_warehouse_id=warehouse.id,
                is_active=True,
                served=served,
            ),
        ]
    )
    await db_session.commit()

    row: dict[str, object] = {
        "posting_number": "ozon-scope-1",
        "status": "awaiting_packaging",
        "sku": "ozon-sku-scope",
        "in_process_at": datetime.now(UTC).isoformat(),
        "delivery_method": delivery_method
        or {"id": 45409131, "name": "самостоятельно. В ПВЗ Ozon", "warehouse_id": 1020005028840530},
    }
    provider = OzonMarketplaceProvider(transport=FakeMarketplaceTransport(orders=[row]))
    return tenant, seller, warehouse, provider


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "published, served, expected_orders",
    [(True, True, 1), (False, True, 0), (True, False, 0)],
)
async def test_ozon_poll_takes_only_orders_whose_stock_we_publish(
    db_session: AsyncSession,
    published: bool,
    served: bool,
    expected_orders: int,
) -> None:
    """WMS-352: видим только заказы, по чьим товарам и складам выставлен остаток.

    Кабинет Ozon отдаёт все отправления продавца — в том числе те, что он
    собирает сам на другом складе. Своим считается ровно то, по чему остаток
    публикуем мы: обслуживаемый склад и товар с включённой публикацией. Правило
    то же, что у Wildberries, и отсев идёт там же — до записи в базу.
    """
    tenant, seller, _warehouse, provider = await _seed_ozon_scope_case(
        db_session, published=published, served=served
    )

    result = await ozon_sync_svc.sync_ozon_orders(
        db_session, tenant.id, seller.id, provider, AsyncMock()
    )

    orders = list(
        (await db_session.execute(select(FbsOrder).where(FbsOrder.tenant_id == tenant.id)))
        .scalars()
        .all()
    )
    assert len(orders) == expected_orders
    assert result["orders_created"] == expected_orders


@pytest.mark.asyncio
async def test_ozon_order_row_carries_its_delivery_route(db_session: AsyncSession) -> None:
    """WMS-358: колонка «Маршрут сдачи» у заказа Ozon заполнена методом доставки.

    Отгрузка Ozon создаётся по методу доставки, значит метод и есть маршрут.
    Справочника методов у Ozon нет — `/v1/delivery-method/list` объявлен
    устаревшим, — поэтому название берётся из самого отправления.
    """
    tenant, seller, _warehouse, provider = await _seed_ozon_scope_case(
        db_session, published=True, served=True
    )
    await ozon_sync_svc.sync_ozon_orders(db_session, tenant.id, seller.id, provider, AsyncMock())

    order = (
        await db_session.execute(select(FbsOrder).where(FbsOrder.tenant_id == tenant.id))
    ).scalar_one()
    assert (order.meta_details_json or {})["ozon_delivery_method_id"] == "45409131"

    page = await worklist_svc.fetch_worklist_page(db_session, tenant.id, seller_id=seller.id)

    assert [item["delivery_route"] for item in page.items] == ["самостоятельно. В ПВЗ Ozon"]


@pytest.mark.asyncio
async def test_ozon_order_route_falls_back_to_the_method_id(db_session: AsyncSession) -> None:
    """Без названия метода маршрут показывает его идентификатор, а не прочерк.

    Иначе заказы разных методов — то есть разных отгрузок — на экране выглядели
    бы одинаково, и оператор смешал бы их в одну.
    """
    tenant, seller, _warehouse, provider = await _seed_ozon_scope_case(
        db_session,
        published=True,
        served=True,
        delivery_method={"id": 45409131, "warehouse_id": 1020005028840530},
    )
    await ozon_sync_svc.sync_ozon_orders(db_session, tenant.id, seller.id, provider, AsyncMock())

    page = await worklist_svc.fetch_worklist_page(db_session, tenant.id, seller_id=seller.id)

    assert [item["delivery_route"] for item in page.items] == ["Метод доставки 45409131"]


@pytest.mark.asyncio
async def test_supply_creation_refuses_a_mixed_wb_and_ozon_selection(
    db_session: AsyncSession,
) -> None:
    """WMS-353: смешать заказы двух площадок в одну поставку нельзя.

    Проверка идёт до любого обращения к маркетплейсу, поэтому отказ виден на
    самом создании поставки, а не только в списке замечаний предпроверки.
    """
    tenant = Tenant(name="Mixed supply", slug=f"mixed-{uuid.uuid4().hex[:12]}")
    seller = Seller(tenant=tenant, name="Seller")
    warehouse = Warehouse(tenant=tenant, name="FBS", code=f"mixed-{uuid.uuid4().hex[:8]}")
    product = Product(
        tenant=tenant,
        seller=seller,
        name="Product",
        sku_code=f"sku-{uuid.uuid4().hex[:8]}",
    )
    db_session.add_all([tenant, seller, warehouse, product])
    await db_session.flush()
    now = datetime.now(UTC)
    orders = [
        FbsOrder(
            tenant_id=tenant.id,
            seller_id=seller.id,
            warehouse_id=warehouse.id,
            product_id=product.id,
            marketplace=marketplace,
            external_order_id=f"{marketplace}-mixed-1",
            wb_order_id=wb_order_id,
            wb_warehouse_id=11,
            mapping_status=MAPPING_STATUS_MAPPED,
            reserve_status=RESERVE_STATUS_RESERVED,
            created_at_wb=now,
            deadline_at=now + timedelta(days=1),
        )
        for marketplace, wb_order_id in (("wb", 991), ("ozon", 992))
    ]
    db_session.add_all(orders)
    await db_session.commit()

    with pytest.raises(supply_svc.FbsSupplyError) as raised:
        await supply_svc.create_supply_from_orders(
            db_session,
            tenant.id,
            name="Смешанная",
            order_ids=[orders[0].id, orders[1].id],
            planned_delivery_type=FBS_DELIVERY_TYPE_WAREHOUSE_SC,
            planned_destination=None,
            idempotency_key=str(uuid.uuid4()),
            http_client=AsyncMock(),
        )

    assert raised.value.code == "order_incompatible"
    assert raised.value.http_status == 409
    assert "different_marketplace" in raised.value.context["reasons"]


def test_existing_supply_never_accepts_an_order_of_another_marketplace() -> None:
    """Вторая дверь в поставку — добавление заказа к уже созданной — закрыта тоже.

    Здесь проверка строже, чем при создании: к поставке WB не привязывается
    заказ Ozon, а к поставке Ozon — вообще ничего, потому что состав отправления
    у Ozon определяет сам маркетплейс.
    """
    from app.services.fbs_supply_composition_service import supply_order_link_discrepancy

    now = datetime.now(UTC)
    tenant_id = uuid.uuid4()
    seller_id = uuid.uuid4()
    warehouse_id = uuid.uuid4()

    def _order(marketplace: str, wb_order_id: int) -> FbsOrder:
        return FbsOrder(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            seller_id=seller_id,
            warehouse_id=warehouse_id,
            marketplace=marketplace,
            wb_order_id=wb_order_id,
            wb_warehouse_id=11,
            created_at_wb=now,
            deadline_at=now + timedelta(days=1),
        )

    def _supply(marketplace: str) -> FbsSupply:
        return FbsSupply(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            seller_id=seller_id,
            warehouse_id=warehouse_id,
            marketplace=marketplace,
            status=FBS_SUPPLY_STATUS_ASSEMBLING,
            name="Поставка",
            delivery_type=FBS_DELIVERY_TYPE_WAREHOUSE_SC,
        )

    wb_supply = _supply("wb")
    ozon_supply = _supply("ozon")

    ozon_into_wb = supply_order_link_discrepancy(wb_supply, _order("ozon", 991), existing_orders=[])
    wb_into_ozon = supply_order_link_discrepancy(ozon_supply, _order("wb", 992), existing_orders=[])

    assert ozon_into_wb is not None
    assert ozon_into_wb.code == "different_marketplace"
    assert wb_into_ozon is not None
    assert wb_into_ozon.code == "different_marketplace"
