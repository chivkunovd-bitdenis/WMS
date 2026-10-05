"""Permanent WMS-658 regressions: SQL candidates must preserve Python CIS identity.

Exercise real CSV parsing and the three public import services. Unrelated CSV
GTIN metadata deliberately excludes the GTIN fast path. No identity lookup or
insert result is mocked; PostgreSQL tests pause only the first real commit and
bypass the process-local mutex to exercise independent worker database locking.
"""

from __future__ import annotations

import asyncio
import csv
import io
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal, engine
from app.models.marking_code import (
    STATUS_PRINTED,
    MarkingCode,
    MarkingCodeImport,
    MarkingPool,
    MarkingPoolProduct,
)
from app.models.product import Product
from app.models.seller import Seller
from app.models.tenant import Tenant
from app.services import marking_code_service as marking

_GTIN = "04601234567890"
_METADATA_GTIN = "09999999999999"
_CIS = f"01{_GTIN}21IDENTITY-658\x1d91ABCD\x1d92CRYPTO+/="
_FRAMES = [
    pytest.param("\x1d\t", "\t\x1d", id="gs-tab"),
    pytest.param("\u00a0", "\u00a0", id="nbsp"),
    pytest.param("\x1e", "\x1e", id="record-separator"),
]
_PATHS = ["manual", "auto", "assign"]


@dataclass(frozen=True)
class Scope:
    tenant_id: uuid.UUID
    seller_id: uuid.UUID
    product_id: uuid.UUID
    sku: str


async def _scope(session: AsyncSession) -> Scope:
    suffix = uuid.uuid4().hex
    tenant = Tenant(name=f"WMS658 identity {suffix}", slug=f"wms658-identity-{suffix}")
    session.add(tenant)
    await session.flush()
    seller = Seller(tenant_id=tenant.id, name=f"Synthetic seller {suffix}")
    session.add(seller)
    await session.flush()
    product = Product(
        tenant_id=tenant.id,
        seller_id=seller.id,
        name="Normalized identity regression",
        sku_code=f"WMS658-IDENTITY-{suffix}",
        wb_barcode=_GTIN,
        wb_size="M",
        requires_honest_sign=False,
    )
    session.add(product)
    await session.commit()
    return Scope(tenant.id, seller.id, product.id, product.sku_code)


def _files(scope: Scope, cis: str) -> list[tuple[str, bytes]]:
    body = io.StringIO(newline="")
    writer = csv.writer(body)
    writer.writerow(["cis", "gtin", "sku", "size"])
    writer.writerow([cis, _METADATA_GTIN, scope.sku, "M"])
    return [("identity.csv", body.getvalue().encode("utf-8"))]


async def _import(
    session: AsyncSession, scope: Scope, path: str, cis: str
) -> tuple[uuid.UUID, int]:
    files = _files(scope, cis)
    if path == "manual":
        manual = await marking.import_marking_codes(
            session,
            scope.tenant_id,
            scope.seller_id,
            files=files,
            pool_specs=[marking.PoolImportSpec(
                gtin=_METADATA_GTIN,
                title="Exact synthetic CSV metadata",
                product_ids=[scope.product_id],
            )],
            uploaded_by_user_id=None,
        )
        return manual.import_id, manual.accepted_count
    if path == "auto":
        auto = await marking.auto_import_marking_codes(
            session,
            scope.tenant_id,
            scope.seller_id,
            request_id=uuid.uuid4(),
            files=files,
            uploaded_by_user_id=None,
        )
        return auto.import_id, sum(group.loaded_count for group in auto.groups)
    assert path == "assign"
    assigned = await marking.assign_import_rows_to_product(
        session,
        scope.tenant_id,
        scope.seller_id,
        request_id=uuid.uuid4(),
        files=files,
        row_keys=["0"],
        product_id=scope.product_id,
        uploaded_by_user_id=None,
    )
    return assigned.import_id, len(assigned.assigned_keys)


async def _stored_codes(session: AsyncSession, scope: Scope) -> list[MarkingCode]:
    return list((await session.scalars(
        select(MarkingCode)
        .where(MarkingCode.tenant_id == scope.tenant_id)
        .order_by(MarkingCode.created_at, MarkingCode.id)
    )).all())


async def _assert_one_original(
    session: AsyncSession, scope: Scope, original: str, original_import_id: uuid.UUID
) -> None:
    codes = await _stored_codes(session, scope)
    pools = list((await session.scalars(
        select(MarkingPool).where(MarkingPool.tenant_id == scope.tenant_id)
    )).all())
    links = list((await session.scalars(
        select(MarkingPoolProduct).where(MarkingPoolProduct.tenant_id == scope.tenant_id)
    )).all())
    assert len(codes) == len(pools) == len(links) == 1, (
        f"normalized repeat created codes/pools/links: {len(codes)}/{len(pools)}/{len(links)}"
    )
    assert (codes[0].cis_code, codes[0].gtin, codes[0].import_batch_id) == (
        original, _METADATA_GTIN, original_import_id
    )
    assert codes[0].pool_id == pools[0].id == links[0].pool_id
    assert links[0].product_id == scope.product_id
    assert await session.scalar(
        select(Product.requires_honest_sign).where(Product.id == scope.product_id)
    ) is True


@pytest.mark.asyncio
@pytest.mark.parametrize(("prefix", "suffix"), _FRAMES)
async def test_lookup_fallback_finds_exact_import_with_python_edge_whitespace(
    db_session: AsyncSession, prefix: str, suffix: str
) -> None:
    scope = await _scope(db_session)
    original = prefix + _CIS + suffix
    assert marking.normalize_cis(original) == _CIS
    import_id, accepted = await _import(db_session, scope, "manual", original)
    assert accepted == 1
    code = (await _stored_codes(db_session, scope))[0]
    assert (code.cis_code, code.gtin) == (original, _METADATA_GTIN)
    code.status = STATUS_PRINTED
    await db_session.commit()
    code_id = code.id

    found = await marking.find_marking_code_by_cis_identity(
        db_session, scope.tenant_id, _CIS,
        for_update=True, status_priority=(STATUS_PRINTED,),
    )

    assert found is not None, "SQL fallback missed a Python-equivalent imported payload"
    assert (found.id, found.cis_code, found.import_batch_id) == (code_id, original, import_id)


@pytest.mark.asyncio
@pytest.mark.parametrize("path", _PATHS)
@pytest.mark.parametrize(("prefix", "suffix"), _FRAMES)
async def test_three_import_paths_reject_normalized_repeat_without_new_pool_or_flag(
    db_session: AsyncSession, path: str, prefix: str, suffix: str
) -> None:
    scope = await _scope(db_session)
    original = prefix + _CIS + suffix
    assert marking.normalize_cis(original) == _CIS
    first_id, accepted = await _import(db_session, scope, "manual", original)
    assert accepted == 1
    # C7: a fully duplicate upload cannot enable an unmarked selected product.
    product = await db_session.get(Product, scope.product_id)
    assert product is not None
    product.requires_honest_sign = False
    await db_session.commit()

    repeated_id, repeated_count = await _import(db_session, scope, path, _CIS)
    batch = await db_session.get(MarkingCodeImport, repeated_id)
    codes = await _stored_codes(db_session, scope)
    pool_ids = list((await db_session.scalars(
        select(MarkingPool.id).where(MarkingPool.tenant_id == scope.tenant_id)
    )).all())
    links = list((await db_session.scalars(
        select(MarkingPoolProduct).where(MarkingPoolProduct.tenant_id == scope.tenant_id)
    )).all())
    await db_session.refresh(product)

    assert batch is not None
    assert (
        repeated_count, batch.accepted_count, batch.skipped_count,
        [(code.cis_code, code.gtin, code.import_batch_id) for code in codes],
        len(pool_ids), len(links), product.requires_honest_sign,
    ) == (0, 0, 1, [(original, _METADATA_GTIN, first_id)], 1, 1, False)


@pytest.mark.asyncio
@pytest.mark.parametrize("path", _PATHS)
@pytest.mark.parametrize("internal", ["\t", "\u00a0", "\x1e"], ids=["tab", "nbsp", "rs"])
async def test_fallback_does_not_collapse_internal_whitespace_or_cross_tenant_collision(
    db_session: AsyncSession, path: str, internal: str
) -> None:
    scope = await _scope(db_session)
    foreign = await _scope(db_session)
    distinct = _CIS.replace("IDENTITY-658", f"IDENTITY{internal}-658")
    assert marking.normalize_cis(distinct) == distinct
    assert marking.normalize_cis(distinct) != marking.normalize_cis(_CIS)
    _, foreign_count = await _import(db_session, foreign, "manual", _CIS)
    distinct_id, distinct_count = await _import(db_session, scope, "manual", distinct)
    assert foreign_count == distinct_count == 1
    distinct_code = (await _stored_codes(db_session, scope))[0]
    distinct_code.status = STATUS_PRINTED
    await db_session.commit()

    # No same-tenant identity exists yet. A SQL candidate collision must not
    # suppress this import or select the older printed internal-whitespace row.
    missing = await marking.find_marking_code_by_cis_identity(
        db_session, scope.tenant_id, _CIS, status_priority=(STATUS_PRINTED,)
    )
    assert missing is None
    canonical_id, canonical_count = await _import(db_session, scope, path, _CIS)
    assert canonical_count == 1
    found = await marking.find_marking_code_by_cis_identity(
        db_session, scope.tenant_id, "\u00a0" + _CIS + "\u00a0",
        status_priority=(STATUS_PRINTED,),
    )
    assert found is not None
    assert (found.cis_code, found.import_batch_id) == (_CIS, canonical_id)
    assert {(code.cis_code, code.import_batch_id) for code in await _stored_codes(
        db_session, scope
    )} == {(distinct, distinct_id), (_CIS, canonical_id)}


@pytest.mark.asyncio
@pytest.mark.parametrize("internal", ["\t", "\u00a0", "\x1e"], ids=["tab", "nbsp", "rs"])
async def test_lookup_fallback_selects_true_identity_among_similar_payloads(
    db_session: AsyncSession, internal: str
) -> None:
    scope = await _scope(db_session)
    foreign = await _scope(db_session)
    distinct = _CIS.replace("IDENTITY-658", f"IDENTITY{internal}-658")
    assert marking.normalize_cis(distinct) == distinct
    _, foreign_count = await _import(db_session, foreign, "manual", _CIS)
    distinct_id, distinct_count = await _import(db_session, scope, "manual", distinct)
    distinct_code = (await _stored_codes(db_session, scope))[0]
    distinct_code.status = STATUS_PRINTED
    await db_session.commit()
    original = "\u00a0" + _CIS + "\u00a0"
    target_id, target_count = await _import(db_session, scope, "manual", original)
    assert foreign_count == distinct_count == target_count == 1
    assert marking.normalize_cis(original) == _CIS

    # The target cannot enter the exact/GTIN fast path. Any broader SQL candidate
    # set still needs Python comparison, even with an older printed near-match.
    found = await marking.find_marking_code_by_cis_identity(
        db_session, scope.tenant_id, _CIS, for_update=True,
        status_priority=(STATUS_PRINTED,),
    )

    assert found is not None, "fallback missed the true identity among similar payloads"
    assert (found.cis_code, found.import_batch_id) == (original, target_id)
    assert {(code.cis_code, code.import_batch_id) for code in await _stored_codes(
        db_session, scope
    )} == {(distinct, distinct_id), (original, target_id)}


@asynccontextmanager
async def _independent_worker(_request_id: uuid.UUID) -> AsyncIterator[None]:
    # Different application workers do not share an asyncio mutex. Only remove
    # that mutex; public services still acquire their real PostgreSQL locks.
    yield


@pytest.mark.asyncio
@pytest.mark.postgresql_concurrency
@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="real PostgreSQL required")
@pytest.mark.parametrize(("first_path", "second_path"), [
    ("manual", "auto"), ("manual", "assign"), ("auto", "assign"),
])
@pytest.mark.parametrize(("prefix", "suffix"), _FRAMES)
async def test_postgresql_workers_share_one_code_pool_and_link_for_identity_variants(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    first_path: str,
    second_path: str,
    prefix: str,
    suffix: str,
) -> None:
    scope = await _scope(db_session)
    original = prefix + _CIS + suffix
    assert marking.normalize_cis(original) == _CIS
    monkeypatch.setattr(marking, "_serialize_import_request", _independent_worker)
    ready_to_commit = asyncio.Event()
    release_first = asyncio.Event()

    # Same configured engine/pool and real code, distinct physical connections.
    async with SessionLocal() as first, SessionLocal() as second, SessionLocal() as observer:
        first_pid = int(await first.scalar(text("SELECT pg_backend_pid()")) or 0)
        second_pid = int(await second.scalar(text("SELECT pg_backend_pid()")) or 0)
        assert first_pid != second_pid
        for session in (first, second):
            await session.execute(text("SET LOCAL statement_timeout = '10s'"))
        real_commit = first.commit

        async def pause_real_commit() -> None:
            await first.flush()
            ready_to_commit.set()
            await asyncio.wait_for(release_first.wait(), timeout=8)
            await real_commit()

        monkeypatch.setattr(first, "commit", pause_real_commit)
        first_task = asyncio.create_task(_import(first, scope, first_path, original))
        second_task: asyncio.Task[tuple[uuid.UUID, int]] | None = None
        try:
            await asyncio.wait_for(ready_to_commit.wait(), timeout=8)
            second_task = asyncio.create_task(_import(second, scope, second_path, _CIS))
            async with asyncio.timeout(8):
                while True:
                    blockers = await observer.scalar(
                        text("SELECT pg_blocking_pids(:pid)"), {"pid": second_pid}
                    )
                    await observer.rollback()
                    if blockers and first_pid in blockers:
                        break
                    assert not second_task.done(), "second worker did not wait for the DB lock"
                    await asyncio.sleep(0.01)
            release_first.set()
            first_result, second_result = await asyncio.wait_for(
                asyncio.gather(first_task, second_task), timeout=12
            )
        finally:
            release_first.set()
            pending = [task for task in (first_task, second_task)
                       if task is not None and not task.done()]
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)

    async with SessionLocal() as check:
        # Check physical state before response counts, so duplicate code/pool
        # failures identify the business invariant even if responses look valid.
        await _assert_one_original(check, scope, original, first_result[0])
        assert (first_result[1], second_result[1]) == (1, 0)
        second_batch = await check.get(MarkingCodeImport, second_result[0])
        assert second_batch is not None
        assert (second_batch.accepted_count, second_batch.skipped_count) == (0, 1)
