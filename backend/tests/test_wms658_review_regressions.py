"""WMS-658 review regressions for normalized CIS identity and stale backfill evidence."""

from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal, engine
from app.models.marking_code import MarkingCode
from app.models.product import Product
from app.models.seller import Seller
from app.models.seller_wildberries_imported_card import (
    SellerWildberriesImportedCard,
)
from app.models.tenant import Tenant
from app.services import marking_code_service as marking
from app.services import wb_honest_sign_service as honest_sign


async def _scope(session: AsyncSession) -> tuple[Tenant, Seller]:
    suffix = uuid.uuid4().hex
    tenant = Tenant(name=f"WMS658 review {suffix}", slug=f"wms658-review-{suffix}")
    session.add(tenant)
    await session.flush()
    seller = Seller(tenant_id=tenant.id, name=f"Seller {suffix}")
    session.add(seller)
    await session.commit()
    return tenant, seller


def _catalog() -> honest_sign.WbCategoryCatalog:
    return honest_sign.WbCategoryCatalog(
        parent_by_subject={101: 10, 102: 20},
        clothing_parent_ids={10},
        source="WMS-658 review fixture",
    )


@pytest.mark.asyncio
async def test_same_normalized_cis_is_duplicate_across_ean13_and_gtin14_rows(
    db_session: AsyncSession,
) -> None:
    tenant, seller = await _scope(db_session)
    gtin14 = "04601234567890"
    ean13 = gtin14[1:]
    normalized_cis = f"01{gtin14}21REVIEW-P1\x1d91ABCD\x1d92CRYPTO-P1"
    framed_cis = f"\x1d{normalized_cis}"
    product = Product(
        tenant_id=tenant.id,
        seller_id=seller.id,
        name="Review P1",
        sku_code="WMS658-REVIEW-P1",
        wb_barcode=ean13,
        requires_honest_sign=False,
    )
    db_session.add(product)
    await db_session.commit()

    first = await marking.import_marking_codes(
        db_session,
        tenant.id,
        seller.id,
        files=[("first.csv", f"cis,gtin\n{framed_cis},{ean13}".encode())],
        pool_specs=[
            marking.PoolImportSpec(
                gtin=ean13,
                title="EAN-13 source",
                product_ids=[product.id],
            )
        ],
        uploaded_by_user_id=None,
    )
    second = await marking.import_marking_codes(
        db_session,
        tenant.id,
        seller.id,
        files=[("second.csv", f"cis,gtin\n{normalized_cis},{gtin14}".encode())],
        pool_specs=[
            marking.PoolImportSpec(
                gtin=gtin14,
                title="GTIN-14 source",
                product_ids=[product.id],
            )
        ],
        uploaded_by_user_id=None,
    )
    stored = list(
        (
            await db_session.scalars(
                select(MarkingCode)
                .where(MarkingCode.tenant_id == tenant.id)
                .order_by(MarkingCode.created_at, MarkingCode.id)
            )
        ).all()
    )

    assert first.accepted_count == 1
    assert (
        second.accepted_count,
        second.skipped_count,
        [(code.cis_code, code.gtin) for code in stored],
    ) == (0, 1, [(framed_cis, ean13)])


@pytest.mark.asyncio
@pytest.mark.postgresql_concurrency
@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="real PostgreSQL required")
async def test_backfill_apply_rechecks_card_evidence_after_product_lock(
    db_session: AsyncSession,
) -> None:
    tenant, seller = await _scope(db_session)
    product = Product(
        tenant_id=tenant.id,
        seller_id=seller.id,
        name="Review P2",
        sku_code="WMS658-REVIEW-P2",
        wb_nm_id=65802,
        wb_chrt_id=658020,
        wb_barcode="4601234565802",
        wb_size="M",
        requires_honest_sign=False,
    )
    db_session.add(product)
    await db_session.flush()
    card = SellerWildberriesImportedCard(
        tenant_id=tenant.id,
        seller_id=seller.id,
        nm_id=65802,
        vendor_code=product.sku_code,
        title=product.name,
        raw_json={
            "nmID": 65802,
            "subjectID": 101,
            "needKiz": False,
        },
    )
    db_session.add(card)
    await db_session.commit()
    tenant_id = tenant.id
    seller_id = seller.id
    product_id = product.id
    card_id = card.id
    plan = await honest_sign.build_backfill_plan(
        db_session,
        tenant_id,
        seller_id,
        catalog=_catalog(),
    )
    assert [row["product_id"] for row in plan["apply"]] == [str(product_id)]
    await db_session.rollback()

    async with (
        SessionLocal() as blocker,
        SessionLocal() as applying,
        SessionLocal() as writer,
        SessionLocal() as observer,
    ):
        locked = await blocker.scalar(
            select(Product).where(Product.id == product_id).with_for_update()
        )
        assert locked is not None
        blocker_pid = int(await blocker.scalar(text("SELECT pg_backend_pid()")) or 0)
        applying_pid = int(await applying.scalar(text("SELECT pg_backend_pid()")) or 0)

        async def apply_stale_plan() -> dict[str, object] | honest_sign.BackfillPlanChanged:
            try:
                return await honest_sign.apply_backfill_plan(
                    applying,
                    tenant_id,
                    seller_id,
                    catalog=_catalog(),
                    fingerprint=str(plan["fingerprint"]),
                    product_ids=[str(row["product_id"]) for row in plan["apply"]],
                )
            except honest_sign.BackfillPlanChanged as exc:
                await applying.rollback()
                return exc

        apply_task = asyncio.create_task(apply_stale_plan())
        try:
            async with asyncio.timeout(10):
                while True:
                    blocking_pids = await observer.scalar(
                        text("SELECT pg_blocking_pids(:pid)"),
                        {"pid": applying_pid},
                    )
                    await observer.rollback()
                    if blocking_pids and blocker_pid in blocking_pids:
                        break
                    assert not apply_task.done(), (
                        "Backfill apply reached a result before waiting for the product lock"
                    )
                    await asyncio.sleep(0.01)

            await writer.execute(
                update(SellerWildberriesImportedCard)
                .where(SellerWildberriesImportedCard.id == card_id)
                .values(
                    raw_json={
                        "nmID": 65802,
                        "subjectID": 102,
                        "needKiz": False,
                    }
                )
            )
            await writer.commit()
            await blocker.commit()
            outcome: dict[str, object] | honest_sign.BackfillPlanChanged = (
                await asyncio.wait_for(apply_task, timeout=10)
            )
        finally:
            if blocker.in_transaction():
                await blocker.rollback()
            if not apply_task.done():
                apply_task.cancel()
            await asyncio.gather(apply_task, return_exceptions=True)

    async with SessionLocal() as check:
        saved_flag = await check.scalar(
            select(Product.requires_honest_sign).where(Product.id == product_id)
        )

    assert isinstance(outcome, honest_sign.BackfillPlanChanged), (
        "Backfill applied a plan after its WB card evidence became stale: "
        f"outcome={outcome!r}, requires_honest_sign={saved_flag!r}"
    )
    assert saved_flag is False
