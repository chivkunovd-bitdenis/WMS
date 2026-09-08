"""WMS-082/WMS-085: stored marking verdicts and seller-scoped metadata deletion."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from wb_emulator.db import get_session_factory, reset_db_runtime
from wb_emulator.main import create_app
from wb_emulator.services.marking_meta import reset_marking_meta_store
from wb_emulator.services.orders_store import DEFAULT_MOCK_ORDER, upsert_order
from wb_emulator.settings import get_settings

AUTH = {"Authorization": "test-a"}
FOREIGN_AUTH = {"Authorization": "test-b"}
ORDER_ID = 990001
META_URL = f"/api/v3/orders/{ORDER_ID}/meta"
BATCH_URL = "/api/marketplace/v3/orders/meta"


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("WB_EMULATOR_DB_PATH", str(tmp_path / "emu.sqlite"))
    monkeypatch.setenv(
        "WB_EMULATOR_TOKEN_MAP", json.dumps({"test-a": "a", "test-b": "b"})
    )
    token_file = tmp_path / "tokens.json"
    token_file.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("WB_EMULATOR_TOKEN_MAP_FILE", str(token_file))
    get_settings.cache_clear()
    reset_db_runtime()
    reset_marking_meta_store()
    with TestClient(create_app()) as test_client:
        with get_session_factory()() as session:
            upsert_order(session, "a", DEFAULT_MOCK_ORDER)
        yield test_client
    reset_marking_meta_store()
    reset_db_runtime()
    get_settings.cache_clear()


@pytest.mark.parametrize("kind", ["sgtin", "uin", "imei", "gtin"])
def test_batch_verdict_delete_and_replace(client: TestClient, kind: str) -> None:
    values = ["TEST-ACCEPTED", "TEST-ERR-REJECTED"]
    assert (
        client.put(
            f"{META_URL}/{kind}", headers=AUTH, json={f"{kind}s": values}
        ).status_code
        == 200
    )
    response = client.post(BATCH_URL, headers=AUTH, json={"orders": [ORDER_ID, 999999]})
    assert response.status_code == 200
    rows = response.json()["orders"]
    assert rows == [
        {
            "id": ORDER_ID,
            "meta": {
                f"{kind}s": [
                    {"value": values[0], "checkStatus": "ok"},
                    {"value": values[1], "checkStatus": "error"},
                ]
            },
            "metaDetails": [
                {"key": kind, "value": values[0], "decision": "accepted"},
                {"key": kind, "value": values[1], "decision": "rejected"},
            ],
        },
        {"id": 999999, "meta": {}, "metaDetails": []},
    ]
    # Removal is repeatable and affects both views of the same store.
    for _ in range(2):
        deleted = client.delete(META_URL, headers=AUTH, params={"key": kind})
        assert deleted.status_code == 204
        assert deleted.content == b""
    assert client.get(META_URL, headers=AUTH).json() == {}
    assert client.post(BATCH_URL, headers=AUTH, json={"orders": [ORDER_ID]}).json() == {
        "orders": [{"id": ORDER_ID, "meta": {}, "metaDetails": []}]
    }
    assert (
        client.put(
            f"{META_URL}/{kind}", headers=AUTH, json={f"{kind}s": ["REPLACEMENT"]}
        ).status_code
        == 200
    )
    assert client.post(BATCH_URL, headers=AUTH, json={"orders": [ORDER_ID]}).json()[
        "orders"
    ][0]["metaDetails"] == [
        {"key": kind, "value": "REPLACEMENT", "decision": "accepted"}
    ]


def test_delete_preserves_other_kind_and_seller(client: TestClient) -> None:
    client.put(f"{META_URL}/sgtin", headers=AUTH, json={"sgtins": ["CODE-A"]})
    client.put(f"{META_URL}/uin", headers=AUTH, json={"uins": ["UIN-A"]})
    assert (
        client.delete(
            META_URL, headers=FOREIGN_AUTH, params={"key": "sgtin"}
        ).status_code
        == 404
    )
    assert client.post(
        BATCH_URL, headers=FOREIGN_AUTH, json={"orders": [ORDER_ID]}
    ).json() == {"orders": [{"id": ORDER_ID, "meta": {}, "metaDetails": []}]}
    assert "sgtins" in client.get(META_URL, headers=AUTH).json()
    assert (
        client.delete(META_URL, headers=AUTH, params={"key": "sgtin"}).status_code
        == 204
    )
    assert client.get(META_URL, headers=AUTH).json() == {
        "uins": [{"value": "UIN-A", "checkStatus": "ok"}]
    }
    with get_session_factory()() as session:
        upsert_order(session, "b", DEFAULT_MOCK_ORDER)
    client.put(f"{META_URL}/uin", headers=FOREIGN_AUTH, json={"uins": ["UIN-B"]})
    assert (
        client.delete(META_URL, headers=FOREIGN_AUTH, params={"key": "uin"}).status_code
        == 204
    )
    assert client.get(META_URL, headers=AUTH).json()["uins"][0]["value"] == "UIN-A"


def test_metadata_auth_and_delete_validation(client: TestClient) -> None:
    for headers in ({}, {"Authorization": "unknown"}):
        assert (
            client.delete(
                META_URL, headers=headers, params={"key": "sgtin"}
            ).status_code
            == 401
        )
        assert (
            client.post(
                BATCH_URL, headers=headers, json={"orders": [ORDER_ID]}
            ).status_code
            == 401
        )
    assert client.delete(META_URL, headers=AUTH).status_code == 422
    assert (
        client.delete(META_URL, headers=AUTH, params={"key": "wrong"}).status_code
        == 400
    )
    assert (
        client.delete(
            "/api/v3/orders/999999/meta", headers=AUTH, params={"key": "sgtin"}
        ).status_code
        == 404
    )
