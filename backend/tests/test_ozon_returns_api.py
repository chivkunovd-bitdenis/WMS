"""API contract for Ozon return giveouts; every provider response is local and fake."""

from __future__ import annotations

import base64
import uuid
from types import SimpleNamespace
from typing import cast

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.inbound_intake import _refresh_ozon_return_statuses_after_posting
from app.api.ozon_returns import get_ozon_return_provider
from app.models.inbound_intake import InboundIntakeRequest
from app.services import ozon_return_service
from app.services.marketplace_account_service import MarketplaceAccountService
from app.services.marketplace_provider import FakeMarketplaceTransport, OzonMarketplaceProvider

BASE = "/operations/inbound-intake-requests"


async def _admin_headers(async_client: AsyncClient) -> dict[str, str]:
    suffix = uuid.uuid4().hex
    response = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Ozon returns API",
            "slug": f"ozon-returns-{suffix}",
            "admin_email": f"ozon-returns-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _return_request(
    async_client: AsyncClient,
    headers: dict[str, str],
    *,
    marketplace: str | None = "ozon",
) -> tuple[str, str]:
    suffix = uuid.uuid4().hex[:8]
    warehouse = await async_client.post(
        "/warehouses",
        headers=headers,
        json={"name": "Return warehouse", "code": f"ret-{suffix}"},
    )
    assert warehouse.status_code == 200, warehouse.text
    seller = await async_client.post(
        "/sellers", headers=headers, json={"name": f"Ozon Seller {suffix}"}
    )
    assert seller.status_code in (200, 201), seller.text
    created = await async_client.post(
        BASE,
        headers=headers,
        json={
            "warehouse_id": warehouse.json()["id"],
            "seller_id": seller.json()["id"],
            "operation_type": "return",
            "marketplace": marketplace,
        },
    )
    assert created.status_code == 201, created.text
    return created.json()["id"], seller.json()["id"]


def _transport() -> FakeMarketplaceTransport:
    png = base64.b64encode(b"png-pass").decode()
    pdf = base64.b64encode(b"pdf-pass").decode()
    return FakeMarketplaceTransport(
        endpoint_responses={
            "/v1/return/giveout/is-enabled": {"enabled": True},
            "/v1/return/giveout/list": {
                "giveouts": [
                    {
                        "giveout_id": 42,
                        "giveout_status": "GIVEOUT_STATUS_APPROVED",
                        "warehouse_id": 701,
                        "warehouse_name": "ПВЗ Тверская",
                        "warehouse_address": "Тверская, 1",
                        "approved_articles_count": 1,
                        "total_articles_count": 1,
                        "created_at": "2026-08-25T10:00:00Z",
                    }
                ]
            },
            "/v1/return/giveout/info": {
                "giveout_id": 42,
                "giveout_status": "GIVEOUT_STATUS_COMPLETED",
                "warehouse_name": "ПВЗ Тверская",
                "warehouse_address": "Тверская, 1",
                "articles": [{"name": "Неизвестный товар", "approved": True}],
            },
            "/v1/returns/list": {
                "has_next": False,
                "returns": [
                    {
                        "id": 101,
                        "posting_number": "123-456",
                        "return_reason_name": "Не подошёл",
                        "type": "FullReturn",
                        "product": {
                            "sku": 90210,
                            "offer_id": "offer-1",
                            "name": "Неизвестный товар",
                            "quantity": 1,
                        },
                        "logistic": {"barcode": "return-label-1"},
                        "storage": {
                            "days": 3,
                            "utilization_forecast_date": "2026-08-31",
                        },
                    }
                ],
            },
            "/v1/returns/company/fbs/info": {
                "has_next": False,
                "drop_off_points": [
                    {
                        "id": 11,
                        "name": "FBS точка",
                        "address": "Адрес, 2",
                        "returns_count": 2,
                        "pass_info": {"count": 1, "is_required": True},
                    }
                ],
            },
            "/v1/return/giveout/barcode": {"barcode": "seller-pass"},
            "/v1/return/giveout/get-pdf": {
                "file_content": pdf,
                "file_name": "pass.pdf",
                "content_type": "application/pdf",
            },
            "/v1/return/giveout/get-png": {
                "file_content": png,
                "file_name": "pass.png",
                "content_type": "image/png",
            },
            "/v1/return/giveout/barcode-reset": {
                "file_content": png,
                "file_name": "new-pass.png",
                "content_type": "image/png",
            },
        }
    )


@pytest.mark.asyncio
async def test_ozon_return_endpoints_use_all_return_operations_through_fake_transport(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = await _admin_headers(async_client)
    request_id, _seller_id = await _return_request(async_client, headers)
    transport = _transport()
    provider = OzonMarketplaceProvider(transport=transport)

    async def stored_credentials(
        _self: MarketplaceAccountService, _tenant_id: uuid.UUID, _seller_id: uuid.UUID
    ) -> tuple[str, str]:
        return "fake-client", "fake-key"

    monkeypatch.setattr(MarketplaceAccountService, "stored_credentials", stored_credentials)
    app = async_client._transport.app  # type: ignore[attr-defined]
    app.dependency_overrides[get_ozon_return_provider] = lambda: provider

    preview = await async_client.get(f"{BASE}/{request_id}/ozon-returns/preview", headers=headers)
    assert preview.status_code == 200, preview.text
    assert preview.json()["groups"][0]["items"][0]["warning"] == "Товар не сопоставлен с каталогом"

    imported = await async_client.post(
        f"{BASE}/{request_id}/ozon-returns/import",
        headers=headers,
        json={"giveout_ids": [42]},
    )
    assert imported.status_code == 200, imported.text
    assert imported.json() == {"giveouts_imported": 1, "items_imported": 1, "unmatched_items": 1}

    groups = await async_client.get(f"{BASE}/{request_id}/ozon-returns/groups", headers=headers)
    assert groups.status_code == 200, groups.text
    assert groups.json()[0]["giveout_status"] == "GIVEOUT_STATUS_COMPLETED"

    refreshed = await async_client.post(
        f"{BASE}/{request_id}/ozon-returns/refresh-statuses", headers=headers
    )
    assert refreshed.status_code == 200, refreshed.text
    assert refreshed.json()[0]["giveout_status"] == "GIVEOUT_STATUS_COMPLETED"

    points = await async_client.get(
        f"{BASE}/{request_id}/ozon-returns/fbs-return-points", headers=headers
    )
    assert points.status_code == 200, points.text
    assert points.json() == [
        {
            "id": 11,
            "name": "FBS точка",
            "address": "Адрес, 2",
            "place_id": None,
            "box_count": None,
            "returns_count": 2,
            "utc_offset": None,
            "warehouses_ids": [],
            "pass_count": 1,
            "pass_required": True,
        }
    ]

    barcode = await async_client.get(f"{BASE}/{request_id}/ozon-returns/barcode", headers=headers)
    assert barcode.json() == {"barcode": "seller-pass"}
    pdf = await async_client.get(f"{BASE}/{request_id}/ozon-returns/pass.pdf", headers=headers)
    assert pdf.status_code == 200 and pdf.content == b"pdf-pass"
    png = await async_client.get(f"{BASE}/{request_id}/ozon-returns/pass.png", headers=headers)
    assert png.status_code == 200 and png.content == b"png-pass"
    reset = await async_client.post(
        f"{BASE}/{request_id}/ozon-returns/barcode/reset.png", headers=headers
    )
    assert reset.status_code == 200 and reset.content == b"png-pass"
    assert [path for path, _payload in transport.endpoint_calls].count(
        "/v1/return/giveout/barcode-reset"
    ) == 1


@pytest.mark.asyncio
async def test_marketplace_is_return_only_and_is_in_request_output(
    async_client: AsyncClient,
) -> None:
    headers = await _admin_headers(async_client)
    suffix = uuid.uuid4().hex[:8]
    warehouse = await async_client.post(
        "/warehouses", headers=headers, json={"name": "W", "code": f"w-{suffix}"}
    )
    assert warehouse.status_code == 200

    rejected = await async_client.post(
        BASE,
        headers=headers,
        json={"warehouse_id": warehouse.json()["id"], "marketplace": "ozon"},
    )
    assert rejected.status_code == 422
    assert rejected.json()["detail"] == "marketplace_allowed_only_for_return"

    for marketplace in (None, "wildberries", "ozon"):
        created = await async_client.post(
            BASE,
            headers=headers,
            json={
                "warehouse_id": warehouse.json()["id"],
                "operation_type": "return",
                "marketplace": marketplace,
            },
        )
        assert created.status_code == 201, created.text
        assert created.json()["marketplace"] == marketplace


@pytest.mark.asyncio
async def test_return_defective_quantity_uses_the_inbound_service_constraint(
    async_client: AsyncClient,
) -> None:
    headers = await _admin_headers(async_client)
    request_id, seller_id = await _return_request(async_client, headers, marketplace=None)
    suffix = uuid.uuid4().hex[:8]
    product = await async_client.post(
        "/products",
        headers=headers,
        json={
            "name": "Возвратный товар",
            "sku_code": f"return-{suffix}",
            "seller_id": seller_id,
        },
    )
    assert product.status_code == 200, product.text
    line = await async_client.post(
        f"{BASE}/{request_id}/lines",
        headers=headers,
        json={"product_id": product.json()["id"], "expected_qty": 2},
    )
    assert line.status_code == 201, line.text
    line_id = line.json()["id"]
    planned = await async_client.patch(
        f"{BASE}/{request_id}", headers=headers, json={"planned_box_count": 1}
    )
    assert planned.status_code == 200, planned.text
    submitted = await async_client.post(f"{BASE}/{request_id}/submit", headers=headers)
    assert submitted.status_code == 200, submitted.text
    accepted = await async_client.patch(
        f"{BASE}/{request_id}/lines/{line_id}/actual",
        headers=headers,
        json={"actual_qty": 2},
    )
    assert accepted.status_code == 200, accepted.text

    defective = await async_client.patch(
        f"{BASE}/{request_id}/lines/{line_id}/defective",
        headers=headers,
        json={"defective_qty": 1},
    )
    assert defective.status_code == 200, defective.text
    assert defective.json()["defective_qty"] == 1
    exceeds_accepted = await async_client.patch(
        f"{BASE}/{request_id}/lines/{line_id}/defective",
        headers=headers,
        json={"defective_qty": 3},
    )
    assert exceeds_accepted.status_code == 422
    assert exceeds_accepted.json()["detail"] == "defective_qty_exceeds_accepted"


@pytest.mark.asyncio
async def test_posted_ozon_return_refresh_is_best_effort_and_uses_fake_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = cast(
        InboundIntakeRequest,
        SimpleNamespace(
            id=uuid.uuid4(), operation_type="return", marketplace="ozon"
        ),
    )
    calls: list[object] = []

    async def recorded_refresh(
        _session: AsyncSession,
        _request: InboundIntakeRequest,
        provider: OzonMarketplaceProvider,
    ) -> None:
        calls.append(provider.transport)

    monkeypatch.setattr(ozon_return_service, "refresh_giveout_statuses", recorded_refresh)
    await _refresh_ozon_return_statuses_after_posting(
        cast(AsyncSession, None), request
    )
    assert len(calls) == 1
    assert isinstance(calls[0], FakeMarketplaceTransport)

    async def failing_refresh(
        _session: AsyncSession,
        _request: InboundIntakeRequest,
        _provider: OzonMarketplaceProvider,
    ) -> None:
        raise ozon_return_service.OzonReturnError("ozon_unavailable", "Ozon недоступен")

    monkeypatch.setattr(ozon_return_service, "refresh_giveout_statuses", failing_refresh)
    await _refresh_ozon_return_statuses_after_posting(
        cast(AsyncSession, None), request
    )
