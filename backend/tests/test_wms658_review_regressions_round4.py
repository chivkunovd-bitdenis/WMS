"""WMS-658 fourth-review regressions for metadata-independent CIS identity."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.marking_code import STATUS_APPLIED, STATUS_PRINTED, MarkingCode
from app.models.product import Product
from app.models.seller import Seller
from app.models.tenant import Tenant
from app.models.user import User
from app.services import marking_code_service as marking

_ACTUAL_GTIN = "04601234567890"
_UNRELATED_METADATA_GTIN = "09999999999999"
_NORMALIZED_CIS = (
    f"01{_ACTUAL_GTIN}21REVIEW-CSV-GTIN\x1d91ABCD\x1d92CRYPTO"
)
_FIRST_IMPORTED_PAYLOAD = f"\x1d{_NORMALIZED_CIS}"


async def _scope(session: AsyncSession) -> tuple[Tenant, Seller, Product, User]:
    suffix = uuid.uuid4().hex
    tenant = Tenant(name=f"WMS658 round4 {suffix}", slug=f"wms658-round4-{suffix}")
    session.add(tenant)
    await session.flush()
    seller = Seller(tenant_id=tenant.id, name=f"Seller {suffix}")
    session.add(seller)
    await session.flush()
    product = Product(
        tenant_id=tenant.id,
        seller_id=seller.id,
        name="Metadata-independent CIS identity",
        sku_code=f"WMS658-ROUND4-{suffix}",
        wb_barcode=_ACTUAL_GTIN,
        requires_honest_sign=False,
    )
    actor = User(
        tenant_id=tenant.id,
        email=f"wms658-round4-{suffix}@example.com",
        password_hash="synthetic-unused",
        role="fulfillment_admin",
    )
    session.add_all([product, actor])
    await session.commit()
    return tenant, seller, product, actor


async def _manual_import(
    session: AsyncSession,
    *,
    tenant: Tenant,
    seller: Seller,
    product: Product,
    actor: User,
    filename: str,
    cis: str,
    metadata_gtin: str,
) -> marking.MarkingImportResult:
    return await marking.import_marking_codes(
        session,
        tenant.id,
        seller.id,
        files=[(filename, f"cis,gtin\n{cis},{metadata_gtin}".encode())],
        pool_specs=[
            marking.PoolImportSpec(
                gtin=metadata_gtin,
                title=f"CSV metadata GTIN {metadata_gtin}",
                product_ids=[product.id],
            )
        ],
        uploaded_by_user_id=actor.id,
    )


@pytest.mark.asyncio
async def test_lookup_and_pair_verification_ignore_unrelated_import_metadata_gtin(
    db_session: AsyncSession,
) -> None:
    tenant, seller, product, actor = await _scope(db_session)
    imported = await _manual_import(
        db_session,
        tenant=tenant,
        seller=seller,
        product=product,
        actor=actor,
        filename="first.csv",
        cis=_FIRST_IMPORTED_PAYLOAD,
        metadata_gtin=_UNRELATED_METADATA_GTIN,
    )
    code = await db_session.scalar(
        select(MarkingCode).where(MarkingCode.import_batch_id == imported.import_id)
    )
    assert imported.accepted_count == 1
    assert code is not None
    assert (code.cis_code, code.gtin) == (
        _FIRST_IMPORTED_PAYLOAD,
        _UNRELATED_METADATA_GTIN,
    )
    code.status = STATUS_PRINTED
    await db_session.commit()
    code_id = code.id

    found = await marking.find_marking_code_by_cis_identity(
        db_session,
        tenant.id,
        _NORMALIZED_CIS,
    )
    verified = await marking.verify_pair_and_apply(
        db_session,
        tenant.id,
        cis_a=_NORMALIZED_CIS,
        cis_b=_NORMALIZED_CIS,
        acting_user_id=actor.id,
    )
    await db_session.refresh(code)

    assert (
        found.id if found is not None else None,
        verified.match,
        verified.applied,
        verified.code_id,
        code.status,
    ) == (code_id, True, True, code_id, STATUS_APPLIED)


@pytest.mark.asyncio
async def test_repeat_import_uses_cis_identity_not_csv_metadata_gtin(
    db_session: AsyncSession,
) -> None:
    tenant, seller, product, actor = await _scope(db_session)
    first = await _manual_import(
        db_session,
        tenant=tenant,
        seller=seller,
        product=product,
        actor=actor,
        filename="first.csv",
        cis=_FIRST_IMPORTED_PAYLOAD,
        metadata_gtin=_UNRELATED_METADATA_GTIN,
    )
    repeated = await _manual_import(
        db_session,
        tenant=tenant,
        seller=seller,
        product=product,
        actor=actor,
        filename="repeat.csv",
        cis=_NORMALIZED_CIS,
        metadata_gtin=_ACTUAL_GTIN,
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
        repeated.accepted_count,
        repeated.skipped_count,
        [(reason.reason, reason.count) for reason in repeated.skip_reasons],
    ) == (0, 1, [("duplicate", 1)])
    assert len(stored) == 1
    assert (stored[0].cis_code, stored[0].gtin) == (
        _FIRST_IMPORTED_PAYLOAD,
        _UNRELATED_METADATA_GTIN,
    )
    assert marking.normalize_cis(stored[0].cis_code) == _NORMALIZED_CIS
