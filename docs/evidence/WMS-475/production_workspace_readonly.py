"""Bounded production GET audit: no IDs, sticker text, size text, or articles emitted."""
import asyncio
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from types import SimpleNamespace

import httpx
from fastapi import FastAPI
from sqlalchemy import event, text

from app.api import fbs_supplies
from app.api.deps import get_current_user
from app.db.session import SessionLocal, get_db

logging.disable(logging.CRITICAL)
DEPLOYED_AT = datetime(2026, 9, 21, 2, 21, 14, tzinfo=timezone.utc)


async def reject_external_http(_transport, _request):
    raise RuntimeError("external_http_forbidden")


# The sole HTTP client below uses ASGITransport. An unexpected WB/httpx request
# fails closed before reaching the network.
httpx.AsyncHTTPTransport.handle_async_request = reject_external_http


async def protect(session):
    await session.execute(text("SET TRANSACTION READ ONLY"))
    await session.execute(text("SET LOCAL statement_timeout = '15000ms'"))
    if await session.scalar(text("SHOW transaction_read_only")) != "on":
        raise RuntimeError("readonly_not_enabled")

    def no_flush(*_args):
        raise RuntimeError("unexpected_flush")

    event.listen(session.sync_session, "before_flush", no_flush)
    return no_flush


@asynccontextmanager
async def readonly_session():
    async with SessionLocal() as session:
        guard = await protect(session)
        try:
            yield session
        finally:
            event.remove(session.sync_session, "before_flush", guard)
            await session.rollback()


QUERY = """
WITH late_links AS (
  SELECT DISTINCT ON (e.tenant_id, e.document_id, e.payload_json->>'fbs_order_id')
         e.tenant_id, e.document_id AS supply_id,
         (e.payload_json->>'fbs_order_id')::uuid AS order_id, e.occurred_at
  FROM document_event e
  WHERE e.document_type = 'fbs_supply'
    AND e.event_type = 'line_added'
    AND e.source = 'user'
    AND e.actor_user_id IS NOT NULL
    AND e.payload_json ? 'fbs_order_id'
    AND EXISTS (
      SELECT 1 FROM document_event s
      WHERE s.tenant_id = e.tenant_id
        AND s.document_type = 'fbs_supply'
        AND s.document_id = e.document_id
        AND s.event_type = 'status_changed'
        AND s.payload_json->>'to' IN ('assembling', 'packed')
        AND s.occurred_at < e.occurred_at
    )
  ORDER BY e.tenant_id, e.document_id,
           e.payload_json->>'fbs_order_id', e.occurred_at DESC
)
SELECT l.tenant_id, l.supply_id, l.order_id, l.occurred_at,
       o.sticker_code, p.wb_size
FROM late_links l
JOIN fbs_supplies s ON s.id = l.supply_id AND s.tenant_id = l.tenant_id
JOIN fbs_orders o ON o.id = l.order_id AND o.supply_id = s.id
JOIN products p ON p.id = o.product_id
WHERE s.marketplace = 'wb' AND s.source = 'wms'
  AND nullif(trim(o.sticker_code), '') IS NOT NULL
  AND o.sticker_code ~ '[0-9]{4}$'
  AND nullif(trim(p.wb_size), '') IS NOT NULL
ORDER BY l.occurred_at DESC
LIMIT 1
"""

CENSUS_QUERY = """
WITH late_links AS (
  SELECT DISTINCT e.tenant_id, e.document_id AS supply_id,
         (e.payload_json->>'fbs_order_id')::uuid AS order_id
  FROM document_event e
  WHERE e.document_type = 'fbs_supply'
    AND e.event_type = 'line_added'
    AND e.source = 'user'
    AND e.actor_user_id IS NOT NULL
    AND e.payload_json ? 'fbs_order_id'
    AND EXISTS (
      SELECT 1 FROM document_event s
      WHERE s.tenant_id = e.tenant_id
        AND s.document_type = 'fbs_supply'
        AND s.document_id = e.document_id
        AND s.event_type = 'status_changed'
        AND s.payload_json->>'to' IN ('assembling', 'packed')
        AND s.occurred_at < e.occurred_at
    )
)
SELECT s.status, count(*) AS linked_rows
FROM late_links l
JOIN fbs_supplies s ON s.id = l.supply_id AND s.tenant_id = l.tenant_id
JOIN fbs_orders o ON o.id = l.order_id AND o.supply_id = s.id
WHERE s.marketplace = 'wb' AND s.source = 'wms'
GROUP BY s.status
ORDER BY s.status
"""


async def main():
    async with readonly_session() as session:
        census = (await session.execute(text(CENSUS_QUERY))).all()
        census_summary = {row.status: row.linked_rows for row in census}
        candidate = (await session.execute(text(QUERY))).first()
        if candidate is None:
            print(json.dumps({"verdict": "not-covered", "reason": "no_combined_late_order",
                              "late_link_census_by_current_status": census_summary}))
            return
        actor = (await session.execute(text("""
            SELECT id, tenant_id, role FROM users
            WHERE tenant_id = :tenant_id AND role = 'fulfillment_admin'
            ORDER BY id LIMIT 1
        """), {"tenant_id": candidate.tenant_id})).first()
        if actor is None:
            print(json.dumps({"verdict": "not-covered", "reason": "no_ff_admin_actor"}))
            return
        actor_user = SimpleNamespace(id=actor.id, tenant_id=actor.tenant_id, role=actor.role)

    app = FastAPI()
    app.include_router(fbs_supplies.router)

    async def db():
        async with readonly_session() as session:
            yield session

    async def authenticated_actor():
        return actor_user

    app.dependency_overrides[get_db] = db
    app.dependency_overrides[get_current_user] = authenticated_actor
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://local") as client:
        response = await client.get(f"/operations/fbs-supplies/{candidate.supply_id}/workspace")
    if response.status_code != 200:
        print(json.dumps({"verdict": "not-covered", "http_status": response.status_code,
                          "reason": "workspace_get_unavailable"}))
        return

    workspace = response.json()
    orders = workspace.get("orders") or []
    matching = [order for order in orders if order.get("id") == str(candidate.order_id)]
    if len(matching) != 1:
        print(json.dumps({"verdict": "fail", "reason": "late_order_missing_from_workspace"}))
        return
    order = matching[0]
    code = ((order.get("sticker") or {}).get("code") or "").strip()
    size = ((order.get("product") or {}).get("size") or "").strip()
    db_code = (candidate.sticker_code or "").strip()
    db_size = (candidate.wb_size or "").strip()
    tail = code.split(" ")[-1] if " " in code else code[-4:]
    checks = {
        "late_add_event_user_after_started": True,
        "workspace_http_200": True,
        "order_in_workspace_once": True,
        "sticker_matches_db": code == db_code,
        "sticker_tail_four_digits": len(tail) == 4 and tail.isdecimal(),
        "product_size_matches_db": bool(size) and size == db_size,
        "some_workspace_order_has_size": any(
            bool(((item.get("product") or {}).get("size") or "").strip()) for item in orders
        ),
    }
    print(json.dumps({
        "verdict": "pass" if all(checks.values()) else "fail",
        "deployment_checkout": "9f6f1521",
        "link_after_deployment": candidate.occurred_at >= DEPLOYED_AT,
        "late_link_census_by_current_status": census_summary,
        "supply_stage": workspace.get("stage"),
        "workspace_order_count": len(orders),
        "checks": checks,
        "boundary": "ASGI GET with existing FF admin identity substituted; no JWT, browser, WB, or printing",
    }, ensure_ascii=False))


try:
    asyncio.run(main())
except Exception as exc:
    print(json.dumps({"verdict": "error", "error_class": type(exc).__name__}))
    raise SystemExit(1)
