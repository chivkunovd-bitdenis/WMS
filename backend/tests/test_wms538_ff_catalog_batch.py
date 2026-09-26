"""WMS-538: /products/ff-catalog ронял Postgres у ArtMaks и «Империи».

Причина — сплошной IN по кортежам (seller_id, nm_id) на весь каталог тенанта:
у ArtMaks (55 313 товаров) и «Империи» (25 029) он превращался в список из
десятков тысяч пар и валил парсер Postgres (OperationalError: stack depth
limit exceeded). Похожие безлимитные IN нашлись и в соседних выборках той же
области (chrt_id для FBS-синка, product_id для привязок Ozon, nm_id для
каталога отдельного селлера) — все теперь читают порциями через
``catalog_service.chunked``.

Тест воспроизводит это на наборе заметно больше размера пачки и проверяет,
что порционная выборка находит ровно те же карточки/привязки, что и старый
одиночный запрос — то есть чтение порциями прозрачно для результата.
Настоящий сбой Postgres (упор в глубину стека парсера) в SQLite не
воспроизводится — там нет такого лимита, поэтому здесь проверяется
корректность склейки порций, а не сам крах. Регрессия на Postgres не
прогонялась: в проекте нет отдельного Postgres-контура для тестов.

Порционная выборка сама по себе аварию не закрыла: по замерам на бою
GET /products/ff-catalog без фильтра у ArtMaks и «Империи» всё равно занимал
11-16 с чистого CPU в единственном процессе uvicorn (на это время вставал
весь API), а следом падал в другом запросе лимитом psycopg на 65 535
параметров. Поэтому такой запрос без seller_id и search теперь отклоняется
сразу кодом 413 по лёгкому count(*) — это проверяет второй тест ниже.
"""

from __future__ import annotations

import time
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.models.product_marketplace_link import ProductMarketplaceLink
from app.models.seller import Seller
from app.models.seller_wildberries_imported_card import SellerWildberriesImportedCard
from app.models.tenant import Tenant
from app.services.catalog_service import ID_IN_BATCH_SIZE, chunked
from app.services.seller_wb_catalog_service import (
    _PAIR_IN_BATCH_SIZE,
    list_ff_catalog_rows,
    list_linked_wb_catalog_rows,
)


def test_chunked_splits_into_fixed_size_batches_with_trailing_remainder() -> None:
    """Базовая проверка примитива: ни одного элемента не теряется и не дублируется."""
    assert list(chunked([], 3)) == []
    assert list(chunked([1], 3)) == [[1]]
    assert list(chunked([1, 2, 3], 3)) == [[1, 2, 3]]
    assert list(chunked([1, 2, 3, 4], 3)) == [[1, 2, 3], [4]]
    assert list(chunked(range(7), 2)) == [[0, 1], [2, 3], [4, 5], [6]]


@pytest.mark.asyncio
async def test_ff_catalog_batched_card_lookup_matches_single_query_wms538(
    db_session: AsyncSession,
) -> None:
    tenant = Tenant(id=uuid.uuid4(), name="T538", slug=f"t538-{uuid.uuid4().hex[:8]}")
    seller = Seller(id=uuid.uuid4(), tenant_id=tenant.id, name="Seller538")

    # Больше обеих пачек разом: пар (seller_id, nm_id) — больше _PAIR_IN_BATCH_SIZE,
    # и скалярных id (product_id/chrt_id) — больше ID_IN_BATCH_SIZE. У обоих
    # получается неполная последняя пачка — самое частое место off-by-one.
    total = ID_IN_BATCH_SIZE + 200
    assert total > _PAIR_IN_BATCH_SIZE * 4

    def nm_id_for(i: int) -> int:
        return 1_000_000 + i

    products: list[Product] = []
    cards: list[SellerWildberriesImportedCard] = []
    links: list[ProductMarketplaceLink] = []
    for i in range(total):
        nm_id = nm_id_for(i)
        product = Product(
            # Детерминированный, монотонно растущий id: сортировка по id
            # в chunked(sorted(...)) совпадает с порядком заведения, и можно
            # предсказать, в какую пачку попадёт конкретный индекс.
            id=uuid.UUID(int=i + 1),
            tenant_id=tenant.id,
            seller_id=seller.id,
            name=f"Товар {i}",
            sku_code=f"SKU538-{i:05d}",
            wb_nm_id=nm_id,
            wb_vendor_code=f"VC-{i:05d}",
            wb_chrt_id=9_000_000 + i,
        )
        products.append(product)
        cards.append(
            SellerWildberriesImportedCard(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                seller_id=seller.id,
                nm_id=nm_id,
                vendor_code=f"VC-{i:05d}",
                title=f"Карточка {i}",
                raw_json={
                    "nmID": nm_id,
                    "vendorCode": f"VC-{i:05d}",
                    "subjectName": f"Категория {i}",
                    "sizes": [{"techSize": "M", "skus": [f"{2_000_000_000_000 + i}"]}],
                    "photos": [{"big": f"https://img.example/card-{i}.jpg"}],
                },
            )
        )
        links.append(
            ProductMarketplaceLink(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                seller_id=seller.id,
                product_id=product.id,
                marketplace="ozon",
                external_sku=f"OZ-{i:05d}",
            )
        )

    db_session.add_all([tenant, seller, *products, *cards, *links])
    await db_session.commit()

    # "Старое" поведение: один сплошной IN по всем парам разом — то, что на
    # проде валило Postgres. SQLite такой лимит парсера не знает, поэтому
    # запрос здесь просто служит эталоном для сравнения с порционным чтением.
    reference_stmt = select(SellerWildberriesImportedCard).where(
        SellerWildberriesImportedCard.tenant_id == tenant.id,
        tuple_(
            SellerWildberriesImportedCard.seller_id,
            SellerWildberriesImportedCard.nm_id,
        ).in_({(seller.id, nm_id_for(i)) for i in range(total)}),
    )
    reference_rows = (await db_session.execute(reference_stmt)).scalars().all()
    reference_by_nm = {int(c.nm_id): c.raw_json for c in reference_rows}
    assert len(reference_by_nm) == total  # sanity: ничего не потерялось и в самом наборе данных

    rows = await list_linked_wb_catalog_rows(db_session, tenant.id, seller_id=seller.id)
    assert len(rows) == total
    rows_by_nm = {r.wb_nm_id: r for r in rows}
    assert set(rows_by_nm) == set(reference_by_nm)

    # Ни один товар не остался без карточки и без привязки Ozon — если бы
    # порционная выборка теряла последнюю (неполную) пачку, здесь были бы None.
    assert all(r.wb_subject_name is not None for r in rows)
    assert all(r.ozon_sku is not None for r in rows)
    # Без сидированных FbsWarehouseBinding/FbsStockSyncItem синк-статус не
    # заполняется — проверяем, что порционный chrt_id-запрос не заводит его
    # ошибочно и не падает на количестве, пересекающем границу пачки.
    assert all(r.fbs_sync_status is None for r in rows)

    boundary_indices = sorted(
        {
            0,
            1,
            _PAIR_IN_BATCH_SIZE - 1,
            _PAIR_IN_BATCH_SIZE,
            ID_IN_BATCH_SIZE - 1,
            ID_IN_BATCH_SIZE,
            total - 1,
        }
    )
    for i in boundary_indices:
        nm_id = nm_id_for(i)
        row = rows_by_nm[nm_id]
        assert row.wb_subject_name == f"Категория {i}", i
        assert row.wb_primary_image_url == f"https://img.example/card-{i}.jpg", i
        assert row.wb_primary_barcode == str(2_000_000_000_000 + i), i
        assert row.wb_vendor_code == f"VC-{i:05d}", i
        assert row.ozon_sku == f"OZ-{i:05d}", i


@pytest.mark.asyncio
async def test_ff_catalog_rejects_huge_unscoped_tenant_with_413_wms538(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Без seller_id и search и с каталогом больше порога — сразу 413, без чтения каталога.

    С seller_id (или search) запрос по-прежнему проходит как раньше, даже если
    общий каталог тенанта больше порога — потолок считает область именно
    полного тенантного запроса, а не отфильтрованную выдачу.
    """
    monkeypatch.setattr("app.api.products.FF_CATALOG_MAX_UNSCOPED_PRODUCTS", 2)

    calls: list[tuple[object, ...]] = []

    async def spying_list_ff_catalog_rows(*args: object, **kwargs: object) -> object:
        calls.append((args, kwargs))
        return await list_ff_catalog_rows(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr("app.api.products.list_ff_catalog_rows", spying_list_ff_catalog_rows)

    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Big Cat Co",
            "slug": f"big-cat-{suffix}",
            "admin_email": f"big-cat-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200
    ah = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    seller = (await async_client.post("/sellers", headers=ah, json={"name": "Big Seller"})).json()
    sid = seller["id"]

    # 3 товара > патченный порог (2) — этого достаточно, чтобы сработал потолок.
    for i in range(3):
        created = await async_client.post(
            "/products",
            headers=ah,
            json={
                "name": f"Товар {i}",
                "sku_code": f"SKU538G-{suffix}-{i}",
                "length_mm": 10,
                "width_mm": 10,
                "height_mm": 10,
                "seller_id": sid,
            },
        )
        assert created.status_code == 200, created.text

    too_large = await async_client.get("/products/ff-catalog", headers=ah)
    assert too_large.status_code == 413, too_large.text
    assert too_large.json()["detail"] == "catalog_too_large"
    assert calls == []  # каталог при отказе вообще не читался

    scoped = await async_client.get(f"/products/ff-catalog?seller_id={sid}", headers=ah)
    assert scoped.status_code == 200, scoped.text
    assert len(scoped.json()) == 3
    assert len(calls) == 1  # отфильтрованный по продавцу запрос каталог всё же читает
