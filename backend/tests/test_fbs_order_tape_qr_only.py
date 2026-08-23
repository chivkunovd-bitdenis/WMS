import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services import fbs_order_tape_print_service as service
from app.services.fbs_print_asset_service import PrintBatchResult


@pytest.mark.asyncio
async def test_qr_only_tape_does_not_allocate_or_print_honest_sign(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant_id = uuid.uuid4()
    supply_id = uuid.uuid4()
    order_id = uuid.uuid4()
    qr_asset_id = uuid.uuid4()
    order = SimpleNamespace(
        id=order_id,
        wb_order_id=123456,
        product_id=uuid.uuid4(),
        product=SimpleNamespace(requires_honest_sign=True),
        required_meta_json=["sgtin"],
    )
    supply = SimpleNamespace(
        honest_sign_skipped_at=None,
        orders=[order, SimpleNamespace(id=uuid.uuid4())],
    )
    qr_asset = SimpleNamespace(
        id=qr_asset_id,
        fbs_order_id=order_id,
        status="ready",
    )
    batch = PrintBatchResult(
        requested=1,
        ready=1,
        missing=0,
        failed=0,
        assets=[qr_asset],
    )
    preflight = AsyncMock()
    print_code = AsyncMock()
    monkeypatch.setattr(service, "_load_supply", AsyncMock(return_value=supply))
    monkeypatch.setattr(service, "_orders_in_requested_order", lambda *_: [order])
    monkeypatch.setattr(service, "_line_by_product", AsyncMock(return_value={}))
    monkeypatch.setattr(service, "_preflight_new_code_shortage", preflight)
    monkeypatch.setattr(service, "_print_or_reprint_order_code", print_code)
    monkeypatch.setattr(service, "request_supply_print_batch", AsyncMock(return_value=batch))
    monkeypatch.setattr(
        service.pack_int_svc,
        "try_promote_fbs_supply_if_ready",
        AsyncMock(),
    )
    session = AsyncMock()

    result = await service.print_fbs_order_tape(
        session,
        tenant_id,
        supply_id,
        order_ids=[order_id],
        layout={"units": []},
        allow_partial=False,
        include_order_qr=True,
        reprint=False,
        actor_user_id=uuid.uuid4(),
        http_client=SimpleNamespace(),
    )

    assert result.shortage == 0
    assert result.order_errors == []
    assert len(result.orders) == 1
    assert result.orders[0].qr_asset_id == qr_asset_id
    assert result.orders[0].requires_honest_sign is True
    assert result.orders[0].codes == []
    assert result.orders[0].printed_codes == []
    preflight.assert_not_awaited()
    print_code.assert_not_awaited()


@pytest.mark.asyncio
async def test_empty_tape_without_order_qr_is_rejected() -> None:
    with pytest.raises(service.FbsOrderTapePrintError, match="invalid_layout_json"):
        await service.print_fbs_order_tape(
            AsyncMock(),
            uuid.uuid4(),
            uuid.uuid4(),
            order_ids=[uuid.uuid4()],
            layout={"units": []},
            allow_partial=False,
            include_order_qr=False,
            reprint=False,
            actor_user_id=uuid.uuid4(),
            http_client=SimpleNamespace(),
        )
