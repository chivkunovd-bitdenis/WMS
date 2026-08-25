# ruff: noqa: RUF002
"""Лог исходящих вызовов к маркетплейсам: включается и не светит токен."""

from __future__ import annotations

import logging

import httpx
import pytest

from app.core.logging_setup import setup_outbound_http_logging
from app.core.settings import settings
from app.services.wildberries_client import fetch_marketplace_orders_new

SECRET = "eyJhbGciOiJFUzI1NiJ9.SUPER-SECRET-TOKEN-VALUE"


def test_logging_enabled_by_default() -> None:
    setup_outbound_http_logging()
    assert settings.log_outbound_http is True
    assert logging.getLogger("httpx").level == logging.INFO


def test_can_be_switched_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "log_outbound_http", False)
    setup_outbound_http_logging()
    assert logging.getLogger("httpx").level == logging.WARNING


@pytest.mark.asyncio
async def test_outbound_call_is_logged_without_token(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Вызов к WB виден в логе методом и адресом, а токен — нет."""
    monkeypatch.setattr(settings, "e2e_mock_wb_marketplace_orders", False)
    setup_outbound_http_logging()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == SECRET  # токен реально уходит
        return httpx.Response(200, json=[])

    transport = httpx.MockTransport(handler)
    with caplog.at_level(logging.INFO, logger="httpx"):
        async with httpx.AsyncClient(transport=transport) as client:
            await fetch_marketplace_orders_new(client, api_token=SECRET)

    logged = "\n".join(r.getMessage() for r in caplog.records)
    assert "/api/v3/orders/new" in logged
    assert "GET" in logged
    assert SECRET not in logged
    assert "Authorization" not in logged
