"""Two assigned review regressions: pre-SET recovery and shared marking intent.

Unknown after SET must keep its no-repeat fence intact.
"""

from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest
from test_wms663_astra_regressions import SNAPSHOT, STATUS, _exemplar, _scan
from test_wms663_customs_documents_contract import (
    POSTING_NUMBER,
    _AppliedThenLostTransport,
    _remote_snapshot,
    _seed_order,
    _transport,
)
from test_wms663_owner_absent_batch_contract import expected_payload, kwargs, operation, writes

from app.db.session import SessionLocal
from app.services import ozon_exemplar_documents_service as documents
from app.services.ozon_fbs_errors import OzonFbsProcessError


@pytest.mark.asyncio
async def test_interrupted_pre_set_claim_allows_first_explicit_set_but_unknown_never_repeats(
    db_session,
):
    save = operation()
    order, _, _ = await _seed_order(db_session)
    transport = _AppliedThenLostTransport(endpoint_responses={
        SNAPSHOT: _remote_snapshot(),
        STATUS: {"posting_number": POSTING_NUMBER,
                 "status": "validation_in_process", "products": []},
    })
    # This is the real durable claim, not a fabricated pending state. Crash before
    # snapshot/SET; advance only the saved lease through the normal checkpoint.
    claimed = await documents.claim_exemplar_write(
        db_session, order, 0, kind="documents", choice={"all_required_absent": True}
    )
    assert claimed["state"] == "preparing"
    assert claimed["version"] == 1
    assert claimed["set_acknowledged"] is False
    claimed["lease_until"] = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
    assert await documents.checkpoint(db_session, order.tenant_id, order.id, claimed)
    assert transport.endpoint_calls == []

    async with SessionLocal() as restarted:
        recovered = await documents.get_exemplar_documents(restarted, **kwargs(order, transport))
        assert recovered["state"] == "editable"
        assert recovered["version"] == 2
        assert recovered["absence_selected"] is False
        assert writes(transport) == []
        first = await save(
            restarted, **kwargs(order, transport), expected_version=recovered["version"]
        )
        # The first SET is applied but its HTTP response is lost. No acceptance
        # claim is allowed, and the same explicit choice cannot trigger SET #2.
        assert writes(transport) == [expected_payload()]
        assert first["state"] in {"checking", "unknown"}
        assert first["version"] == 3
        assert first["absence_selected"] is True

    before = len(transport.endpoint_calls)
    async with SessionLocal() as restarted_again:
        readback = await documents.get_exemplar_documents(
            restarted_again, **kwargs(order, transport)
        )
        assert readback["state"] in {"checking", "unknown"}
        try:
            repeat = await save(
                restarted_again, **kwargs(order, transport), expected_version=readback["version"]
            )
        except OzonFbsProcessError as error:
            assert error.status_code == 409
        else:
            assert repeat["state"] in {"checking", "unknown"}
        assert writes(transport) == [expected_payload()]
        assert all(path == STATUS for path, _ in transport.endpoint_calls[before:])


@pytest.mark.asyncio
async def test_accepted_batch_intent_survives_real_marking_and_does_not_set_again(db_session):
    save = operation()
    order, first_position, _ = await _seed_order(db_session)
    # Fake cabinet readback contains the exact accepted documents and original
    # requirement flags. The real marking flow remains responsible for its SET.
    confirmed = deepcopy(_remote_snapshot())
    for product in confirmed["products"]:
        for exemplar in product["exemplars"]:
            exemplar.update(
                _exemplar(expected_payload(), product["product_id"], exemplar["exemplar_id"])
            )
    transport = _transport(status={**confirmed, "status": "ship_available"})
    accepted = await save(db_session, **kwargs(order, transport), expected_version=0)
    assert accepted["state"] == "accepted"
    assert accepted["absence_selected"] is True
    assert writes(transport) == [expected_payload()]
    transport.endpoint_responses[SNAPSHOT] = confirmed
    await _scan(db_session, order, first_position, transport, 81)
    assert len(writes(transport)) == 2  # One document SET, then the genuine KIZ SET.
    marked_payload = writes(transport)[1]
    assert _exemplar(marked_payload)["marks"][-1]["mark"].endswith("81")
    for product in confirmed["products"]:
        for exemplar in product["exemplars"]:
            sent = _exemplar(marked_payload, product["product_id"], exemplar["exemplar_id"])
            for field in ("gtd", "rnpt", "is_gtd_absent", "is_rnpt_absent", "weight"):
                assert sent[field] == exemplar[field]
            exemplar.update(sent)
    transport.endpoint_responses[SNAPSHOT] = confirmed
    transport.endpoint_responses[STATUS] = {**confirmed, "status": "ship_available"}

    before = len(transport.endpoint_calls)
    async with SessionLocal() as reopened:
        view = await documents.get_exemplar_documents(reopened, **kwargs(order, transport))
        assert view["state"] == "accepted"
        assert view["absence_selected"] is True
        repeated = await save(
            reopened, **kwargs(order, transport), expected_version=view["version"]
        )
        assert repeated["absence_selected"] is True
    assert writes(transport) == [expected_payload(), marked_payload]
    assert all(path == STATUS for path, _ in transport.endpoint_calls[before:])
