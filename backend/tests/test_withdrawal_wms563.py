"""WMS-563: размер страницы из адреса и выбор КИЗ больше одной страницы."""

from __future__ import annotations

import uuid
from unittest.mock import Mock

import httpx
import pytest
from test_withdrawal_ledger import (
    legacy_sales_http,  # noqa: F401 -- same synthetic I/O fixture
    seed,
)

from app.api.deps import get_current_user
from app.main import create_app
from app.models.user import User
from app.services.true_api_withdrawal import Environment, TrueApiConfig
from app.services.withdrawal_runtime import WithdrawalRuntime, get_withdrawal_runtime
from app.services.withdrawal_service import MAX_OPERATION_ROWS

PREFIX = "/operations/marking-codes/self/withdrawals"


@pytest.mark.asyncio
async def test_registry_accepts_page_size_from_query_string(db_session):
    scope, marking, _, _ = await seed(db_session)
    user = await db_session.get(User, scope.user_id)
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: user
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as http:
        for limit in (50, 100, 250):
            page = await http.get(PREFIX, params={"limit": limit, "offset": 0})
            assert page.status_code == 200, page.text
            assert [row["row_id"] for row in page.json()["rows"]] == [str(marking.id)]
        wrong = await http.get(PREFIX, params={"limit": 73})
        assert wrong.status_code == 422
        assert wrong.json()["detail"] == "invalid_pagination"


@pytest.mark.asyncio
async def test_create_accepts_selection_larger_than_one_page(db_session):
    scope, _, _, _ = await seed(db_session)
    user = await db_session.get(User, scope.user_id)
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: user
    provider = Mock(side_effect=AssertionError("create must not call provider"))
    app.dependency_overrides[get_withdrawal_runtime] = lambda: WithdrawalRuntime(
        TrueApiConfig(Environment.SANDBOX), provider
    )

    def payload(count: int) -> dict[str, object]:
        return {
            "row_ids": [str(uuid.uuid4()) for _ in range(count)],
            "client_request_id": str(uuid.uuid4()),
        }

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as http:
        # 251 чужих id проходят размер выбора и доходят до сверки строк.
        large = await http.post(PREFIX + "/operations", json=payload(251))
        assert large.status_code == 404, large.text
        assert large.json()["detail"] == "withdrawal_rows_not_found"
        too_large = await http.post(PREFIX + "/operations", json=payload(MAX_OPERATION_ROWS + 1))
        assert too_large.status_code == 422
    provider.assert_not_called()
