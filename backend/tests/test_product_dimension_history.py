"""TC-NEW-003: manual measurements remain active until WB is explicitly restored."""

from __future__ import annotations

import time
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal
from app.models.product import Product
from app.models.product_dimension_event import ProductDimensionEvent
from app.services.catalog_service import (
    CatalogError,
    restore_latest_wb_dimensions,
    update_product_container_volume,
    update_product_dimensions,
)
from app.services.tokens import decode_access_token
from app.services.wildberries_product_import_service import upsert_products_from_wb_cards


async def _tenant_seller_and_operator(
    async_client: AsyncClient,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    suffix = str(time.time_ns())
    registered = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Dimension history",
            "slug": f"dimension-history-{suffix}",
            "admin_email": f"dimension-history-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert registered.status_code == 200, registered.text
    token = str(registered.json()["access_token"])
    seller = await async_client.post(
        "/sellers",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Dimension seller"},
    )
    assert seller.status_code == 201, seller.text
    claims = decode_access_token(token)
    return (
        uuid.UUID(str(claims["tenant_id"])),
        uuid.UUID(seller.json()["id"]),
        uuid.UUID(str(claims["sub"])),
    )


def _wb_card(barcode: str, *, length_cm: int = 30) -> dict[str, object]:
    return {
        "nmID": 800_123_456,
        "vendorCode": "DIM-HISTORY",
        "title": "Товар с историей габаритов",
        "dimensions": {"length": length_cm, "width": 20, "height": 10},
        "sizes": [{"chrtID": 1, "skus": [barcode]}],
    }


async def _events(session: AsyncSession, product_id: uuid.UUID) -> list[ProductDimensionEvent]:
    result = await session.execute(
        select(ProductDimensionEvent)
        .where(ProductDimensionEvent.product_id == product_id)
        .order_by(ProductDimensionEvent.observed_at)
    )
    return list(result.scalars())


@pytest.mark.asyncio
async def test_manual_measurement_and_container_override_create_active_versions(
    async_client: AsyncClient,
) -> None:
    tenant_id, seller_id, operator_id = await _tenant_seller_and_operator(async_client)
    async with SessionLocal() as session:
        product = Product(
            tenant_id=tenant_id,
            seller_id=seller_id,
            name="Обмеренный товар",
            sku_code=f"MEASURED-{time.time_ns()}",
        )
        session.add(product)
        await session.commit()

        await update_product_dimensions(
            session,
            tenant_id,
            product.id,
            length_mm=100,
            width_mm=200,
            height_mm=300,
            author_user_id=operator_id,
        )
        refreshed = await session.get(Product, product.id)
        assert refreshed is not None
        assert refreshed.volume_liters == pytest.approx(6.0)
        assert refreshed.dimensions_source == "manual"
        assert refreshed.dimensions_updated_by_user_id == operator_id

        with pytest.raises(CatalogError, match="invalid_container_dimensions"):
            await update_product_container_volume(
                session,
                tenant_id,
                product.id,
                volume_liters=0.5,
                container_basis="   ",
                author_user_id=operator_id,
            )

        await update_product_container_volume(
            session,
            tenant_id,
            product.id,
            volume_liters=0.5,
            container_basis="Короб для хранения",
            author_user_id=operator_id,
        )
        refreshed = await session.get(Product, product.id)
        assert refreshed is not None
        assert refreshed.volume_liters == pytest.approx(0.5)
        assert refreshed.dimensions_source == "container_override"
        events = await _events(session, product.id)
        assert [event.source for event in events] == ["manual", "container_override"]
        assert sum(event.applied for event in events) == 1
        assert events[-1].container_basis == "Короб для хранения"


@pytest.mark.asyncio
async def test_wb_observation_does_not_replace_manual_measurement_and_restore_makes_new_active_wb(
    async_client: AsyncClient,
) -> None:
    tenant_id, seller_id, operator_id = await _tenant_seller_and_operator(async_client)
    barcode = f"WB-DIM-{time.time_ns()}"
    async with SessionLocal() as session:
        product = Product(
            tenant_id=tenant_id,
            seller_id=seller_id,
            name="Ручной обмер поверх WB",
            sku_code=f"WB-MANUAL-{time.time_ns()}",
            wb_barcode=barcode,
        )
        session.add(product)
        await session.commit()
        product_id = product.id

        await update_product_dimensions(
            session,
            tenant_id,
            product_id,
            length_mm=100,
            width_mm=100,
            height_mm=100,
            author_user_id=operator_id,
        )
        await upsert_products_from_wb_cards(session, tenant_id, seller_id, [_wb_card(barcode)])
        await upsert_products_from_wb_cards(session, tenant_id, seller_id, [_wb_card(barcode)])

        refreshed = await session.get(Product, product_id)
        assert refreshed is not None
        assert refreshed.volume_liters == pytest.approx(1.0)
        assert refreshed.dimensions_source == "manual"
        assert refreshed.dimensions_updated_by_user_id == operator_id
        events = await _events(session, product_id)
        assert [event.source for event in events] == ["manual", "wb"]
        assert events[0].applied is True
        assert events[1].applied is False

        await restore_latest_wb_dimensions(session, tenant_id, product_id)
        refreshed = await session.get(Product, product_id)
        assert refreshed is not None
        assert refreshed.volume_liters == pytest.approx(6.0)
        assert refreshed.dimensions_source == "wb"
        assert refreshed.dimensions_updated_at is not None
        assert refreshed.dimensions_updated_by_user_id is None
        events = await _events(session, product_id)
        assert [event.source for event in events] == ["manual", "wb", "wb"]
        assert sum(event.applied for event in events) == 1
        assert events[-1].applied is True
