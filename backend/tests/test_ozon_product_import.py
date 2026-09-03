"""Импорт карточек Ozon: габариты для хранения и штрихкод для сканера.

Числа в фикстуре — не выдумка: это ответ живого кабинета «ИП Горячкина Т.И.»
на читающий вызов `/v4/product/info/attributes` 03.09.2026. Обе карточки
кабинета отдают габариты в миллиметрах, вес в граммах и собственный штрихкод
Ozon вида ``OZN<sku>``.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal, engine
from app.models import Base
from app.models.product import Product
from app.models.product_marketplace_link import ProductMarketplaceLink
from app.models.seller import Seller
from app.models.tenant import Tenant
from app.services import ozon_product_import_service as import_svc
from app.services import scan_resolver_service as scan_svc
from app.services.marketplace_provider import FakeMarketplaceTransport, OzonMarketplaceProvider

GLASSES_CARD: dict[str, Any] = {
    "id": 6204279711,
    "sku": 5680762790,
    "offer_id": "OZ862006269Очки1БЗрозовыйAV",
    "name": "Очки солнцезащитные модные кошачий глаз тренд 2026",
    "barcode": "OZN5680762790",
    "barcodes": ["OZN5680762790"],
    "height": 50,
    "depth": 200,
    "width": 90,
    "dimension_unit": "mm",
    "weight": 100,
    "weight_unit": "g",
}
BAG_CARD: dict[str, Any] = {
    "id": 6149741392,
    "sku": 5632831320,
    "offer_id": "OZ562479787Sum1AVblack",
    "name": "Сумка через плечо багет модная 2026",
    "barcode": "OZN5632831320",
    "barcodes": ["OZN5632831320"],
    "height": 100,
    "depth": 290,
    "width": 170,
    "dimension_unit": "mm",
    "weight": 470,
    "weight_unit": "g",
}


@pytest_asyncio.fixture()
async def db_session() -> AsyncSession:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    async with SessionLocal() as session:
        yield session


async def _seed(
    db_session: AsyncSession, *, external_sku: str = "5680762790"
) -> tuple[Tenant, Seller, Product]:
    tenant = Tenant(name="Ozon import", slug=f"ozon-import-{uuid.uuid4().hex[:8]}")
    seller = Seller(tenant=tenant, name="Seller")
    product = Product(
        tenant=tenant, seller=seller, name="Очки", sku_code=f"sku-{uuid.uuid4().hex[:8]}"
    )
    db_session.add_all([tenant, seller, product])
    await db_session.flush()
    db_session.add(
        ProductMarketplaceLink(
            tenant_id=tenant.id,
            seller_id=seller.id,
            product_id=product.id,
            marketplace="ozon",
            external_sku=external_sku,
        )
    )
    await db_session.commit()
    return tenant, seller, product


def _provider(cards: list[dict[str, Any]]) -> OzonMarketplaceProvider:
    return OzonMarketplaceProvider(
        transport=FakeMarketplaceTransport(
            endpoint_responses={
                import_svc.PRODUCT_ATTRIBUTES_PATH: {"result": cards, "last_id": ""}
            }
        )
    )


async def test_import_fills_dimensions_so_storage_can_be_charged(
    db_session: AsyncSession,
) -> None:
    """Без габаритов литро-дни нулевые и строка за хранение не создаётся вовсе."""
    tenant, seller, product = await _seed(db_session)

    result = await import_svc.import_ozon_product_cards(
        db_session,
        tenant.id,
        seller.id,
        _provider([GLASSES_CARD]),
        client_id="c",
        api_key="k",
    )

    await db_session.refresh(product)
    assert result.links_matched == 1
    assert result.dimensions_applied == 1
    assert (product.length_mm, product.width_mm, product.height_mm) == (200, 90, 50)
    assert product.weight_g == 100
    # Наша же формула: миллиметры в куб делить на миллион.
    assert product.volume_liters == 0.9
    assert product.dimensions_source == "ozon"


async def test_import_fills_the_product_id_that_stock_publishing_needs(
    db_session: AsyncSession,
) -> None:
    """`product_id` и `sku` у Ozon — разные числа; поле под product_id пустовало."""
    tenant, seller, _product = await _seed(db_session)

    result = await import_svc.import_ozon_product_cards(
        db_session,
        tenant.id,
        seller.id,
        _provider([GLASSES_CARD]),
        client_id="c",
        api_key="k",
    )

    link = (
        await db_session.execute(
            ProductMarketplaceLink.__table__.select().where(
                ProductMarketplaceLink.tenant_id == tenant.id
            )
        )
    ).one()
    assert result.product_ids_applied == 1
    assert link.external_product_id == "6204279711"
    assert link.external_barcodes == ["OZN5680762790"]


async def test_import_never_overwrites_a_measurement_a_human_chose(
    db_session: AsyncSession,
) -> None:
    tenant, seller, product = await _seed(db_session)
    product.length_mm, product.width_mm, product.height_mm = 111, 222, 333
    product.volume_liters = 8.2
    product.dimensions_source = "manual"
    await db_session.commit()

    result = await import_svc.import_ozon_product_cards(
        db_session,
        tenant.id,
        seller.id,
        _provider([GLASSES_CARD]),
        client_id="c",
        api_key="k",
    )

    await db_session.refresh(product)
    assert result.skipped_manual_dimensions == 1
    assert result.dimensions_applied == 0
    assert product.dimensions_source == "manual"
    assert (product.length_mm, product.width_mm, product.height_mm) == (111, 222, 333)


async def test_unknown_units_are_skipped_rather_than_guessed(
    db_session: AsyncSession,
) -> None:
    """Ошибиться в габаритах дороже, чем не заполнить их."""
    tenant, seller, product = await _seed(db_session)
    card = {**GLASSES_CARD, "dimension_unit": "parrots"}

    result = await import_svc.import_ozon_product_cards(
        db_session,
        tenant.id,
        seller.id,
        _provider([card]),
        client_id="c",
        api_key="k",
    )

    await db_session.refresh(product)
    assert result.skipped_unknown_units == 1
    assert result.dimensions_applied == 0
    assert product.volume_liters is None


async def test_card_without_a_link_is_reported_and_never_creates_a_product(
    db_session: AsyncSession,
) -> None:
    tenant, seller, _product = await _seed(db_session)

    result = await import_svc.import_ozon_product_cards(
        db_session,
        tenant.id,
        seller.id,
        _provider([GLASSES_CARD, BAG_CARD]),
        client_id="c",
        api_key="k",
    )

    assert result.cards_read == 2
    assert result.links_matched == 1
    assert result.unmatched_offer_ids == ["OZ562479787Sum1AVblack"]
    products = list(
        (await db_session.execute(Product.__table__.select())).mappings().all()
    )
    assert len(products) == 1


async def test_scanner_finds_the_product_by_the_ozon_barcode(
    db_session: AsyncSession,
) -> None:
    """Кладовщик подносит сканер к коробке с этикеткой OZN… и находит товар.

    До этого общий резолвер искал ровно по двум полям товара и отвечал
    «объект с таким кодом не найден», а поле под озоновские штрихкоды стояло
    пустым: ни одной записи, ни одного чтения.
    """
    tenant, seller, product = await _seed(db_session)
    await import_svc.import_ozon_product_cards(
        db_session,
        tenant.id,
        seller.id,
        _provider([GLASSES_CARD]),
        client_id="c",
        api_key="k",
    )

    match = await scan_svc.resolve_any_scan(db_session, tenant.id, "OZN5680762790")

    assert match.type == "product"
    assert match.id == product.id


async def test_scanner_still_finds_nothing_for_an_unknown_code(
    db_session: AsyncSession,
) -> None:
    tenant, seller, _product = await _seed(db_session)
    await import_svc.import_ozon_product_cards(
        db_session,
        tenant.id,
        seller.id,
        _provider([GLASSES_CARD]),
        client_id="c",
        api_key="k",
    )

    with pytest.raises(scan_svc.ScanResolverError) as caught:
        await scan_svc.resolve_any_scan(db_session, tenant.id, "OZN0000000000")
    assert caught.value.code == "scan_not_found"
