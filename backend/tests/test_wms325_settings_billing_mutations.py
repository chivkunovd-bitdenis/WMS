"""WMS-325: audited existing settings/billing transactions, synthetic PostgreSQL only."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select, text

from app.db.session import SessionLocal, engine
from app.models.billing import (
    BillingInvoice,
    BillingInvoiceV2,
    BillingLedgerEntry,
    BillingProfile,
    BillingTariffVersion,
    BillingTariffVersionV2,
)
from app.models.document_event import DocumentEvent
from app.models.operation_fact import OperationFact
from app.models.user import User
from app.services import billing_configuration_service as configuration
from app.services import billing_invoice_service as legacy
from app.services import document_event_service as audit
from app.services import storage_statement_service as storage
from app.services import tenant_settings_service as tenant_settings
from app.services.billing_tariff_matrix_service import MATRIX_SERVICE_CODES
from tests.test_billing_configuration_api import _ff_profile
from tests.test_billing_invoice_api import _add_priced_ledger_entry, _billing_context
from tests.test_document_events import _register_admin


async def seed(client: AsyncClient) -> tuple[dict[str, str], uuid.UUID, uuid.UUID, uuid.UUID]:
    headers, claims = await _register_admin(client)
    created = await client.post(
        "/sellers", headers=headers, json={"name": "Synthetic WMS325 seller"}
    )
    assert created.status_code == 201, created.text
    return (
        headers,
        uuid.UUID(str(claims["tenant_id"])),
        uuid.UUID(str(claims["sub"])),
        uuid.UUID(created.json()["id"]),
    )


async def history(
    client: AsyncClient, headers: dict[str, str], kind: str, doc_id: uuid.UUID | str
) -> list[dict[str, Any]]:
    response = await client.get(
        "/operations/document-events",
        headers=headers,
        params={"document_type": kind, "document_id": str(doc_id)},
    )
    assert response.status_code == 200, response.text
    return list(reversed(response.json()))


async def test_settings_all_fields_noop_authenticated_actor_and_admin_only_history(
    async_client: AsyncClient,
) -> None:
    h, tenant_id, actor_id, seller_id = await seed(async_client)
    body = {
        "address_storage_enabled": False,
        "separate_marking_print_enabled": True,
        "fbs_shipment_cutoff_time": "17:40:00",
        "actor_user_id": str(uuid.uuid4()),
        "unrelated_text": "MUST-NOT-BE-SERIALIZED",
    }
    for _ in range(2):
        response = await async_client.patch("/tenant/settings", headers=h, json=body)
        assert response.status_code == 200, response.text
    rows = await history(async_client, h, "tenant_settings", tenant_id)
    assert len(rows) == 1
    assert rows[0]["payload"]["before"] == {
        "address_storage_enabled": True,
        "separate_marking_print_enabled": False,
        "fbs_shipment_cutoff_time": None,
    }
    assert rows[0]["payload"]["after"] == {
        "address_storage_enabled": False,
        "separate_marking_print_enabled": True,
        "fbs_shipment_cutoff_time": "17:40:00",
    }
    assert rows[0]["actor"]["id"] == str(actor_id) and rows[0]["source"] == "user"
    response = await async_client.patch(
        "/tenant/settings", headers=h, json={"fbs_shipment_cutoff_time": None}
    )
    assert response.status_code == 200, response.text
    assert len(await history(async_client, h, "tenant_settings", tenant_id)) == 2
    other_h, _ = await _register_admin(async_client)
    assert await history(async_client, other_h, "tenant_settings", tenant_id) == []
    async with SessionLocal() as session:
        user = await session.get(User, actor_id)
        assert user is not None
        user.role = "fulfillment_seller"
        user.seller_id = seller_id
        await session.commit()
    for kind in (
        "tenant_settings",
        "billing_profile",
        "billing_tariff",
        "billing_tariff_matrix",
        "billing_invoice",
    ):
        denied = await async_client.get(
            "/operations/document-events",
            headers=h,
            params={"document_type": kind, "document_id": str(tenant_id)},
        )
        assert denied.status_code == 403, denied.text


@pytest.mark.parametrize("seller_profile", [False, True])
async def test_profiles_create_normalize_change_noop_invalid_snapshot(
    async_client: AsyncClient,
    seller_profile: bool,
) -> None:
    h, _, actor_id, seller_id = await seed(async_client)
    url = f"/billing/profiles/sellers/{seller_id}" if seller_profile else "/billing/profiles/ff"
    body = _ff_profile()
    body["legal_name"] = "  Synthetic legal name  "
    saved = await async_client.put(url, headers=h, json={**body, "notes": "EXCLUDED-NOTE"})
    assert saved.status_code == 200, saved.text
    profile_id = saved.json()["id"]
    again = await async_client.put(url, headers=h, json=body)
    assert again.status_code == 200, again.text
    rows = await history(async_client, h, "billing_profile", profile_id)
    assert len(rows) == 1 and rows[0]["payload"]["before"] is None
    assert rows[0]["payload"]["after"]["legal_name"] == "Synthetic legal name"
    assert rows[0]["payload"]["after"]["seller_id"] == (str(seller_id) if seller_profile else None)
    assert "EXCLUDED-NOTE" not in json.dumps(rows)
    invalid = await async_client.put(url, headers=h, json={**body, "inn": "invalid"})
    assert invalid.status_code == 400, invalid.text
    changed = await async_client.put(url, headers=h, json={**body, "kpp": " 123456789 "})
    assert changed.status_code == 200, changed.text
    rows = await history(async_client, h, "billing_profile", profile_id)
    assert len(rows) == 2
    assert rows[-1]["payload"]["before"]["kpp"] is None
    assert rows[-1]["payload"]["after"]["kpp"] == "123456789"
    old_name = rows[0]["actor"]["name"]
    async with SessionLocal() as session:
        user = await session.get(User, actor_id)
        assert user is not None
        user.email = "renamed-billing325@example.com"
        await session.commit()
    assert all(
        r["actor"]["name"] == old_name
        for r in await history(async_client, h, "billing_profile", profile_id)
    )
    other_h, _ = await _register_admin(async_client)
    foreign = await async_client.put(
        f"/billing/profiles/sellers/{seller_id}", headers=other_h, json=body
    )
    assert foreign.status_code == 400, foreign.text
    assert await history(async_client, other_h, "billing_profile", profile_id) == []


async def test_legacy_tariff_audits_new_and_closed_versions_without_extra_financial_fact(
    async_client: AsyncClient,
) -> None:
    h, tenant_id, actor_id, _ = await seed(async_client)
    body = {"service_code": "inbound", "unit": "item", "amount": "1.25", "valid_from": "2026-07-01"}
    first = await async_client.post("/billing/tariffs", headers=h, json=body)
    assert first.status_code == 201, first.text
    second = await async_client.post(
        "/billing/tariffs", headers=h, json={**body, "amount": "2.50", "valid_from": "2026-08-01"}
    )
    assert second.status_code == 201, second.text
    rejected = await async_client.post("/billing/tariffs", headers=h, json=body)
    assert rejected.status_code == 400, rejected.text
    rows = await history(async_client, h, "billing_tariff", tenant_id)
    assert len(rows) == 2
    assert rows[0]["payload"]["before"] == {"billing_enabled_from": None, "versions": []}
    assert rows[0]["payload"]["after"]["billing_enabled_from"] == "2026-07-01"
    assert rows[1]["payload"]["before"]["versions"][0]["valid_to"] is None
    versions = rows[1]["payload"]["after"]["versions"]
    assert versions[0]["version_id"] == first.json()["id"]
    assert versions[0]["valid_to"] == "2026-07-31" and versions[0]["amount_kopecks"] == 125
    assert versions[1]["version_id"] == second.json()["id"] and versions[1]["amount_kopecks"] == 250
    assert all(r["actor"]["id"] == str(actor_id) for r in rows)
    async with SessionLocal() as session:
        assert await session.scalar(select(func.count()).select_from(BillingTariffVersion)) == 2
        assert await session.scalar(select(func.count()).select_from(BillingLedgerEntry)) == 0
        assert await session.scalar(select(func.count()).select_from(OperationFact)) == 0


def matrix_body(revision: int, rate: int, start: str) -> dict[str, Any]:
    return {
        "revision": revision,
        "services": [
            {"service_code": code, "enabled": code == "inbound"} for code in MATRIX_SERVICE_CODES
        ],
        "versions": [
            {
                "seller_id": None,
                "product_id": None,
                "employee_user_id": None,
                "service_code": "inbound",
                "unit": "item",
                "enabled": True,
                "rate": rate,
                "valid_from_at": start,
                "valid_to_at": None,
            }
        ],
    }


async def test_matrix_versions_toggle_noop_and_invalid_batch_rollback(
    async_client: AsyncClient,
) -> None:
    h, tenant_id, actor_id, _ = await seed(async_client)
    first = await async_client.put(
        "/billing/tariff-matrix", headers=h, json=matrix_body(0, 100, "2026-07-01T00:00:00Z")
    )
    assert first.status_code == 200, first.text
    second_body = matrix_body(first.json()["revision"], 200, "2026-08-01T00:00:00Z")
    second = await async_client.put("/billing/tariff-matrix", headers=h, json=second_body)
    assert second.status_code == 200, second.text
    second_body["revision"] = second.json()["revision"]
    again = await async_client.put("/billing/tariff-matrix", headers=h, json=second_body)
    assert again.status_code == 200, again.text
    assert again.json()["revision"] == second.json()["revision"]
    rows = await history(async_client, h, "billing_tariff_matrix", tenant_id)
    assert len(rows) == 2
    after = rows[-1]["payload"]["after"]
    versions = sorted(after["versions"], key=lambda v: v["valid_from_at"])
    assert versions[0]["valid_to_at"] == "2026-08-01T00:00:00+00:00"
    assert versions[1]["rate_kopecks"] == 200
    assert after["billing_enabled_from"] == "2026-07-01"
    # First item would create a version; conflicting second item must roll back all changes.
    bad = matrix_body(second.json()["revision"], 300, "2026-09-01T00:00:00Z")
    bad["versions"].append({**bad["versions"][0], "rate": 400})
    rejected = await async_client.put("/billing/tariff-matrix", headers=h, json=bad)
    assert rejected.status_code == 400, rejected.text
    assert await history(async_client, h, "billing_tariff_matrix", tenant_id) == rows
    for enabled in (False, True):
        second_body["services"][0]["enabled"] = enabled
        changed = await async_client.put("/billing/tariff-matrix", headers=h, json=second_body)
        assert changed.status_code == 200, changed.text
        second_body["revision"] = changed.json()["revision"]
    rows = await history(async_client, h, "billing_tariff_matrix", tenant_id)
    assert len(rows) == 4 and all(r["actor"]["id"] == str(actor_id) for r in rows)
    async with SessionLocal() as session:
        assert await session.scalar(select(func.count()).select_from(BillingTariffVersionV2)) == 2
        assert await session.scalar(select(func.count()).select_from(BillingLedgerEntry)) == 0


async def test_storage_tariff_delegates_one_system_fact_and_noop(async_client: AsyncClient) -> None:
    h, tenant_id, actor_id, seller_id = await seed(async_client)
    start = datetime.now(UTC).date() + timedelta(days=2)
    async with SessionLocal() as session:
        with audit.document_event_actor(actor_id), audit.system_document_events():
            _, _, revision = await storage.create_storage_tariff(
                session,
                tenant_id,
                Decimal("1.00"),
                start,
                0,
                seller_exception=(seller_id, Decimal("2.00"), start),
            )
            await storage.create_storage_tariff(
                session,
                tenant_id,
                Decimal("1.00"),
                start,
                revision,
                seller_exception=(seller_id, Decimal("2.00"), start),
            )
    rows = await history(async_client, h, "billing_tariff_matrix", tenant_id)
    assert len(rows) == 1 and rows[0]["source"] == "system" and rows[0]["actor"] is None
    assert len(rows[0]["payload"]["after"]["versions"]) == 2
    assert "actor_name_snapshot" not in rows[0]["payload"]


async def test_invoice_v2_create_retry_and_distinct_cancel_actor_without_manual_text(
    async_client: AsyncClient,
) -> None:
    h, tenant_id, creator_id, seller_id = await seed(async_client)
    body = {
        "creation_mode": "manual",
        "seller_id": str(seller_id),
        "lines": [{"description": "DO-NOT-AUDIT-MANUAL-TEXT", "amount": "6.30"}],
        "actor_user_id": str(uuid.uuid4()),
    }
    invoice_headers = {**h, "Idempotency-Key": "synthetic-key-not-for-audit"}
    saved = await async_client.post("/billing/invoices-v2", headers=invoice_headers, json=body)
    assert saved.status_code == 201, saved.text
    iid = saved.json()["id"]
    retry = await async_client.post("/billing/invoices-v2", headers=invoice_headers, json=body)
    assert retry.status_code == 201 and retry.json()["id"] == iid
    rows = await history(async_client, h, "billing_invoice", iid)
    assert len(rows) == 1 and rows[0]["actor"]["id"] == str(creator_id)
    # Reuse another already authenticated synthetic user within this tenant; no password changes.
    _, second_claims = await _register_admin(async_client)
    cancel_id = uuid.UUID(str(second_claims["sub"]))
    async with SessionLocal() as session:
        creator = await session.get(User, creator_id)
        canceller = await session.get(User, cancel_id)
        assert creator is not None and canceller is not None
        canceller.tenant_id = creator.tenant_id
        await session.commit()
    # Its old token is tenant-bound, so use service context for the different authenticated actor.
    from app.services.billing_invoice_v2_service import cancel_invoice_v2

    async with SessionLocal() as session:
        with audit.document_event_actor(cancel_id):
            await cancel_invoice_v2(session, tenant_id=tenant_id, invoice_id=uuid.UUID(iid))
            await session.commit()
    for _ in range(2):
        response = await async_client.post(f"/billing/invoices-v2/{iid}/cancel", headers=h)
        assert response.status_code == 200, response.text
    rows = await history(async_client, h, "billing_invoice", iid)
    assert len(rows) == 2
    assert rows[1]["actor"]["id"] == str(cancel_id)
    assert rows[1]["payload"]["before"]["status"] == "issued"
    assert rows[1]["payload"]["after"]["status"] == "cancelled"
    assert rows[1]["payload"]["after"]["total_amount_kopecks"] == 630
    assert "DO-NOT-AUDIT-MANUAL-TEXT" not in json.dumps(rows)
    assert "synthetic-key-not-for-audit" not in json.dumps(rows)
    async with SessionLocal() as session:
        invoice = await session.get(BillingInvoiceV2, uuid.UUID(iid))
        assert invoice is not None and invoice.issued_by_user_id == creator_id
        assert await session.scalar(select(func.count()).select_from(OperationFact)) == 0


async def test_legacy_invoice_create_retry_cancel_and_amount_unchanged(
    async_client: AsyncClient,
) -> None:
    h, tenant_id, seller_id, _ = await _billing_context(async_client)
    await _add_priced_ledger_entry(tenant_id=tenant_id, seller_id=seller_id)
    form = f"/billing/invoices/{seller_id}/2026-07-01/form"
    saved = await async_client.post(form, headers=h)
    assert saved.status_code == 200, saved.text
    iid = saved.json()["id"]
    retry = await async_client.post(form, headers=h)
    assert retry.status_code == 200 and retry.json()["id"] == iid
    for _ in range(2):
        response = await async_client.post(f"/billing/invoices/{iid}/cancel", headers=h)
        assert response.status_code == 200, response.text
    rows = await history(async_client, h, "billing_invoice", iid)
    assert [r["event_type"] for r in rows] == ["document_created", "status_changed"]
    assert rows[0]["payload"]["after"]["origin"] == "legacy"
    assert Decimal(rows[0]["payload"]["after"]["total_amount_kopecks"]) == 100
    assert rows[1]["payload"]["after"]["status"] == "cancelled"
    async with SessionLocal() as session:
        invoice = await session.get(BillingInvoice, uuid.UUID(iid))
        assert invoice is not None and invoice.total_amount == 100
        assert await session.scalar(select(func.count()).select_from(BillingLedgerEntry)) == 1


@pytest.mark.parametrize("kind", ["settings", "profile", "tariff", "matrix", "invoice"])
@pytest.mark.skipif(
    engine.dialect.name != "postgresql",
    reason="PostgreSQL WMS-325 rollback proof; SQLite legacy SAVEPOINT differs",
)
async def test_postgresql_audit_rejection_preserves_existing_business_operation(
    async_client: AsyncClient,
    kind: str,
) -> None:
    h, tenant_id, _, seller_id = await seed(async_client)
    async with SessionLocal() as session:
        assert session.bind is not None and session.bind.dialect.name == "postgresql"
        await session.execute(
            text("""
            CREATE FUNCTION wms325_reject_audit() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN RAISE EXCEPTION 'synthetic history storage unavailable'; END $$
        """)
        )
        await session.execute(
            text("""
            CREATE TRIGGER wms325_reject_audit BEFORE INSERT ON document_event
            FOR EACH ROW EXECUTE FUNCTION wms325_reject_audit()
        """)
        )
        await session.commit()
    try:
        if kind == "settings":
            response = await async_client.patch(
                "/tenant/settings", headers=h, json={"separate_marking_print_enabled": True}
            )
            assert response.status_code == 200 and response.json()["separate_marking_print_enabled"]
        elif kind == "profile":
            response = await async_client.put("/billing/profiles/ff", headers=h, json=_ff_profile())
            assert (
                response.status_code == 200
                and response.json()["legal_name"] == _ff_profile()["legal_name"]
            )
        elif kind == "tariff":
            response = await async_client.post(
                "/billing/tariffs",
                headers=h,
                json={
                    "service_code": "inbound",
                    "unit": "item",
                    "amount": "1.25",
                    "valid_from": "2026-07-01",
                },
            )
            assert response.status_code == 201 and response.json()["amount"] == 125
        elif kind == "matrix":
            response = await async_client.put(
                "/billing/tariff-matrix",
                headers=h,
                json=matrix_body(0, 125, "2026-07-01T00:00:00Z"),
            )
            assert response.status_code == 200 and response.json()["revision"] == 1
        else:
            response = await async_client.post(
                "/billing/invoices-v2",
                headers={**h, "Idempotency-Key": "synthetic-failsoft"},
                json={
                    "creation_mode": "manual",
                    "seller_id": str(seller_id),
                    "lines": [{"description": "Synthetic service", "amount": "1.25"}],
                },
            )
            assert response.status_code == 201 and response.json()["total_amount_kopecks"] == 125
        async with SessionLocal() as session:
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(DocumentEvent)
                    .where(DocumentEvent.tenant_id == tenant_id)
                )
                == 0
            )
            assert await session.scalar(select(func.count()).select_from(OperationFact)) == 0
    finally:
        async with SessionLocal() as session:
            await session.execute(text("DROP TRIGGER wms325_reject_audit ON document_event"))
            await session.execute(text("DROP FUNCTION wms325_reject_audit()"))
            await session.commit()


@pytest.mark.parametrize("kind", ["profile", "tariff", "invoice_cancel", "settings"])
@pytest.mark.skipif(
    engine.dialect.name != "postgresql",
    reason="PostgreSQL WMS-325 rollback proof; SQLite legacy SAVEPOINT differs",
)
async def test_outer_rollback_removes_mutation_and_history(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
) -> None:
    _, tenant_id, actor_id, seller_id = await seed(async_client)
    invoice_id = uuid.uuid4()
    if kind == "invoice_cancel":
        async with SessionLocal() as session:
            session.add(
                BillingInvoice(
                    id=invoice_id,
                    tenant_id=tenant_id,
                    seller_id=seller_id,
                    number="SYNTHETIC-325",
                    period=date(2026, 7, 1),
                    status="issued",
                    total_amount=100,
                    ff_profile_snapshot={},
                    seller_profile_snapshot={},
                    lines=[],
                )
            )
            await session.commit()
    async with SessionLocal() as session:

        async def reject_commit() -> None:
            await session.flush()
            raise RuntimeError("synthetic outer commit rejected")

        with audit.document_event_actor(actor_id):
            if kind == "profile":
                await configuration.save_profile(
                    session,
                    tenant_id=tenant_id,
                    seller_id=seller_id,
                    legal_name="Synthetic",
                    inn="7707083893",
                )
            elif kind == "tariff":
                await configuration.create_tariff(
                    session,
                    tenant_id=tenant_id,
                    seller_id=None,
                    service_code="inbound",
                    unit="item",
                    amount=Decimal("1.25"),
                    valid_from=date(2026, 7, 1),
                )
            elif kind == "invoice_cancel":
                await legacy.cancel_invoice(session, tenant_id=tenant_id, invoice_id=invoice_id)
                await session.flush()
            else:
                monkeypatch.setattr(session, "commit", reject_commit)
                with pytest.raises(RuntimeError, match="synthetic outer commit"):
                    await tenant_settings.update_tenant_settings(
                        session,
                        tenant_id,
                        separate_marking_print_enabled=True,
                        actor_user_id=uuid.uuid4(),
                    )
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(DocumentEvent)
                    .where(DocumentEvent.tenant_id == tenant_id)
                )
                == 1
            )
        await session.rollback()
    async with SessionLocal() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(DocumentEvent)
                .where(DocumentEvent.tenant_id == tenant_id)
            )
            == 0
        )
        if kind == "profile":
            assert await session.scalar(select(func.count()).select_from(BillingProfile)) == 0
        elif kind == "tariff":
            assert await session.scalar(select(func.count()).select_from(BillingTariffVersion)) == 0
        elif kind == "invoice_cancel":
            invoice = await session.get(BillingInvoice, invoice_id)
            assert invoice is not None and invoice.status == "issued"
        else:
            assert (await tenant_settings.get_tenant_settings(session, tenant_id))[
                "separate_marking_print_enabled"
            ] is False
