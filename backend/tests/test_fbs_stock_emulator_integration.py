"""TC-NEW-FBS-STOCK-017 / TC-NEW-FBS-STOCK-018: WMS ↔ WB emulator FBS stock cycle.

Real HTTP via httpx ASGITransport against in-process emulator (no MockTransport on both sides).
"""

from __future__ import annotations

import json
import sys
import time
import uuid
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any, cast

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from wb_emulator.db import reset_db_runtime
from wb_emulator.main import create_app as create_emulator_app
from wb_emulator.services.orders_store import DEFAULT_EMULATOR_WAREHOUSE_ID
from wb_emulator.settings import get_settings as get_emulator_settings

from app.core.settings import settings
from app.db.session import SessionLocal
from app.models.fbs_order import (
    MAPPING_STATUS_MAPPED,
    RESERVE_STATUS_RESERVED,
    FbsOrder,
    FbsOrderReservation,
)
from app.models.fbs_stock_sync_item import STOCK_SYNC_STATUS_CONFIRMED, FbsStockSyncItem
from app.models.marketplace_unload import MarketplaceUnloadLine, MarketplaceUnloadRequest
from app.models.marketplace_unload_reservation import MarketplaceUnloadReservation
from app.models.product import Product
from app.services import inventory_service
from app.services.fbs_autopoll_service import sync_seller_stocks
from app.services.sorting_location_service import get_or_create_sorting_location
from app.services.wb_marketplace_orders_service import sync_seller_orders

EMU_BASE = "http://emu"
EMU_TOKEN = "cycle-test-token"
EMU_SELLER_KEY = "cycle_seller"
EMU_ADMIN_TOKEN = "admin-cycle"
WB_WAREHOUSE_ID = DEFAULT_EMULATOR_WAREHOUSE_ID
CHRT_ID = 111001
WB_BARCODE = "2000000000011"
WB_NM_ID = 123456789
REPO_ROOT = _REPO_ROOT


@pytest_asyncio.fixture
async def emulator_stack(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncGenerator[httpx.AsyncClient, None]:
    """In-process WB emulator + WMS settings pointed at ASGI transport base URL."""
    db_path = tmp_path / "emu.sqlite"
    monkeypatch.setenv("WB_EMULATOR_DB_PATH", str(db_path))
    monkeypatch.setenv(
        "WB_EMULATOR_TOKEN_MAP",
        json.dumps({EMU_TOKEN: EMU_SELLER_KEY}),
    )
    monkeypatch.setenv("WB_EMULATOR_ADMIN_TOKEN", EMU_ADMIN_TOKEN)
    get_emulator_settings.cache_clear()
    reset_db_runtime()
    from wb_emulator.db import init_db

    init_db()

    emu_app = create_emulator_app()
    transport = ASGITransport(app=emu_app)

    monkeypatch.setattr(settings, "wildberries_marketplace_api_base", EMU_BASE)
    monkeypatch.setattr(settings, "e2e_mock_wb_marketplace_orders", False)

    async def noop_wb_mp_sync(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr(
        "app.services.wb_mp_warehouse_service.run_wb_mp_warehouses_sync_task",
        noop_wb_mp_sync,
    )

    class _EmuAsyncClient(httpx.AsyncClient):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            if "transport" not in kwargs:
                kwargs["transport"] = transport
                kwargs.setdefault("base_url", EMU_BASE)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", _EmuAsyncClient)

    async with _EmuAsyncClient() as client:
        yield client

    reset_db_runtime()
    get_emulator_settings.cache_clear()


async def _register_ff_admin(async_client: AsyncClient) -> tuple[dict[str, str], str]:
    suffix = str(time.time_ns())
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": f"Emu cycle {suffix}",
            "slug": f"emu-cycle-{suffix}",
            "admin_email": f"emu-cycle-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200, reg.text
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    return headers, suffix


async def _setup_seller_with_token(
    async_client: AsyncClient,
    headers: dict[str, str],
    suffix: str,
) -> tuple[str, str]:
    seller = await async_client.post(
        "/sellers", headers=headers, json={"name": f"Seller {suffix}"}
    )
    assert seller.status_code in (200, 201), seller.text
    seller_id = seller.json()["id"]
    tok = await async_client.patch(
        f"/integrations/wildberries/sellers/{seller_id}/tokens",
        headers=headers,
        json={
            "supplies_api_token": EMU_TOKEN,
            "marketplace_api_token": EMU_TOKEN,
        },
    )
    assert tok.status_code == 200, tok.text
    warehouse = await async_client.post(
        "/warehouses",
        headers=headers,
        json={"name": "FBS WH", "code": f"fbs-{suffix[-8:]}"},
    )
    assert warehouse.status_code in (200, 201), warehouse.text
    return seller_id, warehouse.json()["id"]


async def _create_binding(
    async_client: AsyncClient,
    headers: dict[str, str],
    seller_id: str,
    wb_warehouse_id: int,
    wms_warehouse_id: str,
) -> None:
    resp = await async_client.put(
        f"/operations/fbs-sellers/{seller_id}/warehouse-bindings/{wb_warehouse_id}",
        headers=headers,
        json={"wms_warehouse_id": wms_warehouse_id, "stock_sync_enabled": True},
    )
    assert resp.status_code == 200, resp.text


async def _emulator_read_stock(
    emu_client: httpx.AsyncClient,
    chrt_id: int,
    *,
    warehouse_id: int = WB_WAREHOUSE_ID,
) -> int:
    response = await emu_client.post(
        f"/api/v3/stocks/{warehouse_id}",
        headers={"Authorization": EMU_TOKEN},
        json={"chrtIds": [chrt_id]},
    )
    assert response.status_code == 200, response.text
    stocks = response.json().get("stocks", [])
    for row in stocks:
        if int(row["chrtId"]) == chrt_id:
            return int(row["amount"])
    return 0


async def _admin_purchase(
    emu_client: httpx.AsyncClient,
    count: int,
    *,
    chrt_id: int = CHRT_ID,
) -> dict[str, Any]:
    response = await emu_client.post(
        f"/__admin/orders?seller={EMU_SELLER_KEY}&count={count}&chrt_id={chrt_id}",
        headers={"X-Admin-Token": EMU_ADMIN_TOKEN},
    )
    assert response.status_code == 200, response.text
    return cast(dict[str, Any], response.json())


# TC-NEW-FBS-STOCK-018
def test_prod_compose_has_no_wb_emulator() -> None:
    """Prod compose must not reference wb-emulator or emulator marketplace base URL."""
    prod = (REPO_ROOT / "docker-compose.prod.yml").read_text(encoding="utf-8")
    lowered = prod.lower()
    assert "wb-emulator" not in lowered
    assert "wb_emulator" not in lowered
    assert "wildberries_marketplace_api_base" not in lowered.replace("_", "")


# TC-NEW-FBS-STOCK-017
@pytest.mark.asyncio
async def test_wms_emulator_fbs_stock_full_cycle(
    async_client: AsyncClient,
    emulator_stack: httpx.AsyncClient,
) -> None:
    """Publish 1 → purchase → intake reserves 1 → publish 0; FBO on other WH ignored."""
    emu_client = emulator_stack
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, fbs_wh_id = await _setup_seller_with_token(async_client, headers, suffix)
    await _create_binding(
        async_client, headers, seller_id, WB_WAREHOUSE_ID, fbs_wh_id
    )

    # Second warehouse for FBO reserve isolation (different physical pool).
    fbo_wh = await async_client.post(
        "/warehouses",
        headers=headers,
        json={"name": "FBO WH", "code": f"fbo-{suffix[-8:]}"},
    )
    assert fbo_wh.status_code in (200, 201), fbo_wh.text
    fbo_wh_id = fbo_wh.json()["id"]

    location = await async_client.post(
        f"/warehouses/{fbs_wh_id}/locations",
        headers=headers,
        json={"code": f"CELL-{suffix[-6:]}"},
    )
    assert location.status_code in (200, 201), location.text
    storage_loc_id = location.json()["id"]

    product = await async_client.post(
        "/products",
        headers=headers,
        json={
            "name": "Emu cycle product",
            "sku_code": f"EMU-{suffix}",
            "seller_id": seller_id,
            "wb_barcode": WB_BARCODE,
        },
    )
    assert product.status_code in (200, 201), product.text
    product_id = uuid.UUID(product.json()["id"])

    async with SessionLocal() as session:
        row = await session.get(Product, product_id)
        assert row is not None
        tenant_id = row.tenant_id
        row.wb_chrt_id = CHRT_ID
        row.wb_nm_id = WB_NM_ID
        row.wb_barcode = WB_BARCODE
        await session.commit()

        await get_or_create_sorting_location(session, tenant_id, uuid.UUID(fbs_wh_id))
        await inventory_service.record_movement_and_adjust_balance(
            session,
            tenant_id=tenant_id,
            product_id=product_id,
            storage_location_id=uuid.UUID(storage_loc_id),
            quantity_delta=1,
            movement_type="inbound_intake",
        )

        unload = MarketplaceUnloadRequest(
            tenant_id=tenant_id,
            warehouse_id=uuid.UUID(fbo_wh_id),
            seller_id=uuid.UUID(seller_id),
            status="collecting",
            ff_modified=False,
            has_discrepancy=False,
        )
        session.add(unload)
        await session.flush()
        unload_line = MarketplaceUnloadLine(
            request_id=unload.id,
            product_id=product_id,
            quantity=50,
        )
        session.add(unload_line)
        await session.flush()
        session.add(
            MarketplaceUnloadReservation(
                tenant_id=tenant_id,
                marketplace_unload_line_id=unload_line.id,
                product_id=product_id,
                warehouse_id=uuid.UUID(fbo_wh_id),
                quantity=50,
            )
        )
        await session.commit()

    seller_uuid = uuid.UUID(seller_id)

    async with SessionLocal() as session:
        stock_result = await sync_seller_stocks(
            session, tenant_id, seller_uuid, emu_client, wb_warehouse_id=WB_WAREHOUSE_ID
        )
    assert stock_result.products_confirmed == 1
    assert stock_result.errors == 0
    assert await _emulator_read_stock(emu_client, CHRT_ID) == 1

    purchase = await _admin_purchase(emu_client, 2)
    assert purchase["created"] == 1
    assert purchase["rejected_no_stock"] == 1
    assert len(purchase["orders"]) == 1
    assert await _emulator_read_stock(emu_client, CHRT_ID) == 0

    async with SessionLocal() as session:
        intake = await sync_seller_orders(session, tenant_id, seller_uuid, emu_client)
    assert intake["orders_created"] >= 1

    async with SessionLocal() as session:
        order = (
            await session.execute(
                select(FbsOrder).where(
                    FbsOrder.tenant_id == tenant_id,
                    FbsOrder.seller_id == seller_uuid,
                )
            )
        ).scalar_one()
        assert order.wb_warehouse_id == WB_WAREHOUSE_ID
        assert str(order.warehouse_id) == fbs_wh_id
        assert order.mapping_status == MAPPING_STATUS_MAPPED
        assert order.reserve_status == RESERVE_STATUS_RESERVED
        assert order.product_id == product_id

        reserve_qty = await session.scalar(
            select(func.coalesce(func.sum(FbsOrderReservation.quantity), 0)).where(
                FbsOrderReservation.fbs_order_id == order.id
            )
        )
        assert int(reserve_qty or 0) == 1

        stock_result2 = await sync_seller_stocks(
            session, tenant_id, seller_uuid, emu_client, wb_warehouse_id=WB_WAREHOUSE_ID
        )
        sync_item = (
            await session.execute(
                select(FbsStockSyncItem).where(
                    FbsStockSyncItem.chrt_id == CHRT_ID,
                    FbsStockSyncItem.status == STOCK_SYNC_STATUS_CONFIRMED,
                )
            )
        ).scalar_one()
        assert sync_item.last_confirmed_amount == 0

    assert stock_result2.products_confirmed >= 1
    assert await _emulator_read_stock(emu_client, CHRT_ID) == 0

    # Manual API path uses same httpx→emulator wiring (patched AsyncClient).
    api_sync = await async_client.post(
        f"/operations/fbs-sellers/{seller_id}/stocks/sync",
        headers=headers,
        json={"wb_warehouse_id": WB_WAREHOUSE_ID},
    )
    assert api_sync.status_code == 200, api_sync.text
    assert api_sync.json()["products_confirmed"] >= 1
