from __future__ import annotations

import pytest

from app.celery_app import celery_app
from app.tasks import billing_tasks


@pytest.mark.asyncio
async def test_already_queued_daily_invoice_task_is_a_db_free_noop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """TC-NEW-0409: the retired automatic writer cannot revive from an old message."""
    def forbidden(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("legacy daily invoice task must not touch dependencies")

    monkeypatch.setattr(billing_tasks, "SessionLocal", forbidden, raising=False)
    monkeypatch.setattr(billing_tasks, "form_invoice", forbidden, raising=False)

    await billing_tasks._run_billing_invoices_daily()
    billing_tasks.run_billing_invoices_daily_task()


def test_beat_has_no_automatic_invoice_task() -> None:
    assert all(
        value.get("task") != "wms.billing_invoices_daily"
        for value in celery_app.conf.beat_schedule.values()
        if isinstance(value, dict)
    )
