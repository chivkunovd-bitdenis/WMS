"""Contract tests for STOCK-030 WB FBS stocks API emulator."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from wb_emulator.db import init_db, reset_db_runtime
from wb_emulator.main import create_app
from wb_emulator.settings import Settings, get_settings

AUTH_A = {"Authorization": "token-a"}
AUTH_B = {"Authorization": "token-b"}
WH_501 = 501
WH_502 = 502
CHRT_1 = 10001
CHRT_2 = 10002
CHRT_UNKNOWN = 99999


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    db_path = tmp_path / "emu.sqlite"
    monkeypatch.setenv("WB_EMULATOR_DB_PATH", str(db_path))
    monkeypatch.setenv(
        "WB_EMULATOR_TOKEN_MAP",
        json.dumps({"token-a": "seller_a", "token-b": "seller_b"}),
    )
    get_settings.cache_clear()
    reset_db_runtime()

    app = create_app()
    with TestClient(app) as test_client:
        yield test_client

    reset_db_runtime()
    get_settings.cache_clear()


def _put_stocks(
    client: TestClient,
    warehouse_id: int,
    stocks: list[dict[str, int]],
    *,
    headers: dict[str, str] = AUTH_A,
) -> None:
    response = client.put(
        f"/api/v3/stocks/{warehouse_id}",
        headers=headers,
        json={"stocks": stocks},
    )
    assert response.status_code == 204
    assert response.content == b""


def _post_stocks(
    client: TestClient,
    warehouse_id: int,
    chrt_ids: list[int],
    *,
    headers: dict[str, str] = AUTH_A,
) -> list[dict[str, int]]:
    response = client.post(
        f"/api/v3/stocks/{warehouse_id}",
        headers=headers,
        json={"chrtIds": chrt_ids},
    )
    assert response.status_code == 200
    return list(response.json()["stocks"])


def test_put_two_then_post_exact(client: TestClient) -> None:
    """PUT two positions, POST returns exact amounts."""
    _put_stocks(
        client,
        WH_501,
        [{"chrtId": CHRT_1, "amount": 7}, {"chrtId": CHRT_2, "amount": 3}],
    )

    rows = _post_stocks(client, WH_501, [CHRT_1, CHRT_2])
    assert rows == [{"chrtId": CHRT_1, "amount": 7}, {"chrtId": CHRT_2, "amount": 3}]


def test_repeat_put_changes_only_one(client: TestClient) -> None:
    """Second PUT with one chrtId updates only that row."""
    _put_stocks(
        client,
        WH_501,
        [{"chrtId": CHRT_1, "amount": 5}, {"chrtId": CHRT_2, "amount": 2}],
    )
    _put_stocks(client, WH_501, [{"chrtId": CHRT_1, "amount": 9}])

    rows = _post_stocks(client, WH_501, [CHRT_1, CHRT_2])
    assert rows == [{"chrtId": CHRT_1, "amount": 9}, {"chrtId": CHRT_2, "amount": 2}]


def test_zero_amount_persists_on_readback(client: TestClient) -> None:
    """amount=0 is valid on PUT and still returned by POST."""
    _put_stocks(client, WH_501, [{"chrtId": CHRT_1, "amount": 0}])

    rows = _post_stocks(client, WH_501, [CHRT_1])
    assert rows == [{"chrtId": CHRT_1, "amount": 0}]


def test_put_returns_204_without_json(client: TestClient) -> None:
    response = client.put(
        f"/api/v3/stocks/{WH_501}",
        headers=AUTH_A,
        json={"stocks": [{"chrtId": CHRT_1, "amount": 1}]},
    )
    assert response.status_code == 204
    assert response.content == b""
    assert response.headers.get("content-type") is None or "json" not in response.headers.get(
        "content-type", ""
    )


def test_put_rejects_empty_and_over_1000(client: TestClient) -> None:
    empty = client.put(
        f"/api/v3/stocks/{WH_501}",
        headers=AUTH_A,
        json={"stocks": []},
    )
    assert empty.status_code == 422

    too_many = client.put(
        f"/api/v3/stocks/{WH_501}",
        headers=AUTH_A,
        json={"stocks": [{"chrtId": i, "amount": 1} for i in range(1001)]},
    )
    assert too_many.status_code == 422


def test_tc_015_token_and_warehouse_isolation(client: TestClient) -> None:
    """TC-NEW-FBS-STOCK-015: token A/B and warehouse 501/502 do not cross."""
    _put_stocks(client, WH_501, [{"chrtId": CHRT_1, "amount": 11}], headers=AUTH_A)
    _put_stocks(client, WH_502, [{"chrtId": CHRT_1, "amount": 22}], headers=AUTH_A)
    _put_stocks(client, WH_501, [{"chrtId": CHRT_1, "amount": 33}], headers=AUTH_B)

    assert _post_stocks(client, WH_501, [CHRT_1], headers=AUTH_A) == [
        {"chrtId": CHRT_1, "amount": 11}
    ]
    assert _post_stocks(client, WH_502, [CHRT_1], headers=AUTH_A) == [
        {"chrtId": CHRT_1, "amount": 22}
    ]
    assert _post_stocks(client, WH_501, [CHRT_1], headers=AUTH_B) == [
        {"chrtId": CHRT_1, "amount": 33}
    ]
    assert _post_stocks(client, WH_502, [CHRT_1], headers=AUTH_B) == []


def test_n4_post_omits_unknown_requested_chrt_ids(client: TestClient) -> None:
    """TC-NEW-FBS-STOCK N4: readback returns only known requested chrtIds."""
    _put_stocks(client, WH_501, [{"chrtId": CHRT_1, "amount": 4}])

    rows = _post_stocks(client, WH_501, [CHRT_1, CHRT_UNKNOWN])
    assert rows == [{"chrtId": CHRT_1, "amount": 4}]


def test_n8_unknown_token_returns_401(client: TestClient) -> None:
    """TC-NEW-FBS-STOCK N8: unknown Authorization on stocks endpoints."""
    bad_headers = {"Authorization": "unknown-token"}

    put = client.put(
        f"/api/v3/stocks/{WH_501}",
        headers=bad_headers,
        json={"stocks": [{"chrtId": CHRT_1, "amount": 1}]},
    )
    assert put.status_code == 401
    assert put.json() == {"detail": "Unauthorized"}

    post = client.post(
        f"/api/v3/stocks/{WH_501}",
        headers=bad_headers,
        json={"chrtIds": [CHRT_1]},
    )
    assert post.status_code == 401
    assert post.json() == {"detail": "Unauthorized"}


def test_stocks_persist_across_restart(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """SQLite bootstrap keeps stocks after process restart."""
    db_path = tmp_path / "persist.sqlite"
    monkeypatch.setenv("WB_EMULATOR_DB_PATH", str(db_path))
    monkeypatch.setenv("WB_EMULATOR_TOKEN_MAP", json.dumps({"token-a": "seller_a"}))
    get_settings.cache_clear()
    reset_db_runtime()

    app = create_app()
    with TestClient(app) as first_client:
        _put_stocks(first_client, WH_501, [{"chrtId": CHRT_1, "amount": 6}])

    reset_db_runtime()
    get_settings.cache_clear()

    init_db(Settings())
    app = create_app()
    with TestClient(app) as second_client:
        rows = _post_stocks(second_client, WH_501, [CHRT_1])
        assert rows == [{"chrtId": CHRT_1, "amount": 6}]

    reset_db_runtime()
    get_settings.cache_clear()
