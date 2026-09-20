"""Capture read-only API responses for AVpack UI replay, never issue access tokens."""
import asyncio
import json

import httpx
from fastapi import FastAPI
from sqlalchemy import select, text

from app.api import auth, inbound_intake, inventory_balances, marketplace_unload_requests, notifications, products, subscription, warehouses
from app.api.deps import get_current_user
from app.db.session import SessionLocal, get_db
from app.models.tenant import Tenant
from app.models.user import User


async def readonly_db():
    async with SessionLocal() as session:
        await session.execute(text("SET TRANSACTION READ ONLY"))
        try:
            yield session
        finally:
            await session.rollback()


async def main():
    app = FastAPI()
    for module in (auth, inbound_intake, inventory_balances, marketplace_unload_requests, notifications, products, subscription, warehouses):
        app.include_router(module.router)
    app.dependency_overrides[get_db] = readonly_db
    result = []
    async with SessionLocal() as session:
        await session.execute(text("SET TRANSACTION READ ONLY"))
        users = (await session.execute(select(User).join(Tenant, Tenant.id == User.tenant_id).where(Tenant.name == "AVpack", User.role == "fulfillment_seller"))).scalars().all()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://audit") as client:
            for user in users:
                async def actor():
                    return user
                app.dependency_overrides[get_current_user] = actor
                snapshot = {"user_id":str(user.id),"responses":{}}
                for path in ["/auth/me", "/subscription", "/products/wb-catalog", "/operations/inventory-balances/summary", "/warehouses", "/operations/inbound-intake-requests", "/operations/marketplace-unload-requests", "/operations/notifications"]:
                    response = await client.get(path)
                    snapshot["responses"][path] = {"status":response.status_code,"body":response.json()}
                result.append(snapshot)
        await session.rollback()
    print(json.dumps(result,ensure_ascii=False))


asyncio.run(main())
