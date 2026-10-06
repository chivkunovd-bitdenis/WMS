"""WMS-658 C16-C20: WB evidence and safe current-product backfill contract."""

from __future__ import annotations

import importlib
import uuid
from typing import Any

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.marking_code import MarkingCode, MarkingPool
from app.models.product import Product
from app.models.seller import Seller
from app.models.seller_wildberries_imported_card import SellerWildberriesImportedCard
from app.models.tenant import Tenant
from app.services import wildberries_product_import_service as product_import


def _marking_service() -> Any:
    return importlib.import_module("app.services.wb_honest_sign_service")


def _catalog(service: Any) -> Any:
    return service.WbCategoryCatalog(
        parent_by_subject={101: 10, 102: 20, 103: 10},
        clothing_parent_ids={10},
        source="GET /content/v2/object/all + /content/v2/object/parent/all",
    )


async def _scope(session: AsyncSession) -> tuple[Tenant, Seller]:
    suffix = uuid.uuid4().hex
    tenant = Tenant(name=f"WMS658 WB {suffix}", slug=f"wms658-wb-{suffix}")
    session.add(tenant)
    await session.flush()
    seller = Seller(tenant_id=tenant.id, name=f"Seller {suffix}")
    session.add(seller)
    await session.commit()
    return tenant, seller


def _card(
    nm_id: int,
    *,
    subject_id: int | None,
    need_kiz: bool | None = None,
    subject_name: str = "Предмет",
    sizes: list[dict[str, object]] | None = None,
    **extra: object,
) -> dict[str, object]:
    row: dict[str, object] = {
        "nmID": nm_id,
        "vendorCode": f"WMS658-{nm_id}",
        "title": f"Product {nm_id}",
        "subjectName": subject_name,
        "sizes": sizes or [
            {"chrtID": nm_id * 10, "techSize": "M", "skus": [f"BAR-{nm_id}"]}
        ],
        **extra,
    }
    if subject_id is not None:
        row["subjectID"] = subject_id
    if need_kiz is not None:
        row["needKiz"] = need_kiz
    return row


@pytest.mark.asyncio
async def test_c16_only_need_kiz_or_official_clothing_parent_enables_flag() -> None:
    service = _marking_service()
    requests: list[tuple[str, str]] = []

    def wb(request: httpx.Request) -> httpx.Response:
        requests.append((request.method, request.url.path))
        if request.url.path.endswith("/object/parent/all"):
            return httpx.Response(
                200,
                json={"data": [{"id": 10, "name": "Одежда"}, {"id": 20, "name": "Обувь"}]},
            )
        if request.url.path.endswith("/object/all"):
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"subjectID": 101, "parentID": 10, "subjectName": "Футболки"},
                        {"subjectID": 102, "parentID": 20, "subjectName": "Кеды"},
                    ]
                },
            )
        return httpx.Response(404)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(wb), base_url="https://content-api.wildberries.ru"
    ) as client:
        catalog = await service.fetch_category_catalog(client, api_token="test-token")
    cases = [
        (_card(1, subject_id=102, need_kiz=True), True, "needKiz"),
        (_card(2, subject_id=101, need_kiz=False), True, "clothing_parent"),
        (_card(3, subject_id=102, need_kiz=False, kizMarked=True), False, None),
        (_card(4, subject_id=102, need_kiz=False, subject_name="Одежда"), False, None),
        (_card(5, subject_id=999, need_kiz=False, subject_name="Платья"), False, None),
    ]

    for card, expected, reason in cases:
        decision = service.derive_marking_requirement(card, catalog)
        assert decision.required is expected
        assert decision.reason == reason
    assert set(requests) == {
        ("GET", "/content/v2/object/parent/all"),
        ("GET", "/content/v2/object/all"),
    }
    assert catalog.parent_by_subject == {101: 10, 102: 20}
    assert catalog.clothing_parent_ids == {10}


@pytest.mark.asyncio
async def test_c17_new_clothing_variants_and_need_kiz_card_are_marked_without_new_identity(
    db_session: AsyncSession,
) -> None:
    tenant, seller = await _scope(db_session)
    service = _marking_service()
    cards = [
        _card(
            17,
            subject_id=101,
            need_kiz=False,
            sizes=[
                {"chrtID": 171, "techSize": "S", "skus": ["BAR-17-S"]},
                {"chrtID": 172, "techSize": "L", "skus": ["BAR-17-L"]},
            ],
        ),
        _card(18, subject_id=102, need_kiz=True),
    ]

    await product_import.upsert_products_from_wb_cards(
        db_session,
        tenant.id,
        seller.id,
        cards,
        marking_catalog=_catalog(service),
    )

    rows = list(
        (
            await db_session.scalars(
                select(Product).where(Product.tenant_id == tenant.id).order_by(Product.wb_chrt_id)
            )
        ).all()
    )
    assert [(row.wb_nm_id, row.wb_chrt_id, row.wb_barcode, row.wb_size) for row in rows] == [
        (17, 171, "BAR-17-S", "S"),
        (17, 172, "BAR-17-L", "L"),
        (18, 180, "BAR-18", "M"),
    ]
    assert all(row.requires_honest_sign for row in rows)
    assert not hasattr(rows[0], "wb_marking_category_id")


@pytest.mark.asyncio
async def test_c18_sync_is_monotonic_and_category_failure_is_diagnostic_not_fatal(
    db_session: AsyncSession,
) -> None:
    tenant, seller = await _scope(db_session)
    service = _marking_service()
    marked = Product(
        tenant_id=tenant.id, seller_id=seller.id, name="Marked", sku_code="WMS658-181",
        wb_nm_id=181, wb_chrt_id=1810, wb_barcode="BAR-181", wb_size="M",
        requires_honest_sign=True,
    )
    unmarked = Product(
        tenant_id=tenant.id, seller_id=seller.id, name="Unmarked", sku_code="WMS658-182",
        wb_nm_id=182, wb_chrt_id=1820, wb_barcode="BAR-182", wb_size="M",
        requires_honest_sign=False,
    )
    db_session.add_all([marked, unmarked])
    await db_session.commit()

    failed_catalog = await product_import.upsert_products_from_wb_cards(
        db_session,
        tenant.id,
        seller.id,
        [
            _card(181, subject_id=101, need_kiz=None),
            _card(182, subject_id=101, need_kiz=None),
        ],
        marking_catalog=None,
        marking_catalog_error="wb_category_catalog_unavailable",
    )
    await db_session.refresh(marked)
    await db_session.refresh(unmarked)
    assert marked.requires_honest_sign is True
    assert unmarked.requires_honest_sign is False
    assert failed_catalog["marking_diagnostics"] == [
        {
            "code": "wb_category_catalog_unavailable",
            "nm_ids": [181, 182],
        }
    ]

    await product_import.upsert_products_from_wb_cards(
        db_session,
        tenant.id,
        seller.id,
        [_card(181, subject_id=102, need_kiz=False), _card(182, subject_id=101)],
        marking_catalog=_catalog(service),
    )
    await db_session.refresh(marked)
    await db_session.refresh(unmarked)
    assert marked.requires_honest_sign is True
    assert unmarked.requires_honest_sign is True


async def _seed_backfill_rows(
    session: AsyncSession,
    tenant: Tenant,
    seller: Seller,
) -> dict[int, Product]:
    rows: dict[int, Product] = {}
    cards = [
        _card(191, subject_id=101, need_kiz=False),
        _card(192, subject_id=102, need_kiz=True),
        _card(193, subject_id=None, need_kiz=False),
        _card(194, subject_id=999, need_kiz=False),
        _card(195, subject_id=102, need_kiz=None),
        _card(196, subject_id=101, need_kiz=False),
    ]
    for card in cards:
        nm_id = int(card["nmID"])
        product = Product(
            tenant_id=tenant.id,
            seller_id=seller.id,
            name=f"Product {nm_id}",
            sku_code=f"WMS658-{nm_id}",
            wb_nm_id=nm_id,
            wb_chrt_id=nm_id * 10,
            wb_barcode=f"BAR-{nm_id}",
            wb_size="M",
            requires_honest_sign=False,
            fbs_stock_limit=nm_id,
        )
        session.add(product)
        await session.flush()
        rows[nm_id] = product
        raw = dict(card)
        if nm_id == 196:
            raw.pop("nmID", None)
        session.add(
            SellerWildberriesImportedCard(
                tenant_id=tenant.id,
                seller_id=seller.id,
                nm_id=nm_id,
                vendor_code=f"WMS658-{nm_id}",
                title=f"Product {nm_id}",
                raw_json=raw,
            )
        )
    await session.commit()
    return rows


@pytest.mark.asyncio
async def test_c19_backfill_dry_run_reports_evidence_and_missing_data_without_writes(
    db_session: AsyncSession,
) -> None:
    tenant, seller = await _scope(db_session)
    products = await _seed_backfill_rows(db_session, tenant, seller)
    service = _marking_service()
    before = {nm: row.requires_honest_sign for nm, row in products.items()}

    report = await service.build_backfill_plan(
        db_session, tenant.id, seller.id, catalog=_catalog(service)
    )

    assert [row["nmID"] for row in report["apply"]] == [191, 192]
    assert {row["reason"] for row in report["apply"]} == {"clothing_parent", "needKiz"}
    assert all(
        {"product_id", "tenant_id", "seller_id", "nmID", "subjectID", "reason", "before"}
        <= row.keys()
        for row in report["apply"]
    )
    assert {row["nmID"]: row["missing"] for row in report["skipped"]} == {
        193: "subjectID",
        194: "subject_catalog_link",
        195: "needKiz",
        196: "nmID",
    }
    for nm, row in products.items():
        await db_session.refresh(row)
        assert row.requires_honest_sign is before[nm]
        assert row.fbs_stock_limit == nm
    assert await db_session.scalar(select(func.count(MarkingCode.id))) == 0
    assert await db_session.scalar(select(func.count(MarkingPool.id))) == 0


@pytest.mark.asyncio
async def test_c20_backfill_apply_rejects_stale_plan_and_changes_only_false_to_true(
    db_session: AsyncSession,
) -> None:
    tenant, seller = await _scope(db_session)
    products = await _seed_backfill_rows(db_session, tenant, seller)
    service = _marking_service()
    stale = await service.build_backfill_plan(
        db_session, tenant.id, seller.id, catalog=_catalog(service)
    )
    card = await db_session.scalar(
        select(SellerWildberriesImportedCard).where(
            SellerWildberriesImportedCard.nm_id == 191
        )
    )
    assert card is not None and card.raw_json is not None
    card.raw_json = {**card.raw_json, "subjectID": 102, "needKiz": False}
    await db_session.commit()

    with pytest.raises(service.BackfillPlanChanged):
        await service.apply_backfill_plan(
            db_session,
            tenant.id,
            seller.id,
            catalog=_catalog(service),
            fingerprint=stale["fingerprint"],
            product_ids=[row["product_id"] for row in stale["apply"]],
        )
    assert all(not row.requires_honest_sign for row in products.values())

    fresh = await service.build_backfill_plan(
        db_session, tenant.id, seller.id, catalog=_catalog(service)
    )
    before_other_fields = {
        nm: (row.name, row.sku_code, row.wb_barcode, row.fbs_stock_limit)
        for nm, row in products.items()
    }
    applied = await service.apply_backfill_plan(
        db_session,
        tenant.id,
        seller.id,
        catalog=_catalog(service),
        fingerprint=fresh["fingerprint"],
        product_ids=[row["product_id"] for row in fresh["apply"]],
    )
    repeated = await service.apply_backfill_plan(
        db_session,
        tenant.id,
        seller.id,
        catalog=_catalog(service),
        fingerprint=fresh["fingerprint"],
        product_ids=[row["product_id"] for row in fresh["apply"]],
    )

    assert applied["changed_product_ids"] == [row["product_id"] for row in fresh["apply"]]
    assert repeated["changed_product_ids"] == []
    selected = {uuid.UUID(row["product_id"]) for row in fresh["apply"]}
    for nm, row in products.items():
        await db_session.refresh(row)
        assert row.requires_honest_sign is (row.id in selected)
        assert (
            row.name,
            row.sku_code,
            row.wb_barcode,
            row.fbs_stock_limit,
        ) == before_other_fields[nm]
    assert await db_session.scalar(select(func.count(MarkingCode.id))) == 0
    assert await db_session.scalar(select(func.count(MarkingPool.id))) == 0
