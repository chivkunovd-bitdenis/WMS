from __future__ import annotations

import sys
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal
from app.models.billing import (
    BillingInvoice,
    BillingInvoiceV2,
    BillingInvoiceV2Line,
    BillingInvoiceV2Source,
    BillingLedgerEntry,
)
from app.models.fbs_order import FbsOrder
from app.models.operation_fact import OperationFact
from app.models.seller import Seller
from app.models.tenant import Tenant
from scripts import backfill_fbs_order_facts as script

WORK = datetime(2026, 8, 20, 10, tzinfo=UTC)
STORED = datetime(2026, 9, 2, 10, tzinfo=UTC)


async def _seed(session: AsyncSession) -> tuple[Tenant, Seller, FbsOrder, OperationFact]:
    tenant = Tenant(name="Backfill only", slug=f"backfill-{uuid.uuid4().hex}")
    session.add(tenant)
    await session.flush()
    seller = Seller(tenant_id=tenant.id, name="Backfill seller")
    session.add(seller)
    await session.flush()
    order = FbsOrder(
        tenant_id=tenant.id,
        seller_id=seller.id,
        wb_order_id=13,
        status="sorted",
        mapping_status="unmapped",
        reserve_status="released",
        created_at_wb=WORK,
        deadline_at=WORK,
    )
    session.add(order)
    await session.flush()
    fact = OperationFact(
        tenant_id=tenant.id,
        seller_id=seller.id,
        operation_code="fbs_order",
        billable_service_code="fbs_order",
        source_kind="fbs_order",
        source_event_id=order.id,
        document_type="fbs_order",
        document_id=order.id,
        idempotency_key=f"fbs-order:{order.id}",
        source="system",
        item_quantity=1,
        occurred_at=STORED,
    )
    session.add(fact)
    await session.flush()
    return tenant, seller, order, fact


def _charge(tenant: Tenant, seller: Seller, order: FbsOrder) -> BillingLedgerEntry:
    return BillingLedgerEntry(
        tenant_id=tenant.id,
        seller_id=seller.id,
        service_code="fbs_order",
        source="fbs_order",
        source_type="fbs_order",
        source_id=order.id,
        unit="item",
        quantity=Decimal(1),
        rate=1000,
        amount=1000,
        occurred_at=STORED,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["unbilled_charge", "legacy", "v2_ledger", "v2_fact"])
@pytest.mark.parametrize("invoice_status", ["issued", "cancelled"])
async def test_apply_preserves_accounted_fact_dates_and_invoice_sources(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    kind: str,
    invoice_status: str,
) -> None:
    session = db_session
    tenant, seller, order, fact = await _seed(session)
    entry = None
    if kind != "v2_fact":
        entry = _charge(tenant, seller, order)
        session.add(entry)
        await session.flush()
    if kind == "legacy":
        assert entry
        session.add(
            BillingInvoice(
                tenant_id=tenant.id,
                seller_id=seller.id,
                number="INV-13",
                period=date(2026, 9, 1),
                status=invoice_status,
                total_amount=Decimal(1000),
                ff_profile_snapshot={},
                seller_profile_snapshot={},
                lines=[
                    {
                        "documents": [
                            {
                                "id": str(entry.id),
                                "occurred_at": STORED.isoformat(),
                                "amount": "1000",
                            }
                        ]
                    }
                ],
            )
        )
    elif kind.startswith("v2"):
        invoice = BillingInvoiceV2(
            tenant_id=tenant.id,
            seller_id=seller.id,
            number="INV-13",
            creation_mode="selected_operations",
            status=invoice_status,
            total_amount_kopecks=1000,
        )
        session.add(invoice)
        await session.flush()
        line = BillingInvoiceV2Line(
            tenant_id=tenant.id,
            invoice_id=invoice.id,
            description_snapshot="FBS",
            total_amount_kopecks=1000,
            sort_order=0,
        )
        session.add(line)
        await session.flush()
        session.add(
            BillingInvoiceV2Source(
                tenant_id=tenant.id,
                invoice_line_id=line.id,
                operation_fact_id=fact.id if kind == "v2_fact" else None,
                billing_ledger_entry_id=entry.id if entry else None,
                signed_amount_kopecks_snapshot=1000,
            )
        )
    await session.commit()
    monkeypatch.setattr(sys, "argv", ["backfill", "--tenant", str(tenant.id), "--apply"])
    await script.main()
    output = capsys.readouterr().out
    assert "дат исправлено: 0" in output
    assert "даты сохранены: есть начисление или ссылка из счёта: 1" in output
    async with SessionLocal() as reread:
        saved = await reread.get(OperationFact, fact.id)
        assert saved and saved.occurred_at.replace(tzinfo=UTC) == STORED
        if entry:
            charge = await reread.get(BillingLedgerEntry, entry.id)
            assert charge and charge.occurred_at.replace(tzinfo=UTC) == STORED
            assert charge.amount == 1000 and charge.quantity == Decimal(1)
        if kind == "legacy":
            legacy = await reread.scalar(select(BillingInvoice))
            assert legacy and legacy.total_amount == Decimal(1000)
            assert legacy.lines[0]["documents"][0]["occurred_at"] == STORED.isoformat()
        if kind.startswith("v2"):
            source = await reread.scalar(select(BillingInvoiceV2Source))
            assert source and source.signed_amount_kopecks_snapshot == 1000
            saved_invoice = await reread.scalar(select(BillingInvoiceV2))
            assert saved_invoice and saved_invoice.total_amount_kopecks == 1000


@pytest.mark.asyncio
@pytest.mark.parametrize("apply", [False, True])
async def test_unaccounted_fact_dates_dry_run_and_apply(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    apply: bool,
) -> None:
    tenant, _, _, fact = await _seed(db_session)
    await db_session.commit()
    monkeypatch.setattr(
        sys, "argv", ["backfill", "--tenant", str(tenant.id)] + (["--apply"] if apply else [])
    )
    await script.main()
    async with SessionLocal() as reread:
        saved = await reread.get(OperationFact, fact.id)
        assert saved and saved.occurred_at.replace(tzinfo=UTC) == (WORK if apply else STORED)
        saved_tenant = await reread.get(Tenant, tenant.id)
        assert saved_tenant and saved_tenant.billing_enabled_from is None
        assert list(await reread.scalars(select(BillingLedgerEntry))) == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,confirmed", [("in_delivery", False), ("in_delivery", True), ("sorted", True)]
)
async def test_backfill_uses_persisted_handover_and_ignores_unconfirmed_import(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    status: str,
    confirmed: bool,
) -> None:
    from app.models.fbs_supply import FbsSupply
    from app.models.warehouse import Warehouse

    tenant, seller, order, fact = await _seed(db_session)
    await db_session.delete(fact)
    order.status = status
    warehouse = Warehouse(tenant_id=tenant.id, name="Historical warehouse", code="HIST")
    db_session.add(warehouse)
    await db_session.flush()
    handed_at = datetime(2026, 8, 25, 10, tzinfo=UTC)
    supply = FbsSupply(
        tenant_id=tenant.id,
        seller_id=seller.id,
        warehouse_id=warehouse.id,
        name="Historical supply",
        wb_supply_id="WB-GI-13",
        delivery_type="sc",
        delivered_at=handed_at if confirmed else None,
    )
    db_session.add(supply)
    await db_session.flush()
    order.supply_id = supply.id
    await db_session.commit()
    monkeypatch.setattr(sys, "argv", ["backfill", "--tenant", str(tenant.id), "--apply"])
    await script.main()
    await script.main()  # A repeated recovery does not duplicate or move the correct date.
    async with SessionLocal() as reread:
        facts = list(await reread.scalars(select(OperationFact)))
        if confirmed:
            assert len(facts) == 1
            assert facts[0].occurred_at.replace(tzinfo=UTC) == handed_at
        else:
            assert facts == []
        assert list(await reread.scalars(select(BillingLedgerEntry))) == []
        saved_tenant = await reread.get(Tenant, tenant.id)
        assert saved_tenant and saved_tenant.billing_enabled_from is None
