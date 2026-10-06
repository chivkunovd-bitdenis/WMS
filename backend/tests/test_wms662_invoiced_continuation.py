"""WMS-662: invoice A/1, then bill only the newly proved unit of A/2.

Public invoice and handoff services are real. No contract is imposed on the
number/identity of facts or charges used to represent incremental work.
"""

from datetime import date, datetime, timedelta
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
from test_wms662_observed_handoff import OzonCards, assert_completed, sync

from app.db.session import SessionLocal
from app.models.billing import BillingInvoiceV2, BillingInvoiceV2Source, BillingTariffVersion
from app.models.fbs_order import FbsOrder
from app.models.user import User
from app.services import inventory_service as inventory
from app.services.billing_invoice_v2_service import (
    BillingInvoiceV2Error,
    create_invoice_v2,
    get_invoice_v2,
    invoice_v2_out,
    preview_invoice_v2,
)

pytestmark = pytest.mark.asyncio


async def invoice_snapshot(case, invoice_id):
    async with SessionLocal() as reader:
        invoice = await get_invoice_v2(reader, tenant_id=case.tenant.id, invoice_id=invoice_id)
        output = await invoice_v2_out(reader, invoice)
        source_amounts = list(await reader.execute(
            select(
                BillingInvoiceV2Source.id,
                BillingInvoiceV2Source.billing_ledger_entry_id,
                BillingInvoiceV2Source.signed_amount_kopecks_snapshot,
            ).where(BillingInvoiceV2Source.invoice_line_id.in_(
                [line.id for line in invoice.lines_v2],
            )),
        ))
        return output, set(source_amounts)


async def issue(case, user_id, request, key):
    async with SessionLocal() as writer:
        invoice = await create_invoice_v2(
            writer, tenant_id=case.tenant.id, user_id=user_id,
            request=request, idempotency_key=key,
        )
        await writer.commit()
        return invoice.id


@pytest.mark.parametrize("repeat_sync", [False, True], ids=["continuation", "repeated-sync"])
async def test_invoiced_partial_handoff_bills_increment_once_without_rewriting_invoice(
    db_session, repeat_sync,
):
    case = await seed(db_session, "ozon")
    user = User(tenant_id=case.tenant.id, role="fulfillment_admin", password_hash="test-only")
    db_session.add(user)
    for service_code, rate in (("fbs_order", 1000), ("packing", 800)):
        db_session.add(BillingTariffVersion(
            tenant_id=case.tenant.id, seller_id=case.seller.id,
            service_code=service_code, unit="item", amount=rate,
            valid_from=date(2020, 1, 1),
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
    # A narrow window around today avoids future periods and midnight races.
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
    first_id = await issue(case, user.id, request, "wms662-invoice-first")
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
    assert sum(Decimal(charge.amount or 0) for charge in completed.charges) == 3600
    if repeat_sync:
        for _ in range(2):
            await sync(case, observed)
        again = await saved(case)
        assert again.stock == completed.stock
        assert again.reserves == completed.reserves
        assert {move.id for move in again.moves} == {move.id for move in completed.moves}
        assert sum(Decimal(charge.amount or 0) for charge in again.charges) == sum(
            Decimal(charge.amount or 0) for charge in completed.charges
        )
    assert approve.endpoint_calls == approved_calls
    assert observed.requested
    assert all(path in {"/v3/posting/fbs/get", "/v1/carriage/get"}
               for path, _ in observed.endpoint_calls)
    assert await invoice_snapshot(case, first_id) == first_snapshot
    assert await issue(case, user.id, request, "wms662-invoice-first") == first_id
    assert await invoice_snapshot(case, first_id) == first_snapshot

    # Selecting the performed order again must expose ONLY its unbilled work.
    # This is a public service expectation, independent of delta-row design.
    async with SessionLocal() as reader:
        try:
            preview = await preview_invoice_v2(reader, tenant_id=case.tenant.id, request=request)
        except BillingInvoiceV2Error as exc:
            pytest.fail(
                f"A/2 is completed; immutable first invoice covers A/1 only, "
                f"but next invoice cannot bill the incremental unit: {exc}"
            )
        assert preview["total_amount_kopecks"] == 1800, "Bill only the additional unit"
        assert sum(line["total_amount_kopecks"] for line in preview["lines"]) == 1800
    second_id = await issue(case, user.id, request, "wms662-invoice-second")
    assert second_id != first_id
    second_snapshot = await invoice_snapshot(case, second_id)
    assert second_snapshot[0]["total_amount_kopecks"] == 1800
    assert sum(row[2] for row in second_snapshot[1]) == 1800
    assert await issue(case, user.id, request, "wms662-invoice-second") == second_id
    await sync(case, observed)
    assert await invoice_snapshot(case, first_id) == first_snapshot
    assert await invoice_snapshot(case, second_id) == second_snapshot
    # After both units have been billed, a new key cannot bill them a third time.
    try:
        third_id = await issue(case, user.id, request, "wms662-invoice-third")
    except BillingInvoiceV2Error as exc:
        assert str(exc) in {"selected_source_already_invoiced", "selected_operations_required"}
    else:
        third_snapshot = await invoice_snapshot(case, third_id)
        assert third_snapshot[0]["total_amount_kopecks"] == 0
    async with SessionLocal() as reader:
        totals = list(await reader.scalars(select(BillingInvoiceV2.total_amount_kopecks).where(
            BillingInvoiceV2.tenant_id == case.tenant.id,
            BillingInvoiceV2.seller_id == case.seller.id,
            BillingInvoiceV2.status != "cancelled",
        )))
        assert sum(totals) == 3600, "Each of the two performed units is invoiced exactly once"
