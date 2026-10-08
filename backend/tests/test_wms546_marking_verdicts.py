"""WMS-546 — минутная сверка вердиктов ЧЗ теперь берёт `draft` и `unknown`.

Реализация — расширение фильтра `sync_marking_verdicts_for_seller`
(`fbs_autopoll_service.py`, WMS-546 R1): активная группа поставки
`draft`/`assembling`/`packed` (было `assembling`/`packed`) x открытый статус
кода `pending`/`sending`/`unknown` (было `pending`/`sending`). Применение
ответа WB (`_sync_order_meta_from_wb`), защиты от гонок и общий десятиминутный
цикл не менялись (R2-R7) — эти тесты проверяют, что расширенная выборка не
сломала уже принятые в WMS-477 гарантии, а не переизобретают их.

Проверки здесь покрывают C1-C6, C9, C10 из docs/requirements/WMS-546.md.
C7 (наложение циклов, advisory lock) и C8 (более свежий вердикт побеждает
устаревший ответ) для нового `draft`/`unknown` случая — в конце файла,
на PostgreSQL (см. WMS_TEST_DATABASE_URL); механизм там общий с WMS-477
и на SQLite не проверяется отдельно, тесты сами себя пропускают, если
дралект не postgresql.
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
    CHECK_STATUS_ERROR,
    CHECK_STATUS_NEW,
    CHECK_STATUS_OK,
    FBS_ORDER_STATUS_PACKED,
    META_STATUS_ACCEPTED,
    META_STATUS_ALLOWED_WITHOUT_CHECK,
    META_STATUS_ASSIGNED,
    META_STATUS_MISSING,
    META_STATUS_PENDING,
    META_STATUS_REJECTED,
    META_STATUS_REPLACEMENT_REQUIRED,
    META_STATUS_SENDING,
    META_STATUS_UNKNOWN,
    FbsOrder,
    FbsOrderMarking,
)
from app.models.fbs_supply import (
    FBS_SUPPLY_STATUS_ASSEMBLING,
    FBS_SUPPLY_STATUS_DONE,
    FBS_SUPPLY_STATUS_DRAFT,
    FBS_SUPPLY_STATUS_IN_DELIVERY,
    FBS_SUPPLY_STATUS_PACKED,
    FbsSupply,
)
from app.models.fbs_wb_operation import (
    WB_OPERATION_STATE_CONFIRMED,
    WB_OPERATION_STATE_PENDING_CONFIRMATION,
    FbsWbOperation,
)
from app.services import fbs_autopoll_service as autopoll
from app.services import fbs_marking_service as marking_svc
from app.services.wildberries_client import WildberriesClientError
from app.services.wildberries_fbs_client import MarketplaceMetaDetail, MarketplaceOrderMetaRow
from tests.test_fbs_marking import _register_ff_admin, _setup_seller_with_token
from tests.test_wms477_marking_verdicts_sync import (
    _fail_if_called,
    _make_wb_supply,
    _marking_status,
)


def _block_writes(monkeypatch: pytest.MonkeyPatch) -> None:
    """R2 — фоновый путь не должен даже пытаться писать в WB.

    Ни один из background-сценариев в этом файле не должен вызвать эти три
    функции: если это случится, тест сразу падает, а не молча проходит.
    """
    monkeypatch.setattr(
        "app.services.fbs_marking_service.put_marketplace_order_meta", _fail_if_called
    )
    monkeypatch.setattr(
        "app.services.fbs_marking_service.attach_order_meta_to_wb_and_sync", _fail_if_called
    )
    monkeypatch.setattr(
        "app.services.fbs_marking_service.reconcile_pending_kiz_operation", _fail_if_called
    )


async def _raw_order(
    *,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    supply_id: uuid.UUID,
    wb_order_id: int,
    marketplace: str = "wb",
    meta_status: str | None = META_STATUS_PENDING,
    now: datetime | None = None,
) -> uuid.UUID:
    """A bare FbsOrder (+ one marking, unless meta_status is None) — no WB
    workspace rendering needed for these tests, so this stays direct SQLAlchemy
    inserts like the WMS-477 filter/isolation tests, not the full
    `upsert_order_from_wb_row` helper.
    """
    now = now or datetime.now(tz=UTC)
    order_id = uuid.uuid4()
    async with SessionLocal() as session:
        session.add(
            FbsOrder(
                id=order_id,
                tenant_id=tenant_id,
                seller_id=seller_id,
                warehouse_id=warehouse_id,
                marketplace=marketplace,
                wb_order_id=wb_order_id,
                wb_rid=f"wms546-rid-{wb_order_id}",
                status=FBS_ORDER_STATUS_PACKED,
                supply_id=supply_id,
                created_at_wb=now,
                deadline_at=now + timedelta(days=1),
                mapping_status="mapped",
                reserve_status="reserved",
            )
        )
        await session.flush()
        if meta_status is not None:
            check_status = (
                CHECK_STATUS_NEW if meta_status == META_STATUS_PENDING else CHECK_STATUS_OK
            )
            session.add(
                FbsOrderMarking(
                    order_id=order_id,
                    tenant_id=tenant_id,
                    kind="sgtin",
                    value=f"01WMS546{wb_order_id}",
                    check_status=check_status,
                    meta_status=meta_status,
                )
            )
        await session.commit()
    return order_id


async def _make_supply(
    *, tenant_id: uuid.UUID, seller_id: uuid.UUID, warehouse_id: uuid.UUID, status: str, marker: str
) -> uuid.UUID:
    return await _make_wb_supply(
        tenant_id=tenant_id,
        seller_id=seller_id,
        warehouse_id=warehouse_id,
        status=status,
        marker=marker,
    )


def _accepting_fetch(requested: list[int]):
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
                        key="sgtin", value=f"01WMS546{oid}", decision="sgtinIntroduced"
                    ),
                ),
            )
            for oid in order_ids
        ]

    return fake_fetch_batch


# --------------------------------------------------------------------------
# C1 — полная матрица отбора: {9 статусов кода} x {5 статусов поставки}
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_c1_selection_matrix_active_supply_open_code(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _block_writes(monkeypatch)
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    seller_uuid, warehouse_uuid = uuid.UUID(seller_id), uuid.UUID(warehouse_id)

    meta_statuses = [
        META_STATUS_PENDING,
        META_STATUS_SENDING,
        META_STATUS_UNKNOWN,
        META_STATUS_ASSIGNED,
        META_STATUS_MISSING,
        META_STATUS_ACCEPTED,
        META_STATUS_ALLOWED_WITHOUT_CHECK,
        META_STATUS_REJECTED,
        META_STATUS_REPLACEMENT_REQUIRED,
    ]
    supply_statuses = [
        FBS_SUPPLY_STATUS_DRAFT,
        FBS_SUPPLY_STATUS_ASSEMBLING,
        FBS_SUPPLY_STATUS_PACKED,
        FBS_SUPPLY_STATUS_IN_DELIVERY,
        FBS_SUPPLY_STATUS_DONE,
    ]
    open_codes = {META_STATUS_PENDING, META_STATUS_SENDING, META_STATUS_UNKNOWN}
    active_supplies = {
        FBS_SUPPLY_STATUS_DRAFT, FBS_SUPPLY_STATUS_ASSEMBLING, FBS_SUPPLY_STATUS_PACKED,
    }

    supply_ids: dict[str, uuid.UUID] = {}
    for supply_status in supply_statuses:
        supply_ids[supply_status] = await _make_supply(
            tenant_id=tenant_id,
            seller_id=seller_uuid,
            warehouse_id=warehouse_uuid,
            status=supply_status,
            marker=f"C1-{supply_status}",
        )

    order_ids: dict[tuple[str, str], uuid.UUID] = {}
    wb_order_id = 991000
    for meta_status in meta_statuses:
        for supply_status in supply_statuses:
            wb_order_id += 1
            order_ids[(meta_status, supply_status)] = await _raw_order(
                tenant_id=tenant_id,
                seller_id=seller_uuid,
                warehouse_id=warehouse_uuid,
                supply_id=supply_ids[supply_status],
                wb_order_id=wb_order_id,
                meta_status=meta_status,
            )
    wb_order_id += 1
    ozon_order = await _raw_order(
        tenant_id=tenant_id,
        seller_id=seller_uuid,
        warehouse_id=warehouse_uuid,
        supply_id=supply_ids[FBS_SUPPLY_STATUS_ASSEMBLING],
        wb_order_id=wb_order_id,
        marketplace="ozon",
        meta_status=META_STATUS_PENDING,
    )
    wb_order_id += 1
    no_code_order = await _raw_order(
        tenant_id=tenant_id,
        seller_id=seller_uuid,
        warehouse_id=warehouse_uuid,
        supply_id=supply_ids[FBS_SUPPLY_STATUS_ASSEMBLING],
        wb_order_id=wb_order_id,
        meta_status=None,
    )

    before = {key: await _marking_status(oid) for key, oid in order_ids.items()}

    requested: list[int] = []
    monkeypatch.setattr(
        "app.services.fbs_marking_service.fetch_marketplace_orders_meta_batch",
        _accepting_fetch(requested),
    )

    async with SessionLocal() as session:
        result = await autopoll.sync_marking_verdicts_for_seller(
            session,
            autopoll.SellerPollTarget(tenant_id=tenant_id, seller_id=seller_uuid),
            async_client,
        )
        await session.commit()

    expected_keys = {
        (meta_status, supply_status)
        for meta_status in meta_statuses
        for supply_status in supply_statuses
        if meta_status in open_codes and supply_status in active_supplies
    }
    assert len(expected_keys) == 9  # 3 open codes x 3 active supply statuses
    # order_ids are unique per key — map wb_order_id back for the requested-set check.
    id_to_key = {v: k for k, v in order_ids.items()}
    async with SessionLocal() as session:
        wb_ids_by_order_id = dict(
            (
                await session.execute(
                    select(FbsOrder.id, FbsOrder.wb_order_id).where(
                        FbsOrder.id.in_(order_ids.values())
                    )
                )
            ).all()
        )
    requested_keys = {
        id_to_key[oid] for oid, wb_id in wb_ids_by_order_id.items() if wb_id in requested
    }
    assert requested_keys == expected_keys
    assert result.orders_checked == 9
    assert result.orders_updated == 9

    for key, order_id in order_ids.items():
        after = await _marking_status(order_id)
        if key in expected_keys:
            assert after == META_STATUS_ACCEPTED, key
        else:
            assert after == before[key], f"{key} must stay untouched"

    assert await _marking_status(ozon_order) == META_STATUS_PENDING
    assert await _marking_status(no_code_order) is None


# --------------------------------------------------------------------------
# C2 — production-подобный черновик AVpack: 38 КИЗ, 20 unknown/pending_confirmation
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_c2_avpack_like_draft_confirms_pending_confirmation_operations(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _block_writes(monkeypatch)
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    seller_uuid, warehouse_uuid = uuid.UUID(seller_id), uuid.UUID(warehouse_id)
    supply_id = await _make_supply(
        tenant_id=tenant_id,
        seller_id=seller_uuid,
        warehouse_id=warehouse_uuid,
        status=FBS_SUPPLY_STATUS_DRAFT,
        marker="AVPACK",
    )

    unknown_ids: list[uuid.UUID] = []
    unknown_wb_ids: list[int] = []
    for i in range(20):
        wb_order_id = 992000 + i
        order_id = await _raw_order(
            tenant_id=tenant_id,
            seller_id=seller_uuid,
            warehouse_id=warehouse_uuid,
            supply_id=supply_id,
            wb_order_id=wb_order_id,
            meta_status=META_STATUS_UNKNOWN,
        )
        async with SessionLocal() as session:
            order = await session.get(FbsOrder, order_id)
            marking = await session.scalar(
                select(FbsOrderMarking).where(FbsOrderMarking.order_id == order_id)
            )
            assert order is not None and marking is not None
            await marking_svc.record_pending_kiz_operation(
                session,
                order,
                marking,
                error_code="wb_readback_empty",
                actor_user_id=None,
                idempotency_key=f"wms546-c2-{wb_order_id}",
            )
            await session.commit()
        unknown_ids.append(order_id)
        unknown_wb_ids.append(wb_order_id)

    settled_ids: list[uuid.UUID] = []
    for i in range(18):
        wb_order_id = 993000 + i
        order_id = await _raw_order(
            tenant_id=tenant_id,
            seller_id=seller_uuid,
            warehouse_id=warehouse_uuid,
            supply_id=supply_id,
            wb_order_id=wb_order_id,
            meta_status=META_STATUS_ACCEPTED,
        )
        settled_ids.append(order_id)

    requested: list[int] = []
    monkeypatch.setattr(
        "app.services.fbs_marking_service.fetch_marketplace_orders_meta_batch",
        _accepting_fetch(requested),
    )

    async with SessionLocal() as session:
        result = await autopoll.sync_marking_verdicts_for_seller(
            session,
            autopoll.SellerPollTarget(tenant_id=tenant_id, seller_id=seller_uuid),
            async_client,
        )
        await session.commit()

    assert set(requested) == set(unknown_wb_ids)  # the 18 already-settled codes were never asked
    assert result.orders_checked == 20
    assert result.orders_updated == 20

    for order_id in unknown_ids:
        assert await _marking_status(order_id) == META_STATUS_ACCEPTED
        async with SessionLocal() as session:
            marking = await session.scalar(
                select(FbsOrderMarking).where(FbsOrderMarking.order_id == order_id)
            )
            assert marking is not None and marking.check_status == CHECK_STATUS_OK
            operation = await session.scalar(
                select(FbsWbOperation).where(FbsWbOperation.local_entity_id == marking.id)
            )
            assert operation is not None
            assert operation.state == WB_OPERATION_STATE_CONFIRMED
            assert operation.confirmed_at is not None

    for order_id in settled_ids:
        assert await _marking_status(order_id) == META_STATUS_ACCEPTED

    async with SessionLocal() as session:
        supply = await session.get(FbsSupply, supply_id)
        assert supply is not None
        assert supply.status == FBS_SUPPLY_STATUS_DRAFT  # no handover triggered


# --------------------------------------------------------------------------
# C3 — пустой unknown повторяется каждый цикл, затем зеленеет
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_c3_empty_unknown_readback_repeats_then_resolves(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _block_writes(monkeypatch)
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    seller_uuid, warehouse_uuid = uuid.UUID(seller_id), uuid.UUID(warehouse_id)
    supply_id = await _make_supply(
        tenant_id=tenant_id,
        seller_id=seller_uuid,
        warehouse_id=warehouse_uuid,
        status=FBS_SUPPLY_STATUS_DRAFT,
        marker="C3",
    )
    wb_order_id = 994001
    order_id = await _raw_order(
        tenant_id=tenant_id,
        seller_id=seller_uuid,
        warehouse_id=warehouse_uuid,
        supply_id=supply_id,
        wb_order_id=wb_order_id,
        meta_status=META_STATUS_UNKNOWN,
    )
    async with SessionLocal() as session:
        order = await session.get(FbsOrder, order_id)
        marking = await session.scalar(
            select(FbsOrderMarking).where(FbsOrderMarking.order_id == order_id)
        )
        assert order is not None and marking is not None
        await marking_svc.record_pending_kiz_operation(
            session,
            order,
            marking,
            error_code="wb_readback_empty",
            actor_user_id=None,
            idempotency_key="wms546-c3",
        )
        await session.commit()
        marking_id = marking.id

    target = autopoll.SellerPollTarget(tenant_id=tenant_id, seller_id=seller_uuid)
    empty_response = [
        MarketplaceOrderMetaRow(
            order_id=wb_order_id,
            meta_details=(MarketplaceMetaDetail(key="sgtin", value=None, decision="optional"),),
        )
    ]

    async def empty_fetch(
        client: object,
        *,
        api_token: str,
        order_ids: list[int],
        marketplace_api_base: str | None = None,
    ) -> list[MarketplaceOrderMetaRow]:
        assert order_ids == [wb_order_id]
        return empty_response

    monkeypatch.setattr(
        "app.services.fbs_marking_service.fetch_marketplace_orders_meta_batch", empty_fetch
    )

    for cycle in range(3):
        async with SessionLocal() as session:
            result = await autopoll.sync_marking_verdicts_for_seller(session, target, async_client)
            await session.commit()
        assert result.orders_checked == 1, f"cycle {cycle}"
        # The WB answer is read and applied (it is a real row, just an empty
        # value) — `orders_updated` counts "a fresh WB answer was applied",
        # not "the status changed"; existing WMS-477/529 behaviour, unchanged
        # here. What matters for R4 is that the code stays `unknown` and gets
        # asked again next cycle, both asserted below.
        assert result.orders_updated == 1, f"cycle {cycle}"
        assert await _marking_status(order_id) == META_STATUS_UNKNOWN
        async with SessionLocal() as session:
            operation = await session.scalar(
                select(FbsWbOperation).where(FbsWbOperation.local_entity_id == marking_id)
            )
            assert operation is not None
            assert operation.state == WB_OPERATION_STATE_PENDING_CONFIRMATION

    async def filled_fetch(
        client: object,
        *,
        api_token: str,
        order_ids: list[int],
        marketplace_api_base: str | None = None,
    ) -> list[MarketplaceOrderMetaRow]:
        return [
            MarketplaceOrderMetaRow(
                order_id=wb_order_id,
                meta_details=(
                    MarketplaceMetaDetail(
                        key="sgtin", value=f"01WMS546{wb_order_id}", decision="filled"
                    ),
                ),
            )
        ]

    monkeypatch.setattr(
        "app.services.fbs_marking_service.fetch_marketplace_orders_meta_batch", filled_fetch
    )
    async with SessionLocal() as session:
        result = await autopoll.sync_marking_verdicts_for_seller(session, target, async_client)
        await session.commit()
    assert result.orders_updated == 1
    assert await _marking_status(order_id) == META_STATUS_ACCEPTED
    async with SessionLocal() as session:
        operation = await session.scalar(
            select(FbsWbOperation).where(FbsWbOperation.local_entity_id == marking_id)
        )
        assert operation is not None
        assert operation.state == WB_OPERATION_STATE_CONFIRMED

    # The existing workspace/presentation layer is untouched by WMS-546 (R6/R7);
    # this just confirms the value it reads now says "accepted" via the same DB read.
    async with SessionLocal() as session:
        final_marking = await session.scalar(
            select(FbsOrderMarking).where(FbsOrderMarking.order_id == order_id)
        )
        assert final_marking is not None
        assert final_marking.meta_status == META_STATUS_ACCEPTED


# --------------------------------------------------------------------------
# P2 (ревью Astra, WMS-546) — `required` decision + пустой sgtin не должен
# давать `missing`, пока WB ещё не подтвердил (эхо) уже отправленный PUT.
#
# `_sync_order_meta_from_wb` проверяла `decision == "required" and not value`
# раньше ветки «SGTIN без значения → unknown», поэтому код с открытой
# `pending_kiz_operation` (WMS-529: КИЗ уже отправлен PUT, ждём эха WB) на
# пустой ответ с decision=required становился `missing` вместо `unknown`.
# `missing` — не открытый статус ни для минутного, ни для 10-минутного
# цикла (R1/R3/R4), поэтому код застревал: WB мог позже прислать точное
# значение, но фон его больше не спрашивал. Исправление точечное: пустой
# ответ с открытой pending_kiz_operation остаётся `unknown`, как и обычный
# пустой `optional`; без открытой операции поведение не менялось.
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_p2_required_empty_with_open_operation_stays_unknown_then_resolves(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _block_writes(monkeypatch)
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    seller_uuid, warehouse_uuid = uuid.UUID(seller_id), uuid.UUID(warehouse_id)
    supply_id = await _make_supply(
        tenant_id=tenant_id, seller_id=seller_uuid, warehouse_id=warehouse_uuid,
        status=FBS_SUPPLY_STATUS_DRAFT, marker="P2",
    )
    wb_order_id = 999201
    order_id = await _raw_order(
        tenant_id=tenant_id, seller_id=seller_uuid, warehouse_id=warehouse_uuid,
        supply_id=supply_id, wb_order_id=wb_order_id, meta_status=META_STATUS_UNKNOWN,
    )
    async with SessionLocal() as session:
        order = await session.get(FbsOrder, order_id)
        marking = await session.scalar(
            select(FbsOrderMarking).where(FbsOrderMarking.order_id == order_id)
        )
        assert order is not None and marking is not None
        # Mirrors the production case: WMS already PUT this exact code and is
        # waiting for WB to echo it back (WMS-529's uncertain-write path).
        await marking_svc.record_pending_kiz_operation(
            session, order, marking, error_code="wb_readback_empty",
            actor_user_id=None, idempotency_key="wms546-p2-open",
        )
        await session.commit()
        marking_id = marking.id

    target = autopoll.SellerPollTarget(tenant_id=tenant_id, seller_id=seller_uuid)

    async def required_empty_fetch(
        client: object,
        *,
        api_token: str,
        order_ids: list[int],
        marketplace_api_base: str | None = None,
    ) -> list[MarketplaceOrderMetaRow]:
        assert order_ids == [wb_order_id]
        return [
            MarketplaceOrderMetaRow(
                order_id=wb_order_id,
                meta_details=(
                    MarketplaceMetaDetail(key="sgtin", value=None, decision="required"),
                ),
            )
        ]

    monkeypatch.setattr(
        "app.services.fbs_marking_service.fetch_marketplace_orders_meta_batch",
        required_empty_fetch,
    )

    async with SessionLocal() as session:
        result = await autopoll.sync_marking_verdicts_for_seller(session, target, async_client)
        await session.commit()
    assert result.orders_checked == 1
    # Not `missing` — that would be the P2 bug (order silently stops being
    # asked by either background cycle, forever, with the PUT already sent).
    assert await _marking_status(order_id) == META_STATUS_UNKNOWN
    async with SessionLocal() as session:
        operation = await session.scalar(
            select(FbsWbOperation).where(FbsWbOperation.local_entity_id == marking_id)
        )
        assert operation is not None
        assert operation.state == WB_OPERATION_STATE_PENDING_CONFIRMATION  # not confirmed/failed

    # Still `unknown` → still an open status → the next cycle asks WB again.
    async with SessionLocal() as session:
        result2 = await autopoll.sync_marking_verdicts_for_seller(session, target, async_client)
        await session.commit()
    assert result2.orders_checked == 1
    assert await _marking_status(order_id) == META_STATUS_UNKNOWN

    async def echoed_fetch(
        client: object,
        *,
        api_token: str,
        order_ids: list[int],
        marketplace_api_base: str | None = None,
    ) -> list[MarketplaceOrderMetaRow]:
        return [
            MarketplaceOrderMetaRow(
                order_id=wb_order_id,
                meta_details=(
                    MarketplaceMetaDetail(
                        key="sgtin", value=f"01WMS546{wb_order_id}", decision="sgtinIntroduced"
                    ),
                ),
            )
        ]

    monkeypatch.setattr(
        "app.services.fbs_marking_service.fetch_marketplace_orders_meta_batch", echoed_fetch
    )
    async with SessionLocal() as session:
        result3 = await autopoll.sync_marking_verdicts_for_seller(session, target, async_client)
        await session.commit()
    assert result3.orders_updated == 1
    assert await _marking_status(order_id) == META_STATUS_ACCEPTED
    async with SessionLocal() as session:
        operation = await session.scalar(
            select(FbsWbOperation).where(FbsWbOperation.local_entity_id == marking_id)
        )
        assert operation is not None
        assert operation.state == WB_OPERATION_STATE_CONFIRMED
        assert operation.confirmed_at is not None


@pytest.mark.asyncio
async def test_p2_required_empty_without_open_operation_still_missing(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression guard for the P2 fix: without an open pending_kiz_operation,
    `required` + empty value must still resolve to `missing` exactly as
    before — WB genuinely has no code for this order, nothing to wait for.
    """
    _block_writes(monkeypatch)
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    seller_uuid, warehouse_uuid = uuid.UUID(seller_id), uuid.UUID(warehouse_id)
    supply_id = await _make_supply(
        tenant_id=tenant_id, seller_id=seller_uuid, warehouse_id=warehouse_uuid,
        status=FBS_SUPPLY_STATUS_DRAFT, marker="P2NOOP",
    )
    wb_order_id = 999301
    order_id = await _raw_order(
        tenant_id=tenant_id, seller_id=seller_uuid, warehouse_id=warehouse_uuid,
        supply_id=supply_id, wb_order_id=wb_order_id, meta_status=META_STATUS_PENDING,
    )
    # No record_pending_kiz_operation call here — no open operation at all.
    target = autopoll.SellerPollTarget(tenant_id=tenant_id, seller_id=seller_uuid)

    async def required_empty_fetch(
        client: object,
        *,
        api_token: str,
        order_ids: list[int],
        marketplace_api_base: str | None = None,
    ) -> list[MarketplaceOrderMetaRow]:
        return [
            MarketplaceOrderMetaRow(
                order_id=wb_order_id,
                meta_details=(
                    MarketplaceMetaDetail(key="sgtin", value=None, decision="required"),
                ),
            )
        ]

    monkeypatch.setattr(
        "app.services.fbs_marking_service.fetch_marketplace_orders_meta_batch",
        required_empty_fetch,
    )
    async with SessionLocal() as session:
        result = await autopoll.sync_marking_verdicts_for_seller(session, target, async_client)
        await session.commit()
    assert result.orders_checked == 1
    assert await _marking_status(order_id) == META_STATUS_MISSING


# --------------------------------------------------------------------------
# C4 — WB пропускает unknown/pending заказ в пакетном ответе
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_c4_wb_omits_unknown_order_from_batch_then_next_cycle_applies(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _block_writes(monkeypatch)
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    seller_uuid, warehouse_uuid = uuid.UUID(seller_id), uuid.UUID(warehouse_id)
    supply_id = await _make_supply(
        tenant_id=tenant_id,
        seller_id=seller_uuid,
        warehouse_id=warehouse_uuid,
        status=FBS_SUPPLY_STATUS_DRAFT,
        marker="C4",
    )
    unknown_id = await _raw_order(
        tenant_id=tenant_id,
        seller_id=seller_uuid,
        warehouse_id=warehouse_uuid,
        supply_id=supply_id,
        wb_order_id=995001,
        meta_status=META_STATUS_UNKNOWN,
    )
    pending_id = await _raw_order(
        tenant_id=tenant_id,
        seller_id=seller_uuid,
        warehouse_id=warehouse_uuid,
        supply_id=supply_id,
        wb_order_id=995002,
        meta_status=META_STATUS_PENDING,
    )
    neighbor_id = await _raw_order(
        tenant_id=tenant_id,
        seller_id=seller_uuid,
        warehouse_id=warehouse_uuid,
        supply_id=supply_id,
        wb_order_id=995003,
        meta_status=META_STATUS_PENDING,
    )

    async def before_state() -> dict[str, object]:
        async with SessionLocal() as session:
            order = await session.get(FbsOrder, unknown_id)
            marking = await session.scalar(
                select(FbsOrderMarking).where(FbsOrderMarking.order_id == unknown_id)
            )
            assert order is not None and marking is not None
            return {
                "meta_status": marking.meta_status,
                "check_status": marking.check_status,
                "reason": marking.reason,
                "meta_details_json": marking.meta_details_json,
                "metadata_last_checked_at": order.metadata_last_checked_at,
                "metadata_delivery_allowed": order.metadata_delivery_allowed,
            }

    snapshot_unknown = await before_state()

    complete = False

    async def fake_fetch(
        client: object,
        *,
        api_token: str,
        order_ids: list[int],
        marketplace_api_base: str | None = None,
    ) -> list[MarketplaceOrderMetaRow]:
        rows = []
        for oid in order_ids:
            if not complete and oid in (995001, 995002):
                continue  # WB silently drops both open codes from the answer
            rows.append(
                MarketplaceOrderMetaRow(
                    order_id=oid,
                    meta_details=(
                        MarketplaceMetaDetail(
                            key="sgtin", value=f"01WMS546{oid}", decision="sgtinIntroduced"
                        ),
                    ),
                )
            )
        return rows

    monkeypatch.setattr(
        "app.services.fbs_marking_service.fetch_marketplace_orders_meta_batch", fake_fetch
    )
    target = autopoll.SellerPollTarget(tenant_id=tenant_id, seller_id=seller_uuid)

    async with SessionLocal() as session:
        result = await autopoll.sync_marking_verdicts_for_seller(session, target, async_client)
        await session.commit()
    assert result.orders_checked == 3
    assert result.orders_updated == 1  # only the answering neighbor
    assert await before_state() == snapshot_unknown  # untouched, byte for byte
    assert await _marking_status(pending_id) == META_STATUS_PENDING
    assert await _marking_status(neighbor_id) == META_STATUS_ACCEPTED

    complete = True
    async with SessionLocal() as session:
        result2 = await autopoll.sync_marking_verdicts_for_seller(session, target, async_client)
        await session.commit()
    assert result2.orders_checked == 2  # neighbor no longer qualifies (already accepted)
    assert result2.orders_updated == 2
    assert await _marking_status(unknown_id) == META_STATUS_ACCEPTED
    assert await _marking_status(pending_id) == META_STATUS_ACCEPTED


# --------------------------------------------------------------------------
# C5 — только чтение, включая ошибочные ответы
# --------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("make_response", "expected_status", "check_operation_failed", "unchanged"),
    [
        pytest.param(
            lambda oid, value: [
                MarketplaceOrderMetaRow(order_id=oid, meta_details=(
                    MarketplaceMetaDetail(key="sgtin", value=value, decision="sgtinIntroduced"),
                )),
            ],
            META_STATUS_ACCEPTED, False, False, id="exact_success",
        ),
        pytest.param(
            lambda oid, value: [
                MarketplaceOrderMetaRow(order_id=oid, meta_details=(
                    MarketplaceMetaDetail(key="sgtin", value=value, decision="pending"),
                )),
            ],
            META_STATUS_PENDING, False, False, id="pending",
        ),
        pytest.param(
            lambda oid, value: [
                MarketplaceOrderMetaRow(order_id=oid, meta_details=(
                    MarketplaceMetaDetail(key="sgtin", value=value, decision="sgtinNotFound"),
                )),
            ],
            META_STATUS_REJECTED, True, False, id="exact_rejection",
        ),
        pytest.param(
            lambda oid, value: [
                MarketplaceOrderMetaRow(order_id=oid, meta_details=(
                    MarketplaceMetaDetail(
                        key="sgtin", value="01OTHERVALUE", decision="sgtinIntroduced"
                    ),
                )),
            ],
            META_STATUS_REPLACEMENT_REQUIRED, False, False, id="other_value",
        ),
        pytest.param(
            lambda oid, value: [
                MarketplaceOrderMetaRow(order_id=oid, meta_details=(
                    MarketplaceMetaDetail(key="sgtin", value=None, decision="optional"),
                )),
            ],
            META_STATUS_UNKNOWN, False, False, id="empty_value",
        ),
        pytest.param(
            lambda oid, value: [
                MarketplaceOrderMetaRow(order_id=oid, meta_details=(), meta={}),
            ],
            META_STATUS_UNKNOWN, False, False, id="missing_kind",
        ),
        pytest.param(lambda oid, value: [], None, False, True, id="missing_row"),
    ],
)
async def test_c5_background_cycle_is_read_only_across_wb_answers(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    make_response,
    expected_status: str | None,
    check_operation_failed: bool,
    unchanged: bool,
) -> None:
    """P3 (ревью Astra) — у каждого сценария свой точный ожидаемый статус,
    а не принадлежность общему множеству: exact_success → accepted,
    pending → pending (без изменения), exact_rejection → rejected и связанная
    pending_confirmation-операция → failed, other_value → replacement_required,
    empty_value → unknown, missing_row → без изменений (`_sync_order_meta_from_wb`
    для этого заказа вообще не вызывается — сосед по пакету не найден).
    """
    _block_writes(monkeypatch)
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    seller_uuid, warehouse_uuid = uuid.UUID(seller_id), uuid.UUID(warehouse_id)
    supply_id = await _make_supply(
        tenant_id=tenant_id,
        seller_id=seller_uuid,
        warehouse_id=warehouse_uuid,
        status=FBS_SUPPLY_STATUS_DRAFT,
        marker="C5",
    )
    wb_order_id = 996001
    order_id = await _raw_order(
        tenant_id=tenant_id,
        seller_id=seller_uuid,
        warehouse_id=warehouse_uuid,
        supply_id=supply_id,
        wb_order_id=wb_order_id,
        meta_status=META_STATUS_UNKNOWN,
    )
    value = f"01WMS546{wb_order_id}"
    before_status = await _marking_status(order_id)

    marking_id: uuid.UUID | None = None
    if check_operation_failed:
        # exact_rejection needs an open pending_kiz_operation to prove it
        # becomes `failed`, not just left dangling.
        async with SessionLocal() as session:
            order = await session.get(FbsOrder, order_id)
            marking = await session.scalar(
                select(FbsOrderMarking).where(FbsOrderMarking.order_id == order_id)
            )
            assert order is not None and marking is not None
            await marking_svc.record_pending_kiz_operation(
                session, order, marking, error_code="wb_readback_empty",
                actor_user_id=None, idempotency_key="wms546-c5-rejection",
            )
            await session.commit()
            marking_id = marking.id

    async def fake_fetch(
        client: object,
        *,
        api_token: str,
        order_ids: list[int],
        marketplace_api_base: str | None = None,
    ) -> list[MarketplaceOrderMetaRow]:
        return make_response(wb_order_id, value)

    monkeypatch.setattr(
        "app.services.fbs_marking_service.fetch_marketplace_orders_meta_batch", fake_fetch
    )
    async with SessionLocal() as session:
        await autopoll.sync_marking_verdicts_for_seller(
            session,
            autopoll.SellerPollTarget(tenant_id=tenant_id, seller_id=seller_uuid),
            async_client,
        )
        await session.commit()
    # _block_writes already asserts no write call happened (it would raise);
    # reaching this point at all is the C5 read-only guarantee.
    if unchanged:
        assert await _marking_status(order_id) == before_status
    else:
        assert await _marking_status(order_id) == expected_status

    if check_operation_failed:
        assert marking_id is not None
        async with SessionLocal() as session:
            operation = await session.scalar(
                select(FbsWbOperation).where(FbsWbOperation.local_entity_id == marking_id)
            )
            assert operation is not None
            assert operation.state == marking_svc.WB_OPERATION_STATE_FAILED
            assert operation.failed_at is not None
            assert operation.error_code == "meta_validation_fail"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error_code", "status_code"),
    [("upstream_error", 429), ("upstream_error", 503), ("network_error", None)],
)
async def test_c5_background_cycle_error_leaves_no_false_success(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    error_code: str,
    status_code: int | None,
) -> None:
    _block_writes(monkeypatch)
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    seller_uuid, warehouse_uuid = uuid.UUID(seller_id), uuid.UUID(warehouse_id)
    supply_id = await _make_supply(
        tenant_id=tenant_id,
        seller_id=seller_uuid,
        warehouse_id=warehouse_uuid,
        status=FBS_SUPPLY_STATUS_DRAFT,
        marker="C5ERR",
    )
    order_id = await _raw_order(
        tenant_id=tenant_id,
        seller_id=seller_uuid,
        warehouse_id=warehouse_uuid,
        supply_id=supply_id,
        wb_order_id=996101,
        meta_status=META_STATUS_UNKNOWN,
    )

    async def failing_fetch(
        client: object,
        *,
        api_token: str,
        order_ids: list[int],
        marketplace_api_base: str | None = None,
    ) -> list[MarketplaceOrderMetaRow]:
        raise WildberriesClientError(error_code, status_code=status_code)

    monkeypatch.setattr(
        "app.services.fbs_marking_service.fetch_marketplace_orders_meta_batch", failing_fetch
    )
    with pytest.raises(WildberriesClientError):
        async with SessionLocal() as session:
            await autopoll.sync_marking_verdicts_for_seller(
                session,
                autopoll.SellerPollTarget(tenant_id=tenant_id, seller_id=seller_uuid),
                async_client,
            )
    assert await _marking_status(order_id) == META_STATUS_UNKNOWN  # not a false accept


# --------------------------------------------------------------------------
# C6 — оба пакета читаются до применения (101 draft/unknown заказ)
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_c6_two_batches_no_partial_write_via_minute_cycle(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _block_writes(monkeypatch)
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    seller_uuid, warehouse_uuid = uuid.UUID(seller_id), uuid.UUID(warehouse_id)
    supply_id = await _make_supply(
        tenant_id=tenant_id,
        seller_id=seller_uuid,
        warehouse_id=warehouse_uuid,
        status=FBS_SUPPLY_STATUS_DRAFT,
        marker="C6",
    )
    now = datetime.now(tz=UTC)
    order_ids: list[uuid.UUID] = []
    async with SessionLocal() as session:
        for index in range(101):
            wb_order_id = 997000 + index
            order = FbsOrder(
                tenant_id=tenant_id,
                seller_id=seller_uuid,
                warehouse_id=warehouse_uuid,
                wb_order_id=wb_order_id,
                wb_rid=f"c6-rid-{wb_order_id}",
                status=FBS_ORDER_STATUS_PACKED,
                supply_id=supply_id,
                created_at_wb=now + timedelta(seconds=index),
                deadline_at=now + timedelta(days=1),
                mapping_status="mapped",
                reserve_status="reserved",
            )
            session.add(order)
            await session.flush()
            order_ids.append(order.id)
            session.add(
                FbsOrderMarking(
                    order_id=order.id,
                    tenant_id=tenant_id,
                    kind="sgtin",
                    value=f"01WMS546{wb_order_id}",
                    check_status=CHECK_STATUS_ERROR,
                    meta_status=META_STATUS_UNKNOWN,
                )
            )
        await session.commit()

    requested_batches: list[list[int]] = []

    async def failing_second_batch(
        client: object,
        *,
        api_token: str,
        order_ids: list[int],
        marketplace_api_base: str | None = None,
    ) -> list[MarketplaceOrderMetaRow]:
        requested_batches.append(order_ids)
        if len(requested_batches) == 2:
            raise WildberriesClientError("upstream_error", status_code=503)
        return [
            MarketplaceOrderMetaRow(
                order_id=oid,
                meta_details=(
                    MarketplaceMetaDetail(
                        key="sgtin", value=f"01WMS546{oid}", decision="sgtinIntroduced"
                    ),
                ),
            )
            for oid in order_ids
        ]

    monkeypatch.setattr(
        "app.services.fbs_marking_service.fetch_marketplace_orders_meta_batch",
        failing_second_batch,
    )
    target = autopoll.SellerPollTarget(tenant_id=tenant_id, seller_id=seller_uuid)

    with pytest.raises(WildberriesClientError):
        async with SessionLocal() as session:
            await autopoll.sync_marking_verdicts_for_seller(session, target, async_client)
    assert [len(batch) for batch in requested_batches] == [100, 1]

    async with SessionLocal() as session:
        markings = list(
            (
                await session.execute(
                    select(FbsOrderMarking).where(FbsOrderMarking.order_id.in_(order_ids))
                )
            )
            .scalars()
            .all()
        )
    assert len(markings) == 101
    assert all(m.meta_status == META_STATUS_UNKNOWN for m in markings)  # nothing stuck

    requested_batches.clear()

    async def recovered(
        client: object,
        *,
        api_token: str,
        order_ids: list[int],
        marketplace_api_base: str | None = None,
    ) -> list[MarketplaceOrderMetaRow]:
        requested_batches.append(order_ids)
        return [
            MarketplaceOrderMetaRow(
                order_id=oid,
                meta_details=(
                    MarketplaceMetaDetail(
                        key="sgtin", value=f"01WMS546{oid}", decision="sgtinIntroduced"
                    ),
                ),
            )
            for oid in order_ids
        ]

    monkeypatch.setattr(
        "app.services.fbs_marking_service.fetch_marketplace_orders_meta_batch", recovered
    )
    async with SessionLocal() as session:
        result = await autopoll.sync_marking_verdicts_for_seller(session, target, async_client)
        await session.commit()
    assert [len(batch) for batch in requested_batches] == [100, 1]
    assert result.orders_checked == 101
    assert result.orders_updated == 101
    for order_id in order_ids:
        assert await _marking_status(order_id) == META_STATUS_ACCEPTED


# --------------------------------------------------------------------------
# C9 — изоляция селлеров и backoff, на draft/unknown
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_c9_seller_isolation_with_draft_unknown_orders(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _block_writes(monkeypatch)
    from tests.fbs_seed_helpers import seed_fbs_warehouse_binding

    headers_a, suffix_a = await _register_ff_admin(async_client)
    seller_a, warehouse_a, tenant_a = await _setup_seller_with_token(
        async_client, headers_a, suffix_a
    )
    headers_b, suffix_b = await _register_ff_admin(async_client)
    seller_b, warehouse_b, tenant_b = await _setup_seller_with_token(
        async_client, headers_b, suffix_b
    )
    async with SessionLocal() as session:
        await seed_fbs_warehouse_binding(
            session, tenant_id=tenant_a, seller_id=uuid.UUID(seller_a),
            wms_warehouse_id=uuid.UUID(warehouse_a),
        )
        await seed_fbs_warehouse_binding(
            session, tenant_id=tenant_b, seller_id=uuid.UUID(seller_b),
            wms_warehouse_id=uuid.UUID(warehouse_b),
        )
        await session.commit()

    supply_a = await _make_supply(
        tenant_id=tenant_a, seller_id=uuid.UUID(seller_a), warehouse_id=uuid.UUID(warehouse_a),
        status=FBS_SUPPLY_STATUS_DRAFT, marker="C9A",
    )
    supply_b = await _make_supply(
        tenant_id=tenant_b, seller_id=uuid.UUID(seller_b), warehouse_id=uuid.UUID(warehouse_b),
        status=FBS_SUPPLY_STATUS_DRAFT, marker="C9B",
    )
    order_a = await _raw_order(
        tenant_id=tenant_a, seller_id=uuid.UUID(seller_a), warehouse_id=uuid.UUID(warehouse_a),
        supply_id=supply_a, wb_order_id=998001, meta_status=META_STATUS_UNKNOWN,
    )
    order_b = await _raw_order(
        tenant_id=tenant_b, seller_id=uuid.UUID(seller_b), warehouse_id=uuid.UUID(warehouse_b),
        supply_id=supply_b, wb_order_id=998002, meta_status=META_STATUS_UNKNOWN,
    )

    async def fake_fetch(
        client: object,
        *,
        api_token: str,
        order_ids: list[int],
        marketplace_api_base: str | None = None,
    ) -> list[MarketplaceOrderMetaRow]:
        if 998001 in order_ids:
            raise WildberriesClientError("upstream_error", status_code=500)
        return [
            MarketplaceOrderMetaRow(
                order_id=oid,
                meta_details=(
                    MarketplaceMetaDetail(
                        key="sgtin", value=f"01WMS546{oid}", decision="sgtinIntroduced"
                    ),
                ),
            )
            for oid in order_ids
        ]

    monkeypatch.setattr(
        "app.services.fbs_marking_service.fetch_marketplace_orders_meta_batch", fake_fetch
    )

    result = await autopoll.sync_fbs_marking_verdicts_all_sellers()

    assert result.seller_errors >= 1
    assert result.sellers_checked >= 1
    assert await _marking_status(order_a) == META_STATUS_UNKNOWN  # seller A's failure isolated
    assert await _marking_status(order_b) == META_STATUS_ACCEPTED  # seller B's commit not lost


@pytest.mark.asyncio
async def test_c9_persistent_429_backoff_stops_further_draft_unknown_polling(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _block_writes(monkeypatch)
    from app.services.marketplace_provider import MarketplaceBackoff
    from tests.fbs_seed_helpers import seed_fbs_warehouse_binding

    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    seller_uuid, warehouse_uuid = uuid.UUID(seller_id), uuid.UUID(warehouse_id)
    async with SessionLocal() as session:
        # sync_fbs_marking_verdicts_all_sellers (called below) discovers
        # sellers via list_sellers_with_marketplace_token, which needs an
        # active, served WB binding — same requirement as the isolation test
        # above; sync_marking_verdicts_for_seller (called directly by the
        # other tests in this file) does not need it.
        await seed_fbs_warehouse_binding(
            session, tenant_id=tenant_id, seller_id=seller_uuid, wms_warehouse_id=warehouse_uuid
        )
        await session.commit()
    supply_id = await _make_supply(
        tenant_id=tenant_id, seller_id=seller_uuid, warehouse_id=warehouse_uuid,
        status=FBS_SUPPLY_STATUS_DRAFT, marker="C9BACKOFF",
    )
    order_id = await _raw_order(
        tenant_id=tenant_id, seller_id=seller_uuid, warehouse_id=warehouse_uuid,
        supply_id=supply_id, wb_order_id=998101, meta_status=META_STATUS_UNKNOWN,
    )
    monkeypatch.setattr(autopoll, "_MARKETPLACE_BACKOFF", MarketplaceBackoff())

    async def rate_limited(
        client: object,
        *,
        api_token: str,
        order_ids: list[int],
        marketplace_api_base: str | None = None,
    ) -> list[MarketplaceOrderMetaRow]:
        raise WildberriesClientError("upstream_error", status_code=429)

    monkeypatch.setattr(
        "app.services.fbs_marking_service.fetch_marketplace_orders_meta_batch", rate_limited
    )

    first = await autopoll.sync_fbs_marking_verdicts_all_sellers()
    assert first.seller_errors == 1
    assert autopoll._MARKETPLACE_BACKOFF.remaining_seconds("wb") > 0
    assert await _marking_status(order_id) == META_STATUS_UNKNOWN

    # Next cycle sees the still-active backoff and must not call WB again at all.
    monkeypatch.setattr(
        "app.services.fbs_marking_service.fetch_marketplace_orders_meta_batch",
        _fail_if_called,
    )
    second = await autopoll.sync_fbs_marking_verdicts_all_sellers()
    assert second.backoff_skips == 1
    assert second.sellers_checked == 0
    assert await _marking_status(order_id) == META_STATUS_UNKNOWN


# --------------------------------------------------------------------------
# C10 — долгое ожидание ограничено активной поставкой
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_c10_long_unknown_wait_limited_to_active_supply(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _block_writes(monkeypatch)
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    seller_uuid, warehouse_uuid = uuid.UUID(seller_id), uuid.UUID(warehouse_id)
    supply_id = await _make_supply(
        tenant_id=tenant_id, seller_id=seller_uuid, warehouse_id=warehouse_uuid,
        status=FBS_SUPPLY_STATUS_DRAFT, marker="C10",
    )
    wb_order_id = 999001
    order_id = await _raw_order(
        tenant_id=tenant_id, seller_id=seller_uuid, warehouse_id=warehouse_uuid,
        supply_id=supply_id, wb_order_id=wb_order_id, meta_status=META_STATUS_UNKNOWN,
    )
    async with SessionLocal() as session:
        order = await session.get(FbsOrder, order_id)
        marking = await session.scalar(
            select(FbsOrderMarking).where(FbsOrderMarking.order_id == order_id)
        )
        assert order is not None and marking is not None
        await marking_svc.record_pending_kiz_operation(
            session, order, marking, error_code="wb_readback_empty",
            actor_user_id=None, idempotency_key="wms546-c10",
        )
        await session.commit()
        marking_id = marking.id

    requested: list[int] = []

    async def always_empty(
        client: object,
        *,
        api_token: str,
        order_ids: list[int],
        marketplace_api_base: str | None = None,
    ) -> list[MarketplaceOrderMetaRow]:
        requested.extend(order_ids)
        return [
            MarketplaceOrderMetaRow(
                order_id=wb_order_id,
                meta_details=(MarketplaceMetaDetail(key="sgtin", value=None, decision="optional"),),
            )
        ]

    monkeypatch.setattr(
        "app.services.fbs_marking_service.fetch_marketplace_orders_meta_batch", always_empty
    )
    target = autopoll.SellerPollTarget(tenant_id=tenant_id, seller_id=seller_uuid)

    for supply_status in (
        FBS_SUPPLY_STATUS_DRAFT, FBS_SUPPLY_STATUS_ASSEMBLING, FBS_SUPPLY_STATUS_PACKED,
    ):
        async with SessionLocal() as session:
            supply = await session.get(FbsSupply, supply_id)
            assert supply is not None
            supply.status = supply_status
            await session.commit()
        requested.clear()
        async with SessionLocal() as session:
            result = await autopoll.sync_marking_verdicts_for_seller(session, target, async_client)
            await session.commit()
        assert requested == [wb_order_id], supply_status
        assert result.orders_checked == 1, supply_status
        assert await _marking_status(order_id) == META_STATUS_UNKNOWN

    for supply_status in (FBS_SUPPLY_STATUS_IN_DELIVERY, FBS_SUPPLY_STATUS_DONE):
        async with SessionLocal() as session:
            supply = await session.get(FbsSupply, supply_id)
            assert supply is not None
            supply.status = supply_status
            await session.commit()
        requested.clear()
        async with SessionLocal() as session:
            result = await autopoll.sync_marking_verdicts_for_seller(session, target, async_client)
            await session.commit()
        assert requested == [], supply_status
        assert result.orders_checked == 0, supply_status

    # Local code and its pending_confirmation operation survive unmodified —
    # no silent success, no deletion, just no more background polling.
    assert await _marking_status(order_id) == META_STATUS_UNKNOWN
    async with SessionLocal() as session:
        operation = await session.scalar(
            select(FbsWbOperation).where(FbsWbOperation.local_entity_id == marking_id)
        )
        assert operation is not None
        assert operation.state == WB_OPERATION_STATE_PENDING_CONFIRMATION


# --------------------------------------------------------------------------
# C7/C8 — advisory lock и «свежий вердикт побеждает старый», для draft/unknown.
#
# C8 is a pure app-level race (asyncio.Event ordering + the existing
# ID/fingerprint freshness check in `_sync_order_meta_from_wb`) and needs no
# real database locking, so it runs on the default SQLite engine exactly like
# WMS-477's own equivalent tests already do. C7 exercises a real PostgreSQL
# advisory lock (`pg_try_advisory_lock`) and only runs when the suite points
# at PostgreSQL — see the verdict in docs/requirements/WMS-546.md for what was
# and was not actually executed against PostgreSQL in this session.
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_c8_fresher_button_verdict_wins_over_slow_minute_cycle_draft_unknown(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _block_writes(monkeypatch)
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    seller_uuid, warehouse_uuid = uuid.UUID(seller_id), uuid.UUID(warehouse_id)
    supply_id = await _make_supply(
        tenant_id=tenant_id, seller_id=seller_uuid, warehouse_id=warehouse_uuid,
        status=FBS_SUPPLY_STATUS_DRAFT, marker="C8",
    )
    wb_order_id = 999101
    order_id = await _raw_order(
        tenant_id=tenant_id, seller_id=seller_uuid, warehouse_id=warehouse_uuid,
        supply_id=supply_id, wb_order_id=wb_order_id, meta_status=META_STATUS_UNKNOWN,
    )
    value = f"01WMS546{wb_order_id}"
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
                    order_id=wb_order_id,
                    meta_details=(
                        MarketplaceMetaDetail(key="sgtin", value=None, decision="optional"),
                    ),
                )
            ]
        return [
            MarketplaceOrderMetaRow(
                order_id=wb_order_id,
                meta_details=(
                    MarketplaceMetaDetail(key="sgtin", value=value, decision="sgtinIntroduced"),
                ),
            )
        ]

    monkeypatch.setattr(
        "app.services.fbs_marking_service.fetch_marketplace_orders_meta_batch", fetch_mock
    )

    async with SessionLocal() as minute_cycle_session:
        minute_cycle_task = asyncio.create_task(
            autopoll.sync_marking_verdicts_for_seller(minute_cycle_session, target, async_client)
        )
        try:
            await asyncio.wait_for(fetching.wait(), 5)

            async with SessionLocal() as button_session:
                button_result = await marking_svc.sync_marking_verdicts_for_supply(
                    button_session, tenant_id, supply_id, async_client, actor_user_id=None,
                )
                await button_session.commit()
            assert button_result.orders_updated == 1
            assert await _marking_status(order_id) == META_STATUS_ACCEPTED

            proceed.set()
            minute_cycle_result = await asyncio.wait_for(minute_cycle_task, 5)
            await minute_cycle_session.commit()
        finally:
            proceed.set()
            if not minute_cycle_task.done():
                minute_cycle_task.cancel()
            await asyncio.gather(minute_cycle_task, return_exceptions=True)

    assert minute_cycle_result.orders_updated == 0  # its own (stale) empty answer was skipped
    assert await _marking_status(order_id) == META_STATUS_ACCEPTED  # not reverted to unknown


@pytest.mark.asyncio
async def test_c7_postgresql_cycle_lock_skips_overlap_with_draft_unknown_seller(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """C7 — a seller with a qualifying draft/unknown order must not be polled
    at all while another minute cycle already holds the advisory lock: the
    second cycle has to skip before even listing sellers. Same mechanism as
    WMS-477's `test_postgresql_marking_verdicts_cycle_lock_skips_concurrent_cycle`
    (that test already proves the lock itself is untouched); this variant adds
    an actual WMS-546-qualifying seller/order to also prove `list_sellers_...`
    and the WB fetch are never reached for it.
    """
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from app.db.session import engine as app_engine

    if app_engine.dialect.name != "postgresql":
        pytest.skip("requires PostgreSQL advisory locks (set WMS_TEST_DATABASE_URL)")

    lock_key = autopoll._MARKING_VERDICTS_CYCLE_LOCK_KEY
    probe_engine = create_async_engine(app_engine.url, pool_size=1, max_overflow=0)
    try:
        async with probe_engine.connect() as probe_conn:
            async with probe_conn.begin():
                held = bool(
                    await probe_conn.scalar(
                        text("select pg_try_advisory_lock(:k)"), {"k": lock_key}
                    )
                )
            assert held is True

            async def _must_not_run(*_a: object, **_k: object) -> list[object]:
                raise AssertionError("cycle must skip before listing sellers")

            monkeypatch.setattr(autopoll, "list_sellers_with_marketplace_token", _must_not_run)
            monkeypatch.setattr(
                "app.services.fbs_marking_service.fetch_marketplace_orders_meta_batch",
                _fail_if_called,
            )

            result = await autopoll.sync_fbs_marking_verdicts_all_sellers()
            assert result.skipped is True
            assert result.sellers_checked == 0

            async with probe_conn.begin():
                await probe_conn.execute(text("select pg_advisory_unlock(:k)"), {"k": lock_key})
    finally:
        await probe_engine.dispose()

    monkeypatch.undo()
    result_after_release = await autopoll.sync_fbs_marking_verdicts_all_sellers()
    assert result_after_release.skipped is False
