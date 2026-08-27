from __future__ import annotations

import time

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_manual_invoice_v2_preview_save_retry_and_cancel(async_client: AsyncClient) -> None:
    suffix = f"invoice-v2-{time.time_ns()}"
    registered = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Invoice v2",
            "slug": suffix,
            "admin_email": f"{suffix}@example.com",
            "password": "password123",
        },
    )
    assert registered.status_code == 200, registered.text
    headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}
    seller = await async_client.post("/sellers", headers=headers, json={"name": "Ручной селлер"})
    seller_id = seller.json()["id"]
    body = {
        "creation_mode": "manual",
        "seller_id": seller_id,
        "lines": [{"description": "Ручная услуга", "amount": "630.00", "unit_price": "12.50"}],
    }

    preview = await async_client.post("/billing/invoices-v2/preview", headers=headers, json=body)
    assert preview.status_code == 200, preview.text
    assert preview.json()["total_amount_kopecks"] == 63000
    assert preview.json()["lines"][0]["unit_price_kopecks"] == 1250

    saved = await async_client.post(
        "/billing/invoices-v2", headers={**headers, "Idempotency-Key": "manual-1"}, json=body
    )
    assert saved.status_code == 201, saved.text
    invoice_id = saved.json()["id"]
    retry = await async_client.post(
        "/billing/invoices-v2", headers={**headers, "Idempotency-Key": "manual-1"}, json=body
    )
    assert retry.status_code == 201
    assert retry.json()["id"] == invoice_id
    changed = await async_client.post(
        "/billing/invoices-v2",
        headers={**headers, "Idempotency-Key": "manual-1"},
        json={**body, "lines": [{"description": "Другая", "amount": "1.00"}]},
    )
    assert changed.status_code == 409
    cancelled = await async_client.post(
        f"/billing/invoices-v2/{invoice_id}/cancel", headers=headers
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"


@pytest.mark.asyncio
async def test_manual_invoice_v2_rejects_decimal_float_and_missing_key(
    async_client: AsyncClient,
) -> None:
    suffix = f"invoice-v2-negative-{time.time_ns()}"
    registered = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Invoice v2",
            "slug": suffix,
            "admin_email": f"{suffix}@example.com",
            "password": "password123",
        },
    )
    assert registered.status_code == 200, registered.text
    headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}
    seller = await async_client.post("/sellers", headers=headers, json={"name": "Селлер"})
    body = {
        "creation_mode": "manual",
        "seller_id": seller.json()["id"],
        "lines": [{"description": "Услуга", "amount": "1.234"}],
    }
    assert (
        await async_client.post("/billing/invoices-v2/preview", headers=headers, json=body)
    ).status_code == 422
    body["lines"][0]["amount"] = "1.00"
    assert (
        await async_client.post("/billing/invoices-v2", headers=headers, json=body)
    ).status_code == 422
