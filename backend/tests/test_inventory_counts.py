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
from app.models.inventory_movement import InventoryMovement
from app.models.pallet import Pallet
from app.models.product import Product
from app.models.seller_wildberries_imported_card import SellerWildberriesImportedCard
from app.models.warehouse_box import WarehouseBox
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
async def test_inventory_count_by_empty_container_returns_clear_conflict(
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

    assert response.status_code == 409, response.text
    assert response.json()["detail"] == "container_has_no_stock"


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
        "storage_location_id": str(setup.location_id),
        "container_kind": "box",
        "container_id": str(box_id),
    }
    first = await async_client.post(
        f"/operations/inventory-counts/{count_id}/found", headers=setup.headers, json=body
    )
    assert first.status_code == 200, first.text
    found_line = next(
        line for line in first.json()["lines"] if line["product_id"] == str(surprise)
    )
    assert found_line["expected_quantity"] == 0
    assert found_line["actual_quantity"] == 1
    assert found_line["container_id"] == str(box_id)

    second = await async_client.post(
        f"/operations/inventory-counts/{count_id}/found", headers=setup.headers, json=body
    )
    assert second.status_code == 200, second.text
    surprise_lines = [
        line for line in second.json()["lines"] if line["product_id"] == str(surprise)
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
            "storage_location_id": str(setup.location_id),
            "container_kind": None,
            "container_id": None,
        },
    )
    assert response.status_code == 200, response.text
    line = next(
        line for line in response.json()["lines"] if line["product_id"] == str(surprise)
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
            "storage_location_id": str(setup.location_id),
            "container_kind": "box",
            "container_id": str(alien_box_id),
        },
    )
    assert response.status_code == 404, response.text
    assert response.json()["detail"] == "container_not_found"
