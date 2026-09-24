"""WMS-456: a product without an active Ozon card is not an Ozon product.

Проверки C1-C10 из docs/requirements/WMS-456.md (раздел 5). Одна заготовка на
все тесты (_seed_case): продавец с WB-привязкой (501001) и Ozon-привязкой
(1020005029603630), обе активные, обслуживаемые и с включённой трансляцией на
одном складе WMS; товар A - без связки Ozon, правило WB включено (50%
"одинаково"), fbs_ozon_stock_sync_enabled=NULL; товар B - со связкой Ozon
(offer_id), правило 50/50 по складам, обе галки включены; свободный остаток по
100 у каждого. C11 (существующие наборы тестов) и C12 (проверка на стенде) -
вне этого файла: C11 запускается тем же pytest по перечисленным в задаче
файлам, C12 требует локального стенда аналитика и в этот файл не входит.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fbs_binding_stock_pool import FbsBindingStockPool
from app.models.fbs_warehouse_binding import FbsWarehouseBinding
from app.models.inventory_balance import InventoryBalance
from app.models.marketplace_account import MarketplaceAccount
from app.models.product import Product
from app.models.product_marketplace_link import ProductMarketplaceLink
from app.models.seller import Seller
from app.models.storage_location import StorageLocation
from app.models.tenant import Tenant
from app.models.warehouse import Warehouse
from app.services import fbs_stock_rule_service as rules
from app.services import ozon_fbs_sync_service as ozon_sync_svc
from app.services.integration_fernet import encrypt_secret
from app.services.marketplace_provider import FakeMarketplaceTransport, OzonMarketplaceProvider

WB_WAREHOUSE_ID = 501001
OZON_WB_WAREHOUSE_ID = -456001
OZON_EXTERNAL_WAREHOUSE_ID = "1020005029603630"


@pytest.fixture(autouse=True)
def _do_not_dispatch_background_publish(monkeypatch: pytest.MonkeyPatch) -> None:
    """Same convention as test_fbs_stock_rule_service.py: no real background dispatch."""
    monkeypatch.setattr(
        "app.services.fbs_stock_rule_service.schedule_seller_stock_publish",
        lambda *_args: None,
    )


@dataclass
class _Case:
    tenant: Tenant
    seller: Seller
    warehouse: Warehouse
    location: StorageLocation
    wb_binding: FbsWarehouseBinding
    ozon_binding: FbsWarehouseBinding
    product_a: Product
    product_b: Product | None


async def _seed_case(session: AsyncSession, *, include_b: bool = True) -> _Case:
    """Продавец с WB- и Ozon-привязками на одном складе WMS; товар A без карточки Ozon.

    ``include_b`` управляет только товаром B (со связкой Ozon, 50/50 по складам)
    — для C3 ("нечего публиковать") и C10 нужен продавец, у которого кроме A
    ничего нет.
    """
    tenant = Tenant(id=uuid.uuid4(), name="WMS-456", slug=f"wms456-{uuid.uuid4().hex[:10]}")
    seller = Seller(id=uuid.uuid4(), tenant_id=tenant.id, name="Seller")
    warehouse = Warehouse(
        id=uuid.uuid4(), tenant_id=tenant.id, name="WH", code=f"wh456-{uuid.uuid4().hex[:8]}",
    )
    wb_binding = FbsWarehouseBinding(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        seller_id=seller.id,
        marketplace="wb",
        wb_warehouse_id=WB_WAREHOUSE_ID,
        external_warehouse_id=str(WB_WAREHOUSE_ID),
        wms_warehouse_id=warehouse.id,
        is_active=True,
        served=True,
        stock_sync_enabled=True,
    )
    ozon_binding = FbsWarehouseBinding(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        seller_id=seller.id,
        marketplace="ozon",
        wb_warehouse_id=OZON_WB_WAREHOUSE_ID,
        external_warehouse_id=OZON_EXTERNAL_WAREHOUSE_ID,
        wms_warehouse_id=warehouse.id,
        is_active=True,
        served=True,
        stock_sync_enabled=True,
    )
    # A: no Ozon card at all. WB rule enabled, 50% "same everywhere". NULL Ozon
    # flag (never resaved) is exactly the WMS-351 rollout leftover from the
    # requirements doc's background section.
    product_a = Product(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        seller_id=seller.id,
        name="A no ozon card",
        sku_code=f"A-{uuid.uuid4().hex[:8]}",
        fbs_stock_sync_enabled=True,
        fbs_ozon_stock_sync_enabled=None,
        fbs_percent=50,
        fbs_same_everywhere=True,
    )
    location = StorageLocation(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        warehouse_id=warehouse.id,
        code=f"CELL456-{uuid.uuid4().hex[:6]}",
        barcode=f"BC456-{uuid.uuid4().hex[:8]}",
    )
    session.add_all([tenant, seller, warehouse, wb_binding, ozon_binding, product_a, location])
    to_add: list[Any] = [
        InventoryBalance(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            storage_location_id=location.id,
            product_id=product_a.id,
            quantity=100,
            quantity_unpacked=100,
        ),
        MarketplaceAccount(
            tenant_id=tenant.id,
            seller_id=seller.id,
            marketplace="ozon",
            account_slot="primary",
            external_account_id="wms456-client",
            secret_encrypted=encrypt_secret("wms456-key"),
            is_active=True,
            validation_status="valid",
        ),
    ]

    product_b: Product | None = None
    if include_b:
        # B: has an active Ozon card. Rule is a genuine 50/50 split by
        # warehouse (not "same everywhere"), both switches explicitly on -
        # this is the honest two-marketplace product WMS-351/376 already cover.
        product_b = Product(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            seller_id=seller.id,
            name="B has ozon card",
            sku_code=f"B-{uuid.uuid4().hex[:8]}",
            fbs_stock_sync_enabled=True,
            fbs_ozon_stock_sync_enabled=True,
            fbs_percent=0,
            fbs_same_everywhere=False,
        )
        to_add.extend(
            [
                product_b,
                InventoryBalance(
                    id=uuid.uuid4(),
                    tenant_id=tenant.id,
                    storage_location_id=location.id,
                    product_id=product_b.id,
                    quantity=100,
                    quantity_unpacked=100,
                ),
                ProductMarketplaceLink(
                    tenant_id=tenant.id,
                    seller_id=seller.id,
                    product_id=product_b.id,
                    marketplace="ozon",
                    external_offer_id="offer-b",
                    is_active=True,
                ),
            ]
        )
    session.add_all(to_add)
    await session.flush()
    if product_b is not None:
        session.add_all(
            [
                FbsBindingStockPool(
                    tenant_id=tenant.id, binding_id=wb_binding.id, product_id=product_b.id,
                    percent=50,
                ),
                FbsBindingStockPool(
                    tenant_id=tenant.id, binding_id=ozon_binding.id, product_id=product_b.id,
                    percent=50,
                ),
            ]
        )
    await session.commit()
    return _Case(
        tenant, seller, warehouse, location, wb_binding, ozon_binding, product_a, product_b,
    )


@pytest.mark.asyncio
async def test_c1_effective_flag_in_api(db_session: AsyncSession) -> None:
    case = await _seed_case(db_session)
    assert case.product_b is not None
    views = await rules.get_rule_views(
        db_session, case.tenant.id, [case.product_a.id, case.product_b.id]
    )
    assert views[case.product_a.id].rule.publish_ozon is False
    assert views[case.product_a.id].rule.publish is True
    assert views[case.product_b.id].rule.publish_ozon is True

    # A raw write of true directly to the column (no card involved) must not
    # move the effective flag: R1 reads "no card" as off regardless of storage.
    case.product_a.fbs_ozon_stock_sync_enabled = True
    await db_session.commit()
    views_after = await rules.get_rule_views(
        db_session, case.tenant.id, [case.product_a.id, case.product_b.id]
    )
    assert views_after[case.product_a.id].rule.publish_ozon is False
    assert views_after[case.product_a.id].rule.publish is True
    assert views_after[case.product_b.id].rule.publish_ozon is True


@pytest.mark.asyncio
async def test_c2_ozon_sync_skips_unlinked_product_without_error(db_session: AsyncSession) -> None:
    case = await _seed_case(db_session)
    transport = FakeMarketplaceTransport()

    result = await ozon_sync_svc.sync_ozon_stocks(
        db_session, case.tenant.id, case.seller.id, OzonMarketplaceProvider(transport=transport),
    )

    # Exactly one row - B's - reaches Ozon; A never appears, not even as a zero.
    assert transport.published_stocks == [
        {"warehouse_id": int(OZON_EXTERNAL_WAREHOUSE_ID), "stock": 50, "offer_id": "offer-b"}
    ]
    assert result.errors == 0
    assert result.binding_errors == 0
    assert result.products_targeted == 1
    await db_session.refresh(case.ozon_binding)
    assert case.ozon_binding.last_sync_status == "confirmed"
    assert case.ozon_binding.last_error_code is None


@pytest.mark.asyncio
async def test_c3_nothing_to_publish_when_only_the_unlinked_product_exists(
    db_session: AsyncSession,
) -> None:
    case = await _seed_case(db_session, include_b=False)
    transport = FakeMarketplaceTransport()

    result = await ozon_sync_svc.sync_ozon_stocks(
        db_session, case.tenant.id, case.seller.id, OzonMarketplaceProvider(transport=transport),
    )

    assert transport.published_stocks == []
    assert transport.calls == []  # Ozon was never even called.
    assert result.errors == 0
    await db_session.refresh(case.ozon_binding)
    assert case.ozon_binding.last_sync_status == "nothing_to_publish"
    assert case.ozon_binding.last_error_code is None


@pytest.mark.asyncio
async def test_c4_real_mapping_error_still_reported(db_session: AsyncSession) -> None:
    """A genuinely broken Ozon link (no offer_id, no numeric product_id) is unchanged."""
    case = await _seed_case(db_session)
    assert case.product_b is not None
    product_c = Product(
        id=uuid.uuid4(),
        tenant_id=case.tenant.id,
        seller_id=case.seller.id,
        name="C broken mapping",
        sku_code=f"C-{uuid.uuid4().hex[:8]}",
        fbs_stock_sync_enabled=True,
        fbs_ozon_stock_sync_enabled=True,
        fbs_percent=50,
        fbs_same_everywhere=True,
    )
    db_session.add(product_c)
    await db_session.flush()
    db_session.add_all(
        [
            InventoryBalance(
                id=uuid.uuid4(),
                tenant_id=case.tenant.id,
                storage_location_id=case.location.id,
                product_id=product_c.id,
                quantity=100,
                quantity_unpacked=100,
            ),
            ProductMarketplaceLink(
                tenant_id=case.tenant.id,
                seller_id=case.seller.id,
                product_id=product_c.id,
                marketplace="ozon",
                external_offer_id=None,
                external_product_id=None,
                is_active=True,
            ),
        ]
    )
    await db_session.commit()
    transport = FakeMarketplaceTransport()

    result = await ozon_sync_svc.sync_ozon_stocks(
        db_session, case.tenant.id, case.seller.id, OzonMarketplaceProvider(transport=transport),
    )

    # B (properly linked) still gets confirmed; C's broken mapping is the only
    # error and it still marks the binding, exactly like before WMS-456.
    assert result.products_targeted == 1
    assert result.products_confirmed == 1
    assert result.errors == 1
    assert result.binding_errors == 1
    await db_session.refresh(case.ozon_binding)
    assert case.ozon_binding.last_error_code == "product_mapping_missing"


@pytest.mark.asyncio
async def test_c5_ozon_applicability_without_common_percent_ceiling(
    db_session: AsyncSession,
) -> None:
    case = await _seed_case(db_session)
    assert case.product_b is not None

    # A has no card: 100% "same everywhere" and 100% on the single WB warehouse
    # are both accepted - only the WB binding counts toward the ceiling.
    await rules.set_rule_for_products(
        db_session, case.tenant.id, [case.product_a.id],
        rules.FbsRule(publish=True, same_everywhere=True, percent=100, by_warehouse={}),
    )
    await rules.set_rule_for_products(
        db_session, case.tenant.id, [case.product_a.id],
        rules.FbsRule(
            publish=True, same_everywhere=False, percent=0,
            by_warehouse={WB_WAREHOUSE_ID: 100},
        ),
    )

    # WMS-469: a linked product may publish 100% to WB and Ozon at once; each
    # binding is capped by the same live physical free stock, not by a summed
    # configuration ceiling.
    await rules.set_rule_for_products(
        db_session, case.tenant.id, [case.product_b.id],
        rules.FbsRule(publish=True, same_everywhere=True, percent=100, by_warehouse={}),
    )
    view = await rules.get_rule_view(db_session, case.tenant.id, case.product_b.id)
    assert view.published_now == 200


@pytest.mark.asyncio
async def test_c6_explicit_true_without_card_saves_false_and_does_not_touch_ozon(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = await _seed_case(db_session)
    zero_calls: list[tuple[str, set[Any]]] = []
    schedule_calls: list[str] = []

    async def fake_clear(_session: Any, binding: Any, ids: set[Any]) -> None:
        zero_calls.append((binding.marketplace, ids))

    monkeypatch.setattr(rules, "_clear_product_publication", fake_clear)
    monkeypatch.setattr(
        rules, "schedule_seller_stock_publish", lambda *a: schedule_calls.append(a[3]),
    )

    # Same WB share as seeded (50%): nothing changes on either marketplace.
    await rules.set_rule_for_products(
        db_session, case.tenant.id, [case.product_a.id],
        rules.FbsRule(
            publish=True, publish_ozon=True, same_everywhere=True, percent=50, by_warehouse={},
        ),
    )
    await db_session.refresh(case.product_a)
    assert case.product_a.fbs_ozon_stock_sync_enabled is False
    views = await rules.get_rule_views(db_session, case.tenant.id, [case.product_a.id])
    assert views[case.product_a.id].rule.publish_ozon is False
    assert zero_calls == []
    assert schedule_calls == []

    # Changing the WB share now schedules WB - Ozon is still never touched,
    # confirming WB and Ozon are scheduled independently of each other.
    await rules.set_rule_for_products(
        db_session, case.tenant.id, [case.product_a.id],
        rules.FbsRule(
            publish=True, publish_ozon=True, same_everywhere=True, percent=30, by_warehouse={},
        ),
    )
    assert schedule_calls == ["wb"]
    assert zero_calls == []
    await db_session.refresh(case.product_a)
    assert case.product_a.fbs_ozon_stock_sync_enabled is False


@pytest.mark.asyncio
async def test_c7_repeating_the_same_save_is_a_no_op(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = await _seed_case(db_session)
    zero_calls: list[tuple[str, set[Any]]] = []
    schedule_calls: list[str] = []

    async def fake_clear(_session: Any, binding: Any, ids: set[Any]) -> None:
        zero_calls.append((binding.marketplace, ids))

    monkeypatch.setattr(rules, "_clear_product_publication", fake_clear)
    monkeypatch.setattr(
        rules, "schedule_seller_stock_publish", lambda *a: schedule_calls.append(a[3]),
    )
    rule = rules.FbsRule(publish=True, same_everywhere=True, percent=50, by_warehouse={})

    # First save matches the seeded state exactly, so it is already a no-op;
    # the real target is the second, repeated call below.
    await rules.set_rule_for_products(db_session, case.tenant.id, [case.product_a.id], rule)
    zero_calls.clear()
    schedule_calls.clear()
    await db_session.refresh(case.wb_binding)
    await db_session.refresh(case.ozon_binding)
    wb_before = (case.wb_binding.served, case.wb_binding.stock_sync_enabled)
    ozon_before = (case.ozon_binding.served, case.ozon_binding.stock_sync_enabled)

    await rules.set_rule_for_products(db_session, case.tenant.id, [case.product_a.id], rule)

    assert zero_calls == []
    assert schedule_calls == []
    await db_session.refresh(case.wb_binding)
    await db_session.refresh(case.ozon_binding)
    assert (case.wb_binding.served, case.wb_binding.stock_sync_enabled) == wb_before
    assert (case.ozon_binding.served, case.ozon_binding.stock_sync_enabled) == ozon_before


@pytest.mark.asyncio
async def test_c8_amounts_and_published_now(db_session: AsyncSession) -> None:
    case = await _seed_case(db_session)
    assert case.product_b is not None

    view_a = await rules.get_rule_view(db_session, case.tenant.id, case.product_a.id)
    assert view_a.published_now == 50
    wb_amounts_a = await rules.publish_amounts_for_binding(
        db_session, case.wb_binding, [case.product_a]
    )
    ozon_amounts_a = await rules.publish_amounts_for_binding(
        db_session, case.ozon_binding, [case.product_a]
    )
    assert wb_amounts_a == {case.product_a.id: 50}
    # Absent, not zero: a zero here would make sync_ozon_stocks count A in
    # missing_links again (see the comment in publish_amounts_for_binding).
    assert ozon_amounts_a == {}

    view_b = await rules.get_rule_view(db_session, case.tenant.id, case.product_b.id)
    assert view_b.published_now == 100
    wb_amounts_b = await rules.publish_amounts_for_binding(
        db_session, case.wb_binding, [case.product_b]
    )
    ozon_amounts_b = await rules.publish_amounts_for_binding(
        db_session, case.ozon_binding, [case.product_b]
    )
    assert wb_amounts_b == {case.product_b.id: 50}
    assert ozon_amounts_b == {case.product_b.id: 50}


@pytest.mark.asyncio
async def test_c9_changing_a_does_not_touch_b_or_the_ozon_binding(
    db_session: AsyncSession,
) -> None:
    case = await _seed_case(db_session)
    assert case.product_b is not None
    before_b = await rules.get_rule_view(db_session, case.tenant.id, case.product_b.id)
    await db_session.refresh(case.ozon_binding)
    ozon_before = (
        case.ozon_binding.stock_sync_enabled,
        case.ozon_binding.served,
        case.ozon_binding.last_sync_status,
    )

    # Only A's WB share changes (50% -> 30%); A has no Ozon card either way.
    await rules.set_rule_for_products(
        db_session, case.tenant.id, [case.product_a.id],
        rules.FbsRule(publish=True, same_everywhere=True, percent=30, by_warehouse={}),
    )

    after_b = await rules.get_rule_view(db_session, case.tenant.id, case.product_b.id)
    assert after_b == before_b
    await db_session.refresh(case.ozon_binding)
    assert (
        case.ozon_binding.stock_sync_enabled,
        case.ozon_binding.served,
        case.ozon_binding.last_sync_status,
    ) == ozon_before
    ozon_amounts_a = await rules.publish_amounts_for_binding(
        db_session, case.ozon_binding, [case.product_a]
    )
    assert ozon_amounts_a == {}


@pytest.mark.asyncio
async def test_c10_a_later_card_does_not_auto_enable_ozon(db_session: AsyncSession) -> None:
    case = await _seed_case(db_session, include_b=False)

    # A explicitly requests publish_ozon=True while it still has no card: the
    # effective false is what gets persisted (decision 3 in the requirements).
    await rules.set_rule_for_products(
        db_session, case.tenant.id, [case.product_a.id],
        rules.FbsRule(
            publish=True, publish_ozon=True, same_everywhere=True, percent=50, by_warehouse={},
        ),
    )
    await db_session.refresh(case.product_a)
    assert case.product_a.fbs_ozon_stock_sync_enabled is False

    # A card appears later (catalog merge, Ozon import, ...).
    db_session.add(
        ProductMarketplaceLink(
            tenant_id=case.tenant.id,
            seller_id=case.seller.id,
            product_id=case.product_a.id,
            marketplace="ozon",
            external_offer_id="offer-a-late",
            is_active=True,
        )
    )
    await db_session.commit()

    # The card alone does not resurrect the old request: still false.
    view = await rules.get_rule_view(db_session, case.tenant.id, case.product_a.id)
    assert view.rule.publish_ozon is False

    # Only an explicit operator save turns it on, now that a card exists.
    await rules.set_rule_for_products(
        db_session, case.tenant.id, [case.product_a.id],
        rules.FbsRule(
            publish=True, publish_ozon=True, same_everywhere=True, percent=50, by_warehouse={},
        ),
    )
    await db_session.refresh(case.product_a)
    assert case.product_a.fbs_ozon_stock_sync_enabled is True
    view_after = await rules.get_rule_view(db_session, case.tenant.id, case.product_a.id)
    assert view_after.rule.publish_ozon is True
