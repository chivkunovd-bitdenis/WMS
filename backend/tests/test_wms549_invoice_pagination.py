"""WMS-549 · регресс на F3 (ревью Astra №1): «Загрузить ещё» не должно терять
старые счета в объединённой истории (legacy + V2).

Дефект жил в общем сервисе billing_invoice_v2_service.list_invoices_v2:
каждая страница заново читала верхний срез limit+1 из каждой таблицы, не
сдвигая окно выборки по курсору, — и старые счета за пределами первого среза
никогда не доставались. Общий для ФФ и раздела селлера, поэтому проверяется
через обе ручки: /billing/invoices-v2 (ФФ) и /seller-billing/invoices
(селлер). Поведение ФФ, кроме исправления потерь, не меняется.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from httpx import AsyncClient

from app.core.roles import FULFILLMENT_ADMIN, FULFILLMENT_SELLER
from app.db.session import SessionLocal
from app.models.billing import BillingInvoice, BillingInvoiceV2
from app.models.seller import Seller
from app.models.tenant import Tenant
from app.models.user import User
from app.services.tokens import create_access_token

_TOTAL_V2_INVOICES = 61
_BASE_ISSUED_AT = datetime(2026, 9, 1, tzinfo=UTC)
_PAGE_LIMIT = 20


async def _seed_many_invoices() -> tuple[User, User, uuid.UUID]:
    async with SessionLocal() as session:
        tenant = Tenant(name="WMS549 F3", slug=f"wms549-f3-{uuid.uuid4().hex}")
        session.add(tenant)
        await session.flush()
        seller = Seller(tenant_id=tenant.id, name="Селлер F3")
        session.add(seller)
        await session.flush()
        owner = User(
            tenant_id=tenant.id, seller_id=seller.id,
            email=f"f3-owner-{uuid.uuid4().hex}@merchant.ru",
            password_hash="unused", role=FULFILLMENT_SELLER,
        )
        admin = User(tenant_id=tenant.id, password_hash="unused", role=FULFILLMENT_ADMIN)
        session.add_all([owner, admin])
        await session.flush()

        # Самый старый счёт истории — legacy, за пределами первого среза
        # limit+1: именно такие счета терялись при старой реализации.
        legacy_id = uuid.uuid4()
        session.add(
            BillingInvoice(
                id=legacy_id, tenant_id=tenant.id, seller_id=seller.id, number="F3-LEGACY-1",
                period=date(2020, 1, 1), status="issued", total_amount=Decimal("1.00"),
                ff_profile_snapshot={}, seller_profile_snapshot={}, lines=[],
                issued_at=_BASE_ISSUED_AT - timedelta(days=1),
            )
        )
        session.add_all(
            BillingInvoiceV2(
                tenant_id=tenant.id, seller_id=seller.id, number=f"F3-V2-{index:03d}",
                creation_mode="manual", status="issued",
                ff_profile_snapshot={}, seller_profile_snapshot={},
                total_amount_kopecks=100 + index,
                issued_at=_BASE_ISSUED_AT + timedelta(minutes=index),
            )
            for index in range(_TOTAL_V2_INVOICES)
        )
        await session.commit()
        return owner, admin, legacy_id


def _headers(user: User) -> dict[str, str]:
    token = create_access_token(user_id=user.id, tenant_id=user.tenant_id, role=user.role)
    return {"Authorization": f"Bearer {token}"}


async def _collect_all_pages(
    async_client: AsyncClient, url: str, headers: dict[str, str]
) -> tuple[list[str], int]:
    seen: list[str] = []
    cursor: str | None = None
    pages = 0
    while True:
        params: dict[str, str] = {"limit": str(_PAGE_LIMIT)}
        if cursor:
            params["cursor"] = cursor
        response = await async_client.get(url, headers=headers, params=params)
        assert response.status_code == 200, response.text
        body = response.json()
        seen.extend(item["id"] for item in body["invoices"])
        pages += 1
        cursor = body["next_cursor"]
        assert pages <= 10, "слишком много страниц — пагинация зациклилась"
        if not cursor:
            break
    return seen, pages


async def test_seller_invoice_history_pagination_does_not_lose_older_invoices(
    async_client: AsyncClient,
) -> None:
    owner, _admin, legacy_id = await _seed_many_invoices()
    ids, pages = await _collect_all_pages(
        async_client, "/seller-billing/invoices", _headers(owner)
    )
    assert pages >= 3, pages
    assert len(ids) == len(set(ids)), "дублирующиеся счета между страницами"
    assert len(ids) == _TOTAL_V2_INVOICES + 1, (len(ids), _TOTAL_V2_INVOICES + 1)
    assert str(legacy_id) in ids  # самый старый счёт не потерян


async def test_ff_invoice_history_pagination_does_not_lose_older_invoices(
    async_client: AsyncClient,
) -> None:
    _owner, admin, legacy_id = await _seed_many_invoices()
    ids, pages = await _collect_all_pages(
        async_client, "/billing/invoices-v2", _headers(admin)
    )
    assert pages >= 3, pages
    assert len(ids) == len(set(ids)), "дублирующиеся счета между страницами"
    assert len(ids) == _TOTAL_V2_INVOICES + 1, (len(ids), _TOTAL_V2_INVOICES + 1)
    assert str(legacy_id) in ids
