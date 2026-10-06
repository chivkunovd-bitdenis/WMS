"""F3 continuation: nonempty requirements are not necessarily complete."""

from copy import deepcopy

import pytest
from test_wms663_customs_documents_contract import (
    POSTING_NUMBER,
    _remote_snapshot,
    _seed_order,
    _transport,
)
from test_wms663_owner_absent_batch_contract import kwargs

from app.services import ozon_exemplar_documents_service as documents


@pytest.mark.asyncio
@pytest.mark.parametrize("shape", ["full", "missing_sku", "missing_quantity"])
async def test_requirements_complete_matches_all_existing_skus_and_quantities(db_session, shape):
    order, _, _ = await _seed_order(db_session)  # Two local SKUs, quantities 2 and 1.
    snapshot = deepcopy(_remote_snapshot())
    if shape == "missing_sku":
        snapshot["products"] = snapshot["products"][:1]
    elif shape == "missing_quantity":
        snapshot["products"][0]["exemplars"] = snapshot["products"][0]["exemplars"][:1]
    transport = _transport(status={**snapshot, "status": "update_available"})
    transport.endpoint_responses["/v3/posting/fbs/get"] = {
        "result": {"posting_number": POSTING_NUMBER, "requirements": {}}
    }
    view = await documents.get_exemplar_documents(db_session, **kwargs(order, transport))
    # All displayed flags say false, even when the required local SKU was omitted.
    assert all(
        not exemplar["gtd_required"] and not exemplar["rnpt_required"]
        for product in view["products"] for exemplar in product["exemplars"]
    )
    assert view.get("requirements_complete") is (shape == "full")
    assert not any(path.endswith("/set") for path, _ in transport.endpoint_calls)
