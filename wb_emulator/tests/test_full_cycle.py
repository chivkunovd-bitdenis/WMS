"""EMU-070: end-to-end emulator cycle (admin → orders → supply → stickers → KIZ → deliver)."""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from wb_emulator.db import reset_db_runtime
from wb_emulator.main import create_app
from wb_emulator.services.marking_meta import reset_marking_meta_store
from wb_emulator.services.orders_store import DEFAULT_EMULATOR_WAREHOUSE_ID
from wb_emulator.settings import get_settings

ADMIN = {"X-Admin-Token": "admin-secret"}
AUTH_A = {"Authorization": "token-a"}
AUTH_B = {"Authorization": "token-b"}
WH_ID = DEFAULT_EMULATOR_WAREHOUSE_ID
CHRT_A = 111001
CHRT_B = 222002
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
KIZ_OK = "010460000000000021N4N57TEST0001"
KIZ_ERR = "010460000000000021ERR-BAD-KIZ"


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    db_path = tmp_path / "emu.sqlite"
    monkeypatch.setenv("WB_EMULATOR_DB_PATH", str(db_path))
    monkeypatch.setenv(
        "WB_EMULATOR_TOKEN_MAP",
        json.dumps({"token-a": "seller_a", "token-b": "seller_b"}),
    )
    monkeypatch.setenv("WB_EMULATOR_ADMIN_TOKEN", "admin-secret")
    get_settings.cache_clear()
    reset_db_runtime()
    reset_marking_meta_store()
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client
    reset_db_runtime()
    reset_marking_meta_store()
    get_settings.cache_clear()


def _put_stock(
    client: TestClient,
    headers: dict[str, str],
    chrt_id: int,
    amount: int,
    *,
    warehouse_id: int = WH_ID,
) -> None:
    response = client.put(
        f"/api/v3/stocks/{warehouse_id}",
        headers=headers,
        json={"stocks": [{"chrtId": chrt_id, "amount": amount}]},
    )
    assert response.status_code == 204


def _seed_orders_stock(client: TestClient, headers: dict[str, str], count: int) -> None:
    _put_stock(client, headers, CHRT_A, count)
    if count > 1:
        _put_stock(client, headers, CHRT_B, count - 1)


def test_full_happy_path_admin_to_deliver(client: TestClient) -> None:
    """TC-NEW-FBS-EMU-001/002 happy: seed → new → supply → stickers → KIZ ok → deliver."""
    _seed_orders_stock(client, AUTH_A, 2)
    created = client.post(
        "/__admin/orders?seller=seller_a&count=2&chrt_id=111001",
        headers=ADMIN,
    )
    assert created.status_code == 200
    order_ids = [row["id"] for row in created.json()["orders"]]
    assert len(order_ids) == 2

    new = client.get("/api/v3/orders/new", headers=AUTH_A)
    assert new.status_code == 200
    new_ids = {row["id"] for row in new.json()["orders"]}
    assert set(order_ids) <= new_ids

    supply = client.post("/api/v3/supplies", headers=AUTH_A, json={"name": "FBS cycle"})
    assert supply.status_code == 200
    supply_id = str(supply.json()["id"])
    assert supply_id.startswith("WB-GI-")

    oid = order_ids[0]
    add = client.patch(f"/api/v3/supplies/{supply_id}/orders/{oid}", headers=AUTH_A)
    assert add.status_code == 204

    stickers = client.post(
        "/api/v3/orders/stickers?type=png&width=58&height=40",
        headers=AUTH_A,
        json={"orders": [oid]},
    )
    assert stickers.status_code == 200
    sticker_rows = stickers.json()["stickers"]
    assert len(sticker_rows) == 1
    assert sticker_rows[0]["orderId"] == oid
    png = base64.b64decode(sticker_rows[0]["file"], validate=True)
    assert png.startswith(PNG_MAGIC)
    assert len(png) > 100

    put_meta = client.put(
        f"/api/v3/orders/{oid}/meta/sgtin",
        headers=AUTH_A,
        json={"sgtins": [KIZ_OK]},
    )
    assert put_meta.status_code == 200
    meta = client.get(f"/api/v3/orders/{oid}/meta", headers=AUTH_A)
    assert meta.status_code == 200
    assert meta.json()["sgtins"] == [{"value": KIZ_OK, "checkStatus": "ok"}]

    deliver = client.patch(f"/api/v3/supplies/{supply_id}/deliver", headers=AUTH_A)
    assert deliver.status_code == 204

    supply_view = client.get(f"/api/v3/supplies/{supply_id}", headers=AUTH_A)
    assert supply_view.status_code == 200
    assert supply_view.json()["done"] is True
    assert oid in supply_view.json()["orders"]


def test_kiz_err_sets_check_status_error(client: TestClient) -> None:
    """TC-NEW-FBS-EMU-002 negative: KIZ with ERR → checkStatus=error (WMS would block deliver)."""
    _put_stock(client, AUTH_A, CHRT_A, 1)
    created = client.post("/__admin/orders?seller=seller_a&count=1", headers=ADMIN)
    oid = created.json()["orders"][0]["id"]

    put_meta = client.put(
        f"/api/v3/orders/{oid}/meta/sgtin",
        headers=AUTH_A,
        json={"sgtins": [KIZ_ERR]},
    )
    assert put_meta.status_code == 200
    meta = client.get(f"/api/v3/orders/{oid}/meta", headers=AUTH_A)
    assert meta.status_code == 200
    assert meta.json()["sgtins"] == [{"value": KIZ_ERR, "checkStatus": "error"}]


def test_unknown_token_returns_401(client: TestClient) -> None:
    """TC-NEW-FBS-EMU-001 negative: unknown Authorization → 401."""
    assert client.get("/api/v3/orders/new").status_code == 401
    assert client.get("/api/v3/orders/new", headers={"Authorization": "unknown-token"}).status_code == 401
    assert (
        client.post(
            "/api/v3/supplies",
            headers={"Authorization": "unknown-token"},
            json={"name": "x"},
        ).status_code
        == 401
    )


def test_warehouses_and_offices_contract(client: TestClient) -> None:
    """Client reads raw list from GET /warehouses and /offices."""
    wh = client.get("/api/v3/warehouses", headers=AUTH_A)
    assert wh.status_code == 200
    warehouses = wh.json()
    assert isinstance(warehouses, list) and warehouses
    assert {"id", "name", "officeId"} <= set(warehouses[0])

    offices = client.get("/api/v3/offices", headers=AUTH_A)
    assert offices.status_code == 200
    rows = offices.json()
    assert isinstance(rows, list) and rows
    assert {"id", "officeId", "name"} <= set(rows[0])

    bare = client.get("/api/v3/warehouses")
    assert bare.status_code == 401


def test_multi_seller_isolation(client: TestClient) -> None:
    """TC-NEW-FBS-EMU-003: each seller token sees only own orders; foreign supply → 404."""
    _seed_orders_stock(client, AUTH_A, 2)
    _put_stock(client, AUTH_B, CHRT_A, 1)
    a = client.post("/__admin/orders?seller=seller_a&count=2", headers=ADMIN)
    b = client.post("/__admin/orders?seller=seller_b&count=1", headers=ADMIN)
    assert a.status_code == 200 and b.status_code == 200
    ids_a = {row["id"] for row in a.json()["orders"]}
    ids_b = {row["id"] for row in b.json()["orders"]}

    new_a = {row["id"] for row in client.get("/api/v3/orders/new", headers=AUTH_A).json()["orders"]}
    new_b = {row["id"] for row in client.get("/api/v3/orders/new", headers=AUTH_B).json()["orders"]}
    assert ids_a <= new_a
    assert ids_b <= new_b
    assert ids_a.isdisjoint(new_b)
    assert ids_b.isdisjoint(new_a)

    supply_a = client.post("/api/v3/supplies", headers=AUTH_A, json={"name": "A only"}).json()["id"]
    foreign = client.get(f"/api/v3/supplies/{supply_a}", headers=AUTH_B)
    assert foreign.status_code == 404
