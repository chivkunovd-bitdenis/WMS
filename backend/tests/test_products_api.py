import time

import pytest


@pytest.mark.asyncio
async def test_product_dimension_history_and_container_measurement(async_client):
    suffix = str(time.time_ns())
    registration = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Dimensions API",
            "slug": f"dimensions-{suffix}",
            "admin_email": f"dimensions-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert registration.status_code == 200, registration.text
    headers = {"Authorization": f"Bearer {registration.json()['access_token']}"}
    created = await async_client.post(
        "/products",
        headers=headers,
        json={"name": "Measured", "sku_code": f"SKU-{suffix}"},
    )
    assert created.status_code == 200, created.text
    product_id = created.json()["id"]

    saved = await async_client.post(
        f"/products/{product_id}/dimensions/container",
        headers=headers,
        json={"volume_liters": 2.5, "container_basis": "Короб подтверждён при приёмке"},
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["volume_liters"] == pytest.approx(2.5)

    history = await async_client.get(
        f"/products/{product_id}/dimensions/history", headers=headers
    )
    assert history.status_code == 200, history.text
    assert history.json()[0]["source"] == "container"
    assert history.json()[0]["applied"] is True

    invalid = await async_client.post(
        f"/products/{product_id}/dimensions/container",
        headers=headers,
        json={"volume_liters": 0, "container_basis": ""},
    )
    assert invalid.status_code == 422

