import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services import fbs_order_tape_print_service as service
from app.services.fbs_print_asset_service import PrintBatchResult


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "layout, include_order_qr",
    [({"units": []}, True), ({"units": [{"block": "label", "copies": 1}]}, False)],
)
async def test_qr_only_tape_does_not_allocate_or_print_honest_sign(
    monkeypatch: pytest.MonkeyPatch,
    layout: dict,
    include_order_qr: bool,
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
    ordinary_order_id = uuid.uuid4()
    ordinary_order = SimpleNamespace(
        id=ordinary_order_id,
        wb_order_id=123457,
        product_id=uuid.uuid4(),
        product=SimpleNamespace(requires_honest_sign=False),
        required_meta_json=[],
    )
    supply = SimpleNamespace(
        honest_sign_skipped_at=None,
        packaging_task_id=None,
        marketplace="wb",
        status="delivered",
        orders=[order, ordinary_order, SimpleNamespace(id=uuid.uuid4())],
    )
    qr_asset = SimpleNamespace(
        id=qr_asset_id,
        fbs_order_id=order_id,
        status="ready",
    )
    ordinary_qr_asset_id = uuid.uuid4()
    ordinary_qr_asset = SimpleNamespace(
        id=ordinary_qr_asset_id,
        fbs_order_id=ordinary_order_id,
        status="ready",
    )
    batch = PrintBatchResult(
        requested=2,
        ready=2,
        missing=0,
        failed=0,
        assets=[qr_asset, ordinary_qr_asset],
    )
    preflight = AsyncMock()
    print_code = AsyncMock()
    monkeypatch.setattr(service, "_load_supply", AsyncMock(return_value=supply))
    monkeypatch.setattr(
        service,
        "_orders_in_requested_order",
        lambda *_: [order, ordinary_order],
    )
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
        order_ids=[order_id, ordinary_order_id],
        layout=layout,
        allow_partial=False,
        include_order_qr=include_order_qr,
        reprint=False,
        actor_user_id=uuid.uuid4(),
        http_client=SimpleNamespace(),
    )

    assert result.shortage == 0
    assert result.order_errors == []
    assert len(result.orders) == 2
    assert result.orders[0].qr_asset_id == (qr_asset_id if include_order_qr else None)
    assert result.orders[0].requires_honest_sign is True
    assert result.orders[0].codes == []
    assert result.orders[0].printed_codes == []
    assert result.orders[1].qr_asset_id == (ordinary_qr_asset_id if include_order_qr else None)
    assert result.orders[1].requires_honest_sign is False
    assert result.orders[1].codes == []
    assert result.orders[1].printed_codes == []
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


@pytest.mark.asyncio
@pytest.mark.parametrize("saved_code", ["pool", "operator", "missing"])
async def test_delivered_wb_reuses_saved_code_without_packaging_task(
    monkeypatch: pytest.MonkeyPatch, saved_code: str,
) -> None:
    order = SimpleNamespace(
        id=uuid.uuid4(), wb_order_id=12, product_id=uuid.uuid4(),
        product=SimpleNamespace(requires_honest_sign=True), required_meta_json=["sgtin"],
    )
    supply = SimpleNamespace(
        marketplace="wb", status="in_delivery", packaging_task_id=None,
        document_number="FBS-TEST", honest_sign_skipped_at=None,
        orders=[order, SimpleNamespace(id=uuid.uuid4())],
    )
    code = SimpleNamespace(id=uuid.uuid4(), cis_code="saved-test-cis", label_artifact_pdf=b"pdf")
    marking = None if saved_code == "missing" else SimpleNamespace(
        source=saved_code, marking_code=code,
    )
    monkeypatch.setattr(service, "_load_supply", AsyncMock(return_value=supply))
    monkeypatch.setattr(service, "_line_by_product", AsyncMock(return_value={}))
    monkeypatch.setattr(service, "_existing_sgtin_marking", lambda _: marking)
    allocate = AsyncMock()
    attach_to_wb = AsyncMock()
    record_event = AsyncMock()
    monkeypatch.setattr(service.mc_svc, "print_codes_for_packaging_line", allocate)
    monkeypatch.setattr(service.mc_svc, "record_event", record_event)
    monkeypatch.setattr(service.marking_svc, "attach_order_meta_to_wb_and_sync", attach_to_wb)

    result = await service.print_fbs_order_tape(
        AsyncMock(), uuid.uuid4(), uuid.uuid4(), order_ids=[order.id],
        layout={"units": [{"block": "cz", "copies": 2}]},
        allow_partial=False, include_order_qr=False, reprint=True,
        actor_user_id=uuid.uuid4(), http_client=SimpleNamespace(),
    )

    allocate.assert_not_awaited()
    attach_to_wb.assert_not_awaited()
    assert supply.packaging_task_id is None
    if saved_code == "pool":
        assert result.order_errors == []
        assert result.orders[0].codes == [code.cis_code]
        assert result.orders[0].printed_codes[0].id == code.id
        record_event.assert_awaited_once()
        assert record_event.call_args.kwargs["copies"] == 2
        assert record_event.call_args.kwargs.get("packaging_task") is None
    else:
        assert result.orders == []
        assert result.order_errors[0].code == (
            "operator_kiz_print_forbidden"
            if saved_code == "operator" else "packaging_line_not_found"
        )
        record_event.assert_not_awaited()
