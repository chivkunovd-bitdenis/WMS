from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.api.billing import _matrix_out
from app.db.session import SessionLocal
from app.models.billing import BillingLedgerEntry, BillingTariffVersion
from app.models.tenant import Tenant


async def _register_admin(async_client: AsyncClient, label: str) -> dict[str, str]:
    suffix = f"{label}-{time.time_ns()}"
    response = await async_client.post(
        "/auth/register",
        json={
            "organization_name": f"Billing {label}",
            "slug": suffix,
            "admin_email": f"{suffix}@example.com",
            "password": "password123",
        },
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _ff_profile() -> dict[str, str]:
    return {
        "legal_name": "Фулфилмент",
        "inn": "7707083893",
        "bank_name": "Банк",
        "bik": "044525225",
        "settlement_account": "40702810000000000001",
        "correspondent_account": "30101810400000000225",
    }


@pytest.mark.asyncio
async def test_billing_configuration_api_validates_profiles_tariffs_and_tenant_boundary(
    async_client: AsyncClient,
) -> None:
    owner_headers = await _register_admin(async_client, "owner")
    other_headers = await _register_admin(async_client, "other")
    foreign_seller = await async_client.post(
        "/sellers", headers=other_headers, json={"name": "Чужой селлер"}
    )
    assert foreign_seller.status_code == 201, foreign_seller.text
    foreign_seller_id = uuid.UUID(foreign_seller.json()["id"])

    invalid_ff = await async_client.put(
        "/billing/profiles/ff",
        headers=owner_headers,
        json={**_ff_profile(), "bank_name": "   "},
    )
    assert invalid_ff.status_code == 400
    assert invalid_ff.json()["detail"] == "Для реквизитов ФФ заполните банковские поля"

    saved_ff = await async_client.put(
        "/billing/profiles/ff", headers=owner_headers, json=_ff_profile()
    )
    assert saved_ff.status_code == 200, saved_ff.text
    assert saved_ff.json()["bank_name"] == "Банк"

    invalid_inn = await async_client.put(
        "/billing/profiles/ff",
        headers=owner_headers,
        json={**_ff_profile(), "legal_name": "Не должно сохраниться", "inn": "7707083894"},
    )
    assert invalid_inn.status_code == 400
    assert invalid_inn.json()["detail"] == "Проверьте ИНН: контрольное число не совпадает"
    unchanged_ff = await async_client.get("/billing/profiles/ff", headers=owner_headers)
    assert unchanged_ff.status_code == 200
    assert unchanged_ff.json()["legal_name"] == "Фулфилмент"
    assert unchanged_ff.json()["inn"] == "7707083893"

    foreign_profile = await async_client.put(
        f"/billing/profiles/sellers/{foreign_seller_id}",
        headers=owner_headers,
        json={"legal_name": "Чужой", "inn": "7707083893"},
    )
    assert foreign_profile.status_code == 400
    assert foreign_profile.json()["detail"] == "Селлер не найден в текущем tenant"

    tariff = {
        "service_code": "inbound",
        "unit": "document",
        "amount": "0.00",
        "valid_from": "2026-09-01",
    }
    created = await async_client.post("/billing/tariffs", headers=owner_headers, json=tariff)
    assert created.status_code == 201, created.text
    assert created.json()["amount"] == 0

    future_tariff = await async_client.post(
        "/billing/tariffs",
        headers=owner_headers,
        json={**tariff, "amount": "45.00", "valid_from": "2026-11-01"},
    )
    assert future_tariff.status_code == 201, future_tariff.text
    assert future_tariff.json()["amount"] == 4500

    async with SessionLocal() as session:
        persisted_tariffs = (
            await session.scalars(
                select(BillingTariffVersion).where(
                    BillingTariffVersion.id.in_(
                        (uuid.UUID(created.json()["id"]), uuid.UUID(future_tariff.json()["id"]))
                    )
                )
            )
        ).all()
    assert {tariff.amount for tariff in persisted_tariffs} == {0, 4500}

    for invalid_amount in ("-0.01", "45.001"):
        invalid_amount_response = await async_client.post(
            "/billing/tariffs",
            headers=owner_headers,
            json={**tariff, "amount": invalid_amount, "valid_from": "2026-12-01"},
        )
        assert invalid_amount_response.status_code == 422

    conflicting = await async_client.post(
        "/billing/tariffs",
        headers=owner_headers,
        json={**tariff, "amount": "10.00", "valid_from": "2026-10-01"},
    )
    assert conflicting.status_code == 400
    assert conflicting.json()["detail"] == "Дата пересекает будущую версию ставки"

    tariffs = await async_client.get("/billing/tariffs", headers=owner_headers)
    assert tariffs.status_code == 200
    assert [item["valid_from"] for item in tariffs.json()] == ["2026-11-01", "2026-09-01"]
    assert [item["valid_to"] for item in tariffs.json()] == [None, "2026-10-31"]
    assert [item["amount"] for item in tariffs.json()] == [4500, 0]


@pytest.mark.asyncio
async def test_tariff_matrix_api_is_explicit_tenant_scoped_and_atomic(
    async_client: AsyncClient,
) -> None:
    headers = await _register_admin(async_client, "matrix-api")
    matrix = await async_client.get("/billing/tariff-matrix", headers=headers)
    assert matrix.status_code == 200, matrix.text
    assert {row["service_code"] for row in matrix.json()["services"]} == {
        "inbound",
        "marketplace_outbound",
        "packing",
        "return",
        "storage",
    }
    assert not any(row["enabled"] for row in matrix.json()["services"])
    # Хранение считается за литро-день, остальные услуги — за штуку.
    assert {row["unit"] for row in matrix.json()["services"]} == {"item", "liter_day"}
    saved = await async_client.put(
        "/billing/tariff-matrix",
        headers=headers,
        json={
            "revision": matrix.json()["revision"],
            "services": [
                {"service_code": "inbound", "enabled": True},
                {"service_code": "marketplace_outbound", "enabled": False},
                {"service_code": "packing", "enabled": False},
                {"service_code": "return", "enabled": False},
                {"service_code": "storage", "enabled": False},
            ],
            "versions": [],
        },
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["revision"] == 1
    stale = await async_client.put(
        "/billing/tariff-matrix",
        headers=headers,
        json={**saved.json(), "revision": 0, "versions": []},
    )
    assert stale.status_code == 400
    unchanged = await async_client.get("/billing/tariff-matrix", headers=headers)
    assert unchanged.json()["revision"] == 1


@pytest.mark.asyncio
async def test_tariff_matrix_api_returns_and_atomically_persists_full_versioned_draft(
    async_client: AsyncClient,
) -> None:
    headers = await _register_admin(async_client, "matrix-full-draft")
    initial = await async_client.get("/billing/tariff-matrix", headers=headers)
    assert initial.status_code == 200, initial.text
    assert initial.json()["versions"] == []
    assert initial.json()["storage"] == {
        "mode": "legacy_daily",
        "editable_in_matrix": False,
    }

    draft = {
        "revision": initial.json()["revision"],
        "services": [
            {"service_code": "inbound", "enabled": True},
            {"service_code": "marketplace_outbound", "enabled": False},
            {"service_code": "packing", "enabled": False},
            {"service_code": "return", "enabled": False},
            {"service_code": "storage", "enabled": False},
        ],
        "versions": [
            {
                "service_code": "inbound",
                "unit": "document",
                "enabled": True,
                "rate": 1250,
                "valid_from_at": "2026-08-27T09:00:00Z",
            }
        ],
    }
    saved = await async_client.put("/billing/tariff-matrix", headers=headers, json=draft)
    assert saved.status_code == 200, saved.text
    assert saved.json()["revision"] == 1
    assert saved.json()["versions"] == [
        {
            "seller_id": None,
            "product_id": None,
            "employee_user_id": None,
            "service_code": "inbound",
            "unit": "document",
            "enabled": True,
            "rate": 1250,
            "valid_from_at": "2026-08-27T09:00:00Z",
            "valid_to_at": None,
        }
    ]

    invalid = await async_client.put(
        "/billing/tariff-matrix",
        headers=headers,
        json={
            **draft,
            "revision": 1,
            "versions": [
                draft["versions"][0],
                {
                    "service_code": "storage_liter_day",
                    "unit": "item",
                    "enabled": True,
                    "rate": 10,
                    "valid_from_at": "2026-08-27T10:00:00Z",
                },
            ],
        },
    )
    assert invalid.status_code == 400
    after_invalid = await async_client.get("/billing/tariff-matrix", headers=headers)
    assert after_invalid.json()["revision"] == 1
    assert after_invalid.json()["versions"] == saved.json()["versions"]

    overflow = await async_client.put(
        "/billing/tariff-matrix",
        headers=headers,
        json={
            **draft,
            "revision": 1,
            "versions": [
                {
                    **draft["versions"][0],
                    "rate": 2_147_483_648,
                }
            ],
        },
    )
    assert overflow.status_code == 422
    after_overflow = await async_client.get("/billing/tariff-matrix", headers=headers)
    assert after_overflow.json()["revision"] == 1
    assert after_overflow.json()["versions"] == saved.json()["versions"]


@pytest.mark.asyncio
async def test_tariff_matrix_api_persists_product_and_employee_rates_without_cross_tenant_leak(
    async_client: AsyncClient,
) -> None:
    headers = await _register_admin(async_client, "matrix-scopes")
    seller = await async_client.post("/sellers", headers=headers, json={"name": "Matrix seller"})
    assert seller.status_code == 201, seller.text
    product = await async_client.post(
        "/products",
        headers=headers,
        json={
            "name": "Matrix product",
            "sku_code": f"matrix-{uuid.uuid4().hex}",
            "seller_id": seller.json()["id"],
        },
    )
    assert product.status_code == 200, product.text
    employee = await async_client.post(
        "/auth/staff-accounts",
        headers=headers,
        json={"email": f"matrix-{uuid.uuid4().hex}@example.com"},
    )
    assert employee.status_code == 201, employee.text
    initial = await async_client.get("/billing/tariff-matrix", headers=headers)
    assert initial.status_code == 200, initial.text

    payload = {
        "revision": initial.json()["revision"],
        "services": [
            {"service_code": "inbound", "enabled": True},
            {"service_code": "marketplace_outbound", "enabled": False},
            {"service_code": "packing", "enabled": False},
            {"service_code": "return", "enabled": False},
            {"service_code": "storage", "enabled": False},
        ],
        "versions": [
            {
                "service_code": "inbound",
                "unit": "item",
                "enabled": True,
                "rate": 1000,
                "valid_from_at": "2026-08-27T09:00:00Z",
            },
            {
                "seller_id": seller.json()["id"],
                "product_id": product.json()["id"],
                "service_code": "inbound",
                "unit": "item",
                "enabled": True,
                "rate": 175,
                "valid_from_at": "2026-08-27T09:00:00Z",
            },
            {
                "employee_user_id": employee.json()["id"],
                "service_code": "inbound",
                "unit": "item",
                "enabled": True,
                "rate": 55,
                "valid_from_at": "2026-08-27T09:00:00Z",
            },
        ],
    }
    saved = await async_client.put("/billing/tariff-matrix", headers=headers, json=payload)
    assert saved.status_code == 200, saved.text
    assert saved.json()["revision"] == 1
    assert {row["rate"] for row in saved.json()["versions"]} == {55, 175, 1000}
    assert saved.json()["products"] == [
        {
            "id": product.json()["id"],
            "seller_id": seller.json()["id"],
            "seller_name": "Matrix seller",
            "sku": product.json()["sku_code"],
            "name": "Matrix product",
            "label": f"Matrix seller · {product.json()['sku_code']} · Matrix product",
        }
    ]
    assert saved.json()["storage"] == {"mode": "legacy_daily", "editable_in_matrix": False}

    retry = await async_client.put(
        "/billing/tariff-matrix",
        headers=headers,
        json={"revision": 1, "services": payload["services"], "versions": saved.json()["versions"]},
    )
    assert retry.status_code == 200, retry.text
    assert retry.json()["revision"] == 1

    foreign_headers = await _register_admin(async_client, "matrix-scopes-foreign")
    foreign_seller = await async_client.post(
        "/sellers", headers=foreign_headers, json={"name": "Foreign seller"}
    )
    foreign_product = await async_client.post(
        "/products",
        headers=foreign_headers,
        json={
            "name": "Foreign product",
            "sku_code": f"foreign-{uuid.uuid4().hex}",
            "seller_id": foreign_seller.json()["id"],
        },
    )
    assert foreign_product.status_code == 200, foreign_product.text
    rejected = await async_client.put(
        "/billing/tariff-matrix",
        headers=headers,
        json={
            **payload,
            "revision": 1,
            "versions": [
                {
                    **payload["versions"][1],
                    "product_id": foreign_product.json()["id"],
                }
            ],
        },
    )
    assert rejected.status_code == 400
    assert rejected.json()["detail"] == "billing_tariff_matrix_product_not_found"
    after_rejected = await async_client.get("/billing/tariff-matrix", headers=headers)
    assert after_rejected.json()["revision"] == 1
    assert {row["rate"] for row in after_rejected.json()["versions"]} == {55, 175, 1000}


@pytest.mark.asyncio
async def test_tariff_matrix_rate_edit_closes_old_interval_and_rejects_document_product_override(
    async_client: AsyncClient,
) -> None:
    headers = await _register_admin(async_client, "matrix-version-edit")
    seller = await async_client.post("/sellers", headers=headers, json={"name": "Version seller"})
    product = await async_client.post(
        "/products",
        headers=headers,
        json={
            "name": "Version product",
            "sku_code": f"version-{uuid.uuid4().hex}",
            "seller_id": seller.json()["id"],
        },
    )
    initial = await async_client.get("/billing/tariff-matrix", headers=headers)
    services = [
        {"service_code": "inbound", "enabled": True},
        {"service_code": "marketplace_outbound", "enabled": False},
        {"service_code": "packing", "enabled": False},
        {"service_code": "return", "enabled": False},
        {"service_code": "storage", "enabled": False},
    ]
    first = {
        "service_code": "inbound",
        "unit": "item",
        "enabled": True,
        "rate": 1000,
        "valid_from_at": "2026-08-27T09:00:00Z",
    }
    created = await async_client.put(
        "/billing/tariff-matrix",
        headers=headers,
        json={"revision": initial.json()["revision"], "services": services, "versions": [first]},
    )
    assert created.status_code == 200, created.text
    edited = await async_client.put(
        "/billing/tariff-matrix",
        headers=headers,
        json={
            "revision": 1,
            "services": services,
            "versions": [
                first,
                {**first, "rate": 1500, "valid_from_at": "2026-08-27T10:00:00Z"},
            ],
        },
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["revision"] == 2
    assert [(row["rate"], row["valid_to_at"]) for row in edited.json()["versions"]] == [
        (1000, "2026-08-27T10:00:00Z"),
        (1500, None),
    ]
    inserted = await async_client.put(
        "/billing/tariff-matrix",
        headers=headers,
        json={
            "revision": 2,
            "services": services,
            "versions": [
                *edited.json()["versions"],
                {**first, "rate": 900, "valid_from_at": "2026-08-27T08:00:00Z"},
            ],
        },
    )
    assert inserted.status_code == 200, inserted.text
    assert inserted.json()["revision"] == 3
    assert (900, "2026-08-27T09:00:00Z") in [
        (row["rate"], row["valid_to_at"]) for row in inserted.json()["versions"]
    ]

    invalid_override = await async_client.put(
        "/billing/tariff-matrix",
        headers=headers,
        json={
            "revision": 3,
            "services": services,
            "versions": [
                *inserted.json()["versions"],
                {
                    "service_code": "inbound",
                    "unit": "document",
                    "enabled": True,
                    "rate": 1200,
                    "valid_from_at": "2026-08-27T11:00:00Z",
                },
                {
                    "seller_id": seller.json()["id"],
                    "product_id": product.json()["id"],
                    "service_code": "inbound",
                    "unit": "item",
                    "enabled": True,
                    "rate": 175,
                    "valid_from_at": "2026-08-27T11:00:00Z",
                },
            ],
        },
    )
    assert invalid_override.status_code == 400
    assert invalid_override.json()["detail"] == "billing_tariff_matrix_product_requires_item"
    after_invalid = await async_client.get("/billing/tariff-matrix", headers=headers)
    assert after_invalid.json()["revision"] == 3


def test_matrix_out_uses_interval_active_common_not_a_future_version() -> None:
    """A scheduled rate is returned as history until its Moscow/UTC interval begins."""
    config = SimpleNamespace(
        revision=7,
        service_states=[SimpleNamespace(service_code="inbound", enabled=True)],
    )
    current = SimpleNamespace(
        seller_id=None,
        product_id=None,
        employee_user_id=None,
        service_code="inbound",
        unit="item",
        enabled=True,
        rate=125,
        valid_from_at=datetime(2026, 8, 27, 9, tzinfo=UTC),
        valid_to_at=datetime(2026, 9, 1, 9, tzinfo=UTC),
    )
    future = SimpleNamespace(
        seller_id=None,
        product_id=None,
        employee_user_id=None,
        service_code="inbound",
        unit="document",
        enabled=True,
        rate=900,
        valid_from_at=datetime(2026, 9, 1, 9, tzinfo=UTC),
        valid_to_at=None,
    )

    before = _matrix_out(
        config, [current, future], [], [], now=datetime(2026, 8, 31, 12, tzinfo=UTC)
    )
    after = _matrix_out(
        config, [current, future], [], [], now=datetime(2026, 9, 1, 9, tzinfo=UTC)
    )

    assert before["services"] == [
        {
            "service_code": "inbound",
            "enabled": True,
            "unit": "item",
            "rate": 125,
            "valid_from_at": datetime(2026, 8, 27, 9, tzinfo=UTC),
        }
    ]
    assert after["services"][0]["unit"] == "document"
    assert after["services"][0]["rate"] == 900


@pytest.mark.asyncio
async def test_creating_covering_tariffs_reprices_unpriced_entries_in_kopecks(
    async_client: AsyncClient,
) -> None:
    headers = await _register_admin(async_client, "repricing")
    warehouse_response = await async_client.post(
        "/warehouses",
        headers=headers,
        json={"name": "Billing repricing warehouse", "code": f"billing-{uuid.uuid4().hex[:8]}"},
    )
    assert warehouse_response.status_code == 200, warehouse_response.text
    warehouse_id = uuid.UUID(warehouse_response.json()["id"])

    async with SessionLocal() as session:
        tenant_id = await session.scalar(
            select(Tenant.id).where(Tenant.name == "Billing repricing")
        )
        assert tenant_id is not None
        entries = {
            "document": BillingLedgerEntry(
                tenant_id=tenant_id,
                service_code="inbound",
                source="inbound",
                source_type="repricing-document",
                source_id=uuid.uuid4(),
                unit="document",
                quantity=Decimal("7"),
                occurred_at=datetime(2026, 9, 2, 12, tzinfo=UTC),
            ),
            "item": BillingLedgerEntry(
                tenant_id=tenant_id,
                service_code="marketplace_outbound",
                source="marketplace_outbound",
                source_type="repricing-item",
                source_id=uuid.uuid4(),
                unit="item",
                quantity=Decimal("2.5"),
                occurred_at=datetime(2026, 9, 2, 12, tzinfo=UTC),
            ),
            "liter_day": BillingLedgerEntry(
                tenant_id=tenant_id,
                warehouse_id=warehouse_id,
                service_code="storage_liter_day",
                source="storage_measurement",
                source_type="repricing-liter-day",
                source_id=uuid.uuid4(),
                unit="liter_day",
                quantity=Decimal("12.5"),
                occurred_at=datetime(2026, 9, 2, 12, tzinfo=UTC),
            ),
        }
        session.add_all(entries.values())
        await session.commit()
        entry_ids = {name: entry.id for name, entry in entries.items()}

    tariffs = (
        ("inbound", "document", "45.00", None),
        ("marketplace_outbound", "item", "12.34", None),
        ("storage_liter_day", "liter_day", "0.15", warehouse_id),
    )
    tariff_ids: dict[str, uuid.UUID] = {}
    for service_code, unit, amount, tariff_warehouse_id in tariffs:
        response = await async_client.post(
            "/billing/tariffs",
            headers=headers,
            json={
                "service_code": service_code,
                "unit": unit,
                "amount": amount,
                "valid_from": "2026-09-01",
                "warehouse_id": str(tariff_warehouse_id) if tariff_warehouse_id else None,
            },
        )
        assert response.status_code == 201, response.text
        tariff_ids[unit] = uuid.UUID(response.json()["id"])

    async with SessionLocal() as session:
        repriced = {
            name: await session.get(BillingLedgerEntry, entry_id)
            for name, entry_id in entry_ids.items()
        }
        await session.flush()

    document = repriced["document"]
    assert document is not None
    assert document.tariff_version_id == tariff_ids["document"]
    assert document.unit == "document"
    assert document.quantity == Decimal("1")
    assert isinstance(document.rate, int) and document.rate == 4500
    assert isinstance(document.amount, int) and document.amount == 4500

    item = repriced["item"]
    assert item is not None
    assert item.tariff_version_id == tariff_ids["item"]
    assert item.unit == "item"
    assert item.quantity == Decimal("2.5")
    assert isinstance(item.rate, int) and item.rate == 1234
    assert isinstance(item.amount, int) and item.amount == 3085

    liter_day = repriced["liter_day"]
    assert liter_day is not None
    assert liter_day.tariff_version_id == tariff_ids["liter_day"]
    assert liter_day.unit == "liter_day"
    assert liter_day.quantity == Decimal("12.5")
    assert isinstance(liter_day.rate, int) and liter_day.rate == 15
    assert isinstance(liter_day.amount, int) and liter_day.amount == 188


@pytest.mark.asyncio
async def test_tariff_and_repricing_overflow_are_rejected_without_partial_state(
    async_client: AsyncClient,
) -> None:
    rate_headers = await _register_admin(async_client, "rate-overflow")

    largest = await async_client.post(
        "/billing/tariffs",
        headers=rate_headers,
        json={
            "service_code": "inbound",
            "unit": "document",
            "amount": "21474836.47",
            "valid_from": "2026-09-01",
        },
    )
    assert largest.status_code == 201, largest.text
    assert largest.json()["amount"] == 2_147_483_647

    too_large = await async_client.post(
        "/billing/tariffs",
        headers=rate_headers,
        json={
            "service_code": "marketplace_outbound",
            "unit": "document",
            "amount": "21474836.48",
            "valid_from": "2026-09-01",
        },
    )
    assert too_large.status_code == 400
    assert "Ставка слишком велика" in too_large.json()["detail"]

    reprice_headers = await _register_admin(async_client, "reprice-overflow")
    async with SessionLocal() as session:
        tenant = await session.scalar(
            select(Tenant).where(Tenant.name == "Billing reprice-overflow")
        )
        assert tenant is not None
        entry = BillingLedgerEntry(
            tenant_id=tenant.id,
            service_code="marketplace_outbound",
            source="marketplace_unload",
            source_type="overflow-repricing",
            source_id=uuid.uuid4(),
            unit="item",
            quantity=Decimal("2"),
            occurred_at=datetime(2026, 9, 2, 12, tzinfo=UTC),
        )
        session.add(entry)
        await session.commit()
        entry_id = entry.id
        tenant_id = tenant.id

    overflow_repricing = await async_client.post(
        "/billing/tariffs",
        headers=reprice_headers,
        json={
            "service_code": "marketplace_outbound",
            "unit": "item",
            "amount": "10737418.24",
            "valid_from": "2026-09-01",
        },
    )
    assert overflow_repricing.status_code == 400
    assert "Сумма дооценки слишком велика" in overflow_repricing.json()["detail"]

    async with SessionLocal() as session:
        unchanged_entry = await session.get(BillingLedgerEntry, entry_id)
        unchanged_tenant = await session.get(Tenant, tenant_id)
        tariffs = (
            await session.scalars(
                select(BillingTariffVersion).where(BillingTariffVersion.tenant_id == tenant_id)
            )
        ).all()

    assert unchanged_entry is not None
    assert unchanged_entry.tariff_version_id is None
    assert unchanged_entry.rate is None
    assert unchanged_entry.amount is None
    assert unchanged_tenant is not None
    assert unchanged_tenant.billing_enabled_from is None
    assert tariffs == []
