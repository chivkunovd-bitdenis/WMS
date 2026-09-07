from __future__ import annotations

import asyncio
import threading
import uuid
from datetime import UTC, datetime

import pytest
from marking_datamatrix_test_helpers import build_datamatrix_pdf
from sqlalchemy import select

from app.db.session import SessionLocal, engine
from app.models.fbs_order import FbsOrder, FbsOrderMarking
from app.models.marking_code import MarkingCode, MarkingCodeImport, MarkingPool
from app.models.product import Product
from app.models.seller import Seller
from app.models.tenant import Tenant
from app.services import marking_code_service as svc

GTIN = "04600000000001"
PREFIX = f"01{GTIN}21SYNTHETIC0961"
FULL = PREFIX + "\x1d93ACTUAL+/=TAIL"


async def seed() -> tuple[uuid.UUID, uuid.UUID]:
    async with SessionLocal() as session:
        tenant = Tenant(name="Restore test", slug=f"restore-{uuid.uuid4()}")
        session.add(tenant)
        await session.flush()
        seller = Seller(tenant_id=tenant.id, name="Restore seller")
        session.add(seller)
        await session.flush()
        batch = MarkingCodeImport(tenant_id=tenant.id, seller_id=seller.id, filename="old.pdf")
        pool = MarkingPool(tenant_id=tenant.id, seller_id=seller.id, title="Old pool", gtin=GTIN)
        product = Product(
            tenant_id=tenant.id,
            seller_id=seller.id,
            sku_code="restore",
            name="Restore",
            wb_barcode=GTIN[1:],
        )
        session.add_all([batch, pool, product])
        await session.flush()
        code = MarkingCode(
            tenant_id=tenant.id,
            seller_id=seller.id,
            pool_id=pool.id,
            product_id=product.id,
            import_batch_id=batch.id,
            cis_code=PREFIX,
            gtin=GTIN,
            serial=PREFIX[18:],
            label_artifact_pdf=build_datamatrix_pdf([FULL]),
        )
        session.add(code)
        await session.commit()
        return tenant.id, code.id


async def snapshot(code_id: uuid.UUID) -> dict:
    async with SessionLocal() as session:
        code = await session.get(MarkingCode, code_id)
        assert code
        return {column.name: getattr(code, column.name) for column in MarkingCode.__table__.columns}


@pytest.mark.asyncio
async def test_restore_dry_run_apply_and_repeat_keep_every_other_column() -> None:
    tenant_id, code_id = await seed()
    before = await snapshot(code_id)
    dry = await svc.restore_truncated_pool_cis_codes(tenant_id=tenant_id)
    assert dry["by_outcome"] == {"would_restore": 1}
    assert await snapshot(code_id) == before
    applied = await svc.restore_truncated_pool_cis_codes(tenant_id=tenant_id, apply=True)
    assert applied["by_outcome"] == {"restored": 1}
    assert await snapshot(code_id) == {**before, "cis_code": FULL}
    repeated = await svc.restore_truncated_pool_cis_codes(tenant_id=tenant_id, apply=True)
    assert repeated["by_outcome"] == {"outside_prefix_shape": 1}
    assert await snapshot(code_id) == {**before, "cis_code": FULL}


@pytest.mark.parametrize(
    "case,outcome",
    [
        ("printed", "not_available"),
        ("linked", "linked_code"),
        ("binding_value", "target_conflict"),
        ("prefix", "prefix_mismatch"),
        ("ambiguous", "ambiguous_artifact"),
        ("conflict", "target_conflict"),
        ("product", "product_mismatch"),
        ("owner", "owner_mismatch"),
        ("same", "unchanged"),
        ("no_pdf", "missing_artifact"),
    ],
)
@pytest.mark.asyncio
async def test_restore_refuses_unproven_or_used_sources(case: str, outcome: str) -> None:
    tenant_id, code_id = await seed()
    async with SessionLocal() as session:
        code = await session.get(MarkingCode, code_id)
        assert code
        if case == "printed":
            code.status = "printed"
        elif case in {"linked", "binding_value"}:
            order = FbsOrder(
                tenant_id=tenant_id,
                seller_id=code.seller_id,
                wb_order_id=96096,
                created_at_wb=datetime.now(UTC),
                deadline_at=datetime.now(UTC),
                mapping_status="mapped",
                reserve_status="reserved",
            )
            session.add(order)
            await session.flush()
            session.add(
                FbsOrderMarking(
                    tenant_id=tenant_id,
                    order_id=order.id,
                    kind="sgtin",
                    value=PREFIX if case == "linked" else FULL,
                    marking_code_id=code_id if case == "linked" else None,
                )
            )
        elif case == "prefix":
            code.label_artifact_pdf = build_datamatrix_pdf(
                [FULL.replace("SYNTHETIC0961", "SYNTHETIC09612")]
            )
        elif case == "ambiguous":
            code.label_artifact_pdf = build_datamatrix_pdf([FULL, FULL + "OTHER"])
        elif case == "conflict":
            session.add(MarkingCode(tenant_id=tenant_id, seller_id=code.seller_id, cis_code=FULL))
        elif case == "product":
            product = await session.get(Product, code.product_id)
            assert product
            product.wb_barcode = "1234567890123"
        elif case == "owner":
            other = Seller(tenant_id=tenant_id, name="Other")
            session.add(other)
            await session.flush()
            batch = await session.get(MarkingCodeImport, code.import_batch_id)
            assert batch
            batch.seller_id = other.id
        elif case == "same":
            code.label_artifact_pdf = build_datamatrix_pdf([PREFIX])
        else:
            code.label_artifact_pdf = None
        await session.commit()
    before = await snapshot(code_id)
    report = await svc.restore_truncated_pool_cis_codes(
        tenant_id=tenant_id, apply=True, code_ids=[code_id]
    )
    assert report["by_outcome"] == {outcome: 1}
    assert await snapshot(code_id) == before
    foreign = await svc.restore_truncated_pool_cis_codes(
        tenant_id=uuid.uuid4(), apply=True, code_ids=[code_id]
    )
    assert foreign["scanned"] == 0


@pytest.mark.parametrize(
    "changed_field,changed_value,outcome",
    [
        ("status", "printed", "not_available"),
        ("cis_code", PREFIX + "CHANGED", "source_changed"),
    ],
)
@pytest.mark.asyncio
async def test_decode_does_not_hold_lock_and_apply_rereads_source(
    monkeypatch: pytest.MonkeyPatch,
    changed_field: str,
    changed_value: str,
    outcome: str,
) -> None:
    if engine.dialect.name != "postgresql":
        pytest.skip("Requires PostgreSQL row locks")
    tenant_id, code_id = await seed()
    entered, release = threading.Event(), threading.Event()
    decode = svc._decode_restore_payloads

    def paused_decode(pdf: bytes) -> set[str]:
        entered.set()
        assert release.wait(timeout=10)
        return decode(pdf)

    monkeypatch.setattr(svc, "_decode_restore_payloads", paused_decode)
    task = asyncio.create_task(
        svc.restore_truncated_pool_cis_codes(tenant_id=tenant_id, apply=True)
    )
    try:
        assert await asyncio.to_thread(entered.wait, 5)
        async with SessionLocal() as session:
            code = await asyncio.wait_for(
                session.scalar(
                    select(MarkingCode).where(MarkingCode.id == code_id).with_for_update()
                ),
                timeout=2,
            )
            assert code
            setattr(code, changed_field, changed_value)
            # Commit while PDF decoding is paused: restore must not hold this row lock.
            await asyncio.wait_for(session.commit(), timeout=2)
    finally:
        release.set()
    report = await asyncio.wait_for(task, timeout=10)
    assert report["by_outcome"] == {outcome: 1}
    final = await snapshot(code_id)
    assert final[changed_field] == changed_value
    assert final["cis_code"] == (changed_value if changed_field == "cis_code" else PREFIX)
