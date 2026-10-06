"""WMS-662 F4/F5: document packing once; complete, idempotent Ozon reversal.

Real approve/sync and public invoice services follow the frozen invoice scenario.
Only marketplace I/O is fake. Ledger representation and row counts are not fixed.
"""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select
from test_wms662_approve_scope_race import (
    ApproveRaceTransport,
    assert_snapshot_only_and_retry,
    fake_credentials_and_no_network,  # noqa: F401 -- blocks real marketplace I/O
    normal_handoff,
    ready_order,
    saved,
    seed,
    shipped,
)
from test_wms662_invoiced_continuation import invoice_snapshot, issue
from test_wms662_observed_handoff import OzonCards, assert_completed, sync

from app.db.session import SessionLocal
from app.models.billing import (
    BillingInvoiceV2,
    BillingLedgerEntry,
    BillingTariffVersion,
    BillingTariffVersionV2,
)
from app.models.fbs_order import FbsOrder
from app.models.user import User
from app.services import inventory_service as inventory
from app.services.billing_invoice_v2_service import BillingInvoiceV2Error, preview_invoice_v2
from app.services.fbs_cancellation_service import reverse_fbs_order_billing

pytestmark = pytest.mark.asyncio


async def invoiced_continuation(db_session, *, document_packing):
    case = await seed(db_session, "ozon")
    user = User(tenant_id=case.tenant.id, role="fulfillment_admin", password_hash="test-only")
    db_session.add(user)
    db_session.add(BillingTariffVersion(
        tenant_id=case.tenant.id, seller_id=case.seller.id,
        service_code="fbs_order", unit="item", amount=1000, valid_from=date(2020, 1, 1),
    ))
    if document_packing:
        # No legacy packing tariff: V2 stores the real unit on the ledger line.
        db_session.add(BillingTariffVersionV2(
            tenant_id=case.tenant.id, seller_id=case.seller.id,
            service_code="packing", unit="document", rate=800,
            valid_from_at=datetime(2020, 1, 1, tzinfo=UTC),
        ))
    else:
        db_session.add(BillingTariffVersion(
            tenant_id=case.tenant.id, seller_id=case.seller.id,
            service_code="packing", unit="item", amount=800, valid_from=date(2020, 1, 1),
        ))
    await db_session.commit()
    await ready_order(db_session, case, case.orders[0], 1)

    async def increase_a():
        async with SessionLocal() as writer:
            order = await writer.get(FbsOrder, case.orders[0].id)
            await writer.refresh(order, attribute_names=["product_positions"])
            order.product_positions[0].quantity = 2
            await inventory.update_fbs_order_reservation(writer, order, reserve=True)
            await writer.commit()

    approve = ApproveRaceTransport(case, increase_a)
    await normal_handoff(case, approve)
    await assert_snapshot_only_and_retry(case, approve)
    approved_calls = list(approve.endpoint_calls)
    today = datetime.now(ZoneInfo("Europe/Moscow")).date()
    request = {
        "creation_mode": "selected_operations",
        "seller_id": str(case.seller.id),
        "date_from": (today - timedelta(days=2)).isoformat(),
        "date_to": today.isoformat(),
        "selected_sources": [
            {"source_type": "fbs_order", "source_id": str(case.orders[0].id),
             "service_code": code}
            for code in ("fbs_order", "packing")
        ],
    }
    first_id = await issue(case, user.id, request, "wms662-f4-f5-first")
    first_snapshot = await invoice_snapshot(case, first_id)
    assert first_snapshot[0]["status"] == "issued"
    assert first_snapshot[0]["total_amount_kopecks"] == 1800
    assert sum(row[2] for row in first_snapshot[1]) == 1800

    observed = OzonCards(case, ("delivering", None))
    observed.set(case, case.orders[0], "delivering", quantities=(2,))
    await sync(case, observed)
    completed = await saved(case)
    assert_completed(case, completed, quantities=(2,))
    assert shipped(completed, case.products[0]) == 2
    assert approve.endpoint_calls == approved_calls
    assert observed.requested
    assert all(path in {"/v3/posting/fbs/get", "/v1/carriage/get"}
               for path, _ in observed.endpoint_calls)
    assert await invoice_snapshot(case, first_id) == first_snapshot
    assert await issue(case, user.id, request, "wms662-f4-f5-first") == first_id
    assert await invoice_snapshot(case, first_id) == first_snapshot
    return case, user, request, first_id, first_snapshot, observed, completed


async def test_f4_v2_document_packing_is_billed_once_after_invoiced_continuation(db_session):
    case, user, request, first_id, first_snapshot, observed, completed = (
        await invoiced_continuation(db_session, document_packing=True)
    )
    assert sum(Decimal(charge.amount or 0) for charge in completed.charges) == 2800, (
        "F4: two items at 1000 plus document packing once at 800 must total 2800"
    )
    for _ in range(2):
        await sync(case, observed)
    again = await saved(case)
    assert again.stock == completed.stock
    assert again.reserves == completed.reserves
    assert {move.id for move in again.moves} == {move.id for move in completed.moves}
    assert sum(Decimal(charge.amount or 0) for charge in again.charges) == 2800
    assert await invoice_snapshot(case, first_id) == first_snapshot

    async with SessionLocal() as reader:
        preview = await preview_invoice_v2(reader, tenant_id=case.tenant.id, request=request)
        assert preview["total_amount_kopecks"] == 1000
        assert sum(line["total_amount_kopecks"] for line in preview["lines"]) == 1000
    second_id = await issue(case, user.id, request, "wms662-f4-second")
    assert second_id != first_id
    second_snapshot = await invoice_snapshot(case, second_id)
    assert second_snapshot[0]["total_amount_kopecks"] == 1000
    assert sum(row[2] for row in second_snapshot[1]) == 1000
    assert await issue(case, user.id, request, "wms662-f4-second") == second_id
    await sync(case, observed)
    assert await invoice_snapshot(case, first_id) == first_snapshot
    assert await invoice_snapshot(case, second_id) == second_snapshot
    try:
        third_id = await issue(case, user.id, request, "wms662-f4-third")
    except BillingInvoiceV2Error as exc:
        assert str(exc) in {"selected_source_already_invoiced", "selected_operations_required"}
    else:
        assert (await invoice_snapshot(case, third_id))[0]["total_amount_kopecks"] == 0
    async with SessionLocal() as reader:
        totals = list(await reader.scalars(select(BillingInvoiceV2.total_amount_kopecks).where(
            BillingInvoiceV2.tenant_id == case.tenant.id,
            BillingInvoiceV2.seller_id == case.seller.id,
            BillingInvoiceV2.status != "cancelled",
        )))
        assert sum(totals) == 2800


async def ledger_snapshot(case):
    # All persisted header fields, including IDs/dates, detect retry mutations.
    async with SessionLocal() as reader:
        rows = await reader.execute(select(BillingLedgerEntry.__table__).where(
            BillingLedgerEntry.tenant_id == case.tenant.id,
            BillingLedgerEntry.seller_id == case.seller.id,
        ).order_by(BillingLedgerEntry.id))
        return [dict(row._mapping) for row in rows]


async def cancel_billing(case):
    async with SessionLocal() as writer:
        order = await writer.get(FbsOrder, case.orders[0].id)
        order.status = "cancelled"
        await reverse_fbs_order_billing(writer, order)
        await writer.commit()
    return await ledger_snapshot(case)


async def test_f5_one_ozon_cancellation_reverses_all_charges_and_retry_changes_nothing(db_session):
    case, _, _, first_id, first_snapshot, _, completed = await invoiced_continuation(
        db_session, document_packing=False,
    )
    assert sum(Decimal(charge.amount or 0) for charge in completed.charges) == 3600
    before = await ledger_snapshot(case)
    charges = {row["id"] for row in before if row["entry_type"] == "charge"}
    assert charges
    assert all(row["source_type"] == "fbs_order"
               and row["source_id"] == case.orders[0].id for row in before)
    assert not any(row["entry_type"] == "reversal" for row in before)
    assert {row["service_code"] for row in before} == {"fbs_order", "packing"}

    first = await cancel_billing(case)
    retry = await cancel_billing(case)
    first_balance = sum(row["amount"] or 0 for row in first)
    retry_balance = sum(row["amount"] or 0 for row in retry)
    assert first_balance == 0, (
        f"F5: one Ozon cancellation must reverse every active charge; "
        f"first={len(first)} rows/balance {first_balance}, "
        f"retry={len(retry)} rows/balance {retry_balance}"
    )
    assert {row["reversal_of_id"] for row in first if row["entry_type"] == "reversal"} == charges
    assert [row for row in first if row["entry_type"] == "charge"] == before
    assert retry == first, "F5: retry must not add or change any billing entry"
    assert retry_balance == 0
    assert await invoice_snapshot(case, first_id) == first_snapshot
