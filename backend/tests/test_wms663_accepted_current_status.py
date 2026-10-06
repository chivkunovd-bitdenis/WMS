"""F4: completed intent A does not accept fresh cabinet documents on a later GET."""

from copy import deepcopy

import pytest
from test_wms663_astra_regressions import SET, SNAPSHOT, STATUS, _accept_a, _exemplar, _scan
from test_wms663_customs_documents_contract import (
    SKU_TWO,
    _remote_snapshot,
    _seed_order,
    _transport,
)

from app.services import ozon_exemplar_documents_service as documents
from app.services import ozon_fbs_process_service as process
from app.services.marketplace_provider import OzonMarketplaceProvider

CURRENT_RESULTS = ("rejected", "checking", "unknown_document_status")


async def _accepted_then_current_status(session, current_result):
    # Fail closed if someone accidentally runs this SQLite-only contract against PG.
    assert session.get_bind().dialect.name == "sqlite"
    order, first, _ = await _seed_order(session)
    transport = _transport(status={**_remote_snapshot(), "status": "ship_available"})
    await _accept_a(session, order, transport)
    completed = documents.document_data(order)
    assert _exemplar(completed["snapshot"])["gtd"] == "001/ABC-09"

    fresh = deepcopy(_remote_snapshot())
    _exemplar(fresh).update(
        gtd="CABINET-NEW", rnpt="CABINET-NEW-RNPT",
        is_gtd_absent=False, is_rnpt_absent=False,
        gtd_check_status="future_status" if current_result == "unknown_document_status" else "",
        gtd_error_codes=["gtd_invalid"] if current_result == "rejected" else [],
    )
    fresh["status"] = {
        "rejected": "ship_not_available",
        "checking": "validation_in_process",
        "unknown_document_status": "ship_available",
    }[current_result]
    transport.endpoint_responses[STATUS] = fresh
    transport.endpoint_responses[SNAPSHOT] = fresh
    kwargs = dict(
        tenant_id=order.tenant_id, order_id=order.id,
        provider=OzonMarketplaceProvider(transport=transport),
        client_id="fake-client", api_key="fake-key",
    )
    calls_before = len(transport.endpoint_calls)
    view = await documents.get_exemplar_documents(session, **kwargs)
    reads = transport.endpoint_calls[calls_before:]
    assert any(path == STATUS for path, _ in reads)
    assert not any(path in {SET, SNAPSHOT} for path, _ in reads)
    assert view["version"] == completed["version"]
    assert view["status"] == fresh["status"]
    for field in ("gtd", "rnpt", "is_gtd_absent", "is_rnpt_absent", "weight", "marks"):
        assert _exemplar(view)[field] == _exemplar(fresh)[field], field
    assert documents.document_data(order)["choices"] == completed["choices"]
    assert not documents.document_data(order)["in_flight"]
    return order, first, transport, fresh, view, kwargs


@pytest.mark.asyncio
async def test_f4_current_rejection_is_visible_in_view_and_exemplar(db_session):
    _, _, _, _, view, _ = await _accepted_then_current_status(db_session, "rejected")
    # These are the errors the real screen consumes, not raw *_error_codes in snapshot.
    assert (
        "gtd_invalid" in view["errors"],
        "gtd_invalid" in _exemplar(view)["errors"],
    ) == (True, True), view
    assert view["state"] != "accepted"
    assert _exemplar(view)["state"] != "accepted"


@pytest.mark.asyncio
async def test_f4_current_validation_is_checking_not_historical_acceptance(db_session):
    _, _, _, _, view, _ = await _accepted_then_current_status(db_session, "checking")
    assert (view["state"], _exemplar(view)["state"]) == ("checking", "checking"), view


@pytest.mark.asyncio
async def test_f4_unknown_current_document_status_is_not_accepted(db_session):
    _, _, _, _, view, _ = await _accepted_then_current_status(
        db_session, "unknown_document_status"
    )
    assert _exemplar(view)["gtd_check_status"] == "future_status"
    assert (
        view["state"] == "accepted", _exemplar(view)["state"] == "accepted"
    ) == (False, False), view


@pytest.mark.asyncio
@pytest.mark.parametrize("current_result", CURRENT_RESULTS)
@pytest.mark.parametrize("next_write", ["documents_b", "marking"])
async def test_f4_current_read_does_not_turn_completed_intent_into_pending_writer(
    db_session, current_result, next_write
):
    order, first, transport, fresh, view, kwargs = await _accepted_then_current_status(
        db_session, current_result
    )
    # A second read must also remain a read: current checking/unknown is not a new writer.
    calls_before = len(transport.endpoint_calls)
    again = await documents.get_exemplar_documents(db_session, **kwargs)
    assert again["version"] == view["version"]
    assert _exemplar(again)["gtd"] == "CABINET-NEW"
    assert again["editable"] is True
    assert any(path == STATUS for path, _ in transport.endpoint_calls[calls_before:])
    assert not any(path in {SET, SNAPSHOT} for path, _ in transport.endpoint_calls[calls_before:])
    if next_write == "documents_b":
        await documents.save_exemplar_documents(
            db_session,
            tenant_id=order.tenant_id, order_id=order.id,
            product_id=SKU_TWO, exemplar_id=91,
            gtd=None, is_gtd_absent=True, rnpt="NEW-B", is_rnpt_absent=False,
            expected_version=again["version"],
            provider=kwargs["provider"], client_id="fake-client", api_key="fake-key",
        )
    else:
        await _scan(db_session, order, first, transport, 82)
    writes = [payload for path, payload in transport.endpoint_calls if path == SET]
    assert len(writes) == 2
    assert documents.document_data(order)["version"] == view["version"] + 1
    for field in ("gtd", "rnpt", "is_gtd_absent", "is_rnpt_absent", "weight", "marks"):
        assert _exemplar(writes[-1])[field] == _exemplar(fresh)[field], field
    if next_write == "documents_b":
        assert _exemplar(writes[-1], SKU_TWO, 91)["rnpt"] == "NEW-B"
    else:
        assert _exemplar(writes[-1], exemplar_id=82)["marks"][-1]["mark"].endswith("82")


@pytest.mark.asyncio
@pytest.mark.parametrize("current_result", CURRENT_RESULTS)
@pytest.mark.parametrize("kind", ["documents", "marking"])
async def test_f4_current_read_preserves_stale_version_control(db_session, current_result, kind):
    order, _, transport, _, view, _ = await _accepted_then_current_status(
        db_session, current_result
    )
    before = documents.document_data(order)
    calls_before = len(transport.endpoint_calls)
    choice = dict(
        product_id=SKU_TWO, exemplar_id=91, gtd=None, rnpt="STALE",
        is_gtd_absent=True, is_rnpt_absent=False,
    ) if kind == "documents" else {"marking_id": "stale"}
    with pytest.raises(process.OzonFbsProcessError) as error:
        await documents.claim_exemplar_write(
            db_session, order, view["version"] - 1, kind=kind, choice=choice
        )
    assert error.value.status_code == 409
    assert error.value.code == "ozon_exemplar_documents_conflict"
    assert documents.document_data(order) == before
    assert len(transport.endpoint_calls) == calls_before
