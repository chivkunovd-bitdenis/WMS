from __future__ import annotations

import asyncio
import time
import uuid
from types import SimpleNamespace
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.settings import settings
from app.db.session import SessionLocal
from app.models.fbs_order import (
    CHECK_STATUS_CHECKING,
    CHECK_STATUS_NEW,
    FBS_ORDER_STATUS_PACKED,
    META_STATUS_ACCEPTED,
    META_STATUS_ALLOWED_WITHOUT_CHECK,
    META_STATUS_PENDING,
    META_STATUS_REJECTED,
    FbsOrderMarking,
)
from app.services.wb_marketplace_orders_service import upsert_order_from_wb_row
from app.services.wildberries_client import reset_mock_marketplace_order_meta
from tests.fbs_seed_helpers import DEFAULT_WB_WAREHOUSE_ID, seed_fbs_warehouse_binding


async def _register_ff_admin(async_client: AsyncClient) -> tuple[dict[str, str], str]:
    suffix = str(time.time_ns())
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": f"FBS marking {suffix}",
            "slug": f"fbs-marking-{suffix}",
            "admin_email": f"fbs-marking-{suffix}@example.com",
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
) -> tuple[str, str, uuid.UUID]:
    seller = await async_client.post(
        "/sellers", headers=headers, json={"name": f"Seller {suffix}"}
    )
    assert seller.status_code in (200, 201), seller.text
    seller_id = seller.json()["id"]
    tok = await async_client.patch(
        f"/integrations/wildberries/sellers/{seller_id}/tokens",
        headers=headers,
        json={"marketplace_api_token": "wb-marketplace-token"},
    )
    assert tok.status_code == 200, tok.text
    warehouse = await async_client.post(
        "/warehouses",
        headers=headers,
        json={"name": "WH", "code": f"wh-{suffix[-8:]}"},
    )
    assert warehouse.status_code in (200, 201), warehouse.text
    reg = await async_client.get("/auth/me", headers=headers)
    assert reg.status_code == 200
    tenant_id = uuid.UUID(reg.json()["tenant_id"])
    return seller_id, warehouse.json()["id"], tenant_id


def _wb_order_row(
    *, order_id: int, wb_warehouse_id: int = DEFAULT_WB_WAREHOUSE_ID, **extra: Any
) -> dict[str, Any]:
    row = {
        "id": order_id,
        "rid": f"rid-{order_id}",
        "createdAt": "2026-07-01T12:00:00+03:00",
        "nmId": 900001,
        "chrtId": 555,
        "article": "ART-001",
        "skus": [f"BAR-{order_id}"],
        "price": 199900,
        "cargoType": 1,
        "officeId": 42,
        "isLegal": False,
        "warehouseId": wb_warehouse_id,
    }
    row.update(extra)
    return row


async def _create_order(
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    *,
    order_id: int,
    status: str | None = None,
    wb_row_extra: dict[str, Any] | None = None,
) -> uuid.UUID:
    async with SessionLocal() as session:
        await seed_fbs_warehouse_binding(
            session,
            tenant_id=tenant_id,
            seller_id=seller_id,
            wms_warehouse_id=warehouse_id,
        )
        row = _wb_order_row(order_id=order_id, **(wb_row_extra or {}))
        order, _ = await upsert_order_from_wb_row(
            session,
            tenant_id,
            seller_id,
            row,
        )
        if status is not None:
            order.status = status
        await session.commit()
        return order.id


@pytest.fixture
def enable_wb_marketplace_marking_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "e2e_mock_wb_marketplace_marking", True)
    reset_mock_marketplace_order_meta()


# TC-NEW-FBS-MARK-002 — sync updates check_status from official batch meta
@pytest.mark.asyncio
async def test_fbs_marking_sync_updates_check_status(
    async_client: AsyncClient,
    enable_wb_marketplace_marking_mock: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    order_id = await _create_order(
        tenant_id,
        uuid.UUID(seller_id),
        uuid.UUID(warehouse_id),
        order_id=920001,
        status=FBS_ORDER_STATUS_PACKED,
    )
    cis = "01CIS-SYNC-001"
    async with SessionLocal() as session:
        session.add(
            FbsOrderMarking(
                order_id=order_id,
                tenant_id=tenant_id,
                kind="sgtin",
                value=cis,
                check_status=CHECK_STATUS_NEW,
                meta_status=META_STATUS_PENDING,
            )
        )
        await session.commit()

    from app.services.wildberries_fbs_client import MarketplaceOrderMetaRow

    async def fake_meta_batch(
        client: object,
        *,
        api_token: str,
        order_ids: list[int],
        marketplace_api_base: str | None = None,
    ) -> list[MarketplaceOrderMetaRow]:
        assert order_ids == [920001]
        return [
            MarketplaceOrderMetaRow(
                order_id=920001,
                meta={"sgtins": [{"value": cis, "checkStatus": "checking"}]},
            )
        ]

    monkeypatch.setattr(
        "app.services.fbs_marking_service.fetch_marketplace_orders_meta_batch",
        fake_meta_batch,
    )

    sync = await async_client.post(
        f"/operations/fbs-orders/{order_id}/markings/sync",
        headers=headers,
    )
    assert sync.status_code == 200, sync.text
    rows = sync.json()
    assert len(rows) == 1
    assert rows[0]["check_status"] == CHECK_STATUS_CHECKING


@pytest.mark.asyncio
@pytest.mark.parametrize("fresh_batch", [[], None], ids=["empty-batch", "wb-error"])
async def test_fbs_marking_sync_clears_stale_filled_verdict(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    fresh_batch: list[object] | None,
) -> None:
    """S-03-TC-006/012: no fresh WB answer must replace a stale green verdict."""
    from app.models.fbs_order import FbsOrder
    from app.services.wildberries_client import WildberriesClientError

    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    order_id = await _create_order(
        tenant_id,
        uuid.UUID(seller_id),
        uuid.UUID(warehouse_id),
        order_id=920002 if fresh_batch == [] else 920003,
        status=FBS_ORDER_STATUS_PACKED,
        wb_row_extra={"requiredMeta": ["sgtin"]},
    )
    async with SessionLocal() as session:
        order = await session.get(FbsOrder, order_id)
        assert order is not None
        order.required_meta_json = ["sgtin"]
        order.metadata_delivery_allowed = True
        session.add(
            FbsOrderMarking(
                order_id=order_id,
                tenant_id=tenant_id,
                kind="sgtin",
                value="01CIS-STALE-FILLED",
                check_status="ok",
                meta_status=META_STATUS_ACCEPTED,
                meta_details_json={"decision": "filled", "reason": None},
            )
        )
        await session.commit()

    async def fake_meta_batch(*args: object, **kwargs: object) -> list[object]:
        del args, kwargs
        if fresh_batch is None:
            raise WildberriesClientError("transport_error")
        return fresh_batch

    monkeypatch.setattr(
        "app.services.fbs_marking_service.fetch_marketplace_orders_meta_batch",
        fake_meta_batch,
    )

    async with SessionLocal() as session:
        order = await session.get(FbsOrder, order_id)
        assert order is not None
        markings = list(
            (
                await session.execute(
                    select(FbsOrderMarking).where(FbsOrderMarking.order_id == order_id)
                )
            ).scalars()
        )
        from app.services.fbs_marking_service import _sync_order_meta_from_wb

        if fresh_batch is None:
            with pytest.raises(WildberriesClientError):
                await _sync_order_meta_from_wb(
                    session, order, async_client, "marketplace-token"
                )
        else:
            await _sync_order_meta_from_wb(
                session, order, async_client, "marketplace-token"
            )
        await session.flush()

        assert order.metadata_delivery_allowed is False
        assert isinstance(order.meta_details_json, dict)
        assert order.meta_details_json["sgtin"]["decision"] is None
        assert markings[0].meta_status == "unknown"
        assert markings[0].reason is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "older_response_finishes_first",
    [True, False],
    ids=["older-persists-first", "newer-persists-first"],
)
async def test_fbs_marking_sync_does_not_apply_stale_response(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    older_response_finishes_first: bool,
) -> None:
    """S-03-TC-016: the later-started WB check wins in either response order."""
    from app.models.fbs_order import FbsOrder
    from app.models.fbs_supply import (
        FBS_DELIVERY_TYPE_WAREHOUSE_SC,
        FBS_SUPPLY_STATUS_PACKED,
    )
    from app.services.fbs_marking_service import _sync_order_meta_from_wb
    from app.services.fbs_shipment_service import _build_delivery_checks
    from app.services.wildberries_fbs_client import (
        MarketplaceMetaDetail,
        MarketplaceOrderMetaRow,
    )

    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    wb_order_id = 920016
    order_id = await _create_order(
        tenant_id,
        uuid.UUID(seller_id),
        uuid.UUID(warehouse_id),
        order_id=wb_order_id,
        status=FBS_ORDER_STATUS_PACKED,
        wb_row_extra={"requiredMeta": ["sgtin"]},
    )
    marking_value = "01CIS-S-03-TC-016"
    async with SessionLocal() as session:
        session.add(
            FbsOrderMarking(
                order_id=order_id,
                tenant_id=tenant_id,
                kind="sgtin",
                value=marking_value,
                check_status=CHECK_STATUS_NEW,
                meta_status=META_STATUS_PENDING,
            )
        )
        await session.commit()

    first_request_waiting = asyncio.Event()
    second_request_waiting = asyncio.Event()
    release_first_request = asyncio.Event()
    release_second_request = asyncio.Event()
    call_count = 0

    async def fake_meta_batch(*args: object, **kwargs: object) -> list[object]:
        nonlocal call_count
        del args, kwargs
        call_count += 1
        if call_count == 1:
            first_request_waiting.set()
            await release_first_request.wait()
            reason = None
        else:
            second_request_waiting.set()
            await release_second_request.wait()
            reason = "uinBadStatus"
        return [
            MarketplaceOrderMetaRow(
                order_id=wb_order_id,
                meta_details=(
                    MarketplaceMetaDetail(
                        key="sgtin",
                        value=marking_value,
                        decision="filled",
                        reason=reason,
                    ),
                ),
            )
        ]

    monkeypatch.setattr(
        "app.services.fbs_marking_service.fetch_marketplace_orders_meta_batch",
        fake_meta_batch,
    )

    async def sync_once() -> None:
        async with SessionLocal() as session:
            order = await session.get(FbsOrder, order_id)
            assert order is not None
            await _sync_order_meta_from_wb(
                session, order, async_client, "marketplace-token"
            )
            await session.commit()

    first_request = asyncio.create_task(sync_once())
    await first_request_waiting.wait()
    second_request = asyncio.create_task(sync_once())
    await second_request_waiting.wait()
    if older_response_finishes_first:
        release_first_request.set()
        await first_request
        async with SessionLocal() as session:
            older_result = await session.get(FbsOrder, order_id)
            assert older_result is not None
            assert older_result.metadata_delivery_allowed is True
            assert older_result.meta_details_json is not None
            assert older_result.meta_details_json["sgtin"]["reason"] is None
        release_second_request.set()
        await second_request
    else:
        release_second_request.set()
        await second_request
        release_first_request.set()
        await first_request

    async with SessionLocal() as session:
        order = await session.get(FbsOrder, order_id)
        assert order is not None
        markings = list(
            (
                await session.execute(
                    select(FbsOrderMarking).where(
                        FbsOrderMarking.order_id == order_id
                    )
                )
            ).scalars()
        )
        assert order.metadata_delivery_allowed is False
        assert order.meta_details_json is not None
        assert order.meta_details_json["sgtin"]["decision"] == "filled"
        assert order.meta_details_json["sgtin"]["reason"] == "uinBadStatus"
        assert markings[0].meta_status == META_STATUS_ACCEPTED
        assert markings[0].reason == "uinBadStatus"

        gate_order = SimpleNamespace(
            id=order.id,
            status=order.status,
            wb_status=order.wb_status,
            required_meta_json=order.required_meta_json,
            optional_meta_json=order.optional_meta_json,
            meta_details_json=order.meta_details_json,
            product=None,
            markings=markings,
        )
        gate_supply = SimpleNamespace(
            status=FBS_SUPPLY_STATUS_PACKED,
            delivery_type=FBS_DELIVERY_TYPE_WAREHOUSE_SC,
            trbxes=[],
            honest_sign_skipped_at=None,
        )
        checks = _build_delivery_checks(
            gate_supply,
            [gate_order],
            cargo_qr_ready=True,
        )
        failed = next(
            check for check in checks if check.code == "marking_not_allowed"
        )
        assert failed.ok is False
        assert failed.order_id == order.id
        assert "uinBadStatus" in failed.message


@pytest.mark.asyncio
@pytest.mark.parametrize("include_required_marking", [False, True])
async def test_fbs_metadata_preserves_optional_wb_decision_without_local_marking(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    include_required_marking: bool,
) -> None:
    """S-03-TC-002: WB optional is passable without a local marking row."""
    from app.models.fbs_order import FbsOrder
    from app.services.wildberries_fbs_client import (
        MarketplaceMetaDetail,
        MarketplaceOrderMetaRow,
    )

    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    wb_order_id = 920010 if include_required_marking else 920011
    required = ["sgtin"] if include_required_marking else []
    order_id = await _create_order(
        tenant_id,
        uuid.UUID(seller_id),
        uuid.UUID(warehouse_id),
        order_id=wb_order_id,
        status=FBS_ORDER_STATUS_PACKED,
        wb_row_extra={"requiredMeta": required, "optionalMeta": ["imei"]},
    )
    if include_required_marking:
        async with SessionLocal() as session:
            session.add(
                FbsOrderMarking(
                    order_id=order_id,
                    tenant_id=tenant_id,
                    kind="sgtin",
                    value="01CIS-REQUIRED-FILLED",
                    check_status="new",
                    meta_status=META_STATUS_PENDING,
                )
            )
            await session.commit()

    async def fake_meta_batch(*args: object, **kwargs: object) -> list[object]:
        del args, kwargs
        details = [
            MarketplaceMetaDetail(
                key="imei",
                value=None,
                decision="optional",
            )
        ]
        if include_required_marking:
            details.append(
                MarketplaceMetaDetail(
                    key="sgtin",
                    value="01CIS-REQUIRED-FILLED",
                    decision="filled",
                )
            )
        return [
            MarketplaceOrderMetaRow(
                order_id=wb_order_id,
                meta_details=tuple(details),
            )
        ]

    monkeypatch.setattr(
        "app.services.fbs_marking_service.fetch_marketplace_orders_meta_batch",
        fake_meta_batch,
    )

    response = await async_client.get(
        f"/operations/fbs-orders/{order_id}/metadata",
        headers=headers,
    )
    assert response.status_code == 200, response.text
    metadata = response.json()
    assert metadata["verdict"]["delivery_allowed"] is True
    assert metadata["delivery_allowed"] is True
    optional_state = next(
        state for state in metadata["states"] if state["kind"] == "imei"
    )
    assert optional_state == {
        "kind": "imei",
        "status": META_STATUS_ALLOWED_WITHOUT_CHECK,
        "reason": None,
        "source": "wb",
        "value_tail": None,
    }

    async with SessionLocal() as session:
        order = await session.get(FbsOrder, order_id)
        assert order is not None
        assert order.meta_details_json is not None
        assert order.meta_details_json["imei"]["decision"] == "optional"


# TC-NEW-FBS-MARK-004 — GET list all kinds; empty → []
@pytest.mark.asyncio
async def test_fbs_marking_get_list_all_kinds(
    async_client: AsyncClient,
    enable_wb_marketplace_marking_mock: None,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    order_id = await _create_order(
        tenant_id,
        uuid.UUID(seller_id),
        uuid.UUID(warehouse_id),
        order_id=940001,
        status=FBS_ORDER_STATUS_PACKED,
    )

    empty = await async_client.get(
        f"/operations/fbs-orders/{order_id}/markings",
        headers=headers,
    )
    assert empty.status_code == 200
    assert empty.json() == []

    async with SessionLocal() as session:
        session.add_all(
            [
                FbsOrderMarking(
                    order_id=order_id,
                    tenant_id=tenant_id,
                    kind=kind,
                    value=value,
                    check_status=CHECK_STATUS_NEW,
                    meta_status=META_STATUS_PENDING,
                )
                for kind, value in (
                    ("sgtin", "01CIS-A"),
                    ("sgtin", "01CIS-B"),
                    ("imei", "356938035643809"),
                )
            ]
        )
        await session.commit()

    listed = await async_client.get(
        f"/operations/fbs-orders/{order_id}/markings",
        headers=headers,
    )
    assert listed.status_code == 200
    rows = listed.json()
    assert len(rows) == 3
    kinds = {row["kind"] for row in rows}
    assert kinds == {"sgtin", "imei"}
    values = {row["value"] for row in rows}
    assert values == {"01CIS-A", "01CIS-B", "356938035643809"}


# TC-14 — metadata gate: rejected blocks; allowed_without_check continues
@pytest.mark.asyncio
async def test_fbs_metadata_gate_rejected_blocks_allowed_without_check_ok(
    async_client: AsyncClient,
    enable_wb_marketplace_marking_mock: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services.fbs_marking_service import compute_delivery_allowed

    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    order_id = await _create_order(
        tenant_id,
        uuid.UUID(seller_id),
        uuid.UUID(warehouse_id),
        order_id=960201,
        status=FBS_ORDER_STATUS_PACKED,
        wb_row_extra={"requiredMeta": ["sgtin"], "optionalMeta": ["imei"]},
    )

    meta = await async_client.get(
        f"/operations/fbs-orders/{order_id}/metadata",
        headers=headers,
    )
    assert meta.status_code == 200, meta.text
    assert meta.json()["required"] == ["sgtin"]
    assert meta.json()["delivery_allowed"] is False

    async with SessionLocal() as session:
        from app.models.fbs_order import FbsOrder

        order = await session.get(FbsOrder, order_id)
        assert order is not None
        order.required_meta_json = ["sgtin"]
        session.add(
            FbsOrderMarking(
                order_id=order_id,
                tenant_id=tenant_id,
                kind="sgtin",
                value="01CIS-REJECTED",
                check_status=CHECK_STATUS_NEW,
                meta_status=META_STATUS_REJECTED,
                reason="invalid_kiz",
            )
        )
        await session.commit()
        markings = list(
            (
                await session.execute(
                    select(FbsOrderMarking).where(FbsOrderMarking.order_id == order_id)
                )
            ).scalars()
        )
        assert compute_delivery_allowed(order, markings) is False

    async with SessionLocal() as session:
        await session.execute(
            select(FbsOrderMarking).where(FbsOrderMarking.order_id == order_id)
        )
        for row in (
            await session.execute(
                select(FbsOrderMarking).where(FbsOrderMarking.order_id == order_id)
            )
        ).scalars():
            await session.delete(row)
        session.add(
            FbsOrderMarking(
                order_id=order_id,
                tenant_id=tenant_id,
                kind="sgtin",
                value="01CIS-ALLOWED",
                check_status=CHECK_STATUS_NEW,
                meta_status=META_STATUS_ALLOWED_WITHOUT_CHECK,
                meta_details_json={"decision": "notRequired"},
            )
        )
        await session.commit()
        order = await session.get(FbsOrder, order_id)
        assert order is not None
        order.optional_meta_json = []
        markings = list(
            (
                await session.execute(
                    select(FbsOrderMarking).where(FbsOrderMarking.order_id == order_id)
                )
            ).scalars()
        )
        assert compute_delivery_allowed(order, markings) is True


def test_fbs_metadata_gate_pending_blocks_filled_allows() -> None:
    from types import SimpleNamespace

    from app.services.fbs_marking_service import (
        compute_delivery_allowed,
        derive_meta_status,
    )

    order = SimpleNamespace(required_meta_json=["sgtin"])
    pending = SimpleNamespace(kind="sgtin", value="01CIS-PENDING", meta_status=META_STATUS_PENDING)
    assert compute_delivery_allowed(order, [pending]) is False
    assert (
        derive_meta_status(
            check_status=None,
            decision="filled",
            has_value=True,
        )
        == META_STATUS_ACCEPTED
    )
    filled = SimpleNamespace(
        kind="sgtin", value="01CIS-FILLED", meta_status=META_STATUS_ACCEPTED,
        meta_details_json={"decision": "filled"},
    )
    assert compute_delivery_allowed(order, [filled]) is True


# S-03-TC-001…007 — one server verdict covers every WB response state.
@pytest.mark.parametrize(
    ("decision", "status", "reason", "signature", "tone", "allowed"),
    [
        ("filled", META_STATUS_ACCEPTED, None, "WB: принято", "ok", True),
        (
            "optional",
            META_STATUS_ALLOWED_WITHOUT_CHECK,
            None,
            "WB: код не требуется",
            "neutral",
            True,
        ),
        (
            "notRequired",
            META_STATUS_ALLOWED_WITHOUT_CHECK,
            None,
            "WB: код не требуется",
            "neutral",
            True,
        ),
        ("filled", META_STATUS_ACCEPTED, "invalid_kiz", "WB не принял", "stop", False),
        ("pending", META_STATUS_PENDING, None, "WB: проверяет", "neutral", False),
        ("required", "missing", None, "WB: нужен код", "stop", False),
        ("unknown", "unknown", None, "Нет ответа WB", "stop", False),
    ],
)
def test_wb_order_verdict_maps_operator_states(
    decision: str,
    status: str,
    reason: str | None,
    signature: str,
    tone: str,
    allowed: bool,
) -> None:
    from types import SimpleNamespace

    from app.services.fbs_marking_service import _wb_order_verdict

    order = SimpleNamespace(required_meta_json=["sgtin"], optional_meta_json=[])
    marking = SimpleNamespace(
        kind="sgtin",
        value="01CIS-VERDICT",
        meta_status=status,
        reason=reason,
        meta_details_json={"decision": decision},
    )
    verdict = _wb_order_verdict(order, [marking])
    assert verdict == {
        "signature": signature,
        "tone": tone,
        "reason": reason,
        "delivery_allowed": allowed,
    }


def test_wb_order_verdict_any_blocker_wins_and_metadata_uses_it() -> None:
    from types import SimpleNamespace

    from app.services.fbs_marking_service import build_order_metadata

    order = SimpleNamespace(
        required_meta_json=["sgtin", "imei"],
        optional_meta_json=[],
        metadata_delivery_allowed=True,
        metadata_last_checked_at=None,
    )
    markings = [
        SimpleNamespace(
            kind="sgtin",
            value="01CIS-OK",
            meta_status=META_STATUS_ACCEPTED,
            reason=None,
            source="wb",
        ),
        SimpleNamespace(
            kind="imei",
            value="356938035643809",
            meta_status=META_STATUS_PENDING,
            reason=None,
            source="wb",
        ),
    ]
    for marking in markings:
        marking.meta_details_json = {"decision": "filled" if marking.kind == "sgtin" else "pending"}
    payload = build_order_metadata(order, markings)
    assert payload["verdict"]["signature"] == "WB: проверяет"
    assert payload["delivery_allowed"] is False
    assert payload["verdict"]["delivery_allowed"] is False


# S-03-TC-001…007 — one server verdict: reason and blocking WB decisions win.
@pytest.mark.parametrize(
    ("decision", "reason", "signature", "tone", "allowed"),
    [
        ("filled", None, "WB: принято", "ok", True),
        ("optional", None, "WB: код не требуется", "neutral", True),
        ("notRequired", None, "WB: код не требуется", "neutral", True),
        ("filled", "invalid_kiz", "WB не принял", "stop", False),
        ("pending", None, "WB: проверяет", "neutral", False),
        ("required", None, "WB: нужен код", "stop", False),
        ("mystery", None, "Нет ответа WB", "stop", False),
    ],
)
def test_wb_order_verdict_contract(
    decision: str,
    reason: str | None,
    signature: str,
    tone: str,
    allowed: bool,
) -> None:
    from types import SimpleNamespace

    from app.services.fbs_marking_service import _wb_order_verdict

    order = SimpleNamespace(required_meta_json=["sgtin"], optional_meta_json=[])
    marking = SimpleNamespace(
        kind="sgtin",
        meta_status="unknown",
        reason=reason,
        meta_details_json={"decision": decision},
    )
    verdict = _wb_order_verdict(order, [marking])
    assert verdict == {
        "signature": signature,
        "tone": tone,
        "reason": reason,
        "delivery_allowed": allowed,
    }


def test_wb_order_verdict_aggregates_blocker_over_positive() -> None:
    from types import SimpleNamespace

    from app.services.fbs_marking_service import _wb_order_verdict

    order = SimpleNamespace(required_meta_json=["sgtin", "imei"], optional_meta_json=[])
    markings = [
        SimpleNamespace(
            kind="sgtin", meta_status="accepted", reason=None,
            meta_details_json={"decision": "filled"},
        ),
        SimpleNamespace(
            kind="imei", meta_status="pending", reason=None,
            meta_details_json={"decision": "pending"},
        ),
    ]
    verdict = _wb_order_verdict(order, markings)
    assert verdict["signature"] == "WB: проверяет"
    assert verdict["delivery_allowed"] is False


def test_wb_order_verdict_blocks_absent_optional_response() -> None:
    from types import SimpleNamespace

    from app.services.fbs_marking_service import _wb_order_verdict

    order = SimpleNamespace(required_meta_json=[], optional_meta_json=["imei"])
    verdict = _wb_order_verdict(order, [])
    assert verdict["signature"] == "Нет ответа WB"
    assert verdict["delivery_allowed"] is False


def test_wb_order_verdict_missing_response_wins_over_pending() -> None:
    from types import SimpleNamespace

    from app.services.fbs_marking_service import _wb_order_verdict

    order = SimpleNamespace(required_meta_json=["sgtin", "imei"], optional_meta_json=[])
    pending = SimpleNamespace(
        kind="sgtin", meta_status="pending", reason=None,
        meta_details_json={"decision": "pending"},
    )
    assigned_without_decision = SimpleNamespace(
        kind="imei", meta_status="assigned", reason=None,
        meta_details_json={},
    )
    verdict = _wb_order_verdict(order, [pending, assigned_without_decision])
    assert verdict["signature"] == "Нет ответа WB"
    assert verdict["delivery_allowed"] is False


def test_compute_delivery_allowed_uses_reason_and_decision() -> None:
    from types import SimpleNamespace

    from app.services.fbs_marking_service import compute_delivery_allowed

    order = SimpleNamespace(required_meta_json=["sgtin"], optional_meta_json=[])
    marking = SimpleNamespace(
        kind="sgtin", meta_status="accepted", reason="uinBadStatus",
        meta_details_json={"decision": "filled"},
    )
    assert compute_delivery_allowed(order, [marking]) is False


def test_workspace_metadata_ready_uses_persisted_wb_rejection() -> None:
    """S-03-TC-003: a WB reason blocks workspace progress despite accepted code."""
    from types import SimpleNamespace

    from app.services.fbs_workspace_service import _metadata_ready

    rejected_by_wb = SimpleNamespace(
        metadata_delivery_allowed=False,
        required_meta_json=["sgtin"],
        meta_details_json={
            "sgtin": {
                "status": META_STATUS_ACCEPTED,
                "decision": "filled",
                "reason": "uinBadStatus",
            }
        },
    )
    legacy_accepted = SimpleNamespace(
        metadata_delivery_allowed=None,
        required_meta_json=["sgtin"],
        meta_details_json={"sgtin": {"status": META_STATUS_ACCEPTED}},
    )

    assert _metadata_ready(rejected_by_wb) is False
    assert _metadata_ready(legacy_accepted) is True


def test_wb_order_verdict_allows_order_without_metadata_requirements() -> None:
    from types import SimpleNamespace

    from app.services.fbs_marking_service import _wb_order_verdict

    order = SimpleNamespace(required_meta_json=[], optional_meta_json=[])
    verdict = _wb_order_verdict(order, [])
    assert verdict["signature"] == "WB: код не требуется"
    assert verdict["delivery_allowed"] is True


def test_wb_meta_parser_preserves_reason_from_real_response() -> None:
    from app.services.wildberries_fbs_client import _parse_meta_detail

    detail = _parse_meta_detail(
        {"key": "sgtin", "value": "123", "decision": "filled", "reason": "uinBadStatus"}
    )
    assert detail is not None
    assert detail.reason == "uinBadStatus"


@pytest.mark.asyncio
async def test_fbs_intake_stores_required_optional_meta(
    async_client: AsyncClient,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    order_id = await _create_order(
        tenant_id,
        uuid.UUID(seller_id),
        uuid.UUID(warehouse_id),
        order_id=960301,
        wb_row_extra={"requiredMeta": ["sgtin"], "optionalMeta": ["imei"]},
    )
    async with SessionLocal() as session:
        from app.models.fbs_order import FbsOrder

        order = await session.get(FbsOrder, order_id)
        assert order is not None
        assert order.required_meta_json == ["sgtin"]
        assert order.optional_meta_json == ["imei"]
