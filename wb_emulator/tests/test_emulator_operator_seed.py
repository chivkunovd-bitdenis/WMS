"""TC-23: operator seed — 3 tokens, 13+ orders, PNG assets, persistence, idempotent re-seed."""

from __future__ import annotations

import base64
import hashlib
import io
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from wb_emulator.db import get_session_factory, init_db, reset_db_runtime
from wb_emulator.main import create_app
from wb_emulator.seed.load_seed import load_token_map, run_seed
from wb_emulator.services.orders_store import (
    count_seeded_orders,
    seed_orders_from_templates,
)
from wb_emulator.settings import get_settings

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
REAL_WB_ORDER_STICKER_SHA256 = {
    "32cfd1ece4d68b6f38b54ac413399f03109d85c9e8ebeb87227577c3786ca570",
    "a88d8e626b108aaf3c2584289160c921672c328a28d5be99781c0fe63780c6d8",
    "58cd63d736dfe0d180db7172890870b5670c1e079a159e4c5cb8d5c4248b10fc",
    "547571cf406f7fff90783b364943d0a15b73163b5ee7b01a2272530a9fd6d8dc",
}
ADMIN = {"X-Admin-Token": "admin-secret"}
SEED_DIR = Path(__file__).resolve().parents[1] / "seed"
TOKENS = {
    "token-a": "seller_a",
    "token-b": "seller_b",
    "token-c": "seller_c",
}
AUTH = {
    "token-a": {"Authorization": "token-a"},
    "token-b": {"Authorization": "token-b"},
    "token-c": {"Authorization": "token-c"},
}


@pytest.fixture()
def seeded_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, Path]:
    db_path = tmp_path / "operator.sqlite"
    monkeypatch.setenv("WB_EMULATOR_DB_PATH", str(db_path))
    monkeypatch.setenv("WB_EMULATOR_TOKEN_MAP", json.dumps(TOKENS))
    monkeypatch.setenv("WB_EMULATOR_ADMIN_TOKEN", "admin-secret")
    get_settings.cache_clear()
    reset_db_runtime()
    init_db()

    session = get_session_factory()()
    try:
        seed_orders_from_templates(session, seller_keys=list(TOKENS.values()))
    finally:
        session.close()

    app = create_app()
    with TestClient(app) as client:
        yield client, db_path

    reset_db_runtime()
    get_settings.cache_clear()


def _assert_png(base64_text: str, *, min_width: int = 10, min_height: int = 10) -> None:
    raw = base64.b64decode(base64_text, validate=True)
    assert raw.startswith(PNG_MAGIC)
    image = Image.open(io.BytesIO(raw))
    assert image.width >= min_width
    assert image.height >= min_height


def test_tokens_json_has_three_sellers() -> None:
    token_map = load_token_map(SEED_DIR / "tokens.json")
    assert len(token_map) == 3
    assert set(token_map.values()) == {"seller_a", "seller_b", "seller_c"}


def test_seed_creates_at_least_thirteen_orders(seeded_client: tuple[TestClient, Path]) -> None:
    """TC-23: operator seed yields ≥13 persisted orders."""
    client, db_path = seeded_client
    session = get_session_factory()()
    try:
        total = count_seeded_orders(session)
    finally:
        session.close()
    assert total >= 13

    state = client.get("/__admin/state", headers=ADMIN)
    assert state.status_code == 200
    assert state.json()["orders_total"] >= 13
    _ = db_path


def test_three_tokens_isolated(seeded_client: tuple[TestClient, Path]) -> None:
    """TC-23: each seller token sees only own /orders/new rows."""
    client, _ = seeded_client
    ids_by_seller: dict[str, set[int]] = {}
    for token, seller_key in TOKENS.items():
        response = client.get("/api/v3/orders/new", headers=AUTH[token])
        assert response.status_code == 200
        ids = {row["id"] for row in response.json()["orders"]}
        ids_by_seller[seller_key] = ids
        assert ids, f"{seller_key} should have seeded new orders"

    sellers = list(ids_by_seller)
    for left in sellers:
        for right in sellers:
            if left == right:
                continue
            assert ids_by_seller[left].isdisjoint(ids_by_seller[right])


def test_cancelled_seed_not_in_orders_new(seeded_client: tuple[TestClient, Path]) -> None:
    client, _ = seeded_client
    response = client.get("/api/v3/orders/new", headers=AUTH["token-c"])
    assert response.status_code == 200
    assert 530003 not in {row["id"] for row in response.json()["orders"]}


def test_kiz_required_meta_roundtrip(seeded_client: tuple[TestClient, Path]) -> None:
    client, _ = seeded_client
    response = client.get("/api/v3/orders/new", headers=AUTH["token-a"])
    assert response.status_code == 200
    by_id = {row["id"]: row for row in response.json()["orders"]}
    assert by_id[510002].get("requiredMeta") == ["sgtin"]


def test_every_sticker_and_qr_png_decodes(seeded_client: tuple[TestClient, Path]) -> None:
    """TC-23: order sticker is exact WB PNG; supply/trbx QR stay valid PNG."""
    client, _ = seeded_client
    new = client.get("/api/v3/orders/new", headers=AUTH["token-a"]).json()["orders"]
    order_ids = [row["id"] for row in new[:4]]
    assert order_ids

    stickers = client.post(
        "/api/v3/orders/stickers?type=png&width=58&height=40",
        headers=AUTH["token-a"],
        json={"orders": order_ids},
    )
    assert stickers.status_code == 200
    for row in stickers.json()["stickers"]:
        raw = base64.b64decode(row["file"], validate=True)
        assert hashlib.sha256(raw).hexdigest() in REAL_WB_ORDER_STICKER_SHA256
        image = Image.open(io.BytesIO(raw)).convert("RGB")
        assert image.size == (580, 400)
        assert row["barcode"].startswith("*DU")
        # The magenta WB mark is part of the original cabinet layout. A plain
        # black Code128 strip cannot satisfy this assertion.
        colors = image.getcolors(maxcolors=image.width * image.height)
        assert colors is not None
        assert any(r > 200 and b > 80 and g < 150 for _, (r, g, b) in colors)

    supply = client.post("/api/v3/supplies", headers=AUTH["token-a"], json={"name": "seed supply"})
    assert supply.status_code == 200
    supply_id = supply.json()["id"]

    delivered = client.patch(f"/api/v3/supplies/{supply_id}/deliver", headers=AUTH["token-a"])
    assert delivered.status_code == 204

    barcode = client.get(
        f"/api/v3/supplies/{supply_id}/barcode?type=png",
        headers=AUTH["token-a"],
    )
    assert barcode.status_code == 200
    assert barcode.content.startswith(PNG_MAGIC)
    supply_qr = Image.open(io.BytesIO(barcode.content))
    assert supply_qr.width >= 10 and supply_qr.height >= 10

    trbx = client.post(
        f"/api/v3/supplies/{supply_id}/trbx",
        headers=AUTH["token-a"],
        json={"amount": 1},
    )
    assert trbx.status_code == 200
    trbx_id = trbx.json()["trbxIds"][0]

    trbx_stickers = client.post(
        f"/api/v3/supplies/{supply_id}/trbx/stickers?type=png",
        headers=AUTH["token-a"],
        json={"trbxIds": [trbx_id]},
    )
    assert trbx_stickers.status_code == 200
    for row in trbx_stickers.json()["stickers"]:
        _assert_png(row["file"])


def test_restart_persistence_same_db_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """TC-23: new client on same SQLite file keeps seeded orders."""
    db_path = tmp_path / "persist.sqlite"
    monkeypatch.setenv("WB_EMULATOR_DB_PATH", str(db_path))
    monkeypatch.setenv("WB_EMULATOR_TOKEN_MAP", json.dumps(TOKENS))
    monkeypatch.setenv("WB_EMULATOR_ADMIN_TOKEN", "admin-secret")

    get_settings.cache_clear()
    reset_db_runtime()
    run_seed(db_path=db_path)

    get_settings.cache_clear()
    reset_db_runtime()
    init_db()
    app = create_app()
    with TestClient(app) as client:
        state = client.get("/__admin/state", headers=ADMIN)
        assert state.status_code == 200
        assert state.json()["orders_total"] >= 13

    reset_db_runtime()
    get_settings.cache_clear()


def test_idempotent_reseed_no_duplicates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """TC-23: running seed twice does not duplicate order rows."""
    db_path = tmp_path / "reseed.sqlite"
    monkeypatch.setenv("WB_EMULATOR_DB_PATH", str(db_path))
    get_settings.cache_clear()
    reset_db_runtime()

    run_seed(db_path=db_path)
    session = get_session_factory()()
    try:
        first_total = count_seeded_orders(session)
    finally:
        session.close()

    run_seed(db_path=db_path)
    session = get_session_factory()()
    try:
        second_total = count_seeded_orders(session)
    finally:
        session.close()

    assert first_total >= 13
    assert second_total == first_total

    reset_db_runtime()
    get_settings.cache_clear()


def test_admin_seed_endpoint_idempotent(seeded_client: tuple[TestClient, Path]) -> None:
    """TC-23: POST /__admin/seed is safe to repeat."""
    client, _ = seeded_client
    first = client.post("/__admin/seed", headers=ADMIN)
    assert first.status_code == 200
    second = client.post("/__admin/seed", headers=ADMIN)
    assert second.status_code == 200
    assert second.json()["orders_total"] >= 13


def test_fault_injection_409(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WB_EMULATOR_DB_PATH", str(tmp_path / "fault.sqlite"))
    monkeypatch.setenv("WB_EMULATOR_TOKEN_MAP", json.dumps(TOKENS))
    monkeypatch.setenv("WB_EMULATOR_FAULT_409", "1")
    get_settings.cache_clear()
    reset_db_runtime()
    init_db()
    app = create_app()
    with TestClient(app) as client:
        response = client.get("/api/v3/orders/new", headers=AUTH["token-a"])
        assert response.status_code == 409
    reset_db_runtime()
    get_settings.cache_clear()


def test_fault_injection_timeout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WB_EMULATOR_DB_PATH", str(tmp_path / "timeout.sqlite"))
    monkeypatch.setenv("WB_EMULATOR_TOKEN_MAP", json.dumps(TOKENS))
    monkeypatch.setenv("WB_EMULATOR_FAULT_TIMEOUT", "1")
    monkeypatch.setenv("WB_EMULATOR_FAULT_TIMEOUT_SECONDS", "0.05")
    get_settings.cache_clear()
    reset_db_runtime()
    init_db()
    app = create_app()
    with TestClient(app) as client:
        response = client.get("/api/v3/orders/new", headers=AUTH["token-a"])
        assert response.status_code == 504
    reset_db_runtime()
    get_settings.cache_clear()
