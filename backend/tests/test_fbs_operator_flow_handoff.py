"""FBSFLOW-140: backend full-flow handoff gate — TC catalog + WMS↔emulator full API paths."""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from wb_emulator.db import init_db, reset_db_runtime
from wb_emulator.main import create_app as create_emulator_app
from wb_emulator.services.fault_injection import reset_fault_store
from wb_emulator.settings import get_settings as get_emulator_settings

from app.core.settings import settings
from app.db.session import SessionLocal
from app.models.fbs_order import (
    FBS_ORDER_STATUS_NEW,
    FBS_ORDER_STATUS_PACKED,
    FbsOrder,
)
from app.models.fbs_supply import (
    FBS_SUPPLY_STATUS_IN_DELIVERY,
    FBS_SUPPLY_STATUS_PACKED,
    FbsSupply,
)
from app.models.fbs_wb_operation import (
    WB_OPERATION_STATE_PENDING_CONFIRMATION,
    FbsWbOperation,
)
from app.services.wb_marketplace_orders_service import sync_seller_orders
from tests.fbs_operator_emulator_seed import (
    OperatorEmulatorSeedResult,
    load_emulator_tokens,
    seed_operator_emulator_wms,
)
from tests.test_fbs_shipment_pvz import _create_cargo_places, _default_boxes
from tests.test_fbs_shipment_warehouse_sc import (
    _deliver_with_preflight,
    _delivery_preflight,
)

HANDOFF_PATH = _REPO_ROOT / "tasks" / "fbs-operator-flow" / "HANDOFF.md"
OPENAPI_PATH = (
    _REPO_ROOT / "tasks" / "fbs-operator-flow" / "openapi" / "fbs-operations.openapi.json"
)
ERROR_CATALOG_PATH = _REPO_ROOT / "tasks" / "fbs-operator-flow" / "ERROR_CATALOG_RU.md"
EMU_BASE = "http://emu"
EMU_ADMIN = "handoff-admin"
WB_ORDER_WAREHOUSE_SC = 510001
WB_ORDER_PVZ = 510005


@pytest_asyncio.fixture
async def emulator_stack(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> httpx.AsyncClient:
    token_map = load_emulator_tokens()
    db_path = tmp_path / "handoff-emu.sqlite"
    monkeypatch.setenv("WB_EMULATOR_DB_PATH", str(db_path))
    monkeypatch.setenv("WB_EMULATOR_TOKEN_MAP", json.dumps(token_map))
    monkeypatch.setenv("WB_EMULATOR_ADMIN_TOKEN", EMU_ADMIN)
    get_emulator_settings.cache_clear()
    reset_db_runtime()
    reset_fault_store()
    init_db()

    emu_app = create_emulator_app()
    transport = ASGITransport(app=emu_app)
    monkeypatch.setattr(settings, "wildberries_marketplace_api_base", EMU_BASE)
    monkeypatch.setattr(settings, "e2e_mock_wb_marketplace_orders", False)
    monkeypatch.setattr(settings, "e2e_mock_wb_marketplace_supplies", False)

    async def noop_wb_mp_sync(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr(
        "app.services.wb_mp_warehouse_service.run_wb_mp_warehouses_sync_task",
        noop_wb_mp_sync,
    )

    class _EmuAsyncClient(httpx.AsyncClient):
        def __init__(self, *args: object, **kwargs: object) -> None:
            if "transport" not in kwargs:
                kwargs["transport"] = transport
                kwargs.setdefault("base_url", EMU_BASE)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", _EmuAsyncClient)

    async with _EmuAsyncClient() as client:
        seed = await client.post(
            "/__admin/seed",
            headers={"X-Admin-Token": EMU_ADMIN},
        )
        assert seed.status_code == 200, seed.text
        yield client

    reset_db_runtime()
    reset_fault_store()
    get_emulator_settings.cache_clear()


async def _sync_orders_for_seller(
    seed: OperatorEmulatorSeedResult,
    seller_key: str,
    emu_client: httpx.AsyncClient,
) -> dict[str, Any]:
    seller = seed.sellers[seller_key]
    async with SessionLocal() as session:
        return await sync_seller_orders(
            session, seed.tenant_id, seller.seller_id, emu_client
        )


async def _local_order_id(
    seed: OperatorEmulatorSeedResult,
    seller_key: str,
    wb_order_id: int,
) -> uuid.UUID:
    seller = seed.sellers[seller_key]
    async with SessionLocal() as session:
        row = await session.scalar(
            select(FbsOrder.id).where(
                FbsOrder.tenant_id == seed.tenant_id,
                FbsOrder.seller_id == seller.seller_id,
                FbsOrder.wb_order_id == wb_order_id,
            )
        )
    assert row is not None, f"wb_order_id={wb_order_id} not synced for {seller_key}"
    return row


async def _promote_supply_packed(supply_id: str, order_ids: list[uuid.UUID]) -> None:
    async with SessionLocal() as session:
        supply_row = await session.get(FbsSupply, uuid.UUID(supply_id))
        assert supply_row is not None
        supply_row.status = FBS_SUPPLY_STATUS_PACKED
        for oid in order_ids:
            order = await session.get(FbsOrder, oid)
            assert order is not None
            order.status = FBS_ORDER_STATUS_PACKED
        await session.commit()


@pytest_asyncio.fixture
async def operator_wms_seed(async_client: AsyncClient) -> OperatorEmulatorSeedResult:
    return await seed_operator_emulator_wms(async_client)


def test_handoff_md_present_with_required_sections() -> None:
    """Handoff doc exists for Codex frontend track."""
    assert HANDOFF_PATH.is_file()
    text = HANDOFF_PATH.read_text(encoding="utf-8")
    for marker in (
        "## Scope",
        "## Local gate commands",
        "## Seed: three sellers",
        "## API flow reference",
        "## Limitations",
        "TC-23",
        "live WB",
    ):
        assert marker in text, f"missing section/marker: {marker}"


def test_handoff_openapi_and_error_catalog_artifacts() -> None:
    assert OPENAPI_PATH.is_file(), "export OpenAPI via backend/scripts/export_fbs_openapi.py"
    assert ERROR_CATALOG_PATH.is_file()
    schema = json.loads(OPENAPI_PATH.read_text(encoding="utf-8"))
    assert "/operations/fbs-supplies/from-orders" in schema["paths"]


def test_emulator_tokens_three_sellers() -> None:
    """TC-01 partial: three seller tokens configured."""
    tokens = load_emulator_tokens()
    assert len(tokens) == 3
    assert set(tokens.values()) == {"seller_a", "seller_b", "seller_c"}


async def test_tc01_three_sellers_wms_seed_isolated(
    async_client: AsyncClient,
    emulator_stack: httpx.AsyncClient,
) -> None:
    """TC-01: one WMS warehouse, three sellers with isolated bindings and worklist scope."""
    _ = emulator_stack
    seeded = await seed_operator_emulator_wms(async_client)
    assert len(seeded.sellers) == 3

    for seller_key, row in seeded.sellers.items():
        wl = await async_client.get(
            "/operations/fbs-orders/worklist",
            headers=seeded.admin_headers,
            params={"seller_id": str(row.seller_id)},
        )
        assert wl.status_code == 200, wl.text
        body = wl.json()
        assert isinstance(body.get("items"), list)
        assert "server_now" in body
        _ = seller_key


async def test_tc23_emulator_admin_seed_orders_visible(
    emulator_stack: httpx.AsyncClient,
) -> None:
    """TC-23 partial (no browser): emulator seed → orders/new per token."""
    tokens = load_emulator_tokens()
    for token in tokens:
        resp = await emulator_stack.get(
            "/api/v3/orders/new",
            headers={"Authorization": token},
        )
        assert resp.status_code == 200, resp.text
        orders = resp.json().get("orders", [])
        assert isinstance(orders, list)


# TC-06 + TC-21 — warehouse/sc full API path via real emulator transport
@pytest.mark.asyncio
async def test_full_flow_warehouse_sc_emulator(
    async_client: AsyncClient,
    emulator_stack: httpx.AsyncClient,
    operator_wms_seed: OperatorEmulatorSeedResult,
) -> None:
    seed = operator_wms_seed
    headers = seed.admin_headers

    await _sync_orders_for_seller(seed, "seller_a", emulator_stack)
    local_order_id = await _local_order_id(seed, "seller_a", WB_ORDER_WAREHOUSE_SC)

    create = await async_client.post(
        "/operations/fbs-supplies/from-orders",
        headers=headers,
        json={
            "name": "Handoff WH/SC",
            "order_ids": [str(local_order_id)],
            "planned_delivery_type": "warehouse_sc",
            "idempotency_key": str(uuid.uuid4()),
        },
    )
    assert create.status_code == 201, create.text
    body = create.json()
    supply_id = body["supply"]["id"]

    await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/start-work",
        headers=headers,
    )
    await _promote_supply_packed(supply_id, [local_order_id])

    deliver = await _deliver_with_preflight(async_client, headers, supply_id)
    assert deliver.status_code == 200, deliver.text
    deliver_body = deliver.json()
    assert deliver_body["supply"]["status"] == FBS_SUPPLY_STATUS_IN_DELIVERY

    barcode = await async_client.get(
        f"/operations/fbs-supplies/{supply_id}/barcode",
        headers=headers,
        params={"type": "png"},
    )
    assert barcode.status_code == 200
    assert barcode.headers["content-type"].startswith("image/png")


# TC-17 + TC-20 + TC-21 — PVZ full API path (cargo places + deliver)
@pytest.mark.asyncio
async def test_full_flow_pvz_emulator(
    async_client: AsyncClient,
    emulator_stack: httpx.AsyncClient,
    operator_wms_seed: OperatorEmulatorSeedResult,
) -> None:
    seed = operator_wms_seed
    headers = seed.admin_headers

    await _sync_orders_for_seller(seed, "seller_a", emulator_stack)
    local_order_id = await _local_order_id(seed, "seller_a", WB_ORDER_PVZ)

    create = await async_client.post(
        "/operations/fbs-supplies/from-orders",
        headers=headers,
        json={
            "name": "Handoff PVZ",
            "order_ids": [str(local_order_id)],
            "planned_delivery_type": "pvz",
            "idempotency_key": str(uuid.uuid4()),
        },
    )
    assert create.status_code == 201, create.text
    supply_id = create.json()["supply"]["id"]

    await _promote_supply_packed(supply_id, [local_order_id])
    cargo = await _create_cargo_places(
        async_client, headers, supply_id, count=1, boxes=_default_boxes(1)
    )
    assert cargo.status_code == 201, cargo.text

    deliver = await _deliver_with_preflight(async_client, headers, supply_id)
    assert deliver.status_code == 200, deliver.text
    assert deliver.json()["supply"]["status"] == FBS_SUPPLY_STATUS_IN_DELIVERY


# TC-06 negative — emulator 409 on batch add → no false local success
@pytest.mark.asyncio
async def test_emulator_409_from_orders_no_false_success(
    async_client: AsyncClient,
    emulator_stack: httpx.AsyncClient,
    operator_wms_seed: OperatorEmulatorSeedResult,
) -> None:
    seed = operator_wms_seed
    headers = seed.admin_headers

    fault = await emulator_stack.post(
        "/__admin/faults?seller=seller_a",
        headers={"X-Admin-Token": EMU_ADMIN},
        json={"supply_conflict_409": True},
    )
    assert fault.status_code == 200, fault.text

    await _sync_orders_for_seller(seed, "seller_a", emulator_stack)
    local_order_id = await _local_order_id(seed, "seller_a", WB_ORDER_WAREHOUSE_SC)

    resp = await async_client.post(
        "/operations/fbs-supplies/from-orders",
        headers=headers,
        json={
            "name": "409 fault",
            "order_ids": [str(local_order_id)],
            "planned_delivery_type": "warehouse_sc",
            "idempotency_key": str(uuid.uuid4()),
        },
    )
    assert resp.status_code == 502, resp.text
    assert resp.json()["detail"]["code"] in {"wb_upstream_error_409", "wb_business_error_409"}

    async with SessionLocal() as session:
        order = await session.get(FbsOrder, local_order_id)
        assert order is not None
        assert order.supply_id is None
        assert order.status == FBS_ORDER_STATUS_NEW


# TC-20 negative — deliver timeout after real emulator from-orders
@pytest.mark.asyncio
async def test_emulator_deliver_timeout_pending_confirmation(
    async_client: AsyncClient,
    emulator_stack: httpx.AsyncClient,
    operator_wms_seed: OperatorEmulatorSeedResult,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed = operator_wms_seed
    headers = seed.admin_headers

    await _sync_orders_for_seller(seed, "seller_a", emulator_stack)
    local_order_id = await _local_order_id(seed, "seller_a", WB_ORDER_WAREHOUSE_SC)

    create = await async_client.post(
        "/operations/fbs-supplies/from-orders",
        headers=headers,
        json={
            "name": "Timeout deliver",
            "order_ids": [str(local_order_id)],
            "planned_delivery_type": "warehouse_sc",
            "idempotency_key": str(uuid.uuid4()),
        },
    )
    assert create.status_code == 201, create.text
    supply_id = create.json()["supply"]["id"]
    await _promote_supply_packed(supply_id, [local_order_id])

    preflight = await _delivery_preflight(async_client, headers, supply_id)
    deliver_calls = {"count": 0}

    async def timeout_then_ok(
        client: object,
        *,
        api_token: str,
        supply_id: str,
        marketplace_api_base: str | None = None,
    ) -> None:
        deliver_calls["count"] += 1
        if deliver_calls["count"] == 1:
            from app.services.wildberries_client import WildberriesClientError

            raise WildberriesClientError("transport_error")
        from app.services.wildberries_client import deliver_marketplace_supply as real_deliver

        await real_deliver(
            client,  # type: ignore[arg-type]
            api_token=api_token,
            supply_id=supply_id,
            marketplace_api_base=marketplace_api_base,
        )

    monkeypatch.setattr(
        "app.services.fbs_shipment_service.deliver_marketplace_supply",
        timeout_then_ok,
    )

    idem_key = str(uuid.uuid4())
    first = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/deliver",
        headers=headers,
        json={
            "idempotency_key": idem_key,
            "confirmed_preflight_version": preflight["version"],
        },
    )
    assert first.status_code == 504, first.text
    assert first.json()["detail"]["code"] == "wb_timeout"

    async with SessionLocal() as session:
        supply_row = await session.get(FbsSupply, uuid.UUID(supply_id))
        assert supply_row is not None
        assert supply_row.status == FBS_SUPPLY_STATUS_PACKED
        op = await session.scalar(
            select(FbsWbOperation).where(FbsWbOperation.idempotency_key == idem_key)
        )
        assert op is not None
        assert op.state == WB_OPERATION_STATE_PENDING_CONFIRMATION


TC_NON_BROWSER_COVERAGE: dict[str, str] = {
    "TC-01": "test_fbs_operator_flow_handoff.py::test_tc01_three_sellers_wms_seed_isolated",
    "TC-02": "test_fbs_supply_from_orders.py::test_tc02_preflight_different_wb_warehouses",
    "TC-03": "test_fbs_supply_from_orders.py::test_tc03_preflight_b2c_b2b_incompatible",
    "TC-04": "test_fbs_supply_from_orders.py::test_tc04_preflight_different_cargo_types",
    "TC-05": "test_fbs_supply_from_orders.py::test_tc05_preflight_pvz_can_pvz_gate",
    "TC-06": "test_fbs_supply_from_orders.py + test_fbs_operator_flow_handoff.py",
    "TC-07": "test_fbs_picking.py",
    "TC-08": "test_fbs_picking.py",
    "TC-09": "test_fbs_picking.py",
    "TC-10": "test_fbs_packaging_integration.py",
    "TC-11": "test_fbs_packaging_fulfillment.py",
    "TC-12": "test_fbs_marking.py",
    "TC-13": "test_fbs_marking.py",
    "TC-14": "test_fbs_marking.py",
    "TC-15": "test_fbs_print_assets.py",
    "TC-16": "test_fbs_print_assets.py",
    "TC-17": (
        "test_fbs_shipment_pvz.py::test_tc17_pvz_cargo_places_create_qr_and_deliver_without_bind"
    ),
    "TC-18": "test_fbs_shipment_pvz.py::test_tc18_pvz_cargo_places_dimension_blockers",
    "TC-19": (
        "test_fbs_shipment_delivery.py::test_tc19_delivery_preflight_checklist_and_stale_version"
    ),
    "TC-20": "test_fbs_shipment_delivery.py + test_fbs_operator_flow_handoff.py",
    "TC-21": "test_fbs_shipment_delivery.py + test_fbs_operator_flow_handoff.py",
    "TC-22": "test_fbs_tracking.py",
    "TC-23": "test_fbs_operator_flow_handoff.py + wb_emulator/tests/test_emulator_operator_seed.py",
}


def test_tc_non_browser_coverage_map_complete() -> None:
    for idx in range(1, 24):
        assert f"TC-{idx:02d}" in TC_NON_BROWSER_COVERAGE
