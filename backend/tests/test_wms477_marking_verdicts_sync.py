"""WMS-477 — «Проверить в WB» (R2/R3) и минутная сверка вердиктов ЧЗ (R5/R6/R7).

Кнопка и фоновая задача делят один сервисный путь
(`fbs_marking_service.sync_marking_verdicts_batch`): читаем все пакеты WB
пачками по 100, потом применяем — без HTTP между замками строк, и без единой
записи, если хотя бы один пакет не получен. Здесь проверяются:

- новая ручка `POST /operations/fbs-supplies/{supply_id}/markings/sync`
  (успех, отказ WB без частичной записи, чужая поставка, поставка не WB,
  отсутствие токена, поставка без единого кода);
- сервисная функция сверки пачками (нет частичной записи при отказе второго
  пакета — 101 заказ, чтобы гарантированно получить два пакета);
- фильтр фоновой задачи (только WB, только assembling/packed, только код в
  pending/sending);
- изоляция ошибок одного селлера в общем цикле;
- пробный advisory-замок цикла (наложение циклов) — только на PostgreSQL.

Постановка: docs/requirements/WMS-477.md.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.fbs_order import (
    CHECK_STATUS_NEW,
    CHECK_STATUS_OK,
    FBS_ORDER_STATUS_PACKED,
    META_STATUS_ACCEPTED,
    META_STATUS_ASSIGNED,
    META_STATUS_PENDING,
    META_STATUS_REJECTED,
    META_STATUS_SENDING,
    FbsOrder,
    FbsOrderMarking,
)
from app.models.fbs_supply import (
    FBS_SUPPLY_STATUS_ASSEMBLING,
    FBS_SUPPLY_STATUS_DRAFT,
    FBS_SUPPLY_STATUS_IN_DELIVERY,
    FBS_SUPPLY_STATUS_PACKED,
    FbsSupply,
)
from app.models.product import Product
from app.services import fbs_autopoll_service as autopoll
from app.services import fbs_marking_service as marking_svc
from app.services.wildberries_client import WildberriesClientError
from app.services.wildberries_fbs_client import MarketplaceMetaDetail, MarketplaceOrderMetaRow
from tests.test_fbs_marking import _register_ff_admin, _setup_seller_with_token, _wb_order_row


async def _setup_seller_without_token(
    async_client: AsyncClient,
    headers: dict[str, str],
    suffix: str,
) -> tuple[str, str, uuid.UUID]:
    """Same as _setup_seller_with_token, minus the WB token PATCH call."""
    seller = await async_client.post(
        "/sellers", headers=headers, json={"name": f"Seller {suffix}"}
    )
    assert seller.status_code in (200, 201), seller.text
    seller_id = seller.json()["id"]
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


async def _seed_coded_wb_order(
    *,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    supply_id: uuid.UUID,
    wb_order_id: int,
    meta_status: str = META_STATUS_PENDING,
) -> tuple[uuid.UUID, str]:
    """Real WB order (via upsert_order_from_wb_row) + one sgtin marking, in `supply_id`.

    Uses the same helper as the rest of the marking tests (see
    tests/test_fbs_marking.py::_create_order and test_fbs_tracking.py's
    _seed_in_delivery_supply) so the order carries whatever fields
    `get_supply_workspace` needs — this is what lets the HTTP-level tests
    below actually reach a rendered FbsWorkspaceOut instead of crashing on a
    hand-rolled, incomplete order.
    """
    from app.services.wb_marketplace_orders_service import upsert_order_from_wb_row
    from tests.fbs_seed_helpers import seed_fbs_warehouse_binding

    value = f"01WMS477{wb_order_id}"
    async with SessionLocal() as session:
        await seed_fbs_warehouse_binding(
            session, tenant_id=tenant_id, seller_id=seller_id, wms_warehouse_id=warehouse_id
        )
        order, _ = await upsert_order_from_wb_row(
            session, tenant_id, seller_id, _wb_order_row(order_id=wb_order_id)
        )
        order.supply_id = supply_id
        order.status = FBS_ORDER_STATUS_PACKED
        check_status = CHECK_STATUS_NEW if meta_status == META_STATUS_PENDING else CHECK_STATUS_OK
        session.add(
            FbsOrderMarking(
                order_id=order.id,
                tenant_id=tenant_id,
                kind="sgtin",
                value=value,
                check_status=check_status,
                meta_status=meta_status,
            )
        )
        await session.commit()
        return order.id, value


async def _make_wb_supply(
    *, tenant_id: uuid.UUID, seller_id: uuid.UUID, warehouse_id: uuid.UUID, status: str, marker: str
) -> uuid.UUID:
    supply_id = uuid.uuid4()
    async with SessionLocal() as session:
        session.add(
            FbsSupply(
                id=supply_id,
                tenant_id=tenant_id,
                seller_id=seller_id,
                warehouse_id=warehouse_id,
                wb_supply_id=f"WB-{marker}-{supply_id.hex[:8]}",
                name=f"WMS-477 {marker} supply",
                status=status,
                delivery_type="warehouse_sc",
            )
        )
        await session.commit()
    return supply_id


async def _marking_status(order_id: uuid.UUID) -> str | None:
    async with SessionLocal() as session:
        return await session.scalar(
            select(FbsOrderMarking.meta_status).where(FbsOrderMarking.order_id == order_id)
        )


def _fail_if_called(*_args: object, **_kwargs: object) -> None:
    raise AssertionError("must not call WB for this scenario")


# --------------------------------------------------------------------------
# R2/R3 — POST /operations/fbs-supplies/{supply_id}/markings/sync
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_markings_sync_endpoint_success_updates_workspace(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    seller_uuid, warehouse_uuid = uuid.UUID(seller_id), uuid.UUID(warehouse_id)
    supply_id = await _make_wb_supply(
        tenant_id=tenant_id,
        seller_id=seller_uuid,
        warehouse_id=warehouse_uuid,
        status=FBS_SUPPLY_STATUS_ASSEMBLING,
        marker="OK",
    )
    confirmed_id, confirmed_value = await _seed_coded_wb_order(
        tenant_id=tenant_id,
        seller_id=seller_uuid,
        warehouse_id=warehouse_uuid,
        supply_id=supply_id,
        wb_order_id=977001,
    )
    pending_id, pending_value = await _seed_coded_wb_order(
        tenant_id=tenant_id,
        seller_id=seller_uuid,
        warehouse_id=warehouse_uuid,
        supply_id=supply_id,
        wb_order_id=977002,
    )

    requested: list[int] = []

    async def fake_fetch_batch(
        client: object,
        *,
        api_token: str,
        order_ids: list[int],
        marketplace_api_base: str | None = None,
    ) -> list[MarketplaceOrderMetaRow]:
        requested.extend(order_ids)
        assert set(order_ids) == {977001, 977002}
        return [
            MarketplaceOrderMetaRow(
                order_id=977001,
                meta_details=(
                    MarketplaceMetaDetail(
                        key="sgtin", value=confirmed_value, decision="sgtinIntroduced"
                    ),
                ),
            ),
            MarketplaceOrderMetaRow(
                order_id=977002,
                meta_details=(
                    MarketplaceMetaDetail(key="sgtin", value=pending_value, decision="pending"),
                ),
            ),
        ]

    monkeypatch.setattr(
        "app.services.fbs_marking_service.fetch_marketplace_orders_meta_batch",
        fake_fetch_batch,
    )

    resp = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/markings/sync",
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["supply"]["id"] == str(supply_id)
    assert len(requested) == 2  # one batch call for the whole supply

    assert await _marking_status(confirmed_id) == META_STATUS_ACCEPTED
    assert await _marking_status(pending_id) == META_STATUS_PENDING

    async with SessionLocal() as session:
        confirmed_order = await session.get(FbsOrder, confirmed_id)
        assert confirmed_order is not None
        assert confirmed_order.metadata_delivery_allowed is True
        assert confirmed_order.metadata_last_checked_at is not None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error_code", "status_code"),
    [("upstream_error", 429), ("upstream_error", 503), ("network_error", None)],
)
async def test_markings_sync_endpoint_wb_error_leaves_no_partial_write(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    error_code: str,
    status_code: int | None,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    seller_uuid, warehouse_uuid = uuid.UUID(seller_id), uuid.UUID(warehouse_id)
    supply_id = await _make_wb_supply(
        tenant_id=tenant_id,
        seller_id=seller_uuid,
        warehouse_id=warehouse_uuid,
        status=FBS_SUPPLY_STATUS_ASSEMBLING,
        marker="WBFAIL",
    )
    order_id, _value = await _seed_coded_wb_order(
        tenant_id=tenant_id,
        seller_id=seller_uuid,
        warehouse_id=warehouse_uuid,
        supply_id=supply_id,
        wb_order_id=977101,
    )

    async def fake_fetch_batch(
        client: object,
        *,
        api_token: str,
        order_ids: list[int],
        marketplace_api_base: str | None = None,
    ) -> list[MarketplaceOrderMetaRow]:
        raise WildberriesClientError(error_code, status_code=status_code)

    monkeypatch.setattr(
        "app.services.fbs_marking_service.fetch_marketplace_orders_meta_batch",
        fake_fetch_batch,
    )

    resp = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/markings/sync",
        headers=headers,
    )
    assert resp.status_code == 502, resp.text
    detail = resp.json()["detail"]
    assert detail["code"] == f"wb_{error_code}" + (f"_{status_code}" if status_code else "")
    assert detail["retryable"] is True

    assert await _marking_status(order_id) == META_STATUS_PENDING

    # The operator is not locked out: printing/scanning and the rest of the
    # supply endpoints keep working, and a retry after WB recovers succeeds.
    workspace = await async_client.get(
        f"/operations/fbs-supplies/{supply_id}/workspace",
        headers=headers,
    )
    assert workspace.status_code == 200, workspace.text

    async def recovered_fetch(*_args: object, **_kwargs: object) -> list[MarketplaceOrderMetaRow]:
        return [
            MarketplaceOrderMetaRow(
                order_id=977101,
                meta_details=(
                    MarketplaceMetaDetail(key="sgtin", value=_value, decision="sgtinIntroduced"),
                ),
            )
        ]

    monkeypatch.setattr(marking_svc, "fetch_marketplace_orders_meta_batch", recovered_fetch)
    retry = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/markings/sync", headers=headers
    )
    assert retry.status_code == 200, retry.text
    assert await _marking_status(order_id) == META_STATUS_ACCEPTED


@pytest.mark.asyncio
async def test_sync_marking_verdicts_batch_no_partial_write_across_two_batches(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """101 coded orders → 2 WB batches; the 2nd fails → nothing from batch 1 sticks either."""
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    seller_uuid, warehouse_uuid = uuid.UUID(seller_id), uuid.UUID(warehouse_id)
    wb_order_ids = list(range(978000, 978101))  # 101 → batches of 100 + 1
    now = datetime.now(tz=UTC)
    supply_id = uuid.uuid4()
    async with SessionLocal() as session:
        session.add(
            FbsSupply(
                id=supply_id,
                tenant_id=tenant_id,
                seller_id=seller_uuid,
                warehouse_id=warehouse_uuid,
                wb_supply_id=f"WB-NOPART-{suffix[-8:]}",
                name="No-partial-write supply",
                status=FBS_SUPPLY_STATUS_PACKED,
                delivery_type="warehouse_sc",
            )
        )
        await session.flush()
        for index, wb_order_id in enumerate(wb_order_ids):
            order = FbsOrder(
                tenant_id=tenant_id,
                seller_id=seller_uuid,
                warehouse_id=warehouse_uuid,
                wb_order_id=wb_order_id,
                wb_rid=f"nopart-rid-{wb_order_id}",
                status=FBS_ORDER_STATUS_PACKED,
                supply_id=supply_id,
                created_at_wb=now + timedelta(seconds=index),
                deadline_at=now + timedelta(days=1),
                mapping_status="mapped",
                reserve_status="reserved",
            )
            session.add(order)
            await session.flush()
            session.add(
                FbsOrderMarking(
                    order_id=order.id,
                    tenant_id=tenant_id,
                    kind="sgtin",
                    value=f"01NOPART{wb_order_id}",
                    check_status=CHECK_STATUS_NEW,
                    meta_status=META_STATUS_PENDING,
                )
            )
        await session.commit()

    requested_batches: list[list[int]] = []

    async def fake_fetch_batch(
        client: object,
        *,
        api_token: str,
        order_ids: list[int],
        marketplace_api_base: str | None = None,
    ) -> list[MarketplaceOrderMetaRow]:
        requested_batches.append(order_ids)
        if len(requested_batches) == 2:
            raise WildberriesClientError("upstream_error")
        return [
            MarketplaceOrderMetaRow(
                order_id=oid,
                meta_details=(
                    MarketplaceMetaDetail(
                        key="sgtin", value=f"01NOPART{oid}", decision="sgtinIntroduced"
                    ),
                ),
            )
            for oid in order_ids
        ]

    monkeypatch.setattr(
        "app.services.fbs_marking_service.fetch_marketplace_orders_meta_batch",
        fake_fetch_batch,
    )

    async with SessionLocal() as session:
        with pytest.raises(marking_svc.FbsMarkingError) as exc_info:
            await marking_svc.sync_marking_verdicts_for_supply(
                session,
                tenant_id,
                supply_id,
                async_client,
                actor_user_id=None,
            )
    assert exc_info.value.code.startswith("wb_")
    assert [len(batch) for batch in requested_batches] == [100, 1]

    async with SessionLocal() as session:
        markings = list(
            (
                await session.execute(
                    select(FbsOrderMarking)
                    .join(FbsOrder, FbsOrder.id == FbsOrderMarking.order_id)
                    .where(FbsOrder.supply_id == supply_id)
                )
            )
            .scalars()
            .all()
        )
    assert len(markings) == 101
    assert all(
        marking.meta_status == META_STATUS_PENDING and marking.check_status == CHECK_STATUS_NEW
        for marking in markings
    )


@pytest.mark.asyncio
async def test_markings_sync_endpoint_foreign_supply_is_404(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner_headers, owner_suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_with_token(
        async_client, owner_headers, owner_suffix
    )
    supply_id = await _make_wb_supply(
        tenant_id=tenant_id,
        seller_id=uuid.UUID(seller_id),
        warehouse_id=uuid.UUID(warehouse_id),
        status=FBS_SUPPLY_STATUS_ASSEMBLING,
        marker="FOREIGN",
    )
    await _seed_coded_wb_order(
        tenant_id=tenant_id,
        seller_id=uuid.UUID(seller_id),
        warehouse_id=uuid.UUID(warehouse_id),
        supply_id=supply_id,
        wb_order_id=977201,
    )

    stranger_headers, _stranger_suffix = await _register_ff_admin(async_client)
    monkeypatch.setattr(
        "app.services.fbs_marking_service.fetch_marketplace_orders_meta_batch",
        _fail_if_called,
    )

    resp = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/markings/sync",
        headers=stranger_headers,
    )
    assert resp.status_code == 404, resp.text
    assert resp.json()["detail"]["code"] == "supply_not_found"


@pytest.mark.asyncio
async def test_markings_sync_endpoint_ozon_supply_is_a_noop(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R2 scopes the query to WB orders; an Ozon supply naturally makes zero WB calls."""
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    seller_uuid, warehouse_uuid = uuid.UUID(seller_id), uuid.UUID(warehouse_id)
    supply_id = uuid.uuid4()
    order_id = uuid.uuid4()
    now = datetime.now(tz=UTC)
    async with SessionLocal() as session:
        session.add(
            Product(
                tenant_id=tenant_id,
                seller_id=seller_uuid,
                name="WMS-477 Ozon product",
                sku_code=f"sku-{suffix[-8:]}",
            )
        )
        session.add(
            FbsSupply(
                id=supply_id,
                tenant_id=tenant_id,
                seller_id=seller_uuid,
                warehouse_id=warehouse_uuid,
                marketplace="ozon",
                wb_supply_id=None,
                external_supply_id=f"ozon-supply-{suffix[-8:]}",
                name="WMS-477 Ozon supply",
                status=FBS_SUPPLY_STATUS_PACKED,
                delivery_type="warehouse_sc",
            )
        )
        session.add(
            FbsOrder(
                id=order_id,
                tenant_id=tenant_id,
                seller_id=seller_uuid,
                warehouse_id=warehouse_uuid,
                marketplace="ozon",
                external_order_id=f"ozon-posting-{suffix[-8:]}",
                wb_order_id=500001,
                status=FBS_ORDER_STATUS_PACKED,
                supply_id=supply_id,
                created_at_wb=now,
                deadline_at=now + timedelta(days=1),
                mapping_status="mapped",
                reserve_status="reserved",
                meta_details_json={"ozon_requirements": {"kinds": []}},
            )
        )
        await session.flush()
        session.add(
            FbsOrderMarking(
                order_id=order_id,
                tenant_id=tenant_id,
                kind="sgtin",
                value="01OZONWMS477",
                check_status=CHECK_STATUS_NEW,
                meta_status=META_STATUS_PENDING,
            )
        )
        await session.commit()

    monkeypatch.setattr(
        "app.services.fbs_marking_service.fetch_marketplace_orders_meta_batch",
        _fail_if_called,
    )

    resp = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/markings/sync",
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["supply"]["marketplace"] == "ozon"
    assert await _marking_status(order_id) == META_STATUS_PENDING


@pytest.mark.asyncio
async def test_markings_sync_endpoint_missing_token_is_403(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_without_token(
        async_client, headers, suffix
    )
    seller_uuid, warehouse_uuid = uuid.UUID(seller_id), uuid.UUID(warehouse_id)
    supply_id = await _make_wb_supply(
        tenant_id=tenant_id,
        seller_id=seller_uuid,
        warehouse_id=warehouse_uuid,
        status=FBS_SUPPLY_STATUS_ASSEMBLING,
        marker="NOTOKEN",
    )
    order_id, _value = await _seed_coded_wb_order(
        tenant_id=tenant_id,
        seller_id=seller_uuid,
        warehouse_id=warehouse_uuid,
        supply_id=supply_id,
        wb_order_id=977301,
    )
    monkeypatch.setattr(
        "app.services.fbs_marking_service.fetch_marketplace_orders_meta_batch",
        _fail_if_called,
    )

    resp = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/markings/sync",
        headers=headers,
    )
    assert resp.status_code == 403, resp.text
    assert resp.json()["detail"]["code"] == "missing_marketplace_token"
    assert await _marking_status(order_id) == META_STATUS_PENDING


@pytest.mark.asyncio
async def test_markings_sync_endpoint_no_codes_is_a_noop(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    supply_id = await _make_wb_supply(
        tenant_id=tenant_id,
        seller_id=uuid.UUID(seller_id),
        warehouse_id=uuid.UUID(warehouse_id),
        status=FBS_SUPPLY_STATUS_ASSEMBLING,
        marker="NOCODE",
    )
    monkeypatch.setattr(
        "app.services.fbs_marking_service.fetch_marketplace_orders_meta_batch",
        _fail_if_called,
    )

    resp = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/markings/sync",
        headers=headers,
    )
    assert resp.status_code == 200, resp.text


# --------------------------------------------------------------------------
# R5/R6/R7 — фоновая сверка вердиктов ЧЗ
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sync_marking_verdicts_for_seller_filters_pending_sending_only(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    seller_uuid, warehouse_uuid = uuid.UUID(seller_id), uuid.UUID(warehouse_id)
    now = datetime.now(tz=UTC)

    async def make_order(
        supply_status: str,
        wb_order_id: int,
        meta_status: str,
        *,
        marketplace: str = "wb",
    ) -> uuid.UUID:
        supply_id = uuid.uuid4()
        order_id = uuid.uuid4()
        async with SessionLocal() as session:
            session.add(
                FbsSupply(
                    id=supply_id,
                    tenant_id=tenant_id,
                    seller_id=seller_uuid,
                    warehouse_id=warehouse_uuid,
                    marketplace=marketplace,
                    wb_supply_id=f"WB-FILT-{supply_id.hex[:8]}",
                    name="filter supply",
                    status=supply_status,
                    delivery_type="warehouse_sc",
                )
            )
            session.add(
                FbsOrder(
                    id=order_id,
                    tenant_id=tenant_id,
                    seller_id=seller_uuid,
                    warehouse_id=warehouse_uuid,
                    marketplace=marketplace,
                    wb_order_id=wb_order_id,
                    wb_rid=f"filt-rid-{wb_order_id}",
                    status=FBS_ORDER_STATUS_PACKED,
                    supply_id=supply_id,
                    created_at_wb=now,
                    deadline_at=now + timedelta(days=1),
                    mapping_status="mapped",
                    reserve_status="reserved",
                )
            )
            await session.flush()
            session.add(
                FbsOrderMarking(
                    order_id=order_id,
                    tenant_id=tenant_id,
                    kind="sgtin",
                    value=f"01FILT{wb_order_id}",
                    check_status=(
                        CHECK_STATUS_NEW if meta_status == META_STATUS_PENDING else CHECK_STATUS_OK
                    ),
                    meta_status=meta_status,
                )
            )
            await session.commit()
        return order_id

    qualifies_pending = await make_order(FBS_SUPPLY_STATUS_ASSEMBLING, 981001, META_STATUS_PENDING)
    qualifies_sending = await make_order(FBS_SUPPLY_STATUS_PACKED, 981002, META_STATUS_SENDING)
    excluded_accepted = await make_order(FBS_SUPPLY_STATUS_ASSEMBLING, 981003, META_STATUS_ACCEPTED)
    excluded_draft = await make_order(FBS_SUPPLY_STATUS_DRAFT, 981004, META_STATUS_PENDING)
    excluded_in_delivery = await make_order(
        FBS_SUPPLY_STATUS_IN_DELIVERY, 981005, META_STATUS_PENDING
    )
    excluded_ozon = await make_order(
        FBS_SUPPLY_STATUS_ASSEMBLING, 981006, META_STATUS_PENDING, marketplace="ozon"
    )

    requested: list[int] = []

    async def fake_fetch_batch(
        client: object,
        *,
        api_token: str,
        order_ids: list[int],
        marketplace_api_base: str | None = None,
    ) -> list[MarketplaceOrderMetaRow]:
        requested.extend(order_ids)
        return [
            MarketplaceOrderMetaRow(
                order_id=oid,
                meta_details=(
                    MarketplaceMetaDetail(
                        key="sgtin", value=f"01FILT{oid}", decision="sgtinIntroduced"
                    ),
                ),
            )
            for oid in order_ids
        ]

    monkeypatch.setattr(
        "app.services.fbs_marking_service.fetch_marketplace_orders_meta_batch",
        fake_fetch_batch,
    )

    async with SessionLocal() as session:
        result = await autopoll.sync_marking_verdicts_for_seller(
            session,
            autopoll.SellerPollTarget(tenant_id=tenant_id, seller_id=seller_uuid),
            async_client,
        )
        await session.commit()

    assert set(requested) == {981001, 981002}
    assert result.orders_checked == 2
    assert result.orders_updated == 2

    assert await _marking_status(qualifies_pending) == META_STATUS_ACCEPTED
    assert await _marking_status(qualifies_sending) == META_STATUS_ACCEPTED
    assert await _marking_status(excluded_accepted) == META_STATUS_ACCEPTED
    assert await _marking_status(excluded_draft) == META_STATUS_PENDING
    assert await _marking_status(excluded_in_delivery) == META_STATUS_PENDING
    assert await _marking_status(excluded_ozon) == META_STATUS_PENDING


@pytest.mark.asyncio
async def test_sync_fbs_marking_verdicts_all_sellers_isolates_seller_errors(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers_a, suffix_a = await _register_ff_admin(async_client)
    seller_a, warehouse_a, tenant_a = await _setup_seller_with_token(
        async_client, headers_a, suffix_a
    )
    headers_b, suffix_b = await _register_ff_admin(async_client)
    seller_b, warehouse_b, tenant_b = await _setup_seller_with_token(
        async_client, headers_b, suffix_b
    )
    now = datetime.now(tz=UTC)

    async def make_pending_order(
        tenant_id: uuid.UUID, seller_id: uuid.UUID, warehouse_id: uuid.UUID, wb_order_id: int
    ) -> uuid.UUID:
        from tests.fbs_seed_helpers import seed_fbs_warehouse_binding

        supply_id = uuid.uuid4()
        order_id = uuid.uuid4()
        async with SessionLocal() as session:
            # list_sellers_with_marketplace_token (used by the top-level cycle
            # under test here) requires an active, served WB binding — without
            # it the seller is invisible to the cycle regardless of its orders.
            await seed_fbs_warehouse_binding(
                session, tenant_id=tenant_id, seller_id=seller_id, wms_warehouse_id=warehouse_id
            )
            session.add(
                FbsSupply(
                    id=supply_id,
                    tenant_id=tenant_id,
                    seller_id=seller_id,
                    warehouse_id=warehouse_id,
                    wb_supply_id=f"WB-ISO-{supply_id.hex[:8]}",
                    name="isolation supply",
                    status=FBS_SUPPLY_STATUS_ASSEMBLING,
                    delivery_type="warehouse_sc",
                )
            )
            session.add(
                FbsOrder(
                    id=order_id,
                    tenant_id=tenant_id,
                    seller_id=seller_id,
                    warehouse_id=warehouse_id,
                    wb_order_id=wb_order_id,
                    wb_rid=f"iso-rid-{wb_order_id}",
                    status=FBS_ORDER_STATUS_PACKED,
                    supply_id=supply_id,
                    created_at_wb=now,
                    deadline_at=now + timedelta(days=1),
                    mapping_status="mapped",
                    reserve_status="reserved",
                )
            )
            await session.flush()
            session.add(
                FbsOrderMarking(
                    order_id=order_id,
                    tenant_id=tenant_id,
                    kind="sgtin",
                    value=f"01ISO{wb_order_id}",
                    check_status=CHECK_STATUS_NEW,
                    meta_status=META_STATUS_PENDING,
                )
            )
            await session.commit()
        return order_id

    order_a = await make_pending_order(
        tenant_a, uuid.UUID(seller_a), uuid.UUID(warehouse_a), 982001
    )
    order_b = await make_pending_order(
        tenant_b, uuid.UUID(seller_b), uuid.UUID(warehouse_b), 982002
    )

    async def fake_fetch_batch(
        client: object,
        *,
        api_token: str,
        order_ids: list[int],
        marketplace_api_base: str | None = None,
    ) -> list[MarketplaceOrderMetaRow]:
        if 982001 in order_ids:
            raise WildberriesClientError("upstream_error")
        return [
            MarketplaceOrderMetaRow(
                order_id=oid,
                meta_details=(
                    MarketplaceMetaDetail(
                        key="sgtin", value=f"01ISO{oid}", decision="sgtinIntroduced"
                    ),
                ),
            )
            for oid in order_ids
        ]

    monkeypatch.setattr(
        "app.services.fbs_marking_service.fetch_marketplace_orders_meta_batch",
        fake_fetch_batch,
    )

    result = await autopoll.sync_fbs_marking_verdicts_all_sellers()

    assert result.skipped is False
    assert result.seller_errors >= 1
    assert result.sellers_checked >= 1
    assert result.orders_updated >= 1

    # The failing seller's code is untouched; the healthy seller's went through.
    assert await _marking_status(order_a) == META_STATUS_PENDING
    assert await _marking_status(order_b) == META_STATUS_ACCEPTED


# --------------------------------------------------------------------------
# Astra review round 1 (docs/reviews/2026-09-19-wms477/review-astra-1.md) —
# findings 1, 3, 4. Findings 2 (frontend) and 5-7 (no fix required) are not
# addressed here.
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stale_new_cycle_answer_does_not_revert_a_fresher_general_cycle_verdict(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Finding 1 — a slow `pending` from the minute cycle must not undo a
    faster `accepted` the general cycle (`fbs-order-statuses-autopoll`, R7,
    untouched) already committed for the very same code. Reproduces the
    reviewer's exact sequence: minute cycle's WB call is still out when the
    general cycle's own (independent) WB call returns and commits first.
    """
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    seller_uuid, warehouse_uuid = uuid.UUID(seller_id), uuid.UUID(warehouse_id)
    supply_id = await _make_wb_supply(
        tenant_id=tenant_id,
        seller_id=seller_uuid,
        warehouse_id=warehouse_uuid,
        status=FBS_SUPPLY_STATUS_ASSEMBLING,
        marker="RACE1",
    )
    order_id, value = await _seed_coded_wb_order(
        tenant_id=tenant_id,
        seller_id=seller_uuid,
        warehouse_id=warehouse_uuid,
        supply_id=supply_id,
        wb_order_id=983001,
    )
    target = autopoll.SellerPollTarget(tenant_id=tenant_id, seller_id=seller_uuid)
    fetching, proceed = asyncio.Event(), asyncio.Event()

    async def slow_new_cycle_fetch(
        client: object,
        *,
        api_token: str,
        order_ids: list[int],
        marketplace_api_base: str | None = None,
    ) -> list[MarketplaceOrderMetaRow]:
        fetching.set()
        await proceed.wait()
        return [
            MarketplaceOrderMetaRow(
                order_id=983001,
                meta_details=(
                    MarketplaceMetaDetail(key="sgtin", value=value, decision="pending"),
                ),
            )
        ]

    async def fast_general_cycle_fetch(
        client: object,
        *,
        api_token: str,
        order_ids: list[int],
        marketplace_api_base: str | None = None,
    ) -> list[MarketplaceOrderMetaRow]:
        return [
            MarketplaceOrderMetaRow(
                order_id=983001,
                meta_details=(
                    MarketplaceMetaDetail(
                        key="sgtin", value=value, decision="sgtinIntroduced"
                    ),
                ),
            )
        ]

    monkeypatch.setattr(
        "app.services.fbs_marking_service.fetch_marketplace_orders_meta_batch",
        slow_new_cycle_fetch,
    )

    async with SessionLocal() as new_cycle_session:
        new_cycle_task = asyncio.create_task(
            autopoll.sync_marking_verdicts_for_seller(new_cycle_session, target, async_client)
        )
        try:
            await asyncio.wait_for(fetching.wait(), 5)

            # sync_marking_statuses_for_assembling_supplies imports the WB
            # client inline, from wildberries_fbs_client — not the name the
            # minute cycle patched above — so both mocks coexist independently.
            monkeypatch.setattr(
                "app.services.wildberries_fbs_client.fetch_marketplace_orders_meta_batch",
                fast_general_cycle_fetch,
            )
            async with SessionLocal() as general_session:
                synced = await autopoll.sync_marking_statuses_for_assembling_supplies(
                    general_session, target, async_client
                )
                await general_session.commit()
            assert synced == 1
            assert await _marking_status(order_id) == META_STATUS_ACCEPTED

            proceed.set()
            result = await asyncio.wait_for(new_cycle_task, 5)
            await new_cycle_session.commit()
        finally:
            proceed.set()
            if not new_cycle_task.done():
                new_cycle_task.cancel()
            await asyncio.gather(new_cycle_task, return_exceptions=True)

    assert result.orders_checked == 1
    assert result.orders_updated == 0  # its own answer was stale, correctly skipped
    assert await _marking_status(order_id) == META_STATUS_ACCEPTED  # not reverted to pending


@pytest.mark.asyncio
async def test_stale_new_cycle_answer_does_not_revert_a_fresher_button_verdict(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Finding 1, second pairing named by the reviewer — minute cycle vs the
    "Проверить в WB" button. Both go through the same `sync_marking_verdicts_batch`,
    so this also proves the shared application point protects same-function callers
    racing each other, not just the minute cycle against the (untouched) general one.
    """
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    seller_uuid, warehouse_uuid = uuid.UUID(seller_id), uuid.UUID(warehouse_id)
    supply_id = await _make_wb_supply(
        tenant_id=tenant_id,
        seller_id=seller_uuid,
        warehouse_id=warehouse_uuid,
        status=FBS_SUPPLY_STATUS_ASSEMBLING,
        marker="RACE2",
    )
    order_id, value = await _seed_coded_wb_order(
        tenant_id=tenant_id,
        seller_id=seller_uuid,
        warehouse_id=warehouse_uuid,
        supply_id=supply_id,
        wb_order_id=983101,
    )
    target = autopoll.SellerPollTarget(tenant_id=tenant_id, seller_id=seller_uuid)
    fetching, proceed = asyncio.Event(), asyncio.Event()
    calls = 0

    async def fetch_mock(
        client: object,
        *,
        api_token: str,
        order_ids: list[int],
        marketplace_api_base: str | None = None,
    ) -> list[MarketplaceOrderMetaRow]:
        nonlocal calls
        calls += 1
        if calls == 1:
            # The minute cycle's call: hold it until the button's answer wins.
            fetching.set()
            await proceed.wait()
            return [
                MarketplaceOrderMetaRow(
                    order_id=983101,
                    meta_details=(
                        MarketplaceMetaDetail(key="sgtin", value=value, decision="pending"),
                    ),
                )
            ]
        # The button's call: resolves immediately with WB's final verdict.
        return [
            MarketplaceOrderMetaRow(
                order_id=983101,
                meta_details=(
                    MarketplaceMetaDetail(
                        key="sgtin", value=value, decision="sgtinIntroduced"
                    ),
                ),
            )
        ]

    monkeypatch.setattr(
        "app.services.fbs_marking_service.fetch_marketplace_orders_meta_batch", fetch_mock
    )

    async with SessionLocal() as new_cycle_session:
        new_cycle_task = asyncio.create_task(
            autopoll.sync_marking_verdicts_for_seller(new_cycle_session, target, async_client)
        )
        try:
            await asyncio.wait_for(fetching.wait(), 5)

            async with SessionLocal() as button_session:
                button_result = await marking_svc.sync_marking_verdicts_for_supply(
                    button_session,
                    tenant_id,
                    supply_id,
                    async_client,
                    actor_user_id=None,
                )
                await button_session.commit()
            assert button_result.orders_updated == 1
            assert await _marking_status(order_id) == META_STATUS_ACCEPTED

            proceed.set()
            new_cycle_result = await asyncio.wait_for(new_cycle_task, 5)
            await new_cycle_session.commit()
        finally:
            proceed.set()
            if not new_cycle_task.done():
                new_cycle_task.cancel()
            await asyncio.gather(new_cycle_task, return_exceptions=True)

    assert new_cycle_result.orders_updated == 0
    assert await _marking_status(order_id) == META_STATUS_ACCEPTED


@pytest.mark.asyncio
async def test_replaced_code_during_http_is_not_counted_as_updated(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Finding 4 — a code replaced while its own WB answer is in flight is
    correctly left alone by `_sync_order_meta_from_wb` (pre-existing ID check),
    but the caller used to count it as `orders_updated` anyway."""
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    seller_uuid, warehouse_uuid = uuid.UUID(seller_id), uuid.UUID(warehouse_id)
    supply_id = await _make_wb_supply(
        tenant_id=tenant_id,
        seller_id=seller_uuid,
        warehouse_id=warehouse_uuid,
        status=FBS_SUPPLY_STATUS_ASSEMBLING,
        marker="COUNT",
    )
    order_id, old_value = await _seed_coded_wb_order(
        tenant_id=tenant_id,
        seller_id=seller_uuid,
        warehouse_id=warehouse_uuid,
        supply_id=supply_id,
        wb_order_id=985001,
    )
    fetching, proceed = asyncio.Event(), asyncio.Event()

    async def slow_fetch(
        client: object,
        *,
        api_token: str,
        order_ids: list[int],
        marketplace_api_base: str | None = None,
    ) -> list[MarketplaceOrderMetaRow]:
        fetching.set()
        await proceed.wait()
        return [
            MarketplaceOrderMetaRow(
                order_id=985001,
                meta_details=(
                    MarketplaceMetaDetail(
                        key="sgtin", value=old_value, decision="sgtinIntroduced"
                    ),
                ),
            )
        ]

    monkeypatch.setattr(
        "app.services.fbs_marking_service.fetch_marketplace_orders_meta_batch", slow_fetch
    )

    async with SessionLocal() as reader_session:
        reading = asyncio.create_task(
            marking_svc.sync_marking_verdicts_for_supply(
                reader_session,
                tenant_id,
                supply_id,
                async_client,
                actor_user_id=None,
            )
        )
        try:
            await asyncio.wait_for(fetching.wait(), 5)

            # The operator scans a replacement code while the HTTP call is out.
            async with SessionLocal() as writer_session:
                old_marking = await writer_session.scalar(
                    select(FbsOrderMarking).where(FbsOrderMarking.order_id == order_id)
                )
                assert old_marking is not None
                await writer_session.delete(old_marking)
                await writer_session.flush()
                writer_session.add(
                    FbsOrderMarking(
                        order_id=order_id,
                        tenant_id=tenant_id,
                        kind="sgtin",
                        value="01REPLACEDDURINGHTTP",
                        check_status=CHECK_STATUS_NEW,
                        meta_status=META_STATUS_ASSIGNED,
                    )
                )
                await writer_session.commit()

            proceed.set()
            result = await asyncio.wait_for(reading, 5)
            await reader_session.commit()
        finally:
            proceed.set()
            if not reading.done():
                reading.cancel()
            await asyncio.gather(reading, return_exceptions=True)

    assert result.orders_checked == 1
    assert result.orders_updated == 0
    assert await _marking_status(order_id) == META_STATUS_ASSIGNED


@pytest.mark.asyncio
async def test_minute_cycle_skips_seller_when_wb_backoff_is_active(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Finding 3, part 1 — an already-active WB backoff (shared with the
    general cycle via the same `_MARKETPLACE_BACKOFF` object) must skip the
    seller before any WB call, not just log and continue."""
    from app.services.marketplace_provider import MarketplaceBackoff

    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    seller_uuid, warehouse_uuid = uuid.UUID(seller_id), uuid.UUID(warehouse_id)
    supply_id = await _make_wb_supply(
        tenant_id=tenant_id,
        seller_id=seller_uuid,
        warehouse_id=warehouse_uuid,
        status=FBS_SUPPLY_STATUS_ASSEMBLING,
        marker="BACKOFF1",
    )
    order_id, _value = await _seed_coded_wb_order(
        tenant_id=tenant_id,
        seller_id=seller_uuid,
        warehouse_id=warehouse_uuid,
        supply_id=supply_id,
        wb_order_id=984001,
    )
    monkeypatch.setattr(autopoll, "_MARKETPLACE_BACKOFF", MarketplaceBackoff())
    autopoll._MARKETPLACE_BACKOFF.record_rate_limit("wb", retry_after_seconds=300)
    monkeypatch.setattr(
        "app.services.fbs_marking_service.fetch_marketplace_orders_meta_batch",
        _fail_if_called,
    )

    result = await autopoll.sync_fbs_marking_verdicts_all_sellers()

    assert result.skipped is False
    assert result.backoff_skips == 1
    assert result.sellers_checked == 0
    assert result.seller_errors == 0
    assert await _marking_status(order_id) == META_STATUS_PENDING


@pytest.mark.asyncio
async def test_minute_cycle_records_wb_backoff_after_persistent_429(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Finding 3, part 2 — a 429 that survives the client's own one-shot retry
    must arm the shared backoff so the rest of this cycle (and the general
    cycle, reading the same object) backs off too."""
    from app.services.marketplace_provider import MarketplaceBackoff

    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    seller_uuid, warehouse_uuid = uuid.UUID(seller_id), uuid.UUID(warehouse_id)
    supply_id = await _make_wb_supply(
        tenant_id=tenant_id,
        seller_id=seller_uuid,
        warehouse_id=warehouse_uuid,
        status=FBS_SUPPLY_STATUS_ASSEMBLING,
        marker="BACKOFF2",
    )
    order_id, _value = await _seed_coded_wb_order(
        tenant_id=tenant_id,
        seller_id=seller_uuid,
        warehouse_id=warehouse_uuid,
        supply_id=supply_id,
        wb_order_id=984101,
    )
    monkeypatch.setattr(autopoll, "_MARKETPLACE_BACKOFF", MarketplaceBackoff())

    async def fake_fetch_429(
        client: object,
        *,
        api_token: str,
        order_ids: list[int],
        marketplace_api_base: str | None = None,
    ) -> list[MarketplaceOrderMetaRow]:
        raise WildberriesClientError("upstream_error", status_code=429)

    monkeypatch.setattr(
        "app.services.fbs_marking_service.fetch_marketplace_orders_meta_batch",
        fake_fetch_429,
    )

    result = await autopoll.sync_fbs_marking_verdicts_all_sellers()

    assert result.seller_errors == 1
    assert result.backoff_skips == 0  # nothing was skipped before this failure
    assert autopoll._MARKETPLACE_BACKOFF.remaining_seconds("wb") > 0
    assert await _marking_status(order_id) == META_STATUS_PENDING


# --------------------------------------------------------------------------
# Astra review round 2 (docs/reviews/2026-09-19-wms477/review-astra-2.md) —
# finding Н1: the single-order path (sync_order_marking_statuses behind
# POST /operations/fbs-orders/{order_id}/markings/sync — the per-row "Проверить
# ЧЗ" button on Ozon rows and the pre-handover sync — and get_order_metadata)
# does its own single WB round trip inside _sync_order_meta_from_wb without a
# caller-supplied snapshot, so it kept losing the freshness check entirely.
# Наблюдение Н2 (счётчик общего цикла) — по решению ревьюера не меняется.
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stale_single_order_sync_does_not_revert_a_fresher_minute_cycle_verdict(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Н1, first reproduced pairing — accepted → pending."""
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    seller_uuid, warehouse_uuid = uuid.UUID(seller_id), uuid.UUID(warehouse_id)
    supply_id = await _make_wb_supply(
        tenant_id=tenant_id,
        seller_id=seller_uuid,
        warehouse_id=warehouse_uuid,
        status=FBS_SUPPLY_STATUS_ASSEMBLING,
        marker="H1A",
    )
    order_id, value = await _seed_coded_wb_order(
        tenant_id=tenant_id,
        seller_id=seller_uuid,
        warehouse_id=warehouse_uuid,
        supply_id=supply_id,
        wb_order_id=986001,
    )
    target = autopoll.SellerPollTarget(tenant_id=tenant_id, seller_id=seller_uuid)
    fetching, proceed = asyncio.Event(), asyncio.Event()
    calls = 0

    async def fetch_mock(
        client: object,
        *,
        api_token: str,
        order_ids: list[int],
        marketplace_api_base: str | None = None,
    ) -> list[MarketplaceOrderMetaRow]:
        nonlocal calls
        calls += 1
        if calls == 1:
            # The single-order sync's own (only) WB call: hold it.
            fetching.set()
            await proceed.wait()
            return [
                MarketplaceOrderMetaRow(
                    order_id=986001,
                    meta_details=(
                        MarketplaceMetaDetail(key="sgtin", value=value, decision="pending"),
                    ),
                )
            ]
        # The minute cycle's call: resolves immediately with the real verdict.
        return [
            MarketplaceOrderMetaRow(
                order_id=986001,
                meta_details=(
                    MarketplaceMetaDetail(
                        key="sgtin", value=value, decision="sgtinIntroduced"
                    ),
                ),
            )
        ]

    monkeypatch.setattr(
        "app.services.fbs_marking_service.fetch_marketplace_orders_meta_batch", fetch_mock
    )

    async with SessionLocal() as single_session:
        single_task = asyncio.create_task(
            marking_svc.sync_order_marking_statuses(
                single_session,
                tenant_id,
                order_id,
                async_client,
                actor_user_id=None,
            )
        )
        try:
            await asyncio.wait_for(fetching.wait(), 5)

            async with SessionLocal() as minute_session:
                minute_result = await autopoll.sync_marking_verdicts_for_seller(
                    minute_session, target, async_client
                )
                await minute_session.commit()
            assert minute_result.orders_updated == 1
            assert await _marking_status(order_id) == META_STATUS_ACCEPTED

            proceed.set()
            await asyncio.wait_for(single_task, 5)
            await single_session.commit()
        finally:
            proceed.set()
            if not single_task.done():
                single_task.cancel()
            await asyncio.gather(single_task, return_exceptions=True)

    assert await _marking_status(order_id) == META_STATUS_ACCEPTED  # not reverted to pending


@pytest.mark.asyncio
async def test_stale_single_order_sync_does_not_revert_a_fresher_button_verdict(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Н1, second reproduced pairing — accepted → pending, single order vs button."""
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    seller_uuid, warehouse_uuid = uuid.UUID(seller_id), uuid.UUID(warehouse_id)
    supply_id = await _make_wb_supply(
        tenant_id=tenant_id,
        seller_id=seller_uuid,
        warehouse_id=warehouse_uuid,
        status=FBS_SUPPLY_STATUS_ASSEMBLING,
        marker="H1B",
    )
    order_id, value = await _seed_coded_wb_order(
        tenant_id=tenant_id,
        seller_id=seller_uuid,
        warehouse_id=warehouse_uuid,
        supply_id=supply_id,
        wb_order_id=986101,
    )
    fetching, proceed = asyncio.Event(), asyncio.Event()
    calls = 0

    async def fetch_mock(
        client: object,
        *,
        api_token: str,
        order_ids: list[int],
        marketplace_api_base: str | None = None,
    ) -> list[MarketplaceOrderMetaRow]:
        nonlocal calls
        calls += 1
        if calls == 1:
            fetching.set()
            await proceed.wait()
            return [
                MarketplaceOrderMetaRow(
                    order_id=986101,
                    meta_details=(
                        MarketplaceMetaDetail(key="sgtin", value=value, decision="pending"),
                    ),
                )
            ]
        return [
            MarketplaceOrderMetaRow(
                order_id=986101,
                meta_details=(
                    MarketplaceMetaDetail(
                        key="sgtin", value=value, decision="sgtinIntroduced"
                    ),
                ),
            )
        ]

    monkeypatch.setattr(
        "app.services.fbs_marking_service.fetch_marketplace_orders_meta_batch", fetch_mock
    )

    async with SessionLocal() as single_session:
        single_task = asyncio.create_task(
            marking_svc.sync_order_marking_statuses(
                single_session,
                tenant_id,
                order_id,
                async_client,
                actor_user_id=None,
            )
        )
        try:
            await asyncio.wait_for(fetching.wait(), 5)

            async with SessionLocal() as button_session:
                button_result = await marking_svc.sync_marking_verdicts_for_supply(
                    button_session,
                    tenant_id,
                    supply_id,
                    async_client,
                    actor_user_id=None,
                )
                await button_session.commit()
            assert button_result.orders_updated == 1
            assert await _marking_status(order_id) == META_STATUS_ACCEPTED

            proceed.set()
            await asyncio.wait_for(single_task, 5)
            await single_session.commit()
        finally:
            proceed.set()
            if not single_task.done():
                single_task.cancel()
            await asyncio.gather(single_task, return_exceptions=True)

    assert await _marking_status(order_id) == META_STATUS_ACCEPTED


@pytest.mark.asyncio
async def test_stale_get_order_metadata_sync_does_not_revert_a_fresher_minute_cycle_verdict(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Н1, third reproduced pairing — get_order_metadata(sync_wb=True) vs minute cycle."""
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    seller_uuid, warehouse_uuid = uuid.UUID(seller_id), uuid.UUID(warehouse_id)
    supply_id = await _make_wb_supply(
        tenant_id=tenant_id,
        seller_id=seller_uuid,
        warehouse_id=warehouse_uuid,
        status=FBS_SUPPLY_STATUS_ASSEMBLING,
        marker="H1C",
    )
    order_id, value = await _seed_coded_wb_order(
        tenant_id=tenant_id,
        seller_id=seller_uuid,
        warehouse_id=warehouse_uuid,
        supply_id=supply_id,
        wb_order_id=986201,
    )
    target = autopoll.SellerPollTarget(tenant_id=tenant_id, seller_id=seller_uuid)
    fetching, proceed = asyncio.Event(), asyncio.Event()
    calls = 0

    async def fetch_mock(
        client: object,
        *,
        api_token: str,
        order_ids: list[int],
        marketplace_api_base: str | None = None,
    ) -> list[MarketplaceOrderMetaRow]:
        nonlocal calls
        calls += 1
        if calls == 1:
            fetching.set()
            await proceed.wait()
            return [
                MarketplaceOrderMetaRow(
                    order_id=986201,
                    meta_details=(
                        MarketplaceMetaDetail(key="sgtin", value=value, decision="pending"),
                    ),
                )
            ]
        return [
            MarketplaceOrderMetaRow(
                order_id=986201,
                meta_details=(
                    MarketplaceMetaDetail(
                        key="sgtin", value=value, decision="sgtinIntroduced"
                    ),
                ),
            )
        ]

    monkeypatch.setattr(
        "app.services.fbs_marking_service.fetch_marketplace_orders_meta_batch", fetch_mock
    )

    async with SessionLocal() as metadata_session:
        metadata_task = asyncio.create_task(
            marking_svc.get_order_metadata(
                metadata_session,
                tenant_id,
                order_id,
                async_client,
                sync_wb=True,
                actor_user_id=None,
            )
        )
        try:
            await asyncio.wait_for(fetching.wait(), 5)

            async with SessionLocal() as minute_session:
                minute_result = await autopoll.sync_marking_verdicts_for_seller(
                    minute_session, target, async_client
                )
                await minute_session.commit()
            assert minute_result.orders_updated == 1
            assert await _marking_status(order_id) == META_STATUS_ACCEPTED

            proceed.set()
            await asyncio.wait_for(metadata_task, 5)
            await metadata_session.commit()
        finally:
            proceed.set()
            if not metadata_task.done():
                metadata_task.cancel()
            await asyncio.gather(metadata_task, return_exceptions=True)

    assert await _marking_status(order_id) == META_STATUS_ACCEPTED


@pytest.mark.asyncio
async def test_stale_single_order_sync_does_not_revert_a_fresher_rejection(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Н1, fourth reproduced pairing — rejected → accepted (the dangerous
    direction: a stale positive answer must not undo a fresh WB rejection)."""
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    seller_uuid, warehouse_uuid = uuid.UUID(seller_id), uuid.UUID(warehouse_id)
    supply_id = await _make_wb_supply(
        tenant_id=tenant_id,
        seller_id=seller_uuid,
        warehouse_id=warehouse_uuid,
        status=FBS_SUPPLY_STATUS_ASSEMBLING,
        marker="H1D",
    )
    order_id, value = await _seed_coded_wb_order(
        tenant_id=tenant_id,
        seller_id=seller_uuid,
        warehouse_id=warehouse_uuid,
        supply_id=supply_id,
        wb_order_id=986301,
    )
    fetching, proceed = asyncio.Event(), asyncio.Event()
    calls = 0

    async def fetch_mock(
        client: object,
        *,
        api_token: str,
        order_ids: list[int],
        marketplace_api_base: str | None = None,
    ) -> list[MarketplaceOrderMetaRow]:
        nonlocal calls
        calls += 1
        if calls == 1:
            # The single-order sync's own (slow) WB call: an eventual positive
            # answer that must lose to the button's fresher rejection below.
            fetching.set()
            await proceed.wait()
            return [
                MarketplaceOrderMetaRow(
                    order_id=986301,
                    meta_details=(
                        MarketplaceMetaDetail(
                            key="sgtin", value=value, decision="sgtinIntroduced"
                        ),
                    ),
                )
            ]
        # The button's call: WB rejects the code outright.
        return [
            MarketplaceOrderMetaRow(
                order_id=986301,
                meta_details=(
                    MarketplaceMetaDetail(key="sgtin", value=value, decision="sgtinNotFound"),
                ),
            )
        ]

    monkeypatch.setattr(
        "app.services.fbs_marking_service.fetch_marketplace_orders_meta_batch", fetch_mock
    )

    async with SessionLocal() as single_session:
        single_task = asyncio.create_task(
            marking_svc.sync_order_marking_statuses(
                single_session,
                tenant_id,
                order_id,
                async_client,
                actor_user_id=None,
            )
        )
        try:
            await asyncio.wait_for(fetching.wait(), 5)

            async with SessionLocal() as button_session:
                button_result = await marking_svc.sync_marking_verdicts_for_supply(
                    button_session,
                    tenant_id,
                    supply_id,
                    async_client,
                    actor_user_id=None,
                )
                await button_session.commit()
            assert button_result.orders_updated == 1
            assert await _marking_status(order_id) == META_STATUS_REJECTED

            proceed.set()
            await asyncio.wait_for(single_task, 5)
            await single_session.commit()
        finally:
            proceed.set()
            if not single_task.done():
                single_task.cancel()
            await asyncio.gather(single_task, return_exceptions=True)

    assert await _marking_status(order_id) == META_STATUS_REJECTED  # not reverted to accepted


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("old_decision", "new_decision", "expected_status"),
    [
        ("pending", "sgtinIntroduced", META_STATUS_ACCEPTED),
        ("sgtinIntroduced", "sgtinNotFound", META_STATUS_REJECTED),
    ],
)
async def test_http_single_order_sync_vs_http_button_stale_answer(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    old_decision: str,
    new_decision: str,
    expected_status: str,
) -> None:
    """Н1 reproduced through the real HTTP routes, matching the reviewer's own
    confirmation: POST .../fbs-orders/{id}/markings/sync (single order) racing
    POST .../fbs-supplies/{id}/markings/sync (button)."""
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    seller_uuid, warehouse_uuid = uuid.UUID(seller_id), uuid.UUID(warehouse_id)
    supply_id = await _make_wb_supply(
        tenant_id=tenant_id,
        seller_id=seller_uuid,
        warehouse_id=warehouse_uuid,
        status=FBS_SUPPLY_STATUS_ASSEMBLING,
        marker="H1HTTP",
    )
    order_id, value = await _seed_coded_wb_order(
        tenant_id=tenant_id,
        seller_id=seller_uuid,
        warehouse_id=warehouse_uuid,
        supply_id=supply_id,
        wb_order_id=986401,
    )
    fetching, proceed = asyncio.Event(), asyncio.Event()
    calls = 0

    async def fetch_mock(
        client: object,
        *,
        api_token: str,
        order_ids: list[int],
        marketplace_api_base: str | None = None,
    ) -> list[MarketplaceOrderMetaRow]:
        nonlocal calls
        calls += 1
        if calls == 1:
            fetching.set()
            await proceed.wait()
            return [
                MarketplaceOrderMetaRow(
                    order_id=986401,
                    meta_details=(
                        MarketplaceMetaDetail(key="sgtin", value=value, decision=old_decision),
                    ),
                )
            ]
        return [
            MarketplaceOrderMetaRow(
                order_id=986401,
                meta_details=(
                    MarketplaceMetaDetail(
                        key="sgtin", value=value, decision=new_decision
                    ),
                ),
            )
        ]

    monkeypatch.setattr(
        "app.services.fbs_marking_service.fetch_marketplace_orders_meta_batch", fetch_mock
    )

    single_task = asyncio.create_task(
        async_client.post(
            f"/operations/fbs-orders/{order_id}/markings/sync",
            headers=headers,
        )
    )
    try:
        await asyncio.wait_for(fetching.wait(), 5)

        button_resp = await async_client.post(
            f"/operations/fbs-supplies/{supply_id}/markings/sync",
            headers=headers,
        )
        assert button_resp.status_code == 200, button_resp.text
        assert await _marking_status(order_id) == expected_status

        proceed.set()
        single_resp = await asyncio.wait_for(single_task, 5)
        assert single_resp.status_code == 200, single_resp.text
    finally:
        proceed.set()
        if not single_task.done():
            single_task.cancel()
        await asyncio.gather(single_task, return_exceptions=True)

    assert await _marking_status(order_id) == expected_status  # the newer verdict survives


# --------------------------------------------------------------------------
# R6а — наложение циклов: пробный advisory-замок (только PostgreSQL)
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_postgresql_marking_verdicts_cycle_lock_skips_concurrent_cycle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from sqlalchemy.ext.asyncio import create_async_engine

    from app.db.session import engine as app_engine

    if app_engine.dialect.name != "postgresql":
        pytest.skip("requires PostgreSQL advisory locks (set WMS_TEST_DATABASE_URL)")

    lock_key = autopoll._MARKING_VERDICTS_CYCLE_LOCK_KEY
    probe_engine = create_async_engine(app_engine.url, pool_size=1, max_overflow=0)
    try:
        async with probe_engine.connect() as probe_conn:
            from sqlalchemy import text

            async with probe_conn.begin():
                held = bool(
                    await probe_conn.scalar(
                        text("select pg_try_advisory_lock(:k)"), {"k": lock_key}
                    )
                )
            assert held is True

            async def _must_not_run(*_a: object, **_k: object) -> list[object]:
                raise AssertionError("cycle must skip before listing sellers")

            monkeypatch.setattr(
                autopoll, "list_sellers_with_marketplace_token", _must_not_run
            )

            result = await autopoll.sync_fbs_marking_verdicts_all_sellers()
            assert result.skipped is True
            assert result.sellers_checked == 0
            assert result.seller_errors == 0

            async with probe_conn.begin():
                await probe_conn.execute(text("select pg_advisory_unlock(:k)"), {"k": lock_key})
    finally:
        await probe_engine.dispose()

    monkeypatch.undo()
    result_after_release = await autopoll.sync_fbs_marking_verdicts_all_sellers()
    assert result_after_release.skipped is False


# --------------------------------------------------------------------------
# R5/R7 — расписание и настройка
# --------------------------------------------------------------------------


def test_celery_schedule_has_marking_verdicts_entry_separate_from_statuses_autopoll() -> None:
    from app.celery_app import celery_app
    from app.core.settings import settings

    schedule = celery_app.conf.beat_schedule
    entry = schedule["fbs-marking-verdicts-autopoll"]
    assert entry["task"] == "wms.fbs_marking_verdicts_autopoll"
    assert float(entry["schedule"]) == float(settings.fbs_marking_verdicts_sync_interval_sec)
    assert settings.fbs_marking_verdicts_sync_interval_sec == 60

    # R7 — общий цикл остаётся на своём интервале и записи, никем не тронут.
    statuses_entry = schedule["fbs-order-statuses-autopoll"]
    assert statuses_entry["task"] == "wms.fbs_order_statuses_autopoll"
    assert float(statuses_entry["schedule"]) == float(settings.fbs_statuses_sync_interval_sec)


@pytest.mark.asyncio
@pytest.mark.postgresql_concurrency
async def test_postgresql_real_cycles_skip_overlap_and_recover_after_cancellation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A cancelled task releases its dedicated lock before the next minute tick."""
    from app.db.session import engine as app_engine

    if app_engine.dialect.name != "postgresql":
        pytest.skip("requires PostgreSQL advisory locks (set WMS_TEST_DATABASE_URL)")
    entered = asyncio.Event()
    calls = 0

    async def controlled_targets(_session: object) -> list[autopoll.SellerPollTarget]:
        nonlocal calls
        calls += 1
        if calls == 1:
            entered.set()
            await asyncio.Event().wait()
        return []

    monkeypatch.setattr(autopoll, "list_sellers_with_marketplace_token", controlled_targets)
    first = asyncio.create_task(autopoll.sync_fbs_marking_verdicts_all_sellers())
    try:
        await asyncio.wait_for(entered.wait(), 5)
        second = await asyncio.wait_for(autopoll.sync_fbs_marking_verdicts_all_sellers(), 5)
        assert second.skipped
        assert calls == 1
    finally:
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(first, 5)
    recovered = await asyncio.wait_for(autopoll.sync_fbs_marking_verdicts_all_sellers(), 5)
    assert not recovered.skipped
    assert calls == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["manual", "background", "single"])
async def test_omitted_wb_order_preserves_saved_verdict_and_next_cycle(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    path: str,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    seller_uuid, warehouse_uuid = uuid.UUID(seller_id), uuid.UUID(warehouse_id)
    supply_id = await _make_wb_supply(
        tenant_id=tenant_id, seller_id=seller_uuid, warehouse_id=warehouse_uuid,
        status=FBS_SUPPLY_STATUS_ASSEMBLING, marker="omitted",
    )
    seeded: dict[int, tuple[uuid.UUID, str]] = {}
    for wb_id, status in (
        (977901, META_STATUS_PENDING), (977902, META_STATUS_SENDING),
        (977903, META_STATUS_ACCEPTED), (977904, META_STATUS_PENDING),
    ):
        seeded[wb_id] = await _seed_coded_wb_order(
            tenant_id=tenant_id, seller_id=seller_uuid, warehouse_id=warehouse_uuid,
            supply_id=supply_id, wb_order_id=wb_id, meta_status=status,
        )
    omitted_ids = [seeded[wb_id][0] for wb_id in (977901, 977902, 977903)]
    async with SessionLocal() as session:
        for order_id in omitted_ids:
            order = await session.get(FbsOrder, order_id)
            assert order is not None
            order.metadata_last_checked_at = datetime(2026, 9, 1, tzinfo=UTC)
            order.metadata_delivery_allowed = True
            order.meta_details_json = [{"key": "sgtin", "decision": "pending"}]
            marking = await session.scalar(
                select(FbsOrderMarking).where(FbsOrderMarking.order_id == order_id)
            )
            assert marking is not None
            marking.reason = "previous WB verdict"
            marking.meta_details_json = {"decision": "pending"}
        await session.commit()

    async def saved_state() -> list[object]:
        async with SessionLocal() as session:
            return list((await session.execute(
                select(
                    FbsOrder.id, FbsOrder.metadata_last_checked_at,
                    FbsOrder.metadata_delivery_allowed, FbsOrder.meta_details_json,
                    FbsOrderMarking.meta_status, FbsOrderMarking.check_status,
                    FbsOrderMarking.reason, FbsOrderMarking.meta_details_json,
                ).join(FbsOrderMarking).where(FbsOrder.id.in_(omitted_ids))
                .order_by(FbsOrder.id)
            )).all())

    before = await saved_state()
    requests: list[set[int]] = []
    complete = False

    async def fake_fetch_batch(
        client: object, *, api_token: str, order_ids: list[int],
        marketplace_api_base: str | None = None,
    ) -> list[MarketplaceOrderMetaRow]:
        requests.append(set(order_ids))
        return [
            MarketplaceOrderMetaRow(
                order_id=wb_id,
                meta_details=(MarketplaceMetaDetail(
                    key="sgtin", value=seeded[wb_id][1], decision="sgtinIntroduced",
                ),),
            )
            for wb_id in order_ids if complete or wb_id == 977904
        ]

    monkeypatch.setattr(marking_svc, "fetch_marketplace_orders_meta_batch", fake_fetch_batch)
    target = autopoll.SellerPollTarget(tenant_id=tenant_id, seller_id=seller_uuid)
    if path == "manual":
        response = await async_client.post(
            f"/operations/fbs-supplies/{supply_id}/markings/sync", headers=headers,
        )
        assert response.status_code == 200, response.text
        assert requests == [{977901, 977902, 977903, 977904}]
    else:
        async with SessionLocal() as session:
            if path == "background":
                result = await autopoll.sync_marking_verdicts_for_seller(
                    session, target, async_client,
                )
                assert result.orders_checked == 3
                assert result.orders_updated == 1
                assert requests == [{977901, 977902, 977904}]
            else:
                for order_id, _value in seeded.values():
                    await marking_svc.sync_order_marking_statuses(
                        session, tenant_id, order_id, async_client, actor_user_id=None,
                    )
                assert requests == [{977901}, {977902}, {977903}, {977904}]
            await session.commit()

    assert await saved_state() == before
    assert await _marking_status(seeded[977904][0]) == META_STATUS_ACCEPTED

    # A fresh session and the real minute-cycle query must still select both
    # omitted pending/sending orders after the previous transaction committed.
    complete = True
    requests.clear()
    async with SessionLocal() as session:
        result = await autopoll.sync_marking_verdicts_for_seller(session, target, async_client)
        await session.commit()
    assert requests == [{977901, 977902}]
    assert result.orders_checked == result.orders_updated == 2
    for wb_id in seeded:
        assert await _marking_status(seeded[wb_id][0]) == META_STATUS_ACCEPTED
