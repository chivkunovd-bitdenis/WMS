"""Async WMS seed helper for WB emulator operator flow (3 sellers + inventory + marking pools)."""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from httpx import AsyncClient
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.marking_code import STATUS_AVAILABLE, MarkingCode, MarkingPool, MarkingPoolProduct
from app.models.product import Product
from app.services import inventory_service
from app.services.sorting_location_service import get_or_create_sorting_location
from tests.fbs_seed_helpers import DEFAULT_WB_WAREHOUSE_ID, seed_fbs_warehouse_binding
from tests.inventory_actor_helpers import resolve_test_actor_user_id

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TEMPLATES_PATH = _REPO_ROOT / "wb_emulator" / "seed" / "order_templates.json"
_TOKENS_PATH = _REPO_ROOT / "wb_emulator" / "seed" / "tokens.json"

DEFAULT_EMULATOR_TOKENS: dict[str, str] = {
    "token-a": "seller_a",
    "token-b": "seller_b",
    "token-c": "seller_c",
}


@dataclass
class OperatorSellerSeed:
    seller_key: str
    token: str
    seller_id: uuid.UUID
    products_by_chrt: dict[int, uuid.UUID] = field(default_factory=dict)


@dataclass
class OperatorEmulatorSeedResult:
    tenant_id: uuid.UUID
    admin_headers: dict[str, str]
    admin_email: str
    admin_password: str
    warehouse_id: uuid.UUID
    storage_location_id: uuid.UUID
    storage_location_code: str
    sellers: dict[str, OperatorSellerSeed]
    marking_pools_by_chrt: dict[int, uuid.UUID] = field(default_factory=dict)


def load_emulator_templates() -> list[dict[str, Any]]:
    raw = json.loads(_TEMPLATES_PATH.read_text(encoding="utf-8"))
    templates = raw.get("templates", [])
    if not isinstance(templates, list):
        raise ValueError("order_templates.json: templates must be a list")
    return templates


def load_emulator_tokens(path: Path | None = None) -> dict[str, str]:
    token_path = path or _TOKENS_PATH
    raw = json.loads(token_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{token_path} must contain a JSON object")
    return {str(token): str(seller_key) for token, seller_key in raw.items()}


async def _register_ff_admin(
    async_client: AsyncClient,
) -> tuple[dict[str, str], uuid.UUID, str, str, str]:
    suffix = str(time.time_ns())
    email = f"emu-op-{suffix}@example.com"
    password = "password123"
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": f"Emu operator {suffix}",
            "slug": f"emu-op-{suffix}",
            "admin_email": email,
            "password": password,
        },
    )
    assert reg.status_code == 200, reg.text
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    me = await async_client.get("/auth/me", headers=headers)
    assert me.status_code == 200, me.text
    tenant_id = uuid.UUID(me.json()["tenant_id"])
    return headers, tenant_id, suffix, email, password


async def seed_operator_emulator_wms(
    async_client: AsyncClient,
    *,
    tokens: dict[str, str] | None = None,
    inventory_qty: int = 50,
) -> OperatorEmulatorSeedResult:
    """Seed one FF tenant, three sellers, bindings, products, inventory, marking pool stubs."""
    token_map = tokens or load_emulator_tokens()
    templates = load_emulator_templates()
    headers, tenant_id, suffix, admin_email, admin_password = await _register_ff_admin(
        async_client
    )

    warehouse = await async_client.post(
        "/warehouses",
        headers=headers,
        json={"name": "Operator FBS WH", "code": f"op-wh-{suffix[-8:]}"},
    )
    assert warehouse.status_code in (200, 201), warehouse.text
    warehouse_id = uuid.UUID(warehouse.json()["id"])

    storage_location_code = f"OP-{suffix[-6:]}"
    location = await async_client.post(
        f"/warehouses/{warehouse_id}/locations",
        headers=headers,
        json={"code": storage_location_code},
    )
    assert location.status_code in (200, 201), location.text
    storage_location_id = uuid.UUID(location.json()["id"])

    async with SessionLocal() as session:
        await get_or_create_sorting_location(session, tenant_id, warehouse_id)

    sellers: dict[str, OperatorSellerSeed] = {}
    chrt_templates: dict[tuple[str, int], dict[str, Any]] = {}
    for template in templates:
        seller_key = str(template.get("seller", "")).strip()
        chrt_id = int(template["chrtId"])
        if seller_key:
            chrt_templates[(seller_key, chrt_id)] = template

    for token, seller_key in token_map.items():
        seller_resp = await async_client.post(
            "/sellers",
            headers=headers,
            json={"name": f"Emu {seller_key}"},
        )
        assert seller_resp.status_code in (200, 201), seller_resp.text
        seller_id = uuid.UUID(seller_resp.json()["id"])

        tok = await async_client.patch(
            f"/integrations/wildberries/sellers/{seller_id}/tokens",
            headers=headers,
            json={
                "supplies_api_token": token,
                "marketplace_api_token": token,
            },
        )
        assert tok.status_code == 200, tok.text

        async with SessionLocal() as session:
            await seed_fbs_warehouse_binding(
                session,
                tenant_id=tenant_id,
                seller_id=seller_id,
                wms_warehouse_id=warehouse_id,
                wb_warehouse_id=DEFAULT_WB_WAREHOUSE_ID,
            )
            await session.commit()

        products_by_chrt: dict[int, uuid.UUID] = {}
        for (sk, chrt_id), template in chrt_templates.items():
            if sk != seller_key:
                continue
            product = await async_client.post(
                "/products",
                headers=headers,
                json={
                    "name": template["article"],
                    "sku_code": f"{seller_key}-{chrt_id}",
                    "seller_id": str(seller_id),
                    "wb_barcode": template["skus"][0],
                },
            )
            assert product.status_code in (200, 201), product.text
            product_id = uuid.UUID(product.json()["id"])
            products_by_chrt[chrt_id] = product_id

            requires_kiz = bool(template.get("requiredMeta"))
            async with SessionLocal() as session:
                row = await session.get(Product, product_id)
                assert row is not None
                row.wb_chrt_id = chrt_id
                row.wb_nm_id = int(template["nmId"])
                row.wb_barcode = template["skus"][0]
                row.requires_honest_sign = requires_kiz
                # Признак участия в ФБС по умолчанию выключен: иначе включение
                # синхронизации выгрузило бы в WB весь каталог. Для сида поднимаем
                # явно, иначе остаток не уедет в эмулятор и тот откажется
                # создавать заказ, отвечая rejected_no_stock.
                row.fbs_stock_sync_enabled = True
                row.fbs_percent = 100
                await session.commit()

                await inventory_service.record_movement_and_adjust_balance(
                    session,
                    tenant_id=tenant_id,
                    product_id=product_id,
                    storage_location_id=storage_location_id,
                    quantity_delta=inventory_qty,
                    movement_type="inbound_intake",
                    actor_user_id=await resolve_test_actor_user_id(session, tenant_id),
                )
                await session.commit()

        sellers[seller_key] = OperatorSellerSeed(
            seller_key=seller_key,
            token=token,
            seller_id=seller_id,
            products_by_chrt=products_by_chrt,
        )

    marking_pools_by_chrt = await _seed_marking_pool_stubs(tenant_id, sellers, templates)

    return OperatorEmulatorSeedResult(
        tenant_id=tenant_id,
        admin_headers=headers,
        admin_email=admin_email,
        admin_password=admin_password,
        warehouse_id=warehouse_id,
        storage_location_id=storage_location_id,
        storage_location_code=storage_location_code,
        sellers=sellers,
        marking_pools_by_chrt=marking_pools_by_chrt,
    )


async def _seed_marking_pool_stubs(
    tenant_id: uuid.UUID,
    sellers: dict[str, OperatorSellerSeed],
    templates: list[dict[str, Any]],
) -> dict[int, uuid.UUID]:
    """Create seller-scoped marking pools with one available code per KIZ-required chrtId."""
    pools: dict[int, uuid.UUID] = {}
    async with SessionLocal() as session:
        for template in templates:
            required = template.get("requiredMeta") or []
            if "sgtin" not in required:
                continue
            seller_key = str(template.get("seller", "")).strip()
            seller = sellers.get(seller_key)
            if seller is None:
                continue
            chrt_id = int(template["chrtId"])
            product_id = seller.products_by_chrt.get(chrt_id)
            if product_id is None:
                continue
            if chrt_id in pools:
                continue

            gtin = f"046{chrt_id:010d}"[-14:]
            cis = f"01{gtin}21{'A' * 20}{chrt_id % 10000:04d}"
            existing_pool = await session.scalar(
                select(MarkingPool.id).where(
                    MarkingPool.tenant_id == tenant_id,
                    MarkingPool.seller_id == seller.seller_id,
                    MarkingPool.gtin == gtin,
                )
            )
            if existing_pool is not None:
                pools[chrt_id] = existing_pool
                continue

            pool = MarkingPool(
                tenant_id=tenant_id,
                seller_id=seller.seller_id,
                gtin=gtin,
                title=f"Emu pool {seller_key} chrt {chrt_id}",
            )
            session.add(pool)
            await session.flush()
            session.add(
                MarkingPoolProduct(
                    tenant_id=tenant_id,
                    pool_id=pool.id,
                    product_id=product_id,
                )
            )
            session.add(
                MarkingCode(
                    tenant_id=tenant_id,
                    seller_id=seller.seller_id,
                    pool_id=pool.id,
                    cis_code=cis,
                    gtin=gtin,
                    status=STATUS_AVAILABLE,
                )
            )
            pools[chrt_id] = pool.id
        await session.commit()
    return pools
