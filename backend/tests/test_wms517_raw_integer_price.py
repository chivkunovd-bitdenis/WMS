"""F3/R22: raw JSON integer parser overflow stays local to the affected sale item."""

# ruff: noqa: F811 -- imported pytest boundary fixtures are injected by name.

import json
import uuid

import httpx
import pytest
from test_withdrawal_orchestration import MOD, Emulator
from test_wms517_sales_contract import fixture_order, sale, sales_http  # noqa: F401
from test_wms517_sales_partial_decimal_regressions import add_same_scope_order
from test_wms517_sales_regressions import redis_boundary  # noqa: F401
from test_wms517_sales_report_singleflight_contract import redis_ownership_io  # noqa: F401

from app.api.deps import get_current_user
from app.db.session import SessionLocal
from app.db.withdrawal_repository import current_items
from app.main import create_app
from app.models.user import User
from app.services.withdrawal_runtime import get_withdrawal_runtime


@pytest.mark.asyncio
@pytest.mark.parametrize("mixed", [False, True], ids=["single", "healthy-neighbor"])
@pytest.mark.parametrize("propagate", [True, False], ids=["exception-trace", "http-status"])
async def test_raw_integer_finished_price_is_per_item_error(
    db_session, sales_http, redis_boundary, monkeypatch, mixed, propagate
):
    scope, bad_mark, bad_order, _ = await fixture_order(db_session, sales_http)
    marker = "RAW_INTEGER_PRICE_F3"
    integer_lexeme = "9" * 5000
    sales_http.rows = [sale(bad_order.wb_rid, identifier="S-raw-bad", price=marker)]
    selected = [bad_mark.id]
    if mixed:
        healthy_mark, healthy_order = await add_same_scope_order(
            db_session, bad_order, rid="raw-integer-healthy", serial="rawintegerB"
        )
        sales_http.rows.append(
            sale(healthy_order.wb_rid, identifier="S-raw-good", price="12.34")
        )
        selected.append(healthy_mark.id)

    # Reuse the real contract's paging/credentials fixture; replace only HTTP
    # response bytes. json= would quote the integer or convert it to float.
    original_handle = sales_http.handle
    raw_pages = []

    async def raw_handle(request):
        response = await original_handle(request)
        if marker.encode() not in response.content:
            return response
        content = response.content.replace(json.dumps(marker).encode(), integer_lexeme.encode())
        assert b'"finishedPrice":' + integer_lexeme.encode() in content
        assert json.dumps(integer_lexeme).encode() not in content
        raw_pages.append(content)
        return httpx.Response(
            200, content=content, headers={"Content-Type": "application/json"}, request=request
        )

    monkeypatch.setattr(sales_http, "handle", raw_handle)
    app = create_app()
    user = await db_session.get(User, scope.user_id)
    app.dependency_overrides[get_current_user] = lambda: user
    emulator = Emulator([MOD])
    async with httpx.AsyncClient(transport=httpx.MockTransport(emulator.handle)) as vendor:
        runtime = emulator.runtime(vendor)
        app.dependency_overrides[get_withdrawal_runtime] = lambda: runtime
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=propagate),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/operations/marking-codes/self/withdrawals/operations",
                json={
                    "row_ids": [str(row_id) for row_id in selected],
                    "client_request_id": str(uuid.uuid4()),
                },
            )
    assert raw_pages, "the public operation must read the raw integer HTTP sale"
    assert response.status_code == 200, "one invalid price must never crash the whole page"
    payload = response.json()
    public_items = {item["row_id"]: item for item in payload["items"]}
    assert set(public_items) == {str(row_id) for row_id in selected}
    assert public_items[str(bad_mark.id)]["error"]["code"] == "invalid_sale_price"
    async with SessionLocal() as reader:
        items = {
            item.marking_id: item
            for item in await current_items(reader, scope, uuid.UUID(payload["operation_id"]))
        }
        assert set(items) == set(selected)
        bad = items[bad_mark.id]
        assert bad.state == "failed" and bad.product_cost is None
        assert bad.error["code"] == "invalid_sale_price"
        assert bad.document_id is None
        assert bad.preflight_evidence["wb_sale"]["finishedPrice"] == integer_lexeme
        if mixed:
            healthy = items[healthy_mark.id]
            assert healthy.state == "pending" and healthy.product_cost == 1234
    if not mixed:
        assert payload["state"] == "failed"
    assert payload["documents"] == []
    assert not emulator.calls
