"""WMS-549 · «Расчёты» в кабинете селлера: изоляция раздела /seller-billing.

Кусок К1 — только сервер. Экран (К3/К4) и ставки (К2) сюда не входят.
Проверки — настоящие HTTP-запросы с настоящими подписанными токенами разных
ролей, а не вызов сервисных функций в обход авторизации.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy import select

from app.api.seller_billing import router as seller_billing_router
from app.core.roles import FULFILLMENT_ADMIN, FULFILLMENT_SELLER, FULFILLMENT_STAFF
from app.db.session import SessionLocal
from app.models.billing import BillingInvoice, BillingInvoiceV2, BillingLedgerEntry
from app.models.ff_staff_permissions import FfStaffPermissions
from app.models.seller import Seller
from app.models.seller_shop_delegation import SellerShopDelegation
from app.models.seller_staff_permissions import SellerStaffPermissions
from app.models.tenant import Tenant
from app.models.user import User
from app.services.tokens import create_access_token

_PERIOD_FROM = "2026-08-01"
_PERIOD_TO = "2026-08-31"
_MOMENT = datetime(2026, 8, 20, 12, tzinfo=UTC)


class _Fixtures:
    def __init__(
        self,
        tenants: dict[str, Tenant],
        sellers: dict[str, Seller],
        users: dict[str, User],
        legacy_invoices: dict[str, uuid.UUID],
        v2_invoices: dict[str, uuid.UUID],
    ) -> None:
        self.tenants = tenants
        self.sellers = sellers
        self.users = users
        self.legacy_invoices = legacy_invoices
        self.v2_invoices = v2_invoices


async def _seed() -> _Fixtures:
    async with SessionLocal() as session:
        tenants = {
            "a": Tenant(name="WMS549 A", slug=f"wms549-a-{uuid.uuid4().hex}"),
            "b": Tenant(name="WMS549 B", slug=f"wms549-b-{uuid.uuid4().hex}"),
        }
        session.add_all(tenants.values())
        await session.flush()

        sellers = {
            "s1": Seller(tenant_id=tenants["a"].id, name="Селлер Один"),
            "s2": Seller(tenant_id=tenants["a"].id, name="Селлер Два"),
            "s3": Seller(tenant_id=tenants["b"].id, name="Селлер Три (чужой тенант)"),
        }
        session.add_all(sellers.values())
        await session.flush()

        users = {
            "owner1": User(
                tenant_id=tenants["a"].id, seller_id=sellers["s1"].id,
                email="owner1@merchant.ru", password_hash="unused", role=FULFILLMENT_SELLER,
            ),
            "staff_docs": User(
                tenant_id=tenants["a"].id, seller_id=sellers["s1"].id,
                email="staff-docs@merchant.ru", password_hash="unused", role=FULFILLMENT_SELLER,
            ),
            "staff_nodocs": User(
                tenant_id=tenants["a"].id, seller_id=sellers["s1"].id,
                email="staff-nodocs@merchant.ru", password_hash="unused", role=FULFILLMENT_SELLER,
            ),
            "manager": User(
                tenant_id=tenants["a"].id, seller_id=sellers["s1"].id,
                email="manager@merchant.ru", password_hash="unused", role=FULFILLMENT_SELLER,
                can_manage_seller_shops=True,
            ),
            "unlinked": User(
                tenant_id=tenants["a"].id, seller_id=None,
                email="unlinked@merchant.ru", password_hash="unused", role=FULFILLMENT_SELLER,
            ),
            "owner2": User(
                tenant_id=tenants["a"].id, seller_id=sellers["s2"].id,
                email="owner2@merchant.ru", password_hash="unused", role=FULFILLMENT_SELLER,
            ),
            "owner3": User(
                tenant_id=tenants["b"].id, seller_id=sellers["s3"].id,
                email="owner3@merchant.ru", password_hash="unused", role=FULFILLMENT_SELLER,
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

        session.add_all(
            [
                SellerStaffPermissions(
                    user_id=users["staff_docs"].id, can_documents=True, can_products=False,
                    can_honest_sign=False, can_settings=False, can_staff=False,
                ),
                SellerStaffPermissions(
                    user_id=users["staff_nodocs"].id, can_documents=False, can_products=True,
                    can_honest_sign=False, can_settings=False, can_staff=False,
                ),
                SellerShopDelegation(
                    user_id=users["manager"].id, target_seller_id=sellers["s2"].id, enabled=True,
                ),
                FfStaffPermissions(user_id=users["staff_ff"].id, can_reception=True),
            ]
        )

        # Начисления: у S1 одна запись, у S2 — две (нужно для курсора дочитки),
        # у S3 (чужой тенант) — своя, отдельная.
        session.add(
            BillingLedgerEntry(
                tenant_id=tenants["a"].id, seller_id=sellers["s1"].id, service_code="inbound",
                source="test", source_type="inbound_intake", source_id=uuid.uuid4(),
                unit="item", quantity=Decimal("1"), rate=100, amount=100, occurred_at=_MOMENT,
            )
        )
        session.add_all(
            [
                BillingLedgerEntry(
                    tenant_id=tenants["a"].id, seller_id=sellers["s2"].id, service_code="inbound",
                    source="test", source_type="inbound_intake", source_id=uuid.uuid4(),
                    unit="item", quantity=Decimal("1"), rate=200, amount=200,
                    occurred_at=_MOMENT,
                ),
                BillingLedgerEntry(
                    tenant_id=tenants["a"].id, seller_id=sellers["s2"].id, service_code="inbound",
                    source="test", source_type="inbound_intake", source_id=uuid.uuid4(),
                    unit="item", quantity=Decimal("1"), rate=250, amount=250,
                    occurred_at=_MOMENT + timedelta(hours=1),
                ),
            ]
        )
        session.add(
            BillingLedgerEntry(
                tenant_id=tenants["b"].id, seller_id=sellers["s3"].id, service_code="inbound",
                source="test", source_type="inbound_intake", source_id=uuid.uuid4(),
                unit="item", quantity=Decimal("1"), rate=300, amount=300, occurred_at=_MOMENT,
            )
        )

        legacy_invoices = {key: uuid.uuid4() for key in ("s1", "s2", "s3")}
        for key, seller_key, tenant_key, amount in (
            ("s1", "s1", "a", "100.00"),
            ("s2", "s2", "a", "200.00"),
            ("s3", "s3", "b", "300.00"),
        ):
            session.add(
                BillingInvoice(
                    id=legacy_invoices[key], tenant_id=tenants[tenant_key].id,
                    seller_id=sellers[seller_key].id, number=f"WMS549-LEG-{key.upper()}",
                    period=date(2026, 8, 1), status="issued", total_amount=Decimal(amount),
                    ff_profile_snapshot={}, seller_profile_snapshot={}, lines=[],
                )
            )

        v2_invoices = {key: uuid.uuid4() for key in ("s1", "s2", "s3")}
        for key, seller_key, tenant_key, amount in (
            ("s1", "s1", "a", 10000),
            ("s2", "s2", "a", 20000),
            ("s3", "s3", "b", 30000),
        ):
            session.add(
                BillingInvoiceV2(
                    id=v2_invoices[key], tenant_id=tenants[tenant_key].id,
                    seller_id=sellers[seller_key].id, number=f"WMS549-V2-{key.upper()}",
                    creation_mode="manual", status="issued",
                    ff_profile_snapshot={}, seller_profile_snapshot={},
                    total_amount_kopecks=amount,
                )
            )

        await session.commit()
        return _Fixtures(tenants, sellers, users, legacy_invoices, v2_invoices)


def _headers(user: User, *, active_seller: uuid.UUID | None = None) -> dict[str, str]:
    token = create_access_token(
        user_id=user.id, tenant_id=user.tenant_id, role=user.role, seller_id=active_seller,
    )
    return {"Authorization": f"Bearer {token}"}


def _period(**extra: str) -> dict[str, str]:
    return {"date_from": _PERIOD_FROM, "date_to": _PERIOD_TO, **extra}


# ---------------------------------------------------------------------------
# R1, R4, C1: роль и право «Документы» решают, кто видит раздел.
# ---------------------------------------------------------------------------


async def test_only_owner_and_staff_with_documents_permission_see_own_seller(
    async_client: AsyncClient,
) -> None:
    fx = await _seed()
    for actor in ("owner1", "staff_docs"):
        response = await async_client.get(
            "/seller-billing/summary", headers=_headers(fx.users[actor]), params=_period(),
        )
        assert response.status_code == 200, (actor, response.text)
        body = response.json()
        assert [row["seller_id"] for row in body["rows"]] == [str(fx.sellers["s1"].id)]
        assert body["rows"][0]["seller_name"] == fx.sellers["s1"].name
        assert body["totals"]["seller_count"] == 1
        assert str(fx.sellers["s2"].id) not in response.text
        assert fx.sellers["s2"].name not in response.text
        assert str(fx.sellers["s3"].id) not in response.text
        assert fx.sellers["s3"].name not in response.text
    for actor in ("staff_nodocs", "unlinked", "admin", "staff_ff"):
        response = await async_client.get(
            "/seller-billing/summary", headers=_headers(fx.users[actor]), params=_period(),
        )
        assert response.status_code == 403, (actor, response.text)


# ---------------------------------------------------------------------------
# R2, R3, C4: числа только своего селлера, чужие операции их не меняют.
# ---------------------------------------------------------------------------


async def test_details_and_storage_total_see_only_own_operations(
    async_client: AsyncClient,
) -> None:
    fx = await _seed()
    details = await async_client.get(
        "/seller-billing/details", headers=_headers(fx.users["owner1"]), params=_period(),
    )
    assert details.status_code == 200, details.text
    body = details.json()
    assert body["seller_id"] == str(fx.sellers["s1"].id)
    assert len(body["entries"]) == 1
    assert body["entries"][0]["amount_kopecks"] == 100
    assert body["totals"]["net_total_kopecks"] == 100
    assert str(fx.sellers["s2"].id) not in details.text
    assert fx.sellers["s2"].name not in details.text

    storage = await async_client.get(
        "/seller-billing/storage-total", headers=_headers(fx.users["owner1"]), params=_period(),
    )
    assert storage.status_code == 200, storage.text
    assert storage.json() == {"liter_days": 0.0, "amount_kopecks": 0, "complete": True}


# ---------------------------------------------------------------------------
# R3, C8: seller_id в строке запроса игнорируется — ручек с этим параметром нет.
# ---------------------------------------------------------------------------


async def test_seller_id_query_parameter_is_ignored(async_client: AsyncClient) -> None:
    fx = await _seed()
    headers = _headers(fx.users["owner1"])
    foreign = str(fx.sellers["s2"].id)
    for path, params in (
        ("/seller-billing/summary", _period(seller_id=foreign)),
        ("/seller-billing/details", _period(seller_id=foreign)),
        ("/seller-billing/storage-total", _period(seller_id=foreign)),
        ("/seller-billing/invoices", {"seller_id": foreign}),
    ):
        response = await async_client.get(path, headers=headers, params=params)
        assert response.status_code == 200, (path, response.text)
        assert foreign not in response.text
        assert fx.sellers["s2"].name not in response.text


# ---------------------------------------------------------------------------
# R3, C9: счёт другого селлера или другого арендатора по id — 404.
# ---------------------------------------------------------------------------


async def test_cross_seller_and_cross_tenant_invoice_by_id_is_404(
    async_client: AsyncClient,
) -> None:
    fx = await _seed()
    headers = _headers(fx.users["owner1"])

    own_legacy = await async_client.get(
        f"/seller-billing/invoices/legacy/{fx.legacy_invoices['s1']}", headers=headers,
    )
    assert own_legacy.status_code == 200, own_legacy.text
    own_v2 = await async_client.get(
        f"/seller-billing/invoices/v2/{fx.v2_invoices['s1']}", headers=headers,
    )
    assert own_v2.status_code == 200, own_v2.text

    for key in ("s2", "s3"):
        legacy = await async_client.get(
            f"/seller-billing/invoices/legacy/{fx.legacy_invoices[key]}", headers=headers,
        )
        assert legacy.status_code == 404, (key, legacy.text)
        v2 = await async_client.get(
            f"/seller-billing/invoices/v2/{fx.v2_invoices[key]}", headers=headers,
        )
        assert v2.status_code == 404, (key, v2.text)

    missing = await async_client.get(
        f"/seller-billing/invoices/legacy/{uuid.uuid4()}", headers=headers,
    )
    assert missing.status_code == 404


# ---------------------------------------------------------------------------
# R3, C10: курсор дочитки документов, выданный для другого селлера, отклоняется.
# ---------------------------------------------------------------------------


async def test_cursor_issued_for_another_seller_is_rejected(async_client: AsyncClient) -> None:
    fx = await _seed()
    first_page = await async_client.get(
        "/seller-billing/details",
        headers=_headers(fx.users["owner2"]),
        params=_period(limit="1"),
    )
    assert first_page.status_code == 200, first_page.text
    foreign_cursor = first_page.json()["next_cursor"]
    assert foreign_cursor

    rejected = await async_client.get(
        "/seller-billing/details",
        headers=_headers(fx.users["owner1"]),
        params=_period(cursor=foreign_cursor),
    )
    assert rejected.status_code == 422, rejected.text
    assert fx.sellers["s1"].name not in rejected.text
    assert fx.sellers["s2"].name not in rejected.text


# ---------------------------------------------------------------------------
# R3, R4, C11, C16: ручки ФФ /billing/* селлеру недоступны и наоборот.
# ---------------------------------------------------------------------------


async def test_ff_billing_routes_still_reject_seller_role(async_client: AsyncClient) -> None:
    fx = await _seed()
    headers = _headers(fx.users["owner1"])
    for path, params in (
        ("/billing/seller-report/summary", _period(include_finance="true")),
        ("/billing/invoices-v2", {}),
        ("/billing/tariff-matrix", {}),
        (f"/billing/invoices/{fx.legacy_invoices['s1']}", {}),
        (f"/billing/invoices-v2/{fx.v2_invoices['s1']}", {}),
    ):
        response = await async_client.get(path, headers=headers, params=params)
        assert response.status_code == 403, (path, response.text)


# ---------------------------------------------------------------------------
# R4, C14: несколько магазинов — только активный, без суммирования.
# ---------------------------------------------------------------------------


async def test_manager_with_multiple_shops_sees_only_active_shop(
    async_client: AsyncClient,
) -> None:
    fx = await _seed()
    manager = fx.users["manager"]

    as_home = await async_client.get(
        "/seller-billing/summary", headers=_headers(manager), params=_period(),
    )
    assert as_home.status_code == 200
    assert [row["seller_id"] for row in as_home.json()["rows"]] == [str(fx.sellers["s1"].id)]

    as_s2 = await async_client.get(
        "/seller-billing/summary",
        headers=_headers(manager, active_seller=fx.sellers["s2"].id),
        params=_period(),
    )
    assert as_s2.status_code == 200, as_s2.text
    assert [row["seller_id"] for row in as_s2.json()["rows"]] == [str(fx.sellers["s2"].id)]
    assert str(fx.sellers["s1"].id) not in as_s2.text
    s2_total = as_s2.json()["totals"]["net_total_kopecks"]
    s1_total = as_home.json()["totals"]["net_total_kopecks"]
    assert s2_total != s1_total

    async with SessionLocal() as session:
        delegation = await session.scalar(
            select(SellerShopDelegation).where(SellerShopDelegation.user_id == manager.id)
        )
        assert delegation is not None
        delegation.enabled = False
        await session.commit()

    revoked = await async_client.get(
        "/seller-billing/summary",
        headers=_headers(manager, active_seller=fx.sellers["s2"].id),
        params=_period(),
    )
    assert revoked.status_code == 403, revoked.text
    assert fx.sellers["s2"].name not in revoked.text


# ---------------------------------------------------------------------------
# R4, C15: без права управлять магазинами чужой seller_id в токене не действует.
# ---------------------------------------------------------------------------


async def test_user_without_shop_management_ignores_foreign_seller_claim(
    async_client: AsyncClient,
) -> None:
    fx = await _seed()
    response = await async_client.get(
        "/seller-billing/summary",
        headers=_headers(fx.users["owner1"], active_seller=fx.sellers["s2"].id),
        params=_period(),
    )
    assert response.status_code == 200, response.text
    assert [row["seller_id"] for row in response.json()["rows"]] == [str(fx.sellers["s1"].id)]
    assert str(fx.sellers["s2"].id) not in response.text


# ---------------------------------------------------------------------------
# R3, R4, C12: чужой арендатор — 404 на счёт, поддельная привязка тенанта — 403.
# ---------------------------------------------------------------------------


async def test_foreign_tenant_owner_is_isolated_and_forged_tenant_claim_rejected(
    async_client: AsyncClient,
) -> None:
    fx = await _seed()
    own = await async_client.get(
        "/seller-billing/summary", headers=_headers(fx.users["owner3"]), params=_period(),
    )
    assert own.status_code == 200, own.text
    assert [row["seller_id"] for row in own.json()["rows"]] == [str(fx.sellers["s3"].id)]
    assert str(fx.sellers["s1"].id) not in own.text and str(fx.sellers["s2"].id) not in own.text

    foreign_invoice = await async_client.get(
        f"/seller-billing/invoices/legacy/{fx.legacy_invoices['s1']}",
        headers=_headers(fx.users["owner3"]),
    )
    assert foreign_invoice.status_code == 404

    forged_token = create_access_token(
        user_id=fx.users["owner3"].id, tenant_id=fx.tenants["a"].id, role=FULFILLMENT_SELLER,
    )
    forged = await async_client.get(
        "/seller-billing/summary",
        headers={"Authorization": f"Bearer {forged_token}"},
        params=_period(),
    )
    assert forged.status_code == 403, forged.text


# ---------------------------------------------------------------------------
# R3, R4, C13, C16: ни одна ручка раздела не обходит общую проверку.
# ---------------------------------------------------------------------------


def _route_request(path_template: str, fx: _Fixtures) -> tuple[str, dict[str, str]]:
    path = path_template.format(invoice_id=fx.legacy_invoices["s1"])
    if "invoices/v2" in path_template:
        path = path_template.format(invoice_id=fx.v2_invoices["s1"])
    return path, _period()


async def test_every_seller_billing_route_enforces_the_common_scope_check(
    async_client: AsyncClient,
) -> None:
    fx = await _seed()
    path_templates = sorted({route.path for route in seller_billing_router.routes})
    assert path_templates == sorted(
        {
            "/seller-billing/summary",
            "/seller-billing/details",
            "/seller-billing/storage-total",
            "/seller-billing/invoices",
            "/seller-billing/invoices/legacy/{invoice_id}",
            "/seller-billing/invoices/v2/{invoice_id}",
            "/seller-billing/rates",
        }
    )
    for template in path_templates:
        path, params = _route_request(template, fx)
        for actor in ("staff_nodocs", "unlinked", "admin", "staff_ff"):
            response = await async_client.get(
                path, headers=_headers(fx.users[actor]), params=params
            )
            assert response.status_code == 403, (template, actor, response.text)
        allowed = await async_client.get(
            path, headers=_headers(fx.users["staff_docs"]), params=params
        )
        assert allowed.status_code == 200, (template, allowed.text)
        assert str(fx.sellers["s2"].id) not in allowed.text
        assert fx.sellers["s2"].name not in allowed.text
