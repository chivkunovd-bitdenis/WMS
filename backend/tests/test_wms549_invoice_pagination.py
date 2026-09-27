"""WMS-549 · регресс на F3 (ревью Astra №1 и №2): «Загрузить ещё» не должно
терять и переставлять местами счета в объединённой истории (legacy + V2).

Проход №1 нашёл, что курсор применялся в Python уже после того, как каждый
SQL-запрос забирал только верхний срез `limit+1` из своей таблицы, — окно
выборки не двигалось между страницами. Ослабленная граница `issued_at <=
курсора` из первого исправления сдвигала окно, но при СОВПАДАЮЩИХ датах
выставления снова целиком заполняла `limit+1` уже показанными строками той
же группы — Python вычищал их все, и `next_cursor` обнулялся раньше времени.
Второе исправление ставит в SQL точную границу «строго после курсора» с
учётом origin своей ветки (см. `_seek_where` в billing_invoice_v2_service.py)
и согласует сортировку `id DESC` с тем же порядком, что использует Python
(`_sort_key`) — иначе LIMIT мог бы взять произвольное, а не «первое по
порядку» подмножество внутри группы совпадений.

Каждый сценарий сравнивает не число страниц, а ПОЛНЫЙ упорядоченный список
id, независимо вычисленный по той же формуле (issued_at, origin, id по
убыванию) — «проверка от обратного»: если бы функция теряла, дублировала
или переставляла счета, порядок разошёлся бы с эталоном. Общий для ФФ и
раздела селлера дефект, поэтому каждый сценарий проверяется через обе ручки:
/billing/invoices-v2 (ФФ) и /seller-billing/invoices (селлер). Поведение ФФ,
кроме исправления потерь, не меняется.
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

_BASE_ISSUED_AT = datetime(2026, 9, 1, tzinfo=UTC)
_PAGE_LIMIT = 20


async def _seed_invoices(
    *,
    legacy_specs: list[datetime],
    v2_specs: list[datetime],
) -> tuple[User, User, list[str]]:
    """Заводит один legacy-счёт на каждую дату из `legacy_specs` и один V2-счёт
    на каждую дату из `v2_specs`; возвращает пользователей и независимо
    вычисленный ЭТАЛОННЫЙ порядок id (issued_at, origin, id — все по убыванию,
    та же формула, что `_sort_key` в billing_invoice_v2_service.py).
    """
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

        entries: list[tuple[str, str, datetime]] = []
        for index, issued_at in enumerate(legacy_specs):
            invoice_id = uuid.uuid4()
            session.add(
                BillingInvoice(
                    id=invoice_id, tenant_id=tenant.id, seller_id=seller.id,
                    number=f"F3-LEG-{index:03d}", period=date(2020, 1, 1), status="issued",
                    total_amount=Decimal("1.00"), ff_profile_snapshot={},
                    seller_profile_snapshot={}, lines=[], issued_at=issued_at,
                )
            )
            entries.append((str(invoice_id), "legacy", issued_at))
        for index, issued_at in enumerate(v2_specs):
            invoice_id = uuid.uuid4()
            session.add(
                BillingInvoiceV2(
                    id=invoice_id, tenant_id=tenant.id, seller_id=seller.id,
                    number=f"F3-V2-{index:03d}", creation_mode="manual", status="issued",
                    ff_profile_snapshot={}, seller_profile_snapshot={},
                    total_amount_kopecks=100 + index, issued_at=issued_at,
                )
            )
            entries.append((str(invoice_id), "v2", issued_at))
        await session.commit()

    expected_order = [
        entry[0]
        for entry in sorted(entries, key=lambda entry: (entry[2], entry[1], entry[0]), reverse=True)
    ]
    return owner, admin, expected_order


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


async def _assert_full_history_matches(
    async_client: AsyncClient, url: str, headers: dict[str, str], expected_order: list[str]
) -> None:
    actual_order, pages = await _collect_all_pages(async_client, url, headers)
    assert pages >= 3, pages
    # Полный список и порядок, а не только количество: если бы функция
    # теряла, задваивала или переставляла счета местами, списки бы разошлись.
    assert actual_order == expected_order, (
        f"missing={set(expected_order) - set(actual_order)}, "
        f"extra={set(actual_order) - set(expected_order)}, "
        f"order_mismatch={actual_order != expected_order}"
    )


async def test_distinct_issued_at_pagination_does_not_lose_older_invoices(
    async_client: AsyncClient,
) -> None:
    """Базовый случай без совпадений дат — контроль, что обычная дочитка исправна."""
    owner, _admin, expected = await _seed_invoices(
        legacy_specs=[_BASE_ISSUED_AT - timedelta(days=1)],
        v2_specs=[_BASE_ISSUED_AT + timedelta(minutes=i) for i in range(61)],
    )
    await _assert_full_history_matches(
        async_client, "/seller-billing/invoices", _headers(owner), expected
    )


async def test_ff_distinct_issued_at_pagination_does_not_lose_older_invoices(
    async_client: AsyncClient,
) -> None:
    _owner, admin, expected = await _seed_invoices(
        legacy_specs=[_BASE_ISSUED_AT - timedelta(days=1)],
        v2_specs=[_BASE_ISSUED_AT + timedelta(minutes=i) for i in range(61)],
    )
    await _assert_full_history_matches(
        async_client, "/billing/invoices-v2", _headers(admin), expected
    )


async def test_large_group_of_identical_v2_dates_is_not_truncated(
    async_client: AsyncClient,
) -> None:
    """61 V2-счёт с ОДНОЙ и той же датой (больше одной страницы) + более
    старый legacy: раньше терялось 40 из 62 (проход №2 ревью, F3)."""
    owner, _admin, expected = await _seed_invoices(
        legacy_specs=[_BASE_ISSUED_AT - timedelta(days=1)],
        v2_specs=[_BASE_ISSUED_AT] * 61,
    )
    await _assert_full_history_matches(
        async_client, "/seller-billing/invoices", _headers(owner), expected
    )
    _owner2, admin2, expected2 = await _seed_invoices(
        legacy_specs=[_BASE_ISSUED_AT - timedelta(days=1)],
        v2_specs=[_BASE_ISSUED_AT] * 61,
    )
    await _assert_full_history_matches(
        async_client, "/billing/invoices-v2", _headers(admin2), expected2
    )


async def test_legacy_and_v2_sharing_the_exact_same_date_are_not_truncated(
    async_client: AsyncClient,
) -> None:
    """legacy тоже имеет ровно ту же дату, что все 61 V2-счёт — смешанная
    группа совпадений из обеих таблиц (проход №2 ревью, F3)."""
    owner, _admin, expected = await _seed_invoices(
        legacy_specs=[_BASE_ISSUED_AT], v2_specs=[_BASE_ISSUED_AT] * 61,
    )
    await _assert_full_history_matches(
        async_client, "/seller-billing/invoices", _headers(owner), expected
    )
    _owner2, admin2, expected2 = await _seed_invoices(
        legacy_specs=[_BASE_ISSUED_AT], v2_specs=[_BASE_ISSUED_AT] * 61,
    )
    await _assert_full_history_matches(
        async_client, "/billing/invoices-v2", _headers(admin2), expected2
    )


async def test_small_groups_of_identical_dates_on_page_boundaries_are_not_truncated(
    async_client: AsyncClient,
) -> None:
    """Маленькие группы по три совпадающих даты, включая границы страниц
    limit=20 (индексы 57-59 и 60 приходятся на конец истории; проход №2
    ревью, F3 — там терялось 3 из 62)."""
    v2_specs = [_BASE_ISSUED_AT + timedelta(minutes=index // 3) for index in range(61)]
    owner, _admin, expected = await _seed_invoices(
        legacy_specs=[_BASE_ISSUED_AT - timedelta(days=1)], v2_specs=v2_specs,
    )
    await _assert_full_history_matches(
        async_client, "/seller-billing/invoices", _headers(owner), expected
    )
    _owner2, admin2, expected2 = await _seed_invoices(
        legacy_specs=[_BASE_ISSUED_AT - timedelta(days=1)], v2_specs=v2_specs,
    )
    await _assert_full_history_matches(
        async_client, "/billing/invoices-v2", _headers(admin2), expected2
    )
