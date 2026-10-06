"""F1-R: reading an accepted intent must not resurrect historical documents."""

from copy import deepcopy

import pytest
from test_wms663_astra_regressions import SET, SNAPSHOT, STATUS, _accept_a, _exemplar, _scan
from test_wms663_customs_documents_contract import (
    SKU_ONE,
    SKU_TWO,
    _remote_snapshot,
    _seed_order,
    _transport,
)

from app.db.session import SessionLocal
from app.services import ozon_exemplar_documents_service as documents
from app.services import ozon_fbs_process_service as process
from app.services.marketplace_provider import OzonMarketplaceProvider


async def _accepted_then_cabinet_read(session):
    order, first, _ = await _seed_order(session)
    transport = _transport(status={**_remote_snapshot(), "status": "ship_available"})
    await _accept_a(session, order, transport)
    fresh = deepcopy(_remote_snapshot())
    _exemplar(fresh).update(
        gtd="NEW-GTD", rnpt="NEW-RNPT", is_gtd_absent=False, is_rnpt_absent=False
    )
    transport.endpoint_responses[SNAPSHOT] = fresh
    transport.endpoint_responses[STATUS] = {**fresh, "status": "ship_available"}
    calls_before = len(transport.endpoint_calls)
    view = await documents.get_exemplar_documents(
        session,
        tenant_id=order.tenant_id,
        order_id=order.id,
        provider=OzonMarketplaceProvider(transport=transport),
        client_id="fake-client",
        api_key="fake-key",
    )
    reads = transport.endpoint_calls[calls_before:]
    assert any(path == STATUS for path, _ in reads)
    assert not any(path in {SET, SNAPSHOT} for path, _ in reads)
    return order, first, transport, fresh, view


@pytest.mark.asyncio
async def test_f1r_accepted_get_shows_fresh_cabinet_and_remains_editable(db_session):
    order, _, _, fresh, view = await _accepted_then_cabinet_read(db_session)
    assert _exemplar(view)["gtd"] == "NEW-GTD"
    assert _exemplar(view)["rnpt"] == "NEW-RNPT"
    for field in ("is_gtd_absent", "is_rnpt_absent", "weight", "marks"):
        assert _exemplar(view)[field] == _exemplar(fresh)[field], field
    assert view["status"] == "ship_available"
    assert view["state"] != "unknown"
    assert view["editable"] is True
    assert _exemplar(documents.document_data(order)["snapshot"])["gtd"] == "NEW-GTD"


@pytest.mark.asyncio
@pytest.mark.parametrize("next_write", ["documents_b", "marking"])
async def test_f1r_accepted_get_allows_next_write_without_old_a(db_session, next_write):
    order, first, transport, fresh, view = await _accepted_then_cabinet_read(db_session)
    if next_write == "documents_b":
        await documents.save_exemplar_documents(
            db_session,
            tenant_id=order.tenant_id,
            order_id=order.id,
            product_id=SKU_TWO,
            exemplar_id=91,
            gtd=None,
            is_gtd_absent=True,
            rnpt="NEW-B",
            is_rnpt_absent=False,
            expected_version=view["version"],
            provider=OzonMarketplaceProvider(transport=transport),
            client_id="fake-client",
            api_key="fake-key",
        )
    else:
        await _scan(db_session, order, first, transport, 82)
    writes = [payload for path, payload in transport.endpoint_calls if path == SET]
    assert len(writes) == 2
    for field in ("gtd", "rnpt", "is_gtd_absent", "is_rnpt_absent", "weight", "marks"):
        assert _exemplar(writes[-1])[field] == _exemplar(fresh)[field], field
    if next_write == "documents_b":
        assert _exemplar(writes[-1], SKU_TWO, 91)["rnpt"] == "NEW-B"
    else:
        assert _exemplar(writes[-1], exemplar_id=82)["marks"][-1]["mark"].endswith("82")


@pytest.mark.asyncio
@pytest.mark.parametrize("blocked", ["unknown", "active_writer"])
async def test_f1r_unresolved_writer_still_blocks_new_claim(db_session, blocked):
    order, _, _ = await _seed_order(db_session)
    transport = _transport(status={**_remote_snapshot(), "status": "ship_available"})
    await _accept_a(db_session, order, transport)
    claimed = await documents.claim_exemplar_write(
        db_session, order, None, kind="marking", choice={"marking_id": "first"}
    )
    if blocked == "unknown":
        claimed.update(state="unknown", in_flight=False, set_acknowledged=False)
        documents.store_document_data(order, claimed)
        await db_session.commit()
    view = await documents.get_exemplar_documents(
        db_session,
        tenant_id=order.tenant_id,
        order_id=order.id,
        provider=OzonMarketplaceProvider(transport=transport),
        client_id="fake-client",
        api_key="fake-key",
    )
    assert view["editable"] is False
    assert view["state"] == ("unknown" if blocked == "unknown" else "preparing")
    before = documents.document_data(order)
    calls_before = len(transport.endpoint_calls)
    with pytest.raises(process.OzonFbsProcessError) as error:
        await documents.claim_exemplar_write(
            db_session, order, before["version"],
            kind="marking", choice={"marking_id": "second"},
        )
    assert error.value.status_code == 409
    assert error.value.code == "ozon_exemplar_documents_conflict"
    assert documents.document_data(order) == before
    assert len(transport.endpoint_calls) == calls_before


@pytest.mark.asyncio
async def test_f1r_old_get_cannot_overwrite_newer_document_claim(db_session, monkeypatch):
    order, _, _ = await _seed_order(db_session)
    transport = _transport(status={**_remote_snapshot(), "status": "ship_available"})
    await _accept_a(db_session, order, transport)
    old_version = documents.document_data(order)["version"]
    provider = OzonMarketplaceProvider(transport=transport)
    original_call = provider.call
    newer = None

    async def call_with_concurrent_claim(**kwargs):
        nonlocal newer
        response = await original_call(**kwargs)
        if kwargs["path"] == STATUS:
            async with SessionLocal() as writer:
                writer_order = await documents.document_order(writer, order.tenant_id, order.id)
                newer = await documents.claim_exemplar_write(
                    writer, writer_order, old_version, kind="documents",
                    choice=dict(
                        product_id=SKU_ONE, exemplar_id=81, gtd="NEW-INPUT", rnpt=None,
                        is_gtd_absent=False, is_rnpt_absent=True,
                    ),
                )
        return response

    monkeypatch.setattr(provider, "call", call_with_concurrent_claim)
    view = await documents.get_exemplar_documents(
        db_session, tenant_id=order.tenant_id, order_id=order.id,
        provider=provider, client_id="fake-client", api_key="fake-key",
    )
    assert newer is not None
    assert view["version"] == old_version + 1
    assert view["state"] == "preparing"
    assert view["editable"] is False
    assert _exemplar(view)["gtd"] == "NEW-INPUT"
    assert documents.document_data(order) == newer
    assert len([1 for path, _ in transport.endpoint_calls if path == SET]) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["documents", "marking"])
async def test_f1r_accepted_operation_still_rejects_stale_version(db_session, kind):
    order, _, _ = await _seed_order(db_session)
    transport = _transport(status={**_remote_snapshot(), "status": "ship_available"})
    await _accept_a(db_session, order, transport)
    before = documents.document_data(order)
    calls_before = len(transport.endpoint_calls)
    choice = dict(
        product_id=SKU_TWO, exemplar_id=91, gtd=None, rnpt="STALE",
        is_gtd_absent=True, is_rnpt_absent=False,
    ) if kind == "documents" else {"marking_id": "stale"}
    with pytest.raises(process.OzonFbsProcessError) as error:
        await documents.claim_exemplar_write(
            db_session, order, before["version"] - 1, kind=kind, choice=choice
        )
    assert error.value.status_code == 409
    assert error.value.code == "ozon_exemplar_documents_conflict"
    assert documents.document_data(order) == before
    assert len(transport.endpoint_calls) == calls_before
