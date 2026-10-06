"""Service regressions for F1/P1, F2/P1 and F3/P2 of the 7d9e9 review."""

from copy import deepcopy

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from test_wms663_customs_documents_contract import (
    POSTING_NUMBER,
    SKU_ONE,
    SKU_TWO,
    _remote_snapshot,
    _seed_order,
    _transport,
)

from app.models.fbs_order import FbsOrderMarking
from app.services import ozon_exemplar_documents_service as documents
from app.services import ozon_fbs_process_service as process
from app.services.marketplace_provider import OzonMarketplaceProvider

STATUS = "/v5/fbs/posting/product/exemplar/status"
SNAPSHOT = "/v6/fbs/posting/product/exemplar/create-or-get"
SET = "/v6/fbs/posting/product/exemplar/set"


def _exemplar(payload, sku=SKU_ONE, exemplar_id=81):
    return next(
        item
        for product in payload["products"]
        if product["product_id"] == sku
        for item in product["exemplars"]
        if item["exemplar_id"] == exemplar_id
    )


async def _accept_a(session, order, transport):
    result = await documents.save_exemplar_documents(
        session,
        tenant_id=order.tenant_id,
        order_id=order.id,
        product_id=SKU_ONE,
        exemplar_id=81,
        gtd="001/ABC-09",
        is_gtd_absent=False,
        rnpt=None,
        is_rnpt_absent=True,
        expected_version=None,
        provider=OzonMarketplaceProvider(transport=transport),
        client_id="fake-client",
        api_key="fake-key",
    )
    assert result["state"] == "accepted"


async def _scan(session, order, position, transport, exemplar_id):
    marking = FbsOrderMarking(
        tenant_id=order.tenant_id,
        order_id=order.id,
        order_product_id=position.id,
        kind="sgtin",
        value=f"010460000000000121REGRESSION{exemplar_id}",
        meta_details_json={"exemplar_id": exemplar_id},
    )
    session.add(marking)
    await session.commit()
    return await process.submit_marking(
        session,
        order=order,
        marking=marking,
        provider=OzonMarketplaceProvider(transport=transport),
        client_id="fake-client",
        api_key="fake-key",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("next_write", ["documents_b", "marking"])
async def test_f1_accepted_a_cabinet_edit_survives_next_write(
    db_session: AsyncSession, next_write: str
) -> None:
    order, first, _ = await _seed_order(db_session)
    transport = _transport(status={**_remote_snapshot(), "status": "ship_available"})
    await _accept_a(db_session, order, transport)
    fresh = deepcopy(_remote_snapshot())
    _exemplar(fresh).update(
        gtd="NEW-CABINET", rnpt="NEW-RNPT", is_gtd_absent=False, is_rnpt_absent=False
    )
    transport.endpoint_responses[SNAPSHOT] = fresh
    transport.endpoint_responses[STATUS] = {**fresh, "status": "ship_available"}
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
            expected_version=None,
            provider=OzonMarketplaceProvider(transport=transport),
            client_id="fake-client",
            api_key="fake-key",
        )
    else:
        await _scan(db_session, order, first, transport, 82)
    writes = [payload for path, payload in transport.endpoint_calls if path == SET]
    assert len(writes) == 2
    actual_a = _exemplar(writes[-1])
    for field in ("gtd", "rnpt", "is_gtd_absent", "is_rnpt_absent", "weight", "marks"):
        assert actual_a[field] == _exemplar(fresh)[field], field
    if next_write == "documents_b":
        assert _exemplar(writes[-1], SKU_TWO, 91)["rnpt"] == "NEW-B"
    else:
        assert _exemplar(writes[-1], SKU_ONE, 82)["marks"][-1]["mark"].endswith("82")


@pytest.mark.asyncio
async def test_f2_explicit_get_refresh_releases_update_not_available(
    db_session: AsyncSession,
) -> None:
    order, _, _ = await _seed_order(db_session)
    transport = _transport(status={**_remote_snapshot(), "status": "update_not_available"})
    transport.endpoint_responses["/v3/posting/fbs/get"] = {
        "result": {"posting_number": POSTING_NUMBER, "requirements": {}}
    }
    kwargs = dict(
        tenant_id=order.tenant_id,
        order_id=order.id,
        provider=OzonMarketplaceProvider(transport=transport),
        client_id="fake-client",
        api_key="fake-key",
    )
    initial = await documents.get_exemplar_documents(db_session, **kwargs)
    assert initial["status"] == "update_not_available"
    assert initial["editable"] is False
    transport.endpoint_responses[STATUS] = {**_remote_snapshot(), "status": "update_available"}
    before = len(transport.endpoint_calls)
    refreshed = await documents.get_exemplar_documents(db_session, **kwargs)
    assert refreshed["status"] == "update_available"
    assert refreshed["editable"] is True
    assert any(path == STATUS for path, _ in transport.endpoint_calls[before:])
    assert not any(path == SET for path, _ in transport.endpoint_calls)
    assert documents.document_data(order)["status"] == "update_available"


@pytest.mark.asyncio
async def test_f3_accepted_gtd_then_two_acknowledged_kiz_writes_continue(
    db_session: AsyncSession,
) -> None:
    order, first, _ = await _seed_order(db_session)
    transport = _transport(status={**_remote_snapshot(), "status": "ship_available"})
    await _accept_a(db_session, order, transport)
    transport.endpoint_responses[STATUS] = {
        **_remote_snapshot(), "status": "validation_in_process"
    }
    await _scan(db_session, order, first, transport, 81)
    pending = documents.document_data(order)
    assert pending["state"] == "checking"
    assert pending["set_acknowledged"] is True
    assert pending["in_flight"] is False
    await _scan(db_session, order, first, transport, 82)
    writes = [payload for path, payload in transport.endpoint_calls if path == SET]
    assert len(writes) == 3
    assert _exemplar(writes[-1], SKU_ONE, 82)["marks"][-1]["mark"].endswith("82")
    assert _exemplar(writes[-1])["gtd"] == "001/ABC-09"


@pytest.mark.asyncio
@pytest.mark.parametrize("blocked", ["unknown", "active_writer"])
async def test_f3_unresolved_or_active_writer_still_conflicts(
    db_session: AsyncSession, blocked: str
) -> None:
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
    count = len(transport.endpoint_calls)
    with pytest.raises(process.OzonFbsProcessError) as error:
        await documents.claim_exemplar_write(
            db_session, order, None, kind="marking", choice={"marking_id": "second"}
        )
    assert error.value.status_code == 409
    assert error.value.code == "ozon_exemplar_documents_conflict"
    assert len(transport.endpoint_calls) == count
