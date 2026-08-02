"""Tests for EMU-050 admin API: order seeding, wb-events, state."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from wb_emulator.db import reset_db_runtime
from wb_emulator.main import create_app
from wb_emulator.settings import get_settings

AUTH_HEADERS = {"Authorization": "env-token"}
ADMIN_TOKEN = "test-admin-token"
ADMIN_HEADERS = {"X-Admin-Token": ADMIN_TOKEN}
SELLER_KEY = "seller_env"


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    db_path = tmp_path / "emu.sqlite"
    monkeypatch.setenv("WB_EMULATOR_DB_PATH", str(db_path))
    monkeypatch.setenv("WB_EMULATOR_TOKEN_MAP", json.dumps({"env-token": SELLER_KEY}))
    monkeypatch.setenv("WB_EMULATOR_ADMIN_TOKEN", ADMIN_TOKEN)
    get_settings.cache_clear()
    reset_db_runtime()

    app = create_app()
    with TestClient(app) as test_client:
        yield test_client

    reset_db_runtime()
    get_settings.cache_clear()


def test_admin_requires_token(client: TestClient) -> None:
    assert client.get("/__admin/state").status_code == 401
    assert client.get("/__admin/orders?seller=seller_env&count=1").status_code == 401


def test_admin_create_orders_appear_in_orders_new(client: TestClient) -> None:
    created = client.get(
        f"/__admin/orders?seller={SELLER_KEY}&count=2",
        headers=ADMIN_HEADERS,
    )
    assert created.status_code == 200
    created_body = created.json()
    assert len(created_body["orders"]) == 2
    created_ids = {order["id"] for order in created_body["orders"]}
    for order in created_body["orders"]:
        assert order["nmId"] in {123456789, 987654321}
        assert order["skus"][0].startswith("20000000000")

    new_response = client.get("/api/v3/orders/new", headers=AUTH_HEADERS)
    assert new_response.status_code == 200
    new_ids = {order["id"] for order in new_response.json()["orders"]}
    assert created_ids <= new_ids


def test_wb_event_sorted_removes_from_new(client: TestClient) -> None:
    created = client.get(
        f"/__admin/orders?seller={SELLER_KEY}&count=1",
        headers=ADMIN_HEADERS,
    )
    order_id = created.json()["orders"][0]["id"]

    event = client.post(
        f"/__admin/orders/{order_id}/wb-event?seller={SELLER_KEY}",
        headers={**ADMIN_HEADERS, "Content-Type": "application/json"},
        json={"event": "sorted"},
    )
    assert event.status_code == 200
    body = event.json()["order"]
    assert body["id"] == order_id

    new_response = client.get("/api/v3/orders/new", headers=AUTH_HEADERS)
    new_ids = {order["id"] for order in new_response.json()["orders"]}
    assert order_id not in new_ids


def test_wb_event_sold_removes_from_new(client: TestClient) -> None:
    created = client.get(
        f"/__admin/orders?seller={SELLER_KEY}&count=1",
        headers=ADMIN_HEADERS,
    )
    order_id = created.json()["orders"][0]["id"]

    event = client.post(
        f"/__admin/orders/{order_id}/wb-event?seller={SELLER_KEY}",
        headers={**ADMIN_HEADERS, "Content-Type": "application/json"},
        json={"event": "sold"},
    )
    assert event.status_code == 200

    new_response = client.get("/api/v3/orders/new", headers=AUTH_HEADERS)
    new_ids = {order["id"] for order in new_response.json()["orders"]}
    assert order_id not in new_ids


def test_wb_event_canceled_by_client_removes_from_new(client: TestClient) -> None:
    created = client.get(
        f"/__admin/orders?seller={SELLER_KEY}&count=1",
        headers=ADMIN_HEADERS,
    )
    order_id = created.json()["orders"][0]["id"]

    event = client.post(
        f"/__admin/orders/{order_id}/wb-event?seller={SELLER_KEY}",
        headers={**ADMIN_HEADERS, "Content-Type": "application/json"},
        json={"event": "canceled_by_client"},
    )
    assert event.status_code == 200

    new_response = client.get("/api/v3/orders/new", headers=AUTH_HEADERS)
    new_ids = {order["id"] for order in new_response.json()["orders"]}
    assert order_id not in new_ids


def test_admin_state_reflects_orders(client: TestClient) -> None:
    client.get(f"/__admin/orders?seller={SELLER_KEY}&count=1", headers=ADMIN_HEADERS)
    state = client.get(f"/__admin/state?seller={SELLER_KEY}", headers=ADMIN_HEADERS)
    assert state.status_code == 200
    body = state.json()
    assert body["seller"] == SELLER_KEY
    assert body["orders_total"] >= 1
    assert body["by_supplier_status"].get("new", 0) >= 1


def test_wb_event_invalid_event_returns_400(client: TestClient) -> None:
    created = client.get(
        f"/__admin/orders?seller={SELLER_KEY}&count=1",
        headers=ADMIN_HEADERS,
    )
    order_id = created.json()["orders"][0]["id"]
    bad = client.post(
        f"/__admin/orders/{order_id}/wb-event?seller={SELLER_KEY}",
        headers={**ADMIN_HEADERS, "Content-Type": "application/json"},
        json={"event": "unknown"},
    )
    assert bad.status_code == 400
