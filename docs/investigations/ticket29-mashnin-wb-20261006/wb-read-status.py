"""Bounded external READ using the installed WMS WB connection; no sync or writes."""
import asyncio
import json
import uuid
from datetime import datetime, timezone

import httpx
from sqlalchemy import text
from app.db.session import SessionLocal
from app.services.wb_marketplace_orders_service import _resolve_marketplace_api_token
from app.services.wildberries_client import fetch_marketplace_orders_status
from app.core.settings import settings

IDS = [5870616745,5870387255,5870016994,5869532011,5867428958,5867046519,
       5866659527,5866444207,5865695824,5865221274,5865221272,5865221271,
       5865095684,5865057392]

async def main():
    try:
        async with SessionLocal() as session:
            await session.execute(text('SET TRANSACTION READ ONLY'))
            token = await _resolve_marketplace_api_token(
                session, uuid.UUID('7b98a8aa-c03c-4649-9677-a645be45c622'),
                uuid.UUID('184f4b05-e623-4746-8edf-c5e408e6d026'))
            async with httpx.AsyncClient() as client:
                rows = await fetch_marketplace_orders_status(client, api_token=token, order_ids=IDS)
            print(json.dumps({'checked_at':datetime.now(timezone.utc).isoformat(),
                'endpoint':settings.wildberries_marketplace_api_base,
                'mock':settings.e2e_mock_wb_marketplace_orders,
                'orders':rows},ensure_ascii=False))
            await session.rollback()
    except Exception as exc:
        print(json.dumps({'error_type':type(exc).__name__, 'code':getattr(exc,'code',None),
            'status_code':getattr(exc,'status_code',None)},ensure_ascii=False))

asyncio.run(main())
