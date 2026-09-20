"""WMS-469 backend contract: per-binding rules, clamps, retries and scope."""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.products import ProductFbsRuleBody, _rule_from_body
from app.db.session import SessionLocal, engine
from app.models.fbs_binding_stock_pool import FbsBindingStockPool
from app.models.fbs_warehouse_binding import FbsWarehouseBinding
from app.models.inventory_balance import InventoryBalance
from app.models.marketplace_account import MarketplaceAccount
from app.models.product import Product
from app.models.product_marketplace_link import ProductMarketplaceLink
from app.models.seller import Seller
from app.models.seller_wildberries_credentials import SellerWildberriesCredentials
from app.models.storage_location import StorageLocation
from app.models.tenant import Tenant
from app.models.warehouse import Warehouse
from app.services import fbs_stock_publish_service as publish_service
from app.services import fbs_stock_rule_service as rules
from app.services import fbs_warehouse_binding_service as bindings_service
from app.services import inventory_service
from app.services.fbs_autopoll_service import SellerPollTarget
from app.services.integration_fernet import encrypt_secret
from app.services.marketplace_provider import FakeMarketplaceTransport, OzonMarketplaceProvider
from tests.test_product_fbs_rule_bulk_read_api import (
    _create_product,
    _create_seller,
    _register_tenant,
    _seller_headers,
)


@dataclass(frozen=True)
class Case:
    tenant: Tenant
    seller: Seller
    warehouse: Warehouse
    bindings: tuple[FbsWarehouseBinding, FbsWarehouseBinding]
    products: tuple[Product, Product]


@pytest.fixture(autouse=True)
def _no_real_rule_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rules, "schedule_seller_stock_publish", lambda *_args: None)


async def _seed_case(session: AsyncSession) -> Case:
    tenant = Tenant(id=uuid.uuid4(), name="WMS-469", slug=f"wms469-{uuid.uuid4().hex[:8]}")
    seller = Seller(id=uuid.uuid4(), tenant_id=tenant.id, name="Seller WMS-469")
    warehouse = Warehouse(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        name="Основной склад ФФ",
        code=f"wms469-{uuid.uuid4().hex[:8]}",
    )
    location = StorageLocation(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        warehouse_id=warehouse.id,
        code=f"CELL-{uuid.uuid4().hex[:6]}",
        barcode=f"BC-{uuid.uuid4().hex[:8]}",
    )
    wb = FbsWarehouseBinding(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        seller_id=seller.id,
        marketplace="wb",
        wb_warehouse_id=501001,
        wms_warehouse_id=warehouse.id,
        is_active=True,
        served=True,
        stock_sync_enabled=True,
    )
    ozon = FbsWarehouseBinding(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        seller_id=seller.id,
        marketplace="ozon",
        external_warehouse_id="1020005028840530",
        wb_warehouse_id=1020005028840530,
        wms_warehouse_id=warehouse.id,
        is_active=True,
        served=True,
        stock_sync_enabled=True,
    )
    first = Product(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        seller_id=seller.id,
        name="Товар с остатком 50",
        sku_code=f"P50-{uuid.uuid4().hex[:8]}",
    )
    second = Product(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        seller_id=seller.id,
        name="Ограничивающий товар",
        sku_code=f"P30-{uuid.uuid4().hex[:8]}",
    )
    session.add_all([tenant, seller, warehouse, location, wb, ozon, first, second])
    for product, quantity in ((first, 50), (second, 30)):
        session.add_all(
            [
                InventoryBalance(
                    tenant_id=tenant.id,
                    storage_location_id=location.id,
                    product_id=product.id,
                    quantity=quantity,
                    quantity_unpacked=quantity,
                ),
                ProductMarketplaceLink(
                    tenant_id=tenant.id,
                    seller_id=seller.id,
                    product_id=product.id,
                    marketplace="ozon",
                    external_offer_id=f"offer-{product.id}",
                    is_active=True,
                ),
            ]
        )
    await session.commit()
    return Case(tenant, seller, warehouse, (wb, ozon), (first, second))


@pytest.mark.asyncio
async def test_c7_c8_c10_c14_binding_rules_clamp_and_publish_independently(
    db_session: AsyncSession,
) -> None:
    """C7/C8/C10/C14: clamp units, floor percent, allow WB 100% + Ozon 100%."""
    case = await _seed_case(db_session)
    wb, ozon = case.bindings
    first, second = case.products

    await rules.set_rule_for_products(
        db_session,
        case.tenant.id,
        [first.id, second.id],
        rules.FbsRule(
            publish=None,
            same_everywhere=False,
            percent=0,
            by_binding={
                wb.id: rules.FbsBindingRule(publish=True, mode="percent", value=100),
                ozon.id: rules.FbsBindingRule(publish=True, mode="percent", value=100),
            },
        ),
    )
    views = await rules.get_rule_views(
        db_session, case.tenant.id, [first.id, second.id]
    )
    assert views[first.id].by_binding[wb.id].published_now == 50
    assert views[first.id].by_binding[ozon.id].published_now == 50
    assert views[second.id].by_binding[wb.id].published_now == 30
    assert views[second.id].by_binding[ozon.id].published_now == 30

    result = await rules.set_rule_for_products(
        db_session,
        case.tenant.id,
        [first.id, second.id],
        rules.FbsRule(
            publish=None,
            same_everywhere=False,
            percent=0,
            by_binding={
                wb.id: rules.FbsBindingRule(publish=True, mode="units", value=50),
            },
        ),
    )
    clamp = result.clamps[wb.id]
    assert (clamp.requested_value, clamp.saved_value) == (50, 30)
    assert clamp.limiting_product_id == second.id
    assert clamp.limiting_product_name == "Ограничивающий товар"

    reread = await rules.get_rule_views(
        db_session, case.tenant.id, [first.id, second.id]
    )
    for product in case.products:
        assert reread[product.id].by_binding[wb.id].mode == "units"
        assert reread[product.id].by_binding[wb.id].value == 30
        # The partial WB edit must not erase the independent Ozon rule.
        assert reread[product.id].by_binding[ozon.id].mode == "percent"
        assert reread[product.id].by_binding[ozon.id].value == 100


@pytest.mark.asyncio
async def test_c22_identical_repeat_is_idempotent_without_duplicate_pools(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """C22/C31: replay adds no rows and never repeats a confirmed final zero."""
    case = await _seed_case(db_session)
    request = rules.FbsRule(
        publish=None,
        same_everywhere=False,
        percent=0,
        by_binding={
            binding.id: rules.FbsBindingRule(publish=True, mode="percent", value=50)
            for binding in case.bindings
        },
    )
    for _ in range(2):
        await rules.set_rule_for_products(
            db_session,
            case.tenant.id,
            [product.id for product in case.products],
            request,
        )
    count = await db_session.scalar(select(func.count()).select_from(FbsBindingStockPool))
    assert count == 4

    zeroed: list[tuple[uuid.UUID, set[uuid.UUID]]] = []

    async def clear(
        _session: AsyncSession,
        binding: FbsWarehouseBinding,
        product_ids: set[uuid.UUID],
    ) -> None:
        zeroed.append((binding.id, product_ids))

    monkeypatch.setattr(rules, "_clear_product_publication", clear)
    disabled = rules.FbsRule(
        publish=None,
        same_everywhere=False,
        percent=0,
        by_binding={
            binding.id: rules.FbsBindingRule(
                publish=False,
                mode="percent",
                value=50,
            )
            for binding in case.bindings
        },
    )
    for _ in range(2):
        await rules.set_rule_for_products(
            db_session,
            case.tenant.id,
            [product.id for product in case.products],
            disabled,
        )
    assert {binding_id for binding_id, _product_ids in zeroed} == {
        binding.id for binding in case.bindings
    }
    assert len(zeroed) == 2
    expected_products = {product.id for product in case.products}
    assert all(product_ids == expected_products for _, product_ids in zeroed)
    reread = await rules.get_rule_views(
        db_session,
        case.tenant.id,
        [product.id for product in case.products],
    )
    assert all(
        item.by_binding[binding.id].value == 50
        for item in reread.values()
        for binding in case.bindings
    )


@pytest.mark.asyncio
async def test_partial_save_materializes_legacy_same_everywhere_neighbour(
    db_session: AsyncSession,
) -> None:
    """B1: a partial WB edit preserves an untouched legacy Ozon percentage."""
    case = await _seed_case(db_session)
    wb, ozon = case.bindings
    product = case.products[0]
    product.fbs_same_everywhere = True
    product.fbs_percent = 50
    product.fbs_stock_sync_enabled = True
    product.fbs_ozon_stock_sync_enabled = True
    product.fbs_units_mode = False
    await db_session.commit()

    before = await rules.publish_amounts_for_binding(db_session, ozon, [product])
    assert before == {product.id: 25}

    await rules.set_rule_for_products(
        db_session,
        case.tenant.id,
        [product.id],
        rules.FbsRule(
            publish=None,
            same_everywhere=False,
            percent=0,
            by_binding={
                wb.id: rules.FbsBindingRule(
                    publish=True,
                    mode="units",
                    value=10,
                )
            },
        ),
    )

    view = await rules.get_rule_view(db_session, case.tenant.id, product.id)
    after = await rules.publish_amounts_for_binding(db_session, ozon, [product])
    assert view.by_binding[ozon.id].mode == "percent"
    assert view.by_binding[ozon.id].value == 50
    assert view.by_binding[ozon.id].published_now == 25
    assert after == before


@pytest.mark.asyncio
async def test_partial_save_materializes_legacy_by_warehouse_neighbour(
    db_session: AsyncSession,
) -> None:
    """B1: a partial WB edit preserves an untouched legacy Ozon pool row."""
    case = await _seed_case(db_session)
    wb, ozon = case.bindings
    product = case.products[0]
    product.fbs_same_everywhere = False
    product.fbs_percent = 0
    product.fbs_stock_sync_enabled = True
    product.fbs_ozon_stock_sync_enabled = True
    product.fbs_units_mode = False
    db_session.add_all(
        [
            FbsBindingStockPool(
                tenant_id=case.tenant.id,
                binding_id=binding.id,
                product_id=product.id,
                percent=40,
                quantity=0,
            )
            for binding in (wb, ozon)
        ]
    )
    await db_session.commit()

    before = await rules.publish_amounts_for_binding(db_session, ozon, [product])
    assert before == {product.id: 20}

    await rules.set_rule_for_products(
        db_session,
        case.tenant.id,
        [product.id],
        rules.FbsRule(
            publish=None,
            same_everywhere=False,
            percent=0,
            by_binding={
                wb.id: rules.FbsBindingRule(
                    publish=True,
                    mode="units",
                    value=10,
                )
            },
        ),
    )

    view = await rules.get_rule_view(db_session, case.tenant.id, product.id)
    after = await rules.publish_amounts_for_binding(db_session, ozon, [product])
    assert view.by_binding[ozon.id].mode == "percent"
    assert view.by_binding[ozon.id].value == 40
    assert view.by_binding[ozon.id].published_now == 20
    assert after == before


@pytest.mark.asyncio
async def test_ozon_transport_stays_off_without_applicable_product(
    db_session: AsyncSession,
) -> None:
    """D3: a WB-only product cannot turn on the Ozon binding transport."""
    case = await _seed_case(db_session)
    _wb, ozon = case.bindings
    product = case.products[0]
    links = list(
        await db_session.scalars(
            select(ProductMarketplaceLink).where(
                ProductMarketplaceLink.product_id == product.id
            )
        )
    )
    for link in links:
        await db_session.delete(link)
    ozon.stock_sync_enabled = False
    await db_session.commit()

    await rules.set_rule_for_products(
        db_session,
        case.tenant.id,
        [product.id],
        rules.FbsRule(
            publish=None,
            same_everywhere=False,
            percent=0,
            by_binding={
                ozon.id: rules.FbsBindingRule(
                    publish=True,
                    mode="percent",
                    value=50,
                )
            },
        ),
    )

    await db_session.refresh(ozon)
    view = await rules.get_rule_view(db_session, case.tenant.id, product.id)
    assert view.by_binding[ozon.id].applicable is False
    assert view.by_binding[ozon.id].publish is False
    assert ozon.stock_sync_enabled is False


@pytest.mark.asyncio
async def test_explicit_empty_by_binding_payload_changes_nothing(
    db_session: AsyncSession,
) -> None:
    """F1: `by_binding: {}` is the new form with no visible edits, not legacy reset."""
    case = await _seed_case(db_session)
    product = case.products[0]
    initial = rules.FbsRule(
        publish=None,
        same_everywhere=False,
        percent=0,
        by_binding={
            binding.id: rules.FbsBindingRule(
                publish=True,
                mode="percent",
                value=value,
            )
            for binding, value in zip(case.bindings, (35, 65), strict=True)
        },
    )
    await rules.set_rule_for_products(
        db_session,
        case.tenant.id,
        [product.id],
        initial,
    )
    before = await rules.get_rule_view(db_session, case.tenant.id, product.id)

    parsed = _rule_from_body(ProductFbsRuleBody.model_validate({"by_binding": {}}))
    assert parsed.by_binding_present is True
    result = await rules.set_rule_for_products(
        db_session,
        case.tenant.id,
        [product.id],
        parsed,
    )
    after = await rules.get_rule_view(db_session, case.tenant.id, product.id)

    assert result.updated_count == 0
    assert {
        binding.id: (
            after.by_binding[binding.id].publish,
            after.by_binding[binding.id].mode,
            after.by_binding[binding.id].value,
        )
        for binding in case.bindings
    } == {
        binding.id: (
            before.by_binding[binding.id].publish,
            before.by_binding[binding.id].mode,
            before.by_binding[binding.id].value,
        )
        for binding in case.bindings
    }


@pytest.mark.asyncio
async def test_c31_off_on_preserves_manual_cap_after_stock_drop(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """C31/R8/R14: stock changes affect min(), never the saved operator cap."""
    case = await _seed_case(db_session)
    binding = case.bindings[0]
    product = case.products[0]
    initial = rules.FbsRule(
        publish=None,
        same_everywhere=False,
        percent=0,
        by_binding={
            binding.id: rules.FbsBindingRule(
                publish=True,
                mode="units",
                value=50,
            )
        },
    )
    await rules.set_rule_for_products(
        db_session,
        case.tenant.id,
        [product.id],
        initial,
    )
    balance = await db_session.scalar(
        select(InventoryBalance).where(InventoryBalance.product_id == product.id)
    )
    assert balance is not None
    balance.quantity = 10
    balance.quantity_unpacked = 10
    await db_session.commit()

    zeroed: list[uuid.UUID] = []

    async def clear(
        _session: AsyncSession,
        selected_binding: FbsWarehouseBinding,
        _product_ids: set[uuid.UUID],
    ) -> None:
        zeroed.append(selected_binding.id)

    monkeypatch.setattr(rules, "_clear_product_publication", clear)
    for publish in (False, False, True):
        await rules.set_rule_for_products(
            db_session,
            case.tenant.id,
            [product.id],
            rules.FbsRule(
                publish=None,
                same_everywhere=False,
                percent=0,
                by_binding={
                    binding.id: rules.FbsBindingRule(
                        publish=publish,
                        mode="units",
                        value=50,
                    )
                },
            ),
        )

    view = await rules.get_rule_view(db_session, case.tenant.id, product.id)
    assert zeroed == [binding.id]
    assert view.by_binding[binding.id].value == 50
    assert view.by_binding[binding.id].published_now == 10


@pytest.mark.asyncio
@pytest.mark.postgresql_concurrency
async def test_c24_parallel_complete_saves_never_mix_rules(
    db_session: AsyncSession,
) -> None:
    """C24: Product row locks make the final state one whole request."""
    if engine.dialect.name != "postgresql":
        pytest.skip("Real PostgreSQL row locking required")
    case = await _seed_case(db_session)
    product_ids = [product.id for product in case.products]
    wb, ozon = case.bindings

    async def save(wb_value: int, ozon_value: int) -> None:
        async with SessionLocal() as session:
            await rules.set_rule_for_products(
                session,
                case.tenant.id,
                product_ids,
                rules.FbsRule(
                    publish=None,
                    same_everywhere=False,
                    percent=0,
                    by_binding={
                        wb.id: rules.FbsBindingRule(
                            publish=True, mode="percent", value=wb_value
                        ),
                        ozon.id: rules.FbsBindingRule(
                            publish=True, mode="percent", value=ozon_value
                        ),
                    },
                ),
            )

    await asyncio.gather(save(25, 75), save(60, 40))
    async with SessionLocal() as session:
        view = await rules.get_rule_view(session, case.tenant.id, case.products[0].id)
    pair = (view.by_binding[wb.id].value, view.by_binding[ozon.id].value)
    assert pair in {(25, 75), (60, 40)}


@pytest.mark.asyncio
@pytest.mark.postgresql_concurrency
async def test_c23_parallel_same_binding_create_keeps_one_row(
    db_session: AsyncSession,
) -> None:
    """C23/R22: concurrent replay of a new binding returns one unique row."""
    if engine.dialect.name != "postgresql":
        pytest.skip("Real PostgreSQL unique-conflict serialization required")
    case = await _seed_case(db_session)

    async def create() -> uuid.UUID:
        async with SessionLocal() as session:
            row = await bindings_service.configure_seller_warehouse(
                session,
                case.tenant.id,
                case.seller.id,
                501002,
                served=True,
                wms_warehouse_id=case.warehouse.id,
                stock_sync_enabled=False,
            )
            assert row is not None
            return row.id

    first_id, second_id = await asyncio.gather(create(), create())
    assert first_id == second_id
    async with SessionLocal() as session:
        count = await session.scalar(
            select(func.count())
            .select_from(FbsWarehouseBinding)
            .where(
                FbsWarehouseBinding.tenant_id == case.tenant.id,
                FbsWarehouseBinding.seller_id == case.seller.id,
                FbsWarehouseBinding.marketplace == "wb",
                FbsWarehouseBinding.wb_warehouse_id == 501002,
            )
        )
    assert count == 1


@pytest.mark.asyncio
async def test_c16_r20_event_publish_starts_within_five_and_confirms_within_ten_seconds(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """C16/R20: a committed stock movement runs real calculation and provider paths."""
    case = await _seed_case(db_session)
    wb, ozon = case.bindings
    product = case.products[0]
    product.wb_chrt_id = 469001
    db_session.add_all(
        [
            SellerWildberriesCredentials(
                seller_id=case.seller.id,
                marketplace_token_encrypted=encrypt_secret("wms469-wb-token"),
            ),
            MarketplaceAccount(
                tenant_id=case.tenant.id,
                seller_id=case.seller.id,
                marketplace="ozon",
                account_slot="primary",
                external_account_id="wms469-ozon-client",
                secret_encrypted=encrypt_secret("wms469-ozon-key"),
                is_active=True,
                validation_status="valid",
            ),
        ]
    )
    await db_session.commit()
    await rules.set_rule_for_products(
        db_session,
        case.tenant.id,
        [product.id],
        rules.FbsRule(
            publish=None,
            same_everywhere=False,
            percent=0,
            by_binding={
                wb.id: rules.FbsBindingRule(
                    publish=True,
                    mode="percent",
                    value=100,
                ),
                ozon.id: rules.FbsBindingRule(
                    publish=True,
                    mode="percent",
                    value=100,
                ),
            },
        ),
    )

    starts: dict[str, float] = {}
    confirmations: dict[str, float] = {}
    wb_batch: list[Any] = []

    from app.services import fbs_autopoll_service, fbs_stock_sync_service

    async def put_wb_batch(
        _client: Any,
        **kwargs: Any,
    ) -> Any:
        starts.setdefault("wb", time.monotonic())
        wb_batch[:] = list(kwargs["batch"])
        return fbs_stock_sync_service._PutBatchOutcome(
            error_code=None,
            status_code=None,
            retry_after_seconds=None,
        )

    async def read_wb_batch(*_args: Any, **_kwargs: Any) -> list[Any]:
        confirmations["wb"] = time.monotonic()
        return list(wb_batch)

    class TimedOzonTransport(FakeMarketplaceTransport):
        async def publish_stocks(
            self,
            *,
            client_id: str,
            api_key: str,
            stocks: Any,
        ) -> int:
            starts.setdefault("ozon", time.monotonic())
            confirmed = await super().publish_stocks(
                client_id=client_id,
                api_key=api_key,
                stocks=stocks,
            )
            confirmations["ozon"] = time.monotonic()
            return confirmed

    ozon_transport = TimedOzonTransport()
    monkeypatch.setattr(fbs_stock_sync_service, "_put_stocks_batch", put_wb_batch)
    monkeypatch.setattr(
        fbs_stock_sync_service,
        "fetch_marketplace_stocks",
        read_wb_batch,
    )
    monkeypatch.setattr(
        fbs_autopoll_service,
        "_blocked_ozon_provider",
        lambda _operation: OzonMarketplaceProvider(transport=ozon_transport),
    )

    balance = await db_session.scalar(
        select(InventoryBalance).where(InventoryBalance.product_id == product.id)
    )
    assert balance is not None
    await inventory_service.record_movement_and_adjust_balance(
        db_session,
        tenant_id=case.tenant.id,
        product_id=product.id,
        storage_location_id=balance.storage_location_id,
        quantity_delta=-1,
        movement_type="wms469_event_test",
        actor_user_id=None,
    )
    await db_session.commit()
    committed_at = time.monotonic()
    await publish_service.drain_background_stock_publish_tasks()

    assert set(starts) == {"wb", "ozon"}
    assert all(start - committed_at <= 5 for start in starts.values())
    assert all(confirmed - committed_at <= 10 for confirmed in confirmations.values())
    assert [(item.chrt_id, item.amount) for item in wb_batch] == [(469001, 49)]
    assert [stock["stock"] for stock in ozon_transport.published_stocks] == [49]


@pytest.mark.asyncio
async def test_c13_unserved_binding_remains_a_publication_target(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """C13/R7: served controls orders only and cannot suppress stock events."""
    case = await _seed_case(db_session)
    for binding in case.bindings:
        binding.served = False
    await db_session.commit()
    calls: list[str] = []

    async def no_account_targets(_session: AsyncSession) -> list[SellerPollTarget]:
        return []

    async def sync(_session: AsyncSession, target: SellerPollTarget, _client: Any) -> Any:
        calls.append(target.marketplace)
        return SimpleNamespace(
            bindings_processed=1,
            products_targeted=1,
            products_confirmed=1,
            errors=0,
            binding_errors=0,
        )

    from app.services import fbs_autopoll_service

    monkeypatch.setattr(
        fbs_autopoll_service,
        "list_marketplace_poll_targets",
        no_account_targets,
    )
    monkeypatch.setattr(fbs_autopoll_service, "sync_marketplace_stocks_for_target", sync)

    await publish_service.publish_seller_stocks_now(case.tenant.id, case.seller.id)
    assert sorted(calls) == ["ozon", "wb"]


@pytest.mark.asyncio
async def test_c20_c21_busy_provider_retries_while_other_provider_proceeds(
    monkeypatch: pytest.MonkeyPatch,
    db_session: AsyncSession,
) -> None:
    """C20/C21: a busy WB lock is retried and does not suppress Ozon."""
    tenant_id, seller_id = uuid.uuid4(), uuid.uuid4()
    attempts = {"wb": 0, "ozon": 0}
    calls: list[str] = []

    async def targets(_session: AsyncSession) -> list[SellerPollTarget]:
        return [
            SellerPollTarget(tenant_id, seller_id, "wb"),
            SellerPollTarget(tenant_id, seller_id, "ozon"),
        ]

    @asynccontextmanager
    async def lock(
        _session: AsyncSession,
        _seller_id: uuid.UUID,
        marketplace: str,
        **_kwargs: Any,
    ) -> AsyncIterator[bool]:
        if marketplace.endswith(":event-follow-up"):
            yield True
            return
        attempts[marketplace] += 1
        yield marketplace == "ozon" or attempts[marketplace] > 1

    async def sync(_session: AsyncSession, target: SellerPollTarget, _client: Any) -> Any:
        calls.append(target.marketplace)
        incomplete = target.marketplace == "ozon" and calls.count("ozon") == 1
        return SimpleNamespace(
            bindings_processed=1,
            products_targeted=1,
            products_confirmed=0 if incomplete else 1,
            errors=1 if incomplete else 0,
            binding_errors=1 if incomplete else 0,
            retryable_errors=1 if incomplete else 0,
            retry_after_seconds=0,
        )

    async def no_delay(_seconds: float) -> None:
        return None

    from app.services import fbs_autopoll_service

    monkeypatch.setattr(fbs_autopoll_service, "list_marketplace_poll_targets", targets)
    monkeypatch.setattr(fbs_autopoll_service, "sync_marketplace_stocks_for_target", sync)
    monkeypatch.setattr(publish_service, "marketplace_seller_lock", lock)
    monkeypatch.setattr(publish_service.asyncio, "sleep", no_delay)

    await publish_service.publish_seller_stocks_now(tenant_id, seller_id)
    assert attempts == {"wb": 2, "ozon": 2}
    assert calls[0] == "ozon"
    assert calls.count("ozon") == 2
    assert calls.count("wb") == 1


@pytest.mark.asyncio
async def test_busy_provider_stops_after_bounded_attempts(
    monkeypatch: pytest.MonkeyPatch,
    db_session: AsyncSession,
) -> None:
    """B2: a permanently busy provider lock cannot keep a worker forever."""
    tenant_id, seller_id = uuid.uuid4(), uuid.uuid4()
    attempts = 0
    wait_timeouts: list[float] = []
    sync_calls = 0

    async def targets(_session: AsyncSession) -> list[SellerPollTarget]:
        return [SellerPollTarget(tenant_id, seller_id, "wb")]

    @asynccontextmanager
    async def always_busy(
        _session: AsyncSession,
        _seller_id: uuid.UUID,
        marketplace: str,
        **_kwargs: Any,
    ) -> AsyncIterator[bool]:
        nonlocal attempts
        if marketplace.endswith(":event-follow-up"):
            yield True
            return
        attempts += 1
        wait_timeouts.append(float(_kwargs["wait_timeout_sec"]))
        yield False

    async def sync(*_args: Any, **_kwargs: Any) -> Any:
        nonlocal sync_calls
        sync_calls += 1
        return SimpleNamespace()

    async def no_delay(_seconds: float) -> None:
        return None

    from app.services import fbs_autopoll_service

    monkeypatch.setattr(fbs_autopoll_service, "list_marketplace_poll_targets", targets)
    monkeypatch.setattr(fbs_autopoll_service, "sync_marketplace_stocks_for_target", sync)
    monkeypatch.setattr(publish_service, "marketplace_seller_lock", always_busy)
    monkeypatch.setattr(publish_service.asyncio, "sleep", no_delay)

    await asyncio.wait_for(
        publish_service.publish_seller_stocks_now(tenant_id, seller_id),
        timeout=5,
    )
    assert attempts == 2
    assert wait_timeouts == [0, publish_service._EVENT_FOLLOW_UP_WAIT_SECONDS]
    assert sync_calls == 0


@pytest.mark.asyncio
async def test_five_events_coalesce_into_one_follow_up_publish(
    monkeypatch: pytest.MonkeyPatch,
    db_session: AsyncSession,
) -> None:
    """B2: an event burst causes one active pass and at most one fresh pass."""
    tenant_id, seller_id = uuid.uuid4(), uuid.uuid4()
    first_pass_started = asyncio.Event()
    release_first_pass = asyncio.Event()
    calls = 0

    async def targets(_session: AsyncSession) -> list[SellerPollTarget]:
        return [SellerPollTarget(tenant_id, seller_id, "wb")]

    async def sync(_session: AsyncSession, _target: SellerPollTarget, _client: Any) -> Any:
        nonlocal calls
        calls += 1
        if calls == 1:
            first_pass_started.set()
            await release_first_pass.wait()
        return SimpleNamespace(
            bindings_processed=1,
            products_targeted=1,
            products_confirmed=1,
            errors=0,
            binding_errors=0,
            retryable_errors=0,
        )

    from app.services import fbs_autopoll_service

    monkeypatch.setattr(fbs_autopoll_service, "list_marketplace_poll_targets", targets)
    monkeypatch.setattr(fbs_autopoll_service, "sync_marketplace_stocks_for_target", sync)

    first = asyncio.create_task(
        publish_service.publish_seller_stocks_now(tenant_id, seller_id)
    )
    await first_pass_started.wait()
    piled_up = [
        asyncio.create_task(
            publish_service.publish_seller_stocks_now(tenant_id, seller_id)
        )
        for _ in range(4)
    ]
    await asyncio.sleep(0)
    release_first_pass.set()
    await asyncio.gather(first, *piled_up)

    assert calls == 2


@pytest.mark.asyncio
async def test_event_during_follow_up_pass_gets_its_own_publish(
    monkeypatch: pytest.MonkeyPatch,
    db_session: AsyncSession,
) -> None:
    """D1: an event during the rerun is not dropped by an arbitrary two-pass cap."""
    tenant_id, seller_id = uuid.uuid4(), uuid.uuid4()
    gates = [asyncio.Event() for _ in range(3)]
    started = [asyncio.Event() for _ in range(3)]
    calls = 0

    async def targets(_session: AsyncSession) -> list[SellerPollTarget]:
        return [SellerPollTarget(tenant_id, seller_id, "wb")]

    async def sync(_session: AsyncSession, _target: SellerPollTarget, _client: Any) -> Any:
        nonlocal calls
        call_index = calls
        calls += 1
        started[call_index].set()
        await gates[call_index].wait()
        return SimpleNamespace(
            bindings_processed=1,
            products_targeted=1,
            products_confirmed=1,
            errors=0,
            binding_errors=0,
            retryable_errors=0,
        )

    from app.services import fbs_autopoll_service

    monkeypatch.setattr(fbs_autopoll_service, "list_marketplace_poll_targets", targets)
    monkeypatch.setattr(fbs_autopoll_service, "sync_marketplace_stocks_for_target", sync)

    first_event = asyncio.create_task(
        publish_service.publish_seller_stocks_now(tenant_id, seller_id)
    )
    await started[0].wait()
    second_event = asyncio.create_task(
        publish_service.publish_seller_stocks_now(tenant_id, seller_id)
    )
    await asyncio.sleep(0)
    gates[0].set()
    await started[1].wait()
    third_event = asyncio.create_task(
        publish_service.publish_seller_stocks_now(tenant_id, seller_id)
    )
    await asyncio.sleep(0)
    gates[1].set()
    await started[2].wait()
    gates[2].set()

    await asyncio.wait_for(
        asyncio.gather(first_event, second_event, third_event),
        timeout=5,
    )
    assert calls == 3


@pytest.mark.asyncio
@pytest.mark.postgresql_concurrency
async def test_cross_process_follow_up_waits_for_long_running_lock_holder(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """D1: the one cross-process follow-up survives a holder longer than one poll."""
    if engine.dialect.name != "postgresql":
        pytest.skip("Real PostgreSQL advisory locks required")
    tenant_id, seller_id = uuid.uuid4(), uuid.uuid4()
    calls: list[float] = []
    started_at = time.monotonic()

    async def targets(_session: AsyncSession) -> list[SellerPollTarget]:
        return [SellerPollTarget(tenant_id, seller_id, "wb")]

    async def sync(_session: AsyncSession, _target: SellerPollTarget, _client: Any) -> Any:
        calls.append(time.monotonic() - started_at)
        if len(calls) == 1:
            await asyncio.sleep(6)
        return SimpleNamespace(
            bindings_processed=1,
            products_targeted=1,
            products_confirmed=1,
            errors=0,
            binding_errors=0,
            retryable_errors=0,
        )

    from app.services import fbs_autopoll_service

    monkeypatch.setattr(fbs_autopoll_service, "list_marketplace_poll_targets", targets)
    monkeypatch.setattr(fbs_autopoll_service, "sync_marketplace_stocks_for_target", sync)

    active_publisher = asyncio.create_task(
        publish_service._publish_seller_stocks_pass(tenant_id, seller_id)
    )
    await asyncio.sleep(0.5)
    follow_up = asyncio.create_task(
        publish_service._publish_seller_stocks_pass(tenant_id, seller_id)
    )
    await asyncio.gather(active_publisher, follow_up)

    assert len(calls) == 2
    assert calls[1] >= 5.5


@pytest.mark.asyncio
async def test_permanent_publish_error_is_not_retried(
    monkeypatch: pytest.MonkeyPatch,
    db_session: AsyncSession,
) -> None:
    """B2: 401/404/conflict/mapping failures remain a single full pass."""
    tenant_id, seller_id = uuid.uuid4(), uuid.uuid4()
    calls = 0

    async def targets(_session: AsyncSession) -> list[SellerPollTarget]:
        return [SellerPollTarget(tenant_id, seller_id, "ozon")]

    async def sync(*_args: Any, **_kwargs: Any) -> Any:
        nonlocal calls
        calls += 1
        return SimpleNamespace(
            bindings_processed=1,
            products_targeted=1,
            products_confirmed=0,
            errors=1,
            binding_errors=1,
            retryable_errors=0,
        )

    from app.services import fbs_autopoll_service

    monkeypatch.setattr(fbs_autopoll_service, "list_marketplace_poll_targets", targets)
    monkeypatch.setattr(fbs_autopoll_service, "sync_marketplace_stocks_for_target", sync)

    await publish_service.publish_seller_stocks_now(tenant_id, seller_id)
    assert calls == 1


@pytest.mark.asyncio
async def test_rate_limit_retry_respects_provider_backoff(
    monkeypatch: pytest.MonkeyPatch,
    db_session: AsyncSession,
) -> None:
    """B2: a retryable 429 waits for Retry-After before the second full pass."""
    tenant_id, seller_id = uuid.uuid4(), uuid.uuid4()
    calls = 0
    sleeps: list[float] = []
    recorded: list[float] = []

    async def targets(_session: AsyncSession) -> list[SellerPollTarget]:
        return [SellerPollTarget(tenant_id, seller_id, "ozon")]

    async def sync(*_args: Any, **_kwargs: Any) -> Any:
        nonlocal calls
        calls += 1
        retryable = calls == 1
        return SimpleNamespace(
            bindings_processed=1,
            products_targeted=1,
            products_confirmed=0 if retryable else 1,
            errors=1 if retryable else 0,
            binding_errors=1 if retryable else 0,
            retryable_errors=1 if retryable else 0,
            retry_after_seconds=7 if retryable else 0,
        )

    class Backoff:
        def remaining_seconds(self, _marketplace: str) -> float:
            return 0.0

        def record_rate_limit(
            self,
            _marketplace: str,
            *,
            retry_after_seconds: float,
        ) -> None:
            recorded.append(retry_after_seconds)

    async def record_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    from app.services import fbs_autopoll_service

    monkeypatch.setattr(fbs_autopoll_service, "list_marketplace_poll_targets", targets)
    monkeypatch.setattr(fbs_autopoll_service, "sync_marketplace_stocks_for_target", sync)
    monkeypatch.setattr(fbs_autopoll_service, "_MARKETPLACE_BACKOFF", Backoff())
    monkeypatch.setattr(publish_service.asyncio, "sleep", record_sleep)

    await publish_service.publish_seller_stocks_now(tenant_id, seller_id)
    assert calls == 2
    assert recorded == [7]
    assert sleeps == [7]


@pytest.mark.asyncio
async def test_c26_seller_reads_own_bindings_but_cannot_write_them(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """C26: products permission grants scoped reads, never binding writes."""
    admin_headers, suffix = await _register_tenant(async_client, "WMS469Scope")
    seller_id = await _create_seller(async_client, admin_headers, name="Scoped seller")
    product_id = await _create_product(
        async_client,
        admin_headers,
        seller_id=seller_id,
        suffix=suffix,
    )
    warehouse = await async_client.post(
        "/warehouses",
        headers=admin_headers,
        json={"name": "Scoped WH", "code": f"scope-{uuid.uuid4().hex[:8]}"},
    )
    assert warehouse.status_code in (200, 201), warehouse.text
    created = await async_client.put(
        f"/operations/fbs-sellers/{seller_id}/warehouse-bindings/501001",
        headers=admin_headers,
        json={
            "wms_warehouse_id": warehouse.json()["id"],
            "stock_sync_enabled": True,
        },
    )
    assert created.status_code == 200, created.text
    repeated = await async_client.put(
        f"/operations/fbs-sellers/{seller_id}/warehouse-bindings/501001",
        headers=admin_headers,
        json={
            "wms_warehouse_id": warehouse.json()["id"],
            "stock_sync_enabled": True,
        },
    )
    assert repeated.status_code == 200, repeated.text
    assert repeated.json()["id"] == created.json()["id"]
    seller_headers = await _seller_headers(
        async_client,
        admin_headers,
        seller_id=seller_id,
        suffix=suffix,
    )

    listed = await async_client.get(
        f"/operations/fbs-sellers/{seller_id}/warehouse-bindings",
        headers=seller_headers,
    )
    assert listed.status_code == 200, listed.text
    assert listed.json()[0]["wms_warehouse_name"] == "Scoped WH"
    assert listed.json()[0]["editable"] is False

    async def wb_directory(*_args: Any, **_kwargs: Any) -> list[dict[str, Any]]:
        return [
            {
                "wb_warehouse_id": 501001,
                "served": True,
                "wms_warehouse_id": warehouse.json()["id"],
                "id": 501001,
                "name": "Склад WB из кабинета",
            }
        ]

    async def ozon_directory(*_args: Any, **_kwargs: Any) -> list[dict[str, Any]]:
        return [
            {
                "warehouse_id": 1020005028840530,
                "name": "Склад Ozon из кабинета",
                "has_entrusted_acceptance": False,
                "is_rfbs": False,
                "served": False,
                "wms_warehouse_id": None,
            }
        ]

    from app.api import fbs_sellers

    monkeypatch.setattr(fbs_sellers.wh_svc, "list_seller_warehouses", wb_directory)
    monkeypatch.setattr(fbs_sellers.wh_svc, "list_ozon_seller_warehouses", ozon_directory)
    wb_list = await async_client.get(
        f"/operations/fbs-sellers/{seller_id}/warehouses",
        headers=seller_headers,
    )
    ozon_list = await async_client.get(
        f"/operations/fbs-sellers/{seller_id}/ozon-warehouses",
        headers=seller_headers,
    )
    assert wb_list.status_code == 200, wb_list.text
    assert wb_list.json()[0]["name"] == "Склад WB из кабинета"
    assert ozon_list.status_code == 200, ozon_list.text
    assert ozon_list.json()[0]["name"] == "Склад Ozon из кабинета"

    binding_id = listed.json()[0]["id"]
    saved_rule = await async_client.put(
        "/products/fbs-rule",
        headers=seller_headers,
        json={
            "product_ids": [product_id],
            "rule": {
                "by_binding": {
                    binding_id: {"publish": True, "mode": "percent", "value": 50}
                }
            },
        },
    )
    assert saved_rule.status_code == 200, saved_rule.text

    denied = await async_client.put(
        f"/operations/fbs-sellers/{seller_id}/warehouse-bindings/501001",
        headers=seller_headers,
        json={
            "wms_warehouse_id": warehouse.json()["id"],
            "stock_sync_enabled": False,
        },
    )
    assert denied.status_code == 403


@pytest.mark.asyncio
async def test_c25_foreign_seller_and_tenant_cannot_read_any_warehouse_endpoint(
    async_client: AsyncClient,
) -> None:
    """C25: all three dialog reads keep seller and tenant boundaries."""
    admin_a, suffix_a = await _register_tenant(async_client, "WMS469ScopeA")
    seller_a = await _create_seller(async_client, admin_a, name="Seller A")
    seller_b = await _create_seller(async_client, admin_a, name="Seller B")
    seller_b_headers = await _seller_headers(
        async_client,
        admin_a,
        seller_id=seller_b,
        suffix=f"{suffix_a}-b",
    )

    admin_c, suffix_c = await _register_tenant(async_client, "WMS469ScopeC")
    seller_c = await _create_seller(async_client, admin_c, name="Seller C")
    seller_c_headers = await _seller_headers(
        async_client,
        admin_c,
        seller_id=seller_c,
        suffix=f"{suffix_c}-c",
    )

    for path in ("warehouse-bindings", "warehouses", "ozon-warehouses"):
        foreign_seller = await async_client.get(
            f"/operations/fbs-sellers/{seller_a}/{path}",
            headers=seller_b_headers,
        )
        assert foreign_seller.status_code == 403, (path, foreign_seller.text)

        foreign_tenant_seller = await async_client.get(
            f"/operations/fbs-sellers/{seller_a}/{path}",
            headers=seller_c_headers,
        )
        assert foreign_tenant_seller.status_code in (403, 404), (
            path,
            foreign_tenant_seller.text,
        )

        foreign_tenant_admin = await async_client.get(
            f"/operations/fbs-sellers/{seller_a}/{path}",
            headers=admin_c,
        )
        assert foreign_tenant_admin.status_code in (403, 404), (
            path,
            foreign_tenant_admin.text,
        )


@pytest.mark.asyncio
async def test_c8_http_bulk_save_returns_saved_clamp_and_binding_state(
    async_client: AsyncClient,
) -> None:
    """C8: the frontend receives the saved value and limiting product name."""
    headers, suffix = await _register_tenant(async_client, "WMS469HTTP")
    seller_id = await _create_seller(async_client, headers, name="HTTP seller")
    first_id = await _create_product(
        async_client, headers, seller_id=seller_id, suffix=f"{suffix}-first"
    )
    second_id = await _create_product(
        async_client, headers, seller_id=seller_id, suffix=f"{suffix}-second"
    )
    warehouse = await async_client.post(
        "/warehouses",
        headers=headers,
        json={"name": "HTTP WH", "code": f"http-{uuid.uuid4().hex[:8]}"},
    )
    assert warehouse.status_code in (200, 201), warehouse.text
    warehouse_id = uuid.UUID(warehouse.json()["id"])
    binding_response = await async_client.put(
        f"/operations/fbs-sellers/{seller_id}/warehouse-bindings/501001",
        headers=headers,
        json={"wms_warehouse_id": str(warehouse_id), "stock_sync_enabled": True},
    )
    assert binding_response.status_code == 200, binding_response.text
    binding_id = binding_response.json()["id"]

    async with SessionLocal() as session:
        first = await session.get(Product, uuid.UUID(first_id))
        second = await session.get(Product, uuid.UUID(second_id))
        assert first is not None and second is not None
        first.name = "Первый товар"
        second.name = "Товар-ограничитель API"
        location = StorageLocation(
            tenant_id=first.tenant_id,
            warehouse_id=warehouse_id,
            code=f"HTTP-{uuid.uuid4().hex[:6]}",
            barcode=f"HTTP-BC-{uuid.uuid4().hex[:8]}",
        )
        session.add(location)
        await session.flush()
        session.add_all(
            [
                InventoryBalance(
                    tenant_id=first.tenant_id,
                    storage_location_id=location.id,
                    product_id=first.id,
                    quantity=8,
                    quantity_unpacked=8,
                ),
                InventoryBalance(
                    tenant_id=second.tenant_id,
                    storage_location_id=location.id,
                    product_id=second.id,
                    quantity=3,
                    quantity_unpacked=3,
                ),
            ]
        )
        await session.commit()

    saved = await async_client.put(
        "/products/fbs-rule",
        headers=headers,
        json={
            "product_ids": [first_id, second_id],
            "rule": {
                "by_binding": {
                    binding_id: {"publish": True, "mode": "units", "value": 8}
                }
            },
        },
    )
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["updated_count"] == 2
    assert body["clamps"][binding_id] == {
        "requested_value": 8,
        "saved_value": 3,
        "limiting_product_id": second_id,
        "limiting_product_name": "Товар-ограничитель API",
    }
    assert [item["by_binding"][binding_id]["value"] for item in body["items"]] == [3, 3]
