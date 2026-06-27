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
) -> tuple[str, uuid.UUID, uuid.UUID, uuid.UUID]:
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
    tenant_id = uuid.UUID(str(decode_access_token(token)["tenant_id"]))
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

    return token, tenant_id, seller_id, product_id


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
    token, tenant_id, seller_id, product_id = await _seed_tenant_seller_product(async_client)
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
    token, _tenant_id, seller_id, product_id = await _seed_tenant_seller_product(async_client)
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
    token, tenant_id, seller_id, _product_id = await _seed_tenant_seller_product(async_client)
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
