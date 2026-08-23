import time
import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient

from app.db.session import SessionLocal
from app.models.product import Product
from app.models.product_dimension_event import ProductDimensionEvent

FF_PERMISSION_DEFAULTS = {
    "settings": False,
    "mp_shipments": False,
    "reception": False,
    "cells": False,
    "inventory": False,
    "packaging": False,
    "shift_lead": False,
}


async def _register_admin(
    async_client: AsyncClient,
    suffix: str,
    label: str,
) -> tuple[dict[str, str], str]:
    email = f"dimensions-{label}-{suffix}@example.com"
    registration = await async_client.post(
        "/auth/register",
        json={
            "organization_name": f"Dimensions API {label}",
            "slug": f"dimensions-{label}-{suffix}",
            "admin_email": email,
            "password": "password123",
        },
    )
    assert registration.status_code == 200, registration.text
    return (
        {"Authorization": f"Bearer {registration.json()['access_token']}"},
        email,
    )


async def _create_staff_headers(
    async_client: AsyncClient,
    admin_headers: dict[str, str],
    suffix: str,
    label: str,
    *,
    inventory: bool,
) -> dict[str, str]:
    email = f"dimensions-staff-{label}-{suffix}@example.com"
    created = await async_client.post(
        "/auth/staff-accounts",
        headers=admin_headers,
        json={"email": email},
    )
    assert created.status_code == 201, created.text
    patched = await async_client.patch(
        f"/auth/staff-accounts/{created.json()['id']}/permissions",
        headers=admin_headers,
        json={**FF_PERMISSION_DEFAULTS, "inventory": inventory},
    )
    assert patched.status_code == 200, patched.text
    password = await async_client.post(
        "/auth/set-initial-password",
        json={"email": email, "password": "password123"},
    )
    assert password.status_code == 200, password.text
    login = await async_client.post(
        "/auth/login",
        json={"email": email, "password": "password123"},
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


async def _create_product(
    async_client: AsyncClient,
    headers: dict[str, str],
    suffix: str,
) -> str:
    created = await async_client.post(
        "/products",
        headers=headers,
        json={"name": "Measured", "sku_code": f"SKU-{suffix}"},
    )
    assert created.status_code == 200, created.text
    return str(created.json()["id"])


@pytest.mark.asyncio
async def test_inventory_staff_saves_both_measurements_and_reads_ui_history(
    async_client: AsyncClient,
) -> None:
    suffix = str(time.time_ns())
    admin_headers, _ = await _register_admin(async_client, suffix, "measure")
    staff_headers = await _create_staff_headers(
        async_client,
        admin_headers,
        suffix,
        "inventory",
        inventory=True,
    )
    product_id = await _create_product(async_client, admin_headers, suffix)

    saved = await async_client.post(
        f"/products/{product_id}/dimensions/container",
        headers=staff_headers,
        json={"volume_liters": 2.5, "container_basis": "Короб подтверждён при приёмке"},
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["volume_liters"] == pytest.approx(2.5)
    assert saved.json()["dimensions_source"] == "container_override"
    assert saved.json()["dimensions_updated_at"] is not None
    assert saved.json()["dimensions_updated_by_user_id"] is not None

    history = await async_client.get(
        f"/products/{product_id}/dimensions/history", headers=staff_headers
    )
    assert history.status_code == 200, history.text
    assert history.json()[0]["source"] == "container"
    assert history.json()[0]["created_at"] is not None
    assert history.json()[0]["author_name"].startswith("dimensions-staff-inventory-")
    assert history.json()[0]["is_current"] is True

    invalid = await async_client.post(
        f"/products/{product_id}/dimensions/container",
        headers=staff_headers,
        json={"volume_liters": 3, "container_basis": "   "},
    )
    assert invalid.status_code == 422

    partial = await async_client.patch(
        f"/products/{product_id}/dimensions",
        headers=staff_headers,
        json={"length_mm": 10},
    )
    assert partial.status_code == 422

    zero = await async_client.patch(
        f"/products/{product_id}/dimensions",
        headers=staff_headers,
        json={"length_mm": 0, "width_mm": 10, "height_mm": 10},
    )
    assert zero.status_code == 422

    manual = await async_client.patch(
        f"/products/{product_id}/dimensions",
        headers=staff_headers,
        json={"length_mm": 100, "width_mm": 200, "height_mm": 300},
    )
    assert manual.status_code == 200, manual.text
    assert manual.json()["volume_liters"] == pytest.approx(6.0)
    assert manual.json()["dimensions_source"] == "manual"
    assert manual.json()["dimensions_updated_at"] is not None
    assert manual.json()["dimensions_updated_by_user_id"] is not None

    history = await async_client.get(
        f"/products/{product_id}/dimensions/history", headers=staff_headers
    )
    assert history.status_code == 200, history.text
    rows = history.json()
    assert [row["source"] for row in rows] == ["manual", "container"]
    assert rows[0]["created_at"] >= rows[1]["created_at"]
    assert rows[0]["author_name"].startswith("dimensions-staff-inventory-")
    assert rows[0]["is_current"] is True
    assert rows[1]["is_current"] is False
    assert all("observed_at" not in row and "applied" not in row for row in rows)


@pytest.mark.asyncio
async def test_invalid_measurements_and_foreign_tenant_do_not_write_history(
    async_client: AsyncClient,
) -> None:
    suffix = str(time.time_ns())
    first_headers, _ = await _register_admin(async_client, suffix, "first")
    second_headers, _ = await _register_admin(async_client, suffix, "second")
    first_product_id = await _create_product(async_client, first_headers, f"first-{suffix}")
    second_product_id = await _create_product(async_client, second_headers, f"second-{suffix}")

    incomplete = await async_client.patch(
        f"/products/{first_product_id}/dimensions",
        headers=first_headers,
        json={"length_mm": 100, "width_mm": 200},
    )
    assert incomplete.status_code == 422
    zero = await async_client.post(
        f"/products/{first_product_id}/dimensions/container",
        headers=first_headers,
        json={"volume_liters": 0, "container_basis": "Короб"},
    )
    assert zero.status_code == 422

    foreign_patch = await async_client.patch(
        f"/products/{second_product_id}/dimensions",
        headers=first_headers,
        json={"length_mm": 100, "width_mm": 200, "height_mm": 300},
    )
    assert foreign_patch.status_code == 404
    foreign_history = await async_client.get(
        f"/products/{second_product_id}/dimensions/history",
        headers=first_headers,
    )
    assert foreign_history.status_code == 404

    first_history = await async_client.get(
        f"/products/{first_product_id}/dimensions/history",
        headers=first_headers,
    )
    second_history = await async_client.get(
        f"/products/{second_product_id}/dimensions/history",
        headers=second_headers,
    )
    assert first_history.status_code == 200
    assert first_history.json() == []
    assert second_history.status_code == 200
    assert second_history.json() == []


@pytest.mark.asyncio
async def test_only_admin_can_restore_latest_wb_dimensions(
    async_client: AsyncClient,
) -> None:
    suffix = str(time.time_ns())
    admin_headers, _ = await _register_admin(async_client, suffix, "restore")
    staff_headers = await _create_staff_headers(
        async_client,
        admin_headers,
        suffix,
        "restore",
        inventory=True,
    )
    no_inventory_headers = await _create_staff_headers(
        async_client,
        admin_headers,
        suffix,
        "denied",
        inventory=False,
    )
    product_id = await _create_product(async_client, admin_headers, f"restore-{suffix}")

    manual = await async_client.patch(
        f"/products/{product_id}/dimensions",
        headers=staff_headers,
        json={"length_mm": 100, "width_mm": 100, "height_mm": 100},
    )
    assert manual.status_code == 200, manual.text

    async with SessionLocal() as session:
        product = await session.get(Product, uuid.UUID(product_id))
        assert product is not None
        session.add(
            ProductDimensionEvent(
                tenant_id=product.tenant_id,
                product_id=product.id,
                source="wb",
                length_mm=200,
                width_mm=200,
                height_mm=200,
                volume_liters=Decimal("8"),
                applied=False,
                fingerprint=f"wb-{suffix}",
            )
        )
        await session.commit()

    denied = await async_client.post(
        f"/products/{product_id}/dimensions/restore-wb",
        headers=staff_headers,
    )
    assert denied.status_code == 403
    denied_measure = await async_client.patch(
        f"/products/{product_id}/dimensions",
        headers=no_inventory_headers,
        json={"length_mm": 300, "width_mm": 300, "height_mm": 300},
    )
    assert denied_measure.status_code == 403

    restore = await async_client.post(
        f"/products/{product_id}/dimensions/restore-wb", headers=admin_headers
    )
    assert restore.status_code == 200, restore.text
    assert restore.json()["dimensions_source"] == "wb"
    assert restore.json()["volume_liters"] == pytest.approx(8.0)

    history = await async_client.get(
        f"/products/{product_id}/dimensions/history",
        headers=staff_headers,
    )
    assert history.status_code == 200, history.text
    assert history.json()[0]["source"] == "wildberries"
    assert history.json()[0]["author_name"] is None
    assert history.json()[0]["is_current"] is True
