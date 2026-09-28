"""Scanner unit placement, source ownership and durable retries."""

import asyncio
import uuid

import pytest
from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models.inbound_intake import InboundIntakeBoxLine, InboundIntakeDistributionLine
from app.models.inventory_balance import InventoryBalance
from app.models.product import Product
from app.models.product_barcode import ProductBarcode
from app.models.product_marketplace_link import ProductMarketplaceLink
from app.models.seller import Seller
from app.models.seller_wildberries_imported_card import SellerWildberriesImportedCard
from app.services import inbound_intake_service as intake
from app.services import warehouse_map_service as warehouse_map
from app.services.catalog_service import create_product, create_warehouse
from app.services.sorting_scan_service import matching_scan_lines, scan_product
from tests.test_inbound_intake_service_sort_be01 import _auth_ids, _mixed_sorting_request


async def seed(client, *, loose=0, boxed=3):
    tenant, actor = await _auth_ids(client)
    req, product, box, cell, other_cell = await _mixed_sorting_request(
        client, tenant, actor, loose_qty=loose, box_qty=boxed
    )
    async with SessionLocal() as session:
        item = await session.get(Product, product)
        item.wb_barcode = "WMS550-SKU"
        request = await intake.get_request(session, tenant, req)
        warehouse = request.warehouse_id
        await session.commit()
    args = dict(tenant_id=tenant, actor_user_id=actor, warehouse_id=warehouse,
                inbound_request_id=req, cell_id=cell, barcode="WMS550-SKU")
    return args, product, box, other_cell


async def scan(args, operation=None, **overrides):
    async with SessionLocal() as session:
        return await scan_product(session, **(args | overrides),
                                  operation_id=operation or uuid.uuid4())


async def qty(product, cell):
    async with SessionLocal() as session:
        return await session.scalar(select(func.coalesce(func.sum(InventoryBalance.quantity), 0))
                                    .where(InventoryBalance.product_id == product,
                                           InventoryBalance.storage_location_id == cell))


@pytest.mark.asyncio
async def test_box_unit_scan_repeat_and_completion(async_client):
    args, product, box, other_cell = await seed(async_client, boxed=2)
    op = uuid.uuid4()
    assert (await scan(args, op))["moved_qty"] == 1
    assert await scan(args, op) == {"id": str(op), "moved_qty": 1, "reload": True}
    with pytest.raises(warehouse_map.WarehouseMapError, match="operation_conflict"):
        await scan(args, op, cell_id=other_cell)
    assert await qty(product, args["cell_id"]) == 1
    async with SessionLocal() as session:
        content = await session.scalar(select(InboundIntakeBoxLine).where(
            InboundIntakeBoxLine.box_id == box))
        assert content.posted_qty == 1
    await scan(args)
    assert await qty(product, args["cell_id"]) == 2
    with pytest.raises(warehouse_map.WarehouseMapError, match="nothing_to_move"):
        await scan(args)
    assert await scan(args, op) == {"id": str(op), "moved_qty": 1, "reload": True}
    async with SessionLocal() as session:
        request = await intake.get_request(session, args["tenant_id"], args["inbound_request_id"])
        assert request.lines[0].posted_qty == 2
        assert request.status == "done"
        receipts = await session.scalar(select(func.count())
                                        .select_from(InboundIntakeDistributionLine).where(
                                            InboundIntakeDistributionLine.request_id == request.id))
        assert receipts == 2


@pytest.mark.asyncio
async def test_scan_loose_into_selected_container_and_retry(async_client):
    args, product, _box, _ = await seed(async_client, loose=2, boxed=0)
    async with SessionLocal() as session:
        target = await warehouse_map.create_sorting_object(
            session, args["tenant_id"], args["warehouse_id"], kind="box",
            inbound_request_id=args["inbound_request_id"],
        )
        target_id = uuid.UUID(target["id"])
        await warehouse_map.place_sorting_object(
            session, tenant_id=args["tenant_id"], warehouse_id=args["warehouse_id"],
            actor_user_id=args["actor_user_id"], kind="box", object_id=target_id,
            cell_id=args["cell_id"], to_id=None, quantity=None,
            inbound_request_id=args["inbound_request_id"],
        )
    op = uuid.uuid4()
    result = await scan(args, op, to_id=target_id)
    assert result["reload"] is False
    assert result["remaining_qty"] == 1
    assert result["product_id"] == str(product)
    assert result["target_holder"] == f"obj:{target_id}"
    async with SessionLocal() as session:
        target_balance = await session.get(InventoryBalance, uuid.UUID(result["target_id"]))
        source_balance = await session.get(InventoryBalance, uuid.UUID(result["source_id"]))
        assert target_balance.quantity == source_balance.quantity == 1
        assert target_balance.container_id == target_id
    await scan(args, op, to_id=target_id)
    await scan(args, to_id=target_id)
    assert await qty(product, args["cell_id"]) == 2
    with pytest.raises(warehouse_map.WarehouseMapError, match="already_in_target"):
        await scan(args, to_id=target_id)


@pytest.mark.asyncio
async def test_multiple_sources_are_not_guessed(async_client):
    args, product, _, _ = await seed(async_client, loose=2, boxed=2)
    with pytest.raises(warehouse_map.WarehouseMapError, match="ambiguous_source"):
        await scan(args)
    assert await qty(product, args["cell_id"]) == 0


@pytest.mark.asyncio
async def test_wrong_document_barcode_and_tenant_cannot_consume(async_client):
    args, product, _, _ = await seed(async_client)
    with pytest.raises(warehouse_map.WarehouseMapError, match="product_not_on_request"):
        await scan(args, barcode="NOT-ON-DOCUMENT")
    with pytest.raises(warehouse_map.WarehouseMapError, match="inbound_request_not_found"):
        await scan(args, tenant_id=uuid.uuid4())
    assert await qty(product, args["cell_id"]) == 0


@pytest.mark.asyncio
async def test_two_scanners_cannot_spend_last_unit_twice(async_client):
    args, product, _, _ = await seed(async_client, boxed=1)
    results = await asyncio.gather(scan(args), scan(args), return_exceptions=True)
    assert sum(isinstance(result, dict) for result in results) == 1
    assert await qty(product, args["cell_id"]) == 1


@pytest.mark.asyncio
async def test_saved_variant_alternative_and_primary_share_stock(async_client):
    args, product, _, _ = await seed(async_client, loose=2, boxed=0)
    async with SessionLocal() as session:
        item = await session.get(Product, product)
        seller = Seller(tenant_id=item.tenant_id, name="WMS556")
        other_seller = Seller(tenant_id=item.tenant_id, name="WMS556 other")
        session.add_all([seller, other_seller])
        await session.flush()
        item.seller_id = seller.id
        item.wb_nm_id = 556
        item.wb_chrt_id = 50
        session.add(SellerWildberriesImportedCard(
            tenant_id=item.tenant_id, seller_id=item.seller_id, nm_id=556,
            raw_json={"sizes": [
                {"chrtID": 50, "skus": ["WMS550-SKU", "2039751597840"]},
                {"chrtID": 52, "skus": ["OTHER-SIZE"]},
            ]},
        ))
        session.add(SellerWildberriesImportedCard(
            tenant_id=item.tenant_id, seller_id=other_seller.id, nm_id=556,
            raw_json={"sizes": [{"chrtID": 50, "skus": ["OTHER-SELLER"]}]},
        ))
        await session.commit()
    with pytest.raises(warehouse_map.WarehouseMapError, match="product_not_on_request"):
        await scan(args, barcode="OTHER-SIZE")
    with pytest.raises(warehouse_map.WarehouseMapError, match="product_not_on_request"):
        await scan(args, barcode="OTHER-SELLER")
    op = uuid.uuid4()
    assert (await scan(args, op, barcode="2039751597840"))["moved_qty"] == 1
    assert (await scan(args, op, barcode="2039751597840"))["reload"] is True
    await scan(args)
    assert await qty(product, args["cell_id"]) == 2
    async with SessionLocal() as session:
        assert (await session.get(Product, product)).wb_barcode == "WMS550-SKU"


# WMS-578 review (P2-4): sorting used to resolve a scan only against
# product.wb_barcode and the WB card's declared per-size skus, missing
# everything else receiving's own document-scoped index already accepts --
# extra WB barcodes (product_barcodes, WMS-535), Ozon barcodes, the WMS
# article and case-insensitive matching. A product sold only on Ozon (no
# wb_barcode/wb_nm_id) could never be sorted by scan at all.


@pytest.mark.asyncio
async def test_wms578_extra_wb_barcode_from_product_barcodes_sorts_case_insensitively(
    async_client,
):
    args, product, _box, _ = await seed(async_client, loose=2, boxed=0)
    async with SessionLocal() as session:
        item = await session.get(Product, product)
        seller = Seller(tenant_id=item.tenant_id, name="WMS578")
        session.add(seller)
        await session.flush()
        item.seller_id = seller.id
        request = await intake.get_request(session, args["tenant_id"], args["inbound_request_id"])
        request.seller_id = seller.id
        session.add(ProductBarcode(
            tenant_id=item.tenant_id, seller_id=seller.id, product_id=item.id,
            barcode="EXTRA-2039751597840", source="wb",
        ))
        await session.commit()
    op = uuid.uuid4()
    # Сканер прочитал штрихкод строчными — приёмка такой уже принимает (без
    # учёта регистра), сортировка должна тоже.
    assert (await scan(args, op, barcode="extra-2039751597840"))["moved_qty"] == 1
    await scan(args)  # второй экземпляр — прежним основным ШК WB, из args по умолчанию
    assert await qty(product, args["cell_id"]) == 2


@pytest.mark.asyncio
async def test_wms578_wms_article_sku_code_sorts(async_client):
    args, product, _box, _ = await seed(async_client, loose=1, boxed=0)
    async with SessionLocal() as session:
        item = await session.get(Product, product)
        sku_code = item.sku_code
    assert (await scan(args, barcode=sku_code))["moved_qty"] == 1
    assert await qty(product, args["cell_id"]) == 1


@pytest.mark.asyncio
async def test_wms578_ozon_only_product_sorts_by_ozon_barcode(async_client):
    args, product, _box, _ = await seed(async_client, loose=1, boxed=0)
    async with SessionLocal() as session:
        item = await session.get(Product, product)
        seller = Seller(tenant_id=item.tenant_id, name="WMS578 Ozon")
        session.add(seller)
        await session.flush()
        item.seller_id = seller.id
        # Товар только на Ozon: нет WB-штрихкода и карточки WB вовсе.
        item.wb_barcode = None
        item.wb_nm_id = None
        request = await intake.get_request(session, args["tenant_id"], args["inbound_request_id"])
        request.seller_id = seller.id
        session.add(ProductMarketplaceLink(
            tenant_id=item.tenant_id, seller_id=seller.id, product_id=item.id,
            marketplace="ozon", external_product_id="777001",
            external_offer_id="OFFER-578", external_sku="OZ-578",
            external_barcodes=["OZONBAR-578"],
        ))
        await session.commit()
    assert (await scan(args, barcode="OZONBAR-578"))["moved_qty"] == 1
    assert await qty(product, args["cell_id"]) == 1


@pytest.mark.asyncio
async def test_wms578_primary_wb_barcode_still_sorts_case_insensitively(async_client):
    args, product, _box, _ = await seed(async_client, loose=1, boxed=0)
    # Прежний основной ШК WB по-прежнему раскладывается — включая другой
    # регистр, которого раньше прямое сравнение не прощало.
    assert (await scan(args, barcode="wms550-sku"))["moved_qty"] == 1
    assert await qty(product, args["cell_id"]) == 1


@pytest.mark.asyncio
async def test_wms578_ambiguous_shared_barcode_across_two_products(async_client):
    """Один и тот же штрихкод у двух товаров документа — как у приёмки (barcode_ambiguous).

    Штрихкод WB одного товара документа совпадает с артикулом WMS другого —
    `product_barcodes` не участвует (там штрихкод уникален на продавца, такое
    совпадение там технически невозможно), совпадение поперёк разных полей.
    """
    tenant, _actor = await _auth_ids(async_client)
    async with SessionLocal() as session:
        wh = await create_warehouse(
            session, tenant, name="W578A", code=f"w578a-{uuid.uuid4().hex[:6]}",
        )
        p1 = await create_product(
            session, tenant, name="P1", sku_code=f"SKU1-{uuid.uuid4().hex[:6]}",
            length_mm=10, width_mm=10, height_mm=10, wb_barcode="SHARED-578", commit=False,
        )
        p2 = await create_product(session, tenant, name="P2", sku_code="SHARED-578",
                                  length_mm=10, width_mm=10, height_mm=10, commit=False)
        await session.flush()
        req = await intake.create_request(session, tenant, warehouse_id=wh.id)
        await intake.add_line(session, tenant, req.id, product_id=p1.id, expected_qty=1)
        await intake.add_line(session, tenant, req.id, product_id=p2.id, expected_qty=1)
        request_id = req.id
    async with SessionLocal() as session:
        # Свежая сессия: у исходной `.lines` не обновилась бы после второго
        # add_line в том же объекте (сессия не истекает объекты после commit).
        loaded = await intake.get_request(session, tenant, request_id)
        with pytest.raises(warehouse_map.WarehouseMapError, match="ambiguous_product"):
            await matching_scan_lines(session, loaded, "SHARED-578")
