from __future__ import annotations

import asyncio
import logging

from app.celery_app import celery_app
from app.core.settings import settings

logger = logging.getLogger(__name__)


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


@celery_app.task(name="wms.client_registry_google_sheets_sync")
def run_client_registry_google_sheets_sync_task() -> None:
    """Export the WMS-515 register without retrying a failed Google request in a loop."""
    if not (
        settings.google_sheets_client_registry_sheet_id
        and settings.google_sheets_service_account_file
    ):
        logger.error("client_registry_google_sheets_sync skipped: configuration_missing")
        return

    from app.services.client_registry_google_sheets_service import (
        ClientRegistryGoogleSheetsError,
        GoogleSheetsClientRegistryGateway,
        sync_client_registry,
    )

    gateway = GoogleSheetsClientRegistryGateway(
        spreadsheet_id=settings.google_sheets_client_registry_sheet_id,
        service_account_file=settings.google_sheets_service_account_file,
    )
    try:
        asyncio.run(sync_client_registry(gateway))
    except ClientRegistryGoogleSheetsError as exc:
        # Do not include provider exception text: it can contain paths, account details,
        # or request metadata. The next Beat run performs the idempotent upsert again.
        logger.error("client_registry_google_sheets_sync failed: %s", exc.code)
    except Exception:
        # A scheduled reporting failure must not enter a Celery retry storm or
        # surface connection/request details. The next scheduled run is the recovery path.
        logger.error("client_registry_google_sheets_sync failed: unexpected_error")


async def _run_billing_invoices_daily() -> None:
    """Compatibility no-op for older application messages."""
    return None
