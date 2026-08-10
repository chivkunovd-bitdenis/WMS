from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models.fbs_order import (
    CHECK_STATUS_NEW,
    FBS_ORDER_STATUS_IN_DELIVERY,
    FBS_ORDER_STATUS_PACKED,
    MAPPING_STATUS_MAPPED,
    MARKING_KIND_SGTIN,
    META_STATUS_ACCEPTED,
    RESERVE_STATUS_RESERVED,
    FbsOrder,
    FbsOrderMarking,
)
from app.models.fbs_packaging_fulfillment import FbsPackagingFulfillment
from app.models.fbs_supply import FBS_DELIVERY_TYPE_WAREHOUSE_SC, FbsSupply
from app.models.marking_code import (
    EVENT_APPLIED,
    EVENT_VOIDED,
    STATUS_APPLIED,
    STATUS_VOID,
    MarkingCode,
    MarkingCodeEvent,
)
from app.models.packaging_task import PackagingTask, PackagingTaskLine
from app.models.product import Product
from app.models.storage_location import StorageLocation
from app.services import fbs_kiz_service as kiz_svc
from app.services.wildberries_errors import MetaValidationFailItem, WildberriesBusinessError
from app.services.wildberries_fbs_client import MarketplaceMetaDetail, MarketplaceOrderMetaRow

_GS = "\x1d"
_CLEAN_CIS = f"010460043993125321AbCxyz{_GS}91K1aZ{_GS}92Crypto~|#<GS>tail"


@dataclass(frozen=True)
class _SeededOrder:
    supply_id: uuid.UUID
    order_id: uuid.UUID
    wb_order_id: int
    product_id: uuid.UUID
    product_name: str
    product_barcode: str
    seller_article: str
    packaging_task_id: uuid.UUID | None = None
    packaging_task_line_id: uuid.UUID | None = None


async def _register_ff_admin(async_client: AsyncClient) -> tuple[dict[str, str], str]:
    suffix = str(time.time_ns())
    response = await async_client.post(
        "/auth/register",
        json={
            "organization_name": f"FBS KIZ {suffix}",
            "slug": f"fbs-kiz-{suffix}",
            "admin_email": f"fbs-kiz-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}, suffix


async def _setup_seller_warehouse(
    async_client: AsyncClient,
    headers: dict[str, str],
    suffix: str,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    seller_response = await async_client.post(
        "/sellers",
        headers=headers,
        json={"name": f"Seller {suffix}"},
    )
    assert seller_response.status_code in (200, 201), seller_response.text
    seller_id = seller_response.json()["id"]

    token_response = await async_client.patch(
        f"/integrations/wildberries/sellers/{seller_id}/tokens",
        headers=headers,
        json={"marketplace_api_token": "wb-marketplace-token"},
    )
    assert token_response.status_code == 200, token_response.text

    warehouse_response = await async_client.post(
        "/warehouses",
        headers=headers,
        json={"name": "WH", "code": f"wh-{suffix[-8:]}"},
    )
    assert warehouse_response.status_code in (200, 201), warehouse_response.text

    me_response = await async_client.get("/auth/me", headers=headers)
    assert me_response.status_code == 200, me_response.text
    return (
        uuid.UUID(seller_id),
        uuid.UUID(warehouse_response.json()["id"]),
        uuid.UUID(me_response.json()["tenant_id"]),
    )


async def _create_supply(
    *,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    suffix: str,
) -> uuid.UUID:
    async with SessionLocal() as session:
        supply = FbsSupply(
            tenant_id=tenant_id,
            seller_id=seller_id,
            warehouse_id=warehouse_id,
            wb_supply_id=f"WB-GI-KIZ-{suffix}-{uuid.uuid4().hex[:8]}",
            name=f"KIZ supply {suffix}",
            delivery_type=FBS_DELIVERY_TYPE_WAREHOUSE_SC,
        )
        session.add(supply)
        await session.commit()
        return supply.id


async def _create_order(
    *,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    supply_id: uuid.UUID,
    suffix: str,
    wb_order_id: int,
    sticker_code: str | None,
    wb_barcode: str | None,
    status: str = FBS_ORDER_STATUS_PACKED,
    meta_details_json: dict[str, Any] | None = None,
    marking: FbsOrderMarking | None = None,
    with_packaging: bool = False,
) -> _SeededOrder:
    now = datetime.now(tz=UTC)
    product_name = f"KIZ product {wb_order_id}"
    seller_article = f"SKU-KIZ-{suffix}-{wb_order_id}"
    product_barcode = f"PROD-KIZ-{suffix}-{wb_order_id}"
    packaging_task_id: uuid.UUID | None = None
    packaging_task_line_id: uuid.UUID | None = None
    async with SessionLocal() as session:
        product = Product(
            tenant_id=tenant_id,
            seller_id=seller_id,
            name=product_name,
            sku_code=seller_article,
            wb_nm_id=wb_order_id + 1000,
            wb_vendor_code=f"VENDOR-{wb_order_id}",
            wb_chrt_id=wb_order_id + 2000,
            wb_barcode=product_barcode,
        )
        session.add(product)
        await session.flush()

        order = FbsOrder(
            tenant_id=tenant_id,
            seller_id=seller_id,
            warehouse_id=warehouse_id,
            product_id=product.id,
            wb_order_id=wb_order_id,
            wb_rid=f"rid-{wb_order_id}",
            wb_nm_id=product.wb_nm_id,
            wb_chrt_id=product.wb_chrt_id,
            wb_article=product.wb_vendor_code,
            wb_barcode=wb_barcode,
            price=1000,
            is_legal=False,
            cargo_type="mgt",
            wb_office_id=42,
            wb_warehouse_id=99,
            can_pvz=False,
            supply_id=supply_id,
            sticker_code=sticker_code,
            status=status,
            created_at_wb=now,
            deadline_at=now + timedelta(days=1),
            mapping_status=MAPPING_STATUS_MAPPED,
            reserve_status=RESERVE_STATUS_RESERVED,
            meta_details_json=meta_details_json,
        )
        session.add(order)
        await session.flush()

        if with_packaging:
            task = PackagingTask(
                tenant_id=tenant_id,
                warehouse_id=warehouse_id,
                status="done",
                document_number=f"PKG-KIZ-{wb_order_id}",
            )
            location = StorageLocation(
                tenant_id=tenant_id,
                warehouse_id=warehouse_id,
                code=f"KIZ-SORT-{suffix[-8:]}-{wb_order_id}",
                barcode=f"KIZ-SORT-{suffix}-{wb_order_id}",
            )
            session.add_all([task, location])
            await session.flush()
            line = PackagingTaskLine(
                task_id=task.id,
                product_id=product.id,
                storage_location_id=location.id,
                qty_total=1,
                qty_suggested_packed=0,
                qty_confirmed_packed=0,
                qty_packed_in_task=1,
                qty_marking_printed=0,
                qty_marking_external=0,
            )
            session.add(line)
            await session.flush()
            supply = await session.get(FbsSupply, supply_id)
            assert supply is not None
            supply.packaging_task_id = task.id
            session.add(
                FbsPackagingFulfillment(
                    tenant_id=tenant_id,
                    fbs_order_id=order.id,
                    packaging_task_id=task.id,
                    packaging_task_line_id=line.id,
                    fulfilled_at=now,
                    pack_idempotency_key=f"kiz-pack-{wb_order_id}",
                )
            )
            packaging_task_id = task.id
            packaging_task_line_id = line.id

        if marking is not None:
            marking.order_id = order.id
            marking.tenant_id = tenant_id
            session.add(marking)

        await session.commit()
        return _SeededOrder(
            supply_id=supply_id,
            order_id=order.id,
            wb_order_id=wb_order_id,
            product_id=product.id,
            product_name=product_name,
            product_barcode=wb_barcode or product_barcode,
            seller_article=seller_article,
            packaging_task_id=packaging_task_id,
            packaging_task_line_id=packaging_task_line_id,
        )


async def _lookup(
    async_client: AsyncClient,
    headers: dict[str, str],
    *,
    supply_id: uuid.UUID,
    sticker: str,
) -> Any:
    return await async_client.get(
        "/operations/fbs-orders/kiz/lookup",
        headers=headers,
        params={"supply_id": str(supply_id), "sticker": sticker},
    )


def _cis(suffix: str) -> str:
    return f"010460043993125321KIZ{suffix}"


async def _marking_row_counts(tenant_id: uuid.UUID) -> tuple[int, int]:
    async with SessionLocal() as session:
        markings = await session.scalar(
            select(func.count(FbsOrderMarking.id)).where(
                FbsOrderMarking.tenant_id == tenant_id
            )
        )
        codes = await session.scalar(
            select(func.count(MarkingCode.id)).where(MarkingCode.tenant_id == tenant_id)
        )
    return int(markings or 0), int(codes or 0)


def _patch_wb_acceptance(
    monkeypatch: pytest.MonkeyPatch,
    *,
    reject_order_id: int | None = None,
) -> dict[int, str]:
    sent_values: dict[int, str] = {}

    async def fake_put(
        client: object,
        *,
        api_token: str,
        order_id: int,
        kind: str,
        value: str,
        marketplace_api_base: str | None = None,
    ) -> None:
        del client, api_token, kind, marketplace_api_base
        if order_id == reject_order_id:
            raise WildberriesBusinessError(
                "meta_validation_fail",
                status_code=409,
                meta_validation=[
                    MetaValidationFailItem(
                        order_id=order_id,
                        key=MARKING_KIND_SGTIN,
                        value=value,
                        decision="invalid",
                        reason="bad kiz",
                    )
                ],
            )
        sent_values[order_id] = value

    async def fake_meta_batch(
        client: object,
        *,
        api_token: str,
        order_ids: list[int],
        marketplace_api_base: str | None = None,
    ) -> list[MarketplaceOrderMetaRow]:
        del client, api_token, marketplace_api_base
        order_id = order_ids[0]
        value = sent_values[order_id]
        return [
            MarketplaceOrderMetaRow(
                order_id=order_id,
                meta_details=(
                    MarketplaceMetaDetail(
                        key=MARKING_KIND_SGTIN,
                        value=value,
                        decision="accepted",
                    ),
                ),
                meta={MARKING_KIND_SGTIN: [{"value": value, "checkStatus": "ok"}]},
            )
        ]

    monkeypatch.setattr(
        "app.services.fbs_marking_service.put_marketplace_order_meta",
        fake_put,
    )
    monkeypatch.setattr(
        "app.services.fbs_marking_service.fetch_marketplace_orders_meta_batch",
        fake_meta_batch,
    )
    return sent_values


@pytest.mark.parametrize("prefix", ["]d2", "]d1", "]Q1", "]Q3", "]C1"])
def test_normalize_scanned_cis_strips_aim_prefix(prefix: str) -> None:
    # TC-NEW-FBS-KIZ-002: scanner AIM symbology prefixes are server-normalized.
    value, hints = kiz_svc.normalize_scanned_cis(f"{prefix}{_CLEAN_CIS}")

    assert value == _CLEAN_CIS
    assert hints == ["aim_prefix"]


@pytest.mark.parametrize("separator", ["~", "|", "#", "<GS>", "{GS}", "\\x1d"])
def test_normalize_scanned_cis_restores_gs_substitute_only_at_separator(
    separator: str,
) -> None:
    # TC-NEW-FBS-KIZ-002: visible GS substitutes are restored only at GS1 boundaries.
    raw = f"010460043993125321AbCxyz{separator}91K1aZ{separator}92Crypto~|#<GS>tail"

    value, hints = kiz_svc.normalize_scanned_cis(raw)

    assert value == _CLEAN_CIS
    assert hints == ["gs_substitute"]


def test_normalize_scanned_cis_repairs_keyboard_layout() -> None:
    # TC-NEW-FBS-KIZ-002: Russian keyboard-layout scans are converted back to QWERTY.
    raw = (
        "010460043993125321"
        "\u0424\u0438\u0421\u0447\u043d\u044f"
        f"{_GS}91\u041b1\u0444\u042f"
        f"{_GS}92\u0421\u043a\u043d\u0437\u0435\u0449"
    )

    value, hints = kiz_svc.normalize_scanned_cis(raw)

    assert value == f"010460043993125321AbCxyz{_GS}91K1aZ{_GS}92Crypto"
    assert hints == ["keyboard_layout"]


def test_normalize_scanned_cis_trims_scanner_suffix() -> None:
    # TC-NEW-FBS-KIZ-002: scanner suffix whitespace is ignored before validation.
    value, hints = kiz_svc.normalize_scanned_cis(f"{_CLEAN_CIS}\r\n ")

    assert value == _CLEAN_CIS
    assert hints == []


def test_normalize_scanned_cis_repairs_keyboard_layout_and_gs_together() -> None:
    # TC-NEW-FBS-KIZ-002: independent scanner issues can be repaired in one pass.
    raw = (
        "010460043993125321"
        "\u0424\u0438\u0421\u0447\u043d\u044f"
        "~91\u041b1\u0444\u042f#92\u0421\u043a\u043d\u0437\u0435\u0449~tail"
    )

    value, hints = kiz_svc.normalize_scanned_cis(raw)

    assert value == f"010460043993125321AbCxyz{_GS}91K1aZ{_GS}92Crypto~tail"
    assert hints == ["gs_substitute", "keyboard_layout"]


def test_normalize_scanned_cis_clean_value_has_no_hints() -> None:
    # TC-NEW-FBS-KIZ-002: valid scanner input is preserved byte-for-byte.
    value, hints = kiz_svc.normalize_scanned_cis(_CLEAN_CIS)

    assert value == _CLEAN_CIS
    assert hints == []


def test_is_probably_cis_rejects_garbage() -> None:
    # TC-NEW-FBS-KIZ-002: non-CIS garbage must not be sent to WB.
    assert kiz_svc.is_probably_cis("laser scanner noise") is False


def test_scan_debug_masks_gs_in_edges() -> None:
    # TC-NEW-FBS-KIZ-002: diagnostics expose scan shape without invisible GS bytes.
    debug = kiz_svc.scan_debug(f"AB{_GS}CDEFGHIJ{_GS}KL")

    assert debug == {
        "length": 14,
        "first8": "AB<GS>CDEFG",
        "last8": "FGHIJ<GS>KL",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("sticker_code", "wb_barcode", "meta_details_json", "scan"),
    [
        ("STICKER123", "WB-BAR-IGNORED", None, "\ufeff STICKER \r\n123 "),
        ("STICKER-IGNORED", "WBBAR456", None, " WB \rBAR\n456 "),
    ],
    ids=["sticker_code", "wb_barcode"],
)
async def test_fbs_kiz_lookup_matches_tolerant_sticker_fields(
    async_client: AsyncClient,
    sticker_code: str,
    wb_barcode: str,
    meta_details_json: dict[str, Any] | None,
    scan: str,
) -> None:
    # TC-NEW-FBS-KIZ-001 / TC-NEW-FBS-KIZ-002: lookup by sticker variants.
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_warehouse(
        async_client, headers, suffix
    )
    supply_id = await _create_supply(
        tenant_id=tenant_id,
        seller_id=seller_id,
        warehouse_id=warehouse_id,
        suffix=suffix,
    )
    order = await _create_order(
        tenant_id=tenant_id,
        seller_id=seller_id,
        warehouse_id=warehouse_id,
        supply_id=supply_id,
        suffix=suffix,
        wb_order_id=931001,
        sticker_code=sticker_code,
        wb_barcode=wb_barcode,
        meta_details_json=meta_details_json,
    )

    response = await _lookup(async_client, headers, supply_id=supply_id, sticker=scan)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["order_id"] == str(order.order_id)
    assert body["wb_order_id"] == order.wb_order_id
    assert body["product"] == {
        "name": order.product_name,
        "image_url": None,
        "barcode": order.product_barcode,
        "seller_article": order.seller_article,
    }
    assert body["current_kiz"] is None
    assert body["needs_confirmation"] is False
    assert body["can_bind"] is True
    assert body["block_reason"] is None


@pytest.mark.asyncio
async def test_fbs_kiz_lookup_garbage_sticker_returns_404(
    async_client: AsyncClient,
) -> None:
    # TC-NEW-FBS-KIZ-002: negative garbage scan.
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_warehouse(
        async_client, headers, suffix
    )
    supply_id = await _create_supply(
        tenant_id=tenant_id,
        seller_id=seller_id,
        warehouse_id=warehouse_id,
        suffix=suffix,
    )
    await _create_order(
        tenant_id=tenant_id,
        seller_id=seller_id,
        warehouse_id=warehouse_id,
        supply_id=supply_id,
        suffix=suffix,
        wb_order_id=931101,
        sticker_code="REAL-STICKER",
        wb_barcode="REAL-WB-BAR",
    )

    response = await _lookup(async_client, headers, supply_id=supply_id, sticker="UNKNOWN")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "sticker_not_found"


@pytest.mark.asyncio
async def test_fbs_kiz_lookup_foreign_supply_sticker_returns_404(
    async_client: AsyncClient,
) -> None:
    # TC-NEW-FBS-KIZ-001: negative sticker from another supply.
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_warehouse(
        async_client, headers, suffix
    )
    target_supply_id = await _create_supply(
        tenant_id=tenant_id,
        seller_id=seller_id,
        warehouse_id=warehouse_id,
        suffix=f"{suffix}-target",
    )
    foreign_supply_id = await _create_supply(
        tenant_id=tenant_id,
        seller_id=seller_id,
        warehouse_id=warehouse_id,
        suffix=f"{suffix}-foreign",
    )
    await _create_order(
        tenant_id=tenant_id,
        seller_id=seller_id,
        warehouse_id=warehouse_id,
        supply_id=foreign_supply_id,
        suffix=suffix,
        wb_order_id=931201,
        sticker_code="FOREIGN-STICKER",
        wb_barcode="FOREIGN-WB-BAR",
    )

    response = await _lookup(
        async_client,
        headers,
        supply_id=target_supply_id,
        sticker="FOREIGN-STICKER",
    )

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "sticker_not_found"


@pytest.mark.asyncio
async def test_fbs_kiz_lookup_frozen_order_returns_409(
    async_client: AsyncClient,
) -> None:
    # TC-NEW-FBS-KIZ-001: frozen order cannot be bound.
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_warehouse(
        async_client, headers, suffix
    )
    supply_id = await _create_supply(
        tenant_id=tenant_id,
        seller_id=seller_id,
        warehouse_id=warehouse_id,
        suffix=suffix,
    )
    await _create_order(
        tenant_id=tenant_id,
        seller_id=seller_id,
        warehouse_id=warehouse_id,
        supply_id=supply_id,
        suffix=suffix,
        wb_order_id=931301,
        sticker_code="FROZEN-STICKER",
        wb_barcode="FROZEN-WB-BAR",
        status=FBS_ORDER_STATUS_IN_DELIVERY,
    )

    response = await _lookup(
        async_client,
        headers,
        supply_id=supply_id,
        sticker="FROZEN-STICKER",
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "order_frozen"


@pytest.mark.asyncio
async def test_fbs_kiz_lookup_existing_pool_kiz_needs_confirmation(
    async_client: AsyncClient,
) -> None:
    # TC-NEW-FBS-KIZ-006: existing pool KIZ is a confirmation warning, not a product block.
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_warehouse(
        async_client, headers, suffix
    )
    supply_id = await _create_supply(
        tenant_id=tenant_id,
        seller_id=seller_id,
        warehouse_id=warehouse_id,
        suffix=suffix,
    )
    await _create_order(
        tenant_id=tenant_id,
        seller_id=seller_id,
        warehouse_id=warehouse_id,
        supply_id=supply_id,
        suffix=suffix,
        wb_order_id=931401,
        sticker_code="POOL-STICKER",
        wb_barcode="POOL-WB-BAR",
        marking=FbsOrderMarking(
            order_id=uuid.uuid4(),
            tenant_id=tenant_id,
            kind=MARKING_KIND_SGTIN,
            value="010123456789012121POOLABCDEF",
            source="pool",
            check_status=CHECK_STATUS_NEW,
            meta_status=META_STATUS_ACCEPTED,
        ),
    )

    response = await _lookup(
        async_client,
        headers,
        supply_id=supply_id,
        sticker="POOL-STICKER",
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["current_kiz"] == {
        "masked": "…ABCDEF",
        "meta_status": META_STATUS_ACCEPTED,
        "from_pool": True,
    }
    assert body["needs_confirmation"] is True
    assert body["can_bind"] is True
    assert body["block_reason"] is None


@pytest.mark.asyncio
async def test_fbs_kiz_validate_normalizes_and_does_not_write(
    async_client: AsyncClient,
) -> None:
    # TC-NEW-FBS-KIZ-003: validate returns scanner hints and does not persist rows.
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_warehouse(
        async_client, headers, suffix
    )
    supply_id = await _create_supply(
        tenant_id=tenant_id,
        seller_id=seller_id,
        warehouse_id=warehouse_id,
        suffix=suffix,
    )
    order = await _create_order(
        tenant_id=tenant_id,
        seller_id=seller_id,
        warehouse_id=warehouse_id,
        supply_id=supply_id,
        suffix=suffix,
        wb_order_id=931501,
        sticker_code="VALIDATE-STICKER",
        wb_barcode="VALIDATE-WB-BAR",
    )
    before = await _marking_row_counts(tenant_id)

    response = await async_client.post(
        "/operations/fbs-orders/kiz/validate",
        headers=headers,
        json={"order_id": str(order.order_id), "value": f"]d2{_cis('VAL001')}"},
    )

    assert response.status_code == 200, response.text
    assert response.json() == {"ok": True, "hints": ["aim_prefix"]}
    assert await _marking_row_counts(tenant_id) == before


@pytest.mark.asyncio
async def test_fbs_kiz_validate_rejects_garbage_with_debug(
    async_client: AsyncClient,
) -> None:
    # TC-NEW-FBS-KIZ-002: non-CIS scanner noise is rejected before WB.
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_warehouse(
        async_client, headers, suffix
    )
    supply_id = await _create_supply(
        tenant_id=tenant_id,
        seller_id=seller_id,
        warehouse_id=warehouse_id,
        suffix=suffix,
    )
    order = await _create_order(
        tenant_id=tenant_id,
        seller_id=seller_id,
        warehouse_id=warehouse_id,
        supply_id=supply_id,
        suffix=suffix,
        wb_order_id=931601,
        sticker_code="GARBAGE-STICKER",
        wb_barcode="GARBAGE-WB-BAR",
    )
    before = await _marking_row_counts(tenant_id)

    response = await async_client.post(
        "/operations/fbs-orders/kiz/validate",
        headers=headers,
        json={"order_id": str(order.order_id), "value": f"laser{_GS}noise"},
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["code"] == "not_a_kiz"
    assert detail["context"]["debug"] == {
        "length": 11,
        "first8": "laser<GS>no",
        "last8": "er<GS>noise",
    }
    assert await _marking_row_counts(tenant_id) == before


@pytest.mark.asyncio
async def test_fbs_kiz_validate_duplicate_marking_returns_order_context(
    async_client: AsyncClient,
) -> None:
    # TC-NEW-FBS-KIZ-003: another active order owns the same CIS.
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_warehouse(
        async_client, headers, suffix
    )
    supply_id = await _create_supply(
        tenant_id=tenant_id,
        seller_id=seller_id,
        warehouse_id=warehouse_id,
        suffix=suffix,
    )
    value = _cis("DUP001")
    await _create_order(
        tenant_id=tenant_id,
        seller_id=seller_id,
        warehouse_id=warehouse_id,
        supply_id=supply_id,
        suffix=suffix,
        wb_order_id=931701,
        sticker_code="DUP-OWNER",
        wb_barcode="DUP-OWNER-BAR",
        marking=FbsOrderMarking(
            order_id=uuid.uuid4(),
            tenant_id=tenant_id,
            kind=MARKING_KIND_SGTIN,
            value=value,
            source="operator",
            check_status=CHECK_STATUS_NEW,
            meta_status=META_STATUS_ACCEPTED,
        ),
    )
    target = await _create_order(
        tenant_id=tenant_id,
        seller_id=seller_id,
        warehouse_id=warehouse_id,
        supply_id=supply_id,
        suffix=suffix,
        wb_order_id=931702,
        sticker_code="DUP-TARGET",
        wb_barcode="DUP-TARGET-BAR",
    )

    response = await async_client.post(
        "/operations/fbs-orders/kiz/validate",
        headers=headers,
        json={"order_id": str(target.order_id), "value": value},
    )

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["code"] == "duplicate_kiz"
    assert detail["context"]["wb_order_id"] == 931701
    assert "created_at" in detail["context"]


@pytest.mark.asyncio
async def test_fbs_kiz_validate_frozen_order_returns_409(
    async_client: AsyncClient,
) -> None:
    # TC-NEW-FBS-KIZ-003: frozen orders cannot pass validation.
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_warehouse(
        async_client, headers, suffix
    )
    supply_id = await _create_supply(
        tenant_id=tenant_id,
        seller_id=seller_id,
        warehouse_id=warehouse_id,
        suffix=suffix,
    )
    order = await _create_order(
        tenant_id=tenant_id,
        seller_id=seller_id,
        warehouse_id=warehouse_id,
        supply_id=supply_id,
        suffix=suffix,
        wb_order_id=931801,
        sticker_code="FROZEN-VALIDATE",
        wb_barcode="FROZEN-VALIDATE-BAR",
        status=FBS_ORDER_STATUS_IN_DELIVERY,
    )

    response = await async_client.post(
        "/operations/fbs-orders/kiz/validate",
        headers=headers,
        json={"order_id": str(order.order_id), "value": _cis("FROZEN001")},
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "order_frozen"


@pytest.mark.asyncio
async def test_fbs_kiz_commit_partial_success_keeps_other_transactions(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # TC-NEW-FBS-KIZ-005: a WB rejection for one pair does not roll back neighbors.
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_warehouse(
        async_client, headers, suffix
    )
    supply_id = await _create_supply(
        tenant_id=tenant_id,
        seller_id=seller_id,
        warehouse_id=warehouse_id,
        suffix=suffix,
    )
    orders = [
        await _create_order(
            tenant_id=tenant_id,
            seller_id=seller_id,
            warehouse_id=warehouse_id,
            supply_id=supply_id,
            suffix=suffix,
            wb_order_id=931900 + index,
            sticker_code=f"COMMIT-{index}",
            wb_barcode=f"COMMIT-BAR-{index}",
            with_packaging=True,
        )
        for index in range(1, 4)
    ]
    reject_order = orders[1]
    _patch_wb_acceptance(monkeypatch, reject_order_id=reject_order.wb_order_id)
    values = [_cis(f"BATCH00{index}") for index in range(1, 4)]

    response = await async_client.post(
        "/operations/fbs-orders/kiz/commit",
        headers=headers,
        json={
            "idempotency_key": "kiz-batch-partial",
            "pairs": [
                {
                    "order_id": str(order.order_id),
                    "value": value,
                    "confirmed": False,
                }
                for order, value in zip(orders, values, strict=True)
            ],
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert [row["status"] for row in body] == ["ok", "error", "ok"]
    assert body[1]["code"] == "meta_validation_fail"
    assert body[1]["message"] == "bad kiz"

    async with SessionLocal() as session:
        saved_markings = list(
            (
                await session.execute(
                    select(FbsOrderMarking).where(
                        FbsOrderMarking.order_id.in_(
                            [order.order_id for order in orders]
                        )
                    )
                )
            ).scalars()
        )
        assert {row.order_id for row in saved_markings} == {
            orders[0].order_id,
            orders[2].order_id,
        }
        saved_codes = list(
            (
                await session.execute(
                    select(MarkingCode).where(MarkingCode.cis_code.in_(values))
                )
            ).scalars()
        )
        assert {code.cis_code for code in saved_codes} == {values[0], values[2]}


@pytest.mark.asyncio
async def test_fbs_kiz_commit_existing_kiz_needs_confirmation_without_writes(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # TC-NEW-FBS-KIZ-006: replacing an existing KIZ requires explicit confirmation.
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_warehouse(
        async_client, headers, suffix
    )
    supply_id = await _create_supply(
        tenant_id=tenant_id,
        seller_id=seller_id,
        warehouse_id=warehouse_id,
        suffix=suffix,
    )
    old_value = _cis("OLD001")
    order = await _create_order(
        tenant_id=tenant_id,
        seller_id=seller_id,
        warehouse_id=warehouse_id,
        supply_id=supply_id,
        suffix=suffix,
        wb_order_id=932001,
        sticker_code="NEEDS-CONFIRM",
        wb_barcode="NEEDS-CONFIRM-BAR",
        with_packaging=True,
        marking=FbsOrderMarking(
            order_id=uuid.uuid4(),
            tenant_id=tenant_id,
            kind=MARKING_KIND_SGTIN,
            value=old_value,
            source="operator",
            check_status=CHECK_STATUS_NEW,
            meta_status=META_STATUS_ACCEPTED,
        ),
    )
    sent = _patch_wb_acceptance(monkeypatch)
    before = await _marking_row_counts(tenant_id)

    response = await async_client.post(
        "/operations/fbs-orders/kiz/commit",
        headers=headers,
        json={
            "idempotency_key": "kiz-needs-confirm",
            "pairs": [
                {
                    "order_id": str(order.order_id),
                    "value": _cis("NEW001"),
                    "confirmed": False,
                }
            ],
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()[0]["status"] == "error"
    assert response.json()[0]["code"] == "needs_confirmation"
    assert sent == {}
    assert await _marking_row_counts(tenant_id) == before
    async with SessionLocal() as session:
        marking = (
            await session.execute(
                select(FbsOrderMarking).where(FbsOrderMarking.order_id == order.order_id)
            )
        ).scalar_one()
        assert marking.value == old_value


@pytest.mark.asyncio
async def test_fbs_kiz_commit_confirmed_replaces_old_kiz_and_voids_code(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # TC-NEW-FBS-KIZ-006: confirmed replacement voids the previous code.
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_warehouse(
        async_client, headers, suffix
    )
    supply_id = await _create_supply(
        tenant_id=tenant_id,
        seller_id=seller_id,
        warehouse_id=warehouse_id,
        suffix=suffix,
    )
    order = await _create_order(
        tenant_id=tenant_id,
        seller_id=seller_id,
        warehouse_id=warehouse_id,
        supply_id=supply_id,
        suffix=suffix,
        wb_order_id=932101,
        sticker_code="CONFIRMED-REPLACE",
        wb_barcode="CONFIRMED-REPLACE-BAR",
        with_packaging=True,
    )
    assert order.packaging_task_line_id is not None
    old_value = _cis("OLDREP")
    new_value = _cis("NEWREP")
    async with SessionLocal() as session:
        old_code = MarkingCode(
            tenant_id=tenant_id,
            seller_id=seller_id,
            product_id=order.product_id,
            cis_code=old_value,
            source="external_fbs",
            status=STATUS_APPLIED,
            applied_at=datetime.now(tz=UTC),
            packaging_task_line_id=order.packaging_task_line_id,
        )
        session.add(old_code)
        await session.flush()
        line = await session.get(PackagingTaskLine, order.packaging_task_line_id)
        assert line is not None
        line.qty_marking_external = 1
        session.add(
            FbsOrderMarking(
                order_id=order.order_id,
                tenant_id=tenant_id,
                kind=MARKING_KIND_SGTIN,
                value=old_value,
                source="operator",
                check_status=CHECK_STATUS_NEW,
                meta_status=META_STATUS_ACCEPTED,
                marking_code_id=old_code.id,
            )
        )
        await session.commit()
        old_code_id = old_code.id

    deleted: list[tuple[int, str]] = []

    async def fake_delete(
        client: object,
        *,
        api_token: str,
        order_id: int,
        key: str,
        marketplace_api_base: str | None = None,
    ) -> None:
        del client, api_token, marketplace_api_base
        deleted.append((order_id, key))

    monkeypatch.setattr(
        "app.services.fbs_kiz_service.delete_marketplace_order_meta",
        fake_delete,
    )
    _patch_wb_acceptance(monkeypatch)

    response = await async_client.post(
        "/operations/fbs-orders/kiz/commit",
        headers=headers,
        json={
            "idempotency_key": "kiz-confirmed-replace",
            "pairs": [
                {
                    "order_id": str(order.order_id),
                    "value": new_value,
                    "confirmed": True,
                }
            ],
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()[0]["status"] == "ok"
    assert deleted == [(order.wb_order_id, MARKING_KIND_SGTIN)]
    async with SessionLocal() as session:
        old_code = await session.get(MarkingCode, old_code_id)
        assert old_code is not None
        assert old_code.status == STATUS_VOID
        markings = list(
            (
                await session.execute(
                    select(FbsOrderMarking).where(
                        FbsOrderMarking.order_id == order.order_id
                    )
                )
            ).scalars()
        )
        assert len(markings) == 1
        assert markings[0].value == new_value
        assert markings[0].source == "operator"
        new_code = await session.get(MarkingCode, markings[0].marking_code_id)
        assert new_code is not None
        assert new_code.status == STATUS_APPLIED
        assert new_code.cis_code == new_value
        line = await session.get(PackagingTaskLine, order.packaging_task_line_id)
        assert line is not None
        assert line.qty_marking_external == 1
        void_event = (
            await session.execute(
                select(MarkingCodeEvent).where(
                    MarkingCodeEvent.code_id == old_code_id,
                    MarkingCodeEvent.event_type == EVENT_VOIDED,
                )
            )
        ).scalar_one()
        assert void_event.reason == "replaced_by_external_fbs_kiz"


@pytest.mark.asyncio
async def test_fbs_kiz_commit_success_creates_records_event_and_counter(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # TC-NEW-FBS-KIZ-004: successful commit persists the external KIZ lifecycle.
    headers, suffix = await _register_ff_admin(async_client)
    me_response = await async_client.get("/auth/me", headers=headers)
    assert me_response.status_code == 200, me_response.text
    actor_user_id = uuid.UUID(me_response.json()["id"])
    seller_id, warehouse_id, tenant_id = await _setup_seller_warehouse(
        async_client, headers, suffix
    )
    supply_id = await _create_supply(
        tenant_id=tenant_id,
        seller_id=seller_id,
        warehouse_id=warehouse_id,
        suffix=suffix,
    )
    order = await _create_order(
        tenant_id=tenant_id,
        seller_id=seller_id,
        warehouse_id=warehouse_id,
        supply_id=supply_id,
        suffix=suffix,
        wb_order_id=932201,
        sticker_code="SUCCESS-COMMIT",
        wb_barcode="SUCCESS-COMMIT-BAR",
        with_packaging=True,
    )
    assert order.packaging_task_line_id is not None
    sent = _patch_wb_acceptance(monkeypatch)
    value = _cis("SUCCESS001")

    response = await async_client.post(
        "/operations/fbs-orders/kiz/commit",
        headers=headers,
        json={
            "idempotency_key": "kiz-success",
            "pairs": [
                {
                    "order_id": str(order.order_id),
                    "value": value,
                    "confirmed": False,
                }
            ],
        },
    )

    assert response.status_code == 200, response.text
    assert response.json() == [
        {
            "order_id": str(order.order_id),
            "status": "ok",
            "code": "ok",
            "message": "ok",
        }
    ]
    assert sent == {order.wb_order_id: value}
    async with SessionLocal() as session:
        marking = (
            await session.execute(
                select(FbsOrderMarking).where(FbsOrderMarking.order_id == order.order_id)
            )
        ).scalar_one()
        assert marking.value == value
        assert marking.kind == MARKING_KIND_SGTIN
        assert marking.source == "operator"
        assert marking.created_by_user_id == actor_user_id
        assert marking.meta_status == META_STATUS_ACCEPTED
        assert marking.marking_code_id is not None

        code = await session.get(MarkingCode, marking.marking_code_id)
        assert code is not None
        assert code.source == "external_fbs"
        assert code.status == STATUS_APPLIED
        assert code.seller_id == seller_id
        assert code.product_id == order.product_id
        assert code.packaging_task_line_id == order.packaging_task_line_id
        assert code.cis_code == value
        assert code.pool_id is None
        assert code.import_batch_id is None
        assert code.label_artifact_pdf is None

        event = (
            await session.execute(
                select(MarkingCodeEvent).where(
                    MarkingCodeEvent.code_id == code.id,
                    MarkingCodeEvent.event_type == EVENT_APPLIED,
                )
            )
        ).scalar_one()
        assert event.actor_user_id == actor_user_id
        assert event.document_number == f"PKG-KIZ-{order.wb_order_id}"
        assert event.packaging_task_line_id == order.packaging_task_line_id

        line = await session.get(PackagingTaskLine, order.packaging_task_line_id)
        assert line is not None
        assert line.qty_marking_external == 1
