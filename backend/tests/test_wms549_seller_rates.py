"""WMS-549 · «Расчёты» в кабинете селлера: вкладка «Ставки» (кусок К2).

GET /seller-billing/rates висит на той же общей проверке
require_seller_billing_scope, что и весь раздел (К1). Ставки читаются тем же
расчётом, которым система реально начисляет деньги за операцию
(_resolve_v2_tariff → _live_price в billing_seller_report_service, уже
проверено чтением кода): второй, независимой формулы приоритета здесь нет.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from httpx import AsyncClient

from app.core.roles import FULFILLMENT_ADMIN, FULFILLMENT_SELLER, FULFILLMENT_STAFF
from app.db.session import SessionLocal
from app.models.billing import BillingTariffVersionV2
from app.models.operation_fact import OperationFact
from app.models.product import Product
from app.models.seller import Seller
from app.models.seller_staff_permissions import SellerStaffPermissions
from app.models.tenant import Tenant
from app.models.user import User
from app.services.tokens import create_access_token

_PAST = datetime(2020, 1, 1, tzinfo=UTC)
_S1_OVERRIDE_FROM = datetime(2021, 1, 1, tzinfo=UTC)
_TERMINATED_TO = datetime(2022, 1, 1, tzinfo=UTC)
_FUTURE = datetime.now(UTC) + timedelta(days=30)
_FACT_MOMENT = datetime(2026, 8, 20, 12, tzinfo=UTC)


class _Fixtures:
    def __init__(
        self,
        tenants: dict[str, Tenant],
        sellers: dict[str, Seller],
        users: dict[str, User],
        products: dict[str, Product],
    ) -> None:
        self.tenants = tenants
        self.sellers = sellers
        self.users = users
        self.products = products


async def _seed() -> _Fixtures:
    async with SessionLocal() as session:
        tenants = {
            "a": Tenant(name="WMS549 Rates A", slug=f"wms549-rates-a-{uuid.uuid4().hex}"),
            "b": Tenant(name="WMS549 Rates B", slug=f"wms549-rates-b-{uuid.uuid4().hex}"),
        }
        session.add_all(tenants.values())
        await session.flush()

        sellers = {
            "s1": Seller(tenant_id=tenants["a"].id, name="Селлер Один"),
            "s2": Seller(tenant_id=tenants["a"].id, name="Селлер Два"),
            "s3": Seller(tenant_id=tenants["b"].id, name="Селлер Три"),
        }
        session.add_all(sellers.values())
        await session.flush()

        products = {
            "p1": Product(
                tenant_id=tenants["a"].id, seller_id=sellers["s1"].id,
                name="Товар Один", sku_code="SKU-P1",
            ),
            "p2": Product(
                tenant_id=tenants["a"].id, seller_id=sellers["s2"].id,
                name="Товар Два", sku_code="SKU-P2",
            ),
        }
        session.add_all(products.values())
        await session.flush()

        users = {
            "owner1": User(
                tenant_id=tenants["a"].id, seller_id=sellers["s1"].id,
                email="rates-owner1@merchant.ru", password_hash="unused", role=FULFILLMENT_SELLER,
            ),
            "staff_nodocs": User(
                tenant_id=tenants["a"].id, seller_id=sellers["s1"].id,
                email="rates-staff-nodocs@merchant.ru", password_hash="unused",
                role=FULFILLMENT_SELLER,
            ),
            "owner2": User(
                tenant_id=tenants["a"].id, seller_id=sellers["s2"].id,
                email="rates-owner2@merchant.ru", password_hash="unused", role=FULFILLMENT_SELLER,
            ),
            "owner3": User(
                tenant_id=tenants["b"].id, seller_id=sellers["s3"].id,
                email="rates-owner3@merchant.ru", password_hash="unused", role=FULFILLMENT_SELLER,
            ),
            "admin": User(
                tenant_id=tenants["a"].id, password_hash="unused", role=FULFILLMENT_ADMIN,
            ),
            "staff_ff": User(
                tenant_id=tenants["a"].id, password_hash="unused", role=FULFILLMENT_STAFF,
            ),
        }
        session.add_all(users.values())
        await session.flush()
        session.add(
            SellerStaffPermissions(
                user_id=users["staff_nodocs"].id, can_documents=False, can_products=True,
                can_honest_sign=False, can_settings=False, can_staff=False,
            )
        )

        session.add_all(
            [
                # Общая ставка на приёмку — тенант A: применится всем, у кого
                # нет своей индивидуальной ставки.
                BillingTariffVersionV2(
                    tenant_id=tenants["a"].id, service_code="inbound", unit="item", rate=100,
                    valid_from_at=_PAST,
                ),
                # Индивидуальная ставка S1 на приёмку — приоритетнее общей.
                BillingTariffVersionV2(
                    tenant_id=tenants["a"].id, seller_id=sellers["s1"].id, service_code="inbound",
                    unit="item", rate=150, valid_from_at=_S1_OVERRIDE_FROM,
                ),
                # Общая ставка на отгрузку ФБО — одна на всех, без переопределений.
                BillingTariffVersionV2(
                    tenant_id=tenants["a"].id, service_code="marketplace_outbound", unit="item",
                    rate=50, valid_from_at=_PAST,
                ),
                # Ставка на конкретный товар S1 — упаковка.
                BillingTariffVersionV2(
                    tenant_id=tenants["a"].id, seller_id=sellers["s1"].id,
                    product_id=products["p1"].id, service_code="packing", unit="item", rate=77,
                    valid_from_at=_PAST,
                ),
                # Ставка на конкретный товар S2 — своя упаковка, не должна быть
                # видна S1.
                BillingTariffVersionV2(
                    tenant_id=tenants["a"].id, seller_id=sellers["s2"].id,
                    product_id=products["p2"].id, service_code="packing", unit="item", rate=88,
                    valid_from_at=_PAST,
                ),
                # Ставка сотрудника ФФ — оплата труда, к операциям селлера
                # никогда не применяется и не должна попасть в его ставки.
                BillingTariffVersionV2(
                    tenant_id=tenants["a"].id, employee_user_id=users["staff_ff"].id,
                    service_code="inbound", unit="item", rate=999, valid_from_at=_PAST,
                ),
                # Будущая версия S2 на приёмку — ещё не вступила в силу.
                BillingTariffVersionV2(
                    tenant_id=tenants["a"].id, seller_id=sellers["s2"].id, service_code="inbound",
                    unit="item", rate=500, valid_from_at=_FUTURE,
                ),
                # Прекращённая версия на возврат — единственная за всю историю,
                # услуга должна остаться без строки вовсе.
                BillingTariffVersionV2(
                    tenant_id=tenants["a"].id, service_code="return", unit="item", rate=999,
                    valid_from_at=_PAST, valid_to_at=_TERMINATED_TO,
                ),
                # Выключенная версия на хранение — включена как enabled=False,
                # услуга тоже не должна показаться.
                BillingTariffVersionV2(
                    tenant_id=tenants["a"].id, service_code="storage", unit="liter_day", rate=10,
                    valid_from_at=_PAST, enabled=False,
                ),
                # Тенант Б — полностью отдельная ставка, не должна течь в А.
                BillingTariffVersionV2(
                    tenant_id=tenants["b"].id, service_code="inbound", unit="item", rate=999,
                    valid_from_at=_PAST,
                ),
            ]
        )
        await session.commit()
        return _Fixtures(tenants, sellers, users, products)


def _headers(user: User) -> dict[str, str]:
    token = create_access_token(user_id=user.id, tenant_id=user.tenant_id, role=user.role)
    return {"Authorization": f"Bearer {token}"}


def _by_service(rates: list[dict[str, object]]) -> dict[tuple[str, str | None], dict[str, object]]:
    return {(row["service_code"], row["product_id"]): row for row in rates}


# ---------------------------------------------------------------------------
# R7: приоритет «товар → селлер → общая», будущая и прекращённая версии
# и ставки сотрудников не показываются.
# ---------------------------------------------------------------------------


async def test_seller_one_sees_own_priority_rate_and_own_product_only(
    async_client: AsyncClient,
) -> None:
    fx = await _seed()
    response = await async_client.get("/seller-billing/rates", headers=_headers(fx.users["owner1"]))
    assert response.status_code == 200, response.text
    rates = response.json()["rates"]
    assert len(rates) == 3, rates

    by_service = _by_service(rates)
    inbound = by_service[("inbound", None)]
    assert inbound["rate_kopecks"] == 150  # индивидуальная ставка S1, не общая 100
    assert inbound["unit"] == "item"
    assert inbound["product_sku"] is None and inbound["product_name"] is None

    outbound = by_service[("marketplace_outbound", None)]
    assert outbound["rate_kopecks"] == 50  # общая, своей нет — так и должно быть

    packing = by_service[("packing", str(fx.products["p1"].id))]
    assert packing["rate_kopecks"] == 77
    assert packing["product_sku"] == "SKU-P1"
    assert packing["product_name"] == "Товар Один"

    assert ("return", None) not in by_service  # прекращённая версия — не показана
    assert ("storage", None) not in by_service  # выключенная версия — не показана
    assert ("fbs_order", None) not in by_service  # нет ни одной версии вовсе
    assert not any(row["rate_kopecks"] == 999 for row in rates)  # ни сотрудник, ни тенант Б
    assert str(fx.products["p2"].id) not in response.text  # чужой товар S2
    # Сравниваем по числу в разобранном JSON, а не подстрокой по сырому тексту
    # ответа: подстрока "88" случайно совпадает с фрагментом чужого UUID
    # товара P1 (он законно присутствует в ответе) и даёт ложное падение.
    assert not any(row["rate_kopecks"] == 88 for row in rates)  # ставка на чужой товар


async def test_seller_two_falls_back_to_general_rate_and_own_product(
    async_client: AsyncClient,
) -> None:
    fx = await _seed()
    response = await async_client.get("/seller-billing/rates", headers=_headers(fx.users["owner2"]))
    assert response.status_code == 200, response.text
    rates = response.json()["rates"]
    by_service = _by_service(rates)

    inbound = by_service[("inbound", None)]
    assert inbound["rate_kopecks"] == 100  # общая: будущая версия S2 ещё не действует
    assert by_service[("marketplace_outbound", None)]["rate_kopecks"] == 50

    packing = by_service[("packing", str(fx.products["p2"].id))]
    assert packing["rate_kopecks"] == 88
    assert ("packing", str(fx.products["p1"].id)) not in by_service  # чужой товар S1
    # По числу в JSON, не подстрокой по тексту: "150" может случайно совпасть
    # с фрагментом легитимного UUID товара P2 в этом же ответе.
    assert not any(row["rate_kopecks"] == 150 for row in rates)  # ставка S1 не утекла
    assert "SKU-P1" not in response.text


async def test_foreign_tenant_seller_sees_only_its_own_tenant_rate(
    async_client: AsyncClient,
) -> None:
    fx = await _seed()
    response = await async_client.get("/seller-billing/rates", headers=_headers(fx.users["owner3"]))
    assert response.status_code == 200, response.text
    rates = response.json()["rates"]
    assert len(rates) == 1
    assert rates[0]["service_code"] == "inbound"
    assert rates[0]["rate_kopecks"] == 999
    assert rates[0]["product_id"] is None
    # По числу в JSON: единственная строка и так проверена выше, но явный
    # список запрещённых чисел фиксирует, что чужие ставки тенанта А сюда
    # точно не попали ни под каким видом.
    leaked_rates = {100, 150, 77, 88, 50}
    assert not any(row["rate_kopecks"] in leaked_rates for row in rates)


# ---------------------------------------------------------------------------
# R3, R4: общая проверка раздела действует и на ручке ставок.
# ---------------------------------------------------------------------------


async def test_rates_route_enforces_the_common_scope_check(async_client: AsyncClient) -> None:
    fx = await _seed()
    for actor in ("staff_nodocs", "admin", "staff_ff"):
        response = await async_client.get(
            "/seller-billing/rates", headers=_headers(fx.users[actor])
        )
        assert response.status_code == 403, (actor, response.text)


# ---------------------------------------------------------------------------
# C7: ставка на вкладке равна ставке, по которой система реально начисляет.
# ---------------------------------------------------------------------------


async def test_rate_shown_matches_live_charge_for_both_sellers(async_client: AsyncClient) -> None:
    fx = await _seed()
    async with SessionLocal() as session:
        session.add_all(
            [
                OperationFact(
                    tenant_id=fx.tenants["a"].id, seller_id=fx.sellers["s1"].id,
                    marketplace="wb", operation_code="inbound_completed",
                    billable_service_code="inbound", source_kind="inbound_intake",
                    source_event_id=uuid.uuid4(), document_type="inbound_intake",
                    document_id=uuid.uuid4(), occurred_at=_FACT_MOMENT, item_quantity=3,
                    source="system",
                ),
                OperationFact(
                    tenant_id=fx.tenants["a"].id, seller_id=fx.sellers["s2"].id,
                    marketplace="wb", operation_code="inbound_completed",
                    billable_service_code="inbound", source_kind="inbound_intake",
                    source_event_id=uuid.uuid4(), document_type="inbound_intake",
                    document_id=uuid.uuid4(), occurred_at=_FACT_MOMENT, item_quantity=2,
                    source="system",
                ),
            ]
        )
        await session.commit()

    params = {"date_from": "2026-08-20", "date_to": "2026-08-20"}
    for actor_key, _seller_key, expected_rate, expected_qty in (
        ("owner1", "s1", 150, 3),
        ("owner2", "s2", 100, 2),
    ):
        rates_response = await async_client.get(
            "/seller-billing/rates", headers=_headers(fx.users[actor_key])
        )
        rate_row = next(
            row for row in rates_response.json()["rates"] if row["service_code"] == "inbound"
        )
        assert rate_row["rate_kopecks"] == expected_rate

        details_response = await async_client.get(
            "/seller-billing/details", headers=_headers(fx.users[actor_key]), params=params,
        )
        assert details_response.status_code == 200, details_response.text
        entry = next(
            row for row in details_response.json()["entries"] if row["service_code"] == "inbound"
        )
        assert entry["rate_kopecks"] == expected_rate == rate_row["rate_kopecks"]
        assert entry["amount_kopecks"] == expected_rate * expected_qty


# ---------------------------------------------------------------------------
# R7, F5 (ревью Astra №1): «Действует с» приходит с явным часовым поясом.
# На SQLite DateTime(timezone=True) отдаёт naive datetime — без нормализации
# JS трактует такую строку как локальное время браузера и может показать
# дату на сутки раньше вместо UTC-даты, которую мы храним.
# ---------------------------------------------------------------------------


async def test_valid_from_at_is_returned_with_explicit_utc_offset(
    async_client: AsyncClient,
) -> None:
    fx = await _seed()
    response = await async_client.get("/seller-billing/rates", headers=_headers(fx.users["owner1"]))
    assert response.status_code == 200, response.text
    rates = response.json()["rates"]

    inbound = next(row for row in rates if row["service_code"] == "inbound")
    raw = inbound["valid_from_at"]
    parsed = datetime.fromisoformat(raw)
    assert parsed.tzinfo is not None, raw
    assert parsed.utcoffset() == timedelta(0), raw
    assert parsed == _S1_OVERRIDE_FROM

    packing = next(row for row in rates if row["service_code"] == "packing")
    packing_parsed = datetime.fromisoformat(packing["valid_from_at"])
    assert packing_parsed.tzinfo is not None, packing["valid_from_at"]
    assert packing_parsed == _PAST
