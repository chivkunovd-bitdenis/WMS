"""Helpers to seed WMS inventory aligned with emulator order_templates (compose / tests)."""

from __future__ import annotations

from typing import Any

import httpx

from wb_emulator.services.orders_store import load_order_templates


def products_for_seller(seller_key: str) -> list[dict[str, Any]]:
    seen: set[int] = set()
    products: list[dict[str, Any]] = []
    for template in load_order_templates():
        if str(template.get("seller", "")).strip() != seller_key:
            continue
        chrt_id = int(template["chrtId"])
        if chrt_id in seen:
            continue
        seen.add(chrt_id)
        products.append(
            {
                "chrtId": chrt_id,
                "nmId": template["nmId"],
                "article": template["article"],
                "skus": list(template["skus"]),
            }
        )
    return products


async def register_ff_tenant(
    client: httpx.AsyncClient,
    *,
    suffix: str,
    password: str = "password123",
) -> tuple[dict[str, str], str]:
    reg = await client.post(
        "/auth/register",
        json={
            "organization_name": f"Emu seed {suffix}",
            "slug": f"emu-seed-{suffix}",
            "admin_email": f"emu-seed-{suffix}@example.com",
            "password": password,
        },
    )
    reg.raise_for_status()
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    return headers, suffix


async def create_seller_with_emulator_token(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    *,
    seller_name: str,
    emulator_token: str,
    warehouse_code: str,
) -> tuple[str, str]:
    seller = await client.post("/sellers", headers=headers, json={"name": seller_name})
    seller.raise_for_status()
    seller_id = seller.json()["id"]
    tok = await client.patch(
        f"/integrations/wildberries/sellers/{seller_id}/tokens",
        headers=headers,
        json={
            "supplies_api_token": emulator_token,
            "marketplace_api_token": emulator_token,
        },
    )
    tok.raise_for_status()
    warehouse = await client.post(
        "/warehouses",
        headers=headers,
        json={"name": f"FBS {seller_name}", "code": warehouse_code},
    )
    warehouse.raise_for_status()
    return seller_id, warehouse.json()["id"]


async def create_storage_location(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    *,
    warehouse_id: str,
    code: str,
) -> str:
    location = await client.post(
        f"/warehouses/{warehouse_id}/locations",
        headers=headers,
        json={"code": code},
    )
    location.raise_for_status()
    return location.json()["id"]


async def create_product_for_seller(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    *,
    seller_id: str,
    sku_code: str,
    name: str,
    wb_barcode: str,
) -> str:
    product = await client.post(
        "/products",
        headers=headers,
        json={
            "name": name,
            "sku_code": sku_code,
            "seller_id": seller_id,
            "wb_barcode": wb_barcode,
        },
    )
    product.raise_for_status()
    return product.json()["id"]


async def seed_wms_products_for_seller(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    *,
    seller_id: str,
    seller_key: str,
    suffix: str,
) -> list[str]:
    """Create WMS products matching emulator templates for one seller."""
    product_ids: list[str] = []
    for index, row in enumerate(products_for_seller(seller_key)):
        product_id = await create_product_for_seller(
            client,
            headers,
            seller_id=seller_id,
            sku_code=f"EMU-{seller_key[:3].upper()}-{suffix[-4:]}-{index}",
            name=f"Emu {seller_key} {row['article']}",
            wb_barcode=str(row["skus"][0]),
        )
        product_ids.append(product_id)
    return product_ids
