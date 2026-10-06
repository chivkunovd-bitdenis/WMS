"""WMS-654 API/data contract; use WMS_TEST_DATABASE_URL for real PG races."""

from __future__ import annotations

import asyncio
import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select

from app.db.session import SessionLocal, engine
from app.models.inventory_balance import InventoryBalance
from app.models.inventory_movement import InventoryMovement
from app.models.storage_location import StorageLocation
from app.models.warehouse import Warehouse
from tests.test_catalog import _create_ff_staff_headers, _register_catalog_admin


@pytest_asyncio.fixture
async def cells(async_client: AsyncClient):
    headers = await _register_catalog_admin(async_client, uuid.uuid4().hex)
    warehouses = (await async_client.get("/warehouses", headers=headers)).json()
    return async_client, headers, warehouses[0]["id"]


def address(rack="А", side=2, tier=3, position=4, *, use_sides=True, use_tiers=True):
    return dict(
        rack_name=rack,
        side=side,
        tier=tier,
        position=position,
        use_sides=use_sides,
        use_tiers=use_tiers,
    )


async def create(cells, body, *, warehouse=None):
    client, headers, wid = cells
    return await client.post(
        f"/warehouses/{warehouse or wid}/locations", headers=headers, json=body
    )


async def listed(cells):
    client, headers, wid = cells
    response = await client.get(f"/warehouses/{wid}/locations", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


async def suggest(cells, rack="А", side=2, tier=3, *, warehouse=None):
    client, headers, wid = cells
    params = dict(
        rack_name=rack,
        use_sides=str(side is not None).lower(),
        use_tiers=str(tier is not None).lower(),
    )
    if side is not None:
        params["side"] = str(side)
    if tier is not None:
        params["tier"] = str(tier)
    return await client.get(
        f"/warehouses/{warehouse or wid}/locations/suggest", headers=headers, params=params
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "use_sides,use_tiers,code",
    [
        (False, False, "А 4"),
        (True, False, "А 2.4"),
        (False, True, "А 3.4"),
        (True, True, "А 2.3.4"),
    ],
)
async def test_c1_four_address_combinations_survive_reload(cells, use_sides, use_tiers, code):
    # Deliberately send stale disabled values: they must not become coordinates.
    response = await create(cells, address(use_sides=use_sides, use_tiers=use_tiers))
    assert response.status_code == 200, response.text
    row = response.json()
    assert row["code"] == code
    assert row["barcode"].startswith("LOC-")
    expected = dict(side=2 if use_sides else None, tier=3 if use_tiers else None, position=4)
    assert {key: row.get(key) for key in expected} == expected
    for _ in range(2):
        reloaded = next(x for x in await listed(cells) if x["id"] == row["id"])
        assert reloaded == row
    async with SessionLocal() as session:
        stored = await session.get(StorageLocation, uuid.UUID(row["id"]))
        assert stored is not None
        assert stored.code == code and stored.barcode == row["barcode"]
        assert {key: getattr(stored, key, None) for key in expected} == expected
        assert stored.rack_id is not None


@pytest.mark.asyncio
async def test_c2_suggestions_use_coordinate_context_and_skip_code_collisions(cells):
    client, headers, _ = cells
    second = await client.post(
        "/warehouses", headers=headers, json={"name": "Other", "code": "other"}
    )
    assert second.status_code == 200, second.text
    seeds = [
        address(position=7),
        address(side=1, position=12),
        address(tier=4, position=15),
        address(rack="Б", position=19),
        address(side=2, tier=88, position=9, use_tiers=False),
        address(side=2, tier=3, position=11, use_sides=False),
        address(side=2, tier=88, position=13, use_sides=False, use_tiers=False),
    ]
    for body in seeds:
        response = await create(cells, body)
        assert response.status_code == 200, response.text
    for rack, side, tier, expected in [
        ("А", 2, 3, (8, "А 2.3.8")),
        ("А", 1, 3, (13, "А 1.3.13")),
        ("А", 2, 4, (16, "А 2.4.16")),
        ("Б", 2, 3, (20, "Б 2.3.20")),
        ("А", 2, None, (10, "А 2.10")),
        ("А", None, 3, (12, "А 3.12")),
        ("А", None, None, (14, "А 14")),
    ]:
        response = await suggest(cells, rack, side, tier)
        assert response.status_code == 200, response.text
        assert response.json() == {"position": expected[0], "code": expected[1]}
    response = await suggest(cells, warehouse=second.json()["id"])
    assert response.status_code == 200, response.text
    assert response.json() == {"position": 1, "code": "А 2.3.1"}
    # Legacy/code-only client can occupy the same rendered address in another context.
    collision = await create(cells, {"code": "В 2.1"})
    assert collision.status_code == 200, collision.text
    response = await suggest(cells, "В", None, 2)
    assert response.status_code == 200, response.text
    assert response.json() == {"position": 2, "code": "В 2.2"}


@pytest.mark.asyncio
async def test_c3_legacy_api_and_existing_rows_are_unchanged(cells):
    old = await create(cells, {"rack_name": "А", "side": 2, "position": 4})
    assert old.status_code == 200, old.text
    assert old.json()["code"] == "А 2.4"
    original = old.json()
    async with SessionLocal() as session:
        stored = await session.get(StorageLocation, uuid.UUID(original["id"]))
        assert stored is not None
        coordinates = (stored.rack_id, stored.side, stored.position)
    another = await create(cells, {"rack_name": "Б", "side": 1, "position": 1})
    assert another.status_code == 200, another.text
    assert another.json()["code"] == "Б 1.1"
    assert next(x for x in await listed(cells) if x["id"] == original["id"]) == original
    async with SessionLocal() as session:
        stored = await session.get(StorageLocation, uuid.UUID(original["id"]))
        assert stored is not None
        assert (stored.rack_id, stored.side, stored.position) == coordinates
        assert stored.code == original["code"] and stored.barcode == original["barcode"]


@pytest.mark.asyncio
async def test_c4_repeat_conflict_does_not_duplicate_new_address(cells):
    body = address()
    first = await create(cells, body)
    assert first.status_code == 200, first.text
    repeated = await create(cells, body)
    assert repeated.status_code == 409, repeated.text
    assert repeated.json()["detail"] == "location_code_taken"
    distinct = await create(cells, address(tier=4))
    assert distinct.status_code == 200, distinct.text
    rows = [x for x in await listed(cells) if x["code"] != "__SORTING__"]
    assert {x["code"] for x in rows} == {"А 2.3.4", "А 2.4.4"}
    assert len({x["barcode"] for x in rows}) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("new_mode", [False, True])
async def test_c4_postgresql_concurrent_requests_have_one_winner(cells, new_mode):
    if engine.dialect.name != "postgresql":
        pytest.skip("Real concurrency proof requires isolated local/CI PostgreSQL")
    # Precreate the rack so the race tests cell uniqueness, not merely rack creation.
    setup = await create(cells, {"rack_name": "А", "side": 1, "position": 99})
    assert setup.status_code == 200, setup.text
    body = address() if new_mode else {"rack_name": "А", "side": 2, "position": 4}
    responses = await asyncio.gather(create(cells, body), create(cells, body))
    assert sorted(x.status_code for x in responses) == [200, 409], [x.text for x in responses]
    loser = next(x for x in responses if x.status_code == 409)
    assert loser.json()["detail"] == "location_code_taken"
    winner = next(x.json() for x in responses if x.status_code == 200)
    assert winner["code"] == ("А 2.3.4" if new_mode else "А 2.4")
    assert len([x for x in await listed(cells) if x["code"] == winner["code"]]) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("new_mode", [False, True])
async def test_c5_tenant_warehouse_and_staff_permissions_are_preserved(cells, new_mode):
    client, headers, wid = cells
    foreign_headers = await _register_catalog_admin(client, uuid.uuid4().hex)
    foreign = (await client.get("/warehouses", headers=foreign_headers)).json()[0]["id"]
    body = address() if new_mode else {"rack_name": "А", "side": 1, "position": 1}
    for target in [foreign, str(uuid.uuid4())]:
        response = await create(cells, body, warehouse=target)
        assert response.status_code == 404, response.text
        response = await client.get(
            f"/warehouses/{target}/locations/suggest",
            headers=headers,
            params={
                "rack_name": "А",
                "side": 1,
                **({"tier": 3, "use_tiers": "true"} if new_mode else {}),
            },
        )
        assert response.status_code == 404, response.text
        assert response.json()["detail"] == "warehouse_not_found"
    staff = await _create_ff_staff_headers(client, headers, uuid.uuid4().hex)
    denied = await client.post(
        f"/warehouses/{wid}/locations",
        headers=staff,
        json=body,
    )
    assert denied.status_code == 403, denied.text
    allowed = await create(cells, body)
    assert allowed.status_code == 200, allowed.text
    assert len([x for x in await listed(cells) if x["code"] != "__SORTING__"]) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", [{"tier": 0}, {"tier": -1}, {"tier": 1.5}, {"side": 3}])
async def test_c7_invalid_coordinates_can_be_corrected_without_changing_neighbors(cells, bad):
    neighbor = await create(cells, {"code": "OLD-01"})
    assert neighbor.status_code == 200, neighbor.text
    before = await listed(cells)
    invalid = await create(cells, address(**bad))
    assert invalid.status_code == 422, invalid.text
    assert await listed(cells) == before
    valid = await create(cells, address())
    assert valid.status_code == 200, valid.text
    assert valid.json()["code"] == "А 2.3.4"
    assert (
        next(x for x in await listed(cells) if x["id"] == neighbor.json()["id"]) == neighbor.json()
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("new_mode", [False, True])
async def test_c10_creation_keeps_existing_stock_placement_and_barcodes(cells, new_mode):
    client, headers, wid = cells
    old = await create(cells, {"code": "OLD-01"})
    assert old.status_code == 200, old.text
    product = await client.post(
        "/products",
        headers=headers,
        json={
            "name": "Box",
            "sku_code": "WMS654-BOX",
            "length_mm": 10,
            "width_mm": 10,
            "height_mm": 10,
        },
    )
    assert product.status_code == 200, product.text
    async with SessionLocal() as session:
        wh = await session.get(Warehouse, uuid.UUID(wid))
        assert wh is not None
        balance = InventoryBalance(
            tenant_id=wh.tenant_id,
            storage_location_id=uuid.UUID(old.json()["id"]),
            product_id=uuid.UUID(product.json()["id"]),
            quantity=7,
            quantity_unpacked=7,
            quantity_packed=0,
        )
        session.add(balance)
        await session.commit()
        balance_id = balance.id
        movements_before = list((await session.scalars(select(InventoryMovement.id))).all())
    new = await create(
        cells,
        address(rack="Б", side=1, tier=1, position=1)
        if new_mode
        else {"rack_name": "Б", "side": 1, "position": 1},
    )
    assert new.status_code == 200, new.text
    assert new.json()["code"] == ("Б 1.1.1" if new_mode else "Б 1.1")
    assert new.json()["barcode"].startswith("LOC-")
    assert new.json()["barcode"] != old.json()["barcode"]
    reloaded = await listed(cells)
    assert next(x for x in reloaded if x["id"] == old.json()["id"]) == old.json()
    assert (
        next(x for x in reloaded if x["id"] == new.json()["id"])["barcode"] == new.json()["barcode"]
    )
    async with SessionLocal() as session:
        balance = await session.get(InventoryBalance, balance_id)
        assert balance is not None
        assert (
            balance.storage_location_id,
            balance.product_id,
            balance.quantity,
            balance.quantity_unpacked,
            balance.quantity_packed,
        ) == (uuid.UUID(old.json()["id"]), uuid.UUID(product.json()["id"]), 7, 7, 0)
        assert list((await session.scalars(select(InventoryMovement.id))).all()) == movements_before


@pytest.mark.asyncio
async def test_c3_new_creation_preserves_legacy_coordinates_and_barcode(cells):
    old = await create(cells, {"rack_name": "А", "side": 2, "position": 4})
    assert old.status_code == 200, old.text
    original = old.json()
    new = await create(cells, address())
    assert new.status_code == 200, new.text
    assert new.json()["code"] == "А 2.3.4"
    assert next(x for x in await listed(cells) if x["id"] == original["id"]) == original
    async with SessionLocal() as session:
        stored = await session.get(StorageLocation, uuid.UUID(original["id"]))
        assert stored is not None
        assert (
            stored.code,
            stored.barcode,
            stored.side,
            stored.position,
            getattr(stored, "tier", None),
        ) == ("А 2.4", original["barcode"], 2, 4, None)
