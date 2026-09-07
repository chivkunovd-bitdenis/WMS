"""WMS-010: permitted piece rates price completed product quantities in both paths."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.session import SessionLocal
from app.models.billing import BillingLedgerEntry
from app.models.inbound_intake import InboundIntakeLine, InboundIntakeRequest
from app.models.product import Product
from app.models.seller import Seller
from app.services.inbound_intake_service import _record_charge_if_done


@pytest.mark.asyncio
@pytest.mark.parametrize("tariff_path", ["legacy", "matrix"])
async def test_completed_multiline_intake_prices_pieces_once_and_keeps_tenant_scope(
    async_client,
    tariff_path: str,
) -> None:
    async def register():
        suffix = uuid.uuid4().hex
        response = await async_client.post(
            "/auth/register",
            json={
                "organization_name": suffix,
                "slug": suffix,
                "admin_email": f"{suffix}@example.com",
                "password": "password123",
            },
        )
        assert response.status_code == 200, response.text
        headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
        me = await async_client.get("/auth/me", headers=headers)
        return headers, uuid.UUID(me.json()["tenant_id"])

    headers, tenant_id = await register()
    foreign_headers, foreign_tenant_id = await register()
    for scope_headers, amount in ((headers, 22000), (foreign_headers, 99000)):
        if tariff_path == "legacy":
            response = await async_client.post(
                "/billing/tariffs",
                headers=scope_headers,
                json={
                    "service_code": "inbound",
                    "unit": "item",
                    "amount": str(amount / 100),
                    "valid_from": "2026-09-01",
                },
            )
            assert response.status_code == 201, response.text
        else:
            matrix = (
                await async_client.get(
                    "/billing/tariff-matrix",
                    headers=scope_headers,
                )
            ).json()
            response = await async_client.put(
                "/billing/tariff-matrix",
                headers=scope_headers,
                json={
                    "revision": matrix["revision"],
                    "services": [
                        {
                            "service_code": row["service_code"],
                            "enabled": row["service_code"] == "inbound",
                        }
                        for row in matrix["services"]
                    ],
                    "versions": [
                        {
                            "service_code": "inbound",
                            "unit": "item",
                            "enabled": True,
                            "rate": amount,
                            "valid_from_at": "2026-09-01T00:00:00Z",
                        }
                    ],
                },
            )
            assert response.status_code == 200, response.text

    async with SessionLocal() as session:
        seller = Seller(tenant_id=tenant_id, name="Piece-rate seller")
        session.add(seller)
        await session.flush()
        products = [
            Product(
                tenant_id=tenant_id, seller_id=seller.id, name=f"Product {i}", sku_code=f"piece-{i}"
            )
            for i in range(2)
        ]
        session.add_all(products)
        await session.flush()
        # The request is a transient service input; the ledger and products are real DB rows.
        request = InboundIntakeRequest(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            seller_id=seller.id,
            status="sorting",
            operation_type="inbound",
            posted_at=datetime(2026, 9, 8, 12, tzinfo=UTC),
            lines=[
                InboundIntakeLine(id=uuid.uuid4(), product_id=product.id, posted_qty=qty)
                for product, qty in zip(products, (2, 3), strict=True)
            ],
        )
        await _record_charge_if_done(session, request, performer_id=None)
        assert await session.scalar(select(BillingLedgerEntry.id)) is None
        request.status = "done"
        await _record_charge_if_done(session, request, performer_id=None)
        await session.commit()
        await _record_charge_if_done(session, request, performer_id=None)
        await session.commit()

    async with SessionLocal() as session:
        entries = (
            await session.scalars(
                select(BillingLedgerEntry).options(selectinload(BillingLedgerEntry.lines))
            )
        ).all()
        assert len(entries) == 1
        entry = entries[0]
        assert entry.tenant_id == tenant_id != foreign_tenant_id
        assert entry.quantity == Decimal("5")
        assert entry.unit == "item"
        assert entry.amount == 110000  # Five pieces at 220 RUB; two product rows.
        assert sorted((line.billing_quantity, line.amount) for line in entry.lines) == [
            (Decimal("2"), 44000),
            (Decimal("3"), 66000),
        ]
        assert all(line.billing_unit == "item" for line in entry.lines)
