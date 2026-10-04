"""WMS-658 C1-C3, C5-C15, C21-C22: contract fixed before implementation."""

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
from sqlalchemy import func, select
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
    row = Product(
        tenant_id=tenant.id,
        seller_id=seller.id,
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
    return await marking.import_marking_codes(
        session,
        tenant.id,
        seller.id,
        files=[(f"codes.{suffix}", f"cis\n{cis}".encode())],
        pool_specs=[
            marking.PoolImportSpec(
                gtin="04601234567890",
                title="WMS-658 exact upload",
                product_ids=[product.id],
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
async def test_c3_assign_import_accepts_unmarked_product_and_enables_it(db_session: AsyncSession) -> None:
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
    assert [code.cis_code for code in await _codes_for_import(db_session, result.import_id)] == [cis]
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
    cases = [
        ([one], "UNKNOWN", "M", "04601234567890", "Не найден"),
        ([one], "SAME", "L", "04601234567890", "размер"),
        ([one], "SAME", "M", "04601234567891", "указывают на разные"),
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


@pytest.mark.asyncio
async def test_c7_duplicates_create_no_pool_and_do_not_enable_product(
    db_session: AsyncSession,
) -> None:
    tenant, seller = await _scope(db_session)
    product = await _product(db_session, tenant, seller, sku="WMS658-C7")
    cis = _full_cis("C7")
    pool = MarkingPool(
        tenant_id=tenant.id, seller_id=seller.id, gtin="04601234567890", title="existing"
    )
    db_session.add(pool)
    await db_session.flush()
    db_session.add_all([
        MarkingPoolProduct(tenant_id=tenant.id, pool_id=pool.id, product_id=product.id),
        MarkingCode(
            tenant_id=tenant.id, seller_id=seller.id, pool_id=pool.id,
            product_id=product.id, cis_code=cis, gtin="04601234567890",
            status=STATUS_AVAILABLE,
        ),
    ])
    await db_session.commit()
    pools_before = int(await db_session.scalar(select(func.count(MarkingPool.id))) or 0)

    manual = await _manual(db_session, tenant, seller, product, cis)
    auto = await _auto(db_session, tenant, seller, product, cis)
    assigned = await marking.assign_import_rows_to_product(
        db_session, tenant.id, seller.id, request_id=uuid.uuid4(),
        files=[("labels.pdf", _label_pdf(cis, article="UNKNOWN"))], row_keys=["0"],
        product_id=product.id, uploaded_by_user_id=None,
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
                db_session, tenant.id, seller.id, request_id=uuid.uuid4(),
                files=[("labels.pdf", _label_pdf(cis, article="UNKNOWN"))],
                row_keys=["0"], product_id=product.id, uploaded_by_user_id=None,
            )
    monkeypatch.setattr(db_session, "commit", original_commit)
    await db_session.rollback()

    async with SessionLocal() as check:
        saved_product = await check.get(Product, product.id)
        assert saved_product is not None and saved_product.requires_honest_sign is False
        assert int(await check.scalar(select(func.count(MarkingCode.id))) or 0) == 0
        assert int(await check.scalar(select(func.count(MarkingPool.id))) or 0) == 0
        assert int(await check.scalar(select(func.count(MarkingPoolProduct.id))) or 0) == 0

    async with SessionLocal() as retry_session:
        retry_product = await retry_session.get(Product, product.id)
        retry_tenant = await retry_session.get(Tenant, tenant.id)
        retry_seller = await retry_session.get(Seller, seller.id)
        assert retry_product is not None and retry_tenant is not None and retry_seller is not None
        if mode == "auto":
            await _auto(retry_session, retry_tenant, retry_seller, retry_product, cis)
        elif mode == "manual":
            await _manual(retry_session, retry_tenant, retry_seller, retry_product, cis)
        else:
            await marking.assign_import_rows_to_product(
                retry_session, tenant.id, seller.id, request_id=uuid.uuid4(),
                files=[("labels.pdf", _label_pdf(cis, article="UNKNOWN"))],
                row_keys=["0"], product_id=product.id, uploaded_by_user_id=None,
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
    cis = _full_cis("C9")
    request_id = uuid.uuid4()
    files = [("labels.pdf", _label_pdf(cis, article=product.sku_code))]

    async def retry() -> marking.AutoMarkingImportResult:
        async with SessionLocal() as session:
            return await marking.auto_import_marking_codes(
                session, tenant.id, seller.id, request_id=request_id, files=files,
                uploaded_by_user_id=None,
            )

    concurrent = await asyncio.gather(retry(), retry())
    first = concurrent[0]
    repeated = await marking.auto_import_marking_codes(
        db_session, tenant.id, seller.id, request_id=request_id, files=files,
        uploaded_by_user_id=None,
    )
    assign_product = await _product(db_session, tenant, seller, sku="WMS658-C9-ASSIGN")
    assign_cis = _full_cis("C9-ASSIGN")
    assign_request_id = uuid.uuid4()
    assign_files = [("assign.pdf", _label_pdf(assign_cis, article="UNKNOWN"))]
    async def assign_attempt() -> marking.AssignMarkingCodesResult:
        async with SessionLocal() as session:
            return await marking.assign_import_rows_to_product(
                session,
                tenant.id,
                seller.id,
                request_id=assign_request_id,
                files=assign_files,
                row_keys=["0"],
                product_id=assign_product.id,
                uploaded_by_user_id=None,
            )

    assigned, assigned_retry = await asyncio.gather(assign_attempt(), assign_attempt())
    manual_product = await _product(db_session, tenant, seller, sku="WMS658-C9-MANUAL")
    manual_cis = _full_cis("C9-MANUAL")
    async def manual_attempt() -> marking.MarkingImportResult:
        async with SessionLocal() as session:
            retry_tenant = await session.get(Tenant, tenant.id)
            retry_seller = await session.get(Seller, seller.id)
            retry_product = await session.get(Product, manual_product.id)
            assert retry_tenant is not None and retry_seller is not None
            assert retry_product is not None
            return await _manual(
                session, retry_tenant, retry_seller, retry_product, manual_cis
            )

    manual_first, manual_retry = await asyncio.gather(manual_attempt(), manual_attempt())

    await db_session.refresh(product)
    await db_session.refresh(assign_product)
    await db_session.refresh(manual_product)
    assert first.import_id == repeated.import_id
    assert {row.import_id for row in concurrent} == {first.import_id}
    assert assigned.import_id == assigned_retry.import_id
    assert assigned.assigned_keys == assigned_retry.assigned_keys == ["0"]
    assert sorted([manual_first.accepted_count, manual_retry.accepted_count]) == [0, 1]
    assert int(await db_session.scalar(select(func.count(MarkingCode.id))) or 0) == 3
    assert int(await db_session.scalar(select(func.count(MarkingPoolProduct.id))) or 0) == 3
    assert all(
        row.requires_honest_sign for row in (product, assign_product, manual_product)
    )


@pytest.mark.asyncio
async def test_c10_import_keeps_exact_tenant_and_seller_boundaries(db_session: AsyncSession) -> None:
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

    result = await _auto(db_session, tenant, seller, own, _full_cis("C10"))
    assert [group.product_id for group in result.groups] == [own.id]
    with pytest.raises(marking.MarkingCodeServiceError):
        await _manual(db_session, tenant, seller, foreign_seller, _full_cis("C10-X"))
    with pytest.raises(marking.MarkingCodeServiceError):
        await _manual(db_session, tenant, seller, foreign_tenant, _full_cis("C10-Y"))
    for row in (foreign_seller, foreign_tenant):
        await db_session.refresh(row)
        assert row.requires_honest_sign is False


@pytest.mark.asyncio
async def test_c11_pdf_keeps_full_payload_artifact_and_import_identity(
    db_session: AsyncSession,
) -> None:
    tenant, seller = await _scope(db_session)
    product = await _product(db_session, tenant, seller, sku="WMS658-C11")
    cis = _full_cis("C11")
    result = await _auto(db_session, tenant, seller, product, cis)
    code = (await _codes_for_import(db_session, result.import_id))[0]

    assert code.cis_code == cis
    assert code.import_batch_id == result.import_id
    assert code.label_artifact_pdf is not None
    assert _decoded_values(code.label_artifact_pdf) == [cis]
    tape = await marking.build_label_artifact_tape_pdf(db_session, tenant.id, [code.id])
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
    build = getattr(marking, "build_import_result_pdf")

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
    first, second = _full_cis("C13-A"), _full_cis("C13-B")
    result = await marking.auto_import_marking_codes(
        db_session, tenant.id, seller.id, request_id=uuid.uuid4(),
        files=[
            ("a.pdf", _label_pdf(first, article=product.sku_code)),
            ("b.pdf", _label_pdf(second, article=product.sku_code)),
        ],
        uploaded_by_user_id=None,
    )
    codes = await _codes_for_import(db_session, result.import_id)
    by_value = {row.cis_code: row for row in codes}
    build = getattr(marking, "build_import_result_pdf")

    pdf = await build(
        db_session, tenant.id, result.import_id,
        code_ids=[by_value[second].id, by_value[first].id], copies=1,
    )

    assert _decoded_values(pdf) == [second, first]
    await db_session.refresh(old)
    assert old.status == STATUS_AVAILABLE


@pytest.mark.asyncio
async def test_c14_missing_artifact_or_foreign_id_fails_without_substitution(
    db_session: AsyncSession,
) -> None:
    tenant, seller = await _scope(db_session)
    product = await _product(db_session, tenant, seller, sku="WMS658-C14")
    cis = _full_cis("C14")
    result = await _auto(db_session, tenant, seller, product, cis)
    code = (await _codes_for_import(db_session, result.import_id))[0]
    neighbor = MarkingCode(
        tenant_id=tenant.id, seller_id=seller.id, product_id=product.id,
        cis_code=_full_cis("C14-NEIGHBOR"), gtin="04601234567890",
        label_artifact_pdf=build_datamatrix_pdf([_full_cis("C14-NEIGHBOR")]),
        status=STATUS_AVAILABLE,
    )
    db_session.add(neighbor)
    code.label_artifact_pdf = None
    await db_session.commit()
    build = getattr(marking, "build_import_result_pdf")

    with pytest.raises(marking.MarkingCodeServiceError):
        await build(db_session, tenant.id, result.import_id, code_ids=[code.id], copies=1)
    with pytest.raises(marking.MarkingCodeServiceError):
        await build(db_session, tenant.id, result.import_id, code_ids=[neighbor.id], copies=1)
    await db_session.refresh(code)
    await db_session.refresh(neighbor)
    assert code.status == neighbor.status == STATUS_AVAILABLE


@pytest.mark.asyncio
async def test_c15_print_result_preserves_order_copies_payloads_and_nonempty_pages(
    db_session: AsyncSession,
) -> None:
    tenant, seller = await _scope(db_session)
    product = await _product(db_session, tenant, seller, sku="WMS658-C15")
    values = [_full_cis("C15-A"), _full_cis("C15-B")]
    result = await marking.auto_import_marking_codes(
        db_session, tenant.id, seller.id, request_id=uuid.uuid4(),
        files=[
            ("wide.pdf", _label_pdf(values[0], article=product.sku_code)),
            ("small.pdf", _label_pdf(values[1], article=product.sku_code)),
        ], uploaded_by_user_id=None,
    )
    codes = await _codes_for_import(db_session, result.import_id)
    build = getattr(marking, "build_import_result_pdf")
    pdf = await build(
        db_session, tenant.id, result.import_id,
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
    before = (old.status, old.pool_id, product.fbs_stock_limit, product.fbs_percent)
    order_before = (
        order.status, order.reserve_status, order.pick_status, order.pack_status,
        order.sticker_status, order.meta_details_json,
    )
    result = await _auto(db_session, tenant, seller, product, _full_cis("C21-NEW"))
    new_code = (await _codes_for_import(db_session, result.import_id))[0]
    build = getattr(marking, "build_import_result_pdf")

    pdf = await build(
        db_session, tenant.id, result.import_id, code_ids=[new_code.id], copies=1
    )

    await db_session.refresh(old)
    await db_session.refresh(product)
    await db_session.refresh(order)
    assert _decoded_values(pdf) == [_full_cis("C21-NEW")]
    assert (old.status, old.pool_id, product.fbs_stock_limit, product.fbs_percent) == before
    assert (
        order.status, order.reserve_status, order.pick_status, order.pack_status,
        order.sticker_status, order.meta_details_json,
    ) == order_before
    assert set(
        (
            await db_session.scalars(
                select(MarkingPoolProduct.product_id).where(
                    MarkingPoolProduct.pool_id == old_pool.id
                )
            )
        ).all()
    ) == {product.id, shared_product.id}


@pytest.mark.asyncio
async def test_c22_incident_audit_is_read_only_and_reports_first_divergence(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant, seller = await _scope(db_session)
    product = await _product(db_session, tenant, seller, sku="WMS658-C22", required=True)
    source_cis = _full_cis("C22-SOURCE")
    saved_cis = _full_cis("C22-SAVED")
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

    report = await audit.audit_marking_import(
        db_session, tenant.id, batch.id, final_print_pdf=build_datamatrix_pdf([saved_cis])
    )

    assert report["first_divergence"] == "saved_cis"
    assert report["source_payloads"] == [source_cis]
    assert report["saved_payloads"] == [saved_cis]
    assert report["codes"][0]["product_id"] == str(product.id)
    assert report["codes"][0]["pool_id"] == str(pool.id)
    assert (
        int(await db_session.scalar(select(func.count(MarkingCode.id))) or 0),
        int(await db_session.scalar(select(func.count(MarkingPool.id))) or 0),
    ) == before

    await db_session.delete(source_file)
    await db_session.commit()
    gap_report = await audit.audit_marking_import(
        db_session, tenant.id, batch.id, final_print_pdf=None
    )
    assert "source_pdf" in gap_report["evidence_gaps"]
