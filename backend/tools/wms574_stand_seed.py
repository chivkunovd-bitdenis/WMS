"""WMS-574: seed a local FBS stand with WB test data (idempotent).

Builds one fulfillment organisation with an admin account, two WB sellers,
one FF warehouse bound to three different WB warehouses, five products (three
requiring Честный знак/КИЗ with a 30+ code pool each, two without), storage
cells with real stock, and 30+ "new" WB FBS orders split across seller × WB
warehouse × B2C/B2B × cargo type so the group-supply screen has something to
group. It talks to a running wms574-api instance (see .claude/launch.json)
over HTTP for everything a normal operator/admin flow can do, and falls back
to direct ORM writes only where the E2E_MOCK_WB_* stubs return a single fixed
row (WB warehouse discovery, "new" WB orders) and a real sync would not give
us the variety the stand needs.

Safe to run more than once: every entity is looked up by its natural key
(slug, seller name, warehouse code, sku_code, wb_order_id, pool title) before
creating it, and existing rows are left alone.

Usage (server must already be running on port 18574, e.g. via preview_start
"wms574-api" from .claude/launch.json):

    backend/.venv/bin/python backend/tools/wms574_stand_seed.py \
        --database-url sqlite+aiosqlite:////path/to/wms574-stand.db \
        --api-base http://127.0.0.1:18574 \
        --readme /path/to/wms574-stand-README.md
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse

# --- Safety: this script may create/patch data and must only ever point at
# the local wms574 stand database, never anything that looks like a shared
# or production URL. -----------------------------------------------------

ADMIN_EMAIL = "wms574-admin@example.com"
PASSWORD = "Wms574-Stand-2026!"  # noqa: S105 - local-only dev stand, recorded in README, not here
ORG_NAME = "WMS-574 учебный фулфилмент"
ORG_SLUG = "wms574-stand"

SELLERS = [
    {"name": "ИП Соколов", "suffix": "01"},
    {"name": "ИП Волкова", "suffix": "02"},
]

WB_WAREHOUSES = [
    {"wb_warehouse_id": 574101, "name": "WB Коледино (WMS-574 стенд)"},
    {"wb_warehouse_id": 574102, "name": "WB Электросталь (WMS-574 стенд)"},
    {"wb_warehouse_id": 574103, "name": "WB Тула (WMS-574 стенд)"},
]

FF_WAREHOUSE_CODE = "wms574-ff"
FF_WAREHOUSE_NAME = "ФФ Стенд WMS-574"

# product_key -> (name, requires_honest_sign, gtin_for_pool)
PRODUCTS = [
    ("tshirt-m", "Футболка базовая M", True, "04600570001001"),
    ("tshirt-l", "Футболка базовая L", True, "04600570001002"),
    ("hoodie", "Худи оверсайз", True, "04600570001003"),
    ("sneakers", "Кроссовки беговые", False, None),
    ("socks", "Носки хлопковые 3 пары", False, None),
]

CODES_PER_POOL = 35


def local_url(value: str) -> str:
    host = urlparse(value).hostname
    if host not in {"localhost", "127.0.0.1"}:
        raise ValueError(f"refusing non-local API base: {value}")
    return value


def assert_local_sqlite(database_url: str) -> None:
    if "wms574" not in database_url:
        raise ValueError(
            "refusing to run: --database-url must point at a path containing "
            "'wms574' (the local stand db), got: " + database_url
        )
    if database_url.startswith(("postgresql://", "postgresql+psycopg://")):
        host = urlparse(database_url).hostname
        if host not in {"localhost", "127.0.0.1"}:
            raise ValueError("refusing non-local database host: " + database_url)


@dataclass
class SeedResult:
    tenant_id: str = ""
    admin_email: str = ADMIN_EMAIL
    sellers: dict[str, str] = field(default_factory=dict)
    warehouse_id: str = ""
    warehouse_code: str = FF_WAREHOUSE_CODE
    wb_warehouses: list[dict] = field(default_factory=list)
    locations: dict[str, dict] = field(default_factory=dict)
    products: dict[str, dict] = field(default_factory=dict)
    pools: dict[str, dict] = field(default_factory=dict)
    sample_kiz_codes: dict[str, list[str]] = field(default_factory=dict)
    order_groups: list[dict] = field(default_factory=list)
    orders_created: int = 0
    orders_total: int = 0
    regular_supply_order_ids: list[str] = field(default_factory=list)


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--api-base", default="http://127.0.0.1:18574")
    parser.add_argument("--readme", default=None, help="Optional: write a JSON summary here too")
    args = parser.parse_args()

    assert_local_sqlite(args.database_url)
    api_base = local_url(args.api_base)

    # Must be set before importing anything from `app.*` — Settings() reads
    # the environment once, at import time.
    os.environ["DATABASE_URL"] = args.database_url
    os.environ.setdefault("JWT_SECRET_KEY", "local-wms574-jwt-secret-key-minimum-32-characters")
    os.environ.setdefault("WMS_AUTO_CREATE_SCHEMA", "1")
    os.environ.setdefault("WMS_ALLOW_PUBLIC_REGISTRATION", "1")
    for flag in (
        "E2E_MOCK_WB_CARDS",
        "E2E_MOCK_WB_SUPPLIES",
        "E2E_MOCK_WB_WAREHOUSES",
        "E2E_MOCK_WB_MARKETPLACE_WAREHOUSES",
        "E2E_MOCK_WB_MARKETPLACE_ORDERS",
        "E2E_MOCK_WB_MARKETPLACE_SUPPLIES",
    ):
        os.environ.setdefault(flag, "1")

    from httpx import AsyncClient

    from app.core.roles import FULFILLMENT_ADMIN
    from app.db.session import SessionLocal
    from app.models.fbs_order import FbsOrder
    from app.models.fbs_warehouse_binding import FbsWarehouseBinding
    from app.models.marking_code import (
        STATUS_AVAILABLE,
        MarkingCode,
        MarkingPool,
        MarkingPoolProduct,
    )
    from app.models.product import Product
    from app.models.tenant_wb_mp_warehouse import TenantWbMpWarehouse
    from app.models.user import User
    from app.services import inventory_service
    from app.services import marking_code_service as mc_svc
    from app.services.wb_marketplace_orders_service import upsert_order_from_wb_row
    from sqlalchemy import select

    result = SeedResult()

    async with AsyncClient(base_url=api_base, timeout=60) as client:

        async def call(method: str, path: str, *, headers=None, json_body=None, params=None):
            resp = await client.request(
                method, path, headers=headers, json=json_body, params=params
            )
            if resp.status_code >= 400:
                raise RuntimeError(
                    f"{method} {path} -> HTTP {resp.status_code}: {resp.text[:500]}"
                )
            return resp.json() if resp.content else {}

        # --- 1. Organisation + admin -------------------------------------
        async with SessionLocal() as session:
            admin = await session.scalar(select(User).where(User.email == ADMIN_EMAIL))
        if admin is None:
            print(f"[org] registering {ORG_SLUG} / {ADMIN_EMAIL}")
            await call(
                "POST",
                "/auth/register",
                json_body={
                    "organization_name": ORG_NAME,
                    "slug": ORG_SLUG,
                    "admin_email": ADMIN_EMAIL,
                    "password": PASSWORD,
                },
            )
        else:
            print(f"[org] {ADMIN_EMAIL} already exists")
        login = await call(
            "POST", "/auth/login", json_body={"email": ADMIN_EMAIL, "password": PASSWORD}
        )
        headers = {"Authorization": f"Bearer {login['access_token']}"}
        me = await call("GET", "/auth/me", headers=headers)
        tenant_id = uuid.UUID(me["tenant_id"])
        result.tenant_id = str(tenant_id)
        assert me["role"] == FULFILLMENT_ADMIN, f"admin registered with role {me['role']!r}"

        # --- 2. Sellers ----------------------------------------------------
        existing_sellers = {s["name"]: s for s in await call("GET", "/sellers", headers=headers)}
        seller_ids: dict[str, uuid.UUID] = {}
        for spec in SELLERS:
            name = spec["name"]
            if name in existing_sellers:
                sid = uuid.UUID(existing_sellers[name]["id"])
                print(f"[seller] {name} already exists ({sid})")
            else:
                created = await call(
                    "POST", "/sellers", headers=headers, json_body={"name": name}
                )
                sid = uuid.UUID(created["id"])
                print(f"[seller] created {name} ({sid})")
            seller_ids[name] = sid
            result.sellers[name] = str(sid)
            # A dummy WB key per seller = "cabinet connected" on the E2E stubs.
            await call(
                "PATCH",
                f"/integrations/wildberries/sellers/{sid}/tokens",
                headers=headers,
                json_body={
                    "content_api_token": f"E2E-WB-CONTENT-{spec['suffix']}",
                    "supplies_api_token": f"E2E-WB-SUPPLIES-{spec['suffix']}",
                    "marketplace_api_token": f"E2E-WB-MARKETPLACE-{spec['suffix']}",
                },
            )

        # --- 3. FF warehouse + WB warehouse bindings -----------------------
        existing_wh = {w["code"]: w for w in await call("GET", "/warehouses", headers=headers)}
        if FF_WAREHOUSE_CODE in existing_wh:
            warehouse_id = uuid.UUID(existing_wh[FF_WAREHOUSE_CODE]["id"])
            print(f"[warehouse] {FF_WAREHOUSE_CODE} already exists ({warehouse_id})")
        else:
            created = await call(
                "POST",
                "/warehouses",
                headers=headers,
                json_body={"name": FF_WAREHOUSE_NAME, "code": FF_WAREHOUSE_CODE},
            )
            warehouse_id = uuid.UUID(created["id"])
            print(f"[warehouse] created {FF_WAREHOUSE_CODE} ({warehouse_id})")
        result.warehouse_id = str(warehouse_id)

        # The E2E_MOCK_WB_MARKETPLACE_WAREHOUSES stub always returns exactly
        # one fixed warehouse (id 501001), so the seller-warehouse discovery
        # API cannot give us three distinct WB warehouses. Bind them directly
        # via the same models the real sync path writes, for both sellers.
        async with SessionLocal() as session:
            for seller_name, sid in seller_ids.items():
                for wh in WB_WAREHOUSES:
                    wb_wh_id = wh["wb_warehouse_id"]
                    existing_name = await session.scalar(
                        select(TenantWbMpWarehouse).where(
                            TenantWbMpWarehouse.tenant_id == tenant_id,
                            TenantWbMpWarehouse.wb_warehouse_id == wb_wh_id,
                        )
                    )
                    if existing_name is None:
                        session.add(
                            TenantWbMpWarehouse(
                                tenant_id=tenant_id,
                                wb_warehouse_id=wb_wh_id,
                                name=wh["name"],
                                is_active=True,
                            )
                        )
                    existing_binding = await session.scalar(
                        select(FbsWarehouseBinding).where(
                            FbsWarehouseBinding.tenant_id == tenant_id,
                            FbsWarehouseBinding.seller_id == sid,
                            FbsWarehouseBinding.marketplace == "wb",
                            FbsWarehouseBinding.wb_warehouse_id == wb_wh_id,
                        )
                    )
                    if existing_binding is None:
                        session.add(
                            FbsWarehouseBinding(
                                tenant_id=tenant_id,
                                seller_id=sid,
                                marketplace="wb",
                                wb_warehouse_id=wb_wh_id,
                                wms_warehouse_id=warehouse_id,
                                is_active=True,
                                served=True,
                                stock_sync_enabled=True,
                            )
                        )
                        print(f"[binding] {seller_name} <- WB {wb_wh_id} -> {FF_WAREHOUSE_CODE}")
            await session.commit()
        result.wb_warehouses = WB_WAREHOUSES

        # --- 4. Storage cells (А-01-NN) -------------------------------------
        existing_locations = {
            loc["code"]: loc
            for loc in await call(
                "GET", f"/warehouses/{warehouse_id}/locations", headers=headers
            )
        }
        cell_codes = [f"А-01-{i:02d}" for i in range(1, 1 + len(SELLERS) * len(PRODUCTS))]
        for code in cell_codes:
            if code in existing_locations:
                loc = existing_locations[code]
            else:
                loc = await call(
                    "POST",
                    f"/warehouses/{warehouse_id}/locations",
                    headers=headers,
                    json_body={"code": code},
                )
                print(f"[cell] created {code}")
            result.locations[code] = {"id": loc["id"], "barcode": loc["barcode"]}
        cell_iter = iter(cell_codes)

        # --- 5. Products + FBS publication + stock --------------------------
        existing_products = await call("GET", "/products", headers=headers)
        by_sku = {p["sku_code"]: p for p in existing_products}

        for seller_name, sid in seller_ids.items():
            suffix = next(s["suffix"] for s in SELLERS if s["name"] == seller_name)
            for key, name, requires_kiz, gtin in PRODUCTS:
                sku = f"WMS574-{suffix}-{key}"
                full_name = f"{name} ({seller_name})"
                if sku in by_sku:
                    prod = by_sku[sku]
                    print(f"[product] {sku} already exists")
                else:
                    barcode = f"2574{suffix}{PRODUCTS.index((key, name, requires_kiz, gtin)):03d}"
                    prod = await call(
                        "POST",
                        "/products",
                        headers=headers,
                        json_body={
                            "name": full_name,
                            "sku_code": sku,
                            "seller_id": str(sid),
                            "wb_barcode": barcode,
                            "wb_vendor_code": sku,
                            "length_mm": 200,
                            "width_mm": 150,
                            "height_mm": 50,
                            "weight_g": 300,
                            "requires_honest_sign": requires_kiz,
                        },
                    )
                    print(f"[product] created {sku} ({prod['id']})")
                pid = uuid.UUID(prod["id"])

                # Publish 100% of free stock to FBS on every bound warehouse.
                await call(
                    "PATCH",
                    f"/products/{pid}/fbs-stock-sync",
                    headers=headers,
                    json_body={"fbs_stock_sync_enabled": True},
                )
                await call(
                    "PUT",
                    f"/products/{pid}/fbs-rule",
                    headers=headers,
                    json_body={"publish": True, "same_everywhere": True, "percent": 100},
                )

                cell_code = next(cell_iter)
                cell_id = uuid.UUID(result.locations[cell_code]["id"])
                async with SessionLocal() as session:
                    from app.models.inventory_balance import InventoryBalance

                    balance = await session.scalar(
                        select(InventoryBalance).where(
                            InventoryBalance.tenant_id == tenant_id,
                            InventoryBalance.product_id == pid,
                            InventoryBalance.storage_location_id == cell_id,
                        )
                    )
                    have_stock = balance is not None and balance.quantity > 0
                    admin_row = await session.scalar(
                        select(User).where(User.email == ADMIN_EMAIL)
                    )
                    if not have_stock:
                        await inventory_service.record_movement_and_adjust_balance(
                            session,
                            tenant_id=tenant_id,
                            product_id=pid,
                            storage_location_id=cell_id,
                            quantity_delta=80,
                            movement_type="inbound_intake",
                            actor_user_id=admin_row.id,
                        )
                        await session.commit()
                        print(f"[stock] +80 {sku} @ {cell_code}")

                result.products[sku] = {
                    "id": str(pid),
                    "seller": seller_name,
                    "name": full_name,
                    "wb_barcode": prod.get("wb_barcode") or barcode,
                    "cell": cell_code,
                    "requires_honest_sign": requires_kiz,
                }

                # --- KIZ pool ------------------------------------------------
                if requires_kiz:
                    pool_title = f"{sku} пул ЧЗ"
                    async with SessionLocal() as session:
                        pool = await session.scalar(
                            select(MarkingPool).where(
                                MarkingPool.tenant_id == tenant_id,
                                MarkingPool.seller_id == sid,
                                MarkingPool.title == pool_title,
                            )
                        )
                    if pool is None:
                        created_pool = await call(
                            "POST",
                            "/operations/marking-codes/_e2e/pools",
                            headers=headers,
                            json_body={"seller_id": str(sid), "gtin": gtin, "title": pool_title},
                        )
                        pool_id = uuid.UUID(created_pool["pool_id"])
                        await call(
                            "PUT",
                            f"/operations/marking-codes/pools/{pool_id}/products",
                            headers=headers,
                            json_body={"product_ids": [str(pid)]},
                        )
                        print(f"[kiz-pool] created {pool_title} ({pool_id})")
                    else:
                        pool_id = pool.id
                        print(f"[kiz-pool] {pool_title} already exists")

                    async with SessionLocal() as session:
                        existing_count = await session.scalar(
                            select(MarkingCode.id).where(
                                MarkingCode.pool_id == pool_id
                            ).limit(1)
                        )
                        codes_now = (
                            await session.execute(
                                select(MarkingCode).where(MarkingCode.pool_id == pool_id)
                            )
                        ).scalars().all()
                        if len(codes_now) < CODES_PER_POOL:
                            need = CODES_PER_POOL - len(codes_now)
                            for i in range(need):
                                serial = f"{sku}{len(codes_now) + i:04d}".upper().replace("-", "")
                                cis = f"01{gtin}21{serial}"
                                session.add(
                                    MarkingCode(
                                        tenant_id=tenant_id,
                                        seller_id=sid,
                                        pool_id=pool_id,
                                        product_id=pid,
                                        cis_code=cis,
                                        source="pool",
                                        gtin=gtin,
                                        status=STATUS_AVAILABLE,
                                    )
                                )
                            await session.commit()
                            print(f"[kiz-codes] +{need} for {pool_title}")
                        all_codes = (
                            await session.execute(
                                select(MarkingCode.cis_code)
                                .where(MarkingCode.pool_id == pool_id)
                                .order_by(MarkingCode.cis_code)
                                .limit(3)
                            )
                        ).scalars().all()
                    result.pools[sku] = {"pool_id": str(pool_id), "gtin": gtin, "title": pool_title}
                    result.sample_kiz_codes[sku] = list(all_codes)

        # --- 6. Orders -------------------------------------------------------
        # E2E_MOCK_WB_MARKETPLACE_ORDERS returns one fixed canned "new" order,
        # so GET /operations/fbs-orders/sync cannot give us 30+ varied ones.
        # Build synthetic WB row dicts and go through the exact same upsert
        # the real sync path uses, so status/mapping/reservation all come out
        # the way a genuine sync would leave them.
        async with SessionLocal() as session:
            existing_wb_ids = {
                row[0]
                for row in (
                    await session.execute(
                        select(FbsOrder.wb_order_id).where(FbsOrder.tenant_id == tenant_id)
                    )
                ).all()
            }

        product_by_sku = result.products
        skus_by_seller: dict[str, list[str]] = {}
        for sku, info in product_by_sku.items():
            skus_by_seller.setdefault(info["seller"], []).append(sku)

        # (seller_name, wb_warehouse_id, is_legal, cargo_type_int, count)
        group_specs = [
            ("ИП Соколов", 574101, False, 1, 6),  # also feeds the regular-supply test
            ("ИП Соколов", 574102, False, 1, 5),
            ("ИП Соколов", 574101, True, 1, 5),
            ("ИП Волкова", 574101, False, 1, 5),
            ("ИП Волкова", 574103, False, 2, 5),
            ("ИП Волкова", 574103, False, 1, 5),
        ]

        base_wb_order_id = 5740000
        order_counter = 0
        created_orders: list[dict] = []
        async with SessionLocal() as session:
            for gi, (seller_name, wb_wh_id, is_legal, cargo_int, count) in enumerate(group_specs):
                sid = seller_ids[seller_name]
                skus = skus_by_seller[seller_name]
                group_order_ids: list[str] = []
                for i in range(count):
                    order_counter += 1
                    wb_order_id = base_wb_order_id + gi * 100 + i
                    sku = skus[order_counter % len(skus)]
                    info = product_by_sku[sku]
                    already = wb_order_id in existing_wb_ids
                    row: dict = {
                        "id": wb_order_id,
                        "rid": f"wms574-rid-{wb_order_id}",
                        "createdAt": datetime.now(tz=UTC).isoformat(),
                        "nmId": None,
                        "chrtId": None,
                        "article": sku,
                        "skus": [info["wb_barcode"]],
                        "price": 199000,
                        "isLegal": is_legal,
                        "cargoType": cargo_int,
                        "officeId": wb_wh_id + 30000,
                        "warehouseId": wb_wh_id,
                        "isPickupPointShipmentAllowed": True,
                    }
                    if info["requires_honest_sign"]:
                        row["requiredMeta"] = ["sgtin"]
                        row["optionalMeta"] = []
                    else:
                        row["requiredMeta"] = []
                        row["optionalMeta"] = []
                    order, created = await upsert_order_from_wb_row(
                        session, tenant_id, sid, row
                    )
                    await session.commit()
                    if created:
                        result.orders_created += 1
                    group_order_ids.append(str(order.id))
                    created_orders.append(
                        {
                            "id": str(order.id),
                            "wb_order_id": wb_order_id,
                            "seller": seller_name,
                            "wb_warehouse_id": wb_wh_id,
                            "sku": sku,
                            "is_legal": is_legal,
                            "cargo_type": order.cargo_type,
                            "status": order.status,
                            "reserve_status": order.reserve_status,
                            "mapping_status": order.mapping_status,
                        }
                    )
                result.order_groups.append(
                    {
                        "seller": seller_name,
                        "wb_warehouse_id": wb_wh_id,
                        "is_legal": is_legal,
                        "cargo_type_int": cargo_int,
                        "count": count,
                        "order_ids": group_order_ids,
                    }
                )
        result.orders_total = order_counter
        # First 3 of the first (homogeneous) group are reserved for the
        # scripted single-supply walk-through; the rest of "Новые" is left
        # untouched for manual testing.
        result.regular_supply_order_ids = result.order_groups[0]["order_ids"][:3]

    print("\n=== SEED SUMMARY ===")
    print(json.dumps(result.__dict__, ensure_ascii=False, indent=2))

    if args.readme:
        with open(args.readme + ".seed-summary.json", "w", encoding="utf-8") as fh:
            json.dump(result.__dict__, fh, ensure_ascii=False, indent=2)
        print(f"\n[summary written] {args.readme}.seed-summary.json")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:  # noqa: BLE001
        print(f"FATAL: {exc}", file=sys.stderr)
        raise
