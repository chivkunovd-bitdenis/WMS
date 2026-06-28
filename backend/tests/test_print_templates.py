from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from app.db.session import SessionLocal
from app.models.print_template import LAYOUT_BLOCK_CZ, LAYOUT_BLOCK_LABEL
from app.services import print_template_service as pt_svc
from app.services.tokens import decode_access_token


async def _seed_tenant_seller_product(
    async_client: AsyncClient,
) -> tuple[str, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]:
    email = f"pt-{uuid.uuid4().hex[:8]}@example.com"
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Print Template FF",
            "slug": f"pt-{uuid.uuid4().hex[:8]}",
            "admin_email": email,
            "password": "password123",
        },
    )
    assert reg.status_code in (200, 201), reg.text
    token = reg.json()["access_token"]
    payload = decode_access_token(token)
    tenant_id = uuid.UUID(str(payload["tenant_id"]))
    user_id = uuid.UUID(str(payload["sub"]))
    headers = {"Authorization": f"Bearer {token}"}

    seller_resp = await async_client.post(
        "/sellers",
        headers=headers,
        json={"name": "PT Seller", "email": f"s-{uuid.uuid4().hex[:8]}@example.com"},
    )
    assert seller_resp.status_code == 201, seller_resp.text
    seller_id = uuid.UUID(seller_resp.json()["id"])

    product_resp = await async_client.post(
        "/products",
        headers=headers,
        json={
            "name": "Шаблон-товар",
            "sku_code": f"PT-{uuid.uuid4().hex[:6]}",
            "length_mm": 100,
            "width_mm": 100,
            "height_mm": 100,
            "seller_id": str(seller_id),
        },
    )
    assert product_resp.status_code == 200, product_resp.text
    product_id = uuid.UUID(product_resp.json()["id"])

    return token, tenant_id, user_id, seller_id, product_id


def _label_cz_layout() -> dict[str, object]:
    return {
        "units": [
            {"block": LAYOUT_BLOCK_LABEL, "copies": 1},
            {"block": LAYOUT_BLOCK_CZ, "copies": 1},
        ],
    }


@pytest.mark.asyncio
async def test_resolve_default_template_product_over_seller_over_system(
    async_client: AsyncClient,
) -> None:
    token, tenant_id, _user_id, seller_id, product_id = await _seed_tenant_seller_product(
        async_client
    )
    headers = {"Authorization": f"Bearer {token}"}

    async with SessionLocal() as session:
        system_row = await pt_svc.resolve_default_print_template(
            session,
            tenant_id,
            product_id=product_id,
            seller_id=seller_id,
        )
        assert system_row.is_system is True
        assert system_row.name == "Парами"
        assert system_row.layout.units[0].block == LAYOUT_BLOCK_CZ
        assert system_row.layout.units[0].copies == 2

        await pt_svc.create_print_template(
            session,
            tenant_id,
            name="Seller default",
            layout={"units": [{"block": LAYOUT_BLOCK_CZ, "copies": 1}]},
            seller_id=seller_id,
            is_default=True,
        )
        await session.commit()

    async with SessionLocal() as session:
        seller_row = await pt_svc.resolve_default_print_template(
            session,
            tenant_id,
            product_id=product_id,
            seller_id=seller_id,
        )
        assert seller_row.is_system is False
        assert seller_row.name == "Seller default"
        assert seller_row.layout.units[0].copies == 1

    create_product_tpl = await async_client.post(
        "/operations/marking-codes/print-templates",
        headers=headers,
        json={
            "name": "Product default",
            "layout": _label_cz_layout(),
            "product_id": str(product_id),
            "is_default": True,
        },
    )
    assert create_product_tpl.status_code == 201, create_product_tpl.text

    resolve_resp = await async_client.get(
        "/operations/marking-codes/print-templates/resolve",
        headers=headers,
        params={"product_id": str(product_id), "seller_id": str(seller_id)},
    )
    assert resolve_resp.status_code == 200, resolve_resp.text
    resolved = resolve_resp.json()
    assert resolved["name"] == "Product default"
    assert resolved["is_system"] is False
    assert resolved["layout"]["units"] == [
        {"block": LAYOUT_BLOCK_LABEL, "copies": 1},
        {"block": LAYOUT_BLOCK_CZ, "copies": 1},
    ]


@pytest.mark.asyncio
async def test_print_template_crud(async_client: AsyncClient) -> None:
    token, _tenant_id, _user_id, seller_id, product_id = await _seed_tenant_seller_product(
        async_client
    )
    headers = {"Authorization": f"Bearer {token}"}

    create_resp = await async_client.post(
        "/operations/marking-codes/print-templates",
        headers=headers,
        json={
            "name": "My template",
            "layout": _label_cz_layout(),
            "seller_id": str(seller_id),
        },
    )
    assert create_resp.status_code == 201, create_resp.text
    template_id = create_resp.json()["id"]

    list_resp = await async_client.get(
        "/operations/marking-codes/print-templates",
        headers=headers,
        params={"seller_id": str(seller_id)},
    )
    assert list_resp.status_code == 200, list_resp.text
    assert any(row["id"] == template_id for row in list_resp.json())

    update_resp = await async_client.put(
        f"/operations/marking-codes/print-templates/{template_id}",
        headers=headers,
        json={"name": "Renamed template", "is_default": True},
    )
    assert update_resp.status_code == 200, update_resp.text
    assert update_resp.json()["name"] == "Renamed template"
    assert update_resp.json()["is_default"] is True

    delete_resp = await async_client.delete(
        f"/operations/marking-codes/print-templates/{template_id}",
        headers=headers,
    )
    assert delete_resp.status_code == 204, delete_resp.text

    list_after = await async_client.get(
        "/operations/marking-codes/print-templates",
        headers=headers,
        params={"product_id": str(product_id)},
    )
    assert list_after.status_code == 200, list_after.text
    assert all(row["id"] != template_id for row in list_after.json())


@pytest.mark.asyncio
async def test_is_default_clears_previous_flag(async_client: AsyncClient) -> None:
    token, tenant_id, _user_id, seller_id, _product_id = await _seed_tenant_seller_product(
        async_client
    )
    headers = {"Authorization": f"Bearer {token}"}

    first = await async_client.post(
        "/operations/marking-codes/print-templates",
        headers=headers,
        json={
            "name": "First default",
            "layout": {"units": [{"block": LAYOUT_BLOCK_CZ, "copies": 1}]},
            "seller_id": str(seller_id),
            "is_default": True,
        },
    )
    assert first.status_code == 201, first.text
    first_id = uuid.UUID(first.json()["id"])

    second = await async_client.post(
        "/operations/marking-codes/print-templates",
        headers=headers,
        json={
            "name": "Second default",
            "layout": {"units": [{"block": LAYOUT_BLOCK_CZ, "copies": 2}]},
            "seller_id": str(seller_id),
            "is_default": True,
        },
    )
    assert second.status_code == 201, second.text

    async with SessionLocal() as session:
        first_row = await pt_svc.get_print_template(session, tenant_id, first_id)
        assert first_row.is_default is False


@pytest.mark.asyncio
async def test_user_last_layout_preferred_over_seller_default(
    async_client: AsyncClient,
) -> None:
    token, tenant_id, user_id, seller_id, product_id = await _seed_tenant_seller_product(
        async_client
    )
    headers = {"Authorization": f"Bearer {token}"}
    user_layout = {
        "units": [
            {"block": LAYOUT_BLOCK_LABEL, "copies": 1},
            {"block": LAYOUT_BLOCK_CZ, "copies": 2},
        ],
    }

    async with SessionLocal() as session:
        await pt_svc.create_print_template(
            session,
            tenant_id,
            name="Seller default",
            layout={"units": [{"block": LAYOUT_BLOCK_CZ, "copies": 1}]},
            seller_id=seller_id,
            is_default=True,
        )
        await pt_svc.save_user_last_print_layout(session, tenant_id, user_id, user_layout)

    resolve_resp = await async_client.get(
        "/operations/marking-codes/print-templates/resolve",
        headers=headers,
        params={"product_id": str(product_id), "seller_id": str(seller_id)},
    )
    assert resolve_resp.status_code == 200, resolve_resp.text
    resolved = resolve_resp.json()
    assert resolved["name"] == "Последняя раскладка"
    assert resolved["user_id"] == str(user_id)
    assert resolved["layout"]["units"] == user_layout["units"]


@pytest.mark.asyncio
async def test_two_users_get_different_last_layouts(async_client: AsyncClient) -> None:
    token_a, tenant_id, user_a_id, seller_id, product_id = await _seed_tenant_seller_product(
        async_client
    )
    headers_a = {"Authorization": f"Bearer {token_a}"}

    suffix = uuid.uuid4().hex[:8]
    staff_email = f"pt-staff-{suffix}@example.com"
    created = await async_client.post(
        "/auth/staff-accounts",
        headers=headers_a,
        json={"email": staff_email},
    )
    assert created.status_code == 201, created.text
    staff_id = created.json()["id"]
    patched = await async_client.patch(
        f"/auth/staff-accounts/{staff_id}/permissions",
        headers=headers_a,
        json={
            "settings": False,
            "mp_shipments": False,
            "reception": False,
            "cells": False,
            "inventory": False,
            "packaging": True,
        },
    )
    assert patched.status_code == 200, patched.text
    await async_client.post(
        "/auth/set-initial-password",
        json={"email": staff_email, "password": "password123"},
    )
    login_b = await async_client.post(
        "/auth/login",
        json={"email": staff_email, "password": "password123"},
    )
    assert login_b.status_code == 200, login_b.text
    token_b = login_b.json()["access_token"]
    user_b_id = uuid.UUID(str(decode_access_token(token_b)["sub"]))
    headers_b = {"Authorization": f"Bearer {token_b}"}

    layout_a = {"units": [{"block": LAYOUT_BLOCK_LABEL, "copies": 1}]}
    layout_b = {"units": [{"block": LAYOUT_BLOCK_CZ, "copies": 3}]}

    async with SessionLocal() as session:
        await pt_svc.save_user_last_print_layout(session, tenant_id, user_a_id, layout_a)
        await pt_svc.save_user_last_print_layout(session, tenant_id, user_b_id, layout_b)

    resolve_a = await async_client.get(
        "/operations/marking-codes/print-templates/resolve",
        headers=headers_a,
        params={"product_id": str(product_id), "seller_id": str(seller_id)},
    )
    resolve_b = await async_client.get(
        "/operations/marking-codes/print-templates/resolve",
        headers=headers_b,
        params={"product_id": str(product_id), "seller_id": str(seller_id)},
    )
    assert resolve_a.status_code == 200, resolve_a.text
    assert resolve_b.status_code == 200, resolve_b.text
    assert resolve_a.json()["layout"]["units"] == layout_a["units"]
    assert resolve_b.json()["layout"]["units"] == layout_b["units"]
    assert resolve_a.json()["user_id"] == str(user_a_id)
    assert resolve_b.json()["user_id"] == str(user_b_id)


@pytest.mark.asyncio
async def test_print_auto_saves_user_last_layout(async_client: AsyncClient) -> None:
    from test_marking_print_pool import _seed_product_with_pool_codes
    from test_packaging_tasks import _inventory_at_location

    h, _seller_id, product_id, wh_id = await _seed_product_with_pool_codes(
        async_client, code_count=5
    )
    user_id = uuid.UUID(str(decode_access_token(h["Authorization"].split()[1])["sub"]))
    tenant_id = uuid.UUID(str(decode_access_token(h["Authorization"].split()[1])["tenant_id"]))

    loc_id = await _inventory_at_location(
        async_client,
        h,
        warehouse_id=wh_id,
        product_id=product_id,
        qty=5,
        location_code="pt-user-layout",
    )
    task = await async_client.post(
        "/operations/packaging-tasks",
        headers=h,
        json={
            "warehouse_id": wh_id,
            "lines": [
                {
                    "product_id": product_id,
                    "storage_location_id": loc_id,
                    "quantity": 5,
                }
            ],
        },
    )
    assert task.status_code == 201, task.text
    line_id = task.json()["lines"][0]["id"]

    custom_layout = {
        "units": [
            {"block": LAYOUT_BLOCK_LABEL, "copies": 1},
            {"block": LAYOUT_BLOCK_CZ, "copies": 1},
            {"block": LAYOUT_BLOCK_LABEL, "copies": 1},
        ],
    }
    printed = await async_client.post(
        f"/operations/marking-codes/packaging-lines/{line_id}/print",
        headers=h,
        json={"layout_json": custom_layout, "allow_partial": False},
    )
    assert printed.status_code == 200, printed.text
    assert printed.json()["quantity"] == 5

    resolve_resp = await async_client.get(
        "/operations/marking-codes/print-templates/resolve",
        headers=h,
        params={"product_id": product_id},
    )
    assert resolve_resp.status_code == 200, resolve_resp.text
    resolved = resolve_resp.json()
    assert resolved["user_id"] == str(user_id)
    assert resolved["layout"]["units"] == custom_layout["units"]

    list_resp = await async_client.get(
        "/operations/marking-codes/print-templates",
        headers=h,
    )
    assert list_resp.status_code == 200, list_resp.text
    assert all(row["name"] != pt_svc.USER_LAST_LAYOUT_NAME for row in list_resp.json())

    async with SessionLocal() as session:
        row = await pt_svc.resolve_default_print_template(
            session,
            tenant_id,
            user_id=user_id,
            product_id=uuid.UUID(product_id),
        )
        assert row.layout.units[0].block == LAYOUT_BLOCK_LABEL
        assert len(row.layout.units) == 3

