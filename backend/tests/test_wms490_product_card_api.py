"""WMS-490 D1: карточка товара и фильтр по товару на карте склада.

Кусок D1 добавляет два серверных места, которыми пользуется вкладка
«Основное» (R4-R7) и вкладка «Расположение» (R10) карточки товара:

- ``GET /products/{product_id}/card`` — не считает ничего заново: строка
  собирается тем же сборщиком, что строка каталога ФФ
  (``_enrich_linked_products`` + ``_ff_catalog_out_rows``), к ней добавлены
  только габариты/вес товара и список складов, где он физически лежит
  (R17: не дублировать вычисляемую величину вторым способом).
- ``GET /warehouses/{warehouse_id}/map?product_id=`` — та же карта склада,
  что раздел «Ячейки», но с ней остаются только строки и контейнеры этого
  товара; без параметра ответ не меняется.

Проверки здесь — часть C1-C5, C9, C18 из docs/requirements/WMS-490.md,
покрывающая именно эти два эндпоинта (вкладки фронта проверяют другие куски).
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from app.core.roles import FULFILLMENT_ADMIN, FULFILLMENT_SELLER, FULFILLMENT_STAFF
from app.db.session import SessionLocal
from app.models.ff_staff_permissions import FfStaffPermissions
from app.models.inbound_intake import InboundIntakeBox, InboundIntakeRequest
from app.models.inventory_balance import InventoryBalance
from app.models.pallet import Pallet
from app.models.product import Product
from app.models.product_marketplace_link import ProductMarketplaceLink
from app.models.seller import Seller
from app.models.storage_location import StorageLocation
from app.models.tenant import Tenant
from app.models.user import User
from app.models.warehouse import Warehouse
from app.services.sorting_location_service import get_or_create_sorting_location
from app.services.tokens import create_access_token


def _headers(user: User) -> dict[str, str]:
    token = create_access_token(
        user_id=user.id,
        tenant_id=user.tenant_id,
        role=user.role,
        seller_id=user.seller_id,
    )
    return {"Authorization": f"Bearer {token}"}


async def _seed_tenant(label: str) -> tuple[Tenant, User]:
    """Тенант с администратором ФФ — минимальный набор для карточки товара."""
    suffix = uuid.uuid4().hex[:10]
    async with SessionLocal() as session:
        tenant = Tenant(name=f"ФФ {label}", slug=f"{label}-{suffix}")
        session.add(tenant)
        await session.flush()
        admin = User(tenant_id=tenant.id, role=FULFILLMENT_ADMIN, password_hash="unused")
        session.add(admin)
        await session.commit()
        session.expunge_all()
        return tenant, admin


async def _create_seller(tenant: Tenant, name: str) -> Seller:
    async with SessionLocal() as session:
        seller = Seller(tenant_id=tenant.id, name=name)
        session.add(seller)
        await session.commit()
        session.expunge(seller)
        return seller


async def _create_product(
    tenant: Tenant,
    seller: Seller,
    *,
    name: str,
    sku_suffix: str,
    wb_nm_id: int | None = None,
    wb_vendor_code: str | None = None,
    wb_barcode: str | None = None,
    wb_size: str | None = None,
    length_mm: int | None = None,
    width_mm: int | None = None,
    height_mm: int | None = None,
    weight_g: int | None = None,
    requires_honest_sign: bool = False,
    packaging_instructions: str | None = None,
) -> Product:
    async with SessionLocal() as session:
        product = Product(
            tenant_id=tenant.id,
            seller_id=seller.id,
            name=name,
            sku_code=f"WMS490-{sku_suffix}",
            wb_nm_id=wb_nm_id,
            wb_vendor_code=wb_vendor_code,
            wb_barcode=wb_barcode,
            wb_size=wb_size,
            length_mm=length_mm,
            width_mm=width_mm,
            height_mm=height_mm,
            weight_g=weight_g,
            requires_honest_sign=requires_honest_sign,
            packaging_instructions=packaging_instructions,
        )
        session.add(product)
        await session.commit()
        session.expunge(product)
        return product


async def _add_ozon_link(
    tenant: Tenant,
    seller: Seller,
    product: Product,
    *,
    sku: str,
    offer_id: str,
    external_product_id: str,
    barcodes: list[str],
) -> None:
    async with SessionLocal() as session:
        session.add(
            ProductMarketplaceLink(
                tenant_id=tenant.id,
                seller_id=seller.id,
                product_id=product.id,
                marketplace="ozon",
                external_sku=sku,
                external_offer_id=offer_id,
                external_product_id=external_product_id,
                external_barcodes=barcodes,
            )
        )
        await session.commit()


def _flatten(nodes: list[dict[str, object]]) -> list[dict[str, object]]:
    flat: list[dict[str, object]] = []
    for node in nodes:
        flat.append(node)
        children = node.get("children")
        if isinstance(children, list):
            flat.extend(_flatten(children))
    return flat


@pytest.mark.asyncio
async def test_product_card_matches_catalog_row_and_adds_dimensions_wms490(
    async_client: AsyncClient,
) -> None:
    """C4/C5: карточка = строка каталога того же товара, плюс габариты и вес."""
    tenant, admin = await _seed_tenant("card-wb-ozon")
    seller = await _create_seller(tenant, "Селлер А")
    product = await _create_product(
        tenant,
        seller,
        name="Рюкзак городской, чёрный",
        sku_suffix="A",
        wb_nm_id=123456,
        wb_vendor_code="BAG-CITY-BLK",
        wb_barcode="4600000000001",
        wb_size="one size",
        length_mm=400,
        width_mm=300,
        height_mm=150,
        weight_g=900,
        requires_honest_sign=True,
        packaging_instructions="Упаковать в пакет",
    )
    await _add_ozon_link(
        tenant,
        seller,
        product,
        sku="OZ-SKU-1",
        offer_id="OZ-OFFER-1",
        external_product_id="OZ-PID-1",
        barcodes=["2000000000001", "2000000000002"],
    )
    headers = _headers(admin)

    card_resp = await async_client.get(f"/products/{product.id}/card", headers=headers)
    assert card_resp.status_code == 200, card_resp.text
    card = card_resp.json()

    catalog_resp = await async_client.get(
        "/products/ff-catalog-page", headers=headers, params={"search": "BAG-CITY-BLK"}
    )
    assert catalog_resp.status_code == 200, catalog_resp.text
    [catalog_row] = catalog_resp.json()["items"]

    # Каждое поле строки каталога должно дословно совпасть с карточкой — карточка
    # не пересчитывает и не переформатирует ни одно из них (R17).
    assert catalog_row  # sanity: строка действительно есть
    for field, value in catalog_row.items():
        assert card[field] == value, field

    assert card["length_mm"] == 400
    assert card["width_mm"] == 300
    assert card["height_mm"] == 150
    assert card["weight_g"] == 900
    assert card["marketplaces"] == ["wb", "ozon"]
    assert card["location_warehouses"] == []


@pytest.mark.asyncio
async def test_product_card_manual_product_without_marketplace_wms490(
    async_client: AsyncClient,
) -> None:
    """C5: товар без площадки — нет ни WB-, ни Ozon-набора, ШК берётся из товара."""
    tenant, admin = await _seed_tenant("card-manual")
    seller = await _create_seller(tenant, "Селлер Д")
    product = await _create_product(
        tenant,
        seller,
        name="Товар ручной",
        sku_suffix="D",
        wb_barcode="4600000000099",
    )
    headers = _headers(admin)

    card = (await async_client.get(f"/products/{product.id}/card", headers=headers)).json()
    assert card["marketplaces"] == []
    assert card["wb_barcodes"] == ["4600000000099"]
    assert card["is_manual"] is True
    assert card["length_mm"] is None
    assert card["width_mm"] is None
    assert card["location_warehouses"] == []


@pytest.mark.asyncio
async def test_product_card_requires_catalog_cells_access_wms490(
    async_client: AsyncClient,
) -> None:
    """C18: те же права, что у каталога — cells/inventory пускают, продавца нет."""
    tenant, admin = await _seed_tenant("card-access")
    seller = await _create_seller(tenant, "Селлер Access")
    product = await _create_product(
        tenant, seller, name="Товар доступа", sku_suffix="ACC", wb_barcode="4600000000100"
    )

    async with SessionLocal() as session:
        staff_no_perm = User(tenant_id=tenant.id, role=FULFILLMENT_STAFF, password_hash="unused")
        staff_cells = User(tenant_id=tenant.id, role=FULFILLMENT_STAFF, password_hash="unused")
        staff_inventory = User(tenant_id=tenant.id, role=FULFILLMENT_STAFF, password_hash="unused")
        seller_user = User(
            tenant_id=tenant.id,
            seller_id=seller.id,
            role=FULFILLMENT_SELLER,
            password_hash="unused",
        )
        session.add_all([staff_no_perm, staff_cells, staff_inventory, seller_user])
        await session.flush()
        session.add(FfStaffPermissions(user_id=staff_cells.id, can_cells=True))
        session.add(FfStaffPermissions(user_id=staff_inventory.id, can_inventory=True))
        await session.commit()
        session.expunge_all()

    admin_resp = await async_client.get(f"/products/{product.id}/card", headers=_headers(admin))
    assert admin_resp.status_code == 200, admin_resp.text

    denied = await async_client.get(
        f"/products/{product.id}/card", headers=_headers(staff_no_perm)
    )
    assert denied.status_code == 403, denied.text
    assert denied.json()["detail"] == "forbidden"

    ok_cells = await async_client.get(
        f"/products/{product.id}/card", headers=_headers(staff_cells)
    )
    assert ok_cells.status_code == 200, ok_cells.text

    ok_inventory = await async_client.get(
        f"/products/{product.id}/card", headers=_headers(staff_inventory)
    )
    assert ok_inventory.status_code == 200, ok_inventory.text

    seller_denied = await async_client.get(
        f"/products/{product.id}/card", headers=_headers(seller_user)
    )
    assert seller_denied.status_code == 403, seller_denied.text


@pytest.mark.asyncio
async def test_product_card_foreign_tenant_and_missing_product_return_404_wms490(
    async_client: AsyncClient,
) -> None:
    """C18: чужая организация и несуществующий товар — «не найден», не отказ прав."""
    _tenant_a, admin_a = await _seed_tenant("card-tenant-a")
    tenant_b, admin_b = await _seed_tenant("card-tenant-b")
    seller_b = await _create_seller(tenant_b, "Селлер Б")
    product_b = await _create_product(
        tenant_b, seller_b, name="Чужой товар", sku_suffix="FOREIGN", wb_barcode="4600000000200"
    )

    cross = await async_client.get(
        f"/products/{product_b.id}/card", headers=_headers(admin_a)
    )
    assert cross.status_code == 404, cross.text
    assert cross.json()["detail"] == "product_not_found"

    missing = await async_client.get(
        f"/products/{uuid.uuid4()}/card", headers=_headers(admin_b)
    )
    assert missing.status_code == 404, missing.text
    assert missing.json()["detail"] == "product_not_found"


async def _seed_filtered_map(
    tenant: Tenant,
    product_a: Product,
    product_b: Product,
) -> tuple[Warehouse, StorageLocation, StorageLocation, StorageLocation, Warehouse, Warehouse]:
    """Пример из C9: A россыпью, A и чужой B в коробе на палете, A «без ячеек»,

    чужой B один в третьей ячейке (должна пропасть целиком под фильтром), и A
    на втором складе; третий склад — вообще без остатка A.
    """
    suffix = uuid.uuid4().hex[:8]
    async with SessionLocal() as session:
        warehouse1 = Warehouse(tenant_id=tenant.id, name="Основной склад", code=f"W1-{suffix}")
        warehouse2 = Warehouse(tenant_id=tenant.id, name="Второй склад", code=f"W2-{suffix}")
        warehouse3 = Warehouse(tenant_id=tenant.id, name="Третий склад", code=f"W3-{suffix}")
        session.add_all([warehouse1, warehouse2, warehouse3])
        await session.flush()

        cell1 = StorageLocation(
            tenant_id=tenant.id, warehouse_id=warehouse1.id, code="А-01-01", barcode=f"C1-{suffix}"
        )
        cell2 = StorageLocation(
            tenant_id=tenant.id, warehouse_id=warehouse1.id, code="А-01-02", barcode=f"C2-{suffix}"
        )
        cell_other = StorageLocation(
            tenant_id=tenant.id, warehouse_id=warehouse1.id, code="А-01-03", barcode=f"C3-{suffix}"
        )
        cell_w2 = StorageLocation(
            tenant_id=tenant.id, warehouse_id=warehouse2.id, code="Б-01-01", barcode=f"CW2-{suffix}"
        )
        session.add_all([cell1, cell2, cell_other, cell_w2])
        await session.flush()

        sorting1 = await get_or_create_sorting_location(session, tenant.id, warehouse1.id)

        pallet = Pallet(
            tenant_id=tenant.id,
            warehouse_id=warehouse1.id,
            code="П-000001",
            barcode=f"PLT-{suffix}",
            storage_location_id=cell2.id,
        )
        session.add(pallet)
        await session.flush()

        request = InboundIntakeRequest(
            tenant_id=tenant.id, warehouse_id=warehouse1.id, status="receiving"
        )
        session.add(request)
        await session.flush()

        box = InboundIntakeBox(
            tenant_id=tenant.id,
            request_id=request.id,
            box_number=1,
            internal_barcode=f"BOX-{suffix}",
            pallet_id=pallet.id,
        )
        session.add(box)
        await session.flush()

        session.add_all(
            [
                InventoryBalance(
                    tenant_id=tenant.id,
                    storage_location_id=cell1.id,
                    product_id=product_a.id,
                    quantity=3,
                    quantity_unpacked=3,
                    quantity_packed=0,
                ),
                InventoryBalance(
                    tenant_id=tenant.id,
                    storage_location_id=cell2.id,
                    product_id=product_a.id,
                    container_kind="box",
                    container_id=box.id,
                    quantity=5,
                    quantity_unpacked=5,
                    quantity_packed=0,
                ),
                InventoryBalance(
                    tenant_id=tenant.id,
                    storage_location_id=cell2.id,
                    product_id=product_b.id,
                    container_kind="box",
                    container_id=box.id,
                    quantity=9,
                    quantity_unpacked=9,
                    quantity_packed=0,
                ),
                InventoryBalance(
                    tenant_id=tenant.id,
                    storage_location_id=sorting1.id,
                    product_id=product_a.id,
                    quantity=2,
                    quantity_unpacked=2,
                    quantity_packed=0,
                ),
                InventoryBalance(
                    tenant_id=tenant.id,
                    storage_location_id=cell_other.id,
                    product_id=product_b.id,
                    quantity=4,
                    quantity_unpacked=4,
                    quantity_packed=0,
                ),
                InventoryBalance(
                    tenant_id=tenant.id,
                    storage_location_id=cell_w2.id,
                    product_id=product_a.id,
                    quantity=1,
                    quantity_unpacked=1,
                    quantity_packed=0,
                ),
            ]
        )
        await session.commit()
        for row in (warehouse1, warehouse2, warehouse3, cell1, cell2, cell_other):
            session.expunge(row)
        return warehouse1, cell1, cell2, cell_other, warehouse2, warehouse3


@pytest.mark.asyncio
async def test_warehouse_map_product_filter_keeps_only_matching_rows_wms490(
    async_client: AsyncClient,
) -> None:
    """C9: карта с ?product_id= показывает только это место и это количество."""
    tenant, admin = await _seed_tenant("map-filter")
    seller_a = await _create_seller(tenant, "Селлер A")
    seller_b = await _create_seller(tenant, "Селлер B")
    product_a = await _create_product(
        tenant, seller_a, name="Товар A", sku_suffix="MAPA", wb_barcode="4600000000300"
    )
    product_b = await _create_product(
        tenant, seller_b, name="Товар B чужой", sku_suffix="MAPB", wb_barcode="4600000000301"
    )
    warehouse1, cell1, cell2, cell_other, warehouse2, warehouse3 = await _seed_filtered_map(
        tenant, product_a, product_b
    )
    headers = _headers(admin)

    # Без фильтра — ровно то же поведение, что раньше: все три ячейки на месте,
    # чужой товар B никуда не делся.
    unfiltered = await async_client.get(f"/warehouses/{warehouse1.id}/map", headers=headers)
    assert unfiltered.status_code == 200, unfiltered.text
    unfiltered_data = unfiltered.json()
    assert {cell["id"] for cell in unfiltered_data["cells"]} == {
        str(cell1.id),
        str(cell2.id),
        str(cell_other.id),
    }
    assert set(unfiltered_data["sellers"]) == {seller_a.name, seller_b.name}
    assert any(
        node.get("product_id") == str(product_b.id)
        for cell in unfiltered_data["cells"]
        for node in _flatten(cell["children"])
    )

    filtered = await async_client.get(
        f"/warehouses/{warehouse1.id}/map",
        headers=headers,
        params={"product_id": str(product_a.id)},
    )
    assert filtered.status_code == 200, filtered.text
    data = filtered.json()

    # Ячейка с одним только чужим товаром пропадает целиком, а не остаётся пустой.
    assert {cell["id"] for cell in data["cells"]} == {str(cell1.id), str(cell2.id)}
    assert data["sellers"] == [seller_a.name]

    cell1_out = next(c for c in data["cells"] if c["id"] == str(cell1.id))
    assert cell1_out["qty"] == 3
    assert [child["kind"] for child in cell1_out["children"]] == ["product"]
    assert cell1_out["children"][0]["product_id"] == str(product_a.id)

    cell2_out = next(c for c in data["cells"] if c["id"] == str(cell2.id))
    assert cell2_out["qty"] == 5
    pallet_node = next(child for child in cell2_out["children"] if child["kind"] == "pallet")
    assert pallet_node["qty"] == 5
    box_node = next(child for child in pallet_node["children"] if child["kind"] == "box")
    assert box_node["qty"] == 5
    assert [child["kind"] for child in box_node["children"]] == ["product"]
    assert box_node["children"][0]["product_id"] == str(product_a.id)

    unassigned_products = [node for node in data["unassigned"] if node["kind"] == "product"]
    assert len(unassigned_products) == 1
    assert unassigned_products[0]["product_id"] == str(product_a.id)
    assert unassigned_products[0]["qty"] == 2

    total_qty = sum(cell["qty"] for cell in data["cells"]) + sum(
        node["qty"] for node in data["unassigned"]
    )
    assert total_qty == 3 + 5 + 2

    # Второй склад отдаёт только свою 1 штуку A, третий — пустую карту.
    map2 = await async_client.get(
        f"/warehouses/{warehouse2.id}/map",
        headers=headers,
        params={"product_id": str(product_a.id)},
    )
    assert map2.status_code == 200, map2.text
    map2_data = map2.json()
    map2_total = sum(cell["qty"] for cell in map2_data["cells"]) + sum(
        node["qty"] for node in map2_data["unassigned"]
    )
    assert map2_total == 1

    map3 = await async_client.get(
        f"/warehouses/{warehouse3.id}/map",
        headers=headers,
        params={"product_id": str(product_a.id)},
    )
    assert map3.status_code == 200, map3.text
    map3_data = map3.json()
    assert map3_data["cells"] == []
    assert map3_data["unassigned"] == []


@pytest.mark.asyncio
async def test_product_card_location_warehouses_matches_nonempty_maps_wms490(
    async_client: AsyncClient,
) -> None:
    """D1 план: location_warehouses совпадает с непустыми отфильтрованными картами."""
    tenant, admin = await _seed_tenant("map-location")
    seller_a = await _create_seller(tenant, "Селлер A")
    seller_b = await _create_seller(tenant, "Селлер B")
    product_a = await _create_product(
        tenant, seller_a, name="Товар A", sku_suffix="LOCA", wb_barcode="4600000000400"
    )
    product_b = await _create_product(
        tenant, seller_b, name="Товар B", sku_suffix="LOCB", wb_barcode="4600000000401"
    )
    warehouse1, *_rest, warehouse2, warehouse3 = await _seed_filtered_map(
        tenant, product_a, product_b
    )
    headers = _headers(admin)

    card = (await async_client.get(f"/products/{product_a.id}/card", headers=headers)).json()
    location_ids = {w["id"] for w in card["location_warehouses"]}
    assert location_ids == {str(warehouse1.id), str(warehouse2.id)}
    assert str(warehouse3.id) not in location_ids

    # Товар B лежит только в третьей ячейке первого склада.
    card_b = (await async_client.get(f"/products/{product_b.id}/card", headers=headers)).json()
    location_ids_b = {w["id"] for w in card_b["location_warehouses"]}
    assert location_ids_b == {str(warehouse1.id)}
