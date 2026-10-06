"""API/storage contract for grouped WB delivery errors in WMS-653."""

from __future__ import annotations

import json
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.fbs_wb_operation import WB_OPERATION_STATE_FAILED, FbsWbOperation
from app.services.wildberries_errors import (
    MetaValidationFailItem,
    WildberriesBusinessError,
)
from tests.test_fbs_shipment_warehouse_sc import (
    _create_and_fill_physical_box,
    _deliver_with_preflight,
    _prepare_supply_with_orders,
    _register_ff_admin,
    _setup_seller_with_token,
)


# WMS-653 C4/C11: смешанный ответ даёт две операторские группы, а исходные
# decision/reason/value остаются только в существующем журнале операции.
@pytest.mark.asyncio
async def test_wms653_mixed_response_preserves_groups_and_raw_reason(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    wb_order_ids = [287890531, 287890532]
    supply, order_ids = await _prepare_supply_with_orders(
        async_client,
        headers,
        seller_id,
        warehouse_id,
        tenant_id,
        wb_order_ids=wb_order_ids,
        supply_name="WMS-653 mixed KIZ",
    )
    await _create_and_fill_physical_box(async_client, headers, supply["id"], order_ids)

    pending_kiz = "0104600000000017215AbCdEfGh-WMS653-PENDING"
    rejected_kiz = "0104600000000017215AbCdEfGh-WMS653-REJECTED"
    rejection_reason = "КИЗ уже использован в другом заказе"
    raw_body = json.dumps(
        {
            "code": "MetaValidationFail",
            "orders": [
                {
                    "id": wb_order_ids[0],
                    "metaDetails": [
                        {"key": "sgtin", "value": pending_kiz, "decision": "pending"}
                    ],
                },
                {
                    "id": wb_order_ids[1],
                    "metaDetails": [
                        {
                            "key": "sgtin",
                            "value": rejected_kiz,
                            "decision": "rejected",
                            "reason": rejection_reason,
                        }
                    ],
                },
            ],
        },
        ensure_ascii=False,
    )

    async def reject_mixed(*_args: object, **_kwargs: object) -> None:
        raise WildberriesBusinessError(
            "meta_validation_fail",
            status_code=409,
            wb_code="MetaValidationFail",
            message="Meta validation failed",
            response_body=raw_body,
            meta_validation=[
                MetaValidationFailItem(
                    order_id=wb_order_ids[0],
                    key="sgtin",
                    value=pending_kiz,
                    decision="pending",
                ),
                MetaValidationFailItem(
                    order_id=wb_order_ids[1],
                    key="sgtin",
                    value=rejected_kiz,
                    decision="rejected",
                    reason=rejection_reason,
                ),
            ],
        )

    monkeypatch.setattr(
        "app.services.fbs_shipment_service.deliver_marketplace_supply",
        reject_mixed,
    )
    idempotency_key = str(uuid.uuid4())
    response = await _deliver_with_preflight(
        async_client,
        headers,
        supply["id"],
        idempotency_key=idempotency_key,
    )

    assert response.status_code == 409, response.text
    detail = response.json()["detail"]
    assert detail["context"]["operator_errors"] == [
        {
            "title": "Wildberries ещё обрабатывает КИЗы",
            "orders": [wb_order_ids[0]],
        },
        {
            "title": "Wildberries не принял КИЗы",
            "orders": [wb_order_ids[1]],
            "message": rejection_reason,
        },
    ]
    public_payload = json.dumps(detail, ensure_ascii=False)
    assert pending_kiz not in public_payload
    assert rejected_kiz not in public_payload
    assert '"decision"' not in public_payload
    assert '"sgtin"' not in public_payload

    async with SessionLocal() as session:
        operation = await session.scalar(
            select(FbsWbOperation).where(
                FbsWbOperation.idempotency_key == idempotency_key
            )
        )
        assert operation is not None
        assert operation.state == WB_OPERATION_STATE_FAILED
        saved = operation.error_context_json
        assert saved is not None
        assert saved["wb_code"] == "MetaValidationFail"
        assert saved["wb_response_body"] == raw_body
        assert saved["meta_validation"][0]["value"] == pending_kiz
        assert saved["meta_validation"][0]["decision"] == "pending"
        assert saved["meta_validation"][1]["value"] == rejected_kiz
        assert saved["meta_validation"][1]["decision"] == "rejected"
        assert saved["meta_validation"][1]["reason"] == rejection_reason
