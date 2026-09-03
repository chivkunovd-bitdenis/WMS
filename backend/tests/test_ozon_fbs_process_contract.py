"""Мутации Ozon: то, что не сошлось бы со спецификацией и с живым кабинетом.

Три места, проверенные здесь, до этих правок вели себя неверно:

* экземпляры «Честного знака» уходили по одному, хотя спецификация метода
  `/v6/fbs/posting/product/exemplar/set` требует прямо: «Всегда передавайте
  полный набор данных по экземплярам и продуктам»;
* ограничения пункта приёма считались нарушением по самому факту их наличия,
  поэтому на живом пункте приёма передача не прошла бы никогда;
* лист отгрузки запрашивался методом, который Ozon уже отключил — живой вызов
  03.09.2026 отвечает `400 {"code":9,"message":"obsolete method cannot be used"}`.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal, engine
from app.models import Base
from app.models.fbs_order import (
    MAPPING_STATUS_MAPPED,
    RESERVE_STATUS_RESERVED,
    FbsOrder,
    FbsOrderMarking,
    FbsOrderProduct,
)
from app.models.fbs_supply import (
    FBS_DELIVERY_TYPE_WAREHOUSE_SC,
    FBS_SUPPLY_STATUS_PACKED,
    FbsSupply,
)
from app.models.product import Product
from app.models.seller import Seller
from app.models.tenant import Tenant
from app.models.warehouse import Warehouse
from app.schemas.ozon_fbs_api import OzonV1GetRestrictionsResponse
from app.services import ozon_fbs_process_service as process_svc
from app.services.marketplace_provider import FakeMarketplaceTransport, OzonMarketplaceProvider

SKU = 5680762790
POSTING_NUMBER = "0195832-0021-1"


@pytest_asyncio.fixture()
async def db_session() -> AsyncSession:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    async with SessionLocal() as session:
        yield session


async def _seed_order(db_session: AsyncSession) -> tuple[FbsOrder, FbsOrderProduct]:
    tenant = Tenant(name="Ozon process", slug=f"ozon-proc-{uuid.uuid4().hex[:8]}")
    seller = Seller(tenant=tenant, name="Seller")
    warehouse = Warehouse(tenant=tenant, name="FBS", code=f"ozon-proc-{uuid.uuid4().hex[:8]}")
    product = Product(
        tenant=tenant, seller=seller, name="Очки", sku_code=f"sku-{uuid.uuid4().hex[:8]}"
    )
    now = datetime.now(UTC)
    order = FbsOrder(
        tenant=tenant,
        seller=seller,
        warehouse=warehouse,
        product=product,
        marketplace="ozon",
        external_order_id=POSTING_NUMBER,
        wb_order_id=-1,
        created_at_wb=now,
        deadline_at=now + timedelta(days=1),
        price=250000,
        mapping_status=MAPPING_STATUS_MAPPED,
        reserve_status=RESERVE_STATUS_RESERVED,
    )
    db_session.add_all([tenant, seller, warehouse, product, order])
    await db_session.flush()
    position = FbsOrderProduct(
        order_id=order.id,
        product_id=product.id,
        ozon_sku=SKU,
        offer_id="OZ862006269",
        name="Очки",
        quantity=3,
        position_index=0,
        provider_data_json={"sku": SKU, "quantity": 3, "weight": 100},
    )
    db_session.add(position)
    await db_session.commit()
    return order, position


def _exemplar_responses() -> dict[str, Any]:
    return {
        "/v6/fbs/posting/product/exemplar/create-or-get": {
            "posting_number": POSTING_NUMBER,
            "products": [
                {
                    "product_id": SKU,
                    "exemplars": [
                        {"exemplar_id": 81},
                        {"exemplar_id": 82},
                        {"exemplar_id": 83},
                    ],
                }
            ],
        },
        "/v5/fbs/posting/product/exemplar/validate": {
            "products": [{"product_id": SKU, "valid": True, "exemplars": []}]
        },
        "/v6/fbs/posting/product/exemplar/set": {},
        "/v5/fbs/posting/product/exemplar/status": {
            "posting_number": POSTING_NUMBER,
            "status": "ship_available",
            "products": [],
        },
    }


async def test_exemplar_set_carries_every_code_of_the_posting_not_only_the_last(
    db_session: AsyncSession,
) -> None:
    """Отправление из трёх единиц должно уходить в Ozon целиком.

    Мы слали ровно один только что отсканированный код, поэтому у Ozon
    оставался бы только последний, а два предыдущих терялись при каждой
    следующей отправке.
    """
    order, position = await _seed_order(db_session)
    already_sent = FbsOrderMarking(
        tenant_id=order.tenant_id,
        order_id=order.id,
        order_product_id=position.id,
        kind="sgtin",
        value="0104601234567890211111",
        meta_details_json={"exemplar_id": 81},
    )
    second_sent = FbsOrderMarking(
        tenant_id=order.tenant_id,
        order_id=order.id,
        order_product_id=position.id,
        kind="sgtin",
        value="0104601234567890212222",
        meta_details_json={"exemplar_id": 82},
    )
    current = FbsOrderMarking(
        tenant_id=order.tenant_id,
        order_id=order.id,
        order_product_id=position.id,
        kind="sgtin",
        value="0104601234567890213333",
    )
    db_session.add_all([already_sent, second_sent, current])
    await db_session.commit()

    transport = FakeMarketplaceTransport(endpoint_responses=_exemplar_responses())
    result = await process_svc.submit_marking(
        db_session,
        order=order,
        marking=current,
        provider=OzonMarketplaceProvider(transport=transport),
        client_id="c",
        api_key="k",
    )

    assert result.accepted is True
    sent = next(
        payload
        for path, payload in transport.endpoint_calls
        if path == "/v6/fbs/posting/product/exemplar/set"
    )
    products = sent["products"]
    assert len(products) == 1
    assert products[0]["product_id"] == SKU
    exemplar_ids = sorted(item["exemplar_id"] for item in products[0]["exemplars"])
    assert exemplar_ids == [81, 82, 83]
    marks = sorted(
        mark["mark"] for item in products[0]["exemplars"] for mark in item["marks"]
    )
    assert marks == [
        "0104601234567890211111",
        "0104601234567890212222",
        "0104601234567890213333",
    ]


async def test_rejected_codes_are_not_resent_with_the_full_set(
    db_session: AsyncSession,
) -> None:
    order, position = await _seed_order(db_session)
    rejected = FbsOrderMarking(
        tenant_id=order.tenant_id,
        order_id=order.id,
        order_product_id=position.id,
        kind="sgtin",
        value="0104601234567890219999",
        meta_status="rejected",
        meta_details_json={"exemplar_id": 81},
    )
    current = FbsOrderMarking(
        tenant_id=order.tenant_id,
        order_id=order.id,
        order_product_id=position.id,
        kind="sgtin",
        value="0104601234567890213333",
    )
    db_session.add_all([rejected, current])
    await db_session.commit()

    transport = FakeMarketplaceTransport(endpoint_responses=_exemplar_responses())
    await process_svc.submit_marking(
        db_session,
        order=order,
        marking=current,
        provider=OzonMarketplaceProvider(transport=transport),
        client_id="c",
        api_key="k",
    )

    sent = next(
        payload
        for path, payload in transport.endpoint_calls
        if path == "/v6/fbs/posting/product/exemplar/set"
    )
    marks = [mark["mark"] for item in sent["products"][0]["exemplars"] for mark in item["marks"]]
    assert marks == ["0104601234567890213333"]


async def test_empty_exemplar_answer_is_a_typed_error_not_a_crash(
    db_session: AsyncSession,
) -> None:
    """Пустой ответ давал `TypeError` и пятисотку оператору на скане кода."""
    order, position = await _seed_order(db_session)
    marking = FbsOrderMarking(
        tenant_id=order.tenant_id,
        order_id=order.id,
        order_product_id=position.id,
        kind="sgtin",
        value="0104601234567890213333",
    )
    db_session.add(marking)
    await db_session.commit()

    transport = FakeMarketplaceTransport()  # любой путь отвечает пустым словарём
    with pytest.raises(process_svc.OzonFbsProcessError) as caught:
        await process_svc.submit_marking(
            db_session,
            order=order,
            marking=marking,
            provider=OzonMarketplaceProvider(transport=transport),
            client_id="c",
            api_key="k",
        )
    assert caught.value.code == "ozon_exemplar_missing"


def test_restrictions_of_a_real_drop_off_point_are_limits_not_violations() -> None:
    """Пример из спецификации: 40 000 г и 500 000 ₽ — это лимиты пункта приёма."""
    response = OzonV1GetRestrictionsResponse.model_validate(
        {
            "result": {
                "posting_number": POSTING_NUMBER,
                "max_posting_weight": 40000,
                "min_posting_weight": 0,
                "width": 500,
                "height": 500,
                "length": 500,
                "max_posting_price": 500000,
                "min_posting_price": 0,
            }
        }
    )
    assert (
        process_svc._restriction_violations(response, weight_grams=300.0, price_rub=2500.0) == []
    )


def test_restrictions_still_stop_a_posting_that_really_exceeds_them() -> None:
    response = OzonV1GetRestrictionsResponse.model_validate(
        {
            "result": {
                "posting_number": POSTING_NUMBER,
                "max_posting_weight": 40000,
                "max_posting_price": 500000,
            }
        }
    )
    violations = process_svc._restriction_violations(
        response,
        weight_grams=41000.0,
        price_rub=600000.0,
    )
    assert len(violations) == 2
    assert "вес" in violations[0]
    assert "стоимость" in violations[1]


async def test_posting_weight_is_summed_over_positions(db_session: AsyncSession) -> None:
    order, _ = await _seed_order(db_session)
    assert await process_svc._posting_weight_grams(db_session, order) == 300.0


def test_shipping_list_uses_the_method_ozon_still_serves() -> None:
    """`/v2/posting/fbs/digital/act/get-pdf` отключён; живая замена — без `digital`."""
    assert process_svc.SHIPPING_LIST_PATH == "/v2/posting/fbs/act/get-pdf"


async def test_handoff_asks_for_the_shipping_list_by_the_live_path(
    db_session: AsyncSession,
) -> None:
    order, _ = await _seed_order(db_session)
    supply = FbsSupply(
        tenant_id=order.tenant_id,
        seller_id=order.seller_id,
        warehouse_id=order.warehouse_id,
        marketplace="ozon",
        wb_supply_id=None,
        name="Ozon FBS",
        status=FBS_SUPPLY_STATUS_PACKED,
        delivery_type=FBS_DELIVERY_TYPE_WAREHOUSE_SC,
    )
    db_session.add(supply)
    await db_session.commit()

    png = (
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAE"
        "hQGAhKmMIQAAAABJRU5ErkJggg=="
    )
    transport = FakeMarketplaceTransport(
        endpoint_responses={
            "/v3/posting/fbs/get": {
                "result": {
                    "posting_number": POSTING_NUMBER,
                    "status": "awaiting_deliver",
                    "substatus": "posting_in_carriage",
                    "related_postings": {"related_posting_numbers": []},
                }
            },
            "/v1/posting/fbs/restrictions": {
                "result": {"posting_number": POSTING_NUMBER, "max_posting_weight": 40000}
            },
            "/v4/posting/fbs/ship": {"result": [POSTING_NUMBER]},
            "/v2/posting/fbs/package-label/create": {"result": {"tasks": [{"task_id": 71}]}},
            "/v1/posting/fbs/package-label/get": {"result": {"status": "completed"}},
            "/v2/posting/fbs/package-label": {"file_content": png},
            "/v1/carriage/create": {"carriage_id": 901},
            "/v1/carriage/get": {"carriage_id": 901, "status": "sended"},
            "/v1/carriage/set-postings": {
                "result": [{"posting_number": POSTING_NUMBER, "result": True}]
            },
            "/v1/carriage/approve": {},
            "/v2/posting/fbs/act/get-barcode": {"file_content": png},
            "/v2/posting/fbs/act/get-barcode/text": {"result": "OZON-ACT-901"},
            "/v2/posting/fbs/act/get-pdf": {"file_content": png},
        }
    )

    result = await process_svc.handoff_supply(
        db_session,
        supply=supply,
        orders=[order],
        provider=OzonMarketplaceProvider(transport=transport),
        client_id="c",
        api_key="k",
    )

    called = [path for path, _ in transport.endpoint_calls]
    assert "/v2/posting/fbs/act/get-pdf" in called
    assert "/v2/posting/fbs/digital/act/get-pdf" not in called
    assert result.shipping_list_bytes is not None
    assert result.carriage_id == 901
