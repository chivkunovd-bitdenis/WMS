from __future__ import annotations

import time
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models.inbound_intake import (
    InboundIntakeBox,
    InboundIntakeBoxLine,
    InboundIntakeCargoPlace,
    InboundIntakeCargoPlaceLine,
    InboundIntakeRequest,
)
from app.models.inventory_balance import InventoryBalance
from app.models.pallet import Pallet
from app.models.product import Product
from app.models.seller import Seller
from app.models.storage_location import StorageLocation
from app.models.tenant import Tenant
from app.models.user import User
from app.models.warehouse import Warehouse
from app.services.sorting_location_service import (
    SORTING_LOCATION_CODE,
    get_or_create_sorting_location,
)


async def _register(
    client: AsyncClient, label: str
) -> tuple[dict[str, str], User, Tenant]:
    suffix = f"{label}-{time.time_ns()}"
    email = f"{suffix}@example.com"
    response = await client.post(
        "/auth/register",
        json={
            "organization_name": f"Склад {label}",
            "slug": suffix,
            "admin_email": email,
            "password": "password123",
        },
    )
    assert response.status_code == 200, response.text
    headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
    async with SessionLocal() as session:
        user = await session.scalar(select(User).where(User.email == email))
        assert user is not None
        tenant = await session.get(Tenant, user.tenant_id)
        assert tenant is not None
        session.expunge(user)
        session.expunge(tenant)
    return headers, user, tenant


async def _seed_map(
    tenant_id: uuid.UUID,
) -> tuple[
    Warehouse,
    StorageLocation,
    StorageLocation,
    Product,
    Product,
    InventoryBalance,
    Pallet,
    InboundIntakeBox,
]:
    async with SessionLocal() as session:
        suffix = uuid.uuid4().hex[:10]
        warehouse = Warehouse(
            tenant_id=tenant_id,
            name="Ярцево",
            code=f"map-{suffix}",
            barcode=f"WH-MAP-{suffix}",
        )
        session.add(warehouse)
        await session.flush()
        cell = StorageLocation(
            tenant_id=tenant_id,
            warehouse_id=warehouse.id,
            code="А-01-01",
            barcode=f"CELL-{suffix}",
        )
        session.add(cell)
        await session.flush()
        sorting = await get_or_create_sorting_location(session, tenant_id, warehouse.id)
        seller = Seller(tenant_id=tenant_id, name="ИП Тестовый")
        session.add(seller)
        await session.flush()
        product = Product(
            tenant_id=tenant_id,
            seller_id=seller.id,
            name="Футболка белая",
            sku_code=f"TS-{suffix}",
            wb_barcode=f"4600{suffix[:8]}",
        )
        sorting_product = Product(
            tenant_id=tenant_id,
            seller_id=seller.id,
            name="Носки",
            sku_code=f"SK-{suffix}",
            wb_barcode=f"4700{suffix[:8]}",
        )
        session.add_all([product, sorting_product])
        await session.flush()
        request = InboundIntakeRequest(
            tenant_id=tenant_id,
            warehouse_id=warehouse.id,
            status="receiving",
        )
        session.add(request)
        await session.flush()
        box = InboundIntakeBox(
            tenant_id=tenant_id,
            request_id=request.id,
            box_number=41,
            internal_barcode=f"BOX-{suffix}",
        )
        pallet = Pallet(
            tenant_id=tenant_id,
            warehouse_id=warehouse.id,
            code="П-000131",
            barcode=f"PLT-{suffix}",
            storage_location_id=cell.id,
        )
        session.add_all([box, pallet])
        await session.flush()
        box.pallet_id = pallet.id
        loose = InventoryBalance(
            tenant_id=tenant_id,
            storage_location_id=cell.id,
            product_id=product.id,
            quantity=5,
            quantity_unpacked=5,
            quantity_packed=0,
        )
        boxed = InventoryBalance(
            tenant_id=tenant_id,
            storage_location_id=cell.id,
            product_id=product.id,
            container_kind="box",
            container_id=box.id,
            quantity=7,
            quantity_unpacked=7,
            quantity_packed=0,
        )
        loose_sorting = InventoryBalance(
            tenant_id=tenant_id,
            storage_location_id=sorting.id,
            product_id=sorting_product.id,
            quantity=3,
            quantity_unpacked=3,
            quantity_packed=0,
        )
        session.add_all([loose, boxed, loose_sorting])
        await session.commit()
        for row in (
            warehouse,
            cell,
            sorting,
            product,
            sorting_product,
            loose,
            pallet,
            box,
        ):
            session.expunge(row)
        return (
            warehouse,
            cell,
            sorting,
            product,
            sorting_product,
            loose,
            pallet,
            box,
        )


def _tree_qty(data: dict[str, object]) -> int:
    cells = data["cells"]
    unassigned = data["unassigned"]
    assert isinstance(cells, list)
    assert isinstance(unassigned, list)
    return sum(int(cell["qty"]) for cell in cells) + sum(
        int(node["qty"]) for node in unassigned
    )


@pytest.mark.asyncio
async def test_map_totals_moves_sorting_disband_and_tenant_scope(
    async_client: AsyncClient,
) -> None:
    headers, user, tenant = await _register(async_client, "map")
    (
        warehouse,
        cell,
        sorting,
        _product,
        _sorting_product,
        loose,
        pallet,
        box,
    ) = await _seed_map(tenant.id)

    response = await async_client.get(
        f"/warehouses/{warehouse.id}/map", headers=headers
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["sellers"] == ["ИП Тестовый"]
    assert data["cells"][0]["qty"] == 12
    pallet_node = next(
        node for node in data["cells"][0]["children"] if node["kind"] == "pallet"
    )
    assert pallet_node["qty"] == 7
    assert pallet_node["children"][0]["kind"] == "box"
    assert sum(node["qty"] for node in data["unassigned"]) == 3
    async with SessionLocal() as session:
        db_total = int(
            await session.scalar(
                select(func.sum(InventoryBalance.quantity))
                .join(StorageLocation)
                .where(
                    InventoryBalance.tenant_id == tenant.id,
                    StorageLocation.warehouse_id == warehouse.id,
                )
            )
            or 0
        )
    assert _tree_qty(data) == db_total == 15

    moved = await async_client.post(
        f"/warehouses/{warehouse.id}/map/move",
        headers=headers,
        json={
            "kind": "product",
            "id": str(loose.id),
            "to_kind": "unassigned",
            "to_id": None,
            "qty": 2,
        },
    )
    assert moved.status_code == 200, moved.text
    after_move = (
        await async_client.get(f"/warehouses/{warehouse.id}/map", headers=headers)
    ).json()
    assert after_move["cells"][0]["qty"] == 10
    assert sum(node["qty"] for node in after_move["unassigned"]) == 5
    assert after_move["journal"][0]["actor_name"] == user.email
    assert after_move["journal"][0]["from_label"] == "Ячейка А-01-01"
    assert after_move["journal"][0]["to_label"] == "Без ячеек"
    assert _tree_qty(after_move) == db_total

    zero = await async_client.post(
        f"/warehouses/{warehouse.id}/map/move",
        headers=headers,
        json={
            "kind": "product",
            "id": str(loose.id),
            "to_kind": "unassigned",
            "qty": 0,
        },
    )
    assert zero.status_code == 422

    self_move = await async_client.post(
        f"/warehouses/{warehouse.id}/map/move",
        headers=headers,
        json={
            "kind": "pallet",
            "id": str(pallet.id),
            "to_kind": "pallet",
            "to_id": str(pallet.id),
            "qty": 7,
        },
    )
    assert self_move.status_code == 409
    assert self_move.json()["detail"] == "container_cycle"

    sorting_objects = await async_client.get(
        f"/warehouses/{warehouse.id}/sorting-objects", headers=headers
    )
    assert sorting_objects.status_code == 200, sorting_objects.text
    sorting_line = next(
        row for row in sorting_objects.json()["lines"] if row["qty"] == 3
    )
    placed = await async_client.post(
        f"/warehouses/{warehouse.id}/sorting-objects/place",
        headers=headers,
        json={
            "kind": "product",
            "id": sorting_line["id"],
            "cell_id": str(cell.id),
            "qty": 3,
        },
    )
    assert placed.status_code == 200, placed.text
    # Настоящий идентификатор строки остатка в месте назначения. Экран
    # показывает перенос сразу и до ответа держит строку под временным id;
    # без этого поля второй перенос той же строки уходил с выдуманным
    # идентификатором и получал 404 «объект не найден» — двухшаговая
    # раскладка (положил в короб, потом переставил короб) не работала.
    placed_balance_id = placed.json()["balance_id"]
    assert placed_balance_id
    assert placed_balance_id != sorting_line["id"]
    # Этим идентификатором строку можно двигать дальше, не перечитывая карту.
    moved_again = await async_client.post(
        f"/warehouses/{warehouse.id}/sorting-objects/place",
        headers=headers,
        json={
            "kind": "product",
            "id": placed_balance_id,
            "cell_id": None,
            "qty": 1,
        },
    )
    assert moved_again.status_code == 200, moved_again.text
    assert moved_again.json()["moved_qty"] == 1

    moved_pallet = await async_client.post(
        f"/warehouses/{warehouse.id}/map/move",
        headers=headers,
        json={
            "kind": "pallet",
            "id": str(pallet.id),
            "to_kind": "unassigned",
            "qty": 7,
        },
    )
    assert moved_pallet.status_code == 200, moved_pallet.text
    assert moved_pallet.json()["moved_qty"] == 7
    after_pallet_move = (
        await async_client.get(f"/warehouses/{warehouse.id}/map", headers=headers)
    ).json()
    moved_pallet_node = next(
        node
        for node in after_pallet_move["unassigned"]
        if node["kind"] == "pallet" and node["id"] == str(pallet.id)
    )
    assert moved_pallet_node["qty"] == 7

    disbanded = await async_client.post(
        f"/warehouses/{warehouse.id}/map/disband",
        headers=headers,
        json={"pallet_id": str(pallet.id)},
    )
    assert disbanded.status_code == 200, disbanded.text
    async with SessionLocal() as session:
        stored_pallet = await session.get(Pallet, pallet.id)
        stored_box = await session.get(InboundIntakeBox, box.id)
        assert stored_pallet is not None and stored_pallet.disbanded_at is not None
        assert stored_box is not None and stored_box.pallet_id is None
        box_location = await session.scalar(
            select(InventoryBalance.storage_location_id).where(
                InventoryBalance.tenant_id == tenant.id,
                InventoryBalance.container_kind == "box",
                InventoryBalance.container_id == box.id,
                InventoryBalance.quantity > 0,
            )
        )
        assert box_location == sorting.id

    other_headers, _other_user, other_tenant = await _register(async_client, "other")
    del other_headers
    (
        other_warehouse,
        _other_cell,
        _other_sorting,
        _other_product,
        _other_sorting_product,
        foreign_balance,
        _other_pallet,
        _other_box,
    ) = await _seed_map(other_tenant.id)
    denied = await async_client.post(
        f"/warehouses/{warehouse.id}/map/move",
        headers=headers,
        json={
            "kind": "product",
            "id": str(foreign_balance.id),
            "to_kind": "unassigned",
            "qty": 1,
        },
    )
    assert denied.status_code == 404
    assert denied.json()["detail"] == "object_not_found"
    assert other_warehouse.tenant_id == other_tenant.id


@pytest.mark.asyncio
async def test_address_storage_disabled_hides_cells_and_rejects_place(
    async_client: AsyncClient,
) -> None:
    headers, _user, tenant = await _register(async_client, "no-address")
    warehouse, cell, _sorting, *_rest = await _seed_map(tenant.id)
    switched = await async_client.patch(
        "/tenant/settings",
        headers=headers,
        json={"address_storage_enabled": False},
    )
    assert switched.status_code == 200, switched.text

    response = await async_client.get(
        f"/warehouses/{warehouse.id}/map", headers=headers
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["cells"] == []
    assert sum(node["qty"] for node in data["unassigned"]) == 15

    line = next(
        row
        for row in (
            await async_client.get(
                f"/warehouses/{warehouse.id}/sorting-objects", headers=headers
            )
        ).json()["lines"]
        if row["qty"] > 0
    )
    placed = await async_client.post(
        f"/warehouses/{warehouse.id}/sorting-objects/place",
        headers=headers,
        json={
            "kind": "product",
            "id": line["id"],
            "cell_id": str(cell.id),
            "qty": 1,
        },
    )
    assert placed.status_code == 409
    assert placed.json()["detail"] == "address_storage_disabled"

    async with SessionLocal() as session:
        locations = list(
            (
                await session.scalars(
                    select(StorageLocation).where(
                        StorageLocation.warehouse_id == warehouse.id,
                        StorageLocation.code == SORTING_LOCATION_CODE,
                    )
                )
            ).all()
        )
    assert len(locations) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["box", "cargo_place"])
async def test_empty_inbound_container_keeps_cell_after_map_reload(
    async_client: AsyncClient,
    kind: str,
) -> None:
    headers, _user, tenant = await _register(
        async_client, f"empty-{kind.replace('_', '-')}"
    )
    async with SessionLocal() as session:
        suffix = uuid.uuid4().hex[:10]
        warehouse = Warehouse(
            tenant_id=tenant.id,
            name="Склад пустой тары",
            code=f"empty-{suffix}",
            barcode=f"WH-EMPTY-{suffix}",
        )
        session.add(warehouse)
        await session.flush()
        cell = StorageLocation(
            tenant_id=tenant.id,
            warehouse_id=warehouse.id,
            code="Б-02-03",
            barcode=f"CELL-EMPTY-{suffix}",
        )
        request = InboundIntakeRequest(
            tenant_id=tenant.id,
            warehouse_id=warehouse.id,
            status="receiving",
        )
        session.add_all([cell, request])
        await session.flush()
        if kind == "box":
            container = InboundIntakeBox(
                tenant_id=tenant.id,
                request_id=request.id,
                box_number=1,
                internal_barcode=f"BOX-EMPTY-{suffix}",
            )
        else:
            container = InboundIntakeCargoPlace(
                tenant_id=tenant.id,
                request_id=request.id,
                place_number=1,
                internal_barcode=f"CARGO-EMPTY-{suffix}",
            )
        session.add(container)
        await session.commit()
        warehouse_id = warehouse.id
        cell_id = cell.id
        container_id = container.id

    moved = await async_client.post(
        f"/warehouses/{warehouse_id}/map/move",
        headers=headers,
        json={
            "kind": kind,
            "id": str(container_id),
            "to_kind": "cell",
            "to_id": str(cell_id),
            "qty": 1,
        },
    )

    assert moved.status_code == 200, moved.text
    reloaded = await async_client.get(
        f"/warehouses/{warehouse_id}/map",
        headers=headers,
    )
    assert reloaded.status_code == 200, reloaded.text
    target_cell = next(row for row in reloaded.json()["cells"] if row["id"] == str(cell_id))
    assert str(container_id) in {row["id"] for row in target_cell["children"]}
    assert str(container_id) not in {
        row["id"] for row in reloaded.json()["unassigned"]
    }

    async with SessionLocal() as session:
        model = InboundIntakeBox if kind == "box" else InboundIntakeCargoPlace
        stored = await session.get(model, container_id)
        assert stored is not None
        assert stored.storage_location_id == cell_id


@pytest.mark.asyncio
async def test_map_shows_unposted_contents_of_unfinished_inbound_containers(
    async_client: AsyncClient,
) -> None:
    headers, _user, tenant = await _register(async_client, "pending-contents")
    async with SessionLocal() as session:
        suffix = uuid.uuid4().hex[:10]
        warehouse = Warehouse(
            tenant_id=tenant.id,
            name="Склад незавершённой приёмки",
            code=f"pending-{suffix}",
            barcode=f"WH-PENDING-{suffix}",
        )
        seller = Seller(tenant_id=tenant.id, name="Селлер незавершённой тары")
        session.add_all([warehouse, seller])
        await session.flush()
        cell = StorageLocation(
            tenant_id=tenant.id,
            warehouse_id=warehouse.id,
            code="В-03-04",
            barcode=f"CELL-PENDING-{suffix}",
        )
        product = Product(
            tenant_id=tenant.id,
            seller_id=seller.id,
            name="Товар ещё не разложен",
            sku_code=f"PENDING-{suffix}",
            wb_barcode=f"4900{suffix[:8]}",
        )
        request = InboundIntakeRequest(
            tenant_id=tenant.id,
            warehouse_id=warehouse.id,
            seller_id=seller.id,
            status="receiving",
            document_number="ПРИЕМ-НЕЗАВЕРШЕННЫЙ-1",
        )
        session.add_all([cell, product, request])
        await session.flush()
        box = InboundIntakeBox(
            tenant_id=tenant.id,
            request_id=request.id,
            box_number=1,
            internal_barcode=f"BOX-PENDING-{suffix}",
            storage_location_id=cell.id,
        )
        cargo = InboundIntakeCargoPlace(
            tenant_id=tenant.id,
            request_id=request.id,
            place_number=1,
            internal_barcode=f"CARGO-PENDING-{suffix}",
            storage_location_id=cell.id,
        )
        session.add_all([box, cargo])
        await session.flush()
        session.add_all(
            [
                InboundIntakeBoxLine(
                    box_id=box.id,
                    product_id=product.id,
                    quantity=8,
                    posted_qty=3,
                ),
                InboundIntakeCargoPlaceLine(
                    tenant_id=tenant.id,
                    cargo_place_id=cargo.id,
                    product_id=product.id,
                    quantity=6,
                    posted_qty=2,
                ),
            ]
        )
        await session.commit()
        warehouse_id = warehouse.id
        cell_id = cell.id
        cargo_id = cargo.id
        expected = {str(box.id): 5, str(cargo.id): 4}

    response = await async_client.get(
        f"/warehouses/{warehouse_id}/map",
        headers=headers,
    )

    assert response.status_code == 200, response.text
    target_cell = next(row for row in response.json()["cells"] if row["id"] == str(cell_id))
    by_id = {row["id"]: row for row in target_cell["children"]}
    for container_id, remaining_qty in expected.items():
        assert by_id[container_id]["qty"] == remaining_qty
        assert by_id[container_id]["source_document_number"] == (
            "ПРИЕМ-НЕЗАВЕРШЕННЫЙ-1"
        )
        children = by_id[container_id]["children"]
        assert len(children) == 1
        assert children[0]["name"] == "Товар ещё не разложен"
        assert children[0]["seller_name"] == "Селлер незавершённой тары"
        assert children[0]["qty"] == remaining_qty

    blocked_cargo = await async_client.post(
        f"/warehouses/{warehouse_id}/sorting-objects/place",
        headers=headers,
        json={
            "kind": "cargo_place",
            "id": str(cargo_id),
            "cell_id": str(cell_id),
            "to_id": None,
            "qty": 4,
        },
    )
    assert blocked_cargo.status_code == 409, blocked_cargo.text
    assert blocked_cargo.json()["detail"] == "container_stock_missing"


async def test_empty_container_can_be_taken_off_a_cell(
    async_client: AsyncClient,
) -> None:
    """Пустой короб снимается с ячейки: у тары количество не спрашивают.

    Контракт карты склада, 3.1: «qty: null — переехало целиком; так всегда для
    контейнеров». Раньше поле было обязательным и строго больше нуля, поэтому
    снятие пустого короба падало с текстом «qty: Input should be greater than 0»,
    и кладовщик не мог убрать короб с ячейки.
    """
    headers, _user, tenant = await _register(async_client, "empty-box-off")
    warehouse, cell, *_rest = await _seed_map(tenant.id)

    created = await async_client.post(
        f"/warehouses/{warehouse.id}/sorting-objects",
        headers=headers,
        json={"kind": "box"},
    )
    assert created.status_code in (200, 201), created.text
    box_id = created.json()["id"]

    placed = await async_client.post(
        f"/warehouses/{warehouse.id}/sorting-objects/place",
        headers=headers,
        json={"kind": "box", "id": box_id, "cell_id": str(cell.id)},
    )
    assert placed.status_code == 200, placed.text

    # Снятие БЕЗ количества — так и должно быть для тары.
    moved = await async_client.post(
        f"/warehouses/{warehouse.id}/map/move",
        headers=headers,
        json={"kind": "box", "id": box_id, "to_kind": "unassigned", "to_id": None},
    )
    assert moved.status_code == 200, moved.text

    fresh = await async_client.get(f"/warehouses/{warehouse.id}/map", headers=headers)
    assert fresh.status_code == 200, fresh.text
    assert box_id in {n["id"] for n in fresh.json()["unassigned"]}, fresh.text
