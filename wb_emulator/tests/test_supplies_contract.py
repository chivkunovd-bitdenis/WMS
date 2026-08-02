"""Contract tests for EMU-030 supplies + trbx API."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from wb_emulator.db import reset_db_runtime
from wb_emulator.main import create_app
from wb_emulator.settings import get_settings

AUTH = {"Authorization": "env-token"}


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    db_path = tmp_path / "emu.sqlite"
    monkeypatch.setenv("WB_EMULATOR_DB_PATH", str(db_path))
    monkeypatch.setenv("WB_EMULATOR_TOKEN_MAP", json.dumps({"env-token": "seller_a"}))
    get_settings.cache_clear()
    reset_db_runtime()

    app = create_app()
    with TestClient(app) as test_client:
        yield test_client

    reset_db_runtime()
    get_settings.cache_clear()


def _create_supply(client: TestClient, name: str = "Test supply") -> str:
    response = client.post("/api/v3/supplies", headers=AUTH, json={"name": name})
    assert response.status_code == 200
    body = response.json()
    assert "id" in body
    assert body["name"] == name
    return str(body["id"])


def test_create_supply_returns_id_and_name(client: TestClient) -> None:
    supply_id = _create_supply(client, "My FBS supply")
    assert supply_id.startswith("WB-GI-")


def test_get_supply_optional(client: TestClient) -> None:
    supply_id = _create_supply(client)
    response = client.get(f"/api/v3/supplies/{supply_id}", headers=AUTH)
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == supply_id
    assert body["done"] is False
    assert body["orders"] == []
    assert body["trbxIds"] == []


def test_add_order_and_deliver_flow(client: TestClient) -> None:
    supply_id = _create_supply(client)

    add = client.patch(f"/api/v3/supplies/{supply_id}/orders/1001", headers=AUTH)
    assert add.status_code == 204

    get_after = client.get(f"/api/v3/supplies/{supply_id}", headers=AUTH)
    assert get_after.json()["orders"] == [1001]

    deliver = client.patch(f"/api/v3/supplies/{supply_id}/deliver", headers=AUTH)
    assert deliver.status_code == 204

    get_done = client.get(f"/api/v3/supplies/{supply_id}", headers=AUTH)
    assert get_done.json()["done"] is True

    add_after_deliver = client.patch(f"/api/v3/supplies/{supply_id}/orders/1002", headers=AUTH)
    assert add_after_deliver.status_code == 400


def test_order_conflict_between_supplies(client: TestClient) -> None:
    supply_a = _create_supply(client, "A")
    supply_b = _create_supply(client, "B")

    ok = client.patch(f"/api/v3/supplies/{supply_a}/orders/42", headers=AUTH)
    assert ok.status_code == 204

    conflict = client.patch(f"/api/v3/supplies/{supply_b}/orders/42", headers=AUTH)
    assert conflict.status_code == 409


def test_trbx_create_bind_and_stickers_stub(client: TestClient) -> None:
    supply_id = _create_supply(client)
    client.patch(f"/api/v3/supplies/{supply_id}/orders/2001", headers=AUTH)
    client.patch(f"/api/v3/supplies/{supply_id}/orders/2002", headers=AUTH)

    create_trbx = client.post(
        f"/api/v3/supplies/{supply_id}/trbx",
        headers=AUTH,
        json={"amount": 2},
    )
    assert create_trbx.status_code == 200
    trbx_ids = create_trbx.json()["trbxIds"]
    assert len(trbx_ids) == 2

    bind = client.patch(
        f"/api/v3/supplies/{supply_id}/trbx/{trbx_ids[0]}",
        headers=AUTH,
        json={"orderIds": [2001, 2002]},
    )
    assert bind.status_code == 204

    stickers = client.post(
        f"/api/v3/supplies/{supply_id}/trbx/stickers?type=png",
        headers=AUTH,
        json={"trbxIds": trbx_ids},
    )
    assert stickers.status_code == 200
    payload = stickers.json()
    assert len(payload) == 2
    assert payload[0]["trbxId"] in trbx_ids
    assert payload[0]["file"]


def test_barcode_stub_returns_png(client: TestClient) -> None:
    supply_id = _create_supply(client)
    response = client.get(f"/api/v3/supplies/{supply_id}/barcode?type=png", headers=AUTH)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/png")
    assert len(response.content) > 0


def test_unknown_supply_returns_404(client: TestClient) -> None:
    response = client.patch("/api/v3/supplies/WB-GI-MISSING/orders/1", headers=AUTH)
    assert response.status_code == 404


def test_seller_isolation(client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "iso.sqlite"
    monkeypatch.setenv("WB_EMULATOR_DB_PATH", str(db_path))
    monkeypatch.setenv(
        "WB_EMULATOR_TOKEN_MAP",
        json.dumps({"token-a": "seller_a", "token-b": "seller_b"}),
    )
    get_settings.cache_clear()
    reset_db_runtime()

    app = create_app()
    with TestClient(app) as iso_client:
        created = iso_client.post(
            "/api/v3/supplies",
            headers={"Authorization": "token-a"},
            json={"name": "A only"},
        )
        supply_id = created.json()["id"]

        foreign = iso_client.get(
            f"/api/v3/supplies/{supply_id}",
            headers={"Authorization": "token-b"},
        )
        assert foreign.status_code == 404

    reset_db_runtime()
    get_settings.cache_clear()
