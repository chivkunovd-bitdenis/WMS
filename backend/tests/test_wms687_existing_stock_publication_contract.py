"""WMS-671/687: the existing stock-publication chain reused by the new UI."""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal
from app.services import fbs_stock_publish_service as publisher
from app.services import fbs_stock_rule_service as rules
from app.services import inbound_intake_service as intake
from app.services.catalog_service import create_product, create_seller, create_warehouse
from app.services.tokens import decode_access_token
from tests.guards.stock_seeds import _seed


@pytest.mark.asyncio
async def test_wms687_first_enable_dispatches_after_commit_once_but_identical_replay_does_not(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A first FBS rule invokes the old publisher; an identical enabled save is a no-op."""
    seed = await _seed(db_session, on_hand=10)
    dispatched: list[tuple[uuid.UUID, uuid.UUID, str | None]] = []

    @asynccontextmanager
    async def uncontended_lock(*_args: object, **_kwargs: object):
        yield True

    monkeypatch.setattr(rules, "marketplace_seller_lock", uncontended_lock)
    monkeypatch.setattr(publisher, "_dispatch", lambda *args: dispatched.append(args))
    binding = seed.bindings[0]
    rule = rules.FbsRule(
        publish=None,
        same_everywhere=False,
        percent=0,
        by_binding={
            binding.id: rules.FbsBindingRule(publish=True, mode="percent", value=50),
        },
        by_binding_present=True,
    )

    await rules.set_rule_for_products(
        db_session, seed.tenant.id, [seed.product.id], rule,
    )
    assert dispatched == [(seed.tenant.id, seed.seller.id, "wb")]

    dispatched.clear()
    await rules.set_rule_for_products(
        db_session, seed.tenant.id, [seed.product.id], rule,
    )
    assert dispatched == []


async def _tenant_and_actor(async_client: AsyncClient) -> tuple[uuid.UUID, uuid.UUID]:
    suffix = uuid.uuid4().hex[:10]
    response = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "WMS-687 stock trigger",
            "slug": f"wms687-stock-{suffix}",
            "admin_email": f"wms687-stock-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert response.status_code == 200, response.text
    payload = decode_access_token(response.json()["access_token"])
    return uuid.UUID(str(payload["tenant_id"])), uuid.UUID(str(payload["sub"]))


@pytest.mark.asyncio
@pytest.mark.parametrize("operation_type", ["inbound", "return"])
async def test_wms687_completed_document_dispatches_existing_publisher_after_commit(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    operation_type: str,
) -> None:
    """Both document kinds create the stock movement before one after-commit publish."""
    tenant_id, actor_user_id = await _tenant_and_actor(async_client)
    async with SessionLocal() as session:
        warehouse = await create_warehouse(
            session, tenant_id, name="Основной", code=f"wms687-{uuid.uuid4().hex[:6]}",
        )
        seller = await create_seller(session, tenant_id, name="Селлер WMS-687")
        product = await create_product(
            session,
            tenant_id,
            name="Товар WMS-687",
            sku_code=f"WMS687-{uuid.uuid4().hex[:8]}",
            length_mm=10,
            width_mm=10,
            height_mm=10,
            seller_id=seller.id,
        )
        request = await intake.create_request(
            session,
            tenant_id,
            warehouse_id=warehouse.id,
            seller_id=seller.id,
            operation_type=operation_type,
        )
        await intake.add_line(
            session, tenant_id, request.id, product_id=product.id, expected_qty=2,
        )
        request_id = request.id

    published: list[tuple[uuid.UUID, uuid.UUID, str | None]] = []

    async def publish(
        tenant_id: uuid.UUID,
        seller_id: uuid.UUID,
        marketplace: str | None = None,
    ) -> None:
        published.append((tenant_id, seller_id, marketplace))

    monkeypatch.setattr(publisher, "publish_seller_stocks_now", publish)
    monkeypatch.setattr(publisher.settings, "celery_broker_url", None)
    async with SessionLocal() as session:
        if operation_type == "inbound":
            completed = await intake.complete_receiving(
                session, tenant_id, request_id, actor_user_id=actor_user_id,
            )
        else:
            completed = await intake.begin_receiving(
                session, tenant_id, request_id, actor_user_id=actor_user_id,
            )
        assert completed.status == intake.STATUS_SORTING

    await publisher.drain_background_stock_publish_tasks()
    assert published == [(tenant_id, seller.id, None)]
