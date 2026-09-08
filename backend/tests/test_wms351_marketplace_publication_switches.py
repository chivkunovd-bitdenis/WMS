"""WMS-351: each marketplace switch owns publication and its final zero."""

from dataclasses import replace
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fbs_binding_stock_pool import FbsBindingStockPool
from app.services import fbs_stock_rule_service as rules
from tests.test_fbs_stock_rule_service import _seed


@pytest.mark.asyncio
@pytest.mark.parametrize("wb,ozon", [(True, False), (False, True), (True, True), (False, False)])
async def test_independent_switches_roundtrip_and_publish_scope(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    wb: bool,
    ozon: bool,
) -> None:
    seed = await _seed(db_session, on_hand=10, wb_warehouse_ids=(501001, 501002))
    wb_binding, ozon_binding = seed.bindings
    ozon_binding.marketplace = "ozon"
    ozon_binding.external_warehouse_id = "501002"
    seed.product.fbs_percent = 50
    seed.product.fbs_same_everywhere = False
    for binding in seed.bindings:
        db_session.add(
            FbsBindingStockPool(
                tenant_id=seed.tenant.id,
                binding_id=binding.id,
                product_id=seed.product.id,
                quantity=0,
                percent=50,
            )
        )
    await db_session.commit()
    before = await rules.get_rule_view(db_session, seed.tenant.id, seed.product.id)
    assert before.rule.publish and before.rule.publish_ozon
    assert seed.product.fbs_ozon_stock_sync_enabled is None
    zeros: list[tuple[str, set[Any]]] = []
    scheduled: list[str] = []

    async def clear(_session: Any, binding: Any, ids: set[Any]) -> None:
        zeros.append((binding.marketplace, ids))

    monkeypatch.setattr(rules, "_clear_product_publication", clear)
    monkeypatch.setattr(rules, "schedule_seller_stock_publish", lambda *a: scheduled.append(a[3]))
    rule = replace(before.rule, publish=wb, publish_ozon=ozon)
    await rules.set_rule_for_products(db_session, seed.tenant.id, [seed.product.id], rule)
    reread = await rules.get_rule_view(db_session, seed.tenant.id, seed.product.id)
    assert (reread.rule.publish, reread.rule.publish_ozon) == (wb, ozon)
    assert reread.published_now == 5 * (int(wb) + int(ozon))
    assert zeros == [
        (mp, {seed.product.id}) for mp, enabled in [("wb", wb), ("ozon", ozon)] if not enabled
    ]
    assert scheduled == []
    for binding, enabled in [(wb_binding, wb), (ozon_binding, ozon)]:
        amounts = await rules.publish_amounts_for_binding(
            db_session,
            binding,
            [seed.product],
        )
        assert amounts == ({seed.product.id: 5} if enabled else {})
        assert binding.served and binding.stock_sync_enabled
    await rules.set_rule_for_products(db_session, seed.tenant.id, [seed.product.id], rule)
    assert len(zeros) == int(not wb) + int(not ozon)
    assert scheduled == []
    if not wb:
        await rules.set_rule_for_products(
            db_session,
            seed.tenant.id,
            [seed.product.id],
            replace(rule, publish=True),
        )
        assert scheduled == ["wb"]
        assert seed.product.fbs_ozon_stock_sync_enabled == ozon


@pytest.mark.asyncio
async def test_failed_final_zero_keeps_old_switches(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed = await _seed(db_session)
    seed.product.fbs_percent = 50
    await db_session.commit()
    before = await rules.get_rule_view(db_session, seed.tenant.id, seed.product.id)

    async def reject(*_args: Any) -> None:
        raise rules.FbsStockRuleError("stock_cleanup_failed")

    monkeypatch.setattr(rules, "_clear_product_publication", reject)
    with pytest.raises(rules.FbsStockRuleError, match="stock_cleanup_failed"):
        await rules.set_rule_for_products(
            db_session,
            seed.tenant.id,
            [seed.product.id],
            replace(before.rule, publish=False),
        )
    await db_session.refresh(seed.product)
    assert seed.product.fbs_stock_sync_enabled
    assert seed.product.fbs_ozon_stock_sync_enabled is None


@pytest.mark.asyncio
async def test_old_rule_request_freezes_ozon_before_changing_wb(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed = await _seed(db_session)
    seed.product.fbs_percent = 50
    await db_session.commit()

    async def clear(*_args: Any) -> None:
        pass

    monkeypatch.setattr(rules, "_clear_product_publication", clear)
    monkeypatch.setattr(rules, "schedule_seller_stock_publish", lambda *_a: None)
    await rules.set_rule_for_products(
        db_session,
        seed.tenant.id,
        [seed.product.id],
        rules.FbsRule(publish=False, same_everywhere=True, percent=50),
    )
    assert not seed.product.fbs_stock_sync_enabled
    assert seed.product.fbs_ozon_stock_sync_enabled is True


@pytest.mark.asyncio
@pytest.mark.parametrize("units", [False, True])
async def test_disabled_allocation_is_preserved_without_blocking_other_marketplace(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    units: bool,
) -> None:
    seed = await _seed(db_session, on_hand=10, wb_warehouse_ids=(501001, 501002))
    seed.bindings[1].marketplace = "ozon"
    seed.product.fbs_stock_sync_enabled = False
    seed.product.fbs_ozon_stock_sync_enabled = False
    await db_session.commit()
    monkeypatch.setattr(rules, "schedule_seller_stock_publish", lambda *_a: None)
    rule = rules.FbsRule(
        publish=False,
        publish_ozon=True,
        same_everywhere=False,
        percent=0,
        by_warehouse={"wb:501001": 100, "ozon:501002": 100},
        units_mode=units,
        units_by_warehouse={"wb:501001": 10, "ozon:501002": 10},
    )
    await rules.set_rule_for_products(db_session, seed.tenant.id, [seed.product.id], rule)
    view = await rules.get_rule_view(db_session, seed.tenant.id, seed.product.id)
    assert view.published_now == 10
    assert view.rule.units_by_warehouse[501001] == (10 if units else 0)
    assert view.rule.by_warehouse[501001] == 100
    with pytest.raises(rules.FbsStockRuleError):
        await rules.set_rule_for_products(
            db_session,
            seed.tenant.id,
            [seed.product.id],
            replace(rule, publish=True),
        )


@pytest.mark.asyncio
async def test_ozon_final_zero_targets_only_changed_product_and_failure_preserves_rule(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.models.product_marketplace_link import ProductMarketplaceLink
    from app.services.marketplace_provider import MarketplaceProviderError

    seed = await _seed(db_session)
    binding = seed.bindings[0]
    binding.marketplace = "ozon"
    binding.external_warehouse_id = "501001"
    seed.product.fbs_stock_sync_enabled = False
    seed.product.fbs_ozon_stock_sync_enabled = True
    seed.product.fbs_percent = 100
    seed.product.wb_chrt_id = None
    db_session.add(
        ProductMarketplaceLink(
            tenant_id=seed.tenant.id,
            seller_id=seed.seller.id,
            product_id=seed.product.id,
            marketplace="ozon",
            external_offer_id="ozon-only",
            is_active=True,
        )
    )
    await db_session.commit()
    calls: list[list[dict[str, Any]]] = []
    reject = True

    class Provider:
        async def publish_stocks(self, **kwargs: Any) -> int:
            calls.append(kwargs["stocks"])
            if reject:
                raise MarketplaceProviderError("ozon", 500, {}, code="ozon_stock_rejected")
            return len(kwargs["stocks"])

    async def credentials(*_args: Any) -> tuple[str, str]:
        return "synthetic-client", "synthetic-key"

    monkeypatch.setattr(
        "app.services.marketplace_account_service.MarketplaceAccountService.stored_credentials",
        credentials,
    )
    monkeypatch.setattr(
        "app.services.ozon_provider_factory.build_ozon_provider", lambda **_k: Provider()
    )
    monkeypatch.setattr(
        rules, "schedule_seller_stock_publish", lambda *_a: pytest.fail("unexpected publish")
    )
    rule = rules.FbsRule(publish=False, publish_ozon=False, same_everywhere=True, percent=100)
    with pytest.raises(rules.FbsStockRuleError):
        await rules.set_rule_for_products(db_session, seed.tenant.id, [seed.product.id], rule)
    await db_session.rollback()
    await db_session.refresh(seed.product)
    assert seed.product.fbs_ozon_stock_sync_enabled
    reject = False
    await rules.set_rule_for_products(db_session, seed.product.tenant_id, [seed.product.id], rule)
    assert not seed.product.fbs_ozon_stock_sync_enabled
    assert calls == [[{"warehouse_id": 501001, "stock": 0, "offer_id": "ozon-only"}]] * 2


@pytest.mark.asyncio
async def test_bulk_untouched_marketplace_preserves_each_products_legacy_value(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import uuid

    from app.models.product import Product

    seed = await _seed(db_session)
    seed.product.fbs_percent = 0
    other = Product(
        id=uuid.uuid4(),
        tenant_id=seed.tenant.id,
        seller_id=seed.seller.id,
        name="Other legacy flags",
        sku_code=uuid.uuid4().hex,
        fbs_stock_sync_enabled=False,
        fbs_ozon_stock_sync_enabled=None,
        fbs_percent=0,
    )
    db_session.add(other)
    await db_session.commit()
    scheduled = []

    async def clear(*_a: Any) -> None:
        pass

    monkeypatch.setattr(rules, "_clear_product_publication", clear)
    monkeypatch.setattr(rules, "schedule_seller_stock_publish", lambda *a: scheduled.append(a[3]))
    ids = [seed.product.id, other.id]
    await rules.set_rule_for_products(
        db_session,
        seed.tenant.id,
        ids,
        rules.FbsRule(
            publish=None,
            publish_ozon=True,
            same_everywhere=True,
            percent=0,
        ),
    )
    assert seed.product.fbs_stock_sync_enabled is True
    assert other.fbs_stock_sync_enabled is False
    assert seed.product.fbs_ozon_stock_sync_enabled and other.fbs_ozon_stock_sync_enabled
    assert scheduled == ["ozon"]
    await rules.set_rule_for_products(
        db_session,
        seed.tenant.id,
        ids,
        rules.FbsRule(
            publish=False,
            publish_ozon=None,
            same_everywhere=True,
            percent=0,
        ),
    )
    assert not seed.product.fbs_stock_sync_enabled and not other.fbs_stock_sync_enabled
    assert seed.product.fbs_ozon_stock_sync_enabled and other.fbs_ozon_stock_sync_enabled
    assert scheduled == ["ozon"]


@pytest.mark.asyncio
@pytest.mark.parametrize("ozon_enabled", [True, False])
async def test_ozon_order_scope_uses_its_own_switch(
    db_session: AsyncSession,
    ozon_enabled: bool,
) -> None:
    from unittest.mock import AsyncMock

    from sqlalchemy import select

    from app.models.product import Product
    from app.services.ozon_fbs_sync_service import sync_ozon_orders
    from tests.test_fbs_ozon_lane import _seed_ozon_scope_case

    tenant, seller, _warehouse, provider = await _seed_ozon_scope_case(
        db_session,
        published=not ozon_enabled,
        served=True,
    )
    product = (await db_session.scalars(select(Product))).one()
    product.fbs_ozon_stock_sync_enabled = ozon_enabled
    await db_session.commit()
    result = await sync_ozon_orders(db_session, tenant.id, seller.id, provider, AsyncMock())
    assert result["orders_created"] == int(ozon_enabled)
