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
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.models.product_marketplace_link import ProductMarketplaceLink
from app.models.seller import Seller
from app.models.tenant import Tenant
from app.services import catalog_service as catalog_svc
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


async def test_card_without_a_match_becomes_a_product_of_its_own(
    db_session: AsyncSession,
) -> None:
    """WMS-347: селлер ввёл ключи — товары кабинета приехали сами.

    Раньше импорт принципиально не заводил товары, и каталог у чисто
    озоновского продавца оставался пустым, пока оператор не наберёт его руками.
    """
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
    assert result.products_created == 1
    assert result.links_created == 1
    assert result.unmatched_offer_ids == []
    products = list((await db_session.execute(Product.__table__.select())).mappings().all())
    assert len(products) == 2
    created = next(row for row in products if row["sku_code"] == "OZ562479787Sum1AVblack")
    assert created["name"] == "Сумка через плечо багет модная 2026"
    assert created["seller_id"] == seller.id
    # Габариты приезжают тем же проходом: без них литро-дни нулевые.
    assert (created["length_mm"], created["width_mm"], created["height_mm"]) == (290, 170, 100)
    assert created["weight_g"] == 470
    link = (
        await db_session.execute(
            ProductMarketplaceLink.__table__.select().where(
                ProductMarketplaceLink.product_id == created["id"]
            )
        )
    ).one()
    # Пометка «товар озоновский» — это и есть привязка, отдельного флага не заводим.
    assert link.marketplace == "ozon"
    assert link.external_sku == "5632831320"
    assert link.external_product_id == "6149741392"


async def test_second_run_does_not_create_the_same_product_twice(
    db_session: AsyncSession,
) -> None:
    tenant, seller, _product = await _seed(db_session)
    for _ in range(2):
        result = await import_svc.import_ozon_product_cards(
            db_session,
            tenant.id,
            seller.id,
            _provider([BAG_CARD]),
            client_id="c",
            api_key="k",
        )

    assert result.products_created == 0
    assert result.links_matched == 1
    products = list((await db_session.execute(Product.__table__.select())).mappings().all())
    assert len(products) == 2


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


async def _seed_without_link(db_session: AsyncSession) -> tuple[Tenant, Seller]:
    tenant = Tenant(name="Ozon match", slug=f"ozon-match-{uuid.uuid4().hex[:8]}")
    seller = Seller(tenant=tenant, name="Seller")
    db_session.add_all([tenant, seller])
    await db_session.commit()
    return tenant, seller


async def _add_product(
    db_session: AsyncSession,
    tenant: Tenant,
    seller: Seller,
    *,
    sku_code: str,
    wb_nm_id: int | None = None,
    wb_vendor_code: str | None = None,
    wb_barcode: str | None = None,
) -> Product:
    product = Product(
        tenant_id=tenant.id,
        seller_id=seller.id,
        name=sku_code,
        sku_code=sku_code,
        wb_nm_id=wb_nm_id,
        wb_vendor_code=wb_vendor_code,
        wb_barcode=wb_barcode,
    )
    db_session.add(product)
    await db_session.commit()
    return product


async def test_link_is_computed_from_the_article_assembled_by_the_transfer(
    db_session: AsyncSession,
) -> None:
    """WMS-344: `OZ` + nmID + артикул продавца — оба поля разом, не одно.

    Сверяем не разбором чужой строки, а сборкой своей: складываем ожидаемый
    артикул из полей нашего товара и сравниваем целиком. Тогда не нужно гадать,
    где кончается nmID и начинается артикул продавца.
    """
    tenant, seller = await _seed_without_link(db_session)
    product = await _add_product(
        db_session,
        tenant,
        seller,
        sku_code="OCHKI-1",
        wb_nm_id=862006269,
        wb_vendor_code="Очки1БЗрозовыйAV",
    )

    result = await import_svc.import_ozon_product_cards(
        db_session, tenant.id, seller.id, _provider([GLASSES_CARD]), client_id="c", api_key="k"
    )

    assert result.links_created == 1
    assert result.products_created == 0
    link = (
        await db_session.execute(
            ProductMarketplaceLink.__table__.select().where(
                ProductMarketplaceLink.tenant_id == tenant.id
            )
        )
    ).one()
    assert link.product_id == product.id


async def test_link_is_computed_from_the_seller_article(db_session: AsyncSession) -> None:
    """Артикул продавца уникален внутри продавца — совпадение однозначно."""
    tenant, seller = await _seed_without_link(db_session)
    product = await _add_product(db_session, tenant, seller, sku_code="OZ862006269Очки1БЗрозовыйAV")

    result = await import_svc.import_ozon_product_cards(
        db_session, tenant.id, seller.id, _provider([GLASSES_CARD]), client_id="c", api_key="k"
    )

    assert result.products_created == 0
    link = (
        await db_session.execute(
            ProductMarketplaceLink.__table__.select().where(
                ProductMarketplaceLink.tenant_id == tenant.id
            )
        )
    ).one()
    assert link.product_id == product.id


async def test_barcode_picks_the_right_size_out_of_a_dozen_cards(
    db_session: AsyncSession,
) -> None:
    """WMS-345: у каждого размера свой штрихкод, и он один и тот же на обеих площадках.

    Артикул размера не содержит, поэтому по нему одна карточка Ozon смотрит на
    все размеры сразу. Штрихкод различает их без единой догадки.
    """
    tenant, seller = await _seed_without_link(db_session)
    sizes = ["S", "M", "L"]
    products = [
        await _add_product(
            db_session,
            tenant,
            seller,
            sku_code=f"DRESS/{size}",
            wb_nm_id=170981862,
            wb_vendor_code="Платье1",
            wb_barcode=f"463001234567{index}",
        )
        for index, size in enumerate(sizes)
    ]
    card = {
        **BAG_CARD,
        "offer_id": "OZ170981862Платье1",
        "barcodes": ["OZN5632831320", "4630012345671"],
    }

    result = await import_svc.import_ozon_product_cards(
        db_session, tenant.id, seller.id, _provider([card]), client_id="c", api_key="k"
    )

    assert result.products_created == 0
    link = (
        await db_session.execute(
            ProductMarketplaceLink.__table__.select().where(
                ProductMarketplaceLink.tenant_id == tenant.id
            )
        )
    ).one()
    assert link.product_id == products[1].id


async def test_ambiguous_article_links_nothing_and_creates_nothing(
    db_session: AsyncSession,
) -> None:
    """WMS-345: один артикул на дюжину размеров — связку не ставим вовсе.

    Ни угадать нужный размер, ни завести дубль рядом с настоящими карточками
    нельзя: и то и другое сводит вместе чужие остатки. Карточка уходит оператору
    на ручное объединение.
    """
    tenant, seller = await _seed_without_link(db_session)
    for size in ("S", "M"):
        await _add_product(
            db_session,
            tenant,
            seller,
            sku_code=f"DRESS/{size}",
            wb_nm_id=170981862,
            wb_vendor_code="Платье1",
        )
    card = {**BAG_CARD, "offer_id": "OZ170981862Платье1"}

    result = await import_svc.import_ozon_product_cards(
        db_session, tenant.id, seller.id, _provider([card]), client_id="c", api_key="k"
    )

    assert result.links_created == 0
    assert result.products_created == 0
    assert result.unmatched_offer_ids == ["OZ170981862Платье1"]
    products = list((await db_session.execute(Product.__table__.select())).mappings().all())
    assert len(products) == 2


async def test_ozon_own_barcode_never_matches_and_never_blocks_the_next_signal(
    db_session: AsyncSession,
) -> None:
    """`OZN<sku>` выдан самим Ozon: в карточке WMS такого кода быть не может."""
    assert import_svc.card_matchable_barcodes(GLASSES_CARD) == []
    tenant, seller = await _seed_without_link(db_session)
    product = await _add_product(
        db_session,
        tenant,
        seller,
        sku_code="OCHKI-1",
        wb_nm_id=862006269,
        wb_vendor_code="Очки1БЗрозовыйAV",
        wb_barcode="OZN5680762790",
    )

    result = await import_svc.import_ozon_product_cards(
        db_session, tenant.id, seller.id, _provider([GLASSES_CARD]), client_id="c", api_key="k"
    )

    assert result.links_created == 1
    link = (
        await db_session.execute(
            ProductMarketplaceLink.__table__.select().where(
                ProductMarketplaceLink.tenant_id == tenant.id
            )
        )
    ).one()
    assert link.product_id == product.id


async def test_photo_from_the_ozon_card_is_readable_by_the_screens(
    db_session: AsyncSession,
) -> None:
    """WMS-343: у озоновского товара было пусто на пятнадцати экранах.

    Фото берётся из снапшота карточки Wildberries, которого у такого товара нет
    вовсе. Кладовщик сверяет товар глазами по картинке, поэтому пустой квадрат
    здесь — не косметика.
    """
    tenant, seller, product = await _seed(db_session)
    card = {**GLASSES_CARD, "primary_image": "https://cdn1.ozone.ru/s3/glasses/big.jpg"}

    result = await import_svc.import_ozon_product_cards(
        db_session, tenant.id, seller.id, _provider([card]), client_id="c", api_key="k"
    )

    assert result.images_applied == 1
    links = await catalog_svc.list_ozon_product_links(db_session, tenant.id, {product.id})
    assert (
        catalog_svc.ozon_link_primary_image_url(links[product.id])
        == "https://cdn1.ozone.ru/s3/glasses/big.jpg"
    )
    by_product = await catalog_svc.load_ozon_primary_image_urls(db_session, tenant.id, {product.id})
    assert by_product == {product.id: "https://cdn1.ozone.ru/s3/glasses/big.jpg"}


async def test_photo_falls_back_to_the_first_image_of_the_card() -> None:
    """Главное фото не выбрано — главным считается первое изображение карточки."""
    card = {"images": ["https://a/1.jpg", "https://a/2.jpg"]}
    assert import_svc.card_primary_image_url(card) == "https://a/1.jpg"
    assert import_svc.card_primary_image_url({}) is None


async def test_last_free_size_is_not_a_disambiguation(db_session: AsyncSession) -> None:
    """Разобранные размеры не делают признак однозначным.

    Если считать занятость до подсчёта кандидатов, у модели с двумя размерами
    хватит одной разобранной карточки, чтобы вторая «однозначно» легла на
    оставшийся размер. Признак при этом размеров по-прежнему не различает —
    получилась бы догадка с чужим остатком на складе.
    """
    tenant, seller = await _seed_without_link(db_session)
    small, large = [
        await _add_product(
            db_session,
            tenant,
            seller,
            sku_code=f"DRESS/{size}",
            wb_nm_id=170981862,
            wb_vendor_code="Платье1",
        )
        for size in ("S", "L")
    ]
    db_session.add(
        ProductMarketplaceLink(
            tenant_id=tenant.id,
            seller_id=seller.id,
            product_id=small.id,
            marketplace="ozon",
            external_sku="9999999999",
            external_offer_id="OZ170981862Платье1-S",
        )
    )
    await db_session.commit()
    card = {**BAG_CARD, "offer_id": "OZ170981862Платье1"}

    result = await import_svc.import_ozon_product_cards(
        db_session, tenant.id, seller.id, _provider([card]), client_id="c", api_key="k"
    )

    assert result.links_created == 0
    assert result.products_created == 0
    assert result.unmatched_offer_ids == ["OZ170981862Платье1"]
    links = list(
        (await db_session.execute(ProductMarketplaceLink.__table__.select())).mappings().all()
    )
    assert [row["product_id"] for row in links] == [small.id]
    assert large.id not in {row["product_id"] for row in links}
