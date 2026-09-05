"""WMS-375: retain the old Ozon target until explicit zero is confirmed."""
from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.models.product_marketplace_link import ProductMarketplaceLink
from app.services.fbs_warehouse_binding_service import FbsWarehouseBindingError, upsert_binding
from app.services.marketplace_provider import MarketplaceProviderError
from tests.test_fbs_stock_rule_service import _seed


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["disable", "replace", "reject", "invalid_new", "foreign"])
async def test_ozon_binding_cleanup_preserves_target_until_confirmed(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch, change: str,
) -> None:
    seed = await _seed(db_session)
    binding = seed.bindings[0]
    binding.marketplace = "ozon"
    binding.external_warehouse_id = "102"
    binding.served = change != "foreign"
    seed.product.fbs_percent = 50
    unrelated = Product(
        id=uuid.uuid4(), tenant_id=seed.tenant.id, seller_id=seed.seller.id,
        name="Never configured", sku_code=uuid.uuid4().hex,
    )
    db_session.add(unrelated)
    for product, offer in ((seed.product, "configured"), (unrelated, "untouched")):
        db_session.add(ProductMarketplaceLink(
            tenant_id=seed.tenant.id, seller_id=seed.seller.id,
            product_id=product.id, marketplace="ozon", external_offer_id=offer,
            is_active=True,
        ))
    await db_session.commit()
    calls: list[list[dict[str, object]]] = []

    async def credentials(*_args: Any) -> tuple[str, str]:
        return "test-client", "test-key"

    class Provider:
        async def publish_stocks(self, **kwargs: Any) -> int:
            # The address is still intact when the external side effect occurs.
            assert binding.external_warehouse_id == "102"
            assert binding.stock_sync_enabled
            calls.append(kwargs["stocks"])
            if change == "reject":
                raise MarketplaceProviderError("ozon", 500, {}, code="ozon_stock_rejected")
            return len(kwargs["stocks"])

    monkeypatch.setattr(
        "app.services.marketplace_account_service.MarketplaceAccountService.stored_credentials",
        credentials,
    )
    monkeypatch.setattr(
        "app.services.ozon_provider_factory.build_ozon_provider", lambda **_kw: Provider(),
    )
    monkeypatch.setattr(
        "app.services.fbs_stock_publish_service.schedule_seller_stock_publish", lambda *_a: None,
    )
    new_id = "bad-id" if change == "invalid_new" else "103" if change == "replace" else "102"
    enabled = change in {"replace", "invalid_new"}
    if change in {"reject", "invalid_new"}:
        with pytest.raises(FbsWarehouseBindingError) as error:
            await upsert_binding(
                db_session, seed.tenant.id, seed.seller.id, binding.wb_warehouse_id,
                wms_warehouse_id=seed.warehouse.id, stock_sync_enabled=enabled,
                marketplace="ozon", external_warehouse_id=new_id,
            )
        assert error.value.code == (
            "invalid_wb_warehouse_id" if change == "invalid_new" else "ozon_stock_cleanup_failed"
        )
        await db_session.refresh(binding)
        assert binding.external_warehouse_id == "102"
        assert binding.stock_sync_enabled
    else:
        result = await upsert_binding(
            db_session, seed.tenant.id, seed.seller.id, binding.wb_warehouse_id,
                wms_warehouse_id=seed.warehouse.id, stock_sync_enabled=enabled,
                marketplace="ozon", external_warehouse_id=new_id,
        )
        assert result.external_warehouse_id == new_id
        assert result.stock_sync_enabled == (change == "replace")
    assert calls == (
        [] if change in {"invalid_new", "foreign"}
        else [[{"warehouse_id": 102, "stock": 0, "offer_id": "configured"}]]
    )
