from app.celery_app import celery_app


def test_billing_invoice_daily_schedule_is_0230_moscow() -> None:
    schedule = celery_app.conf.beat_schedule["billing-invoices-daily"]["schedule"]

    assert celery_app.conf.timezone == "Europe/Moscow"
    assert schedule._orig_hour == 2
    assert schedule._orig_minute == 30
