import pickle
from datetime import timedelta

from app.celery_app import celery_app


def test_beat_schedule_survives_persistent_scheduler_serialization() -> None:
    restored = pickle.loads(pickle.dumps(celery_app.conf.beat_schedule))
    schedule = restored["billing-storage-daily"]["schedule"]
    assert schedule.now().utcoffset() == timedelta(hours=3)
    assert set(restored) == set(celery_app.conf.beat_schedule)
