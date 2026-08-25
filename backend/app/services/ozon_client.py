"""The deliberately tiny, read-only Ozon validation boundary for S0."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Protocol

import httpx

OZON_SELLER_API_HOST = "https://api-seller.ozon.ru"


class OzonTransport(Protocol):
    async def request(
        self,
        *,
        host: str,
        method: str,
        path: str,
        headers: dict[str, str],
        json: object,
        follow_redirects: bool,
    ) -> int: ...


@dataclass(frozen=True)
class OzonValidationResult:
    status_code: int | None
    transport_failed: bool = False

    @classmethod
    def success(cls) -> OzonValidationResult:
        return cls(status_code=204)

    @classmethod
    def http(cls, status_code: int) -> OzonValidationResult:
        return cls(status_code=status_code)

    @classmethod
    def transport_error(cls) -> OzonValidationResult:
        return cls(status_code=None, transport_failed=True)


class OzonProviderError(Exception):
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        super().__init__("ozon provider validation failed")


class _HttpxOzonTransport:
    async def request(
        self,
        *,
        host: str,
        method: str,
        path: str,
        headers: dict[str, str],
        json: object,
        follow_redirects: bool,
    ) -> int:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=follow_redirects) as client:
            response = await client.request(method, f"{host}{path}", headers=headers, json=json)
        return response.status_code


class _PlaywrightLocalOzonTransport:
    """Composition-only fake for the Playwright-managed local backend."""

    async def request(
        self,
        *,
        host: str,
        method: str,
        path: str,
        headers: dict[str, str],
        json: object,
        follow_redirects: bool,
    ) -> int:
        _ = host, method, path, headers, json, follow_redirects
        return 204


async def validate_seller_info(
    *,
    transport: OzonTransport,
    client_id: str,
    api_key: str,
) -> OzonValidationResult:
    """Perform exactly one allowlisted request; response content is intentionally ignored."""
    try:
        status_code = await transport.request(
            host=OZON_SELLER_API_HOST,
            method="POST",
            path="/v1/seller/info",
            headers={
                "Client-Id": client_id,
                "Api-Key": api_key,
                "Content-Type": "application/json",
            },
            json={},
            follow_redirects=False,
        )
    except (httpx.HTTPError, TimeoutError, OSError):
        return OzonValidationResult.transport_error()
    if 200 <= status_code < 300:
        return OzonValidationResult.http(status_code)
    raise OzonProviderError(status_code)


async def validate_ozon_credentials(client_id: str, api_key: str) -> OzonValidationResult:
    """Production entrypoint, kept small so API tests can inject a local fake."""
    # This is deliberately a composition setting, not a request input.  Playwright
    # sets both values only for its disposable local backend; all ordinary processes
    # use the single allowlisted HTTP adapter below.
    transport: OzonTransport
    if (
        os.environ.get("E2E_MOCK_OZON_VALIDATION") == "1"
        and os.environ.get("WMS_AUTO_CREATE_SCHEMA") == "1"
    ):
        transport = _PlaywrightLocalOzonTransport()
    else:
        transport = _HttpxOzonTransport()
    try:
        return await validate_seller_info(transport=transport, client_id=client_id, api_key=api_key)
    except OzonProviderError as exc:
        return OzonValidationResult.http(exc.status_code)
