"""TC-15/TC-16 — FBS print assets binary API."""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from httpx import AsyncClient

from app.core.settings import settings
from app.db.session import SessionLocal
from app.models.fbs_order import STICKER_STATUS_APPLIED, STICKER_STATUS_PRINT_OPENED, FbsOrder
from app.models.fbs_print_asset import FbsPrintAsset, PRINT_ASSET_KIND_LABEL_TAPE
from app.models.seller import Seller
from app.services.fbs_print_asset_service import FbsPrintAssetError, get_asset_binary_content
from app.services.fbs_print_asset_storage import (
    PNG_MAGIC,
    FbsPrintAssetStorageError,
    validate_relative_storage_path,
)
from tests.test_fbs_supply_assembly import (
    _create_order,
    _create_supply,
    _register_ff_admin,
    _setup_seller_with_token,
)


@pytest.fixture
def enable_wb_marketplace_supplies_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "e2e_mock_wb_marketplace_supplies", True)


async def _seed_supply_with_orders(
    async_client: AsyncClient,
    headers: dict[str, str],
    *,
    order_count: int = 1,
    base_order_id: int = 950001,
) -> tuple[dict[str, object], list[uuid.UUID], uuid.UUID]:
    suffix = str(time.time_ns())
    seller_id, warehouse_id = await _setup_seller_with_token(async_client, headers, suffix)
    seller_uuid = uuid.UUID(seller_id)
    warehouse_uuid = uuid.UUID(warehouse_id)
    async with SessionLocal() as session:
        seller_obj = await session.get(Seller, seller_uuid)
        assert seller_obj is not None
        tenant_id = seller_obj.tenant_id

    order_ids = [
        await _create_order(
            tenant_id,
            seller_uuid,
            warehouse_uuid,
            order_id=base_order_id + idx,
        )
        for idx in range(order_count)
    ]
    supply = await _create_supply(async_client, headers, seller_id, warehouse_id)
    for oid in order_ids:
        add = await async_client.post(
            f"/operations/fbs-supplies/{supply['id']}/orders",
            headers=headers,
            json={"order_id": str(oid)},
        )
        assert add.status_code == 200, add.text
    return supply, order_ids, tenant_id


# TC-15 — one order sticker: real PNG, 58x40, binary content; missing file -> not ready
@pytest.mark.asyncio
async def test_tc15_one_order_sticker_binary_content(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
) -> None:
    headers, _ = await _register_ff_admin(async_client)
    supply, order_ids, _tenant_id = await _seed_supply_with_orders(async_client, headers)

    batch = await async_client.post(
        f"/operations/fbs-supplies/{supply['id']}/print-assets",
        headers=headers,
        json={"kind": "order_sticker", "order_ids": [str(order_ids[0])], "retry_missing": False},
    )
    assert batch.status_code == 200, batch.text
    body = batch.json()
    assert body["requested"] == 1
    assert body["ready"] == 1
    assert body["failed"] == 0
    assert len(body["assets"]) == 1
    asset = body["assets"][0]
    assert asset["status"] == "ready"
    assert asset["content_type"] == "image/png"
    assert asset["width_mm"] == 58
    assert asset["height_mm"] == 40
    assert asset["download_url"].endswith("/content")
    assert asset["checksum"].startswith("sha256:")

    content = await async_client.get(asset["download_url"], headers=headers)
    assert content.status_code == 200, content.text
    assert content.headers["content-type"].startswith("image/png")
    assert content.content[:8] == PNG_MAGIC

    async with SessionLocal() as session:
        order = await session.get(FbsOrder, order_ids[0])
        assert order is not None
        assert order.sticker_status == STICKER_STATUS_PRINT_OPENED


@pytest.mark.asyncio
async def test_tc15_missing_file_not_ready(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
) -> None:
    headers, _ = await _register_ff_admin(async_client)
    supply, order_ids, _tenant_id = await _seed_supply_with_orders(async_client, headers)

    batch = await async_client.post(
        f"/operations/fbs-supplies/{supply['id']}/print-assets",
        headers=headers,
        json={"kind": "order_sticker", "order_ids": [str(order_ids[0])], "retry_missing": False},
    )
    assert batch.status_code == 200, batch.text
    asset_id = batch.json()["assets"][0]["id"]

    async with SessionLocal() as session:
        asset = await session.get(FbsPrintAsset, uuid.UUID(asset_id))
        assert asset is not None
        assert asset.storage_path is not None
        missing_path = Path(settings.wms_data_dir) / asset.storage_path
        if missing_path.is_file():
            missing_path.unlink()

    content = await async_client.get(
        f"/operations/fbs-print-assets/{asset_id}/content",
        headers=headers,
    )
    assert content.status_code == 404
    detail = content.json()["detail"]
    assert detail["code"] == "asset_not_ready"


@pytest.mark.asyncio
async def test_label_tape_asset_expires_after_twelve_hours(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
) -> None:
    headers, _suffix = await _register_ff_admin(async_client)
    supply, order_ids, tenant_id = await _seed_supply_with_orders(async_client, headers)
    batch = await async_client.post(
        f"/operations/fbs-supplies/{supply['id']}/print-assets",
        headers=headers,
        json={"kind": "order_sticker", "order_ids": [str(order_ids[0])], "retry_missing": False},
    )
    asset_id = uuid.UUID(batch.json()["assets"][0]["id"])
    async with SessionLocal() as session:
        asset = await session.get(FbsPrintAsset, asset_id)
        assert asset is not None
        asset.kind = PRINT_ASSET_KIND_LABEL_TAPE
        asset.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()
        with pytest.raises(FbsPrintAssetError, match="asset_expired"):
            await get_asset_binary_content(session, tenant_id, asset_id, user_id=uuid.uuid4())


# TC-16 — batch stickers: counts, partial failure, retry missing only
@pytest.mark.asyncio
async def test_tc16_batch_stickers_partial_failure_and_retry_missing(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers, _ = await _register_ff_admin(async_client)
    supply, _order_ids, _tenant_id = await _seed_supply_with_orders(
        async_client, headers, order_count=3, base_order_id=960001
    )

    from app.services import wildberries_client as wb_client

    real_fetch = wb_client.fetch_marketplace_order_stickers

    async def flaky_stickers(
        _client: object,
        *,
        api_token: str,
        order_ids: list[int],
        marketplace_api_base: str | None = None,
        width: int = 58,
        height: int = 40,
    ) -> list[dict[str, object]]:
        rows = await real_fetch(
            _client,
            api_token=api_token,
            order_ids=order_ids,
            marketplace_api_base=marketplace_api_base,
            width=width,
            height=height,
        )
        if len(order_ids) > 1:
            return [row for row in rows if int(row["orderId"]) != order_ids[1]]
        return rows

    monkeypatch.setattr(
        "app.services.fbs_print_asset_service.fetch_marketplace_order_stickers",
        flaky_stickers,
    )

    batch = await async_client.post(
        f"/operations/fbs-supplies/{supply['id']}/print-assets",
        headers=headers,
        json={"kind": "order_sticker", "retry_missing": False},
    )
    assert batch.status_code == 200, batch.text
    body = batch.json()
    assert body["requested"] == 3
    assert body["ready"] == 2
    assert body["failed"] == 1
    assert body["missing"] == 0
    assert len(body["order_errors"]) == 1
    ready_assets = [a for a in body["assets"] if a["status"] == "ready"]
    assert len(ready_assets) == 2
    for asset in ready_assets:
        content = await async_client.get(asset["download_url"], headers=headers)
        assert content.status_code == 200
        assert len(content.content) > 0
        assert content.content.startswith(PNG_MAGIC)

    monkeypatch.setattr(
        "app.services.fbs_print_asset_service.fetch_marketplace_order_stickers",
        wb_client.fetch_marketplace_order_stickers,
    )

    retry = await async_client.post(
        f"/operations/fbs-supplies/{supply['id']}/print-assets",
        headers=headers,
        json={"kind": "order_sticker", "retry_missing": True},
    )
    assert retry.status_code == 200, retry.text
    retry_body = retry.json()
    assert retry_body["ready"] == 3
    assert retry_body["failed"] == 0
    assert retry_body["missing"] == 0


@pytest.mark.asyncio
async def test_tc16_retry_missing_does_not_regenerate_ready(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers, _ = await _register_ff_admin(async_client)
    supply, order_ids, _tenant_id = await _seed_supply_with_orders(async_client, headers)
    calls: list[list[int]] = []

    from app.services import wildberries_client as wb_client

    async def counting_stickers(
        _client: object,
        *,
        api_token: str,
        order_ids: list[int],
        marketplace_api_base: str | None = None,
        width: int = 58,
        height: int = 40,
    ) -> list[dict[str, object]]:
        calls.append(list(order_ids))
        return await wb_client.fetch_marketplace_order_stickers(
            _client,
            api_token=api_token,
            order_ids=order_ids,
            marketplace_api_base=marketplace_api_base,
            width=width,
            height=height,
        )

    monkeypatch.setattr(
        "app.services.fbs_print_asset_service.fetch_marketplace_order_stickers",
        counting_stickers,
    )

    first = await async_client.post(
        f"/operations/fbs-supplies/{supply['id']}/print-assets",
        headers=headers,
        json={"kind": "order_sticker", "order_ids": [str(order_ids[0])], "retry_missing": False},
    )
    assert first.status_code == 200, first.text
    assert first.json()["ready"] == 1
    assert len(calls) == 1

    retry = await async_client.post(
        f"/operations/fbs-supplies/{supply['id']}/print-assets",
        headers=headers,
        json={"kind": "order_sticker", "order_ids": [str(order_ids[0])], "retry_missing": True},
    )
    assert retry.status_code == 200, retry.text
    assert retry.json()["ready"] == 1
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_print_asset_cross_tenant_404(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
) -> None:
    headers_a, _ = await _register_ff_admin(async_client)
    supply_a, order_ids_a, _ = await _seed_supply_with_orders(async_client, headers_a)
    batch_a = await async_client.post(
        f"/operations/fbs-supplies/{supply_a['id']}/print-assets",
        headers=headers_a,
        json={"kind": "order_sticker", "order_ids": [str(order_ids_a[0])], "retry_missing": False},
    )
    assert batch_a.status_code == 200, batch_a.text
    asset_id = batch_a.json()["assets"][0]["id"]

    headers_b, _ = await _register_ff_admin(async_client)
    foreign = await async_client.get(
        f"/operations/fbs-print-assets/{asset_id}/content",
        headers=headers_b,
    )
    assert foreign.status_code == 404
    assert foreign.json()["detail"]["code"] == "asset_not_found"


def test_storage_traversal_path_rejected() -> None:
    with pytest.raises(FbsPrintAssetStorageError) as exc:
        validate_relative_storage_path(
            "../../etc/passwd",
            subdir="fbs-print-assets/order-stickers",
        )
    assert exc.value.code == "invalid_storage_path"


@pytest.mark.asyncio
async def test_applied_separate_from_print_opened(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
) -> None:
    headers, _ = await _register_ff_admin(async_client)
    supply, order_ids, _ = await _seed_supply_with_orders(async_client, headers)
    batch = await async_client.post(
        f"/operations/fbs-supplies/{supply['id']}/print-assets",
        headers=headers,
        json={"kind": "order_sticker", "order_ids": [str(order_ids[0])], "retry_missing": False},
    )
    asset_id = batch.json()["assets"][0]["id"]
    content = await async_client.get(
        f"/operations/fbs-print-assets/{asset_id}/content",
        headers=headers,
    )
    assert content.status_code == 200

    async with SessionLocal() as session:
        order = await session.get(FbsOrder, order_ids[0])
        assert order is not None
        assert order.sticker_status == STICKER_STATUS_PRINT_OPENED

    applied = await async_client.post(
        f"/operations/fbs-print-assets/{asset_id}/applied",
        headers=headers,
        json={"idempotency_key": "apply-1"},
    )
    assert applied.status_code == 200, applied.text
    assert applied.json()["applied_at"] is not None

    async with SessionLocal() as session:
        order = await session.get(FbsOrder, order_ids[0])
        assert order is not None
        assert order.sticker_status == STICKER_STATUS_APPLIED
