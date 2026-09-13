"""Add WMS445-only synthetic operators, rates, stock and marketplace orders.

No schema reset, no task marked done/delivered, no existing fixture overwritten.
Run only after the coordinator has connected both local marketplace emulators.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from httpx import AsyncClient

PASSWORD = "Wms445-demo-only"
ADMIN_EMAIL = "wms445-admin@example.com"
STAFF_EMAIL = "wms445-staff@example.com"


def local_url(value: str) -> str:
    if urlparse(value).hostname not in {"localhost", "127.0.0.1"}:
        raise ValueError("WMS445 fixture accepts loopback services only")
    return value


async def seed(args: argparse.Namespace) -> dict[str, Any]:
    # Validate the destination before loading application settings or models.
    db = urlparse(args.database_url)
    if db.hostname not in {"localhost", "127.0.0.1"} or db.path not in {
        "/wms445_tests",
        "/wms445_fixture",
        "/wms_tsd_20260913",
    }:
        raise ValueError("Use only a named local WMS445/package database")
    os.environ["DATABASE_URL"] = args.database_url
    for setting in (
        "WILDBERRIES_MARKETPLACE_API_BASE",
        "WILDBERRIES_SUPPLIES_API_BASE",
        "WILDBERRIES_CONTENT_API_BASE",
    ):
        os.environ[setting] = local_url(args.wb_base)
    os.environ["WMS_OZON_SELLER_API_BASE"] = local_url(args.ozon_base)
    os.environ["WMS_OZON_LIVE_API"] = "true"
    from tools.wms445_local_http import install_http_guard

    install_http_guard()
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session
    from wb_emulator.services.orders_store import (  # type: ignore[import-not-found]
        get_order,
        upsert_order,
    )

    from app.core.roles import FULFILLMENT_SELLER
    from app.db.session import SessionLocal
    from app.models.fbs_order import FbsOrder
    from app.models.fbs_supply import FbsSupply
    from app.models.fbs_warehouse_binding import FbsWarehouseBinding
    from app.models.inventory_movement import InventoryMovement
    from app.models.product import Product
    from app.models.product_marketplace_link import ProductMarketplaceLink
    from app.models.seller import Seller
    from app.models.storage_location import StorageLocation
    from app.models.user import User
    from app.models.warehouse import Warehouse
    from app.services import inventory_service
    from app.services.marketplace_account_service import MarketplaceAccountService
    from app.services.marketplace_provider import OzonMarketplaceProvider
    from app.services.ozon_fbs_sync_service import sync_ozon_orders
    from app.services.ozon_marketplace_transport import HttpxOzonMarketplaceTransport
    from app.services.passwords import hash_password
    from app.services.wb_marketplace_orders_service import upsert_order_from_wb_row
    from app.services.wildberries_credentials_service import SKIP, patch_seller_tokens

    async with AsyncClient(base_url=local_url(args.api_base), timeout=60) as client:

        async def request(
            method: str, path: str, *, headers: dict[str, str] | None = None, body: Any = None
        ) -> Any:
            response = await client.request(method, path, headers=headers, json=body)
            if response.status_code >= 400:
                # Do not print request/response bodies containing auth material.
                raise RuntimeError(f"Fixture {method} {path}: HTTP {response.status_code}")
            return response.json() if response.content else {}

        async with SessionLocal() as session:
            admin = await session.scalar(select(User).where(User.email == ADMIN_EMAIL))
        if admin is None:
            await request(
                "POST",
                "/auth/register",
                body={
                    "organization_name": "WMS445 учебный фулфилмент",
                    "slug": "wms445-fixture",
                    "admin_email": ADMIN_EMAIL,
                    "password": PASSWORD,
                },
            )
        login = await request(
            "POST", "/auth/login", body={"email": ADMIN_EMAIL, "password": PASSWORD}
        )
        headers = {"Authorization": f"Bearer {login['access_token']}"}
        me = await request("GET", "/auth/me", headers=headers)
        tenant_id = uuid.UUID(me["tenant_id"])
        admin_id = uuid.UUID(me["id"])
        async with SessionLocal() as session:
            admin_db = await session.get(User, admin_id)
            if admin_db is None or admin_db.tenant_id != tenant_id:
                raise ValueError("API and fixture database are different")
            staff = await session.scalar(select(User).where(User.email == STAFF_EMAIL))
        if staff is None:
            staff_data = await request(
                "POST",
                "/auth/staff-accounts",
                headers=headers,
                body={"email": STAFF_EMAIL, "password": PASSWORD},
            )
            staff_id = staff_data["id"]
            await request(
                "PATCH",
                f"/auth/staff-accounts/{staff_id}/permissions",
                headers=headers,
                body={
                    "mp_shipments": True,
                    "reception": True,
                    "cells": True,
                    "inventory": True,
                    "packaging": True,
                },
            )
            await request(
                "PATCH",
                f"/auth/staff-accounts/{staff_id}/packaging-rate",
                headers=headers,
                body={"rate_rub": "7.00"},
            )
        else:
            staff_id = str(staff.id)
        async with SessionLocal() as session:
            warehouse = await session.scalar(
                select(Warehouse).where(
                    Warehouse.tenant_id == tenant_id, Warehouse.code == "wms445"
                )
            )
        if warehouse is None:
            wh = await request(
                "POST",
                "/warehouses",
                headers=headers,
                body={"name": "WMS445 учебный склад", "code": "WMS445"},
            )
            warehouse_id = uuid.UUID(wh["id"])
        else:
            warehouse_id = warehouse.id
        sources = []
        for code in ("WMS445-A", "WMS445-B"):
            async with SessionLocal() as session:
                location = await session.scalar(
                    select(StorageLocation).where(
                        StorageLocation.tenant_id == tenant_id, StorageLocation.code == code
                    )
                )
            if location is None:
                value = await request(
                    "POST",
                    f"/warehouses/{warehouse_id}/locations",
                    headers=headers,
                    body={"code": code},
                )
                sources.append(uuid.UUID(value["id"]))
            else:
                sources.append(location.id)
        sellers: dict[str, uuid.UUID] = {}
        for key in ("a", "b", "c"):
            name = f"WMS445 Селлер {key.upper()}" + (" без тарифа" if key == "c" else "")
            async with SessionLocal() as session:
                seller = await session.scalar(
                    select(Seller).where(Seller.tenant_id == tenant_id, Seller.name == name)
                )
            if seller is None:
                data = await request("POST", "/sellers", headers=headers, body={"name": name})
                sellers[key] = uuid.UUID(data["id"])
            else:
                sellers[key] = seller.id
        matrix = await request("GET", "/billing/tariff-matrix", headers=headers)
        rates = {
            "inbound": 1000,
            "return": 1200,
            "marketplace_outbound": 2000,
            "packing": 3000,
            "fbs_order": 4000,
        }
        if not matrix["versions"]:
            await request(
                "PUT",
                "/billing/tariff-matrix",
                headers=headers,
                body={
                    "revision": matrix["revision"],
                    "services": [
                        {"service_code": code, "enabled": code != "storage"}
                        for code in [*rates, "storage"]
                    ],
                    "versions": [
                        {
                            "seller_id": str(sellers[key]),
                            "service_code": code,
                            "unit": "item",
                            "enabled": True,
                            "rate": rate,
                            "valid_from_at": "2026-09-01T00:00:00Z",
                        }
                        for key in ("a", "b")
                        for code, rate in rates.items()
                    ],
                },
            )
        products: dict[str, list[uuid.UUID]] = {}
        for key in ("a", "b"):
            seller_id = sellers[key]
            async with SessionLocal() as session:
                await patch_seller_tokens(
                    session,
                    tenant_id,
                    seller_id,
                    content_api_token=SKIP,
                    marketplace_api_token=f"token-{key}",
                    supplies_api_token=f"token-{key}",
                )
                await MarketplaceAccountService(session).save_validated_candidate(
                    tenant_id, seller_id, admin_id, f"445{key}", "wms445-synthetic"
                )
            async with SessionLocal() as session:
                seller_email = f"wms445-seller-{key}@example.com"
                seller_user = await session.scalar(select(User).where(User.email == seller_email))
                if seller_user is None:
                    session.add(
                        User(
                            tenant_id=tenant_id,
                            seller_id=seller_id,
                            email=seller_email,
                            password_hash=hash_password(PASSWORD),
                            role=FULFILLMENT_SELLER,
                        )
                    )
                    await session.commit()
            products[key] = []
            for index in (0, 1):
                sku = 445100 + (100 if key == "b" else 0) + index
                async with SessionLocal() as session:
                    product = await session.scalar(
                        select(Product).where(
                            Product.tenant_id == tenant_id, Product.sku_code == str(sku)
                        )
                    )
                    if product is None:
                        product = Product(
                            tenant_id=tenant_id,
                            seller_id=seller_id,
                            name=f"WMS445 {key.upper()} учебный товар {index + 1} длинное название",
                            sku_code=str(sku),
                            wb_barcode=f"2000000{sku}",
                            wb_nm_id=sku,
                            wb_chrt_id=sku,
                            fbs_stock_sync_enabled=True,
                            fbs_ozon_stock_sync_enabled=True,
                            fbs_stock_limit=100,
                            fbs_percent=100,
                        )
                        session.add(product)
                        await session.flush()
                        session.add(
                            ProductMarketplaceLink(
                                tenant_id=tenant_id,
                                seller_id=seller_id,
                                product_id=product.id,
                                marketplace="ozon",
                                external_sku=str(sku),
                                external_offer_id=str(sku),
                                external_barcodes=[f"OZN{sku}"],
                            )
                        )
                        for location_id in sources:
                            await inventory_service.record_movement_and_adjust_balance(
                                session,
                                tenant_id=tenant_id,
                                product_id=product.id,
                                storage_location_id=location_id,
                                quantity_delta=20,
                                movement_type="inbound_intake",
                                actor_user_id=admin_id,
                            )
                        await session.commit()
                    products[key].append(product.id)
            async with SessionLocal() as session:
                for marketplace, external_wh in (("wb", 501001), ("ozon", 1020005029603630)):
                    exists = await session.scalar(
                        select(FbsWarehouseBinding).where(
                            FbsWarehouseBinding.tenant_id == tenant_id,
                            FbsWarehouseBinding.seller_id == seller_id,
                            FbsWarehouseBinding.marketplace == marketplace,
                            FbsWarehouseBinding.wb_warehouse_id == external_wh,
                        )
                    )
                    if exists is not None and exists.external_warehouse_id is None:
                        exists.external_warehouse_id = str(external_wh)
                    if exists is None:
                        session.add(
                            FbsWarehouseBinding(
                                tenant_id=tenant_id,
                                seller_id=seller_id,
                                marketplace=marketplace,
                                wb_warehouse_id=external_wh,
                                external_warehouse_id=str(external_wh),
                                wms_warehouse_id=warehouse_id,
                                served=True,
                                is_active=True,
                                stock_sync_enabled=False,
                            )
                        )
                await session.commit()
        # Add only deterministic 445xxxxxx WB orders. Existing rows retain lifecycle state.
        wb_engine = create_engine(f"sqlite:///{Path(args.wb_db).resolve()}")
        now = datetime.now(UTC)
        wb_ids: dict[str, list[str]] = {"a": [], "b": []}
        for key in ("a", "b"):
            for index in range(6):
                sku = 445100 + (100 if key == "b" else 0)
                external_id = 445000000 + (100 if key == "b" else 0) + index
                payload = {
                    "id": external_id,
                    "rid": f"wms445-{external_id}",
                    "createdAt": (now - timedelta(hours=3 + index)).isoformat(),
                    "nmId": sku,
                    "chrtId": sku,
                    "article": str(sku),
                    "skus": [f"2000000{sku}"],
                    "price": 120000,
                    "cargoType": 1,
                    "warehouseId": 501001,
                    "officeId": 601001,
                    "canPvz": index >= 3,
                }
                with Session(wb_engine) as wb_session:
                    if get_order(wb_session, f"seller_{key}", external_id) is None:
                        upsert_order(wb_session, f"seller_{key}", payload)
                async with SessionLocal() as session:
                    order = await session.scalar(
                        select(FbsOrder).where(
                            FbsOrder.tenant_id == tenant_id,
                            FbsOrder.marketplace == "wb",
                            FbsOrder.wb_order_id == external_id,
                        )
                    )
                    if order is None:
                        order, _ = await upsert_order_from_wb_row(
                            session, tenant_id, sellers[key], payload
                        )
                        await session.commit()
                    wb_ids[key].append(str(order.id))
        wb_engine.dispose()
        ozon_rows = []
        for key in ("a", "b"):
            for index in range(3):
                first_sku = 445100 + (100 if key == "b" else 0)
                ozon_rows.append(
                    {
                        "posting_number": f"445-{key}-{index}",
                        "fixture_client": f"445{key}",
                        "order_id": 445000 + index,
                        "order_number": f"445-{key}-{index}",
                        "status": "awaiting_packaging",
                        "substatus": "posting_created",
                        "in_process_at": (now - timedelta(days=2 - index)).isoformat(),
                        "shipment_date": (now + timedelta(hours=2 + 12 * index)).isoformat(),
                        "delivering_date": None,
                        "analytics_data": None,
                        "financial_data": None,
                        "delivery_method": {
                            "id": 44501,
                            "name": "WMS445 пункт Ozon Садовая",
                            "warehouse_id": 1020005029603630,
                            "tpl_provider_id": 0,
                        },
                        "products": [
                            {
                                "sku": first_sku + pos,
                                "offer_id": str(first_sku + pos),
                                "name": f"WMS445 {key} product {pos + 1}",
                                "quantity": qty,
                                "price": "1200.00",
                                "currency_code": "RUB",
                            }
                            for pos, qty in [(0, 2), (1, 1)]
                        ],
                        "requirements": {},
                        "related_postings": None,
                    }
                )
        async with AsyncClient(base_url=local_url(args.ozon_base), timeout=30) as ozon:
            seeded_response = await ozon.post("/__admin/seed", json={"postings": ozon_rows})
            seeded_response.raise_for_status()
        for key in ("a", "b"):
            async with SessionLocal() as session:
                await sync_ozon_orders(
                    session,
                    tenant_id,
                    sellers[key],
                    OzonMarketplaceProvider(
                        transport=HttpxOzonMarketplaceTransport(base_url=local_url(args.ozon_base))
                    ),
                    client,
                    selected_posting_numbers=frozenset(f"445-{key}-{i}" for i in range(3)),
                )
                await session.commit()
        # One WB document genuinely created at the marketplace and started via WMS.
        async with SessionLocal() as session:
            begun = await session.scalar(
                select(FbsSupply).where(
                    FbsSupply.tenant_id == tenant_id, FbsSupply.name == "WMS445 WB в работе"
                )
            )
        if begun is None:
            workspace = await request(
                "POST",
                "/operations/fbs-supplies/from-orders",
                headers=headers,
                body={
                    "name": "WMS445 WB в работе",
                    "order_ids": wb_ids["a"][:2],
                    "planned_delivery_type": "warehouse_sc",
                    "idempotency_key": "wms445-seed-wb-active",
                },
            )
            active_id = workspace["supply"]["id"]
            await request(
                "POST", f"/operations/fbs-supplies/{active_id}/start-work", headers=headers
            )
        else:
            active_id = str(begun.id)
        async with SessionLocal() as session:
            orders = list(
                (
                    await session.scalars(select(FbsOrder).where(FbsOrder.tenant_id == tenant_id))
                ).all()
            )
            movements = list(
                (
                    await session.scalars(
                        select(InventoryMovement.id).where(InventoryMovement.tenant_id == tenant_id)
                    )
                ).all()
            )
        result = {
            "tenant_id": str(tenant_id),
            "warehouse_id": str(warehouse_id),
            "seller_ids": {key: str(value) for key, value in sellers.items()},
            "source_ids": [str(value) for value in sources],
            "source_codes": ["WMS445-A", "WMS445-B"],
            "staff_id": staff_id,
            "active_wb_supply_id": active_id,
            "orders": [
                {
                    "id": str(o.id),
                    "marketplace": o.marketplace,
                    "status": o.status,
                    "external_id": o.external_order_id or str(o.wb_order_id),
                }
                for o in orders
            ],
            "inbound_movement_ids": [str(value) for value in movements],
            "admin_email": ADMIN_EMAIL,
            "staff_email": STAFF_EMAIL,
            "state_note": "No delivery is pre-set; complete it through the operator scenario.",
        }
        Path(args.manifest).write_text(json.dumps(result, ensure_ascii=False, indent=2))
        return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--wb-db", required=True)
    parser.add_argument("--wb-base", default="http://127.0.0.1:19092")
    parser.add_argument("--api-base", default="http://127.0.0.1:18082")
    parser.add_argument("--ozon-base", default="http://127.0.0.1:19093")
    parser.add_argument("--manifest", required=True)
    output = asyncio.run(seed(parser.parse_args()))
    print(
        json.dumps(
            {
                "tenant_id": output["tenant_id"],
                "orders": len(output["orders"]),
                "active_wb_supply_id": output["active_wb_supply_id"],
            }
        )
    )
