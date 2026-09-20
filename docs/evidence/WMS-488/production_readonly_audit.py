"""Run inside deployed API container: SELECT-only routes, no login/token issuance.

Authentication is replaced in this isolated process with each existing DB user;
real authorization dependencies and queries remain. This is not a browser/login test.
"""
import asyncio
import json
from collections import Counter

import httpx
from fastapi import FastAPI
from sqlalchemy import select, text

from app.api import inventory_balances, products, reports, scan_resolver
from app.api.deps import get_current_user
from app.db.session import SessionLocal, get_db
from app.models.product import Product
from app.models.tenant import Tenant
from app.models.user import User


async def readonly_db():
    async with SessionLocal() as session:
        await session.execute(text("SET TRANSACTION READ ONLY"))
        try:
            yield session
        finally:
            await session.rollback()


def ids_from(value):
    if isinstance(value, list):
        return set().union(*(ids_from(row) for row in value)) if value else set()
    if isinstance(value, dict):
        result = {str(value[k]) for k in ("id", "product_id") if value.get(k)}
        for item in value.values():
            if isinstance(item, (dict, list)):
                result.update(ids_from(item))
        return result
    return set()


async def main():
    app = FastAPI()
    for module in (products, inventory_balances, reports, scan_resolver):
        app.include_router(module.router)
    app.dependency_overrides[get_db] = readonly_db
    async with SessionLocal() as session:
        await session.execute(text("SET TRANSACTION READ ONLY"))
        users = (await session.execute(select(User, Tenant.name).join(Tenant, Tenant.id == User.tenant_id).where(User.role.in_(["fulfillment_seller", "fulfillment_admin"])))).all()
        product_rows = (await session.execute(select(Product.id, Product.seller_id, Product.tenant_id, Product.sku_code))).all()
        ownership = {str(p.id): (p.seller_id, p.tenant_id) for p in product_rows}
        avpack = next(u.tenant_id for u, tenant in users if tenant == "AVpack")
        owners = Counter(p.seller_id for p in product_rows if p.tenant_id == avpack)
        victim_owner = owners.most_common(1)[0][0]
        victim = next(p for p in product_rows if p.tenant_id == avpack and p.seller_id == victim_owner)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://audit") as client:
            for user, tenant in users:
                async def actor():
                    return user
                app.dependency_overrides[get_current_user] = actor
                paths = ["/products", "/products/wb-catalog", "/products/linked-wb-catalog", "/products/ff-catalog", "/products/ff-catalog-page", "/operations/inventory-balances/summary"]
                if tenant != "AVpack":
                    paths = [path + "?search=" + victim.sku_code for path in paths[:5]]
                    paths.append(f"/operations/scan/resolve?code={victim.sku_code}")
                if tenant == "AVpack":
                    paths += [f"/products/{victim.id}/dimensions/history", f"/products/{victim.id}/fbs-rule", f"/products/{victim.id}/stock-directions", f"/products?search={victim.sku_code}", f"/products/wb-catalog?search={victim.sku_code}", f"/operations/scan/resolve?code={victim.sku_code}", f"/reports/inventory?date_from=2026-09-01T00:00:00Z&date_to=2026-09-21T23:59:59Z&seller_id={victim.seller_id}"]
                checks = []
                for path in paths:
                    try:
                        response = await client.get(path)
                    except Exception as exc:
                        checks.append({"path": path, "error_type": type(exc).__name__})
                        continue
                    data = response.json()
                    returned = ids_from(data) & ownership.keys()
                    foreign_seller = [pid for pid in returned if user.role == "fulfillment_seller" and ownership[pid][0] != user.seller_id]
                    foreign_tenant = [pid for pid in returned if ownership[pid][1] != user.tenant_id]
                    checks.append({"path":path,"status":response.status_code,"products":len(returned),"foreign_seller":foreign_seller,"foreign_tenant":foreign_tenant})
                print(json.dumps({"tenant":tenant,"user_id":str(user.id),"role":user.role,"home_seller":str(user.seller_id),"checks":checks}, ensure_ascii=False), flush=True)
        await session.rollback()


asyncio.run(main())
