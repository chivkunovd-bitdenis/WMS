"""Owner delta: one explicit posting absence action, no per-exemplar SET loop.

These tests precede implementation. Existing customs/marking guards stay intact.
"""

import uuid
from copy import deepcopy

import pytest
from test_wms663_astra_regressions import SET, SNAPSHOT, STATUS, _exemplar
from test_wms663_customs_documents_contract import (
    POSTING_NUMBER,
    SKU_ONE,
    SKU_TWO,
    _AppliedThenLostTransport,
    _remote_snapshot,
    _seed_order,
    _transport,
)

from app.db.session import SessionLocal
from app.services import ozon_exemplar_documents_service as documents
from app.services.marketplace_provider import OzonMarketplaceProvider
from app.services.ozon_fbs_errors import OzonFbsProcessError


def operation():
    save = getattr(documents, "save_absent_exemplar_documents", None)
    assert callable(save), "Owner663: the explicit one-SET posting absence operation is missing"
    return save


def kwargs(order, transport):
    return dict(tenant_id=order.tenant_id, order_id=order.id,
                provider=OzonMarketplaceProvider(transport=transport),
                client_id="fake-client", api_key="fake-key")


def writes(transport):
    return [deepcopy(payload) for path, payload in transport.endpoint_calls if path == SET]


def expected_payload():
    snapshot = _remote_snapshot()
    expected = {"posting_number": POSTING_NUMBER, "multi_box_qty": snapshot["multi_box_qty"],
                "products": [{"product_id": product["product_id"],
                              "exemplars": deepcopy(product["exemplars"])}
                             for product in snapshot["products"]]}
    # Only required document kinds change; this must preserve the RNPT of SKU_ONE
    # and GTD of SKU_TWO, all marks, weights, IDs and every other payload field.
    for sku, exemplar_id, kind in [
        (SKU_ONE, 81, "gtd"), (SKU_ONE, 82, "gtd"), (SKU_TWO, 91, "rnpt")
    ]:
        _exemplar(expected, sku, exemplar_id).update({kind: "", f"is_{kind}_absent": True})
    return expected


@pytest.mark.asyncio
async def test_one_explicit_batch_sets_all_required_exemplars_once_and_preserves_rest(db_session):
    save = operation()
    order, _, _ = await _seed_order(db_session)
    order.meta_details_json = {"unrelated_metadata": "keep"}
    await db_session.commit()
    transport = _transport(status={**_remote_snapshot(), "status": "validation_in_process"})
    result = await save(db_session, **kwargs(order, transport), expected_version=0)
    assert writes(transport) == [expected_payload()]
    assert [path for path, _ in transport.endpoint_calls].count(STATUS) == 1
    assert result["state"] in {"checking", "unknown"}  # HTTP 200 alone is not acceptance.
    assert {payload["posting_number"] for _, payload in transport.endpoint_calls} == {
        POSTING_NUMBER
    }
    await db_session.refresh(order)
    assert order.meta_details_json["unrelated_metadata"] == "keep"
    saved = documents.document_data(order)
    assert saved["version"] == 1
    assert set(saved["choices"]) == {f"{SKU_ONE}:81", f"{SKU_ONE}:82", f"{SKU_TWO}:91"}


@pytest.mark.asyncio
async def test_unknown_batch_survives_restart_and_repeat_only_reads_status(db_session):
    save = operation()
    order, _, _ = await _seed_order(db_session)
    transport = _AppliedThenLostTransport(endpoint_responses={
        SNAPSHOT: _remote_snapshot(), STATUS: {"posting_number": POSTING_NUMBER,
            "status": "validation_in_process", "products": []},
    })
    result = await save(db_session, **kwargs(order, transport), expected_version=0)
    assert result["state"] in {"unknown", "checking"}
    assert writes(transport) == [expected_payload()]
    await db_session.refresh(order)
    version = documents.document_data(order)["version"]
    assert version == 1
    # New DB session represents a restarted worker/client; keep Ozon unresolved.
    before = len(transport.endpoint_calls)
    async with SessionLocal() as restarted:
        read = await documents.get_exemplar_documents(restarted, **kwargs(order, transport))
        assert read["state"] in {"unknown", "checking"}
        try:
            repeated = await save(restarted, **kwargs(order, transport), expected_version=version)
        except OzonFbsProcessError as error:
            assert error.status_code == 409
        else:
            assert repeated["state"] in {"unknown", "checking"}
    assert writes(transport) == [expected_payload()]
    assert all(path == STATUS for path, _ in transport.endpoint_calls[before:])
    await db_session.refresh(order)
    assert documents.document_data(order)["version"] == version


@pytest.mark.asyncio
@pytest.mark.parametrize("foreign", ["tenant", "wb"])
async def test_batch_rejects_foreign_tenant_or_wb_before_marketplace_io(db_session, foreign):
    save = operation()
    order, _, _ = await _seed_order(db_session)
    transport = _transport()
    args = kwargs(order, transport)
    if foreign == "tenant":
        args["tenant_id"] = uuid.uuid4()
    else:
        order.marketplace = "wb"
        await db_session.commit()
    with pytest.raises(OzonFbsProcessError) as rejected:
        await save(db_session, **args, expected_version=0)
    assert rejected.value.status_code == (404 if foreign == "tenant" else 400)
    assert transport.endpoint_calls == []


@pytest.mark.asyncio
async def test_stale_batch_version_is_rejected_without_set(db_session):
    save = operation()
    order, _, _ = await _seed_order(db_session)
    transport = _transport()
    with pytest.raises(OzonFbsProcessError) as rejected:
        await save(db_session, **kwargs(order, transport), expected_version=99)
    assert rejected.value.status_code == 409
    assert writes(transport) == []
