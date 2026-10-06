"""WMS-658 C1-C3, C5-C15, C21-C22: contract fixed before implementation."""

# Correction checkpoint combines verified fixture and Ruff-only fixes; expectations unchanged.

from __future__ import annotations

import asyncio
import importlib
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import fitz
import pytest
from marking_datamatrix_test_helpers import build_datamatrix_pdf, encode_datamatrix_png
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal
from app.models.fbs_order import FBS_ORDER_STATUS_PACKED, FbsOrder
from app.models.marking_code import (
    STATUS_AVAILABLE,
    MarkingCode,
    MarkingCodeImport,
    MarkingCodeImportFile,
    MarkingPool,
    MarkingPoolProduct,
)
from app.models.product import Product
from app.models.seller import Seller
from app.models.tenant import Tenant
from app.services import marking_code_service as marking
from app.services.marking_datamatrix_service import decode_datamatrix_codes_on_pdf_page


def _full_cis(tag: str, gtin: str = "04601234567890") -> str:
    return f"01{gtin}21{tag}\x1d91ABCD\x1d92CRYPTO+/={tag}"


def _label_pdf(cis: str, *, article: str = "WMS658", size: str = "M") -> bytes:
    doc = fitz.open()
    try:
        page = doc.new_page(width=220, height=220)
        page.insert_text((10, 18), f"SKU: {article}", fontsize=8)
        page.insert_text((10, 30), f"Size: {size}", fontsize=8)
        page.insert_image(
            fitz.Rect(30, 45, 190, 205),
            stream=encode_datamatrix_png(cis),
        )
        return bytes(doc.tobytes())
    finally:
        doc.close()


def _decoded_values(pdf: bytes) -> list[str]:
    with fitz.open(stream=pdf, filetype="pdf") as doc:
        return [
            code.value
            for page in doc
            for code in decode_datamatrix_codes_on_pdf_page(page)
        ]


async def _scope(session: AsyncSession) -> tuple[Tenant, Seller]:
    suffix = uuid.uuid4().hex
    tenant = Tenant(name=f"WMS658 {suffix}", slug=f"wms658-{suffix}")
    session.add(tenant)
    await session.flush()
    seller = Seller(tenant_id=tenant.id, name=f"Seller {suffix}")
    session.add(seller)
    await session.commit()
    return tenant, seller


async def _product(
    session: AsyncSession,
    tenant: Tenant,
    seller: Seller,
    *,
    sku: str,
    barcode: str = "04601234567890",
    size: str = "M",
    required: bool = False,
) -> Product:
    return await _product_ids(
        session,
        tenant.id,
        seller.id,
        sku=sku,
        barcode=barcode,
        size=size,
        required=required,
    )


async def _product_ids(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    *,
    sku: str,
    barcode: str = "04601234567890",
    size: str = "M",
    required: bool = False,
) -> Product:
    row = Product(
        tenant_id=tenant_id,
        seller_id=seller_id,
        name=f"Product {sku}",
        sku_code=sku,
        wb_vendor_code=sku,
        wb_barcode=barcode,
        wb_size=size,
        requires_honest_sign=required,
    )
    session.add(row)
    await session.commit()
    return row


async def _auto(
    session: AsyncSession,
    tenant: Tenant,
    seller: Seller,
    product: Product,
    cis: str,
    *,
    request_id: uuid.UUID | None = None,
) -> marking.AutoMarkingImportResult:
    return await marking.auto_import_marking_codes(
        session,
        tenant.id,
        seller.id,
        request_id=request_id or uuid.uuid4(),
        files=[("labels.pdf", _label_pdf(cis, article=product.sku_code))],
        uploaded_by_user_id=None,
    )


async def _manual(
    session: AsyncSession,
    tenant: Tenant,
    seller: Seller,
    product: Product,
    cis: str,
    *,
    suffix: str = "csv",
) -> marking.MarkingImportResult:
    return await _manual_ids(
        session,
        tenant.id,
        seller.id,
        product.id,
        cis,
        suffix=suffix,
    )


async def _manual_ids(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    product_id: uuid.UUID,
    cis: str,
    *,
    suffix: str = "csv",
) -> marking.MarkingImportResult:
    return await marking.import_marking_codes(
        session,
        tenant_id,
        seller_id,
        files=[(f"codes.{suffix}", f"cis\n{cis}".encode())],
        pool_specs=[
            marking.PoolImportSpec(
                gtin="04601234567890",
                title="WMS-658 exact upload",
                product_ids=[product_id],
            )
        ],
        uploaded_by_user_id=None,
    )


async def _codes_for_import(session: AsyncSession, import_id: uuid.UUID) -> list[MarkingCode]:
    return list(
        (
            await session.scalars(
                select(MarkingCode)
                .where(MarkingCode.import_batch_id == import_id)
                .order_by(MarkingCode.created_at, MarkingCode.id)
            )
        ).all()
    )


@pytest.mark.asyncio
async def test_c1_auto_import_finds_unmarked_product_and_enables_it_atomically(
    db_session: AsyncSession,
) -> None:
    tenant, seller = await _scope(db_session)
    product = await _product(db_session, tenant, seller, sku="WMS658-C1")
    cis = _full_cis("C1")

    result = await _auto(db_session, tenant, seller, product, cis)

    await db_session.refresh(product)
    codes = await _codes_for_import(db_session, result.import_id)
    assert [(group.product_id, group.loaded_count) for group in result.groups] == [
        (product.id, 1)
    ]
    assert [(code.product_id, code.cis_code) for code in codes] == [(product.id, cis)]
    assert product.requires_honest_sign is True


@pytest.mark.asyncio
async def test_c2_manual_import_enables_unmarked_selected_product(db_session: AsyncSession) -> None:
    tenant, seller = await _scope(db_session)
    product = await _product(db_session, tenant, seller, sku="WMS658-C2")
    cis = _full_cis("C2")

    result = await _manual(db_session, tenant, seller, product, cis)

    await db_session.refresh(product)
    codes = await _codes_for_import(db_session, result.import_id)
    assert result.accepted_count == 1
    assert [code.cis_code for code in codes] == [cis]
    assert codes[0].pool_id is not None
    assert await db_session.scalar(
        select(func.count(MarkingPoolProduct.id)).where(
            MarkingPoolProduct.pool_id == codes[0].pool_id,
            MarkingPoolProduct.product_id == product.id,
        )
    ) == 1
    assert product.requires_honest_sign is True


@pytest.mark.asyncio
async def test_c3_assign_import_accepts_unmarked_product_and_enables_it(
    db_session: AsyncSession,
) -> None:
    tenant, seller = await _scope(db_session)
    product = await _product(db_session, tenant, seller, sku="WMS658-C3")
    cis = _full_cis("C3")
    files = [("labels.pdf", _label_pdf(cis, article="NO-MATCH"))]

    result = await marking.assign_import_rows_to_product(
        db_session,
        tenant.id,
        seller.id,
        request_id=uuid.uuid4(),
        files=files,
        row_keys=["0"],
        product_id=product.id,
        uploaded_by_user_id=None,
    )

    await db_session.refresh(product)
    assert result.assigned_keys == ["0"]
    assert [
        code.cis_code for code in await _codes_for_import(db_session, result.import_id)
    ] == [cis]
    assert product.requires_honest_sign is True


def test_c5_auto_match_preserves_existing_article_size_and_gtin_rules() -> None:
    exact = Product(
        id=uuid.uuid4(), tenant_id=uuid.uuid4(), seller_id=uuid.uuid4(),
        name="Exact", sku_code="SKU-ONE", wb_vendor_code="WB-ONE",
        wb_barcode="04601234567890", wb_size="M", requires_honest_sign=False,
    )
    by_sku, reason = marking._resolve_auto_product(
        [exact], article="SKU-ONE", size="M", gtin="09999999999999"
    )
    by_wb_article, _ = marking._resolve_auto_product(
        [exact], article="WB-ONE", size="M", gtin="09999999999999"
    )
    by_gtin, _ = marking._resolve_auto_product(
        [exact], article="", size="M", gtin="04601234567890"
    )
    assert reason == ""
    assert by_sku is by_wb_article is by_gtin is exact


def test_c6_auto_match_rejects_missing_size_conflict_and_ambiguity() -> None:
    tenant_id, seller_id = uuid.uuid4(), uuid.uuid4()
    one = Product(
        id=uuid.uuid4(), tenant_id=tenant_id, seller_id=seller_id,
        name="One", sku_code="SAME", wb_vendor_code="V-ONE",
        wb_barcode="04601234567890", wb_size="M", requires_honest_sign=False,
    )
    two = Product(
        id=uuid.uuid4(), tenant_id=tenant_id, seller_id=seller_id,
        name="Two", sku_code="SAME", wb_vendor_code="V-TWO",
        wb_barcode="04601234567891", wb_size="M", requires_honest_sign=False,
    )
    gtin_conflict = Product(
        id=uuid.uuid4(), tenant_id=tenant_id, seller_id=seller_id,
        name="GTIN conflict", sku_code="OTHER", wb_vendor_code="V-OTHER",
        wb_barcode="04601234567891", wb_size="M", requires_honest_sign=False,
    )
    cases = [
        ([one], "UNKNOWN", "M", "04601234567890", "Не найден"),
        ([one], "SAME", "L", "04601234567890", "размер"),
        ([one, gtin_conflict], "SAME", "M", "04601234567891", "указывают на разные"),
        ([one, two], "SAME", "M", "09999999999999", "неоднозначно"),
    ]
    for products, article, size, gtin, expected_reason in cases:
        matched, reason = marking._resolve_auto_product(
            products, article=article, size=size, gtin=gtin
        )
        assert matched is None
        assert expected_reason.casefold() in reason.casefold()
    assert one.requires_honest_sign is False
    assert two.requires_honest_sign is False
    assert gtin_conflict.requires_honest_sign is False


@pytest.mark.asyncio
async def test_c7_duplicates_create_no_pool_and_do_not_enable_product(
    db_session: AsyncSession,
) -> None:
    tenant, seller = await _scope(db_session)
    product = await _product(db_session, tenant, seller, sku="WMS658-C7")
    tenant_id, seller_id, product_id = tenant.id, seller.id, product.id
    cis = _full_cis("C7")
    pool = MarkingPool(
        tenant_id=tenant_id, seller_id=seller_id, gtin="04601234567890", title="existing"
    )
    db_session.add(pool)
    await db_session.flush()
    db_session.add_all([
        MarkingPoolProduct(tenant_id=tenant_id, pool_id=pool.id, product_id=product_id),
        MarkingCode(
            tenant_id=tenant_id, seller_id=seller_id, pool_id=pool.id,
            product_id=product_id, cis_code=cis, gtin="04601234567890",
            status=STATUS_AVAILABLE,
        ),
    ])
    await db_session.commit()
    pools_before = int(await db_session.scalar(select(func.count(MarkingPool.id))) or 0)

    manual = await _manual(db_session, tenant, seller, product, cis)
    auto = await _auto(db_session, tenant, seller, product, cis)
    assigned = await marking.assign_import_rows_to_product(
        db_session, tenant_id, seller_id, request_id=uuid.uuid4(),
        files=[("labels.pdf", _label_pdf(cis, article="UNKNOWN"))], row_keys=["0"],
        product_id=product_id, uploaded_by_user_id=None,
    )

    await db_session.refresh(product)
    assert manual.accepted_count == 0
    assert auto.groups == [] and auto.unmatched[0].eligible_for_assignment is False
    assert assigned.assigned_keys == []
    assert int(await db_session.scalar(select(func.count(MarkingCode.id))) or 0) == 1
    assert int(await db_session.scalar(select(func.count(MarkingPool.id))) or 0) == pools_before
    assert product.requires_honest_sign is False


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["auto", "manual", "assign"])
async def test_c8_each_import_path_rolls_back_code_pool_link_and_flag_on_commit_failure(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
) -> None:
    tenant, seller = await _scope(db_session)
    product = await _product(db_session, tenant, seller, sku=f"WMS658-C8-{mode}")
    tenant_id, seller_id, product_id = tenant.id, seller.id, product.id
    cis = _full_cis(f"C8-{mode}")
    original_commit: Callable[..., Any] = db_session.commit

    async def fail_commit() -> None:
        raise RuntimeError("WMS658 failure before commit")

    monkeypatch.setattr(db_session, "commit", fail_commit)
    with pytest.raises(RuntimeError, match="WMS658 failure"):
        if mode == "auto":
            await _auto(db_session, tenant, seller, product, cis)
        elif mode == "manual":
            await _manual(db_session, tenant, seller, product, cis)
        else:
            await marking.assign_import_rows_to_product(
                db_session, tenant_id, seller_id, request_id=uuid.uuid4(),
                files=[("labels.pdf", _label_pdf(cis, article="UNKNOWN"))],
                row_keys=["0"], product_id=product_id, uploaded_by_user_id=None,
            )
    monkeypatch.setattr(db_session, "commit", original_commit)
    await db_session.rollback()

    async with SessionLocal() as check:
        saved_product = await check.get(Product, product_id)
        assert saved_product is not None and saved_product.requires_honest_sign is False
        assert int(await check.scalar(select(func.count(MarkingCode.id))) or 0) == 0
        assert int(await check.scalar(select(func.count(MarkingPool.id))) or 0) == 0
        assert int(await check.scalar(select(func.count(MarkingPoolProduct.id))) or 0) == 0

    async with SessionLocal() as retry_session:
        retry_product = await retry_session.get(Product, product_id)
        retry_tenant = await retry_session.get(Tenant, tenant_id)
        retry_seller = await retry_session.get(Seller, seller_id)
        assert retry_product is not None and retry_tenant is not None and retry_seller is not None
        if mode == "auto":
            await _auto(retry_session, retry_tenant, retry_seller, retry_product, cis)
        elif mode == "manual":
            await _manual(retry_session, retry_tenant, retry_seller, retry_product, cis)
        else:
            await marking.assign_import_rows_to_product(
                retry_session, tenant_id, seller_id, request_id=uuid.uuid4(),
                files=[("labels.pdf", _label_pdf(cis, article="UNKNOWN"))],
                row_keys=["0"], product_id=product_id, uploaded_by_user_id=None,
            )
        await retry_session.refresh(retry_product)
        assert retry_product.requires_honest_sign is True
        assert int(await retry_session.scalar(select(func.count(MarkingCode.id))) or 0) == 1
        assert int(await retry_session.scalar(select(func.count(MarkingPoolProduct.id))) or 0) == 1


@pytest.mark.asyncio
async def test_c9_retry_and_concurrent_attempts_have_one_code_one_link_and_true_flag(
    db_session: AsyncSession,
) -> None:
    tenant, seller = await _scope(db_session)
    product = await _product(db_session, tenant, seller, sku="WMS658-C9")
    tenant_id, seller_id, product_id = tenant.id, seller.id, product.id
    cis = _full_cis("C9")
    request_id = uuid.uuid4()
    files = [("labels.pdf", _label_pdf(cis, article=product.sku_code))]

    async def retry() -> marking.AutoMarkingImportResult:
        async with SessionLocal() as session:
            return await marking.auto_import_marking_codes(
                session, tenant_id, seller_id, request_id=request_id, files=files,
                uploaded_by_user_id=None,
            )

    concurrent = await asyncio.gather(retry(), retry())
    first = concurrent[0]
    repeated = await marking.auto_import_marking_codes(
        db_session, tenant_id, seller_id, request_id=request_id, files=files,
        uploaded_by_user_id=None,
    )
    assign_product = await _product_ids(
        db_session,
        tenant_id,
        seller_id,
        sku="WMS658-C9-ASSIGN",
        barcode="04601234567891",
    )
    assign_product_id = assign_product.id
    assign_cis = _full_cis("C9-ASSIGN")
    assign_request_id = uuid.uuid4()
    assign_files = [("assign.pdf", _label_pdf(assign_cis, article="UNKNOWN"))]
    async def assign_attempt() -> marking.AssignMarkingCodesResult:
        async with SessionLocal() as session:
            return await marking.assign_import_rows_to_product(
                session,
                tenant_id,
                seller_id,
                request_id=assign_request_id,
                files=assign_files,
                row_keys=["0"],
                product_id=assign_product_id,
                uploaded_by_user_id=None,
            )

    assigned, assigned_retry = await asyncio.gather(assign_attempt(), assign_attempt())
    manual_product = await _product_ids(
        db_session,
        tenant_id,
        seller_id,
        sku="WMS658-C9-MANUAL",
        barcode="04601234567892",
    )
    manual_product_id = manual_product.id
    manual_cis = _full_cis("C9-MANUAL")
    async def manual_attempt() -> marking.MarkingImportResult:
        async with SessionLocal() as session:
            retry_tenant = await session.get(Tenant, tenant_id)
            retry_seller = await session.get(Seller, seller_id)
            retry_product = await session.get(Product, manual_product_id)
            assert retry_tenant is not None and retry_seller is not None
            assert retry_product is not None
            return await _manual(
                session, retry_tenant, retry_seller, retry_product, manual_cis
            )

    manual_first, manual_retry = await asyncio.gather(manual_attempt(), manual_attempt())

    assert first.import_id == repeated.import_id
    assert {row.import_id for row in concurrent} == {first.import_id}
    assert assigned.import_id == assigned_retry.import_id
    assert assigned.assigned_keys == assigned_retry.assigned_keys == ["0"]
    assert sorted([manual_first.accepted_count, manual_retry.accepted_count]) == [0, 1]
    async with SessionLocal() as check:
        products = [
            await check.get(Product, row_id)
            for row_id in (product_id, assign_product_id, manual_product_id)
        ]
        assert int(await check.scalar(select(func.count(MarkingCode.id))) or 0) == 3
        assert int(await check.scalar(select(func.count(MarkingPoolProduct.id))) or 0) == 3
        assert all(row is not None and row.requires_honest_sign for row in products)


@pytest.mark.asyncio
async def test_c10_import_keeps_exact_tenant_and_seller_boundaries(
    db_session: AsyncSession,
) -> None:
    tenant, seller = await _scope(db_session)
    other_seller = Seller(tenant_id=tenant.id, name="WMS658 other seller")
    db_session.add(other_seller)
    await db_session.commit()
    own = await _product(db_session, tenant, seller, sku="WMS658-C10")
    foreign_seller = await _product(
        db_session, tenant, other_seller, sku="WMS658-C10"
    )
    other_tenant, other_tenant_seller = await _scope(db_session)
    foreign_tenant = await _product(
        db_session, other_tenant, other_tenant_seller, sku="WMS658-C10",
    )
    tenant_id, seller_id = tenant.id, seller.id
    own_id = own.id
    foreign_seller_id, foreign_tenant_id = foreign_seller.id, foreign_tenant.id

    result = await _auto(db_session, tenant, seller, own, _full_cis("C10"))
    assert [group.product_id for group in result.groups] == [own_id]
    async with SessionLocal() as foreign_seller_session:
        with pytest.raises(marking.MarkingCodeServiceError):
            await _manual_ids(
                foreign_seller_session,
                tenant_id,
                seller_id,
                foreign_seller_id,
                _full_cis("C10-X"),
            )
    async with SessionLocal() as foreign_tenant_session:
        with pytest.raises(marking.MarkingCodeServiceError):
            await _manual_ids(
                foreign_tenant_session,
                tenant_id,
                seller_id,
                foreign_tenant_id,
                _full_cis("C10-Y"),
            )
    async with SessionLocal() as check:
        for row_id in (foreign_seller_id, foreign_tenant_id):
            row = await check.get(Product, row_id)
            assert row is not None and row.requires_honest_sign is False


@pytest.mark.asyncio
async def test_c11_pdf_keeps_full_payload_artifact_and_import_identity(
    db_session: AsyncSession,
) -> None:
    tenant, seller = await _scope(db_session)
    product = await _product(db_session, tenant, seller, sku="WMS658-C11")
    tenant_id = tenant.id
    cis = _full_cis("C11")
    result = await _auto(db_session, tenant, seller, product, cis)
    code = (await _codes_for_import(db_session, result.import_id))[0]

    assert code.cis_code == cis
    assert code.import_batch_id == result.import_id
    assert code.label_artifact_pdf is not None
    assert _decoded_values(code.label_artifact_pdf) == [cis]
    tape = await marking.build_label_artifact_tape_pdf(db_session, tenant_id, [code.id])
    assert _decoded_values(tape) == [cis]


@pytest.mark.asyncio
@pytest.mark.parametrize("suffix", ["csv", "txt"])
async def test_c12_text_import_prints_full_saved_payload_not_gtin_or_barcode(
    db_session: AsyncSession,
    suffix: str,
) -> None:
    tenant, seller = await _scope(db_session)
    product = await _product(db_session, tenant, seller, sku=f"WMS658-C12-{suffix}")
    cis = _full_cis(f"C12-{suffix}")
    result = await _manual(db_session, tenant, seller, product, cis, suffix=suffix)
    code = (await _codes_for_import(db_session, result.import_id))[0]
    build = marking.build_import_result_pdf

    pdf = await build(
        db_session, tenant.id, result.import_id, code_ids=[code.id], copies=1
    )

    assert code.cis_code == cis
    assert _decoded_values(pdf) == [cis]


@pytest.mark.asyncio
async def test_c13_print_result_uses_only_selected_ids_in_requested_order(
    db_session: AsyncSession,
) -> None:
    tenant, seller = await _scope(db_session)
    product = await _product(db_session, tenant, seller, sku="WMS658-C13")
    old = MarkingCode(
        tenant_id=tenant.id, seller_id=seller.id, product_id=product.id,
        cis_code=_full_cis("C13-OLD"), gtin="04601234567890",
        label_artifact_pdf=build_datamatrix_pdf([_full_cis("C13-OLD")]),
        status=STATUS_AVAILABLE,
    )
    db_session.add(old)
    await db_session.commit()
    tenant_id, seller_id = tenant.id, seller.id
    product_sku = product.sku_code
    old_id = old.id
    first, second = _full_cis("C13-A"), _full_cis("C13-B")
    result = await marking.auto_import_marking_codes(
        db_session, tenant_id, seller_id, request_id=uuid.uuid4(),
        files=[
            ("a.pdf", _label_pdf(first, article=product_sku)),
            ("b.pdf", _label_pdf(second, article=product_sku)),
        ],
        uploaded_by_user_id=None,
    )
    codes = await _codes_for_import(db_session, result.import_id)
    by_value = {row.cis_code: row for row in codes}
    build = marking.build_import_result_pdf

    pdf = await build(
        db_session, tenant_id, result.import_id,
        code_ids=[by_value[second].id, by_value[first].id], copies=1,
    )

    assert _decoded_values(pdf) == [second, first]
    async with SessionLocal() as check:
        saved_old = await check.get(MarkingCode, old_id)
        assert saved_old is not None and saved_old.status == STATUS_AVAILABLE


@pytest.mark.asyncio
async def test_c14_missing_artifact_or_foreign_id_fails_without_substitution(
    db_session: AsyncSession,
) -> None:
    tenant, seller = await _scope(db_session)
    product = await _product(db_session, tenant, seller, sku="WMS658-C14")
    tenant_id, seller_id, product_id = tenant.id, seller.id, product.id
    cis = _full_cis("C14")
    result = await _auto(db_session, tenant, seller, product, cis)
    code = (await _codes_for_import(db_session, result.import_id))[0]
    neighbor = MarkingCode(
        tenant_id=tenant_id, seller_id=seller_id, product_id=product_id,
        cis_code=_full_cis("C14-NEIGHBOR"), gtin="04601234567890",
        label_artifact_pdf=build_datamatrix_pdf([_full_cis("C14-NEIGHBOR")]),
        status=STATUS_AVAILABLE,
    )
    db_session.add(neighbor)
    code.label_artifact_pdf = None
    await db_session.commit()
    code_id, neighbor_id = code.id, neighbor.id
    build = marking.build_import_result_pdf

    with pytest.raises(marking.MarkingCodeServiceError):
        await build(db_session, tenant_id, result.import_id, code_ids=[code_id], copies=1)
    with pytest.raises(marking.MarkingCodeServiceError):
        await build(db_session, tenant_id, result.import_id, code_ids=[neighbor_id], copies=1)
    async with SessionLocal() as check:
        saved_code = await check.get(MarkingCode, code_id)
        saved_neighbor = await check.get(MarkingCode, neighbor_id)
        assert saved_code is not None and saved_neighbor is not None
        assert saved_code.status == saved_neighbor.status == STATUS_AVAILABLE


@pytest.mark.asyncio
async def test_c15_print_result_preserves_order_copies_payloads_and_nonempty_pages(
    db_session: AsyncSession,
) -> None:
    tenant, seller = await _scope(db_session)
    product = await _product(db_session, tenant, seller, sku="WMS658-C15")
    tenant_id, seller_id, product_sku = tenant.id, seller.id, product.sku_code
    values = [_full_cis("C15-A"), _full_cis("C15-B")]
    result = await marking.auto_import_marking_codes(
        db_session, tenant_id, seller_id, request_id=uuid.uuid4(),
        files=[
            ("wide.pdf", _label_pdf(values[0], article=product_sku)),
            ("small.pdf", _label_pdf(values[1], article=product_sku)),
        ], uploaded_by_user_id=None,
    )
    codes = await _codes_for_import(db_session, result.import_id)
    build = marking.build_import_result_pdf
    pdf = await build(
        db_session, tenant_id, result.import_id,
        code_ids=[codes[1].id, codes[0].id], copies=2,
    )

    with fitz.open(stream=pdf, filetype="pdf") as doc:
        assert len(doc) == 4
        assert all(page.get_pixmap().samples.strip(b"\xff") for page in doc)
    assert _decoded_values(pdf) == [values[1], values[1], values[0], values[0]]


@pytest.mark.asyncio
async def test_c21_exact_import_print_leaves_existing_pool_and_neighbor_processes_unchanged(
    db_session: AsyncSession,
) -> None:
    tenant, seller = await _scope(db_session)
    product = await _product(db_session, tenant, seller, sku="WMS658-C21", required=True)
    shared_product = await _product(
        db_session, tenant, seller, sku="WMS658-C21-SHARED", barcode="04601234567891",
        required=True,
    )
    old_pool = MarkingPool(
        tenant_id=tenant.id, seller_id=seller.id, gtin="04601234567890", title="shared"
    )
    db_session.add(old_pool)
    await db_session.flush()
    old = MarkingCode(
        tenant_id=tenant.id, seller_id=seller.id, product_id=product.id,
        pool_id=old_pool.id, cis_code=_full_cis("C21-OLD"),
        gtin="04601234567890", label_artifact_pdf=build_datamatrix_pdf([_full_cis("C21-OLD")]),
        status=STATUS_AVAILABLE,
    )
    db_session.add_all([
        MarkingPoolProduct(tenant_id=tenant.id, pool_id=old_pool.id, product_id=product.id),
        MarkingPoolProduct(
            tenant_id=tenant.id, pool_id=old_pool.id, product_id=shared_product.id
        ),
        old,
    ])
    order = FbsOrder(
        tenant_id=tenant.id,
        seller_id=seller.id,
        product_id=product.id,
        marketplace="wb",
        external_order_id="WMS658-C21-ORDER",
        wb_order_id=65821,
        status=FBS_ORDER_STATUS_PACKED,
        created_at_wb=datetime.now(UTC),
        deadline_at=datetime.now(UTC),
        mapping_status="mapped",
        reserve_status="reserved",
        pick_status="picked",
        pack_status="packed",
        sticker_status="applied",
        meta_details_json={"marking_copies": 2},
    )
    db_session.add(order)
    await db_session.commit()
    tenant_id = tenant.id
    product_id, shared_product_id = product.id, shared_product.id
    old_id, old_pool_id, order_id = old.id, old_pool.id, order.id
    before = (old.status, old.pool_id, product.fbs_stock_limit, product.fbs_percent)
    order_before = (
        order.status, order.reserve_status, order.pick_status, order.pack_status,
        order.sticker_status, order.meta_details_json,
    )
    result = await _auto(db_session, tenant, seller, product, _full_cis("C21-NEW"))
    new_code = (await _codes_for_import(db_session, result.import_id))[0]
    build = marking.build_import_result_pdf

    pdf = await build(
        db_session, tenant_id, result.import_id, code_ids=[new_code.id], copies=1
    )

    assert _decoded_values(pdf) == [_full_cis("C21-NEW")]
    async with SessionLocal() as check:
        saved_old = await check.get(MarkingCode, old_id)
        saved_product = await check.get(Product, product_id)
        saved_order = await check.get(FbsOrder, order_id)
        assert saved_old is not None and saved_product is not None and saved_order is not None
        assert (
            saved_old.status,
            saved_old.pool_id,
            saved_product.fbs_stock_limit,
            saved_product.fbs_percent,
        ) == before
        assert (
            saved_order.status,
            saved_order.reserve_status,
            saved_order.pick_status,
            saved_order.pack_status,
            saved_order.sticker_status,
            saved_order.meta_details_json,
        ) == order_before
        assert set(
            (
                await check.scalars(
                    select(MarkingPoolProduct.product_id).where(
                        MarkingPoolProduct.pool_id == old_pool_id
                    )
                )
            ).all()
        ) == {product_id, shared_product_id}


@pytest.mark.asyncio
async def test_c22_incident_audit_is_read_only_and_reports_first_divergence(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant, seller = await _scope(db_session)
    product = await _product(db_session, tenant, seller, sku="WMS658-C22", required=True)
    saved_cis = _full_cis("C22-SAVED")
    source_cis = saved_cis
    batch = MarkingCodeImport(
        tenant_id=tenant.id, seller_id=seller.id, filename="04-10-2026.pdf",
        accepted_count=1, skipped_count=0,
    )
    db_session.add(batch)
    await db_session.flush()
    source_file = MarkingCodeImportFile(
        tenant_id=tenant.id,
        import_batch_id=batch.id,
        original_filename="04-10-2026.pdf",
        storage_key="wms658/04-10-2026.pdf",
        content_type="application/pdf",
        size_bytes=1,
        sha256_hex="0" * 64,
    )
    pool = MarkingPool(
        tenant_id=tenant.id,
        seller_id=seller.id,
        gtin="04601234567890",
        title="WMS658 incident pool",
    )
    db_session.add_all([source_file, pool])
    await db_session.flush()
    db_session.add(
        MarkingPoolProduct(
            tenant_id=tenant.id, pool_id=pool.id, product_id=product.id
        )
    )
    code = MarkingCode(
        tenant_id=tenant.id, seller_id=seller.id, product_id=product.id,
        pool_id=pool.id, import_batch_id=batch.id, cis_code=saved_cis,
        gtin="04601234567890",
        label_artifact_pdf=build_datamatrix_pdf([saved_cis]), status=STATUS_AVAILABLE,
    )
    db_session.add(code)
    await db_session.commit()
    before = (
        int(await db_session.scalar(select(func.count(MarkingCode.id))) or 0),
        int(await db_session.scalar(select(func.count(MarkingPool.id))) or 0),
    )
    audit = importlib.import_module("app.services.marking_import_audit_service")
    monkeypatch.setattr(
        audit, "read_source_pdf", lambda *_args, **_kwargs: build_datamatrix_pdf([source_cis])
    )

    # C22 investigates a specific import.  It must not turn an unavailable
    # final print artifact into a synthetic successful comparison.
    missing_final_report = await audit.audit_marking_import(
        db_session, tenant.id, batch.id, final_print_pdf=None
    )

    assert missing_final_report["source_payloads"] == [source_cis]
    assert missing_final_report["saved_payloads"] == [saved_cis]
    assert missing_final_report["codes"] == [
        {
            "id": str(code.id),
            "cis_code": saved_cis,
            "product_id": str(product.id),
            "pool_id": str(pool.id),
            "artifact_payloads": [saved_cis],
        }
    ]
    assert "final_print_pdf" in missing_final_report["evidence_gaps"]
    assert missing_final_report["first_divergence"] is None
    assert (
        int(await db_session.scalar(select(func.count(MarkingCode.id))) or 0),
        int(await db_session.scalar(select(func.count(MarkingPool.id))) or 0),
    ) == before

    # The same DataMatrix in a newly generated visual layout is not proof that
    # the original label survived.  The audit must name the final-layout gap;
    # it must not mark this controlled comparison as a successful incident
    # investigation merely because the payload itself still decodes.
    rebuilt_layout_report = await audit.audit_marking_import(
        db_session,
        tenant.id,
        batch.id,
        final_print_pdf=_label_pdf(saved_cis, article="REBUILT-C22", size="XL"),
    )
    assert rebuilt_layout_report["final_print_payloads"] == [saved_cis]
    assert rebuilt_layout_report["first_divergence"] == "final_print_layout"
    assert "final_print_layout" in rebuilt_layout_report["evidence_gaps"]
    assert (
        int(await db_session.scalar(select(func.count(MarkingCode.id))) or 0),
        int(await db_session.scalar(select(func.count(MarkingPool.id))) or 0),
    ) == before

    await db_session.delete(source_file)
    await db_session.commit()
    source_gap_report = await audit.audit_marking_import(
        db_session, tenant.id, batch.id, final_print_pdf=None
    )
    assert "source_pdf" in source_gap_report["evidence_gaps"]
    assert "final_print_pdf" in source_gap_report["evidence_gaps"]


async def _seed_c22_audit_import(
    session: AsyncSession,
    *,
    cis: str,
    label_artifact_pdf: bytes,
) -> tuple[Tenant, MarkingCodeImport]:
    tenant, seller = await _scope(session)
    product = await _product(session, tenant, seller, sku=f"WMS658-C22-{uuid.uuid4().hex}")
    batch = MarkingCodeImport(
        tenant_id=tenant.id,
        seller_id=seller.id,
        filename="04-10-2026.pdf",
        accepted_count=1,
        skipped_count=0,
    )
    session.add(batch)
    await session.flush()
    source_file = MarkingCodeImportFile(
        tenant_id=tenant.id,
        import_batch_id=batch.id,
        original_filename="04-10-2026.pdf",
        storage_key=f"wms658/{batch.id}.pdf",
        content_type="application/pdf",
        size_bytes=1,
        sha256_hex="0" * 64,
    )
    pool = MarkingPool(
        tenant_id=tenant.id,
        seller_id=seller.id,
        gtin="04601234567890",
        title="WMS658 audit regression",
    )
    session.add_all((source_file, pool))
    await session.flush()
    session.add(MarkingPoolProduct(tenant_id=tenant.id, pool_id=pool.id, product_id=product.id))
    session.add(
        MarkingCode(
            tenant_id=tenant.id,
            seller_id=seller.id,
            product_id=product.id,
            pool_id=pool.id,
            import_batch_id=batch.id,
            cis_code=cis,
            gtin="04601234567890",
            label_artifact_pdf=label_artifact_pdf,
            status=STATUS_AVAILABLE,
        )
    )
    await session.commit()
    return tenant, batch


def _rasterized_label_pdf(cis: str, *, article: str) -> bytes:
    """Make visually different label bytes with the same DataMatrix geometry."""
    source = fitz.open(stream=_label_pdf(cis, article=article), filetype="pdf")
    try:
        pixmap = source[0].get_pixmap(matrix=fitz.Matrix(3, 3), alpha=False)
        doc = fitz.open()
        try:
            page = doc.new_page(width=220, height=220)
            page.insert_image(page.rect, stream=bytes(pixmap.tobytes("png")))
            return bytes(doc.tobytes())
        finally:
            doc.close()
    finally:
        source.close()


def _framed_label_page(label_pdf: bytes) -> bytes:
    """Place an unchanged 220x220 label on a larger supplier source page."""
    label = fitz.open(stream=label_pdf, filetype="pdf")
    try:
        document = fitz.open()
        try:
            page = document.new_page(width=600, height=800)
            page.show_pdf_page(fitz.Rect(30, 30, 250, 250), label, 0)
            page.draw_rect(fitz.Rect(30, 30, 250, 250))
            return bytes(document.tobytes())
        finally:
            document.close()
    finally:
        label.close()


def _merge_pdf_pages(pages: list[bytes]) -> bytes:
    document = fitz.open()
    try:
        for page_pdf in pages:
            with fitz.open(stream=page_pdf, filetype="pdf") as source:
                document.insert_pdf(source)
        return bytes(document.tobytes())
    finally:
        document.close()


@pytest.mark.asyncio
async def test_c22_audit_reports_source_to_saved_label_substitution(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A full CIS match does not prove that the supplied label was preserved."""
    cis = _full_cis("C22-SOURCE-LABEL")
    source_pdf = _label_pdf(cis, article="SUPPLIER-ORIGINAL", size="M")
    regenerated_pdf = build_datamatrix_pdf([cis])
    assert _decoded_values(source_pdf) == [cis]
    assert _decoded_values(regenerated_pdf) == [cis]
    assert source_pdf != regenerated_pdf

    tenant, batch = await _seed_c22_audit_import(
        db_session, cis=cis, label_artifact_pdf=regenerated_pdf
    )
    audit = importlib.import_module("app.services.marking_import_audit_service")
    monkeypatch.setattr(audit, "read_source_pdf", lambda *_args, **_kwargs: source_pdf)
    before = int(await db_session.scalar(select(func.count(MarkingCode.id))) or 0)

    report = await audit.audit_marking_import(
        db_session, tenant.id, batch.id, final_print_pdf=regenerated_pdf
    )

    assert report["source_payloads"] == [cis]
    assert report["saved_payloads"] == [cis]
    assert report["artifact_payloads"] == [cis]
    assert report["first_divergence"] == "label_artifact_pdf"
    assert int(await db_session.scalar(select(func.count(MarkingCode.id))) or 0) == before


@pytest.mark.asyncio
async def test_c22_audit_reports_raster_final_label_substitution(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Image placement alone cannot prove the final label image has not changed."""
    cis = _full_cis("C22-RASTER-LABEL")
    original_pdf = _rasterized_label_pdf(cis, article="SUPPLIER-ORIGINAL")
    substituted_pdf = _rasterized_label_pdf(cis, article="REPLACED-ARTICLE")
    assert _decoded_values(original_pdf) == [cis]
    assert _decoded_values(substituted_pdf) == [cis]
    assert original_pdf != substituted_pdf

    tenant, batch = await _seed_c22_audit_import(
        db_session, cis=cis, label_artifact_pdf=original_pdf
    )
    audit = importlib.import_module("app.services.marking_import_audit_service")
    monkeypatch.setattr(audit, "read_source_pdf", lambda *_args, **_kwargs: original_pdf)

    report = await audit.audit_marking_import(
        db_session, tenant.id, batch.id, final_print_pdf=substituted_pdf
    )

    assert report["source_payloads"] == [cis]
    assert report["artifact_payloads"] == [cis]
    assert report["final_print_payloads"] == [cis]
    assert report["first_divergence"] == "final_print_layout"
    assert "final_print_layout" in report["evidence_gaps"]


@pytest.mark.asyncio
async def test_c22_audit_accepts_unchanged_label_cropped_from_supplier_page(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The known source crop is evidence, not a layout substitution."""
    tenant, seller = await _scope(db_session)
    product = await _product(db_session, tenant, seller, sku="WMS658-C22-CROP")
    tenant_id, seller_id, product_sku = tenant.id, seller.id, product.sku_code
    cis = _full_cis("C22-CROP")
    source_pdf = _framed_label_page(_label_pdf(cis, article=product_sku))

    result = await marking.auto_import_marking_codes(
        db_session,
        tenant_id,
        seller_id,
        request_id=uuid.uuid4(),
        files=[("supplier-page.pdf", source_pdf)],
        uploaded_by_user_id=None,
    )
    code = (await _codes_for_import(db_session, result.import_id))[0]
    assert code.label_artifact_pdf is not None
    assert _decoded_values(source_pdf) == [cis]
    assert _decoded_values(code.label_artifact_pdf) == [cis]
    with fitz.open(stream=code.label_artifact_pdf, filetype="pdf") as artifact:
        assert tuple(artifact[0].rect) == (0.0, 0.0, 220.0, 220.0)

    # The importer can persist the source under the test storage backend.
    # Keep one metadata row whose bytes are supplied by the controlled external
    # storage boundary, exactly as an audit of a preserved source would see it.
    await db_session.execute(
        delete(MarkingCodeImportFile).where(
            MarkingCodeImportFile.import_batch_id == result.import_id
        )
    )
    db_session.add(
        MarkingCodeImportFile(
            tenant_id=tenant_id,
            import_batch_id=result.import_id,
            original_filename="supplier-page.pdf",
            storage_key=f"wms658/{result.import_id}/supplier-page.pdf",
            content_type="application/pdf",
            size_bytes=len(source_pdf),
            sha256_hex="0" * 64,
        )
    )
    await db_session.commit()
    final_pdf = await marking.build_import_result_pdf(
        db_session, tenant_id, result.import_id, code_ids=[code.id], copies=1
    )
    audit = importlib.import_module("app.services.marking_import_audit_service")
    monkeypatch.setattr(audit, "read_source_pdf", lambda *_args, **_kwargs: source_pdf)

    report = await audit.audit_marking_import(
        db_session, tenant_id, result.import_id, final_print_pdf=final_pdf
    )

    assert report["source_payloads"] == [cis]
    assert report["artifact_payloads"] == [cis]
    assert report["final_print_payloads"] == [cis]
    assert report["first_divergence"] is None
    assert report["evidence_gaps"] == []


@pytest.mark.asyncio
async def test_c22_audit_reports_ambiguous_layouts_for_same_cis_in_one_source_pdf(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Deduplication of imported codes must not discard source-layout evidence."""
    cis = _full_cis("C22-ONE-PDF-AMBIGUOUS")
    source_pdf = _merge_pdf_pages([
        _framed_label_page(_label_pdf(cis, article="SOURCE-ORIGINAL")),
        _framed_label_page(_label_pdf(cis, article="SOURCE-DIFFERENT")),
    ])
    with fitz.open(stream=source_pdf, filetype="pdf") as source:
        assert len(source) == 2
        assert [
            decoded.value
            for page in source
            for decoded in decode_datamatrix_codes_on_pdf_page(page)
        ] == [cis, cis]
        assert "SOURCE-ORIGINAL" in source[0].get_text()
        assert "SOURCE-DIFFERENT" in source[1].get_text()
    parsed = marking.parse_import_file("two-layouts.pdf", source_pdf)
    assert len(parsed) == 1
    assert parsed[0]["cis"] == cis
    saved_label = bytes(parsed[0]["label_pdf"])
    assert _decoded_values(saved_label) == [cis]

    tenant, batch = await _seed_c22_audit_import(
        db_session, cis=cis, label_artifact_pdf=saved_label
    )
    audit = importlib.import_module("app.services.marking_import_audit_service")
    monkeypatch.setattr(audit, "read_source_pdf", lambda *_args, **_kwargs: source_pdf)

    report = await audit.audit_marking_import(
        db_session, tenant.id, batch.id, final_print_pdf=saved_label
    )

    assert report["source_payloads"] == [cis, cis]
    assert report["artifact_payloads"] == [cis]
    assert report["first_divergence"] is None
    assert "source_to_artifact_layout" in report["evidence_gaps"]
