"""Loopback-only HTTP boundary for the WMS445 local acceptance harness."""

from __future__ import annotations

import os
from typing import Any

import httpx

_INSTALLED = False


def install_http_guard() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    allowed = {
        int(port)
        for port in os.environ.get(
            "WMS445_ALLOWED_HTTP_PORTS", "18082,18084,19092,19093,19094"
        ).split(",")
    }
    original_async = httpx.AsyncClient._send_single_request
    original_sync = httpx.Client._send_single_request

    def check(request: httpx.Request) -> None:
        if (
            request.url.host not in {"localhost", "127.0.0.1", "::1"}
            or request.url.port not in allowed
        ):
            raise httpx.ConnectError(
                "WMS445 harness blocked a non-allowlisted HTTP destination", request=request
            )

    async def guarded_async(
        client: httpx.AsyncClient, request: httpx.Request, **kwargs: Any
    ) -> httpx.Response:
        check(request)
        return await original_async(client, request, **kwargs)

    def guarded_sync(client: httpx.Client, request: httpx.Request, **kwargs: Any) -> httpx.Response:
        check(request)
        return original_sync(client, request, **kwargs)

    httpx.AsyncClient._send_single_request = guarded_async  # type: ignore[method-assign, assignment]
    httpx.Client._send_single_request = guarded_sync  # type: ignore[method-assign, assignment]
    _INSTALLED = True


def create_app() -> Any:
    install_http_guard()
    from app.main import create_app as wms_create_app

    return wms_create_app()
