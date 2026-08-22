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
    assert saved.json()["dimensions_source"] == "container_override"
    assert saved.json()["dimensions_updated_at"] is not None
    assert saved.json()["dimensions_updated_by_user_id"] is not None

    history = await async_client.get(
        f"/products/{product_id}/dimensions/history", headers=headers
    )
    assert history.status_code == 200, history.text
    assert history.json()[0]["source"] == "container_override"
    assert history.json()[0]["applied"] is True

    invalid = await async_client.post(
        f"/products/{product_id}/dimensions/container",
        headers=headers,
        json={"volume_liters": 0, "container_basis": ""},
    )
    assert invalid.status_code == 422

    partial = await async_client.patch(
        f"/products/{product_id}/dimensions",
        headers=headers,
        json={"length_mm": 10},
    )
    assert partial.status_code == 422

    zero = await async_client.patch(
        f"/products/{product_id}/dimensions",
        headers=headers,
        json={"length_mm": 0, "width_mm": 10, "height_mm": 10},
    )
    assert zero.status_code == 422

    manual = await async_client.patch(
        f"/products/{product_id}/dimensions",
        headers=headers,
        json={"length_mm": 100, "width_mm": 200, "height_mm": 300},
    )
    assert manual.status_code == 200, manual.text
    assert manual.json()["volume_liters"] == pytest.approx(6.0)
    assert manual.json()["dimensions_source"] == "manual"
    assert manual.json()["dimensions_updated_at"] is not None
    assert manual.json()["dimensions_updated_by_user_id"] is not None

    history = await async_client.get(
        f"/products/{product_id}/dimensions/history", headers=headers
    )
    assert history.status_code == 200, history.text
    assert history.json()[0]["source"] == "manual"
    assert history.json()[0]["author_user_id"] is not None
    assert history.json()[0]["applied"] is True

    restore = await async_client.post(
        f"/products/{product_id}/dimensions/restore-wb", headers=headers
    )
    assert restore.status_code == 404
    assert restore.json()["detail"] == "wb_dimensions_not_found"
