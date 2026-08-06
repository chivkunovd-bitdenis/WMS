"""Smoke tests for EMU-010 scaffold: health, auth, SQLite bootstrap."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from wb_emulator.db import init_db, reset_db_runtime
from wb_emulator.main import create_app
from wb_emulator.settings import Settings, get_settings


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

    app = create_app()
    with TestClient(app) as test_client:
        yield test_client

    reset_db_runtime()
    get_settings.cache_clear()


def test_health_returns_200(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_unknown_token_on_api_v3_returns_401(client: TestClient) -> None:
    response = client.get("/api/v3/orders/new")
    assert response.status_code == 401
    assert response.json() == {"detail": "Unauthorized"}


def test_known_token_passes_auth_middleware(client: TestClient) -> None:
    response = client.get("/api/v3/orders/new", headers={"Authorization": "env-token"})
    assert response.status_code != 401
    assert response.status_code == 200
    assert "orders" in response.json()


def test_sqlite_file_created_on_startup(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    settings = get_settings()
    assert settings.db_path.exists()
    assert settings.db_path.stat().st_size > 0


def test_token_map_file_override(client: TestClient) -> None:
    settings = get_settings()
    assert settings.seller_key_for_token("file-token") == "seller_from_file"
    assert settings.seller_key_for_token("env-token") == "seller_env"


def test_dynamic_test_token_requires_explicit_switch() -> None:
    assert Settings().seller_key_for_token("wms-test-seller-1") is None
    enabled = Settings(allow_dynamic_test_tokens=True)
    assert enabled.seller_key_for_token("wms-test-seller-1") == "wms-test-seller-1"
    assert enabled.seller_key_for_token("unknown-token") is None


def test_init_db_creates_schema(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "manual.sqlite"
    monkeypatch.setenv("WB_EMULATOR_DB_PATH", str(db_path))
    get_settings.cache_clear()
    reset_db_runtime()

    created = init_db(Settings())
    assert created == db_path.resolve()
    assert db_path.exists()

    reset_db_runtime()
    get_settings.cache_clear()
