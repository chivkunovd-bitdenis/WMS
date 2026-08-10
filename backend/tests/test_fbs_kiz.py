from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient

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
from app.models.fbs_supply import FBS_DELIVERY_TYPE_WAREHOUSE_SC, FbsSupply
from app.models.product import Product
from app.services import fbs_kiz_service as kiz_svc

_GS = "\x1d"
_CLEAN_CIS = f"010460043993125321AbCxyz{_GS}91K1aZ{_GS}92Crypto~|#<GS>tail"


@dataclass(frozen=True)
class _SeededOrder:
    supply_id: uuid.UUID
    order_id: uuid.UUID
    wb_order_id: int
    product_name: str
    product_barcode: str
    seller_article: str


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

    warehouse_response = await async_client.post(
        "/warehouses",
        headers=headers,
        json={"name": "WH", "code": f"wh-{suffix[-8:]}"},
    )
    assert warehouse_response.status_code in (200, 201), warehouse_response.text

    me_response = await async_client.get("/auth/me", headers=headers)
    assert me_response.status_code == 200, me_response.text
    return (
        uuid.UUID(seller_response.json()["id"]),
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
) -> _SeededOrder:
    now = datetime.now(tz=UTC)
    product_name = f"KIZ product {wb_order_id}"
    seller_article = f"SKU-KIZ-{suffix}-{wb_order_id}"
    product_barcode = f"PROD-KIZ-{suffix}-{wb_order_id}"
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

        if marking is not None:
            marking.order_id = order.id
            marking.tenant_id = tenant_id
            session.add(marking)

        await session.commit()
        return _SeededOrder(
            supply_id=supply_id,
            order_id=order.id,
            wb_order_id=wb_order_id,
            product_name=product_name,
            product_barcode=wb_barcode or product_barcode,
            seller_article=seller_article,
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
