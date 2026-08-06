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
    monkeypatch.setenv("WB_EMULATOR_ADMIN_TOKEN", "admin-token")
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

    state = client.get("/__admin/state?seller=seller_a", headers={"X-Admin-Token": "admin-token"})
    assert state.status_code == 200
    supply_state = next(row for row in state.json()["supplies"] if row["id"] == supply_id)
    assert supply_state == {
        "id": supply_id,
        "seller": "seller_a",
        "done": True,
        "orders": [1001],
        "trbx": [],
        "deliver_calls": 1,
    }

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
    rows = payload["stickers"] if isinstance(payload, dict) else payload
    assert len(rows) == 2
    assert rows[0]["trbxId"] in trbx_ids
    assert rows[0]["file"]


def test_trbx_delete_removes_only_requested_cargo_place(client: TestClient) -> None:
    supply_id = _create_supply(client)
    created = client.post(
        f"/api/v3/supplies/{supply_id}/trbx",
        headers=AUTH,
        json={"amount": 2},
    )
    trbx_ids = created.json()["trbxIds"]

    deleted = client.request(
        "DELETE",
        f"/api/v3/supplies/{supply_id}/trbx",
        headers=AUTH,
        json={"trbxIds": [trbx_ids[0]]},
    )
    assert deleted.status_code == 204

    listed = client.get(f"/api/v3/supplies/{supply_id}/trbx", headers=AUTH)
    assert listed.status_code == 200
    assert listed.json() == {"trbxIds": [trbx_ids[1]]}


def test_trbx_delete_with_missing_or_foreign_id_is_atomic(client: TestClient) -> None:
    supply_id = _create_supply(client, "target")
    target_ids = client.post(
        f"/api/v3/supplies/{supply_id}/trbx", headers=AUTH, json={"amount": 2}
    ).json()["trbxIds"]
    other_supply_id = _create_supply(client, "other")
    foreign_id = client.post(
        f"/api/v3/supplies/{other_supply_id}/trbx", headers=AUTH, json={"amount": 1}
    ).json()["trbxIds"][0]

    for invalid_id in ("TRBX-MISSING", foreign_id):
        response = client.request(
            "DELETE",
            f"/api/v3/supplies/{supply_id}/trbx",
            headers=AUTH,
            json={"trbxIds": [target_ids[0], invalid_id]},
        )
        assert response.status_code == 404
        assert client.get(f"/api/v3/supplies/{supply_id}/trbx", headers=AUTH).json() == {
            "trbxIds": target_ids
        }


def test_trbx_delete_is_seller_isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "delete-isolation.sqlite"
    monkeypatch.setenv("WB_EMULATOR_DB_PATH", str(db_path))
    monkeypatch.setenv(
        "WB_EMULATOR_TOKEN_MAP",
        json.dumps({"token-a": "seller_a", "token-b": "seller_b"}),
    )
    get_settings.cache_clear()
    reset_db_runtime()

    with TestClient(create_app()) as iso_client:
        created = iso_client.post(
            "/api/v3/supplies", headers={"Authorization": "token-a"}, json={"name": "A only"}
        )
        supply_id = created.json()["id"]
        trbx_id = iso_client.post(
            f"/api/v3/supplies/{supply_id}/trbx",
            headers={"Authorization": "token-a"},
            json={"amount": 1},
        ).json()["trbxIds"][0]

        foreign_delete = iso_client.request(
            "DELETE",
            f"/api/v3/supplies/{supply_id}/trbx",
            headers={"Authorization": "token-b"},
            json={"trbxIds": [trbx_id]},
        )
        assert foreign_delete.status_code == 404
        assert iso_client.get(
            f"/api/v3/supplies/{supply_id}/trbx", headers={"Authorization": "token-a"}
        ).json() == {"trbxIds": [trbx_id]}

    reset_db_runtime()
    get_settings.cache_clear()


def test_trbx_delete_after_deliver_keeps_cargo_places(client: TestClient) -> None:
    supply_id = _create_supply(client)
    trbx_id = client.post(
        f"/api/v3/supplies/{supply_id}/trbx", headers=AUTH, json={"amount": 1}
    ).json()["trbxIds"][0]
    assert client.patch(f"/api/v3/supplies/{supply_id}/deliver", headers=AUTH).status_code == 204

    deleted = client.request(
        "DELETE",
        f"/api/v3/supplies/{supply_id}/trbx",
        headers=AUTH,
        json={"trbxIds": [trbx_id]},
    )
    assert deleted.status_code == 400
    assert client.get(f"/api/v3/supplies/{supply_id}/trbx", headers=AUTH).json() == {
        "trbxIds": [trbx_id]
    }


def test_supply_qr_is_available_only_after_delivery_and_retry_is_idempotent(
    client: TestClient,
) -> None:
    supply_id = _create_supply(client)
    before_delivery = client.get(
        f"/api/v3/supplies/{supply_id}/barcode?type=png", headers=AUTH
    )
    assert before_delivery.status_code == 409

    assert client.patch(f"/api/v3/supplies/{supply_id}/deliver", headers=AUTH).status_code == 204

    first = client.get(f"/api/v3/supplies/{supply_id}/barcode?type=png", headers=AUTH)
    retry = client.get(f"/api/v3/supplies/{supply_id}/barcode?type=png", headers=AUTH)
    assert first.status_code == retry.status_code == 200
    assert first.headers["content-type"].startswith("image/png")
    assert first.content == retry.content

    state = client.get("/__admin/state?seller=seller_a", headers={"X-Admin-Token": "admin-token"})
    supply_state = next(row for row in state.json()["supplies"] if row["id"] == supply_id)
    assert supply_state["deliver_calls"] == 1


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
