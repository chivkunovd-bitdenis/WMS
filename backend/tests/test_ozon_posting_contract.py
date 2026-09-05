"""Разбор отправления Ozon: форму задаёт спецификация, а не тестовая фикстура.

Контракт приёма заказов Ozon раньше был задан выдуманной плоской строкой в
тесте: `{"posting_number": ..., "warehouse_id": ..., "created_at": ...}`. Такой
формы Ozon не возвращает никогда. Здесь строки собраны по схеме
`posting.v4.PostingFbsUnfulfilledListResponse.Postings` из официальной
спецификации в репозитории, а словарь статусов — по описанию поля `status`
там же и в `v3FbsPostingDetail`.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.billing import BillingLedgerEntry
from app.models.fbs_order import (
    FBS_ORDER_STATUS_ASSEMBLING,
    FBS_ORDER_STATUS_DONE,
    FBS_ORDER_STATUS_EXTERNAL_PROCESSING,
    FBS_ORDER_STATUS_NEW,
    RESERVE_STATUS_WAREHOUSE_UNMAPPED,
    FbsOrder,
)
from app.models.fbs_warehouse_binding import FbsWarehouseBinding
from app.models.marketplace_account import MarketplaceAccount
from app.models.product import Product
from app.models.product_marketplace_link import ProductMarketplaceLink
from app.models.seller import Seller
from app.models.tenant import Tenant
from app.models.warehouse import Warehouse
from app.services import fbs_warehouse_binding_service as binding_svc
from app.services import ozon_fbs_marking_gate_service as gate_svc
from app.services import ozon_fbs_sync_service as sync_svc
from app.services.marketplace_provider import FakeMarketplaceTransport, OzonMarketplaceProvider
from app.services.wildberries_credentials_service import encrypt_secret

OZON_WAREHOUSE_ID = 1020005028840530  # живой склад кабинета, /v2/warehouse/list
POSTING_NUMBER = "0195832-0021-1"


def posting_row(
    *,
    status: str = "awaiting_packaging",
    substatus: str | None = None,
    requirements: dict[str, Any] | None = None,
    sku: int = 5680762790,
) -> dict[str, Any]:
    """Строка отправления в той форме, в которой её действительно отдаёт Ozon."""
    row: dict[str, Any] = {
        "posting_number": POSTING_NUMBER,
        "order_id": 123456789,
        "order_number": "0195832-0021",
        "status": status,
        "in_process_at": "2026-09-01T10:30:00Z",
        "shipment_date": "2026-09-04T10:30:00Z",
        "delivery_method": {
            "id": 21321684811000,
            "name": "Ozon Логистика самостоятельно, Москва",
            "warehouse_id": OZON_WAREHOUSE_ID,
            "warehouse": "мой склад",
        },
        "barcodes": {"lower_barcode": "%303%3435", "upper_barcode": "10221545"},
        "products": [
            {
                "sku": sku,
                "offer_id": "OZ862006269",
                "name": "Очки солнцезащитные",
                "quantity": 2,
                "price": {"amount": "1250.00", "currency": "RUB"},
                "weight": 100,
            }
        ],
        "financial_data": {
            "products": [
                {"product_id": sku, "price": 1250.0, "quantity": 2},
            ]
        },
    }
    if substatus is not None:
        row["substatus"] = substatus
    if requirements is not None:
        row["requirements"] = requirements
    return row


async def _seed(db_session: AsyncSession, *, with_binding: bool = True) -> SimpleNamespace:
    tenant = Tenant(name="Ozon contract", slug=f"ozon-contract-{uuid.uuid4().hex[:8]}")
    seller = Seller(tenant=tenant, name="Seller")
    warehouse = Warehouse(tenant=tenant, name="FBS", code=f"ozon-contract-{uuid.uuid4().hex[:8]}")
    product = Product(
        tenant=tenant,
        seller=seller,
        name="Очки",
        sku_code=f"sku-{uuid.uuid4().hex[:8]}",
        # WMS-352: заказ Ozon импортируется только там, где мы публикуем остаток.
        fbs_stock_sync_enabled=True,
    )
    db_session.add_all([tenant, seller, warehouse, product])
    await db_session.flush()
    db_session.add_all(
        [
            MarketplaceAccount(
                tenant_id=tenant.id,
                seller_id=seller.id,
                marketplace="ozon",
                account_slot="primary",
                external_account_id="client-id",
                secret_encrypted=encrypt_secret("api-key"),
                is_active=True,
                validation_status="valid",
            ),
            ProductMarketplaceLink(
                tenant_id=tenant.id,
                seller_id=seller.id,
                product_id=product.id,
                marketplace="ozon",
                external_sku="5680762790",
                external_product_id="6204279711",
                external_offer_id="OZ862006269",
            ),
        ]
    )
    if with_binding:
        db_session.add(
            FbsWarehouseBinding(
                tenant_id=tenant.id,
                seller_id=seller.id,
                marketplace="ozon",
                external_warehouse_id=str(OZON_WAREHOUSE_ID),
                wb_warehouse_id=-1,
                wms_warehouse_id=warehouse.id,
            )
        )
    await db_session.commit()
    return SimpleNamespace(tenant=tenant, seller=seller, warehouse=warehouse, product=product)


async def _sync(db_session: AsyncSession, ctx: SimpleNamespace, rows: list[dict[str, Any]]) -> None:
    provider = OzonMarketplaceProvider(transport=FakeMarketplaceTransport(orders=rows))
    await sync_svc.sync_ozon_orders(db_session, ctx.tenant.id, ctx.seller.id, provider, AsyncMock())


async def _order(db_session: AsyncSession) -> FbsOrder:
    return (
        await db_session.execute(
            select(FbsOrder).where(FbsOrder.external_order_id == POSTING_NUMBER)
        )
    ).scalar_one()


async def test_warehouse_is_read_from_delivery_method_not_from_the_top_level(
    db_session: AsyncSession,
) -> None:
    """Идентификатор склада Ozon кладёт в `delivery_method`, а не наверх строки.

    Пока его искали на верхнем уровне, даже правильно заведённая привязка не
    находилась и каждый заказ Ozon получал `warehouse_unmapped`.
    """
    ctx = await _seed(db_session)
    await _sync(db_session, ctx, [posting_row()])

    order = await _order(db_session)
    assert order.warehouse_id == ctx.warehouse.id
    assert order.reserve_status != RESERVE_STATUS_WAREHOUSE_UNMAPPED


async def test_binding_created_through_the_normal_path_matches_a_real_posting(
    db_session: AsyncSession,
) -> None:
    """Две половины должны сойтись: как привязку заводят и как её потом ищут.

    Привязку создаём тем же путём, что и оператор, — через сервис, а не руками
    в базе, — и проверяем, что разбор отправления её находит.

    Синхронизация остатка включена, потому что `upsert_binding` выводит из неё
    «обслуживаем этот склад», а с WMS-352 необслуживаемый склад в опрос вообще
    не попадает.
    """
    ctx = await _seed(db_session, with_binding=False)
    await binding_svc.upsert_binding(
        db_session,
        ctx.tenant.id,
        ctx.seller.id,
        OZON_WAREHOUSE_ID,
        wms_warehouse_id=ctx.warehouse.id,
        stock_sync_enabled=True,
        marketplace="ozon",
    )

    await _sync(db_session, ctx, [posting_row()])

    order = await _order(db_session)
    assert order.warehouse_id == ctx.warehouse.id
    assert order.reserve_status != RESERVE_STATUS_WAREHOUSE_UNMAPPED


async def test_posting_barcode_price_and_creation_date_come_from_the_real_fields(
    db_session: AsyncSession,
) -> None:
    ctx = await _seed(db_session)
    await _sync(db_session, ctx, [posting_row()])

    order = await _order(db_session)
    # Штрихкоды лежат в объекте `barcodes`; на верхнем уровне поля `barcode` нет.
    assert order.wb_barcode == "%303%3435"
    # Цены на верхнем уровне у отправления нет: считаем по позициям, в копейках.
    assert order.price == 250000
    # Даты создания у отправления нет — есть `in_process_at`. Раньше сюда молча
    # подставлялось «сейчас».
    assert order.created_at_wb == datetime(2026, 9, 1, 10, 30, tzinfo=UTC)
    assert order.deadline_at == datetime(2026, 9, 4, 10, 30, tzinfo=UTC)


async def test_assembled_posting_is_not_offered_to_the_operator_as_new(
    db_session: AsyncSession,
) -> None:
    """`awaiting_deliver` — это «уже собрано», а не «возьмите в работу»."""
    ctx = await _seed(db_session)
    await _sync(db_session, ctx, [posting_row(status="awaiting_deliver")])

    order = await _order(db_session)
    assert order.status == FBS_ORDER_STATUS_EXTERNAL_PROCESSING
    assert order.status != FBS_ORDER_STATUS_NEW


async def test_delivered_substatus_finishes_the_order(db_session: AsyncSession) -> None:
    """В списках Ozon доставку видно подстатусом, а не статусом `delivered`.

    Раньше мы ждали `delivered`/`done` на верхнем уровне, поэтому заказ Ozon
    не доходил до «завершён» никогда и застревал в доставке.
    """
    ctx = await _seed(db_session)
    await _sync(
        db_session,
        ctx,
        [posting_row(status="delivering", substatus="posting_delivered")],
    )

    order = await _order(db_session)
    assert order.status == FBS_ORDER_STATUS_DONE


async def test_poll_never_drags_an_order_out_of_our_own_workflow(
    db_session: AsyncSession,
) -> None:
    """Заказ, взятый в сборку, не должен возвращаться в «новые» каждым опросом."""
    ctx = await _seed(db_session)
    await _sync(db_session, ctx, [posting_row()])
    order = await _order(db_session)
    order.status = FBS_ORDER_STATUS_ASSEMBLING
    await db_session.commit()

    await _sync(db_session, ctx, [posting_row()])

    db_session.expire_all()
    order = await _order(db_session)
    assert order.status == FBS_ORDER_STATUS_ASSEMBLING


async def test_marking_requirement_arrives_from_ozon_and_opens_the_gate_honestly(
    db_session: AsyncSession,
) -> None:
    """Требование «Честного знака» приходит от Ozon и попадает в гейт выпуска.

    Раньше `required_meta_json` заполнял только вайлдберрисовский разбор, у
    заказа Ozon поле оставалось пустым, а пустое требование гейт считал
    разрешением: отправление с маркируемым товаром уезжало без единого кода.
    """
    ctx = await _seed(db_session)
    await _sync(
        db_session,
        ctx,
        [
            posting_row(
                requirements={"products_requiring_mandatory_mark": [5680762790]},
            )
        ],
    )

    order = await _order(db_session)
    assert order.required_meta_json == ["sgtin"]
    assert gate_svc.ozon_requirements_known(order) is True
    # Кодов нет — выпускать нельзя.
    assert gate_svc.compute_delivery_allowed(order, []) is False
    assert "не подтвердил" in gate_svc.delivery_message(order, [])


async def test_empty_requirements_from_ozon_mean_no_marking_needed(
    db_session: AsyncSession,
) -> None:
    ctx = await _seed(db_session)
    await _sync(db_session, ctx, [posting_row(requirements={})])

    order = await _order(db_session)
    assert order.required_meta_json == []
    assert gate_svc.compute_delivery_allowed(order, []) is True
    assert gate_svc.delivery_message(order, []) == "Ozon: маркировка не требуется."


async def test_markable_product_requires_marking_even_when_ozon_stays_silent(
    db_session: AsyncSession,
) -> None:
    """Второй источник требования — наш собственный каталог.

    Маркируемый товар маркируется независимо от того, попросил ли маркетплейс.
    Серверная проверка готовности к отгрузке смотрит только на «главный» товар
    заказа, а у Ozon отправление многотоварное — маркируемая вторая позиция
    мимо неё проезжала.
    """
    ctx = await _seed(db_session)
    ctx.product.requires_honest_sign = True
    await db_session.commit()

    await _sync(db_session, ctx, [posting_row()])

    order = await _order(db_session)
    assert order.required_meta_json == ["sgtin"]
    assert gate_svc.compute_delivery_allowed(order, []) is False


async def test_unknown_requirement_is_not_an_answer_and_never_a_permission(
    db_session: AsyncSession,
) -> None:
    """Пока требования не разобраны, «маркировка не требуется» — враньё."""
    order = FbsOrder(
        tenant_id=uuid.uuid4(),
        seller_id=uuid.uuid4(),
        marketplace="ozon",
        external_order_id=POSTING_NUMBER,
        wb_order_id=-1,
        created_at_wb=datetime.now(UTC),
        deadline_at=datetime.now(UTC) + timedelta(days=1),
    )

    assert gate_svc.ozon_requirements_known(order) is False
    assert gate_svc.compute_delivery_allowed(order, []) is False
    assert "ещё не получены" in gate_svc.delivery_message(order, [])


async def test_delivery_method_id_is_stored_for_the_future_carriage(
    db_session: AsyncSession,
) -> None:
    """Создание перевозки читает `ozon_delivery_method_id`, а писать было некому."""
    ctx = await _seed(db_session)
    await _sync(db_session, ctx, [posting_row()])

    order = await _order(db_session)
    details = order.meta_details_json or {}
    assert details["ozon_delivery_method_id"] == "21321684811000"


async def test_accepted_posting_is_charged_like_a_confirmed_wb_order(
    db_session: AsyncSession,
) -> None:
    """Заказы Ozon не тарифицировались вообще — ни сборка, ни упаковка.

    Единственная точка, где появляются деньги за сборку FBS, вызывалась только
    из вайлдберрисовского обработчика статусов. Селлер мог сдать через
    фулфилмент сотню заказов Ozon, они уезжали, и в счёт не попадало ни копейки.
    Момент начисления — подтверждение самого Ozon («идёт приёмка» в пункте
    приёма), а не наша кнопка.
    """
    ctx = await _seed(db_session)
    ctx.tenant.billing_enabled_from = date(2020, 1, 1)
    await db_session.commit()
    await _sync(db_session, ctx, [posting_row()])
    await _sync(db_session, ctx, [posting_row(status="acceptance_in_progress")])

    order = await _order(db_session)
    assert order.status == "sorted"
    charges = list(
        (
            await db_session.execute(
                select(BillingLedgerEntry).where(
                    BillingLedgerEntry.source_type == "fbs_order",
                    BillingLedgerEntry.source_id == order.id,
                )
            )
        )
        .scalars()
        .all()
    )
    assert sorted(entry.service_code for entry in charges) == ["fbs_order", "packing"]

    # Повторный проход опроса не задваивает деньги.
    await _sync(db_session, ctx, [posting_row(status="acceptance_in_progress")])
    repeated = list(
        (
            await db_session.execute(
                select(BillingLedgerEntry).where(
                    BillingLedgerEntry.source_type == "fbs_order",
                    BillingLedgerEntry.source_id == order.id,
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(repeated) == len(charges)


@pytest.mark.parametrize(
    ("status", "substatus", "expected"),
    [
        ("awaiting_packaging", None, FBS_ORDER_STATUS_NEW),
        ("acceptance_in_progress", None, "sorted"),
        ("awaiting_deliver", "posting_in_carriage", FBS_ORDER_STATUS_EXTERNAL_PROCESSING),
        ("awaiting_approve", None, FBS_ORDER_STATUS_EXTERNAL_PROCESSING),
        ("awaiting_verification", None, FBS_ORDER_STATUS_EXTERNAL_PROCESSING),
        ("delivering", None, "in_delivery"),
        ("delivering", "posting_received", FBS_ORDER_STATUS_DONE),
        ("delivered", None, FBS_ORDER_STATUS_DONE),
        ("cancelled", None, "cancelled"),
        ("cancelled_from_split_pending", None, "cancelled"),
        # Спор по доставке — не отмена: отмена развернула бы отгрузку и сняла резерв.
        ("client_arbitration", None, FBS_ORDER_STATUS_EXTERNAL_PROCESSING),
        ("arbitration", None, FBS_ORDER_STATUS_EXTERNAL_PROCESSING),
    ],
)
def test_status_dictionary_matches_the_official_list(
    status: str, substatus: str | None, expected: str
) -> None:
    assert sync_svc._local_status(status, substatus) == expected


@pytest.mark.asyncio
async def test_repeat_sync_metadata_preserves_position_and_box_assignment(
    db_session: AsyncSession,
) -> None:
    from app.models.fbs_packing_box import FbsPackingBoxItem
    from app.models.fbs_supply import FbsSupply
    from app.services import fbs_packing_box_service as box_svc

    ctx = await _seed(db_session)
    await _sync(db_session, ctx, [posting_row()])
    order = await _order(db_session)
    await db_session.refresh(order, attribute_names=["product_positions"])
    position_id = order.product_positions[0].id
    supply = FbsSupply(
        tenant_id=ctx.tenant.id,
        seller_id=ctx.seller.id,
        warehouse_id=ctx.warehouse.id,
        marketplace="ozon",
        wb_supply_id="sync-position-box",
        delivery_type="warehouse_sc",
        name="Ozon sync",
    )
    db_session.add(supply)
    await db_session.flush()
    order.supply_id = supply.id
    boxes = await box_svc.create_boxes(
        db_session,
        ctx.tenant.id,
        supply.id,
        1,
        "metadata",
        actor_user_id=None,
    )
    await box_svc.assign_orders(
        db_session,
        ctx.tenant.id,
        supply.id,
        boxes[0].id,
        [],
        actor_user_id=None,
        order_product_ids=[position_id],
    )
    await db_session.commit()

    changed = posting_row()
    changed["products"][0]["name"] = "Новое название очков"
    changed["products"][0]["weight"] = 120
    changed["products"][0]["price"] = {"amount": "1350.00", "currency": "RUB"}
    await _sync(db_session, ctx, [changed])
    await db_session.refresh(order, attribute_names=["product_positions"])
    position = order.product_positions[0]
    assert position.id == position_id
    assert position.quantity == 2
    assert position.name == "Новое название очков"
    assignment = await db_session.scalar(
        select(FbsPackingBoxItem).where(
            FbsPackingBoxItem.order_product_id == position_id,
        )
    )
    assert assignment is not None and assignment.box_id == boxes[0].id


@pytest.mark.asyncio
async def test_repeat_sync_after_assembly_preserves_original_composition(
    db_session: AsyncSession,
) -> None:
    ctx = await _seed(db_session)
    await _sync(db_session, ctx, [posting_row()])
    order = await _order(db_session)
    await db_session.refresh(order, attribute_names=["product_positions"])
    original = order.product_positions[0]
    original_id = original.id
    order.meta_details_json = {
        **(order.meta_details_json or {}),
        "ozon_assembly": {
            "posting_numbers": [POSTING_NUMBER, "0195832-0021-2"],
        },
    }
    await db_session.commit()
    split_readback = posting_row(status="awaiting_deliver")
    split_readback["products"][0]["quantity"] = 1
    await _sync(db_session, ctx, [split_readback])
    await db_session.refresh(order, attribute_names=["product_positions"])
    assert [(position.id, position.quantity) for position in order.product_positions] == [
        (original_id, 2),
    ]


def test_repeat_sync_reordered_metadata_matches_the_product_not_the_index() -> None:
    from app.models.fbs_order import FbsOrderProduct

    first = FbsOrderProduct(
        id=uuid.uuid4(), ozon_sku=1, offer_id="first", quantity=2, position_index=0, name="First"
    )
    second = FbsOrderProduct(
        id=uuid.uuid4(), ozon_sku=2, offer_id="second", quantity=3, position_index=1, name="Second"
    )
    incoming = [
        FbsOrderProduct(
            ozon_sku=2, offer_id="second", quantity=3, position_index=0, name="Second updated"
        ),
        FbsOrderProduct(
            ozon_sku=1, offer_id="first", quantity=2, position_index=1, name="First updated"
        ),
    ]
    sync_svc._update_position_metadata([first, second], incoming)
    assert (first.name, first.position_index) == ("First updated", 0)
    assert (second.name, second.position_index) == ("Second updated", 1)
