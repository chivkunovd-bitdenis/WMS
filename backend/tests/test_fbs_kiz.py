from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.db.session import SessionLocal
from app.models.fbs_order import (
    CHECK_STATUS_CHECKING,
    CHECK_STATUS_ERROR,
    CHECK_STATUS_NEW,
    CHECK_STATUS_OK,
    FBS_ORDER_STATUS_IN_DELIVERY,
    FBS_ORDER_STATUS_PACKED,
    MAPPING_STATUS_MAPPED,
    MARKING_KIND_SGTIN,
    META_STATUS_ACCEPTED,
    META_STATUS_ALLOWED_WITHOUT_CHECK,
    META_STATUS_MISSING,
    META_STATUS_PENDING,
    META_STATUS_REJECTED,
    META_STATUS_REPLACEMENT_REQUIRED,
    META_STATUS_UNKNOWN,
    RESERVE_STATUS_RESERVED,
    FbsOrder,
    FbsOrderMarking,
)
from app.models.fbs_packaging_fulfillment import FbsPackagingFulfillment
from app.models.fbs_supply import FBS_DELIVERY_TYPE_WAREHOUSE_SC, FbsSupply
from app.models.marking_code import (
    EVENT_APPLIED,
    EVENT_VOIDED,
    EVENT_WB_ORPHANED,
    STATUS_APPLIED,
    STATUS_AVAILABLE,
    STATUS_PRINTED,
    STATUS_RESERVED,
    STATUS_VOID,
    MarkingCode,
    MarkingCodeEvent,
)
from app.models.packaging_task import STATUS_IN_PROGRESS, PackagingTask, PackagingTaskLine
from app.models.product import Product
from app.models.storage_location import StorageLocation
from app.services import fbs_kiz_service as kiz_svc
from app.services import fbs_marking_service as fbs_marking_svc
from app.services import fbs_order_tape_print_service as tape_print_svc
from app.services import fbs_worklist_service as fbs_worklist_svc
from app.services import fbs_workspace_service as fbs_workspace_svc
from app.services import marking_code_service as mc_svc
from app.services.wildberries_errors import (
    MetaValidationFailItem,
    WildberriesBusinessError,
    WildberriesClientError,
)
from app.services.wildberries_fbs_client import MarketplaceMetaDetail, MarketplaceOrderMetaRow


@pytest.mark.parametrize(
    ("decision", "expected"),
    [
        ("filled", META_STATUS_ACCEPTED),
        ("optional", META_STATUS_ALLOWED_WITHOUT_CHECK),
        ("pending", META_STATUS_PENDING),
        ("required", None),
        ("invalid", META_STATUS_REJECTED),
        ("something-new", None),
    ],
)
def test_wb_decision_mapping_covers_safe_sync_states(
    decision: str, expected: str | None
) -> None:
    # TC-NEW-FBS-MARKING-001: WB decisions map to stable local statuses;
    # unknown decisions are fail-closed and do not become an acceptance.
    assert fbs_marking_svc.map_wb_decision_to_meta_status(decision) == expected


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
            # Карточка товара главнее задания WB: в задании лежит внутренний код WB
            # (префикс 20…), а на коробке — производственный из карточки. Печать и
            # экран сборки должны показывать то, что наклеено на товаре.
            product_barcode=product_barcode,
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


async def _seed_active_marking(
    *,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    order: _SeededOrder,
    value: str,
    code_source: str,
    marking_source: str,
    code_status: str,
    qty_marking_printed: int,
    qty_marking_external: int,
) -> uuid.UUID:
    assert order.packaging_task_line_id is not None
    async with SessionLocal() as session:
        code = MarkingCode(
            tenant_id=tenant_id,
            seller_id=seller_id,
            product_id=order.product_id,
            cis_code=value,
            source=code_source,
            status=code_status,
            applied_at=datetime.now(tz=UTC),
            packaging_task_line_id=order.packaging_task_line_id,
        )
        session.add(code)
        await session.flush()
        line = await session.get(PackagingTaskLine, order.packaging_task_line_id)
        assert line is not None
        line.qty_marking_printed = qty_marking_printed
        line.qty_marking_external = qty_marking_external
        session.add(
            FbsOrderMarking(
                order_id=order.order_id,
                tenant_id=tenant_id,
                kind=MARKING_KIND_SGTIN,
                value=value,
                source=marking_source,
                check_status=CHECK_STATUS_NEW,
                meta_status=META_STATUS_ACCEPTED,
                marking_code_id=code.id,
            )
        )
        await session.commit()
        return code.id


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


def test_normalize_scanned_cis_restores_separator_before_weight_ai() -> None:
    # TC-NEW-FBS-KIZ-002: variable AI 93 is separated before fixed weight AI 3103.
    raw = "0104607428679083215AbCdE~93dGVz~3103001500"

    value, hints = kiz_svc.normalize_scanned_cis(raw)

    assert value == f"0104607428679083215AbCdE{_GS}93dGVz{_GS}3103001500"
    assert hints == ["gs_substitute"]


def test_normalize_scanned_cis_repairs_russian_aim_prefix_after_layout() -> None:
    # TC-NEW-FBS-KIZ-002: a Russian-layout AIM prefix is repaired and stripped.
    raw = (
        "\u044a\u04322"
        "010460043993125321\u0424\u0438\u0421\u0447\u043d\u044f"
        "<GS>91\u041b1\u0444\u042f<GS>92\u0421\u043a\u043d\u0437\u0435\u0449"
    )

    value, hints = kiz_svc.normalize_scanned_cis(raw)

    assert value == f"010460043993125321AbCxyz{_GS}91K1aZ{_GS}92Crypto"
    assert hints == ["aim_prefix", "gs_substitute", "keyboard_layout"]


def test_windows_russian_keyboard_layout_mapping_is_complete() -> None:
    # TC-NEW-FBS-KIZ-002: every non-identical Windows RU key maps to its US key.
    russian = (
        "\u0451\u0439\u0446\u0443\u043a\u0435\u043d\u0433\u0448\u0449"
        "\u0437\u0445\u044a\u0444\u044b\u0432\u0430\u043f\u0440\u043e"
        "\u043b\u0434\u0436\u044d\u044f\u0447\u0441\u043c\u0438\u0442"
        "\u044c\u0431\u044e."
        "\u0401\u0419\u0426\u0423\u041a\u0415\u041d\u0413\u0428\u0429"
        "\u0417\u0425\u042a\u0424\u042b\u0412\u0410\u041f\u0420\u041e"
        "\u041b\u0414\u0416\u042d\u042f\u0427\u0421\u041c\u0418\u0422"
        "\u042c\u0411\u042e,"
        '"\u2116;:?/'
    )
    expected = (
        "`qwertyuiop[]asdfghjkl;'zxcvbnm,./"
        '~QWERTYUIOP{}ASDFGHJKL:"ZXCVBNM<>?'
        "@#$^&|"
    )

    assert russian.translate(kiz_svc._KEYBOARD_LAYOUT_TRANSLATION) == expected


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
    async with SessionLocal() as session:
        db_order = await session.get(FbsOrder, order.order_id)
        assert db_order is not None
        db_order.required_meta_json = [MARKING_KIND_SGTIN]
        await session.commit()
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

    workspace = await async_client.get(
        f"/operations/fbs-supplies/{supply_id}/workspace",
        headers=headers,
    )
    assert workspace.status_code == 200, workspace.text
    workspace_order = next(
        item
        for item in workspace.json()["orders"]
        if item["id"] == str(order.order_id)
    )
    assert workspace_order["metadata"]["states"][0]["source"] == "operator"


@pytest.mark.asyncio
async def test_fbs_kiz_delete_wb_error_does_not_change_records(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # TC-NEW-FBS-KIZ-009: WB delete failure is fail-closed; local rows stay intact.
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
        wb_order_id=932301,
        sticker_code="DELETE-WB-ERROR",
        wb_barcode="DELETE-WB-ERROR-BAR",
        with_packaging=True,
    )
    assert order.packaging_task_line_id is not None
    value = _cis("DELETEERR")
    async with SessionLocal() as session:
        code = MarkingCode(
            tenant_id=tenant_id,
            seller_id=seller_id,
            product_id=order.product_id,
            cis_code=value,
            source="external_fbs",
            status=STATUS_APPLIED,
            applied_at=datetime.now(tz=UTC),
            packaging_task_line_id=order.packaging_task_line_id,
        )
        session.add(code)
        await session.flush()
        line = await session.get(PackagingTaskLine, order.packaging_task_line_id)
        assert line is not None
        line.qty_marking_external = 1
        session.add(
            FbsOrderMarking(
                order_id=order.order_id,
                tenant_id=tenant_id,
                kind=MARKING_KIND_SGTIN,
                value=value,
                source="operator",
                check_status=CHECK_STATUS_NEW,
                meta_status=META_STATUS_ACCEPTED,
                marking_code_id=code.id,
            )
        )
        await session.commit()
        code_id = code.id

    async def fake_delete(
        client: object,
        *,
        api_token: str,
        order_id: int,
        key: str,
        marketplace_api_base: str | None = None,
    ) -> None:
        del client, api_token, order_id, key, marketplace_api_base
        raise WildberriesBusinessError("delete_failed", status_code=503)

    monkeypatch.setattr(
        "app.services.fbs_kiz_service.delete_marketplace_order_meta",
        fake_delete,
    )

    response = await async_client.delete(
        f"/operations/fbs-orders/{order.order_id}/kiz",
        headers=headers,
    )

    assert response.status_code == 502, response.text
    assert response.json()["detail"]["code"] == "wb_delete_failed_503"
    async with SessionLocal() as session:
        marking_count = await session.scalar(
            select(func.count(FbsOrderMarking.id)).where(
                FbsOrderMarking.order_id == order.order_id
            )
        )
        assert int(marking_count or 0) == 1
        code = await session.get(MarkingCode, code_id)
        assert code is not None
        assert code.status == STATUS_APPLIED
        line = await session.get(PackagingTaskLine, order.packaging_task_line_id)
        assert line is not None
        assert line.qty_marking_external == 1
        voided_count = await session.scalar(
            select(func.count(MarkingCodeEvent.id)).where(
                MarkingCodeEvent.code_id == code_id,
                MarkingCodeEvent.event_type == EVENT_VOIDED,
            )
        )
        assert int(voided_count or 0) == 0


@pytest.mark.asyncio
async def test_fbs_kiz_commit_same_pair_is_idempotent_without_second_wb_call(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # TC-NEW-FBS-KIZ-004: retrying the same active pair is a no-op success.
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
        wb_order_id=932401,
        sticker_code="IDEMPOTENT-COMMIT",
        wb_barcode="IDEMPOTENT-COMMIT-BAR",
        with_packaging=True,
    )
    assert order.packaging_task_line_id is not None
    value = _cis("IDEMPOTENT")
    sent: list[tuple[int, str]] = []

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
        sent.append((order_id, value))

    async def fake_meta_batch(
        client: object,
        *,
        api_token: str,
        order_ids: list[int],
        marketplace_api_base: str | None = None,
    ) -> list[MarketplaceOrderMetaRow]:
        del client, api_token, marketplace_api_base
        order_id = order_ids[0]
        assert sent == [(order_id, value)]
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

    payload = {
        "pairs": [
            {
                "order_id": str(order.order_id),
                "value": value,
                "confirmed": False,
            }
        ],
    }
    first = await async_client.post(
        "/operations/fbs-orders/kiz/commit",
        headers=headers,
        json={"idempotency_key": "kiz-idempotent-1", **payload},
    )
    second = await async_client.post(
        "/operations/fbs-orders/kiz/commit",
        headers=headers,
        json={"idempotency_key": "kiz-idempotent-2", **payload},
    )

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()[0]["status"] == "ok"
    assert second.json()[0]["status"] == "ok"
    assert sent == [(order.wb_order_id, value)]
    async with SessionLocal() as session:
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
        codes = list(
            (
                await session.execute(
                    select(MarkingCode).where(
                        MarkingCode.tenant_id == tenant_id,
                        MarkingCode.cis_code == value,
                    )
                )
            ).scalars()
        )
        assert len(codes) == 1
        line = await session.get(PackagingTaskLine, order.packaging_task_line_id)
        assert line is not None
        assert line.qty_marking_external == 1
        applied_events = await session.scalar(
            select(func.count(MarkingCodeEvent.id)).where(
                MarkingCodeEvent.code_id == codes[0].id,
                MarkingCodeEvent.event_type == EVENT_APPLIED,
            )
        )
        assert int(applied_events or 0) == 1


@pytest.mark.asyncio
async def test_fbs_kiz_external_marking_counts_as_printed_for_pool_and_gate(
    async_client: AsyncClient,
) -> None:
    # TC-NEW-FBS-KIZ-010 / TC-NEW-FBS-KIZ-011: external KIZ reduces print need.
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
    now = datetime.now(tz=UTC)
    order_ids: list[uuid.UUID] = []
    async with SessionLocal() as session:
        product = Product(
            tenant_id=tenant_id,
            seller_id=seller_id,
            name="KIZ mixed source product",
            sku_code=f"KIZ-MIX-{suffix[-8:]}",
            wb_nm_id=990001,
            wb_vendor_code="KIZ-MIX-ART",
            wb_chrt_id=990002,
            wb_barcode=f"KIZ-MIX-BAR-{suffix[-8:]}",
            requires_honest_sign=True,
        )
        task = PackagingTask(
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            status=STATUS_IN_PROGRESS,
            document_number=f"PKG-KIZ-MIX-{suffix[-8:]}",
        )
        location = StorageLocation(
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            code=f"KIZ-MIX-{suffix[-8:]}",
            barcode=f"KIZ-MIX-BAR-{suffix[-8:]}",
        )
        session.add_all([product, task, location])
        await session.flush()
        line = PackagingTaskLine(
            task_id=task.id,
            product_id=product.id,
            storage_location_id=location.id,
            qty_total=150,
            qty_suggested_packed=0,
            qty_confirmed_packed=0,
            qty_packed_in_task=150,
            qty_marking_printed=0,
            qty_marking_external=100,
        )
        session.add(line)
        await session.flush()
        supply = await session.get(FbsSupply, supply_id)
        assert supply is not None
        supply.packaging_task_id = task.id

        orders: list[FbsOrder] = []
        for index in range(150):
            order = FbsOrder(
                tenant_id=tenant_id,
                seller_id=seller_id,
                warehouse_id=warehouse_id,
                product_id=product.id,
                wb_order_id=940000 + index,
                wb_rid=f"rid-mix-{index}",
                wb_nm_id=product.wb_nm_id,
                wb_chrt_id=product.wb_chrt_id,
                wb_article=product.wb_vendor_code,
                wb_barcode=f"KIZ-MIX-ORDER-BAR-{index}",
                price=1000,
                is_legal=False,
                cargo_type="mgt",
                wb_office_id=42,
                wb_warehouse_id=99,
                can_pvz=False,
                supply_id=supply_id,
                sticker_code=f"KIZ-MIX-STICKER-{index}",
                status=FBS_ORDER_STATUS_PACKED,
                created_at_wb=now,
                deadline_at=now + timedelta(minutes=index),
                mapping_status=MAPPING_STATUS_MAPPED,
                reserve_status=RESERVE_STATUS_RESERVED,
                required_meta_json=[MARKING_KIND_SGTIN],
            )
            session.add(order)
            orders.append(order)
        await session.flush()
        order_ids = [order.id for order in orders]

        for index, order in enumerate(orders[:100]):
            value = _cis(f"MIXEXT{index:03d}")
            external_code = MarkingCode(
                tenant_id=tenant_id,
                seller_id=seller_id,
                product_id=product.id,
                cis_code=value,
                source="external_fbs",
                status=STATUS_APPLIED,
                applied_at=now,
                packaging_task_line_id=line.id,
            )
            session.add(external_code)
            await session.flush()
            session.add(
                FbsOrderMarking(
                    order_id=order.id,
                    tenant_id=tenant_id,
                    kind=MARKING_KIND_SGTIN,
                    value=value,
                    source="operator",
                    check_status=CHECK_STATUS_NEW,
                    meta_status=META_STATUS_ACCEPTED,
                    marking_code_id=external_code.id,
                )
            )

        for index in range(50):
            session.add(
                MarkingCode(
                    tenant_id=tenant_id,
                    seller_id=seller_id,
                    product_id=product.id,
                    cis_code=_cis(f"MIXPOOL{index:03d}"),
                    source="pool",
                    status=STATUS_AVAILABLE,
                )
            )
        await session.commit()
        task_id = task.id
        line_id = line.id
        product_id = product.id

    async with SessionLocal() as session:
        orders = list(
            (
                await session.execute(
                    select(FbsOrder).where(FbsOrder.id.in_(order_ids))
                )
            ).scalars()
        )
        marking_pool = await fbs_workspace_svc._build_marking_pool(
            session,
            tenant_id,
            orders,
        )
        assert marking_pool["required"] == 50
        assert marking_pool["available"] == 50
        assert marking_pool["shortage"] == 0
        assert marking_pool["orders_without_code"] == []

        first_marking = (
            await session.execute(
                select(FbsOrderMarking).where(
                    FbsOrderMarking.order_id == order_ids[0]
                )
            )
        ).scalar_one()
        first_order = await session.get(FbsOrder, order_ids[0])
        assert first_order is not None
        state = fbs_marking_svc.build_order_metadata(first_order, [first_marking])[
            "states"
        ][0]
        assert state["source"] == "operator"
        missing_order = await session.get(FbsOrder, order_ids[-1])
        assert missing_order is not None
        missing_state = fbs_marking_svc.build_order_metadata(missing_order, [])["states"][0]
        assert missing_state["source"] is None

    async with SessionLocal() as session:
        first_preview = await mc_svc.print_all_for_packaging_task(
            session,
            tenant_id,
            task_id,
            acting_user_id=actor_user_id,
            allow_partial=False,
            dry_run=True,
        )
        assert first_preview.quantity == 50
        assert first_preview.lines[0].quantity == 50

    async with SessionLocal() as session:
        manual = await mc_svc.print_codes_for_packaging_line(
            session,
            tenant_id,
            line_id,
            acting_user_id=actor_user_id,
            units_to_print=10,
        )
        assert manual.quantity == 10

    async with SessionLocal() as session:
        second_preview = await mc_svc.print_all_for_packaging_task(
            session,
            tenant_id,
            task_id,
            acting_user_id=actor_user_id,
            allow_partial=False,
            dry_run=True,
        )
        assert second_preview.quantity == 40
        assert second_preview.lines[0].quantity == 40

    async with SessionLocal() as session:
        printed_rest = await mc_svc.print_all_for_packaging_task(
            session,
            tenant_id,
            task_id,
            acting_user_id=actor_user_id,
            allow_partial=False,
        )
        assert printed_rest.quantity == 40
        line = await session.get(PackagingTaskLine, line_id)
        assert line is not None
        await mc_svc.assert_packaging_line_marking_done(session, tenant_id, line)
        assert line.qty_marking_printed == 50
        assert line.qty_marking_external == 100
        printed_count = await session.scalar(
            select(func.count(MarkingCode.id)).where(
                MarkingCode.tenant_id == tenant_id,
                MarkingCode.product_id == product_id,
                MarkingCode.status == STATUS_PRINTED,
            )
        )
        assert int(printed_count or 0) == 50


@pytest.mark.asyncio
async def test_fbs_kiz_validate_rejects_available_pool_code_owner_mismatches(
    async_client: AsyncClient,
) -> None:
    # TC-NEW-FBS-KIZ-003: available pool codes keep seller and product ownership.
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
        wb_order_id=950101,
        sticker_code="POOL-OWNER-VALIDATE",
        wb_barcode="POOL-OWNER-VALIDATE-BAR",
    )
    other_seller_response = await async_client.post(
        "/sellers",
        headers=headers,
        json={"name": f"Other seller {suffix}"},
    )
    assert other_seller_response.status_code in (200, 201), other_seller_response.text
    other_seller_id = uuid.UUID(other_seller_response.json()["id"])
    cross_seller_value = _cis("CROSSSELLER")
    wrong_product_value = _cis("WRONGPRODUCT")
    async with SessionLocal() as session:
        other_product = Product(
            tenant_id=tenant_id,
            seller_id=seller_id,
            name="Other pool product",
            sku_code=f"OTHER-POOL-{suffix}",
        )
        session.add(other_product)
        await session.flush()
        session.add_all(
            [
                MarkingCode(
                    tenant_id=tenant_id,
                    seller_id=other_seller_id,
                    product_id=order.product_id,
                    cis_code=cross_seller_value,
                    source="pool",
                    status=STATUS_AVAILABLE,
                ),
                MarkingCode(
                    tenant_id=tenant_id,
                    seller_id=seller_id,
                    product_id=other_product.id,
                    cis_code=wrong_product_value,
                    source="pool",
                    status=STATUS_AVAILABLE,
                ),
            ]
        )
        await session.commit()

    cross_seller = await async_client.post(
        "/operations/fbs-orders/kiz/validate",
        headers=headers,
        json={"order_id": str(order.order_id), "value": cross_seller_value},
    )
    wrong_product = await async_client.post(
        "/operations/fbs-orders/kiz/validate",
        headers=headers,
        json={"order_id": str(order.order_id), "value": wrong_product_value},
    )

    assert cross_seller.status_code == 409, cross_seller.text
    assert cross_seller.json()["detail"]["code"] == "cross_seller_code"
    assert wrong_product.status_code == 409, wrong_product.text
    assert wrong_product.json()["detail"]["code"] == "code_product_mismatch"


@pytest.mark.asyncio
async def test_fbs_kiz_commit_claims_available_pool_code_without_reclassifying_it(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # TC-NEW-FBS-KIZ-004: a known pool KIZ stays pool-owned and uses the printed counter.
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
        wb_order_id=950201,
        sticker_code="POOL-CLAIM-COMMIT",
        wb_barcode="POOL-CLAIM-COMMIT-BAR",
        with_packaging=True,
    )
    assert order.packaging_task_line_id is not None
    value = _cis("POOLCLAIM")
    async with SessionLocal() as session:
        code = MarkingCode(
            tenant_id=tenant_id,
            seller_id=seller_id,
            product_id=order.product_id,
            cis_code=value,
            source="pool",
            status=STATUS_AVAILABLE,
            label_artifact_pdf=b"original-pool-label",
        )
        session.add(code)
        await session.commit()
        code_id = code.id
    _patch_wb_acceptance(monkeypatch)

    response = await async_client.post(
        "/operations/fbs-orders/kiz/commit",
        headers=headers,
        json={
            "idempotency_key": "claim-known-pool-code",
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
    assert response.json()[0]["status"] == "ok"
    async with SessionLocal() as session:
        claimed_code = await session.get(MarkingCode, code_id)
        assert claimed_code is not None
        assert claimed_code.source == "pool"
        assert claimed_code.status == STATUS_RESERVED
        assert claimed_code.seller_id == seller_id
        assert claimed_code.product_id == order.product_id
        assert claimed_code.label_artifact_pdf == b"original-pool-label"
        marking = (
            await session.execute(
                select(FbsOrderMarking).where(FbsOrderMarking.order_id == order.order_id)
            )
        ).scalar_one()
        assert marking.source == "pool"
        assert marking.marking_code_id == code_id
        line = await session.get(PackagingTaskLine, order.packaging_task_line_id)
        assert line is not None
        assert line.qty_marking_printed == 1
        assert line.qty_marking_external == 0


@pytest.mark.asyncio
async def test_fbs_kiz_replacement_runs_registry_checks_before_wb_delete(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # TC-NEW-FBS-KIZ-006: a locally occupied replacement never deletes the old WB KIZ.
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
        wb_order_id=950301,
        sticker_code="LOCAL-CHECK-BEFORE-DELETE",
        wb_barcode="LOCAL-CHECK-BEFORE-DELETE-BAR",
        with_packaging=True,
    )
    old_value = _cis("LOCALOLD")
    new_value = _cis("LOCALBUSY")
    await _seed_active_marking(
        tenant_id=tenant_id,
        seller_id=seller_id,
        order=order,
        value=old_value,
        code_source="external_fbs",
        marking_source="operator",
        code_status=STATUS_APPLIED,
        qty_marking_printed=0,
        qty_marking_external=1,
    )
    async with SessionLocal() as session:
        session.add(
            MarkingCode(
                tenant_id=tenant_id,
                seller_id=seller_id,
                product_id=order.product_id,
                cis_code=new_value,
                source="pool",
                status=STATUS_APPLIED,
            )
        )
        await session.commit()
    deleted: list[int] = []

    async def fake_delete(
        client: object,
        *,
        api_token: str,
        order_id: int,
        key: str,
        marketplace_api_base: str | None = None,
    ) -> None:
        del client, api_token, key, marketplace_api_base
        deleted.append(order_id)

    monkeypatch.setattr(
        "app.services.fbs_kiz_service.delete_marketplace_order_meta",
        fake_delete,
    )

    response = await async_client.post(
        "/operations/fbs-orders/kiz/commit",
        headers=headers,
        json={
            "idempotency_key": "local-check-before-delete",
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
    assert response.json()[0]["code"] == "duplicate_kiz"
    assert deleted == []


@pytest.mark.asyncio
async def test_fbs_kiz_replacement_restores_old_wb_value_when_new_value_is_rejected(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # TC-NEW-FBS-KIZ-006: failed replacement compensates WB before rolling back locally.
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
        wb_order_id=950401,
        sticker_code="RESTORE-OLD-KIZ",
        wb_barcode="RESTORE-OLD-KIZ-BAR",
        with_packaging=True,
    )
    old_value = _cis("RESTOREOLD")
    new_value = _cis("REJECTNEW")
    old_code_id = await _seed_active_marking(
        tenant_id=tenant_id,
        seller_id=seller_id,
        order=order,
        value=old_value,
        code_source="external_fbs",
        marking_source="operator",
        code_status=STATUS_APPLIED,
        qty_marking_printed=0,
        qty_marking_external=1,
    )
    wb_value: dict[str, str | None] = {"value": old_value}
    calls: list[tuple[str, str | None]] = []

    async def fake_delete(
        client: object,
        *,
        api_token: str,
        order_id: int,
        key: str,
        marketplace_api_base: str | None = None,
    ) -> None:
        del client, api_token, order_id, key, marketplace_api_base
        calls.append(("delete", wb_value["value"]))
        wb_value["value"] = None

    async def reject_new_put(
        client: object,
        *,
        api_token: str,
        order_id: int,
        kind: str,
        value: str,
        marketplace_api_base: str | None = None,
    ) -> None:
        del client, api_token, kind, marketplace_api_base
        calls.append(("put_new", value))
        raise WildberriesBusinessError(
            "meta_validation_fail",
            status_code=409,
            meta_validation=[
                MetaValidationFailItem(
                    order_id=order_id,
                    key=MARKING_KIND_SGTIN,
                    value=value,
                    decision="invalid",
                    reason="bad replacement",
                )
            ],
        )

    async def restore_old_put(
        client: object,
        *,
        api_token: str,
        order_id: int,
        kind: str,
        value: str,
        marketplace_api_base: str | None = None,
    ) -> None:
        del client, api_token, order_id, kind, marketplace_api_base
        calls.append(("restore_old", value))
        wb_value["value"] = value

    monkeypatch.setattr(
        "app.services.fbs_kiz_service.delete_marketplace_order_meta",
        fake_delete,
    )
    monkeypatch.setattr(
        "app.services.fbs_marking_service.put_marketplace_order_meta",
        reject_new_put,
    )
    monkeypatch.setattr(
        "app.services.fbs_kiz_service.put_marketplace_order_meta",
        restore_old_put,
    )

    response = await async_client.post(
        "/operations/fbs-orders/kiz/commit",
        headers=headers,
        json={
            "idempotency_key": "restore-old-after-reject",
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
    assert response.json()[0]["code"] == "meta_validation_fail"
    assert calls == [
        ("delete", old_value),
        ("put_new", new_value),
        ("delete", None),
        ("restore_old", old_value),
    ]
    assert wb_value["value"] == old_value
    async with SessionLocal() as session:
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
        assert markings[0].value == old_value
        assert markings[0].meta_status == META_STATUS_ACCEPTED
        old_code = await session.get(MarkingCode, old_code_id)
        assert old_code is not None
        assert old_code.status == STATUS_APPLIED
        new_code_count = await session.scalar(
            select(func.count(MarkingCode.id)).where(
                MarkingCode.tenant_id == tenant_id,
                MarkingCode.cis_code == new_value,
            )
        )
        assert int(new_code_count or 0) == 0


@pytest.mark.asyncio
async def test_fbs_kiz_replacement_persists_reason_when_wb_restore_also_fails(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # TC-NEW-FBS-KIZ-006: an uncompensated WB replacement is explicitly blocking.
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
        wb_order_id=950501,
        sticker_code="RESTORE-FAILS",
        wb_barcode="RESTORE-FAILS-BAR",
        with_packaging=True,
    )
    old_value = _cis("RESTOREFAILOLD")
    new_value = _cis("RESTOREFAILNEW")
    await _seed_active_marking(
        tenant_id=tenant_id,
        seller_id=seller_id,
        order=order,
        value=old_value,
        code_source="external_fbs",
        marking_source="operator",
        code_status=STATUS_APPLIED,
        qty_marking_printed=0,
        qty_marking_external=1,
    )

    async def fake_delete(
        client: object,
        *,
        api_token: str,
        order_id: int,
        key: str,
        marketplace_api_base: str | None = None,
    ) -> None:
        del client, api_token, order_id, key, marketplace_api_base

    async def reject_new_put(
        client: object,
        *,
        api_token: str,
        order_id: int,
        kind: str,
        value: str,
        marketplace_api_base: str | None = None,
    ) -> None:
        del client, api_token, order_id, kind, value, marketplace_api_base
        raise WildberriesClientError("upstream_error", status_code=503)

    async def fail_restore_put(
        client: object,
        *,
        api_token: str,
        order_id: int,
        kind: str,
        value: str,
        marketplace_api_base: str | None = None,
    ) -> None:
        del client, api_token, order_id, kind, value, marketplace_api_base
        raise WildberriesClientError("transport_error")

    monkeypatch.setattr(
        "app.services.fbs_kiz_service.delete_marketplace_order_meta",
        fake_delete,
    )
    monkeypatch.setattr(
        "app.services.fbs_marking_service.put_marketplace_order_meta",
        reject_new_put,
    )
    monkeypatch.setattr(
        "app.services.fbs_kiz_service.put_marketplace_order_meta",
        fail_restore_put,
    )

    response = await async_client.post(
        "/operations/fbs-orders/kiz/commit",
        headers=headers,
        json={
            "idempotency_key": "persist-restore-failure",
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
    assert response.json()[0]["code"] == "wb_replacement_restore_failed"
    async with SessionLocal() as session:
        marking = (
            await session.execute(
                select(FbsOrderMarking).where(FbsOrderMarking.order_id == order.order_id)
            )
        ).scalar_one()
        assert marking.value == old_value
        assert marking.meta_status == META_STATUS_REPLACEMENT_REQUIRED
        assert marking.reason is not None
        assert "replacement_failed_and_restore_failed" in marking.reason
        assert "wb_upstream_error_503" in marking.reason
        assert "wb_transport_error" in marking.reason
        line = await session.get(PackagingTaskLine, order.packaging_task_line_id)
        assert line is not None
        assert line.qty_marking_external == 1


@pytest.mark.asyncio
async def test_fbs_kiz_pool_to_external_replacement_does_not_double_count_unit(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # TC-NEW-FBS-KIZ-006: replacing a printed pool KIZ keeps one counted unit.
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
        wb_order_id=950601,
        sticker_code="POOL-TO-EXTERNAL",
        wb_barcode="POOL-TO-EXTERNAL-BAR",
        with_packaging=True,
    )
    old_value = _cis("PRINTEDPOOL")
    new_value = _cis("NEWEXTERNAL")
    await _seed_active_marking(
        tenant_id=tenant_id,
        seller_id=seller_id,
        order=order,
        value=old_value,
        code_source="pool",
        marking_source="pool",
        code_status=STATUS_PRINTED,
        qty_marking_printed=1,
        qty_marking_external=0,
    )

    async def fake_delete(
        client: object,
        *,
        api_token: str,
        order_id: int,
        key: str,
        marketplace_api_base: str | None = None,
    ) -> None:
        del client, api_token, order_id, key, marketplace_api_base

    monkeypatch.setattr(
        "app.services.fbs_kiz_service.delete_marketplace_order_meta",
        fake_delete,
    )
    _patch_wb_acceptance(monkeypatch)

    response = await async_client.post(
        "/operations/fbs-orders/kiz/commit",
        headers=headers,
        json={
            "idempotency_key": "pool-to-external-no-double-count",
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
    async with SessionLocal() as session:
        line = await session.get(PackagingTaskLine, order.packaging_task_line_id)
        assert line is not None
        assert line.qty_marking_printed == 1
        assert line.qty_marking_external == 0
        assert line.qty_marking_printed + line.qty_marking_external == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("reprint", [False, True])
async def test_fbs_order_tape_refuses_print_for_operator_kiz(
    async_client: AsyncClient,
    reprint: bool,
) -> None:
    # TC-NEW-FBS-KIZ-010: print and reprint cannot issue a pool label over operator KIZ.
    headers, suffix = await _register_ff_admin(async_client)
    actor_response = await async_client.get("/auth/me", headers=headers)
    assert actor_response.status_code == 200, actor_response.text
    actor_user_id = uuid.UUID(actor_response.json()["id"])
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
        wb_order_id=950701 + int(reprint),
        sticker_code=f"OPERATOR-PRINT-{reprint}",
        wb_barcode=f"OPERATOR-PRINT-BAR-{reprint}",
        with_packaging=True,
    )
    async with SessionLocal() as session:
        db_order = await session.get(FbsOrder, order.order_id)
        assert db_order is not None
        db_order.required_meta_json = [MARKING_KIND_SGTIN]
        await session.commit()
    await _seed_active_marking(
        tenant_id=tenant_id,
        seller_id=seller_id,
        order=order,
        value=_cis(f"OPPRINT{int(reprint)}"),
        code_source="external_fbs",
        marking_source="operator",
        code_status=STATUS_APPLIED,
        qty_marking_printed=0,
        qty_marking_external=1,
    )

    async with SessionLocal() as session:
        result = await tape_print_svc.print_fbs_order_tape(
            session,
            tenant_id,
            supply_id,
            order_ids=[order.order_id],
            layout={"units": [{"block": "cz", "copies": 1}]},
            allow_partial=True,
            include_order_qr=False,
            reprint=reprint,
            actor_user_id=actor_user_id,
            http_client=async_client,
        )

    assert result.orders == []
    assert len(result.order_errors) == 1
    assert result.order_errors[0].code == "operator_kiz_print_forbidden"


@pytest.mark.asyncio
async def test_fbs_marking_readers_prefer_active_row_over_newer_rejected_row(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # TC-NEW-FBS-KIZ-008: a rejected history row never shadows the active KIZ.
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
        wb_order_id=950801,
        sticker_code="ACTIVE-OVER-REJECTED",
        wb_barcode="ACTIVE-OVER-REJECTED-BAR",
    )
    active_value = _cis("ACTIVEROW")
    rejected_value = _cis("REJECTEDROW")
    now = datetime.now(tz=UTC)
    async with SessionLocal() as session:
        db_order = await session.get(FbsOrder, order.order_id)
        assert db_order is not None
        db_order.required_meta_json = [MARKING_KIND_SGTIN]
        session.add_all(
            [
                FbsOrderMarking(
                    order_id=order.order_id,
                    tenant_id=tenant_id,
                    kind=MARKING_KIND_SGTIN,
                    value=active_value,
                    source="operator",
                    check_status=CHECK_STATUS_NEW,
                    meta_status=META_STATUS_ACCEPTED,
                    created_at=now,
                ),
                FbsOrderMarking(
                    order_id=order.order_id,
                    tenant_id=tenant_id,
                    kind=MARKING_KIND_SGTIN,
                    value=rejected_value,
                    source="pool",
                    check_status=CHECK_STATUS_NEW,
                    meta_status=META_STATUS_REJECTED,
                    reason="old rejection",
                    created_at=now + timedelta(minutes=1),
                ),
            ]
        )
        await session.commit()

    async def fake_meta_batch(
        client: object,
        *,
        api_token: str,
        order_ids: list[int],
        marketplace_api_base: str | None = None,
    ) -> list[MarketplaceOrderMetaRow]:
        del client, api_token, marketplace_api_base
        return [
            MarketplaceOrderMetaRow(
                order_id=order_ids[0],
                meta_details=(
                    MarketplaceMetaDetail(
                        key=MARKING_KIND_SGTIN,
                        value=active_value,
                        decision="accepted",
                    ),
                ),
                meta={
                    MARKING_KIND_SGTIN: [
                        {"value": active_value, "checkStatus": "error"},
                        {"value": rejected_value, "checkStatus": "ok"},
                    ]
                },
            )
        ]

    monkeypatch.setattr(
        "app.services.fbs_marking_service.fetch_marketplace_orders_meta_batch",
        fake_meta_batch,
    )
    async with SessionLocal() as session:
        db_order = (
            await session.execute(
                select(FbsOrder)
                .where(FbsOrder.id == order.order_id)
                .options(selectinload(FbsOrder.markings))
            )
        ).scalar_one()
        markings = await fbs_marking_svc._sync_order_meta_from_wb(
            session,
            db_order,
            async_client,
            "test-token",
        )
        metadata = fbs_marking_svc.build_order_metadata(db_order, markings)
        worklist_metadata = fbs_worklist_svc._build_metadata(db_order, markings)
        current = tape_print_svc._existing_sgtin_marking(db_order)
        rejected = next(marking for marking in markings if marking.value == rejected_value)

    assert metadata["states"][0]["status"] == META_STATUS_ACCEPTED
    assert metadata["states"][0]["source"] == "operator"
    assert metadata["delivery_allowed"] is True
    assert worklist_metadata["states"][0]["status"] == META_STATUS_ACCEPTED
    assert current is not None
    assert current.value == active_value
    # Deprecated row.meta must not override either the current or historical row.
    assert rejected.meta_status == META_STATUS_REJECTED


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("decision", "wb_value", "expected_status", "expected_check_status"),
    [
        ("filled", "same", META_STATUS_ACCEPTED, "ok"),
        ("optional", "same", META_STATUS_ALLOWED_WITHOUT_CHECK, "no_check"),
        ("pending", "same", META_STATUS_PENDING, CHECK_STATUS_CHECKING),
        ("required", None, META_STATUS_MISSING, CHECK_STATUS_NEW),
        ("invalid", "same", META_STATUS_REJECTED, CHECK_STATUS_ERROR),
        ("unrecognized", "same", META_STATUS_UNKNOWN, CHECK_STATUS_ERROR),
        ("required", "same", META_STATUS_UNKNOWN, CHECK_STATUS_NEW),
        ("filled", "other", META_STATUS_REPLACEMENT_REQUIRED, CHECK_STATUS_ERROR),
        ("invalid", "other", META_STATUS_REPLACEMENT_REQUIRED, CHECK_STATUS_ERROR),
    ],
)
async def test_fbs_marking_wb_meta_decision_is_safe_and_preserves_raw_detail(
    async_client: AsyncClient,
    decision: str,
    wb_value: str | None,
    expected_status: str,
    expected_check_status: str,
) -> None:
    # TC-NEW-FBS-MARKING-001: Given a returned WB detail, When its decision is
    # applied, Then its raw payload and a fail-closed compatible status are saved.
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_warehouse(
        async_client, headers, suffix
    )
    supply_id = await _create_supply(
        tenant_id=tenant_id, seller_id=seller_id, warehouse_id=warehouse_id, suffix=suffix
    )
    value = _cis(f"SYNC-{decision}")
    order = await _create_order(
        tenant_id=tenant_id,
        seller_id=seller_id,
        warehouse_id=warehouse_id,
        supply_id=supply_id,
        suffix=suffix,
        wb_order_id=951000 + len(decision),
        sticker_code="WB-META-SYNC",
        wb_barcode="WB-META-SYNC-BAR",
        marking=FbsOrderMarking(
            kind=MARKING_KIND_SGTIN,
            value=value,
            source="operator",
            check_status=CHECK_STATUS_NEW,
            meta_status=META_STATUS_ACCEPTED,
        ),
    )
    remote_value = value if wb_value == "same" else (_cis("OTHER") if wb_value else None)
    batch = [
        MarketplaceOrderMetaRow(
            order_id=order.wb_order_id,
            meta_details=(
                MarketplaceMetaDetail(
                    key=MARKING_KIND_SGTIN,
                    value=remote_value,
                    decision=decision,
                    reason="WB reason",
                ),
            ),
        )
    ]
    async with SessionLocal() as session:
        db_order = await session.get(FbsOrder, order.order_id)
        assert db_order is not None
        markings = await fbs_marking_svc._sync_order_meta_from_wb(
            session, db_order, async_client, "test-token", meta_batch=batch
        )
        await session.commit()
        remote_summary = db_order.meta_details_json

    marking = markings[0]
    assert marking.meta_status == expected_status
    assert marking.check_status == expected_check_status
    assert marking.reason == "WB reason"
    assert marking.meta_details_json == {
        "decision": decision,
        "value": remote_value,
        "reason": "WB reason",
    }
    assert remote_summary[MARKING_KIND_SGTIN] == {
        "status": (
            fbs_marking_svc.map_wb_decision_to_meta_status(decision)
            or META_STATUS_UNKNOWN
        ),
        "value": remote_value,
        "decision": decision,
        "reason": "WB reason",
    }


@pytest.mark.asyncio
async def test_fbs_marking_partial_wb_row_is_unknown_without_fresh_check_time(
    async_client: AsyncClient,
) -> None:
    # TC-NEW-FBS-MARKING-001: negative — a row without the expected kind is not
    # a successful check and must not overwrite the prior KIZ payload or timestamp.
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_warehouse(
        async_client, headers, suffix
    )
    supply_id = await _create_supply(
        tenant_id=tenant_id, seller_id=seller_id, warehouse_id=warehouse_id, suffix=suffix
    )
    value = _cis("PARTIAL")
    order = await _create_order(
        tenant_id=tenant_id,
        seller_id=seller_id,
        warehouse_id=warehouse_id,
        supply_id=supply_id,
        suffix=suffix,
        wb_order_id=951099,
        sticker_code="WB-META-PARTIAL",
        wb_barcode="WB-META-PARTIAL-BAR",
        marking=FbsOrderMarking(
            kind=MARKING_KIND_SGTIN,
            value=value,
            source="operator",
            check_status=CHECK_STATUS_NEW,
            meta_status=META_STATUS_ACCEPTED,
            meta_details_json={"kept": True},
        ),
    )
    async with SessionLocal() as session:
        db_order = await session.get(FbsOrder, order.order_id)
        assert db_order is not None
        markings = await fbs_marking_svc._sync_order_meta_from_wb(
            session,
            db_order,
            async_client,
            "test-token",
            meta_batch=[
                MarketplaceOrderMetaRow(
                    order_id=order.wb_order_id,
                    meta_details=(
                        MarketplaceMetaDetail(
                            key="future_wb_key",
                            value="remote-only-value",
                            decision="future_decision",
                            reason="future reason",
                        ),
                    ),
                )
            ],
        )
        await session.commit()
        remote_summary = db_order.meta_details_json

    assert markings[0].meta_status == META_STATUS_UNKNOWN
    assert markings[0].meta_details_json == {"kept": True}
    assert markings[0].check_status == CHECK_STATUS_ERROR
    assert remote_summary == {
        "future_wb_key": {
            "status": META_STATUS_UNKNOWN,
            "value": "remote-only-value",
            "decision": "future_decision",
            "reason": "future reason",
        }
    }
    async with SessionLocal() as session:
        refreshed = await session.get(FbsOrder, order.order_id)
        assert refreshed is not None
        assert refreshed.metadata_last_checked_at is None


@pytest.mark.asyncio
async def test_fbs_marking_omitted_wb_row_clears_stale_verdict_only(
    async_client: AsyncClient,
) -> None:
    # TC-NEW-FBS-MARKING-001: negative — an order omitted from a successful
    # batch becomes unknown without erasing its KIZ binding, lifecycle, raw
    # detail, reason, or last successful check time.
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_warehouse(
        async_client, headers, suffix
    )
    supply_id = await _create_supply(
        tenant_id=tenant_id, seller_id=seller_id, warehouse_id=warehouse_id, suffix=suffix
    )
    order = await _create_order(
        tenant_id=tenant_id,
        seller_id=seller_id,
        warehouse_id=warehouse_id,
        supply_id=supply_id,
        suffix=suffix,
        wb_order_id=951100,
        sticker_code="WB-META-OMITTED",
        wb_barcode="WB-META-OMITTED-BAR",
        with_packaging=True,
    )
    value = _cis("OMITTED")
    code_id = await _seed_active_marking(
        tenant_id=tenant_id,
        seller_id=seller_id,
        order=order,
        value=value,
        code_source="pool",
        marking_source="pool",
        code_status=STATUS_RESERVED,
        qty_marking_printed=1,
        qty_marking_external=0,
    )
    previous_check = datetime.now(tz=UTC) - timedelta(hours=1)
    async with SessionLocal() as session:
        db_order = await session.get(FbsOrder, order.order_id)
        marking = await session.scalar(
            select(FbsOrderMarking).where(FbsOrderMarking.order_id == order.order_id)
        )
        assert db_order is not None
        assert marking is not None
        db_order.metadata_last_checked_at = previous_check
        marking.meta_status = META_STATUS_ACCEPTED
        marking.check_status = CHECK_STATUS_OK
        marking.reason = "previous WB reason"
        marking.meta_details_json = {"decision": "filled", "value": value}
        await session.commit()

    async with SessionLocal() as session:
        db_order = await session.get(FbsOrder, order.order_id)
        assert db_order is not None
        markings = await fbs_marking_svc._sync_order_meta_from_wb(
            session, db_order, async_client, "test-token", meta_batch=[]
        )
        await session.commit()

    marking = markings[0]
    assert marking.meta_status == META_STATUS_UNKNOWN
    assert marking.check_status == CHECK_STATUS_ERROR
    assert marking.marking_code_id == code_id
    assert marking.reason == "previous WB reason"
    assert marking.meta_details_json == {"decision": "filled", "value": value}
    async with SessionLocal() as session:
        refreshed_order = await session.get(FbsOrder, order.order_id)
        refreshed_code = await session.get(MarkingCode, code_id)
        assert refreshed_order is not None
        assert refreshed_order.metadata_last_checked_at == previous_check.replace(tzinfo=None)
        assert refreshed_code is not None
        assert refreshed_code.status == STATUS_RESERVED


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("decision", "remote_value", "expected_status"),
    [
        ("required", None, META_STATUS_MISSING),
        ("invalid", "other", META_STATUS_REPLACEMENT_REQUIRED),
    ],
)
async def test_fbs_marking_orphaned_audit_is_created_once_for_concurrent_and_repeated_mismatch(
    async_client: AsyncClient,
    decision: str,
    remote_value: str | None,
    expected_status: str,
) -> None:
    # TC-NEW-FBS-MARKING-001: Given WB repeatedly reports a missing or different
    # KIZ, When two workers sync concurrently and one repeats, Then the binding
    # stays intact and there is one audit fact.
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_warehouse(
        async_client, headers, suffix
    )
    supply_id = await _create_supply(
        tenant_id=tenant_id, seller_id=seller_id, warehouse_id=warehouse_id, suffix=suffix
    )
    order = await _create_order(
        tenant_id=tenant_id,
        seller_id=seller_id,
        warehouse_id=warehouse_id,
        supply_id=supply_id,
        suffix=suffix,
        wb_order_id=951200,
        sticker_code="WB-META-AUDIT",
        wb_barcode="WB-META-AUDIT-BAR",
        with_packaging=True,
    )
    value = _cis("AUDIT")
    wb_value = _cis("AUDIT-OTHER") if remote_value == "other" else None
    code_id = await _seed_active_marking(
        tenant_id=tenant_id,
        seller_id=seller_id,
        order=order,
        value=value,
        code_source="pool",
        marking_source="pool",
        code_status=STATUS_RESERVED,
        qty_marking_printed=1,
        qty_marking_external=0,
    )
    batch = [
        MarketplaceOrderMetaRow(
            order_id=order.wb_order_id,
            meta_details=(
                MarketplaceMetaDetail(
                    key=MARKING_KIND_SGTIN,
                    value=wb_value,
                    decision=decision,
                    reason="mismatch at WB",
                ),
            ),
        )
    ]
    async def sync_once() -> None:
        async with SessionLocal() as session:
            db_order = await session.get(FbsOrder, order.order_id)
            assert db_order is not None
            await fbs_marking_svc._sync_order_meta_from_wb(
                session, db_order, async_client, "test-token", meta_batch=batch
            )
            await session.commit()

    await asyncio.gather(sync_once(), sync_once())
    await sync_once()

    async with SessionLocal() as session:
        marking = await session.scalar(
            select(FbsOrderMarking).where(FbsOrderMarking.order_id == order.order_id)
        )
        code = await session.get(MarkingCode, code_id)
        audit_count = await session.scalar(
            select(func.count(MarkingCodeEvent.id)).where(
                MarkingCodeEvent.code_id == code_id,
                MarkingCodeEvent.event_type == EVENT_WB_ORPHANED,
            )
        )
    assert marking is not None
    assert marking.meta_status == expected_status
    assert marking.marking_code_id == code_id
    assert code is not None
    assert code.status == STATUS_RESERVED
    assert audit_count == 1


@pytest.mark.asyncio
async def test_fbs_marking_pool_counts_replacement_required_order_as_needing_code(
    async_client: AsyncClient,
) -> None:
    # TC-NEW-FBS-KIZ-011: replacement_required remains in the pool deficit demand.
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
        wb_order_id=950901,
        sticker_code="REPLACEMENT-DEFICIT",
        wb_barcode="REPLACEMENT-DEFICIT-BAR",
        marking=FbsOrderMarking(
            order_id=uuid.uuid4(),
            tenant_id=tenant_id,
            kind=MARKING_KIND_SGTIN,
            value=_cis("NEEDSREPLACE"),
            source="pool",
            check_status=CHECK_STATUS_NEW,
            meta_status=META_STATUS_REPLACEMENT_REQUIRED,
        ),
    )
    async with SessionLocal() as session:
        db_order = await session.get(FbsOrder, order.order_id)
        assert db_order is not None
        db_order.required_meta_json = [MARKING_KIND_SGTIN]
        session.add(
            MarkingCode(
                tenant_id=tenant_id,
                seller_id=seller_id,
                product_id=order.product_id,
                cis_code=_cis("REPLACEMENTPOOL"),
                source="pool",
                status=STATUS_AVAILABLE,
            )
        )
        await session.commit()

    async with SessionLocal() as session:
        db_order = await session.get(FbsOrder, order.order_id)
        assert db_order is not None
        marking_pool = await fbs_workspace_svc._build_marking_pool(
            session,
            tenant_id,
            [db_order],
        )

    assert marking_pool["required"] == 1
    assert marking_pool["available"] == 1
    assert marking_pool["shortage"] == 0
    assert marking_pool["orders_without_code"] == []


# --------------------------------------------------------------------------
# I3 — GS-разделители, вырезанные браузерным полем ввода целиком.
#
# Отличие от блока "gs_substitute" выше: там сканер подставляет ВИДИМЫЙ символ
# ("~", "<GS>"), и по нему видно, где резать. Здесь HTML-поле не пропускает сам
# байт 0x1D, никакого следа не остаётся, и единственный ориентир — структура
# КИЗ: 01<GTIN,14>21<серийник,1..20>|91<код,4>|92<подпись,44 одежда / 88 обувь>.
# --------------------------------------------------------------------------

# Реальный скан с прода 28.08.2026 (ИП Рябов, десять залипших заказов): 83
# символа, склеено, WB принял и вернул те же данные со своими разделителями —
# 85 символов.
_PROD_GLUED_CIS = (
    "0104630710098651215VaAOh'u!tRFR"
    "91EE12"
    "92/p5ES3Y984dx9CHANLa3oqpTJkYWL0iMcO/2z6i0be4="
)
_PROD_RESTORED_CIS = (
    "0104630710098651215VaAOh'u!tRFR"
    f"{_GS}91EE12"
    f"{_GS}92/p5ES3Y984dx9CHANLa3oqpTJkYWL0iMcO/2z6i0be4="
)

_GTIN14 = "04606012345678"
_SIGNATURE_44 = "MTIzNDU2Nzg5MGFiY2RlZmdoaWprbG1ub3BxcnN0dXY="
_SIGNATURE_88 = _SIGNATURE_44 + "MTIzNDU2Nzg5MGFiY2RlZmdoaWprbG1ub3BxcnN0dXZ3"


def _kiz(
    serial: str,
    verification: str,
    signature: str,
    *,
    with_gs: bool,
    gtin: str = _GTIN14,
) -> str:
    sep = _GS if with_gs else ""
    return f"01{gtin}21{serial}{sep}91{verification}{sep}92{signature}"


def test_gs_restore_fixes_production_scan_byte_for_byte() -> None:
    # TC-NEW-FBS-KIZ-I3-001: боевой случай 28.08.2026 целиком. Проверяем не
    # «примерно починилось», а буквальное равенство тому, что вернул WB:
    # 83 символа на входе, 85 на выходе, ровно два вставленных разделителя.
    assert len(_PROD_GLUED_CIS) == 83
    assert len(_PROD_RESTORED_CIS) == 85
    assert _GS not in _PROD_GLUED_CIS

    value, hints = kiz_svc.normalize_scanned_cis(_PROD_GLUED_CIS)

    assert value == _PROD_RESTORED_CIS
    assert value.count(_GS) == 2
    assert hints == ["gs_structure_restored"]
    assert kiz_svc.is_probably_cis(value) is True
    # Данные не переставлены и не потеряны — изменились только разделители.
    assert value.replace(_GS, "") == _PROD_GLUED_CIS


def test_gs_restore_is_idempotent_on_production_scan() -> None:
    # TC-NEW-FBS-KIZ-I3-001: повторный прогон уже починенного значения не должен
    # ни вставлять третий разделитель, ни выставлять hint. Риск реальный: после
    # первого прохода в хвосте появляется GS, и второй проход обязан это увидеть.
    once, first_hints = kiz_svc.normalize_scanned_cis(_PROD_GLUED_CIS)
    twice, second_hints = kiz_svc.normalize_scanned_cis(once)
    thrice, third_hints = kiz_svc.normalize_scanned_cis(twice)

    assert first_hints == ["gs_structure_restored"]
    assert twice == once == thrice
    assert second_hints == []
    assert third_hints == []


def test_gs_restore_handles_footwear_88_char_signature() -> None:
    # TC-NEW-FBS-KIZ-I3-002: у обуви криптоподпись 88 символов, а не 44. Разбор
    # обязан попробовать обе длины, иначе обувь целиком уедет в отказ.
    glued = _kiz("Zk9L2pQ1", "M3xR", _SIGNATURE_88, with_gs=False)
    expected = _kiz("Zk9L2pQ1", "M3xR", _SIGNATURE_88, with_gs=True)
    assert len(_SIGNATURE_88) == 88

    value, hints = kiz_svc.normalize_scanned_cis(glued)

    assert value == expected
    assert hints == ["gs_structure_restored"]


def test_gs_restore_not_fooled_by_91_and_92_inside_serial() -> None:
    # TC-NEW-FBS-KIZ-I3-003: главная ловушка. Серийник сам содержит "91" и "92".
    # Наивный поиск подстроки обрубил бы серийник на первом ложном совпадении и
    # отправил бы в WB другой код — тихая порча данных, которую оператор не
    # заметит. Разбор от конца строки обязан найти настоящие маркеры.
    trap_serial = "A91XB92YC7z"
    glued = _kiz(trap_serial, "Q9zK", _SIGNATURE_44, with_gs=False)
    expected = _kiz(trap_serial, "Q9zK", _SIGNATURE_44, with_gs=True)

    value, hints = kiz_svc.normalize_scanned_cis(glued)

    assert value == expected
    assert hints == ["gs_structure_restored"]
    # Серийник дошёл целиком, вместе с ложными "91"/"92" внутри.
    assert f"21{trap_serial}{_GS}91" in value
    assert value.count(_GS) == 2


def test_gs_restore_leaves_already_separated_code_untouched() -> None:
    # TC-NEW-FBS-KIZ-I3-004: главный регрессионный риск задачи — испортить
    # нормальный код. Разделители на месте → значение не меняется, hint пустой.
    already_ok = _kiz("aXq7Tz9Km", "K7pQ", _SIGNATURE_44, with_gs=True)

    value, hints = kiz_svc.normalize_scanned_cis(already_ok)

    assert value == already_ok
    assert hints == []


def test_gs_restore_leaves_short_form_kiz_without_crypto_tail() -> None:
    # TC-NEW-FBS-KIZ-I3-005: короткий КИЗ (01+GTIN+21+серийник) — валидный
    # формат WB. Блоков 91/92 у него нет, разделитель перед последним полем не
    # нужен. Такой код нельзя ни «чинить», ни браковать как неразбираемый.
    short_form = "010460601234567821SHORT1234"

    value, hints = kiz_svc.normalize_scanned_cis(short_form)

    assert value == short_form
    assert hints == []
    assert kiz_svc.is_probably_cis(value) is True


@pytest.mark.parametrize(
    ("case", "raw"),
    [
        # Подпись обрублена при передаче — не 44 и не 88.
        ("truncated_signature", _kiz("aXq7Tz9Km", "K7pQ", _SIGNATURE_44, with_gs=False)[:-5]),
        # Подпись длиннее одежды и короче обуви.
        ("signature_66", _kiz("aXq7Tz9Km", "K7pQ", "A" * 66, with_gs=False)),
        # Серийник длиннее максимума GS1 (20) — структура не сходится.
        ("serial_21", _kiz("A" * 21, "K7pQ", _SIGNATURE_44, with_gs=False)),
        # Серийника нет вовсе.
        ("serial_empty", _kiz("", "K7pQ", _SIGNATURE_44, with_gs=False)),
        # На месте маркера 91 стоит что-то другое.
        (
            "wrong_ai_marker",
            _kiz("aXq7Tz9Km", "K7pQ", _SIGNATURE_44, with_gs=False).replace(
                "91K7pQ", "93K7pQ"
            ),
        ),
        # Просто длинный мусор с правильным началом.
        ("long_noise", "01" + _GTIN14 + "21" + "X" * 300),
    ],
)
def test_gs_restore_refuses_to_guess_when_structure_does_not_match(
    case: str, raw: str
) -> None:
    # TC-NEW-FBS-KIZ-I3-006: если длина хвоста не сходится ни с одеждой, ни с
    # обувью — гадать нельзя. Значение не подменяется на догадку, а помечается
    # служебным hint, по которому вызывающий код откажется слать код в WB.
    value, hints = kiz_svc.normalize_scanned_cis(raw)

    assert value == raw, case
    assert hints == ["gs_unrestorable"], case
    assert _GS not in value, case


@pytest.mark.parametrize("serial_length", [1, 20])
def test_gs_restore_accepts_serial_length_boundaries(serial_length: int) -> None:
    # TC-NEW-FBS-KIZ-I3-006: границы допустимой длины серийного номера GS1
    # (1..20) должны попадать внутрь, а не срезаться проверкой «строго меньше».
    serial = "A" * serial_length
    glued = _kiz(serial, "K7pQ", _SIGNATURE_44, with_gs=False)

    value, hints = kiz_svc.normalize_scanned_cis(glued)

    assert value == _kiz(serial, "K7pQ", _SIGNATURE_44, with_gs=True)
    assert hints == ["gs_structure_restored"]


@pytest.mark.parametrize(
    ("case", "raw"),
    [
        ("empty", ""),
        ("only_separators", _GS * 3),
        ("noise", "laser scanner noise"),
        ("gtin_not_digits", "01ABCDEFGHIJKLMN21aXq7Tz9Km91K7pQ92" + _SIGNATURE_44),
        ("gtin_13_digits", "01" + "0" * 13 + "21aXq7Tz9Km91K7pQ92" + _SIGNATURE_44),
        ("no_ai21", "01" + _GTIN14 + "10aXq7Tz9Km91K7pQ92" + _SIGNATURE_44),
        ("not_a_gs1_string_at_all", "PROD-BARCODE-1234567890"),
    ],
)
def test_gs_restore_ignores_values_that_are_not_kiz_prefixed(case: str, raw: str) -> None:
    # TC-NEW-FBS-KIZ-I3-007: всё, что не начинается с 01<14 цифр>21, новый шаг
    # трогать не должен вообще — ни чинить, ни брать на себя отказ. Такой вход
    # обязан дойти до старой проверки is_probably_cis и упасть как not_a_kiz.
    value, hints = kiz_svc.normalize_scanned_cis(raw)

    assert value == raw, case
    assert hints == [], case


def test_gs_restore_survives_aim_prefix_and_russian_layout() -> None:
    # TC-NEW-FBS-KIZ-I3-008: восстановление структуры идёт последним шагом, уже
    # после снятия AIM-префикса и разворота раскладки. Если порядок шагов
    # сломать, префикс сдвинет все смещения и структура не сойдётся.
    glued = _kiz("aXq7Tz9Km", "K7pQ", _SIGNATURE_44, with_gs=False)
    expected = _kiz("aXq7Tz9Km", "K7pQ", _SIGNATURE_44, with_gs=True)
    ru_layout = str.maketrans("qwertyuiopasdfghjklzxcvbnm", "йцукенгшщзфывапролдячсмить")
    scanned = "]d2" + glued.translate(ru_layout)
    assert scanned != "]d2" + glued

    value, hints = kiz_svc.normalize_scanned_cis(scanned)

    assert value == expected
    assert hints == ["aim_prefix", "keyboard_layout", "gs_structure_restored"]


def test_gs_restore_ignores_trailing_scanner_newline() -> None:
    # TC-NEW-FBS-KIZ-I3-008: сканер дописывает Enter. Хвост длиннее на символ —
    # если его не срезать до разбора структуры, длина подписи не сойдётся и
    # рабочий скан уедет в отказ gs_separator_lost.
    glued = _kiz("aXq7Tz9Km", "K7pQ", _SIGNATURE_44, with_gs=False)

    value, hints = kiz_svc.normalize_scanned_cis(f"{glued}\r\n ")

    assert value == _kiz("aXq7Tz9Km", "K7pQ", _SIGNATURE_44, with_gs=True)
    assert hints == ["gs_structure_restored"]


@pytest.mark.parametrize("suffix", ["\t", " ", "\r\n", "\x0b", "\x0c", "\t\t \r\n"])
def test_gs_restore_ignores_any_trailing_scanner_whitespace(suffix: str) -> None:
    # TC-NEW-FBS-KIZ-I3-008 (negative): сканер дописывает суффикс, и Tab —
    # такая же штатная настройка, как Enter. Лишний символ сдвигает длину
    # хвоста, структура не сходится, и рабочий скан уезжает в отказ
    # gs_separator_lost — то есть кладовщик вообще не может сдать заказ.
    glued = _kiz("aXq7Tz9Km", "K7pQ", _SIGNATURE_44, with_gs=False)

    value, hints = kiz_svc.normalize_scanned_cis(f"{glued}{suffix}")

    assert value == _kiz("aXq7Tz9Km", "K7pQ", _SIGNATURE_44, with_gs=True)
    assert hints == ["gs_structure_restored"]


def test_normalize_does_not_strip_separator_as_if_it_were_whitespace() -> None:
    # TC-NEW-FBS-KIZ-I3-008 (negative): 0x1D Python считает пробельным
    # символом, поэтому голый rstrip() срезал бы САМ разделитель — ровно то,
    # что мы тут восстанавливаем. Список срезаемых символов обязан быть явным.
    assert "\x1d".isspace() is True
    # Значение, которое новый шаг не трогает (структура не опознана), обязано
    # дойти до проверки байт в байт, вместе с концевым разделителем.
    tail_separator = f"{_CLEAN_CIS}{_GS}"

    value, hints = kiz_svc.normalize_scanned_cis(tail_separator)

    assert value == tail_separator
    assert value.endswith(_GS)
    assert hints == []


def test_gs_restore_never_loses_payload_characters() -> None:
    # TC-NEW-FBS-KIZ-I3-008: инвариант на все входы разом — восстановление
    # имеет право менять ТОЛЬКО расстановку разделителей. Если из значения
    # пропадёт хоть один символ данных, в WB уедет другой код.
    samples = [
        _PROD_GLUED_CIS,
        _kiz("aXq7Tz9Km", "K7pQ", _SIGNATURE_44, with_gs=False),
        _kiz("Zk9L2pQ1", "M3xR", _SIGNATURE_88, with_gs=False),
        _kiz("A91XB92YC7z", "Q9zK", _SIGNATURE_44, with_gs=False),
        _kiz("aXq7Tz9Km", "K7pQ", _SIGNATURE_44, with_gs=True),
        "010460601234567821SHORT1234",
        _CLEAN_CIS,
    ]
    for raw in samples:
        value, _ = kiz_svc.normalize_scanned_cis(raw)
        assert value.replace(_GS, "") == raw.replace(_GS, ""), raw


@pytest.mark.parametrize("missing_before", ["91", "92"])
def test_gs_restore_repairs_code_with_only_one_of_two_separators(
    missing_before: str,
) -> None:
    # TC-NEW-FBS-KIZ-I3-009: разделители теряются и поодиночке. Половинчатый
    # код обязан достраиваться до канонического вида с ОБОИМИ разделителями —
    # раньше он проходил насквозь как «нормальный» и получал от WB sgtinNoGS.
    full = _kiz("aXq7Tz9Km", "K7pQ", _SIGNATURE_44, with_gs=True)
    half = full.replace(f"{_GS}{missing_before}", missing_before, 1)
    assert half.count(_GS) == 1

    value, hints = kiz_svc.normalize_scanned_cis(half)

    assert value == full
    assert value.count(_GS) == 2
    assert hints == ["gs_structure_restored"]


def test_gs_restore_collapses_duplicated_separators_to_canonical_form() -> None:
    # TC-NEW-FBS-KIZ-I3-009: если разделитель приехал дважды (сканер отдал и
    # байт, и видимую замену), результат всё равно должен быть каноническим —
    # WB сверяет значение со своим, лишний байт сделает его «другим кодом».
    doubled = (
        f"01{_GTIN14}21aXq7Tz9Km{_GS}{_GS}91K7pQ{_GS}92{_SIGNATURE_44}"
    )

    value, hints = kiz_svc.normalize_scanned_cis(doubled)

    assert value == _kiz("aXq7Tz9Km", "K7pQ", _SIGNATURE_44, with_gs=True)
    assert hints == ["gs_structure_restored"]


def test_gs_restore_does_not_call_a_separated_code_lost() -> None:
    # TC-NEW-FBS-KIZ-I3-009 (negative): у кода разделители есть, но структуру
    # мы не опознали (лишнее поле, обрезанная подпись). Звать такой код
    # «разделители потеряны» — врать оператору и без нужды блокировать сдачу:
    # диагноз про потерю разделителей тут заведомо неверен.
    half_broken = _kiz("aXq7Tz9Km", "K7pQ", _SIGNATURE_44, with_gs=True)[:-5]
    assert _GS in half_broken

    value, hints = kiz_svc.normalize_scanned_cis(half_broken)

    assert value == half_broken
    assert hints == []


@pytest.mark.asyncio
async def test_fbs_kiz_validate_rejects_unrestorable_glued_code(
    async_client: AsyncClient,
) -> None:
    # TC-NEW-FBS-KIZ-I3-010: неразбираемый склеенный код останавливается на
    # валидации с адресной причиной, а не с общим not_a_kiz — оператор должен
    # понять, что код надо пересканировать целиком.
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
        wb_order_id=934001,
        sticker_code="GS-UNRESTORABLE",
        wb_barcode="GS-UNRESTORABLE-BAR",
        with_packaging=True,
    )
    broken = _kiz("aXq7Tz9Km", "K7pQ", _SIGNATURE_44, with_gs=False)[:-5]

    response = await async_client.post(
        "/operations/fbs-orders/kiz/validate",
        headers=headers,
        json={"order_id": str(order.order_id), "value": broken},
    )

    detail = response.json()["detail"]
    assert detail["code"] == "gs_separator_lost"
    assert "раздел" in detail["message"].lower()
    assert detail["retryable"] is False
    # Оператору отдаём форму скана для диагностики, а не сам код.
    assert detail["context"]["debug"]["length"] == len(broken)


@pytest.mark.asyncio
async def test_fbs_kiz_validate_unrestorable_code_is_client_error_not_500(
    async_client: AsyncClient,
) -> None:
    # TC-NEW-FBS-KIZ-I3-010 (negative): плохой скан — это 4xx. 500 поднимает
    # алерты как отказ сервиса и на клиенте обрабатывается общим «сервер лёг»,
    # а не адресной подсказкой оператору.
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
        wb_order_id=934004,
        sticker_code="GS-STATUS",
        wb_barcode="GS-STATUS-BAR",
        with_packaging=True,
    )
    broken = _kiz("aXq7Tz9Km", "K7pQ", _SIGNATURE_44, with_gs=False)[:-5]

    response = await async_client.post(
        "/operations/fbs-orders/kiz/validate",
        headers=headers,
        json={"order_id": str(order.order_id), "value": broken},
    )

    assert response.status_code == 400, response.text


@pytest.mark.asyncio
async def test_fbs_kiz_commit_never_sends_unrestorable_code_to_wb(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # TC-NEW-FBS-KIZ-I3-011: суть отказа — не текст на экране, а то, что запроса
    # в WB не было и в базе ничего не осталось. Если склеенный код всё-таки
    # уедет, WB ответит sgtinNoGS и заказ снова залипнет.
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
        wb_order_id=934002,
        sticker_code="GS-NO-WB",
        wb_barcode="GS-NO-WB-BAR",
        with_packaging=True,
    )
    sent = _patch_wb_acceptance(monkeypatch)
    markings_before, codes_before = await _marking_row_counts(tenant_id)
    broken = _kiz("aXq7Tz9Km", "K7pQ", _SIGNATURE_44, with_gs=False)[:-5]

    response = await async_client.post(
        "/operations/fbs-orders/kiz/commit",
        headers=headers,
        json={
            "idempotency_key": "kiz-gs-unrestorable",
            "pairs": [
                {"order_id": str(order.order_id), "value": broken, "confirmed": False}
            ],
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body[0]["status"] == "error"
    assert body[0]["code"] == "gs_separator_lost"
    # Главное: WB не трогали вообще.
    assert sent == {}
    assert await _marking_row_counts(tenant_id) == (markings_before, codes_before)


@pytest.mark.asyncio
async def test_fbs_kiz_commit_sends_restored_production_value_to_wb(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # TC-NEW-FBS-KIZ-I3-012: сквозная проверка боевого случая. Раньше в WB
    # уходили склеенные 83 символа; теперь WB обязан получить ровно те 85, что
    # он сам вернул, и столько же должно осесть в базе.
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
        wb_order_id=934003,
        sticker_code="GS-RESTORE",
        wb_barcode="GS-RESTORE-BAR",
        with_packaging=True,
    )
    sent = _patch_wb_acceptance(monkeypatch)

    response = await async_client.post(
        "/operations/fbs-orders/kiz/commit",
        headers=headers,
        json={
            "idempotency_key": "kiz-gs-restore-prod",
            "pairs": [
                {
                    "order_id": str(order.order_id),
                    "value": _PROD_GLUED_CIS,
                    "confirmed": False,
                }
            ],
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()[0]["status"] == "ok", response.text
    assert sent[934003] == _PROD_RESTORED_CIS
    assert len(sent[934003]) == 85

    async with SessionLocal() as session:
        marking = (
            await session.execute(
                select(FbsOrderMarking).where(
                    FbsOrderMarking.order_id == order.order_id
                )
            )
        ).scalar_one()
        assert marking.value == _PROD_RESTORED_CIS
        code = (
            await session.execute(
                select(MarkingCode).where(MarkingCode.tenant_id == tenant_id)
            )
        ).scalar_one()
        assert code.cis_code == _PROD_RESTORED_CIS


def test_gs_restore_normalizes_trailing_gs1_terminator_without_losing_data() -> None:
    # TC-NEW-FBS-KIZ-I3-009: у канонического кода концевой 0x1D — это
    # терминатор GS1, а не разделитель поля. Убрать его можно, но данные при
    # этом должны остаться байт в байт: WB сверяет значение со своим.
    canonical = _kiz("aXq7Tz9Km", "K7pQ", _SIGNATURE_44, with_gs=True)

    value, _ = kiz_svc.normalize_scanned_cis(f"{canonical}{_GS}")

    assert value == canonical
    assert value.replace(_GS, "") == canonical.replace(_GS, "")


@pytest.mark.xfail(
    strict=True,
    reason=(
        "ДЕФЕКТ (остаточный, внесён починкой половинчатых кодов): очистка "
        "хвоста от разделителей сделала достраивание применимым и к кодам, "
        "которые уже разбирались однозначно. КИЗ вида 21<серийник><GS>92<44> "
        "(без блока 91), чей серийник заканчивается на шаблон '91'+2 символа, "
        "переразбирается: шесть символов серийного номера уезжают в выдуманный "
        "блок 91, и в WB уходит другой ЛОГИЧЕСКИЙ код при тех же байтах. "
        "Лечится проверкой «если значение уже разбирается как валидный GS1 "
        "имеющимися разделителями — не трогать»."
    ),
)
def test_gs_restore_does_not_reparse_a_code_that_already_parses() -> None:
    # TC-NEW-FBS-KIZ-I3-013 (negative): тихая подмена границ полей — худший
    # вид отказа: байты те же, оператор ничего не замечает, а WB видит другой
    # серийный номер.
    victim = f"01{_GTIN14}21AB91ZZQQ{_GS}92{_SIGNATURE_44}"

    value, hints = kiz_svc.normalize_scanned_cis(victim)

    assert value == victim
    assert hints == []


def test_gs_restore_leaves_alternative_crypto_tag_93_alone_when_separated() -> None:
    # TC-NEW-FBS-KIZ-I3-014: по документации WB (wb-docs/04-labeling/
    # verify-product-identifiers.md) криптохвост стоит «после тега 92 ИЛИ 93»,
    # а его длина зависит от категории товара. Мы умеем восстанавливать только
    # 92 + 44/88. Нормально отсканированный код с тегом 93 обязан проходить
    # насквозь без изменений — граница возможностей не должна ломать то, что
    # и так работает.
    separated = f"01{_GTIN14}21aXq7Tz9Km{_GS}91K7pQ{_GS}93{'M' * 44}"

    value, hints = kiz_svc.normalize_scanned_cis(separated)

    assert value == separated
    assert hints == []


@pytest.mark.parametrize(
    ("case", "raw"),
    [
        ("crypto_tag_93", f"01{_GTIN14}21aXq7Tz9Km91K7pQ93{'M' * 44}"),
        ("unknown_tail_length_60", f"01{_GTIN14}21aXq7Tz9Km91K7pQ92{'M' * 60}"),
    ],
)
def test_gs_restore_refuses_rather_than_guesses_unknown_kiz_shapes(
    case: str, raw: str
) -> None:
    # TC-NEW-FBS-KIZ-I3-014 (negative): формы КИЗ, которых нет в нашей таблице
    # (тег 93, другая длина криптохвоста), склеенными восстановить нельзя.
    # Правильное поведение — назвать причину оператору, а не гадать и не слать
    # в WB заведомо битый код.
    value, hints = kiz_svc.normalize_scanned_cis(raw)

    assert value == raw, case
    assert hints == ["gs_unrestorable"], case
