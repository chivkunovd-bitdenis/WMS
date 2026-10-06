"""R11/C8/C10/C16: an explicit retry after a definite rejection stays reachable."""

import asyncio

import pytest
from test_wms663_astra_regressions import SET, SNAPSHOT, STATUS
from test_wms663_customs_documents_contract import (
    POSTING_NUMBER,
    _AppliedThenLostTransport,
    _remote_snapshot,
    _seed_order,
    _transport,
)
from test_wms663_owner_absent_batch_contract import expected_payload, kwargs, writes

from app.db.session import SessionLocal, engine
from app.services import ozon_exemplar_documents_service as documents
from app.services.marketplace_provider import MarketplaceProviderError
from app.services.ozon_fbs_errors import OzonFbsProcessError


def accepted_status():
    return {**expected_payload(), "status": "ship_available"}


@pytest.mark.asyncio
async def test_definite_429_then_explicit_retry_sends_one_new_set_and_persists_acceptance(
    db_session,
):
    order, _, _ = await _seed_order(db_session)
    order.meta_details_json = {"unrelated_metadata": {"keep": "neighbor"}}
    await db_session.commit()
    transport = _transport(status={**_remote_snapshot(), "status": "update_available"})
    transport.errors[SET] = MarketplaceProviderError("ozon", 429, code="fixture_rate_limit")
    rejected = await documents.save_absent_exemplar_documents(
        db_session, **kwargs(order, transport), expected_version=0,
    )
    assert rejected["state"] == "rejected"
    assert rejected["absence_selected"] is True  # Intent survives rejection.
    assert writes(transport) == [expected_payload()]
    await db_session.refresh(order)
    assert documents.document_data(order)["in_flight"] is False

    # The operator explicitly retries the current persisted version, after Ozon
    # became editable. Reopening alone is never permission for another SET.
    transport.errors.pop(SET)
    original_call = transport.call

    async def accept_after_new_set(**args):
        response = await original_call(**args)
        if args["path"] == SET:
            transport.endpoint_responses[STATUS] = accepted_status()
        return response

    transport.call = accept_after_new_set
    async with SessionLocal() as restarted:
        await documents.get_exemplar_documents(restarted, **kwargs(order, transport))
        assert writes(transport) == [expected_payload()]  # Reopening is read-only.
        recovered = await documents.save_absent_exemplar_documents(
            restarted, **kwargs(order, transport), expected_version=rejected["version"],
        )
    assert writes(transport) == [expected_payload(), expected_payload()], (
        "A definite 429 must permit exactly one NEW SET for the next explicit retry"
    )
    assert recovered["state"] == "accepted"
    assert recovered["version"] == rejected["version"] + 1
    await db_session.refresh(order)
    saved = documents.document_data(order)
    assert saved["state"] == "accepted"
    assert saved["version"] == recovered["version"]
    assert saved["in_flight"] is False
    assert order.meta_details_json["unrelated_metadata"] == {"keep": "neighbor"}
    assert all(
        payload["posting_number"] == POSTING_NUMBER for _, payload in transport.endpoint_calls
    )


@pytest.mark.asyncio
async def test_unknown_with_old_update_available_readback_cannot_duplicate_batch(db_session):
    order, _, _ = await _seed_order(db_session)
    transport = _AppliedThenLostTransport(endpoint_responses={
        SNAPSHOT: _remote_snapshot(),
        STATUS: {**_remote_snapshot(), "status": "update_available"},
    })
    unknown = await documents.save_absent_exemplar_documents(
        db_session, **kwargs(order, transport), expected_version=0,
    )
    assert unknown["state"] == "unknown"
    async with SessionLocal() as restarted:
        for _ in range(2):
            result = await documents.get_exemplar_documents(restarted, **kwargs(order, transport))
            assert result["state"] == "unknown"
            try:
                await documents.save_absent_exemplar_documents(
                    restarted, **kwargs(order, transport), expected_version=unknown["version"],
                )
            except OzonFbsProcessError as conflict:
                assert conflict.status_code == 409
    assert writes(transport) == [expected_payload()]
    await db_session.refresh(order)
    assert documents.document_data(order)["version"] == unknown["version"]


@pytest.mark.asyncio
async def test_accepted_batch_reopen_and_repeat_never_create_new_set(db_session):
    order, _, _ = await _seed_order(db_session)
    transport = _transport(status=accepted_status())
    accepted = await documents.save_absent_exemplar_documents(
        db_session, **kwargs(order, transport), expected_version=0,
    )
    assert accepted["state"] == "accepted"
    async with SessionLocal() as restarted:
        reopened = await documents.get_exemplar_documents(restarted, **kwargs(order, transport))
        assert reopened["state"] == "accepted"
        await documents.save_absent_exemplar_documents(
            restarted, **kwargs(order, transport), expected_version=reopened["version"],
        )
    assert writes(transport) == [expected_payload()]
    await db_session.refresh(order)
    assert documents.document_data(order)["version"] == accepted["version"]


@pytest.mark.asyncio
@pytest.mark.parametrize("retry", [False, True], ids=["initial-batch", "rejected-batch-retry"])
async def test_two_sessions_same_version_batch_allow_only_one_set(db_session, retry):
    if engine.dialect.name != "postgresql":
        pytest.skip("actual two-session row-lock contract requires isolated PostgreSQL")
    order, _, _ = await _seed_order(db_session)
    version = 0
    if retry:
        rejected_transport = _transport()
        rejected_transport.errors[SET] = MarketplaceProviderError(
            "ozon", 429, code="fixture_rate_limit",
        )
        rejected = await documents.save_absent_exemplar_documents(
            db_session, **kwargs(order, rejected_transport), expected_version=0,
        )
        assert rejected["state"] == "rejected"
        version = rejected["version"]

    # Hold the winner at the external snapshot boundary after the durable
    # claim. The second database session sees the same operator version.
    entered, release = asyncio.Event(), asyncio.Event()
    first_transport = _transport(status=accepted_status())
    second_transport = _transport(status=accepted_status())
    original_call = first_transport.call

    async def held_call(**args):
        if args["path"] == SNAPSHOT:
            entered.set()
            await release.wait()
        return await original_call(**args)

    first_transport.call = held_call

    async def save(transport):
        async with SessionLocal() as session:
            return await documents.save_absent_exemplar_documents(
                session, **kwargs(order, transport), expected_version=version,
            )

    first = asyncio.create_task(save(first_transport))
    try:
        try:
            await asyncio.wait_for(entered.wait(), timeout=3)
        except TimeoutError:
            pytest.fail("Explicit rejected-batch retry never claimed a fresh write/snapshot")
        try:
            await save(second_transport)
        except OzonFbsProcessError as conflict:
            assert conflict.status_code == 409
        assert writes(second_transport) == []
    finally:
        release.set()
        outcome = await first
    assert outcome["state"] == "accepted"
    assert writes(first_transport) + writes(second_transport) == [expected_payload()]
    await db_session.refresh(order)
    assert documents.document_data(order)["version"] == version + 1
