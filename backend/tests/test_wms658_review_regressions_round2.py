"""WMS-658 second-review regressions for scanner identity and lock ordering."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal, engine
from app.models.marking_code import STATUS_APPLIED, STATUS_PRINTED, MarkingCode
from app.models.product import Product
from app.models.seller import Seller
from app.models.seller_wildberries_imported_card import (
    SellerWildberriesImportedCard,
)
from app.models.tenant import Tenant
from app.models.user import User
from app.services import marking_code_service as marking
from app.services import wb_honest_sign_service as honest_sign


async def _scope(session: AsyncSession) -> tuple[Tenant, Seller]:
    suffix = uuid.uuid4().hex
    tenant = Tenant(name=f"WMS658 round2 {suffix}", slug=f"wms658-round2-{suffix}")
    session.add(tenant)
    await session.flush()
    seller = Seller(tenant_id=tenant.id, name=f"Seller {suffix}")
    session.add(seller)
    await session.commit()
    return tenant, seller


def _catalog() -> honest_sign.WbCategoryCatalog:
    return honest_sign.WbCategoryCatalog(
        parent_by_subject={101: 10},
        clothing_parent_ids={10},
        source="WMS-658 round2 fixture",
    )


@pytest.mark.asyncio
async def test_verify_pair_finds_printed_ean13_import_by_normalized_scans(
    db_session: AsyncSession,
) -> None:
    tenant, seller = await _scope(db_session)
    gtin14 = "04601234567890"
    ean13 = gtin14[1:]
    scanned_cis = f"01{gtin14}21REVIEW-PAIR\x1d91ABCD\x1d92CRYPTO-PAIR"
    imported_cis = f"\x1d{scanned_cis}"
    product = Product(
        tenant_id=tenant.id,
        seller_id=seller.id,
        name="Review pair",
        sku_code="WMS658-PAIR",
        wb_barcode=ean13,
        requires_honest_sign=False,
    )
    actor = User(
        tenant_id=tenant.id,
        email=f"wms658-pair-{uuid.uuid4().hex}@example.com",
        password_hash="synthetic-unused",
        role="fulfillment_admin",
    )
    db_session.add_all([product, actor])
    await db_session.commit()

    imported = await marking.import_marking_codes(
        db_session,
        tenant.id,
        seller.id,
        files=[("codes.csv", f"cis,gtin\n{imported_cis},{ean13}".encode())],
        pool_specs=[
            marking.PoolImportSpec(
                gtin=ean13,
                title="EAN-13 printed source",
                product_ids=[product.id],
            )
        ],
        uploaded_by_user_id=actor.id,
    )
    code = await db_session.scalar(
        select(MarkingCode).where(MarkingCode.import_batch_id == imported.import_id)
    )
    assert code is not None and code.cis_code == imported_cis and code.gtin == ean13
    code.status = STATUS_PRINTED
    await db_session.commit()
    code_id = code.id

    result = await marking.verify_pair_and_apply(
        db_session,
        tenant.id,
        cis_a=scanned_cis,
        cis_b=scanned_cis,
        acting_user_id=actor.id,
    )

    await db_session.refresh(code)
    assert result.match is True
    assert result.applied is True
    assert result.code_id == code_id
    assert code.status == STATUS_APPLIED


@pytest.mark.asyncio
@pytest.mark.postgresql_concurrency
@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="real PostgreSQL required")
async def test_manual_import_and_backfill_use_compatible_product_lock_order(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant, seller = await _scope(db_session)
    product_a = Product(
        tenant_id=tenant.id,
        seller_id=seller.id,
        name="Product A",
        sku_code="WMS658-LOCK-A",
        wb_nm_id=65821,
        wb_chrt_id=658210,
        wb_barcode="00000000000002",
        wb_size="M",
        requires_honest_sign=False,
    )
    product_b = Product(
        tenant_id=tenant.id,
        seller_id=seller.id,
        name="Product B",
        sku_code="WMS658-LOCK-B",
        wb_nm_id=65822,
        wb_chrt_id=658220,
        wb_barcode="00000000000001",
        wb_size="M",
        requires_honest_sign=False,
    )
    db_session.add_all([product_a, product_b])
    await db_session.flush()
    db_session.add_all(
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
            for product in (product_a, product_b)
        ]
    )
    await db_session.commit()
    tenant_id = tenant.id
    seller_id = seller.id
    product_a_id = product_a.id
    product_b_id = product_b.id
    plan = await honest_sign.build_backfill_plan(
        db_session,
        tenant_id,
        seller_id,
        catalog=_catalog(),
    )
    assert [row["product_id"] for row in plan["apply"]] == [
        str(product_a_id),
        str(product_b_id),
    ]
    await db_session.rollback()

    gtin_b = "00000000000001"
    gtin_a = "00000000000002"
    cis_b = f"01{gtin_b}21LOCK-B\x1d91ABCD\x1d92CRYPTO-B"
    cis_a = f"01{gtin_a}21LOCK-A\x1d91ABCD\x1d92CRYPTO-A"
    files = [("codes.csv", f"cis,gtin\n{cis_b},{gtin_b}\n{cis_a},{gtin_a}".encode())]
    pool_specs = [
        marking.PoolImportSpec(
            gtin=gtin_b,
            title="Product B first by GTIN",
            product_ids=[product_b_id],
        ),
        marking.PoolImportSpec(
            gtin=gtin_a,
            title="Product A second by GTIN",
            product_ids=[product_a_id],
        ),
    ]

    first_product_flushed = asyncio.Event()
    release_import = asyncio.Event()
    lookup_gtins: list[str] = []
    original_lookup: Callable[
        [AsyncSession, uuid.UUID, list[str]], Awaitable[set[str]]
    ] = marking._existing_import_cis_codes

    async def scheduled_lookup(
        session: AsyncSession,
        lookup_tenant_id: uuid.UUID,
        cis_codes: list[str],
    ) -> set[str]:
        lookup_gtins.extend(
            value
            for cis in cis_codes
            if (value := marking.extract_gtin_from_cis(cis)) is not None
        )
        if session.info.get("wms658_role") == "import" and len(lookup_gtins) == 2:
            # Flush the real first-group product update so PostgreSQL owns B's
            # row lock before backfill begins. Only scheduling is intercepted.
            await session.flush()
            first_product_flushed.set()
            await asyncio.wait_for(release_import.wait(), timeout=10)
        return await original_lookup(session, lookup_tenant_id, cis_codes)

    monkeypatch.setattr(marking, "_existing_import_cis_codes", scheduled_lookup)

    async with (
        SessionLocal() as import_session,
        SessionLocal() as backfill_session,
        SessionLocal() as observer,
    ):
        import_session.info["wms658_role"] = "import"
        import_pid = int(await import_session.scalar(text("SELECT pg_backend_pid()")) or 0)
        backfill_pid = int(await backfill_session.scalar(text("SELECT pg_backend_pid()")) or 0)
        for session in (import_session, backfill_session):
            await session.execute(text("SET LOCAL deadlock_timeout = '100ms'"))
            await session.execute(text("SET LOCAL statement_timeout = '8s'"))

        async def run_import() -> marking.MarkingImportResult | Exception:
            try:
                return await marking.import_marking_codes(
                    import_session,
                    tenant_id,
                    seller_id,
                    files=files,
                    pool_specs=pool_specs,
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

        import_task = asyncio.create_task(run_import())
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
                        "Backfill finished before encountering the import row lock"
                    )
                    await asyncio.sleep(0.01)
            release_import.set()
            import_outcome, backfill_outcome = await asyncio.wait_for(
                asyncio.gather(import_task, backfill_task),
                timeout=12,
            )
        finally:
            release_import.set()
            pending = [
                task
                for task in (import_task, backfill_task)
                if task is not None and not task.done()
            ]
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)

    assert lookup_gtins[:2] == [gtin_b, gtin_a]
    assert isinstance(import_outcome, marking.MarkingImportResult), (
        f"manual import failed under opposite lock order: {import_outcome!r}"
    )
    assert isinstance(backfill_outcome, dict | honest_sign.BackfillPlanChanged), (
        f"backfill failed instead of finishing or requesting retry: {backfill_outcome!r}"
    )

    async with SessionLocal() as check:
        flags = list(
            await check.scalars(
                select(Product.requires_honest_sign)
                .where(Product.id.in_([product_a_id, product_b_id]))
                .order_by(Product.wb_nm_id)
            )
        )
        code_count = int(
            await check.scalar(
                select(func.count(MarkingCode.id)).where(MarkingCode.tenant_id == tenant_id)
            )
            or 0
        )
    assert flags == [True, True]
    assert code_count == 2
