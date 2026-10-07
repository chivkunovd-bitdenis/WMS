"""WMS-689: default beat restart retains catalog stop and other operations."""

import importlib

from celery.beat import PersistentScheduler

from app import celery_app as celery_module


def test_default_restart_removes_only_full_catalog_schedule(tmp_path):
    app = importlib.reload(celery_module).celery_app
    expected = {
        "developer-requests-sync", "withdrawal-poll", "wb-mp-warehouses-daily",
        "marking-low-stock", "fbs-orders-autopoll", "fbs-orders-full-reconcile",
        "fbs-order-statuses-autopoll", "fbs-marking-verdicts-autopoll",
        "fbs-stock-reconcile", "billing-storage-daily",
    }
    assert set(app.conf.beat_schedule) == expected
    # Real persistent scheduler must also remove an entry left by an old release.
    path = str(tmp_path / "beat-schedule")
    schedule = dict(app.conf.beat_schedule)
    app.conf.beat_schedule = {
        **schedule,
        "wb-catalog-hourly": {"task": "wms.wb_catalog_hourly_sync", "schedule": 3600},
    }
    previous = PersistentScheduler(app=app, schedule_filename=path)
    assert "wb-catalog-hourly" in previous.schedule
    previous.close()
    app.conf.beat_schedule = schedule
    restarted = PersistentScheduler(app=app, schedule_filename=path)
    try:
        assert "wb-catalog-hourly" not in restarted.schedule
        assert expected <= set(restarted.schedule)
    finally:
        restarted.close()
