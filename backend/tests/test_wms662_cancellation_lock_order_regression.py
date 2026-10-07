"""WMS-662 F6 regression: a later pool checkout must not erase a confirmed wait."""

from __future__ import annotations

import pytest
import test_wms662_cancellation_lock_order as f6


class _Observer:
    async def scalar(self, statement, params):
        assert "pg_blocking_pids" in str(statement)
        assert params == {"cancel_pid": 902, "handoff_pid": 901}
        return True


class _ObserverContext:
    async def __aenter__(self):
        return _Observer()

    async def __aexit__(self, exc_type, exc, traceback):
        return False


@pytest.mark.asyncio
async def test_f6_confirmed_wait_pid_pair_survives_postrelease_pool_reuse(monkeypatch):
    schedule = f6.LockSchedule()
    schedule.pids.update({"handoff": 901, "cancel": 902})
    monkeypatch.setattr(f6, "SessionLocal", _ObserverContext)

    await schedule.wait_for_contention()

    # The normal handoff may check out another connection after cancellation
    # releases. This is live diagnostic state, not proof of the past wait.
    schedule.pids["handoff"] = 902
    assert schedule.pids == {"handoff": 902, "cancel": 902}
    assert schedule.observed_pids == {"handoff": 901, "cancel": 902}
