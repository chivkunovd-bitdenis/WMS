from __future__ import annotations

import asyncio

from app.celery_app import celery_app


@celery_app.task(name="wms.billing_invoices_daily")
def run_billing_invoices_daily_task() -> None:
    """Compatibility no-op for messages queued before Wave 4 removed beat.

    Задача остаётся зарегистрированной намеренно и в расписание не возвращается:
    счета выставляет человек, автоматического писателя счетов нет. Удалить её
    нельзя — старое сообщение из очереди уронило бы воркера NotRegistered.
    """
    return None


@celery_app.task(name="wms.billing_storage_daily")
def run_billing_storage_daily_task() -> None:
    """Ночное начисление за хранение: литро-дни прошедших суток по всем товарам."""
    from app.services.storage_daily_charge_service import run_daily_storage_charge_all_tenants

    asyncio.run(run_daily_storage_charge_all_tenants())


async def _run_billing_invoices_daily() -> None:
    """Compatibility no-op for older application messages."""
    return None
