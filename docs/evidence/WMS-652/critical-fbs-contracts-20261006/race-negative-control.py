"""Evidence-only in-memory mutations; no product-file edits and no external HTTP."""
import pytest
from app.services import fbs_supply_service as service
from tests.test_fbs_supply_from_orders import (
    test_parallel_from_orders_one_order_one_supply as _actual_race,
)

@pytest.mark.asyncio
@pytest.mark.parametrize("broken", ["generic-503", "wrong-canonical-id", "not-retryable"])
async def test_actual_race_rejects_wrong_pending_contract(async_client, monkeypatch, broken):
    original = service._create_operation_in_progress
    def corrupted(operation):
        error = original(operation)
        if broken == "generic-503":
            error.code = "arbitrary_database_error"
        elif broken == "wrong-canonical-id":
            error.context["operation_id"] = "foreign-operation"
        else:
            error.retryable = False
        return error
    monkeypatch.setattr(service, "_create_operation_in_progress", corrupted)
    from app.core.settings import settings
    monkeypatch.setattr(settings, "e2e_mock_wb_marketplace_supplies", True)
    await _actual_race(async_client, None, monkeypatch)
