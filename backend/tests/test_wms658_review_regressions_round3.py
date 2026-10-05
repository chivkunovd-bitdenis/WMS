"""WMS-658 third-review contract for auto-import/backfill Product lock order."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal, engine
from app.models.marking_code import MarkingCode, MarkingPool, MarkingPoolProduct
from app.models.product import Product
from app.models.seller import Seller
from app.models.seller_wildberries_imported_card import (
    SellerWildberriesImportedCard,
)
from app.models.tenant import Tenant
from app.services import marking_code_service as marking
from app.services import wb_honest_sign_service as honest_sign

PRODUCT_A_ID = uuid.UUID("65800000-0000-0000-0000-000000000001")
PRODUCT_B_ID = uuid.UUID("65800000-0000-0000-0000-000000000002")
GTIN_A = "00000000000002"
GTIN_B = "00000000000001"
CIS_A = f"01{GTIN_A}21AUTO-LOCK-A\x1d91ABCD\x1d92CRYPTO-A"
CIS_B = f"01{GTIN_B}21AUTO-LOCK-B\x1d91ABCD\x1d92CRYPTO-B"


def _catalog() -> honest_sign.WbCategoryCatalog:
    return honest_sign.WbCategoryCatalog(
        parent_by_subject={101: 10},
        clothing_parent_ids={10},
        source="WMS-658 round3 fixture",
    )


def _files_b_then_a() -> list[tuple[str, bytes]]:
    body = (
        "cis,gtin,sku,size\n"
        f"{CIS_B},{GTIN_B},WMS658-AUTO-B,M\n"
        f"{CIS_A},{GTIN_A},WMS658-AUTO-A,M"
    )
    return [("auto-b-then-a.csv", body.encode())]


async def _seed(
    session: AsyncSession,
) -> tuple[uuid.UUID, uuid.UUID, dict[str, object]]:
    suffix = uuid.uuid4().hex
    tenant = Tenant(name=f"WMS658 round3 {suffix}", slug=f"wms658-round3-{suffix}")
    session.add(tenant)
    await session.flush()
    seller = Seller(tenant_id=tenant.id, name=f"Seller {suffix}")
    session.add(seller)
    await session.flush()
    products = [
        Product(
            id=PRODUCT_A_ID,
            tenant_id=tenant.id,
            seller_id=seller.id,
            name="Product A",
            sku_code="WMS658-AUTO-A",
            wb_nm_id=65831,
            wb_chrt_id=658310,
            wb_barcode=GTIN_A,
            wb_size="M",
            requires_honest_sign=False,
        ),
        Product(
            id=PRODUCT_B_ID,
            tenant_id=tenant.id,
            seller_id=seller.id,
            name="Product B",
            sku_code="WMS658-AUTO-B",
            wb_nm_id=65832,
            wb_chrt_id=658320,
            wb_barcode=GTIN_B,
            wb_size="M",
            requires_honest_sign=False,
        ),
    ]
    session.add_all(products)
    await session.flush()
    session.add_all(
        [
            SellerWildberriesImportedCard(
                tenant_id=tenant.id,
                seller_id=seller.id,
                nm_id=product.wb_nm_id,
                vendor_code=product.sku_code,
                title=product.name,
                raw_json={
                    "nmID": product.wb_nm_id,
                    "subjectID": 101,
                    "needKiz": False,
                },
            )
            for product in products
        ]
    )
    await session.commit()
    plan = await honest_sign.build_backfill_plan(
        session,
        tenant.id,
        seller.id,
        catalog=_catalog(),
    )
    assert PRODUCT_A_ID.int < PRODUCT_B_ID.int
    assert [row["product_id"] for row in plan["apply"]] == [
        str(PRODUCT_A_ID),
        str(PRODUCT_B_ID),
    ]
    tenant_id = tenant.id
    seller_id = seller.id
    await session.rollback()
    return tenant_id, seller_id, plan


async def _assert_complete_auto_import(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    result: marking.AutoMarkingImportResult,
) -> None:
    assert result.unmatched == []
    assert {(row.product_id, row.loaded_count) for row in result.groups} == {
        (PRODUCT_A_ID, 1),
        (PRODUCT_B_ID, 1),
    }
    flags = list(
        await session.scalars(
            select(Product.requires_honest_sign)
            .where(Product.id.in_([PRODUCT_A_ID, PRODUCT_B_ID]))
            .order_by(Product.id)
        )
    )
    code_rows = list(
        (
            await session.execute(
                select(MarkingCode.product_id, MarkingCode.cis_code)
                .where(
                    MarkingCode.tenant_id == tenant_id,
                    MarkingCode.import_batch_id == result.import_id,
                )
                .order_by(MarkingCode.product_id)
            )
        ).all()
    )
    assert flags == [True, True]
    assert code_rows == [(PRODUCT_A_ID, CIS_A), (PRODUCT_B_ID, CIS_B)]
    assert await session.scalar(
        select(func.count(MarkingPool.id)).where(MarkingPool.tenant_id == tenant_id)
    ) == 2
    assert await session.scalar(
        select(func.count(MarkingPoolProduct.id)).where(
            MarkingPoolProduct.tenant_id == tenant_id
        )
    ) == 2


@pytest.mark.asyncio
async def test_auto_import_b_then_a_still_imports_both_and_enables_flags_atomically(
    db_session: AsyncSession,
) -> None:
    tenant_id, seller_id, _plan = await _seed(db_session)

    result = await marking.auto_import_marking_codes(
        db_session,
        tenant_id,
        seller_id,
        request_id=uuid.uuid4(),
        files=_files_b_then_a(),
        uploaded_by_user_id=None,
    )

    await _assert_complete_auto_import(db_session, tenant_id, result)


@pytest.mark.asyncio
@pytest.mark.postgresql_concurrency
@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="real PostgreSQL required")
async def test_auto_import_and_backfill_share_product_id_lock_order(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant_id, seller_id, plan = await _seed(db_session)
    first_product_flushed = asyncio.Event()
    release_auto_import = asyncio.Event()
    original_insert: Callable[..., Awaitable[MarkingCode | None]] = (
        marking._try_insert_imported_code
    )

    async def scheduled_insert(
        session: AsyncSession,
        **kwargs: Any,
    ) -> MarkingCode | None:
        code = await original_insert(session, **kwargs)
        if (
            session.info.get("wms658_role") == "auto_import"
            and kwargs.get("product_id") == PRODUCT_B_ID
        ):
            # Flush the real B-row update made by auto-import, then only pause
            # scheduling. The production result and database lock are untouched.
            await session.flush()
            first_product_flushed.set()
            await asyncio.wait_for(release_auto_import.wait(), timeout=10)
        return code

    monkeypatch.setattr(marking, "_try_insert_imported_code", scheduled_insert)

    async with (
        SessionLocal() as import_session,
        SessionLocal() as backfill_session,
        SessionLocal() as observer,
    ):
        import_session.info["wms658_role"] = "auto_import"
        import_pid = int(await import_session.scalar(text("SELECT pg_backend_pid()")) or 0)
        backfill_pid = int(await backfill_session.scalar(text("SELECT pg_backend_pid()")) or 0)
        for session in (import_session, backfill_session):
            await session.execute(text("SET LOCAL deadlock_timeout = '100ms'"))
            await session.execute(text("SET LOCAL statement_timeout = '8s'"))

        async def run_auto_import() -> marking.AutoMarkingImportResult | Exception:
            try:
                return await marking.auto_import_marking_codes(
                    import_session,
                    tenant_id,
                    seller_id,
                    request_id=uuid.uuid4(),
                    files=_files_b_then_a(),
                    uploaded_by_user_id=None,
                )
            except Exception as exc:
                await import_session.rollback()
                return exc

        async def run_backfill() -> dict[str, object] | Exception:
            try:
                return await honest_sign.apply_backfill_plan(
                    backfill_session,
                    tenant_id,
                    seller_id,
                    catalog=_catalog(),
                    fingerprint=str(plan["fingerprint"]),
                    product_ids=[str(row["product_id"]) for row in plan["apply"]],
                )
            except Exception as exc:
                await backfill_session.rollback()
                return exc

        import_task = asyncio.create_task(run_auto_import())
        backfill_task = None
        try:
            await asyncio.wait_for(first_product_flushed.wait(), timeout=10)
            backfill_task = asyncio.create_task(run_backfill())
            async with asyncio.timeout(10):
                while True:
                    blockers = await observer.scalar(
                        text("SELECT pg_blocking_pids(:pid)"),
                        {"pid": backfill_pid},
                    )
                    await observer.rollback()
                    if blockers and import_pid in blockers:
                        break
                    assert not backfill_task.done(), (
                        "Backfill finished before encountering auto-import's Product lock"
                    )
                    await asyncio.sleep(0.01)
            release_auto_import.set()
            import_outcome, backfill_outcome = await asyncio.wait_for(
                asyncio.gather(import_task, backfill_task),
                timeout=12,
            )
        finally:
            release_auto_import.set()
            pending = [
                task
                for task in (import_task, backfill_task)
                if task is not None and not task.done()
            ]
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)

    assert isinstance(import_outcome, marking.AutoMarkingImportResult), (
        f"auto-import failed instead of completing both rows: {import_outcome!r}"
    )
    assert isinstance(backfill_outcome, dict | honest_sign.BackfillPlanChanged), (
        f"backfill deadlocked instead of completing or requesting retry: {backfill_outcome!r}"
    )
    async with SessionLocal() as check:
        await _assert_complete_auto_import(check, tenant_id, import_outcome)
