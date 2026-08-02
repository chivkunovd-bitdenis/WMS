"""Contract tests for EMU-020 orders API (/api/v3/orders/*)."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from wb_emulator.db import get_session_factory, reset_db_runtime
from wb_emulator.main import create_app
from wb_emulator.services import orders_store
from wb_emulator.settings import get_settings

AUTH_HEADERS = {"Authorization": "env-token"}
SELLER_KEY = "seller_env"


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    db_path = tmp_path / "emu.sqlite"
    monkeypatch.setenv("WB_EMULATOR_DB_PATH", str(db_path))
    monkeypatch.setenv("WB_EMULATOR_TOKEN_MAP", json.dumps({"env-token": SELLER_KEY}))
    get_settings.cache_clear()
    reset_db_runtime()

    app = create_app()
    with TestClient(app) as test_client:
        yield test_client

    reset_db_runtime()
    get_settings.cache_clear()


def _with_session(fn: Callable[[Session], None]) -> None:
    session = get_session_factory()()
    try:
        fn(session)
    finally:
        session.close()


def test_get_orders_new_returns_mock_shape(client: TestClient) -> None:
    response = client.get("/api/v3/orders/new", headers=AUTH_HEADERS)
    assert response.status_code == 200
    body = response.json()
    assert "orders" in body
    assert len(body["orders"]) == 1
    order = body["orders"][0]
    assert order["id"] == 990001
    assert order["rid"] == "mock-rid-990001"
    assert order["createdAt"] == "2026-07-01T10:00:00+03:00"
    assert order["nmId"] == 424242
    assert order["chrtId"] == 111
    assert order["article"] == "E2E-MOCK"
    assert order["skus"] == ["E2E-MOCK-BARCODE"]
    assert order["price"] == 150000
    assert order["cargoType"] == 1
    assert order["officeId"] == 12345
    assert order["isLegal"] is False
    assert order["options"] == {"isB2B": False}


def test_get_orders_pagination(client: TestClient) -> None:
    def seed(session: Session) -> None:
        orders_store.upsert_order(
            session,
            SELLER_KEY,
            {
                **orders_store.DEFAULT_MOCK_ORDER,
                "id": 990010,
                "rid": "rid-990010",
            },
        )
        orders_store.upsert_order(
            session,
            SELLER_KEY,
            {
                **orders_store.DEFAULT_MOCK_ORDER,
                "id": 990020,
                "rid": "rid-990020",
            },
        )

    _with_session(seed)

    first = client.get("/api/v3/orders?limit=1", headers=AUTH_HEADERS)
    assert first.status_code == 200
    first_body = first.json()
    assert len(first_body["orders"]) == 1
    assert first_body["next"] == first_body["orders"][0]["id"]

    second = client.get(f"/api/v3/orders?limit=1&next={first_body['next']}", headers=AUTH_HEADERS)
    assert second.status_code == 200
    second_body = second.json()
    assert len(second_body["orders"]) == 1
    assert second_body["orders"][0]["id"] > first_body["orders"][0]["id"]


def test_post_orders_status(client: TestClient) -> None:
    response = client.post(
        "/api/v3/orders/status",
        headers={**AUTH_HEADERS, "Content-Type": "application/json"},
        json={"orders": [990001, 999999]},
    )
    assert response.status_code == 200
    body = response.json()
    assert "orders" in body
    assert body["orders"] == [
        {"id": 990001, "supplierStatus": "new", "wbStatus": "waiting"},
        {"id": 999999, "supplierStatus": "new", "wbStatus": "waiting"},
    ]


def test_patch_cancel_order_is_success_no_body(client: TestClient) -> None:
    seeded = client.get("/api/v3/orders/new", headers=AUTH_HEADERS)
    assert seeded.status_code == 200
    assert len(seeded.json()["orders"]) == 1

    cancel = client.patch("/api/v3/orders/990001/cancel", headers=AUTH_HEADERS)
    assert cancel.status_code == 204
    assert cancel.content == b""

    missing = client.patch("/api/v3/orders/888888/cancel", headers=AUTH_HEADERS)
    assert missing.status_code == 204

    after_cancel = client.get("/api/v3/orders/new", headers=AUTH_HEADERS)
    assert after_cancel.status_code == 200
    assert after_cancel.json()["orders"] == []

    status = client.post(
        "/api/v3/orders/status",
        headers={**AUTH_HEADERS, "Content-Type": "application/json"},
        json={"orders": [990001]},
    )
    assert status.json()["orders"][0]["supplierStatus"] == "cancel"


def test_orders_require_auth(client: TestClient) -> None:
    assert client.get("/api/v3/orders/new").status_code == 401
    assert client.get("/api/v3/orders").status_code == 401
    assert client.post("/api/v3/orders/status", json={"orders": [1]}).status_code == 401
    assert client.patch("/api/v3/orders/1/cancel").status_code == 401
