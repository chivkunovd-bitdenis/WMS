from __future__ import annotations

import uuid
from dataclasses import dataclass

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models.inbound_intake import (
    InboundIntakeCargoPlace,
    InboundIntakeRequest,
)
from app.models.inventory_balance import InventoryBalance
from app.models.inventory_count import InventoryCountCreatedContainer, InventoryCountLine
from app.models.inventory_movement import InventoryMovement
from app.models.pallet import Pallet
from app.models.product import Product
from app.models.seller_wildberries_imported_card import SellerWildberriesImportedCard
from app.models.storage_location import StorageLocation
from app.models.warehouse_box import WarehouseBox
from app.services import inventory_count_service
from app.services.sorting_location_service import (
    SORTING_LOCATION_CODE,
    UNASSIGNED_LABEL,
    get_or_create_sorting_location,
)


@dataclass(frozen=True)
class TenantSetup:
    headers: dict[str, str]
    tenant_id: uuid.UUID
    warehouse_id: uuid.UUID
    location_id: uuid.UUID


async def _tenant(async_client: AsyncClient, label: str) -> TenantSetup:
    suffix = uuid.uuid4().hex[:10]
    response = await async_client.post(
        "/auth/register",
        json={
            "organization_name": label,
            "slug": f"{label.lower()}-{suffix}",
            "admin_email": f"{label.lower()}-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert response.status_code == 200, response.text
    headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
    me = await async_client.get("/auth/me", headers=headers)
    warehouse = await async_client.post(
        "/warehouses",
        headers=headers,
        json={"name": f"Склад {label}", "code": f"WH-{suffix}"},
    )
    location = await async_client.post(
        f"/warehouses/{warehouse.json()['id']}/locations",
        headers=headers,
        json={"code": f"A-{suffix}"},
    )
    assert me.status_code == warehouse.status_code == location.status_code == 200
    return TenantSetup(
        headers=headers,
        tenant_id=uuid.UUID(me.json()["tenant_id"]),
        warehouse_id=uuid.UUID(warehouse.json()["id"]),
        location_id=uuid.UUID(location.json()["id"]),
    )


async def _seller(async_client: AsyncClient, setup: TenantSetup, name: str) -> uuid.UUID:
    response = await async_client.post(
        "/sellers", headers=setup.headers, json={"name": name}
    )
    assert response.status_code == 201, response.text
    return uuid.UUID(response.json()["id"])


async def _product(
    async_client: AsyncClient,
    setup: TenantSetup,
    *,
    name: str,
    seller_id: uuid.UUID | None = None,
) -> uuid.UUID:
    response = await async_client.post(
        "/products",
        headers=setup.headers,
        json={
            "name": name,
            "sku_code": f"SKU-{uuid.uuid4().hex[:12]}",
            "seller_id": str(seller_id) if seller_id is not None else None,
            "length_mm": 1,
            "width_mm": 1,
            "height_mm": 1,
        },
    )
    assert response.status_code == 200, response.text
    return uuid.UUID(response.json()["id"])


async def _balance(
    setup: TenantSetup,
    product_id: uuid.UUID,
    quantity: int,
    *,
    location_id: uuid.UUID | None = None,
    container_kind: str | None = None,
    container_id: uuid.UUID | None = None,
) -> None:
    async with SessionLocal() as session:
        session.add(
            InventoryBalance(
                tenant_id=setup.tenant_id,
                storage_location_id=location_id or setup.location_id,
                product_id=product_id,
                container_kind=container_kind,
                container_id=container_id,
                quantity=quantity,
                quantity_unpacked=quantity,
                quantity_packed=0,
            )
        )
        await session.commit()


async def _containers(
    setup: TenantSetup,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]:
    async with SessionLocal() as session:
        request = InboundIntakeRequest(
            tenant_id=setup.tenant_id,
            warehouse_id=setup.warehouse_id,
            status="receiving",
        )
        pallet = Pallet(
            tenant_id=setup.tenant_id,
            warehouse_id=setup.warehouse_id,
            code=f"П-{uuid.uuid4().hex[:8]}",
            barcode=f"PLT-{uuid.uuid4().hex}",
            storage_location_id=setup.location_id,
        )
        session.add_all([request, pallet])
        await session.flush()
        warehouse_box = WarehouseBox(
            tenant_id=setup.tenant_id,
            warehouse_id=setup.warehouse_id,
            internal_barcode=f"BOX-{uuid.uuid4().hex}",
            storage_location_id=setup.location_id,
            pallet_id=pallet.id,
        )
        empty_box = WarehouseBox(
            tenant_id=setup.tenant_id,
            warehouse_id=setup.warehouse_id,
            internal_barcode=f"EMPTY-{uuid.uuid4().hex}",
            storage_location_id=setup.location_id,
        )
        cargo_place = InboundIntakeCargoPlace(
            tenant_id=setup.tenant_id,
            request_id=request.id,
            place_number=1,
            internal_barcode=f"CARGO-{uuid.uuid4().hex}",
            pallet_id=pallet.id,
        )
        session.add_all([warehouse_box, empty_box, cargo_place])
        await session.commit()
        return pallet.id, warehouse_box.id, cargo_place.id, empty_box.id


async def _create_all(async_client: AsyncClient, setup: TenantSetup) -> dict[str, object]:
    response = await async_client.post(
        "/operations/inventory-counts",
        headers=setup.headers,
        json={
            "source": "planned",
            "filters": {"warehouse_id": str(setup.warehouse_id), "all": True},
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.asyncio
async def test_inventory_count_seller_and_category_filters_do_not_leak_other_products(
    async_client: AsyncClient,
) -> None:
    setup = await _tenant(async_client, "Filter")
    seller_a = await _seller(async_client, setup, "Селлер А")
    seller_b = await _seller(async_client, setup, "Селлер Б")
    product_a = await _product(async_client, setup, name="Платье", seller_id=seller_a)
    product_b = await _product(async_client, setup, name="Ремень", seller_id=seller_b)
    await _balance(setup, product_a, 5)
    await _balance(setup, product_b, 7)

    by_seller = await async_client.post(
        "/operations/inventory-counts",
        headers=setup.headers,
        json={
            "source": "planned",
            "filters": {
                "warehouse_id": str(setup.warehouse_id),
                "seller_id": str(seller_a),
            },
        },
    )
    assert by_seller.status_code == 201, by_seller.text
    assert {line["product_id"] for line in by_seller.json()["lines"]} == {str(product_a)}

    async with SessionLocal() as session:
        loaded_a = await session.get(Product, product_a)
        loaded_b = await session.get(Product, product_b)
        assert loaded_a is not None and loaded_b is not None
        loaded_a.wb_nm_id = 1001
        loaded_b.wb_nm_id = 1002
        session.add_all(
            [
                SellerWildberriesImportedCard(
                    tenant_id=setup.tenant_id,
                    seller_id=seller_a,
                    nm_id=1001,
                    raw_json={"subjectName": "Платья"},
                ),
                SellerWildberriesImportedCard(
                    tenant_id=setup.tenant_id,
                    seller_id=seller_b,
                    nm_id=1002,
                    raw_json={"subjectName": "Аксессуары"},
                ),
            ]
        )
        await session.commit()

    by_category = await async_client.post(
        "/operations/inventory-counts",
        headers=setup.headers,
        json={
            "source": "planned",
            "filters": {
                "warehouse_id": str(setup.warehouse_id),
                "category": "Платья",
            },
        },
    )
    assert by_category.status_code == 201, by_category.text
    assert {line["product_id"] for line in by_category.json()["lines"]} == {str(product_a)}


@pytest.mark.asyncio
async def test_inventory_count_selected_products_narrow_existing_scope(
    async_client: AsyncClient,
) -> None:
    setup = await _tenant(async_client, "Selected")
    other = await _tenant(async_client, "OtherSelected")
    seller = await _seller(async_client, setup, "Селлер")
    first = await _product(async_client, setup, name="Первый", seller_id=seller)
    second = await _product(async_client, setup, name="Второй")
    third = await _product(async_client, setup, name="Третий")
    foreign = await _product(async_client, other, name="Чужой")
    _, box, _, _ = await _containers(setup)
    await _balance(setup, first, 5)
    await _balance(setup, first, 2, container_kind="box", container_id=box)
    await _balance(setup, second, -3)
    await _balance(setup, third, 9)
    await _balance(other, foreign, 12)
    warehouse = await async_client.post(
        "/warehouses", headers=setup.headers, json={"name": "Второй склад", "code": "WH2"}
    )
    location = await async_client.post(
        f"/warehouses/{warehouse.json()['id']}/locations",
        headers=setup.headers,
        json={"code": "B2"},
    )
    assert warehouse.status_code == location.status_code == 200
    await _balance(setup, first, 20, location_id=uuid.UUID(location.json()["id"]))
    async with SessionLocal() as session:
        product = await session.get(Product, first)
        assert product is not None
        product.category = "Одежда"
        await session.commit()

    async def create(filters: dict[str, object]) -> dict:
        response = await async_client.post(
            "/operations/inventory-counts",
            headers=setup.headers,
            json={
                "source": "planned",
                "filters": {"warehouse_id": str(setup.warehouse_id), **filters},
                "comment": "Точечный пересчёт",
            },
        )
        assert response.status_code == 201, response.text
        return response.json()

    single = await create({"product_ids": [str(first), str(first)]})
    assert sorted(line["expected_quantity"] for line in single["lines"]) == [2, 5]
    assert {line["product_id"] for line in single["lines"]} == {str(first)}
    assert any(line["container_id"] == str(box) for line in single["lines"])
    assert single["comment"] == "Точечный пересчёт"
    reread = await async_client.get(
        f"/operations/inventory-counts/{single['id']}", headers=setup.headers
    )
    assert reread.status_code == 200
    assert len(reread.json()["lines"]) == 2

    selected = [str(first), str(second), str(foreign), str(uuid.uuid4())]
    multiple = await create({"product_ids": selected})
    assert {line["product_id"] for line in multiple["lines"]} == {str(first), str(second)}
    assert sorted(line["expected_quantity"] for line in multiple["lines"]) == [-3, 2, 5]
    for narrowing in ({"seller_id": str(seller)}, {"category": "Одежда"}):
        narrowed = await create({"product_ids": selected, **narrowing})
        assert {line["product_id"] for line in narrowed["lines"]} == {str(first)}
    assert (await create({"product_ids": [str(foreign)]}))["lines"] == []
    for unfiltered in ({}, {"product_ids": []}, {"product_ids": None}):
        whole = await create(unfiltered)
        assert {line["product_id"] for line in whole["lines"]} == {
            str(first), str(second), str(third)
        }


@pytest.mark.asyncio
async def test_inventory_count_object_keeps_existing_location_and_product_scopes(
    async_client: AsyncClient,
) -> None:
    setup = await _tenant(async_client, "Object")
    product = await _product(async_client, setup, name="Товар")
    await _balance(setup, product, 2)

    by_location = await async_client.post(
        "/operations/inventory-counts",
        headers=setup.headers,
        json={
            "source": "object",
            "object": {"type": "storage_location", "id": str(setup.location_id)},
        },
    )
    assert by_location.status_code == 201, by_location.text
    assert [line["product_id"] for line in by_location.json()["lines"]] == [str(product)]

    by_product = await async_client.post(
        "/operations/inventory-counts",
        headers=setup.headers,
        json={
            "source": "object",
            "object": {"type": "product", "id": str(product)},
        },
    )
    assert by_product.status_code == 201, by_product.text
    assert [line["product_id"] for line in by_product.json()["lines"]] == [str(product)]


@pytest.mark.asyncio
async def test_inventory_count_uses_human_label_for_sorting_location(
    async_client: AsyncClient,
) -> None:
    # TC-NEW-INVENTORY-SORTING-LABEL-001
    # Дано: товар ещё лежит в системной sorting-зоне. Когда оператор открывает
    # документ пересчёта, тогда заголовок группы говорит «Без ячеек», а не
    # раскрывает технический код, по которому backend находит эту зону.
    setup = await _tenant(async_client, "SortingLabel")
    product = await _product(async_client, setup, name="Товар без ячейки")
    async with SessionLocal() as session:
        sorting = await get_or_create_sorting_location(
            session, setup.tenant_id, setup.warehouse_id
        )
        sorting_id = sorting.id
        await session.commit()
    await _balance(setup, product, 4, location_id=sorting_id)

    response = await async_client.post(
        "/operations/inventory-counts",
        headers=setup.headers,
        json={
            "source": "object",
            "object": {"type": "product", "id": str(product)},
        },
    )

    assert response.status_code == 201, response.text
    cells = response.json()["cells"]
    assert cells[0]["label"] == UNASSIGNED_LABEL
    assert cells[0]["label"] != SORTING_LOCATION_CODE


@pytest.mark.asyncio
async def test_inventory_count_by_box_uses_exact_box_balances(
    async_client: AsyncClient,
) -> None:
    setup = await _tenant(async_client, "BoxCount")
    first_product = await _product(async_client, setup, name="Товар 18")
    second_product = await _product(async_client, setup, name="Товар 7")
    _pallet_id, box_id, _cargo_place_id, _empty_box_id = await _containers(setup)
    await _balance(
        setup,
        first_product,
        18,
        container_kind="box",
        container_id=box_id,
    )
    await _balance(
        setup,
        second_product,
        7,
        container_kind="box",
        container_id=box_id,
    )
    # Тот же SKU лежит россыпью в той же ячейке. Пересчёт короба не должен
    # смешивать этот остаток с 18 штуками внутри короба.
    await _balance(setup, first_product, 99)

    response = await async_client.post(
        "/operations/inventory-counts",
        headers=setup.headers,
        json={
            "source": "object",
            "object": {"type": "box", "id": str(box_id)},
        },
    )

    assert response.status_code == 201, response.text
    lines = {
        line["product_id"]: (
            line["expected_quantity"],
            line["container_kind"],
            line["container_id"],
        )
        for line in response.json()["lines"]
    }
    assert lines == {
        str(first_product): (18, "box", str(box_id)),
        str(second_product): (7, "box", str(box_id)),
    }


@pytest.mark.asyncio
async def test_inventory_count_by_cargo_place_uses_exact_cargo_place_balances(
    async_client: AsyncClient,
) -> None:
    setup = await _tenant(async_client, "CargoCount")
    product = await _product(async_client, setup, name="Товар в грузоместе")
    _pallet_id, _box_id, cargo_place_id, _empty_box_id = await _containers(setup)
    await _balance(
        setup,
        product,
        11,
        container_kind="cargo_place",
        container_id=cargo_place_id,
    )

    response = await async_client.post(
        "/operations/inventory-counts",
        headers=setup.headers,
        json={
            "source": "object",
            "object": {"type": "cargo_place", "id": str(cargo_place_id)},
        },
    )

    assert response.status_code == 201, response.text
    assert [
        (
            line["product_id"],
            line["expected_quantity"],
            line["container_kind"],
            line["container_id"],
        )
        for line in response.json()["lines"]
    ] == [(str(product), 11, "cargo_place", str(cargo_place_id))]


@pytest.mark.asyncio
async def test_inventory_count_by_pallet_includes_nested_container_balances(
    async_client: AsyncClient,
) -> None:
    setup = await _tenant(async_client, "PalletCount")
    pallet_product = await _product(async_client, setup, name="Товар на палете")
    box_product = await _product(async_client, setup, name="Товар во вложенном коробе")
    cargo_product = await _product(
        async_client, setup, name="Товар во вложенном грузоместе"
    )
    pallet_id, box_id, cargo_place_id, _empty_box_id = await _containers(setup)
    await _balance(
        setup,
        pallet_product,
        3,
        container_kind="pallet",
        container_id=pallet_id,
    )
    await _balance(
        setup,
        box_product,
        5,
        container_kind="box",
        container_id=box_id,
    )
    await _balance(
        setup,
        cargo_product,
        9,
        container_kind="cargo_place",
        container_id=cargo_place_id,
    )

    response = await async_client.post(
        "/operations/inventory-counts",
        headers=setup.headers,
        json={
            "source": "object",
            "object": {"type": "pallet", "id": str(pallet_id)},
        },
    )

    assert response.status_code == 201, response.text
    lines = {
        (line["container_kind"], line["container_id"], line["product_id"]): line[
            "expected_quantity"
        ]
        for line in response.json()["lines"]
    }
    assert lines == {
        ("pallet", str(pallet_id), str(pallet_product)): 3,
        ("box", str(box_id), str(box_product)): 5,
        ("cargo_place", str(cargo_place_id), str(cargo_product)): 9,
    }


@pytest.mark.asyncio
async def test_inventory_count_by_empty_container_is_visible_before_confirmation(
    async_client: AsyncClient,
) -> None:
    setup = await _tenant(async_client, "EmptyContainer")
    _pallet_id, _box_id, _cargo_place_id, empty_box_id = await _containers(setup)

    response = await async_client.post(
        "/operations/inventory-counts",
        headers=setup.headers,
        json={
            "source": "object",
            "object": {"type": "box", "id": str(empty_box_id)},
        },
    )

    assert response.status_code == 201, response.text
    assert response.json()["empty_places"] == []
    assert str(empty_box_id) in _container_ids_in_tree(response.json())


@pytest.mark.asyncio
async def test_inventory_count_is_tenant_scoped_for_list_get_and_post(
    async_client: AsyncClient,
) -> None:
    tenant_a = await _tenant(async_client, "TenantA")
    product = await _product(async_client, tenant_a, name="Чужой товар")
    await _balance(tenant_a, product, 3)
    count = await _create_all(async_client, tenant_a)
    tenant_b = await _tenant(async_client, "TenantB")

    listed = await async_client.get(
        "/operations/inventory-counts", headers=tenant_b.headers
    )
    hidden = await async_client.get(
        f"/operations/inventory-counts/{count['id']}", headers=tenant_b.headers
    )
    blocked_post = await async_client.post(
        f"/operations/inventory-counts/{count['id']}/post", headers=tenant_b.headers
    )
    assert listed.status_code == 200
    assert listed.json() == []
    assert hidden.status_code == 404
    assert blocked_post.status_code == 404


@pytest.mark.asyncio
async def test_inventory_count_zero_blank_match_and_mismatch_create_exact_movements(
    async_client: AsyncClient,
) -> None:
    setup = await _tenant(async_client, "Posting")
    zero_product = await _product(async_client, setup, name="Насчитали ноль")
    blank_product = await _product(async_client, setup, name="Не считали")
    match_product = await _product(async_client, setup, name="Сошлось")
    await _balance(setup, zero_product, 5)
    await _balance(setup, blank_product, 4)
    await _balance(setup, match_product, 3)
    count = await _create_all(async_client, setup)
    lines = {line["product_id"]: line for line in count["lines"]}

    saved = await async_client.put(
        f"/operations/inventory-counts/{count['id']}/lines",
        headers=setup.headers,
        json={
            "lines": [
                {"line_id": lines[str(zero_product)]["id"], "actual_quantity": 0},
                {"line_id": lines[str(match_product)]["id"], "actual_quantity": 3},
            ]
        },
    )
    assert saved.status_code == 200, saved.text
    saved_lines = {line["product_id"]: line for line in saved.json()["lines"]}
    assert saved_lines[str(zero_product)]["actual_quantity"] == 0
    assert saved_lines[str(blank_product)]["actual_quantity"] is None

    posted = await async_client.post(
        f"/operations/inventory-counts/{count['id']}/post", headers=setup.headers
    )
    assert posted.status_code == 200, posted.text
    assert posted.json()["posted_lines"] == 1
    assert posted.json()["unchanged_lines"] == 1

    async with SessionLocal() as session:
        balances = {
            product_id: quantity
            for product_id, quantity in (
                await session.execute(
                    select(InventoryBalance.product_id, InventoryBalance.quantity).where(
                        InventoryBalance.tenant_id == setup.tenant_id
                    )
                )
            ).all()
        }
        movements = list(
            (
                await session.execute(
                    select(InventoryMovement).where(
                        InventoryMovement.movement_type == "inventory_count"
                    )
                )
            ).scalars()
        )
    assert balances[zero_product] == 0
    assert balances[blank_product] == 4
    assert balances[match_product] == 3
    assert len(movements) == 1
    assert movements[0].product_id == zero_product
    assert movements[0].quantity_delta == -5
    assert movements[0].inventory_count_line_id == uuid.UUID(
        lines[str(zero_product)]["id"]
    )

    repeated = await async_client.post(
        f"/operations/inventory-counts/{count['id']}/post", headers=setup.headers
    )
    edited = await async_client.put(
        f"/operations/inventory-counts/{count['id']}/lines",
        headers=setup.headers,
        json={
            "lines": [
                {"line_id": lines[str(zero_product)]["id"], "actual_quantity": 1}
            ]
        },
    )
    assert repeated.status_code == 409
    assert repeated.json()["detail"] == "already_posted"
    assert edited.status_code == 409
    assert edited.json()["detail"] == "not_editable"


@pytest.mark.asyncio
async def test_inventory_count_posts_against_current_balance_and_returns_warning(
    async_client: AsyncClient,
) -> None:
    setup = await _tenant(async_client, "Race")
    product = await _product(async_client, setup, name="Движущийся остаток")
    await _balance(setup, product, 10)
    count = await _create_all(async_client, setup)
    line = count["lines"][0]
    saved = await async_client.put(
        f"/operations/inventory-counts/{count['id']}/lines",
        headers=setup.headers,
        json={"lines": [{"line_id": line["id"], "actual_quantity": 4}]},
    )
    assert saved.status_code == 200

    async with SessionLocal() as session:
        balance = await session.scalar(
            select(InventoryBalance).where(
                InventoryBalance.tenant_id == setup.tenant_id,
                InventoryBalance.product_id == product,
            )
        )
        assert balance is not None
        balance.quantity = 7
        balance.quantity_unpacked = 7
        await session.commit()

    posted = await async_client.post(
        f"/operations/inventory-counts/{count['id']}/post", headers=setup.headers
    )
    assert posted.status_code == 200, posted.text
    assert posted.json()["posted_lines"] == 1
    assert posted.json()["changed_balance_count"] == 1
    assert posted.json()["changed_balances"] == [
        {
            "line_id": line["id"],
            "product_id": str(product),
            "storage_location_id": str(setup.location_id),
            "expected_quantity": 10,
            "current_quantity": 7,
        }
    ]
    async with SessionLocal() as session:
        quantity = await session.scalar(
            select(InventoryBalance.quantity).where(
                InventoryBalance.tenant_id == setup.tenant_id,
                InventoryBalance.product_id == product,
            )
        )
        delta = await session.scalar(
            select(InventoryMovement.quantity_delta).where(
                InventoryMovement.inventory_count_line_id == uuid.UUID(line["id"])
            )
        )
    assert quantity == 4
    assert delta == -3


@pytest.mark.asyncio
async def test_inventory_count_empty_document_is_rejected_and_draft_can_be_cancelled(
    async_client: AsyncClient,
) -> None:
    setup = await _tenant(async_client, "Empty")
    count = await _create_all(async_client, setup)
    assert count["lines"] == []

    posted = await async_client.post(
        f"/operations/inventory-counts/{count['id']}/post", headers=setup.headers
    )
    cancelled = await async_client.delete(
        f"/operations/inventory-counts/{count['id']}", headers=setup.headers
    )
    assert posted.status_code == 409
    assert posted.json()["detail"] == "empty_count"
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"


@pytest.mark.asyncio
async def test_inventory_count_without_address_storage_hides_and_does_not_require_cell(
    async_client: AsyncClient,
) -> None:
    setup = await _tenant(async_client, "NoAddress")
    product = await _product(async_client, setup, name="Без ячейки")
    await _balance(setup, product, 6)
    disabled = await async_client.patch(
        "/tenant/settings",
        headers=setup.headers,
        json={"address_storage_enabled": False},
    )
    assert disabled.status_code == 200, disabled.text

    count = await _create_all(async_client, setup)
    assert count["address_storage"] is False
    assert count["lines"][0]["storage_location_id"] is None
    assert count["lines"][0]["storage_location_code"] is None
    assert count["cells"] == [
        {
            "id": "inventory",
            "label": "",
            "children": count["cells"][0]["children"],
        }
    ]
    line_id = count["lines"][0]["id"]
    saved = await async_client.put(
        f"/operations/inventory-counts/{count['id']}/lines",
        headers=setup.headers,
        json={"lines": [{"line_id": line_id, "actual_quantity": 2}]},
    )
    posted = await async_client.post(
        f"/operations/inventory-counts/{count['id']}/post", headers=setup.headers
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["lines"][0]["storage_location_id"] is None
    assert posted.status_code == 200, posted.text
    assert posted.json()["changed_balances"] == []
    async with SessionLocal() as session:
        total = await session.scalar(
            select(func.sum(InventoryBalance.quantity)).where(
                InventoryBalance.tenant_id == setup.tenant_id,
                InventoryBalance.product_id == product,
            )
        )
    assert total == 2


@pytest.mark.asyncio
async def test_inventory_count_includes_negative_balance_and_skips_zero(
    async_client: AsyncClient,
) -> None:
    """Минус обязан попасть в документ, ноль — нет.

    Отрицательная ячейка — самый сильный признак того, что учёт разъехался с
    полкой, и раньше именно её пересчитать было нельзя. Нули не тащим: строка
    баланса при обнулении не удаляется, и документ распух бы фантомами.
    """
    setup = await _tenant(async_client, "NegCount")
    negative = await _product(async_client, setup, name="Ушёл в минус")
    zero = await _product(async_client, setup, name="Обнулённый")
    positive = await _product(async_client, setup, name="Обычный")
    await _balance(setup, negative, -1)
    await _balance(setup, zero, 0)
    await _balance(setup, positive, 5)

    response = await async_client.post(
        "/operations/inventory-counts",
        headers=setup.headers,
        json={"source": "planned", "filters": {}},
    )

    assert response.status_code == 201, response.text
    lines = {line["product_id"]: line["expected_quantity"] for line in response.json()["lines"]}
    assert lines == {str(negative): -1, str(positive): 5}


@pytest.mark.asyncio
async def test_inventory_count_found_creates_line_and_second_scan_increments(
    async_client: AsyncClient,
) -> None:
    """Находка: товар лежит в коробе, где по учёту его нет.

    Ради этого пересчёт и затевают. Первый скан заводит строку со счётом 1,
    второй прибавляет вторую штуку, а не плодит вторую строку.
    """
    setup = await _tenant(async_client, "FoundCount")
    counted = await _product(async_client, setup, name="Числится")
    surprise = await _product(async_client, setup, name="Находка")
    _pallet_id, box_id, _cargo_place_id, _empty_box_id = await _containers(setup)
    await _balance(setup, counted, 3, container_kind="box", container_id=box_id)

    async with SessionLocal() as session:
        product = await session.get(Product, surprise)
        assert product is not None
        product.wb_barcode = "4600000000001"
        await session.commit()

    created = await async_client.post(
        "/operations/inventory-counts",
        headers=setup.headers,
        json={"source": "object", "object": {"type": "box", "id": str(box_id)}},
    )
    assert created.status_code == 201, created.text
    count_id = created.json()["id"]

    body = {
        "barcodes": ["4600000000001"],
        "container_kind": "box",
        "container_id": str(box_id),
    }
    first = await async_client.post(
        f"/operations/inventory-counts/{count_id}/found", headers=setup.headers, json=body
    )
    assert first.status_code == 200, first.text
    found_line = next(
        line for line in first.json()["count"]["lines"] if line["product_id"] == str(surprise)
    )
    assert found_line["expected_quantity"] == 0
    assert found_line["actual_quantity"] == 1
    assert found_line["container_id"] == str(box_id)

    second = await async_client.post(
        f"/operations/inventory-counts/{count_id}/found", headers=setup.headers, json=body
    )
    assert second.status_code == 200, second.text
    surprise_lines = [
        line for line in second.json()["count"]["lines"] if line["product_id"] == str(surprise)
    ]
    assert len(surprise_lines) == 1
    assert surprise_lines[0]["actual_quantity"] == 2


@pytest.mark.asyncio
async def test_inventory_count_found_survives_scanner_layout_and_case(
    async_client: AsyncClient,
) -> None:
    """Сканер в русской раскладке и верхний регистр не должны ронять находку."""
    setup = await _tenant(async_client, "LayoutCount")
    surprise = await _product(async_client, setup, name="Находка раскладкой")
    await _balance(setup, surprise, 0)
    async with SessionLocal() as session:
        product = await session.get(Product, surprise)
        assert product is not None
        product.wb_barcode = "chin-56005"
        await session.commit()

    anchor = await _product(async_client, setup, name="Якорь документа")
    await _balance(setup, anchor, 2)
    created = await async_client.post(
        "/operations/inventory-counts",
        headers=setup.headers,
        json={"source": "planned", "filters": {}},
    )
    assert created.status_code == 201, created.text

    response = await async_client.post(
        f"/operations/inventory-counts/{created.json()['id']}/found",
        headers=setup.headers,
        # Первым идёт то, что реально приехало со сканера, вторым — перевод раскладки.
        json={
            "barcodes": ["Сршт-56005", "CHIN-56005"],
            "cell_id": str(setup.location_id),
            "container_kind": None,
            "container_id": None,
        },
    )
    assert response.status_code == 200, response.text
    line = next(
        line for line in response.json()["count"]["lines"] if line["product_id"] == str(surprise)
    )
    assert line["actual_quantity"] == 1


@pytest.mark.asyncio
async def test_inventory_count_found_rejects_container_from_another_warehouse(
    async_client: AsyncClient,
) -> None:
    """Чужая тара отбивается при записи, а не пятисоткой на проведении."""
    setup = await _tenant(async_client, "AlienBoxCount")
    other = await _tenant(async_client, "AlienBoxOther")
    surprise = await _product(async_client, setup, name="Товар")
    await _balance(setup, surprise, 1)
    async with SessionLocal() as session:
        product = await session.get(Product, surprise)
        assert product is not None
        product.wb_barcode = "4600000000009"
        await session.commit()
    _p, alien_box_id, _c, _e = await _containers(other)

    created = await async_client.post(
        "/operations/inventory-counts",
        headers=setup.headers,
        json={"source": "planned", "filters": {}},
    )
    assert created.status_code == 201, created.text

    response = await async_client.post(
        f"/operations/inventory-counts/{created.json()['id']}/found",
        headers=setup.headers,
        json={
            "barcodes": ["4600000000009"],
            "container_kind": "box",
            "container_id": str(alien_box_id),
        },
    )
    assert response.status_code == 404, response.text
    assert response.json()["detail"] == "container_not_found"


@pytest.mark.asyncio
async def test_inventory_count_found_without_place_goes_to_sorting_zone(
    async_client: AsyncClient,
) -> None:
    """Первый пункт модели владельца: просто сканирую товар — он в россыпи без ячейки.

    Адрес в этом случае определяет сервер, а не экран: в дереве «Без ячеек» —
    виртуальная строка, ячейкой она не является.
    """
    setup = await _tenant(async_client, "LooseCount")
    surprise = await _product(async_client, setup, name="Ничего не открыто")
    anchor = await _product(async_client, setup, name="Якорь")
    await _balance(setup, anchor, 2)
    async with SessionLocal() as session:
        product = await session.get(Product, surprise)
        assert product is not None
        product.wb_barcode = "4600000000777"
        await session.commit()

    created = await async_client.post(
        "/operations/inventory-counts",
        headers=setup.headers,
        json={"source": "planned", "filters": {}},
    )
    assert created.status_code == 201, created.text

    response = await async_client.post(
        f"/operations/inventory-counts/{created.json()['id']}/found",
        headers=setup.headers,
        json={"barcodes": ["4600000000777"], "cell_id": None},
    )
    assert response.status_code == 200, response.text
    line = next(
        line for line in response.json()["count"]["lines"] if line["product_id"] == str(surprise)
    )
    assert line["actual_quantity"] == 1
    assert line["container_id"] is None

    async with SessionLocal() as session:
        location = await session.get(StorageLocation, uuid.UUID(line["storage_location_id"]))
        assert location is not None
        assert location.code == "__SORTING__"


@pytest.mark.asyncio
async def test_inventory_count_found_is_idempotent_per_scan(
    async_client: AsyncClient,
) -> None:
    """Повтор того же скана не превращается в лишнюю штуку на остатке.

    Склад работает по вайфаю, который рвётся: ответ не доехал, экран показал
    ошибку, а запись уже прошла. Кладовщик сканирует ещё раз — и без этой
    защиты на остатке оказывается двойка, которую потом нечем найти.
    """
    setup = await _tenant(async_client, "IdemCount")
    surprise = await _product(async_client, setup, name="Находка с повтором")
    anchor = await _product(async_client, setup, name="Якорь")
    await _balance(setup, anchor, 2)
    async with SessionLocal() as session:
        product = await session.get(Product, surprise)
        assert product is not None
        product.wb_barcode = "4600000000555"
        await session.commit()

    created = await async_client.post(
        "/operations/inventory-counts",
        headers=setup.headers,
        json={"source": "planned", "filters": {}},
    )
    assert created.status_code == 201, created.text
    count_id = created.json()["id"]

    body = {
        "barcodes": ["4600000000555"],
        "cell_id": str(setup.location_id),
        "scan_id": "scan-0001",
    }
    first = await async_client.post(
        f"/operations/inventory-counts/{count_id}/found", headers=setup.headers, json=body
    )
    assert first.status_code == 200, first.text

    # Тот же скан ещё раз — как будто оператор не увидел ответа и повторил.
    again = await async_client.post(
        f"/operations/inventory-counts/{count_id}/found", headers=setup.headers, json=body
    )
    assert again.status_code == 200, again.text

    lines = [
        line for line in again.json()["count"]["lines"] if line["product_id"] == str(surprise)
    ]
    assert len(lines) == 1
    assert lines[0]["actual_quantity"] == 1

    # А настоящий второй пик — это уже другой скан, и он считается.
    third = await async_client.post(
        f"/operations/inventory-counts/{count_id}/found",
        headers=setup.headers,
        json={**body, "scan_id": "scan-0002"},
    )
    assert third.status_code == 200, third.text
    line = next(
        line for line in third.json()["count"]["lines"] if line["product_id"] == str(surprise)
    )
    assert line["actual_quantity"] == 2


@pytest.mark.asyncio
async def test_inventory_count_drops_empty_places_but_keeps_them_scannable(
    async_client: AsyncClient,
) -> None:
    # Пустая по документу тара не должна занимать строку в дереве, но обязана
    # открываться сканом. В пересчёте «Империи ФФ» из 420 коробов товар лежал в
    # 113: остальные 307 висели строками «0 из 0», документ вырастал до сорока
    # тысяч пикселей, и оператор не мог найти в нём свой короб глазами.
    setup = await _tenant(async_client, "EmptyBox")
    product = await _product(async_client, setup, name="Товар в коробе")
    _pallet_id, box_id, _cargo_place_id, empty_box_id = await _containers(setup)
    await _balance(
        setup,
        product,
        3,
        location_id=setup.location_id,
        container_kind="box",
        container_id=box_id,
    )

    count = await _create_all(async_client, setup)

    def container_ids(nodes: list[dict[str, object]]) -> set[str]:
        found: set[str] = set()
        for node in nodes:
            if node["kind"] == "product":
                continue
            found.add(str(node["id"]))
            found |= container_ids(node["children"])  # type: ignore[arg-type]
        return found

    in_tree: set[str] = set()
    for cell in count["cells"]:
        in_tree |= container_ids(cell["children"])  # type: ignore[arg-type]

    assert str(box_id) in in_tree
    assert str(empty_box_id) not in in_tree

    scannable = {item["id"]: item for item in count["scannable_containers"]}
    assert str(empty_box_id) in scannable
    assert scannable[str(empty_box_id)]["kind"] == "box"
    assert scannable[str(empty_box_id)]["cell_id"] == str(setup.location_id)
    # Тара со строками остаётся в дереве и в списке сканируемой не дублируется.
    assert str(box_id) not in scannable


@pytest.mark.asyncio
async def test_inventory_count_create_container_keeps_it_visible_but_not_other_empty_boxes(
    async_client: AsyncClient,
) -> None:
    # Кнопка «Создать короб» была мертва: тара создавалась на складе, но
    # прунинг тут же выбрасывал её из дерева документа — она пуста по
    # определению, оператор только что её завёл. Ручка
    # POST /operations/inventory-counts/{id}/containers должна и создать
    # тару, и удержать её в дереве, но не отключать прунинг для чужой пустой
    # тары склада (см. test_inventory_count_drops_empty_places_...).
    setup = await _tenant(async_client, "NewBox")
    product = await _product(async_client, setup, name="Товар в коробе")
    pallet_id, box_id, _cargo_place_id, empty_box_id = await _containers(setup)
    await _balance(
        setup,
        product,
        3,
        location_id=setup.location_id,
        container_kind="box",
        container_id=box_id,
    )

    count = await _create_all(async_client, setup)

    response = await async_client.post(
        f"/operations/inventory-counts/{count['id']}/containers",
        headers=setup.headers,
        json={"kind": "box"},
    )
    assert response.status_code == 200, response.text
    body = response.json()

    def container_ids(nodes: list[dict[str, object]]) -> set[str]:
        found: set[str] = set()
        for node in nodes:
            if node["kind"] == "product":
                continue
            found.add(str(node["id"]))
            found |= container_ids(node["children"])  # type: ignore[arg-type]
        return found

    in_tree: set[str] = set()
    for cell in body["cells"]:
        in_tree |= container_ids(cell["children"])  # type: ignore[arg-type]

    # Новый короб виден в дереве документа сразу после создания. Короб с
    # товаром и его палета (родитель, у которого теперь есть непустой
    # ребёнок) остаются в дереве по обычному правилу «не пусто — не трогаем».
    created_ids = in_tree - {str(box_id), str(pallet_id)}
    assert len(created_ids) == 1, in_tree
    created_id = next(iter(created_ids))
    assert created_id != str(empty_box_id)

    # ...а старая пустая тара склада, не заведённая через эту ручку,
    # по-прежнему выброшена из дерева: общее правило прунинга не отключилось.
    assert str(empty_box_id) not in in_tree
    scannable_ids = {item["id"] for item in body["scannable_containers"]}
    assert str(empty_box_id) in scannable_ids
    assert created_id not in scannable_ids

    # Исключение привязано к документу, а не только к разовому ответу ручки:
    # обычное переоткрытие документа отдаёт тот же результат.
    reopened = await async_client.get(
        f"/operations/inventory-counts/{count['id']}", headers=setup.headers
    )
    assert reopened.status_code == 200, reopened.text
    reopened_tree: set[str] = set()
    for cell in reopened.json()["cells"]:
        reopened_tree |= container_ids(cell["children"])  # type: ignore[arg-type]
    assert created_id in reopened_tree
    assert str(empty_box_id) not in reopened_tree


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["box", "cargo_place", "pallet"])
async def test_inventory_count_container_and_document_link_commit_together(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch, kind: str,
) -> None:
    """WMS-375/A29: retry after a failed link must not leave an extra container."""
    setup = await _tenant(async_client, "AtomicContainer")
    product = await _product(async_client, setup, name="Synthetic count product")
    await _balance(setup, product, 3)
    count = await _create_all(async_client, setup)
    url = f"/operations/inventory-counts/{count['id']}/containers"
    real_create = inventory_count_service.warehouse_map_service.create_sorting_object

    async def fail_before_document_link(*args, **kwargs):
        await real_create(*args, **kwargs)
        raise RuntimeError("injected failure before document link")

    monkeypatch.setattr(
        inventory_count_service.warehouse_map_service,
        "create_sorting_object", fail_before_document_link,
    )
    with pytest.raises(RuntimeError, match="injected failure"):
        await async_client.post(url, headers=setup.headers, json={"kind": kind})
    async with SessionLocal() as session:
        assert await session.scalar(select(func.count()).select_from(WarehouseBox)) == 0
        assert await session.scalar(select(func.count()).select_from(Pallet)) == 0
        assert await session.scalar(
            select(func.count()).select_from(InventoryCountCreatedContainer)
        ) == 0
        assert await session.scalar(select(func.sum(InventoryBalance.quantity))) == 3
        assert await session.scalar(select(func.count()).select_from(InventoryMovement)) == 0

    monkeypatch.setattr(
        inventory_count_service.warehouse_map_service, "create_sorting_object", real_create,
    )
    retry = await async_client.post(url, headers=setup.headers, json={"kind": kind})
    assert retry.status_code == 200, retry.text
    async with SessionLocal() as session:
        boxes = await session.scalar(select(func.count()).select_from(WarehouseBox))
        pallets = await session.scalar(select(func.count()).select_from(Pallet))
        assert (boxes, pallets) == ((0, 1) if kind == "pallet" else (1, 0))
        links = list((await session.scalars(select(InventoryCountCreatedContainer))).all())
        assert len(links) == 1
        assert links[0].count_id == uuid.UUID(str(count["id"]))
        assert links[0].container_kind == kind
        model = Pallet if kind == "pallet" else WarehouseBox
        assert await session.get(model, links[0].container_id) is not None


@pytest.mark.asyncio
async def test_inventory_count_create_container_rejects_posted_document(
    async_client: AsyncClient,
) -> None:
    # Пересчёт проведён — дерево уже история движений, заводить в него тару
    # незачем и небезопасно. Как и правка строк (save_actuals), создание
    # тары должно быть заперто статусом документа на сервере, а не только
    # проверкой на экране.
    setup = await _tenant(async_client, "PostedNoBox")
    product = await _product(async_client, setup, name="Товар для проводки")
    await _balance(setup, product, 2)
    count = await _create_all(async_client, setup)
    line = count["lines"][0]
    saved = await async_client.put(
        f"/operations/inventory-counts/{count['id']}/lines",
        headers=setup.headers,
        json={"lines": [{"line_id": line["id"], "actual_quantity": 2}]},
    )
    assert saved.status_code == 200, saved.text
    posted = await async_client.post(
        f"/operations/inventory-counts/{count['id']}/post", headers=setup.headers
    )
    assert posted.status_code == 200, posted.text

    response = await async_client.post(
        f"/operations/inventory-counts/{count['id']}/containers",
        headers=setup.headers,
        json={"kind": "box"},
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "not_editable"


@pytest.mark.asyncio
async def test_inventory_count_records_found_into_container_dropped_as_empty(
    async_client: AsyncClient,
) -> None:
    # Пустой короб выброшен из дерева, но оператор подошёл к нему и нашёл товар.
    # Находка обязана лечь именно в этот короб — иначе выброс строки превратился
    # бы в запрет считать то, ради чего пересчёт и делают.
    setup = await _tenant(async_client, "FoundEmptyBox")
    product = await _product(async_client, setup, name="Товар в коробе")
    found_product = await _product(async_client, setup, name="Найденный товар")
    _pallet_id, box_id, _cargo_place_id, empty_box_id = await _containers(setup)
    await _balance(
        setup,
        product,
        3,
        location_id=setup.location_id,
        container_kind="box",
        container_id=box_id,
    )
    barcode = f"FOUND-{uuid.uuid4().hex[:10]}"
    async with SessionLocal() as session:
        card = await session.get(Product, found_product)
        assert card is not None
        card.wb_barcode = barcode
        await session.commit()

    count = await _create_all(async_client, setup)
    assert str(empty_box_id) in {item["id"] for item in count["scannable_containers"]}

    found = await async_client.post(
        f"/operations/inventory-counts/{count['id']}/found",
        headers=setup.headers,
        json={
            "barcodes": [barcode],
            "container_kind": "box",
            "container_id": str(empty_box_id),
            "scan_id": str(uuid.uuid4()),
        },
    )
    assert found.status_code == 200, found.text
    line = next(
        item
        for item in found.json()["count"]["lines"]
        if item["product_id"] == str(found_product)
    )
    assert line["container_id"] == str(empty_box_id)
    assert line["actual_quantity"] == 1


@pytest.mark.asyncio
async def test_inventory_count_reports_ordinary_and_fbs_deductions(
    async_client: AsyncClient,
) -> None:
    from app.models.fbs_binding_stock_pool import FbsBindingStockPool
    from app.models.fbs_warehouse_binding import FbsWarehouseBinding

    setup = await _tenant(async_client, "FbsBreakdown")
    seller_id = await _seller(async_client, setup, "ФБС селлер")
    product_id = await _product(async_client, setup, name="Футболка", seller_id=seller_id)
    await _balance(setup, product_id, 400)
    async with SessionLocal() as session:
        product = await session.get(Product, product_id)
        assert product is not None
        product.fbs_units_mode = True
        for warehouse_number, quantity in [(501001, 100), (501002, 200)]:
            binding = FbsWarehouseBinding(
                tenant_id=setup.tenant_id, seller_id=seller_id,
                wms_warehouse_id=setup.warehouse_id,
                wb_warehouse_id=warehouse_number, marketplace="wb",
            )
            session.add(binding)
            await session.flush()
            session.add(FbsBindingStockPool(
                tenant_id=setup.tenant_id, binding_id=binding.id,
                product_id=product_id, quantity=quantity,
            ))
        await session.commit()
    count = await _create_all(async_client, setup)
    saved = await async_client.put(
        f"/operations/inventory-counts/{count['id']}/lines",
        headers=setup.headers,
        json={"lines": [{"line_id": count["lines"][0]["id"], "actual_quantity": 250}]},
    )
    assert saved.status_code == 200, saved.text
    posted = await async_client.post(
        f"/operations/inventory-counts/{count['id']}/post", headers=setup.headers,
    )
    assert posted.status_code == 200, posted.text
    summary = await async_client.get(
        "/operations/inventory-balances/summary", headers=setup.headers
    )
    assert summary.status_code == 200, summary.text
    stock = next(row for row in summary.json() if row["product_id"] == str(product_id))
    assert stock["quantity_fbs"] == 250
    assert stock["quantity_free_fbo"] == 0
    assert stock["available"] == 0
    deductions = posted.json()["stock_write_off"]
    assert sum(row["quantity"] for row in deductions if row["marketplace"] is None) == 100
    fbs = [row for row in deductions if row["marketplace"] == "wb"]
    assert sum(row["quantity"] for row in fbs) == 50
    assert all(row["warehouse_id"] in {"501001", "501002"} for row in fbs)
    assert all(row["product_id"] == str(product_id) for row in deductions)
    repeat = await async_client.post(
        f"/operations/inventory-counts/{count['id']}/post", headers=setup.headers,
    )
    assert repeat.status_code == 409
    async with SessionLocal() as session:
        assert await session.scalar(select(func.sum(InventoryBalance.quantity)).where(
            InventoryBalance.product_id == product_id,
        )) == 250
        assert await session.scalar(select(func.sum(FbsBindingStockPool.quantity)).where(
            FbsBindingStockPool.product_id == product_id,
        )) == 250


async def test_inventory_count_manual_line_without_selection_uses_sorting_zone(
    async_client: AsyncClient,
) -> None:
    # Оператор нашёл товар, но штрихкода под рукой нет (стёрт, не наклеен) —
    # ищет по каталогу и вводит количество сразу, а не сканирует по штуке.
    # Ничего не выделено — строка уходит в зону сортировки, как и находка без
    # открытой тары или ячейки (тот же резолвер адреса, что у /found).
    setup = await _tenant(async_client, "ManualNoSelect")
    # Документ по всем селлерам сразу — filters без seller_id, как в
    # InventoryCreateDialog при пустом «Селлер» (emptyLabel «Все селлеры»).
    seller_id = await _seller(async_client, setup, "Любой селлер")
    product = await _product(async_client, setup, name="Товар руками", seller_id=seller_id)
    count = await _create_all(async_client, setup)
    assert count["fill"]["seller_id"] is None

    res = await async_client.post(
        f"/operations/inventory-counts/{count['id']}/manual-line",
        headers=setup.headers,
        json={"product_id": str(product), "quantity": 3},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["expected_quantity"] == 0
    assert "ничего не числится" in body["notice"]
    line = next(
        item for item in body["count"]["lines"] if item["product_id"] == str(product)
    )
    assert line["actual_quantity"] == 3
    assert line["expected_quantity"] == 0
    assert line["container_kind"] is None
    assert line["container_id"] is None

    async with SessionLocal() as session:
        sorting = await get_or_create_sorting_location(
            session, setup.tenant_id, setup.warehouse_id
        )
        db_line = await session.scalar(
            select(InventoryCountLine).where(InventoryCountLine.product_id == product)
        )
        assert db_line is not None
        assert db_line.storage_location_id == sorting.id


@pytest.mark.asyncio
async def test_inventory_count_manual_line_into_selected_container_binds_its_location(
    async_client: AsyncClient,
) -> None:
    # Выделение стояло на коробе (задача 2) — количество идёт в этот короб, а
    # адрес строки сервер берёт из карточки короба, а не выдумывает сам.
    setup = await _tenant(async_client, "ManualContainer")
    product = await _product(async_client, setup, name="Товар в короб руками")
    _pallet_id, box_id, _cargo_place_id, _empty_box_id = await _containers(setup)
    count = await _create_all(async_client, setup)

    res = await async_client.post(
        f"/operations/inventory-counts/{count['id']}/manual-line",
        headers=setup.headers,
        json={
            "product_id": str(product),
            "quantity": 2,
            "container_kind": "box",
            "container_id": str(box_id),
        },
    )
    assert res.status_code == 200, res.text
    line = next(
        item
        for item in res.json()["count"]["lines"]
        if item["product_id"] == str(product)
    )
    assert line["container_kind"] == "box"
    assert line["container_id"] == str(box_id)
    assert line["storage_location_id"] == str(setup.location_id)
    assert line["actual_quantity"] == 2


@pytest.mark.asyncio
async def test_inventory_count_manual_line_into_selected_cell(
    async_client: AsyncClient,
) -> None:
    # Выделение стояло на ячейке, а не на коробе — постановка явно описывает
    # только случай с коробом (п. 6) и случай без выделения (п. 7); ячейку
    # ведём тем же путём, что и находка с открытой ячейкой (cell_id без
    # тары) — иначе выбрать ячейку в задаче 2 было бы нечем воспользоваться.
    setup = await _tenant(async_client, "ManualCell")
    product = await _product(async_client, setup, name="Товар в ячейку руками")
    count = await _create_all(async_client, setup)

    res = await async_client.post(
        f"/operations/inventory-counts/{count['id']}/manual-line",
        headers=setup.headers,
        json={
            "product_id": str(product),
            "quantity": 1,
            "cell_id": str(setup.location_id),
        },
    )
    assert res.status_code == 200, res.text
    line = next(
        item
        for item in res.json()["count"]["lines"]
        if item["product_id"] == str(product)
    )
    assert line["container_kind"] is None
    assert line["container_id"] is None
    assert line["storage_location_id"] == str(setup.location_id)
    assert line["actual_quantity"] == 1


@pytest.mark.asyncio
async def test_inventory_count_manual_line_merges_into_existing_line_at_same_place(
    async_client: AsyncClient,
) -> None:
    # Тот же товар в то же место добавляют второй раз (например, нашли ещё) —
    # прибавляем к уже насчитанному, а не заводим вторую строку поверх первой:
    # уникальный индекс документа (product+location+container) этого и не
    # позволил бы, а прибавление — тот же ответ, что и у повторного скана.
    setup = await _tenant(async_client, "ManualMerge")
    product = await _product(async_client, setup, name="Товар дважды руками")
    count = await _create_all(async_client, setup)

    first = await async_client.post(
        f"/operations/inventory-counts/{count['id']}/manual-line",
        headers=setup.headers,
        json={"product_id": str(product), "quantity": 2},
    )
    assert first.status_code == 200, first.text

    second = await async_client.post(
        f"/operations/inventory-counts/{count['id']}/manual-line",
        headers=setup.headers,
        json={"product_id": str(product), "quantity": 5},
    )
    assert second.status_code == 200, second.text
    lines = [
        item
        for item in second.json()["count"]["lines"]
        if item["product_id"] == str(product)
    ]
    assert len(lines) == 1
    assert lines[0]["actual_quantity"] == 7


@pytest.mark.asyncio
async def test_inventory_count_manual_line_rejects_product_from_other_seller(
    async_client: AsyncClient,
) -> None:
    # Документ заведён по конкретному селлеру — модалка обязана предлагать
    # только его товары, но проверка не может жить только на экране: запрос с
    # чужим product_id сервер обязан отклонить сам.
    setup = await _tenant(async_client, "ManualSellerScope")
    seller_a = await _seller(async_client, setup, "Селлер А")
    seller_b = await _seller(async_client, setup, "Селлер Б")
    product_a = await _product(async_client, setup, name="Товар А", seller_id=seller_a)
    product_b = await _product(async_client, setup, name="Товар Б", seller_id=seller_b)
    await _balance(setup, product_a, 1)

    res = await async_client.post(
        "/operations/inventory-counts",
        headers=setup.headers,
        json={
            "source": "planned",
            "filters": {"seller_id": str(seller_a), "warehouse_id": str(setup.warehouse_id)},
        },
    )
    assert res.status_code == 201, res.text
    count = res.json()
    assert count["seller_id"] == str(seller_a)

    blocked = await async_client.post(
        f"/operations/inventory-counts/{count['id']}/manual-line",
        headers=setup.headers,
        json={"product_id": str(product_b), "quantity": 1},
    )
    assert blocked.status_code == 404
    assert blocked.json()["detail"] == "product_not_found"

    allowed = await async_client.post(
        f"/operations/inventory-counts/{count['id']}/manual-line",
        headers=setup.headers,
        json={"product_id": str(product_a), "quantity": 1},
    )
    assert allowed.status_code == 200, allowed.text


@pytest.mark.asyncio
async def test_inventory_count_manual_line_rejects_posted_document(
    async_client: AsyncClient,
) -> None:
    # Как и создание тары (задача 1) и правка факта, добавление строки должно
    # быть заперто статусом документа на сервере, а не только кнопкой на экране.
    setup = await _tenant(async_client, "ManualPostedNo")
    product = await _product(async_client, setup, name="Товар для проводки руками")
    other_product = await _product(async_client, setup, name="Учтённый товар")
    await _balance(setup, other_product, 2)
    count = await _create_all(async_client, setup)
    line = count["lines"][0]
    saved = await async_client.put(
        f"/operations/inventory-counts/{count['id']}/lines",
        headers=setup.headers,
        json={"lines": [{"line_id": line["id"], "actual_quantity": 2}]},
    )
    assert saved.status_code == 200, saved.text
    posted = await async_client.post(
        f"/operations/inventory-counts/{count['id']}/post", headers=setup.headers
    )
    assert posted.status_code == 200, posted.text

    response = await async_client.post(
        f"/operations/inventory-counts/{count['id']}/manual-line",
        headers=setup.headers,
        json={"product_id": str(product), "quantity": 1},
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "count_not_editable"


@pytest.mark.asyncio
async def test_inventory_count_manual_line_rejects_non_positive_quantity(
    async_client: AsyncClient,
) -> None:
    setup = await _tenant(async_client, "ManualZeroQty")
    product = await _product(async_client, setup, name="Товар с нулём")
    count = await _create_all(async_client, setup)

    response = await async_client.post(
        f"/operations/inventory-counts/{count['id']}/manual-line",
        headers=setup.headers,
        json={"product_id": str(product), "quantity": 0},
    )
    assert response.status_code == 422


# WMS-153: тара, созданная через ручку документа, должна попадать в выбранную
# оператором ячейку — а не «на складе без адреса», как раньше. Сама механика
# хранения адреса живёт в pallet_service/warehouse_box_service; здесь мы
# проверяем, что кнопка «Создать короб/палету/грузоместо» с выделенной ячейкой
# доводит выбор до объектов.
@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["box", "cargo_place", "pallet"])
async def test_inventory_count_create_container_places_into_selected_cell(
    async_client: AsyncClient, kind: str,
) -> None:
    setup = await _tenant(async_client, "CellPlacement")
    count = await _create_all(async_client, setup)

    response = await async_client.post(
        f"/operations/inventory-counts/{count['id']}/containers",
        headers=setup.headers,
        json={"kind": kind, "cell_id": str(setup.location_id)},
    )
    assert response.status_code == 200, response.text

    async with SessionLocal() as session:
        link_row = (
            await session.execute(
                select(InventoryCountCreatedContainer).where(
                    InventoryCountCreatedContainer.count_id
                    == uuid.UUID(str(count["id"]))
                )
            )
        ).scalar_one()
        model = Pallet if kind == "pallet" else WarehouseBox
        obj = await session.get(model, link_row.container_id)
        assert obj is not None
        assert obj.storage_location_id == setup.location_id


# WMS-153: чужая ячейка (или удалённая) не должна принимать тару — иначе одна
# ошибочная подстановка id пересаживает объект в другой склад.
@pytest.mark.asyncio
async def test_inventory_count_create_container_rejects_foreign_cell(
    async_client: AsyncClient,
) -> None:
    setup = await _tenant(async_client, "ForeignCell")
    other = await _tenant(async_client, "ForeignCellOther")
    count = await _create_all(async_client, setup)

    response = await async_client.post(
        f"/operations/inventory-counts/{count['id']}/containers",
        headers=setup.headers,
        json={"kind": "box", "cell_id": str(other.location_id)},
    )
    # Ячейка чужого склада для этого документа не найдена — сервер отвечает 404
    # тем же кодом, что и «не нашли объект», чтобы клиент не гадал маппинг.
    assert response.status_code == 404
    assert response.json()["detail"] == "storage_location_not_found"


# WMS-153: обратная совместимость — без cell_id сервер по-прежнему создаёт
# тару «на складе», и старые точки входа (мобильный ТСД, диалог наполнения
# короба) продолжают работать.
@pytest.mark.asyncio
async def test_inventory_count_create_container_without_cell_still_works(
    async_client: AsyncClient,
) -> None:
    setup = await _tenant(async_client, "NoCellStillWorks")
    count = await _create_all(async_client, setup)

    response = await async_client.post(
        f"/operations/inventory-counts/{count['id']}/containers",
        headers=setup.headers,
        json={"kind": "box"},
    )
    assert response.status_code == 200, response.text

    async with SessionLocal() as session:
        link_row = (
            await session.execute(
                select(InventoryCountCreatedContainer).where(
                    InventoryCountCreatedContainer.count_id
                    == uuid.UUID(str(count["id"]))
                )
            )
        ).scalar_one()
        obj = await session.get(WarehouseBox, link_row.container_id)
        assert obj is not None
        assert obj.storage_location_id is None


# WMS-155: комментарий редактируется через ту же ручку сохранения фактов —
# отдельного PUT для документа не заводим (см. правило «Не плоди сущностей»).
# По умолчанию — не трогаем комментарий, чтобы не затирать чужой.
@pytest.mark.asyncio
async def test_inventory_count_lines_put_preserves_comment_by_default(
    async_client: AsyncClient,
) -> None:
    setup = await _tenant(async_client, "CommentDefault")
    product = await _product(async_client, setup, name="Товар с комментарием")
    await _balance(setup, product, 5)

    created = await async_client.post(
        "/operations/inventory-counts",
        headers=setup.headers,
        json={
            "source": "planned",
            "filters": {"warehouse_id": str(setup.warehouse_id), "all": True},
            "comment": "Первичный",
        },
    )
    assert created.status_code == 201, created.text
    count = created.json()

    saved = await async_client.put(
        f"/operations/inventory-counts/{count['id']}/lines",
        headers=setup.headers,
        json={"lines": [
            {"line_id": count["lines"][0]["id"], "actual_quantity": 4},
        ]},
    )
    assert saved.status_code == 200
    assert saved.json()["comment"] == "Первичный"


# WMS-155: если оператор явно правил поле, шлём флаг + значение и сервер
# сохраняет новое.
@pytest.mark.asyncio
async def test_inventory_count_lines_put_updates_comment_when_flag_set(
    async_client: AsyncClient,
) -> None:
    setup = await _tenant(async_client, "CommentUpdate")
    product = await _product(async_client, setup, name="Товар с новой причиной")
    await _balance(setup, product, 5)

    created = await async_client.post(
        "/operations/inventory-counts",
        headers=setup.headers,
        json={
            "source": "planned",
            "filters": {"warehouse_id": str(setup.warehouse_id), "all": True},
            "comment": "Первичный",
        },
    )
    count = created.json()

    saved = await async_client.put(
        f"/operations/inventory-counts/{count['id']}/lines",
        headers=setup.headers,
        json={
            "lines": [{"line_id": count["lines"][0]["id"], "actual_quantity": 4}],
            "update_comment": True,
            "comment": "Пересорт, чужой товар",
        },
    )
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["comment"] == "Пересорт, чужой товар"

    # Переоткрытие документа возвращает новое значение — сервер сохранил на бэке,
    # а не только в ответе ручки.
    reopened = await async_client.get(
        f"/operations/inventory-counts/{count['id']}", headers=setup.headers
    )
    assert reopened.status_code == 200
    assert reopened.json()["comment"] == "Пересорт, чужой товар"


# WMS-155: пустая строка со включённым флагом = стереть комментарий.
@pytest.mark.asyncio
async def test_inventory_count_lines_put_clears_comment_with_empty_string(
    async_client: AsyncClient,
) -> None:
    setup = await _tenant(async_client, "CommentClear")
    product = await _product(async_client, setup, name="Товар без причины")
    await _balance(setup, product, 5)

    created = await async_client.post(
        "/operations/inventory-counts",
        headers=setup.headers,
        json={
            "source": "planned",
            "filters": {"warehouse_id": str(setup.warehouse_id), "all": True},
            "comment": "Раньше писали",
        },
    )
    count = created.json()

    cleared = await async_client.put(
        f"/operations/inventory-counts/{count['id']}/lines",
        headers=setup.headers,
        json={
            "lines": [{"line_id": count["lines"][0]["id"], "actual_quantity": 4}],
            "update_comment": True,
            "comment": "",
        },
    )
    assert cleared.status_code == 200
    # Пустая строка на выдаче — договор API уже был «строка, никогда null».
    assert cleared.json()["comment"] == ""


def _container_ids_in_tree(body: dict[str, object]) -> set[str]:
    def walk(nodes: list[dict[str, object]]) -> set[str]:
        found: set[str] = set()
        for node in nodes:
            if node["kind"] == "product":
                continue
            found.add(str(node["id"]))
            found |= walk(node["children"])  # type: ignore[arg-type]
        return found

    out: set[str] = set()
    for cell in body["cells"]:  # type: ignore[union-attr]
        out |= walk(cell["children"])  # type: ignore[arg-type,index]
    return out


async def _create_container(
    async_client: AsyncClient,
    setup: TenantSetup,
    count_id: str,
    kind: str,
    *,
    cell_id: uuid.UUID | None = None,
) -> uuid.UUID:
    payload: dict[str, object] = {"kind": kind}
    if cell_id is not None:
        payload["cell_id"] = str(cell_id)
    response = await async_client.post(
        f"/operations/inventory-counts/{count_id}/containers",
        headers=setup.headers,
        json=payload,
    )
    assert response.status_code == 200, response.text
    created = _container_ids_in_tree(response.json())
    assert len(created) == 1, created
    return uuid.UUID(next(iter(created)))


@pytest.mark.asyncio
async def test_inventory_count_move_line_transfers_balance_and_line_address(
    async_client: AsyncClient,
) -> None:
    # Задача 2 (WMS-153): «Переложить товар в тару» переносит и физический
    # остаток (тот же механизм, что и на карте склада), и адрес строки
    # документа — иначе после переноса строка показывала бы недостачу там,
    # откуда товар уже забрали, хотя оператор его просто переложил.
    setup = await _tenant(async_client, "MoveLine")
    product = await _product(async_client, setup, name="Товар для переноса")
    await _balance(setup, product, 4)
    count = await _create_all(async_client, setup)
    # Короб заводим в той же ячейке, что и остаток товара, — реалистичный
    # случай (задача 1): оператор стоит у полки, короб появляется тут же.
    box_id = await _create_container(
        async_client, setup, count["id"], "box", cell_id=setup.location_id
    )
    line = next(item for item in count["lines"] if item["product_id"] == str(product))
    assert line["container_kind"] is None
    assert line["storage_location_id"] == str(setup.location_id)

    response = await async_client.post(
        f"/operations/inventory-counts/{count['id']}/lines/{line['id']}/move",
        headers=setup.headers,
        json={"container_kind": "box", "container_id": str(box_id)},
    )
    assert response.status_code == 200, response.text
    moved = next(
        item for item in response.json()["lines"] if item["product_id"] == str(product)
    )
    assert moved["id"] == line["id"]
    assert moved["container_kind"] == "box"
    assert moved["container_id"] == str(box_id)
    assert moved["storage_location_id"] == str(setup.location_id)

    async with SessionLocal() as session:
        loose = await session.scalar(
            select(InventoryBalance).where(
                InventoryBalance.product_id == product,
                InventoryBalance.storage_location_id == setup.location_id,
                InventoryBalance.container_id.is_(None),
            )
        )
        assert loose is None or loose.quantity == 0
        in_box = await session.scalar(
            select(InventoryBalance).where(
                InventoryBalance.product_id == product,
                InventoryBalance.container_kind == "box",
                InventoryBalance.container_id == box_id,
            )
        )
        assert in_box is not None
        assert in_box.quantity == 4


@pytest.mark.asyncio
async def test_inventory_count_move_line_rejects_when_already_there(
    async_client: AsyncClient,
) -> None:
    setup = await _tenant(async_client, "MoveAlreadyThere")
    product = await _product(async_client, setup, name="Товар уже в таре")
    _pallet_id, box_id, _cargo_place_id, _empty_box_id = await _containers(setup)
    await _balance(
        setup, product, 2, location_id=setup.location_id, container_kind="box", container_id=box_id
    )
    count = await _create_all(async_client, setup)
    line = next(item for item in count["lines"] if item["product_id"] == str(product))

    response = await async_client.post(
        f"/operations/inventory-counts/{count['id']}/lines/{line['id']}/move",
        headers=setup.headers,
        json={"container_kind": "box", "container_id": str(box_id)},
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "already_there"


@pytest.mark.asyncio
async def test_inventory_count_move_line_rejects_product_already_at_destination(
    async_client: AsyncClient,
) -> None:
    # Один и тот же товар уже посчитан отдельной строкой в целевой таре —
    # сервер отказывает понятным сообщением вместо тихого слияния двух
    # независимо введённых фактов.
    setup = await _tenant(async_client, "MoveConflict")
    product = await _product(async_client, setup, name="Товар с конфликтом")
    box_id = await _create_container(
        async_client, setup, (await _create_all(async_client, setup))["id"], "box"
    )
    # Остаток по товару в двух местах сразу: россыпью в ячейке и в коробе.
    await _balance(setup, product, 3, location_id=setup.location_id)
    await _balance(
        setup, product, 1, location_id=setup.location_id, container_kind="box", container_id=box_id
    )
    count = await _create_all(async_client, setup)
    loose_line = next(
        item
        for item in count["lines"]
        if item["product_id"] == str(product) and item["container_kind"] is None
    )

    response = await async_client.post(
        f"/operations/inventory-counts/{count['id']}/lines/{loose_line['id']}/move",
        headers=setup.headers,
        json={"container_kind": "box", "container_id": str(box_id)},
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "product_already_at_destination"


@pytest.mark.asyncio
async def test_inventory_count_move_line_rejects_empty_source(
    async_client: AsyncClient,
) -> None:
    # Строка добавлена руками (задача 3 постановки от 03.09.2026), реального
    # остатка за ней нет — переносить нечего, и сервер обязан сказать это
    # прямо, а не молча создать перенос из воздуха.
    setup = await _tenant(async_client, "MoveEmptySource")
    product = await _product(async_client, setup, name="Товар без остатка")
    count = await _create_all(async_client, setup)
    box_id = await _create_container(async_client, setup, count["id"], "box")
    added = await async_client.post(
        f"/operations/inventory-counts/{count['id']}/manual-line",
        headers=setup.headers,
        json={"product_id": str(product), "quantity": 2},
    )
    assert added.status_code == 200, added.text
    line = next(
        item
        for item in added.json()["count"]["lines"]
        if item["product_id"] == str(product)
    )

    response = await async_client.post(
        f"/operations/inventory-counts/{count['id']}/lines/{line['id']}/move",
        headers=setup.headers,
        json={"container_kind": "box", "container_id": str(box_id)},
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "move_source_empty"


@pytest.mark.asyncio
async def test_inventory_count_move_line_rejects_posted_document(
    async_client: AsyncClient,
) -> None:
    setup = await _tenant(async_client, "MovePostedNo")
    product = await _product(async_client, setup, name="Товар для проводки")
    await _balance(setup, product, 2)
    count = await _create_all(async_client, setup)
    box_id = await _create_container(async_client, setup, count["id"], "box")
    line = next(item for item in count["lines"] if item["product_id"] == str(product))
    saved = await async_client.put(
        f"/operations/inventory-counts/{count['id']}/lines",
        headers=setup.headers,
        json={"lines": [{"line_id": line["id"], "actual_quantity": 2}]},
    )
    assert saved.status_code == 200, saved.text
    posted = await async_client.post(
        f"/operations/inventory-counts/{count['id']}/post", headers=setup.headers
    )
    assert posted.status_code == 200, posted.text

    response = await async_client.post(
        f"/operations/inventory-counts/{count['id']}/lines/{line['id']}/move",
        headers=setup.headers,
        json={"container_kind": "box", "container_id": str(box_id)},
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "not_editable"


@pytest.mark.asyncio
async def test_inventory_count_delete_container_removes_empty_box(
    async_client: AsyncClient,
) -> None:
    # Задача 3 (WMS-153): пустую тару, заведённую этой же кнопкой «Создать
    # короб», можно удалить прямо из документа.
    setup = await _tenant(async_client, "DeleteEmptyBox")
    count = await _create_all(async_client, setup)
    box_id = await _create_container(async_client, setup, count["id"], "box")

    response = await async_client.delete(
        f"/operations/inventory-counts/{count['id']}/containers/box/{box_id}",
        headers=setup.headers,
    )
    assert response.status_code == 200, response.text
    assert str(box_id) not in _container_ids_in_tree(response.json())
    assert str(box_id) not in {
        item["id"] for item in response.json()["scannable_containers"]
    }

    async with SessionLocal() as session:
        assert await session.get(WarehouseBox, box_id) is None


@pytest.mark.asyncio
async def test_inventory_count_delete_container_removes_empty_pallet(
    async_client: AsyncClient,
) -> None:
    setup = await _tenant(async_client, "DeleteEmptyPallet")
    count = await _create_all(async_client, setup)
    pallet_id = await _create_container(async_client, setup, count["id"], "pallet")

    response = await async_client.delete(
        f"/operations/inventory-counts/{count['id']}/containers/pallet/{pallet_id}",
        headers=setup.headers,
    )
    assert response.status_code == 200, response.text

    async with SessionLocal() as session:
        pallet = await session.get(Pallet, pallet_id)
        assert pallet is not None
        assert pallet.disbanded_at is not None


@pytest.mark.asyncio
async def test_inventory_count_delete_container_rejects_non_empty(
    async_client: AsyncClient,
) -> None:
    # Ручки удаления не было вовсе, и главное требование постановки —
    # удалять можно только по-настоящему пустую тару, иначе отказ понятным
    # сообщением. Проверяем по живому остатку, а не по строкам этого
    # документа: документ может быть сужен по селлеру/категории, и «пусто в
    # документе» — не то же самое, что «пусто физически».
    setup = await _tenant(async_client, "DeleteNonEmpty")
    seller_id = await _seller(async_client, setup, "Другой селлер")
    other_product = await _product(
        async_client, setup, name="Чужой товар", seller_id=seller_id
    )
    count_for_all = await _create_all(async_client, setup)
    box_id = await _create_container(async_client, setup, count_for_all["id"], "box")
    # Остаток кладём ПОСЛЕ наполнения документа и от другого селлера — у
    # документа этого селлера в строках нет, но физически короб не пуст.
    await _balance(
        setup,
        other_product,
        5,
        location_id=setup.location_id,
        container_kind="box",
        container_id=box_id,
    )

    response = await async_client.delete(
        f"/operations/inventory-counts/{count_for_all['id']}/containers/box/{box_id}",
        headers=setup.headers,
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "container_not_empty"

    async with SessionLocal() as session:
        assert await session.get(WarehouseBox, box_id) is not None


@pytest.mark.asyncio
async def test_inventory_count_delete_container_rejects_pallet_with_children(
    async_client: AsyncClient,
) -> None:
    setup = await _tenant(async_client, "DeletePalletWithKids")
    pallet_id, _box_id, _cargo_place_id, _empty_box_id = await _containers(setup)
    count = await _create_all(async_client, setup)

    response = await async_client.delete(
        f"/operations/inventory-counts/{count['id']}/containers/pallet/{pallet_id}",
        headers=setup.headers,
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "container_not_empty"


@pytest.mark.asyncio
async def test_inventory_count_delete_container_rejects_inbound_linked(
    async_client: AsyncClient,
) -> None:
    # Тара приёмки — другой процесс со своими инвариантами; экран пересчёта
    # её не трогает, даже если по остатку она сейчас пуста.
    setup = await _tenant(async_client, "DeleteInboundLinked")
    async with SessionLocal() as session:
        request = InboundIntakeRequest(
            tenant_id=setup.tenant_id,
            warehouse_id=setup.warehouse_id,
            status="receiving",
        )
        session.add(request)
        await session.flush()
        box = WarehouseBox(
            tenant_id=setup.tenant_id,
            warehouse_id=setup.warehouse_id,
            internal_barcode=f"INB-{uuid.uuid4().hex}",
            storage_location_id=setup.location_id,
            inbound_request_id=request.id,
        )
        session.add(box)
        await session.commit()
        box_id = box.id
    count = await _create_all(async_client, setup)

    response = await async_client.delete(
        f"/operations/inventory-counts/{count['id']}/containers/box/{box_id}",
        headers=setup.headers,
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "container_linked_to_inbound"


@pytest.mark.asyncio
async def test_inventory_count_delete_container_rejects_posted_document(
    async_client: AsyncClient,
) -> None:
    setup = await _tenant(async_client, "DeletePostedNo")
    product = await _product(async_client, setup, name="Товар для проводки")
    await _balance(setup, product, 2)
    count = await _create_all(async_client, setup)
    box_id = await _create_container(async_client, setup, count["id"], "box")
    line = next(item for item in count["lines"] if item["product_id"] == str(product))
    saved = await async_client.put(
        f"/operations/inventory-counts/{count['id']}/lines",
        headers=setup.headers,
        json={"lines": [{"line_id": line["id"], "actual_quantity": 2}]},
    )
    assert saved.status_code == 200, saved.text
    posted = await async_client.post(
        f"/operations/inventory-counts/{count['id']}/post", headers=setup.headers
    )
    assert posted.status_code == 200, posted.text

    response = await async_client.delete(
        f"/operations/inventory-counts/{count['id']}/containers/box/{box_id}",
        headers=setup.headers,
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "not_editable"


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["box", "cargo_place", "pallet"])
async def test_empty_container_without_goods_is_confirmed_reloaded_and_removed_on_post(
    async_client: AsyncClient, kind: str,
) -> None:
    setup = await _tenant(async_client, "EmptyNoRows")
    count = await _create_all(async_client, setup)
    cid = await _create_container(async_client, setup, count["id"], kind, cell_id=setup.location_id)
    marked = await async_client.post(
        f"/operations/inventory-counts/{count['id']}/empty-place", headers=setup.headers,
        json={"kind": kind, "id": str(cid)},
    )
    assert marked.status_code == 200, marked.text
    reopened = await async_client.get(
        f"/operations/inventory-counts/{count['id']}", headers=setup.headers,
    )
    assert reopened.json()["empty_places"] == [{"kind": kind, "id": str(cid)}]
    async with SessionLocal() as session:
        assert await session.get(Pallet if kind == "pallet" else WarehouseBox, cid) is not None
    posted = await async_client.post(
        f"/operations/inventory-counts/{count['id']}/post", headers=setup.headers,
    )
    assert posted.status_code == 200, posted.text
    async with SessionLocal() as session:
        if kind == "pallet":
            pallet = await session.get(Pallet, cid)
            assert pallet is not None and pallet.disbanded_at is not None
        else:
            assert await session.get(WarehouseBox, cid) is None
        assert await session.scalar(select(func.count(InventoryMovement.id))) == 0


@pytest.mark.asyncio
async def test_confirm_empty_zeros_previously_counted_goods_and_removes_container(
    async_client: AsyncClient,
) -> None:
    setup = await _tenant(async_client, "EmptyRecount")
    product = await _product(async_client, setup, name="Counted product")
    count = await _create_all(async_client, setup)
    cid = await _create_container(
        async_client, setup, count["id"], "box", cell_id=setup.location_id,
    )
    await _balance(setup, product, 3, container_kind="box", container_id=cid)
    count = await _create_all(async_client, setup)
    saved = await async_client.put(
        f"/operations/inventory-counts/{count['id']}/lines", headers=setup.headers,
        json={"lines": [{"line_id": count["lines"][0]["id"], "actual_quantity": 2}]},
    )
    assert saved.status_code == 200
    marked = await async_client.post(
        f"/operations/inventory-counts/{count['id']}/empty-place", headers=setup.headers,
        json={"kind": "cell", "id": str(setup.location_id)},
    )
    assert marked.status_code == 200, marked.text
    assert marked.json()["lines"][0]["actual_quantity"] == 0
    posted = await async_client.post(
        f"/operations/inventory-counts/{count['id']}/post", headers=setup.headers,
    )
    assert posted.status_code == 200, posted.text
    async with SessionLocal() as session:
        assert await session.get(WarehouseBox, cid) is None
        assert await session.scalar(select(InventoryBalance.quantity).where(
            InventoryBalance.product_id == product,
        )) == 0
        assert await session.scalar(select(InventoryMovement.quantity_delta).where(
            InventoryMovement.product_id == product,
        )) == -3


@pytest.mark.asyncio
async def test_stale_comment_update_preserves_other_operators_edit(
    async_client: AsyncClient,
) -> None:
    setup = await _tenant(async_client, "CommentConflict")
    count = await _create_all(async_client, setup)
    path = f"/operations/inventory-counts/{count['id']}/lines"
    first = await async_client.put(path, headers=setup.headers, json={
        "lines": [], "update_comment": True, "expected_comment": "", "comment": "Other operator",
    })
    assert first.status_code == 200, first.text
    second = await async_client.put(path, headers=setup.headers, json={
        "lines": [], "update_comment": True, "expected_comment": "", "comment": "Stale overwrite",
    })
    assert second.status_code == 409 and second.json()["detail"] == "comment_changed"
    reread = await async_client.get(
        f"/operations/inventory-counts/{count['id']}", headers=setup.headers,
    )
    assert reread.json()["comment"] == "Other operator"


@pytest.mark.asyncio
async def test_recount_after_empty_confirmation_keeps_container(async_client: AsyncClient) -> None:
    setup = await _tenant(async_client, "RecountAfterEmpty")
    product = await _product(async_client, setup, name="Recounted goods")
    count = await _create_all(async_client, setup)
    cid = await _create_container(
        async_client, setup, count["id"], "box", cell_id=setup.location_id,
    )
    base = f"/operations/inventory-counts/{count['id']}"
    marked = await async_client.post(f"{base}/empty-place", headers=setup.headers,
                                     json={"kind": "box", "id": str(cid)})
    assert marked.status_code == 200, marked.text
    found = await async_client.post(f"{base}/manual-line", headers=setup.headers, json={
        "product_id": str(product), "quantity": 2,
        "container_kind": "box", "container_id": str(cid),
    })
    assert found.status_code == 200, found.text
    assert found.json()["count"]["empty_places"] == []
    posted = await async_client.post(f"{base}/post", headers=setup.headers)
    assert posted.status_code == 200, posted.text
    async with SessionLocal() as session:
        assert await session.get(WarehouseBox, cid) is not None
        assert await session.scalar(select(InventoryBalance.quantity).where(
            InventoryBalance.product_id == product,
        )) == 2


@pytest.mark.asyncio
async def test_new_stock_in_confirmed_empty_container_blocks_removal_atomically(
    async_client: AsyncClient,
) -> None:
    setup = await _tenant(async_client, "EmptyChanged")
    product = await _product(async_client, setup, name="Later incoming goods")
    count = await _create_all(async_client, setup)
    cid = await _create_container(
        async_client, setup, count["id"], "box", cell_id=setup.location_id,
    )
    base = f"/operations/inventory-counts/{count['id']}"
    marked = await async_client.post(f"{base}/empty-place", headers=setup.headers,
                                     json={"kind": "box", "id": str(cid)})
    assert marked.status_code == 200, marked.text
    await _balance(setup, product, 3, container_kind="box", container_id=cid)
    posted = await async_client.post(f"{base}/post", headers=setup.headers)
    assert posted.status_code == 409 and posted.json()["detail"] == "container_not_empty"
    async with SessionLocal() as session:
        assert await session.get(WarehouseBox, cid) is not None
        assert await session.scalar(select(InventoryBalance.quantity).where(
            InventoryBalance.product_id == product,
        )) == 3
        assert await session.scalar(select(func.count(InventoryMovement.id))) == 0


@pytest.mark.asyncio
async def test_save_rereads_stale_count_status(async_client: AsyncClient) -> None:
    setup = await _tenant(async_client, "StaleCount")
    product = await _product(async_client, setup, name="Count then post")
    await _balance(setup, product, 2)
    count = await _create_all(async_client, setup)
    count_id = uuid.UUID(count["id"])
    line_id = uuid.UUID(count["lines"][0]["id"])
    async with SessionLocal() as stale_session:
        stale = await inventory_count_service.get_count(stale_session, setup.tenant_id, count_id)
        assert stale is not None and stale.status == "draft"
        saved = await async_client.put(f"/operations/inventory-counts/{count_id}/lines",
                                      headers=setup.headers,
                                      json={"lines": [{"line_id": str(line_id),
                                                       "actual_quantity": 2}]})
        assert saved.status_code == 200, saved.text
        posted = await async_client.post(f"/operations/inventory-counts/{count_id}/post",
                                        headers=setup.headers)
        assert posted.status_code == 200, posted.text
        with pytest.raises(inventory_count_service.InventoryCountError, match="not_editable"):
            await inventory_count_service.save_actuals(stale_session, setup.tenant_id, count_id,
                                                      [(line_id, 1)], comment="Too late")


@pytest.mark.asyncio
async def test_truly_empty_cell_confirmation_survives_reload_and_posts_without_movements(
    async_client: AsyncClient,
) -> None:
    setup = await _tenant(async_client, "EmptyCell")
    count = await _create_all(async_client, setup)
    base = f"/operations/inventory-counts/{count['id']}"
    marked = await async_client.post(f"{base}/empty-place", headers=setup.headers,
                                     json={"kind": "cell", "id": str(setup.location_id)})
    assert marked.status_code == 200, marked.text
    read = await async_client.get(base, headers=setup.headers)
    assert read.json()["empty_places"] == [{"kind": "cell", "id": str(setup.location_id)}]
    assert any(cell["id"] == str(setup.location_id) for cell in read.json()["cells"])
    posted = await async_client.post(f"{base}/post", headers=setup.headers)
    assert posted.status_code == 200, posted.text
    async with SessionLocal() as session:
        assert await session.scalar(select(func.count(InventoryMovement.id))) == 0


@pytest.mark.asyncio
async def test_move_rejects_destination_stock_missing_from_count(async_client: AsyncClient) -> None:
    setup = await _tenant(async_client, "HiddenDestination")
    product = await _product(async_client, setup, name="Same product at two places")
    await _balance(setup, product, 4)
    count = await _create_all(async_client, setup)
    cid = await _create_container(async_client, setup, count["id"], "box",
                                  cell_id=setup.location_id)
    await _balance(setup, product, 10, container_kind="box", container_id=cid)
    moved = await async_client.post(
        f"/operations/inventory-counts/{count['id']}/lines/{count['lines'][0]['id']}/move",
        headers=setup.headers, json={"container_kind": "box", "container_id": str(cid)},
    )
    assert moved.status_code == 409 and moved.json()["detail"] == "product_already_at_destination"
    async with SessionLocal() as session:
        quantities = list((await session.scalars(select(InventoryBalance.quantity).where(
            InventoryBalance.product_id == product,
        ))).all())
        assert sorted(quantities) == [4, 10]
        assert await session.scalar(select(func.count(InventoryMovement.id))) == 0


@pytest.mark.asyncio
async def test_empty_cell_does_not_schedule_inbound_container_deletion(
    async_client: AsyncClient,
) -> None:
    setup = await _tenant(async_client, "InboundContainerCell")
    async with SessionLocal() as session:
        inbound = InboundIntakeRequest(tenant_id=setup.tenant_id,
                                      warehouse_id=setup.warehouse_id, status="sorting")
        session.add(inbound)
        await session.flush()
        box = WarehouseBox(tenant_id=setup.tenant_id, warehouse_id=setup.warehouse_id,
                           internal_barcode=f"LINKED-{uuid.uuid4().hex}",
                           storage_location_id=setup.location_id, inbound_request_id=inbound.id)
        session.add(box)
        await session.commit()
        cid = box.id
    count = await _create_all(async_client, setup)
    base = f"/operations/inventory-counts/{count['id']}"
    marked = await async_client.post(f"{base}/empty-place", headers=setup.headers,
                                     json={"kind": "cell", "id": str(setup.location_id)})
    assert marked.status_code == 200, marked.text
    assert marked.json()["empty_places"] == [{"kind": "cell", "id": str(setup.location_id)}]
    posted = await async_client.post(f"{base}/post", headers=setup.headers)
    assert posted.status_code == 200, posted.text
    async with SessionLocal() as session:
        assert await session.get(WarehouseBox, cid) is not None
        assert await session.scalar(select(func.count(InventoryMovement.id))) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["box", "cargo_place", "pallet"])
@pytest.mark.parametrize("save_first", [False, True])
async def test_confirmed_empty_container_deleted_by_other_count_is_idempotent(
    async_client: AsyncClient, kind: str, save_first: bool,
) -> None:
    setup = await _tenant(async_client, "AlreadyRemoved")
    count_a = await _create_all(async_client, setup)
    count_b = await _create_all(async_client, setup)
    cid = await _create_container(async_client, setup, count_a["id"], kind,
                                  cell_id=setup.location_id)
    base_a = f"/operations/inventory-counts/{count_a['id']}"
    marked = await async_client.post(f"{base_a}/empty-place", headers=setup.headers,
                                     json={"kind": kind, "id": str(cid)})
    assert marked.status_code == 200, marked.text
    removed = await async_client.delete(
        f"/operations/inventory-counts/{count_b['id']}/containers/{kind}/{cid}",
        headers=setup.headers,
    )
    assert removed.status_code == 200, removed.text
    if save_first:
        for comment in ["After another count removed the container", "Saved again"]:
            saved = await async_client.put(f"{base_a}/lines", headers=setup.headers,
                                           json={"lines": [], "update_comment": True,
                                                 "comment": comment})
            assert saved.status_code == 200, saved.text
            assert saved.json()["comment"] == comment
            assert saved.json()["empty_places"] == [{"kind": kind, "id": str(cid)}]
    posted = await async_client.post(f"{base_a}/post", headers=setup.headers)
    assert posted.status_code == 200, posted.text
    reread = await async_client.get(base_a, headers=setup.headers)
    assert reread.json()["status"] == "posted"
    assert reread.json()["empty_places"] == [{"kind": kind, "id": str(cid)}]
    async with SessionLocal() as session:
        assert await session.scalar(select(func.count(InventoryMovement.id))) == 0
        if kind == "pallet":
            pallet = await session.get(Pallet, cid)
            assert pallet is not None and pallet.disbanded_at is not None
        else:
            assert await session.get(WarehouseBox, cid) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("scope", ["tenant", "warehouse", "kind"])
@pytest.mark.parametrize("operation", ["save", "post"])
async def test_stale_empty_confirmation_does_not_hide_foreign_container(
    async_client: AsyncClient, scope: str, operation: str,
) -> None:
    from app.models.inventory_count import InventoryCount

    setup = await _tenant(async_client, "StaleScope")
    other = await _tenant(async_client, "ForeignScope")
    count = await _create_all(async_client, setup)
    cid = await _create_container(async_client, setup, count["id"], "box",
                                  cell_id=setup.location_id)
    base = f"/operations/inventory-counts/{count['id']}"
    marked = await async_client.post(f"{base}/empty-place", headers=setup.headers,
                                     json={"kind": "box", "id": str(cid)})
    assert marked.status_code == 200, marked.text
    async with SessionLocal() as session:
        box = await session.get(WarehouseBox, cid)
        assert box is not None
        # Synthetic corrupt/stale reference: never reinterpret another scope as deletion.
        if scope == "tenant":
            box.tenant_id = other.tenant_id
            box.warehouse_id = other.warehouse_id
        elif scope == "warehouse":
            default_id = await session.scalar(select(inventory_count_service.Warehouse.id).where(
                inventory_count_service.Warehouse.tenant_id == setup.tenant_id,
                inventory_count_service.Warehouse.id != setup.warehouse_id,
            ))
            assert default_id is not None
            box.warehouse_id = default_id
        else:
            box.container_kind = "cargo_place"
        await session.commit()
    response = (
        await async_client.put(f"{base}/lines", headers=setup.headers,
                               json={"lines": [], "update_comment": True, "comment": "Rejected"})
        if operation == "save" else
        await async_client.post(f"{base}/post", headers=setup.headers)
    )
    assert response.status_code == 404, response.text
    assert response.json()["detail"] == "container_not_found"
    async with SessionLocal() as session:
        assert await session.get(WarehouseBox, cid) is not None
        stored = await session.get(InventoryCount, uuid.UUID(count["id"]))
        assert stored is not None and stored.status == "draft" and not stored.comment
        assert await session.scalar(select(func.count(InventoryMovement.id))) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("orphan_stock", [False, True])
async def test_stale_empty_confirmation_keeps_missing_and_nonempty_errors_distinct(
    async_client: AsyncClient, orphan_stock: bool,
) -> None:
    setup = await _tenant(async_client, "MissingBalance")
    product = await _product(async_client, setup, name="Orphan stock guard")
    count = await _create_all(async_client, setup)
    other = await _create_all(async_client, setup)
    cid = await _create_container(async_client, setup, count["id"], "box",
                                  cell_id=setup.location_id)
    base = f"/operations/inventory-counts/{count['id']}"
    marked = await async_client.post(f"{base}/empty-place", headers=setup.headers,
                                     json={"kind": "box", "id": str(cid)})
    assert marked.status_code == 200, marked.text
    removed = await async_client.delete(
        f"/operations/inventory-counts/{other['id']}/containers/box/{cid}",
        headers=setup.headers,
    )
    assert removed.status_code == 200, removed.text
    if orphan_stock:
        await _balance(setup, product, 3, container_kind="box", container_id=cid)
        posted = await async_client.post(f"{base}/post", headers=setup.headers)
        assert posted.status_code == 409 and posted.json()["detail"] == "container_not_empty"
        async with SessionLocal() as session:
            assert await session.scalar(select(InventoryBalance.quantity).where(
                InventoryBalance.product_id == product,
            )) == 3
            assert await session.scalar(select(func.count(InventoryMovement.id))) == 0
    else:
        # Explicit DELETE is still strict; idempotency is only for a saved confirmation.
        repeated = await async_client.delete(f"{base}/containers/box/{cid}", headers=setup.headers)
        assert repeated.status_code == 404 and repeated.json()["detail"] == "container_not_found"
