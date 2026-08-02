"""Contract tests for EMU-040: stickers, supply barcode, trbx QR, order meta KIZ."""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from wb_emulator.db import reset_db_runtime
from wb_emulator.main import create_app
from wb_emulator.services.marking_meta import reset_marking_meta_store
from wb_emulator.settings import get_settings

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
AUTH_HEADERS = {"Authorization": "env-token"}


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    db_path = tmp_path / "emu.sqlite"
    token_file = tmp_path / "tokens.json"
    token_file.write_text(
        json.dumps({"file-token": "seller_from_file"}),
        encoding="utf-8",
    )
    monkeypatch.setenv("WB_EMULATOR_DB_PATH", str(db_path))
    monkeypatch.setenv("WB_EMULATOR_TOKEN_MAP", json.dumps({"env-token": "seller_env"}))
    monkeypatch.setenv("WB_EMULATOR_TOKEN_MAP_FILE", str(token_file))
    get_settings.cache_clear()
    reset_db_runtime()
    reset_marking_meta_store()

    app = create_app()
    with TestClient(app) as test_client:
        yield test_client

    reset_marking_meta_store()
    reset_db_runtime()
    get_settings.cache_clear()


def _assert_valid_png_b64(payload: str) -> None:
    raw = base64.b64decode(payload, validate=True)
    assert raw.startswith(PNG_MAGIC)
    assert len(raw) > 100


def test_post_order_stickers_returns_code128_png(client: TestClient) -> None:
    response = client.post(
        "/api/v3/orders/stickers",
        params={"type": "png", "width": 58, "height": 40},
        headers=AUTH_HEADERS,
        json={"orders": [100001, 100002]},
    )
    assert response.status_code == 200
    body = response.json()
    stickers = body["stickers"]
    assert len(stickers) == 2
    for row in stickers:
        assert row["orderId"] in (100001, 100002)
        assert row["barcode"].startswith("WB")
        _assert_valid_png_b64(row["file"])


def test_get_supply_barcode_returns_qr_png(client: TestClient) -> None:
    response = client.get(
        "/api/v3/supplies/WB-GI-TEST-1/barcode",
        params={"type": "png"},
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/png")
    assert response.content.startswith(PNG_MAGIC)
    assert len(response.content) > 100


def test_post_trbx_stickers_returns_qr_png(client: TestClient) -> None:
    response = client.post(
        "/api/v3/supplies/WB-GI-TEST-1/trbx/stickers",
        params={"type": "png"},
        headers=AUTH_HEADERS,
        json={"trbxIds": ["TRBX-1", "TRBX-2"]},
    )
    assert response.status_code == 200
    stickers = response.json()["stickers"]
    assert len(stickers) == 2
    ids = {row["trbxId"] for row in stickers}
    assert ids == {"TRBX-1", "TRBX-2"}
    for row in stickers:
        _assert_valid_png_b64(row["file"])


def test_put_meta_kiz_ok_and_get(client: TestClient) -> None:
    order_id = 555001
    kiz = "010460000000000021N4N57TEST0001"
    put_resp = client.put(
        f"/api/v3/orders/{order_id}/meta/sgtin",
        headers=AUTH_HEADERS,
        json={"sgtins": [kiz]},
    )
    assert put_resp.status_code == 200
    assert put_resp.json() == {"status": "ok"}

    get_resp = client.get(f"/api/v3/orders/{order_id}/meta", headers=AUTH_HEADERS)
    assert get_resp.status_code == 200
    meta = get_resp.json()
    assert meta["sgtins"] == [{"value": kiz, "checkStatus": "ok"}]


def test_put_meta_kiz_err_sets_error_check_status(client: TestClient) -> None:
    order_id = 555002
    kiz = "010460000000000021ERR-BAD-KIZ"
    client.put(
        f"/api/v3/orders/{order_id}/meta/sgtin",
        headers=AUTH_HEADERS,
        json={"sgtins": [kiz]},
    )
    get_resp = client.get(f"/api/v3/orders/{order_id}/meta", headers=AUTH_HEADERS)
    assert get_resp.status_code == 200
    entries = get_resp.json()["sgtins"]
    assert len(entries) == 1
    assert entries[0]["value"] == kiz
    assert entries[0]["checkStatus"] == "error"


def test_media_meta_routes_require_auth(client: TestClient) -> None:
    response = client.post(
        "/api/v3/orders/stickers",
        params={"type": "png"},
        json={"orders": [1]},
    )
    assert response.status_code == 401
