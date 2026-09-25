"""Late WB additions prefetch only their missing stickers without blocking packing.

WMS-537: the ``draft`` scenario used to assert that a draft supply skipped the
sticker prefetch entirely (``batch_order_ids == []``). The owner reported that
orders added to a draft supply never got their WB sticker until someone
pressed "Start work" or printed manually. The fix removes the draft-only
branch in ``add_orders_to_existing_supply`` so a draft behaves exactly like a
supply already being worked on: added orders' stickers are requested right
away. The ``draft`` scenario below now asserts the same prefetch as every
other status, plus that the supply stays a draft with no packaging task.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient

from app.core.settings import settings
from app.db.session import SessionLocal
from app.models.fbs_order import STICKER_STATUS_ERROR, FbsOrder
from app.models.fbs_wb_operation import WB_OPERATION_STATE_PENDING_CONFIRMATION
from app.services import fbs_print_asset_service as print_assets
from app.services import fbs_supply_service as supplies
from app.services.fbs_print_asset_storage import (
    PNG_MAGIC,
    FbsPrintAssetStorageError,
    read_print_file,
    save_print_file,
)
from app.services.wildberries_client import WildberriesClientError
from tests.test_fbs_supply_from_orders import (
    _create_product,
    _create_ready_order,
    _register_ff_admin,
    _setup_seller_with_token,
)


@pytest.mark.parametrize(
    "scenario",
    [
        "ready",
        "transport_error",
        "missing",
        "partial_confirmation",
        "draft",
        "asset_error",
        "storage_mkdir",
        "storage_write",
    ],
)
async def test_added_order_sticker_prefetch(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch, scenario: str
) -> None:
    monkeypatch.setattr(settings, "e2e_mock_wb_marketplace_supplies", True)
    headers, suffix = await _register_ff_admin(async_client)
    me = await async_client.get("/auth/me", headers=headers)
    tenant_id = uuid.UUID(me.json()["tenant_id"])
    seller_id, warehouse_id, location_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    product = await _create_product(async_client, headers, seller_id, sku=f"late-{suffix}")
    order_ids = [
        await _create_ready_order(
            tenant_id,
            uuid.UUID(seller_id),
            uuid.UUID(warehouse_id),
            uuid.UUID(location_id),
            product,
            order_id=475001 + idx,
        )
        for idx in range(3)
    ]
    created = await async_client.post(
        "/operations/fbs-supplies/from-orders",
        headers=headers,
        json={
            "name": "Late orders",
            "order_ids": [str(order_ids[0])],
            "planned_delivery_type": "warehouse_sc",
            "idempotency_key": str(uuid.uuid4()),
        },
    )
    assert created.status_code == 201, created.text
    supply_id = created.json()["supply"]["id"]
    if scenario != "draft":
        started = await async_client.post(
            f"/operations/fbs-supplies/{supply_id}/start-work", headers=headers
        )
        assert started.status_code == 200, started.text

    # An older missing code must not widen this prefetch to the whole supply.
    async with SessionLocal() as session:
        initial = await session.get(FbsOrder, order_ids[0])
        assert initial is not None
        initial.sticker_code = None
        await session.commit()

    real_batch = print_assets.request_supply_print_batch
    real_fetch = print_assets.fetch_marketplace_order_stickers
    real_add = supplies._execute_wb_batch_add
    batch_order_ids: list[list[uuid.UUID]] = []
    wb_add_calls: list[list[int]] = []
    fetched_codes: dict[int, str] = {}
    storage_failure = scenario.startswith("storage_")
    storage_method = "mkdir" if scenario == "storage_mkdir" else "write_bytes"
    real_storage_method = getattr(Path, storage_method)

    def fail_storage(path: Path, *args: Any, **kwargs: Any) -> Any:
        if "fbs-print-assets/order-stickers" in str(path):
            raise OSError("Test storage unavailable")
        return real_storage_method(path, *args, **kwargs)

    async def track_batch(*args: Any, **kwargs: Any) -> Any:
        batch_order_ids.append(kwargs["order_ids"])
        if scenario == "asset_error":
            raise print_assets.FbsPrintAssetError(
                "missing_marketplace_token", message="Unavailable"
            )
        return await real_batch(*args, **kwargs)

    async def track_add(*args: Any, **kwargs: Any) -> None:
        wb_add_calls.append(kwargs["wb_order_ids"])
        await real_add(*args, **kwargs)

    async def fetch_stickers(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        if scenario == "transport_error":
            raise WildberriesClientError("transport_error")
        rows = await real_fetch(*args, **kwargs)
        if scenario == "missing":
            rows = [row for row in rows if row["orderId"] != 475003]
        # Use a code explicitly distinct from the order ID.
        for row in rows:
            row["partA"] = "901"
            row["partB"] = "0042"
            if not storage_failure:
                fetched_codes[int(row["orderId"])] = "901 0042"
        return rows

    async def partial_confirmation(*args: Any, **kwargs: Any) -> tuple[str, set[int]]:
        return WB_OPERATION_STATE_PENDING_CONFIRMATION, {475001, 475002}

    monkeypatch.setattr(print_assets, "request_supply_print_batch", track_batch)
    monkeypatch.setattr(print_assets, "fetch_marketplace_order_stickers", fetch_stickers)
    monkeypatch.setattr(supplies, "_execute_wb_batch_add", track_add)
    if scenario == "partial_confirmation":
        monkeypatch.setattr(supplies, "reconcile_supply_orders", partial_confirmation)

    if storage_failure:
        monkeypatch.setattr(Path, storage_method, fail_storage)

    request = {
        "order_ids": [str(order_id) for order_id in order_ids[1:]],
        "idempotency_key": str(uuid.uuid4()),
    }
    response = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/orders/batch", headers=headers, json=request
    )
    assert response.status_code == 200, response.text
    added_ids = order_ids[1:2] if scenario == "partial_confirmation" else order_ids[1:]
    # WMS-537: a draft supply is no longer a special case — the prefetch runs
    # for the just-added orders regardless of supply status.
    assert len(batch_order_ids) == 1
    assert set(batch_order_ids[0]) == set(added_ids)
    assert len(wb_add_calls) == 1
    workspace = response.json()
    assert len(workspace["orders"]) == 1 + len(added_ids)
    if scenario == "draft":
        # The prefetch must not pull the supply out of `draft` or create a
        # packaging task on its own (R2): that stays a separate operator
        # action ("Начать работу с поставкой").
        assert workspace["supply"]["status"] == "draft"
        assert workspace["supply"]["packaging_task_id"] is None
    for order in workspace["orders"]:
        assert order["sticker"]["code"] == fetched_codes.get(order["wb_order_id"])
        if storage_failure and uuid.UUID(order["id"]) in added_ids:
            assert order["sticker"]["status"] == STICKER_STATUS_ERROR
    if scenario == "partial_confirmation":
        assert workspace["partial_rejection"]["rejected_orders"][0]["wb_order_id"] == 475003

    # A new request/session sees the same codes and the confirmed composition.
    reopened = await async_client.get(
        f"/operations/fbs-supplies/{supply_id}/workspace", headers=headers
    )
    assert reopened.status_code == 200, reopened.text
    for order in reopened.json()["orders"]:
        assert order["sticker"]["code"] == fetched_codes.get(order["wb_order_id"])
    async with SessionLocal() as session:
        for order_id in added_ids:
            order = await session.get(FbsOrder, order_id)
            assert order is not None
            assert str(order.supply_id) == supply_id
            assert order.sticker_code == fetched_codes.get(int(order.wb_order_id))
        if scenario == "partial_confirmation":
            rejected = await session.get(FbsOrder, order_ids[2])
            assert rejected is not None and rejected.supply_id is None

    # Existing repeat behavior is a conflict, with no second WB mutation.
    repeated = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/orders/batch", headers=headers, json=request
    )
    assert repeated.status_code == 409, repeated.text
    assert len(wb_add_calls) == 1

    # Normal print retry recovers missing labels without adding orders again.
    if storage_failure:
        monkeypatch.setattr(Path, storage_method, real_storage_method)
    monkeypatch.setattr(print_assets, "request_supply_print_batch", real_batch)
    monkeypatch.setattr(print_assets, "fetch_marketplace_order_stickers", real_fetch)
    retry = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/print-assets",
        headers=headers,
        json={
            "kind": "order_sticker",
            "order_ids": [str(order_id) for order_id in added_ids],
            "retry_missing": True,
        },
    )
    assert retry.status_code == 200, retry.text
    assert retry.json()["ready"] == len(added_ids)
    assert len(wb_add_calls) == 1
    recovered = await async_client.get(
        f"/operations/fbs-supplies/{supply_id}/workspace", headers=headers
    )
    assert recovered.status_code == 200, recovered.text
    for order in recovered.json()["orders"]:
        if uuid.UUID(order["id"]) in added_ids:
            assert order["sticker"]["code"]
            if order["wb_order_id"] in fetched_codes:
                assert order["sticker"]["code"] == fetched_codes[order["wb_order_id"]]


@pytest.mark.parametrize("error", [PermissionError("Cannot read"), FileNotFoundError("Removed")])
def test_storage_read_error_is_domain_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, error: OSError
) -> None:
    monkeypatch.setattr(settings, "wms_data_dir", str(tmp_path))
    relative = f"fbs-print-assets/order-stickers/{uuid.uuid4()}.png"
    save_print_file(relative, PNG_MAGIC + b"test")

    def fail_read(path: Path) -> bytes:
        raise error

    monkeypatch.setattr(Path, "read_bytes", fail_read)
    with pytest.raises(FbsPrintAssetStorageError) as caught:
        read_print_file(relative)
    assert caught.value.code == (
        "file_missing" if isinstance(error, FileNotFoundError) else "file_read_failed"
    )
    assert caught.value.__cause__ is error
