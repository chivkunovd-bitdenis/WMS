"""WMS-402: file delivery, replay safety and tenant/warehouse boundaries."""

import uuid

import fitz
import pytest
from sqlalchemy import func, select

from app.models.background_job import BackgroundJob
from app.models.fbs_print_asset import FbsPrintAsset
from app.models.fbs_supply import FbsSupply
from app.models.seller import Seller
from app.models.tenant import Tenant
from app.models.warehouse import Warehouse
from app.services import fbs_print_job_service as jobs
from app.services.fbs_print_asset_service import FbsPrintAssetError


@pytest.mark.asyncio
async def test_document_replay_claim_and_queue_receipt_do_not_repeat_print(db_session):
    tenant = Tenant(name="Print fixture", slug=uuid.uuid4().hex)
    db_session.add(tenant)
    await db_session.flush()
    seller = Seller(tenant_id=tenant.id, name="Print seller")
    warehouse = Warehouse(tenant_id=tenant.id, name="Print warehouse", code="PRINT")
    db_session.add_all([seller, warehouse])
    await db_session.flush()
    supply = FbsSupply(
        tenant_id=tenant.id, seller_id=seller.id, warehouse_id=warehouse.id,
        marketplace="ozon", name="Print supply", delivery_type="warehouse_sc",
    )
    db_session.add(supply)
    await db_session.flush()
    with fitz.open() as pdf:
        pdf.new_page(width=164.41, height=113.39).insert_text((10, 20), "WMS-402")
        document = pdf.tobytes()
    job_id, user_id = uuid.uuid4(), uuid.uuid4()
    args = dict(job_id=job_id, supply_id=supply.id, document=document, user_id=user_id)
    job = await jobs.create_document_print_job(db_session, tenant.id, **args)
    await db_session.commit()
    replay = await jobs.create_document_print_job(db_session, tenant.id, **args)
    assert replay.id == job.id
    assert await db_session.scalar(select(func.count()).select_from(FbsPrintAsset)) == 1
    assert await db_session.scalar(select(func.count()).select_from(BackgroundJob)) == 1

    with pytest.raises(FbsPrintAssetError) as other_tenant:
        await jobs.get_print_job(db_session, uuid.uuid4(), job.id)
    assert other_tenant.value.code == "print_job_not_found"
    with pytest.raises(FbsPrintAssetError) as premature:
        await jobs.load_print_job_content(db_session, tenant.id, job.id, warehouse_id=warehouse.id)
    assert premature.value.code == "print_job_not_running"
    assert await jobs.claim_next_print_job(db_session, tenant.id, warehouse_id=uuid.uuid4()) is None
    claimed = await jobs.claim_next_print_job(db_session, tenant.id, warehouse_id=warehouse.id)
    assert claimed is not None and claimed.id == job.id
    await db_session.commit()
    assert await jobs.claim_next_print_job(db_session, tenant.id, warehouse_id=warehouse.id) is None
    payload, mime = await jobs.load_print_job_content(
        db_session, tenant.id, job.id, warehouse_id=warehouse.id,
    )
    assert payload == document and mime == "application/pdf"

    receipt = dict(warehouse_id=warehouse.id, queue_receipt="Warehouse-17",
                   handed_to_queue=True, error_message=None)
    done = await jobs.finish_print_job(db_session, tenant.id, job.id, **receipt)
    await db_session.commit()
    assert done.status == "done"
    assert jobs.print_job_status_text(done.status) == "Передано в очередь принтера"
    assert (await jobs.finish_print_job(db_session, tenant.id, job.id, **receipt)).id == job.id
    assert await jobs.claim_next_print_job(db_session, tenant.id, warehouse_id=warehouse.id) is None
    with pytest.raises(FbsPrintAssetError) as changed_intent:
        await jobs.create_document_print_job(
            db_session, tenant.id, **{**args, "document": document + b"\n%changed"},
        )
    assert changed_intent.value.code == "print_job_conflict"
    assert supply.status == "draft" and supply.delivered_at is None
