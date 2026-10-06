"""WMS-442: real HTTP/PG overlap, scope boundaries and label decoding, no printers."""

from __future__ import annotations

import asyncio
import hashlib
import uuid
from datetime import UTC, datetime, timedelta

import fitz
import pytest
import pytest_asyncio
import zxingcpp
from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models.background_job import BackgroundJob
from app.models.fbs_print_asset import FbsPrintAsset
from app.models.fbs_supply import FbsSupply
from app.models.ff_staff_permissions import FfStaffPermissions
from app.models.inbound_intake import InboundIntakeLine, InboundIntakeRequest
from app.models.inventory_movement import InventoryMovement
from app.models.print_connection import PrintConnection
from app.models.product import Product
from app.models.product_marketplace_link import ProductMarketplaceLink
from app.models.seller import Seller
from app.models.storage_location import StorageLocation
from app.models.tenant import Tenant
from app.models.user import User
from app.models.warehouse import Warehouse
from app.services import print_connection_service as pairing
from app.services.fbs_print_asset_storage import save_print_file, sha256_checksum
from app.services.fbs_print_job_service import create_document_print_job, create_print_job
from app.services.sorting_print_service import label_pdf
from app.services.tokens import create_access_token

BASE = "/operations/print"


def auth(user):
    return {
        "Authorization": "Bearer "
        + create_access_token(user_id=user.id, tenant_id=user.tenant_id, role=user.role)
    }


@pytest_asyncio.fixture
async def setup_print(async_client):
    pairing._pairing_clients.clear()
    async with SessionLocal() as session:
        tenant = Tenant(name="442 test", slug=uuid.uuid4().hex)
        other = Tenant(name="442 other", slug=uuid.uuid4().hex)
        session.add_all([tenant, other])
        await session.flush()
        admin = User(
            tenant_id=tenant.id,
            full_name="Администратор Тест",
            role="fulfillment_admin",
            password_hash="synthetic-unused",
            email="print442@example.com",
        )
        worker = User(
            tenant_id=tenant.id,
            full_name="Работник Сортировки",
            role="fulfillment_staff",
            password_hash="synthetic-unused",
            email="worker442@example.com",
        )
        outsider = User(
            tenant_id=other.id,
            full_name="Другой клиент",
            role="fulfillment_admin",
            password_hash="synthetic-unused",
            email="other442@example.com",
        )
        warehouse = Warehouse(tenant_id=tenant.id, name="442", code="442")
        warehouse2 = Warehouse(tenant_id=tenant.id, name="442 other", code="442b")
        seller = Seller(tenant_id=tenant.id, name="442 seller")
        session.add_all([admin, worker, outsider, warehouse, warehouse2, seller])
        await session.flush()
        session.add(FfStaffPermissions(user_id=worker.id, can_reception=True))
        product = Product(
            tenant_id=tenant.id,
            seller_id=seller.id,
            name="Очень длинное название товара для проверки подписи " * 3,
            sku_code="ART-442-XXL",
            wb_barcode="4601234567893",
        )
        location = StorageLocation(
            tenant_id=tenant.id, warehouse_id=warehouse.id, code="А 1.1", barcode="LOC-9DF85B314B88"
        )
        foreign_location = StorageLocation(
            tenant_id=tenant.id, warehouse_id=warehouse2.id, code="Б 2.2", barcode="LOC-OTHER442"
        )
        request = InboundIntakeRequest(
            tenant_id=tenant.id,
            warehouse_id=warehouse.id,
            seller_id=seller.id,
            marketplace="wb",
            status="sorting",
        )
        session.add_all([product, location, foreign_location, request])
        await session.flush()
        session.add(
            InboundIntakeLine(
                request_id=request.id,
                product_id=product.id,
                expected_qty=5,
                actual_qty=5,
                posted_qty=3,
            )
        )
        session.add(
            ProductMarketplaceLink(
                tenant_id=tenant.id,
                seller_id=seller.id,
                product_id=product.id,
                marketplace="ozon",
                external_barcodes=["OZN442234567"],
                external_product_id="442",
                is_active=True,
            )
        )
        await session.commit()
    return dict(
        client=async_client,
        tenant=tenant,
        admin=admin,
        worker=worker,
        outsider=outsider,
        warehouse=warehouse,
        warehouse2=warehouse2,
        seller=seller,
        product=product,
        location=location,
        foreign_location=foreign_location,
        request=request,
    )


async def connect(fixture, warehouse=None, name="Synthetic_442", platform="darwin"):
    client = fixture["client"]
    # Test-only opaque credential, never an employee JWT; values are not logged.
    device_token = hashlib.sha256(uuid.uuid4().bytes).hexdigest()
    body = {
        "connection_id": str(uuid.uuid4()),
        "device_token": device_token,
        "queue_name": name,
        "platform": platform,
    }
    begin = await client.post(BASE + "/pairing", json=body)
    assert begin.status_code == 200, begin.text
    replay = await client.post(BASE + "/pairing", json=body)
    assert replay.json()["pairing_code"] == begin.json()["pairing_code"]
    warehouse = warehouse or fixture["warehouse"]
    confirm_body = {"pairing_code": begin.json()["pairing_code"]}
    confirm_url = f"{BASE}/warehouses/{warehouse.id}/pair"
    preview = await client.post(
        confirm_url + "/preview", json=confirm_body, headers=auth(fixture["admin"])
    )
    assert preview.status_code == 200 and preview.json()["queue_name"] == name
    paired = await client.post(confirm_url, json=confirm_body, headers=auth(fixture["admin"]))
    assert paired.status_code == 200, paired.text
    replay = await client.post(confirm_url, json=confirm_body, headers=auth(fixture["admin"]))
    assert replay.status_code == 200 and replay.json()["connection_id"] == body["connection_id"]
    headers = {"Authorization": "Bearer " + device_token}
    return {"id": body["connection_id"], "headers": headers, "pair_body": confirm_body}


@pytest.mark.anyio
async def test_windows_pairing_accepts_real_unicode_queue_name(setup_print):
    connection = await connect(setup_print, name="Принтер склада 58 x 40", platform="win32")
    destination = await setup_print["client"].get(
        f"{BASE}/warehouses/{setup_print['warehouse'].id}/destination",
        headers=auth(setup_print["worker"]),
    )
    assert destination.status_code == 200
    assert destination.json()["destination"]["connection_id"] == connection["id"]
    assert destination.json()["destination"]["queue_name"] == "Принтер склада 58 x 40"
    assert destination.json()["destination"]["platform"] == "win32"


@pytest.mark.anyio
@pytest.mark.parametrize("queue_name", [" ", "Printer\n58"])
async def test_pairing_rejects_blank_or_control_queue_name(setup_print, queue_name):
    response = await setup_print["client"].post(
        BASE + "/pairing",
        json={
            "connection_id": str(uuid.uuid4()),
            "device_token": hashlib.sha256(uuid.uuid4().bytes).hexdigest(),
            "queue_name": queue_name,
            "platform": "win32",
        },
    )
    assert response.status_code == 422


def intent(f, connection, kind="product", marketplace="wb"):
    return {
        "job_id": str(uuid.uuid4()),
        "kind": kind,
        "object_id": str(f["product" if kind == "product" else "location"].id),
        "marketplace": marketplace if kind == "product" else None,
        "copies": 2,
        "connection_id": connection["id"],
    }


async def create(f, body):
    return await f["client"].post(
        f"{BASE}/sorting/{f['request'].id}/jobs", json=body, headers=auth(f["worker"])
    )


async def claim(f, connection):
    response = await f["client"].post(BASE + "/agent/next", headers=connection["headers"])
    assert response.status_code == 200, response.text
    return response.json()["job"]


async def content(f, connection, job):
    return await f["client"].get(
        f"{BASE}/agent/jobs/{job['id']}/content",
        params={"claim_id": job["claim_id"]},
        headers=connection["headers"],
    )


@pytest.mark.asyncio
async def test_sorting_labels_marketplace_location_immutable_replay_and_no_stock_effects(
    setup_print,
):
    f = setup_print
    connection = await connect(f)
    for kind, marketplace, barcode in [
        ("product", "wb", "4601234567893"),
        ("product", "ozon", "OZN442234567"),
        ("location", None, "LOC-9DF85B314B88"),
    ]:
        body = intent(f, connection, kind, marketplace)
        response = await create(f, body)
        assert response.status_code == 202, response.text
        job = response.json()
        assert job["barcode"] == barcode and job["copies"] == 2
        assert job["queue_name"] == "Synthetic_442" and job["status"] == "pending"
        # Simulate lost POST response: read after new HTTP request and exact replay.
        restored = await f["client"].get(
            BASE + "/jobs/" + body["job_id"], headers=auth(f["worker"])
        )
        assert restored.json() == job
        assert (await create(f, body)).json() == job
        assert (await create(f, {**body, "copies": 3})).status_code == 409
        claimed = await claim(f, connection)
        asset = await content(f, connection, claimed)
        assert asset.status_code == 200
        assert sha256_checksum(asset.content) == job["checksum"]
        with fitz.open(stream=asset.content, filetype="pdf") as pdf:
            page = pdf[0]
            assert abs(page.rect.width * 25.4 / 72 - 58) < 0.01
            assert abs(page.rect.height * 25.4 / 72 - 40) < 0.01
            decoded = zxingcpp.read_barcodes(page.get_pixmap(dpi=300).pil_image())
            assert [x.text for x in decoded] == [barcode]
            text = page.get_text()
            assert barcode in text
            assert ("Ячейка" if kind == "location" else marketplace.upper()) in text
        # Source edits never regenerate an existing intent/file.
        async with SessionLocal() as session:
            if kind == "product":
                product = await session.get(Product, f["product"].id)
                product.name = "Название изменено после отправки"
            else:
                location = await session.get(StorageLocation, f["location"].id)
                location.barcode = "LOC-NEW"
            await session.commit()
        assert (await content(f, connection, claimed)).content == asset.content
        assert (await create(f, body)).json()["checksum"] == job["checksum"]
    async with SessionLocal() as session:
        assert await session.scalar(select(func.count()).select_from(BackgroundJob)) == 3
        assert await session.scalar(select(func.count()).select_from(InventoryMovement)) == 0
        request = await session.get(InboundIntakeRequest, f["request"].id)
        line = await session.scalar(select(InboundIntakeLine))
        assert request.status == "sorting" and request.distribution_completed_at is None
        assert (line.actual_qty, line.posted_qty) == (5, 3)
        assert await session.scalar(select(func.count()).select_from(FbsSupply)) == 0


@pytest.mark.asyncio
@pytest.mark.postgresql_concurrency
async def test_real_http_concurrent_intent_claim_and_conflicting_ack(setup_print):
    from app.db.session import engine

    if engine.dialect.name != "postgresql":
        pytest.skip("Real overlapping transactions are verified against PostgreSQL")
    f = setup_print
    connection = await connect(f)
    body = intent(f, connection)
    created = await asyncio.gather(create(f, body), create(f, body))
    assert [x.status_code for x in created] == [202, 202]
    assert created[0].json() == created[1].json()
    claims = await asyncio.gather(claim(f, connection), claim(f, connection))
    assert sum(x is not None for x in claims) == 1
    job = next(x for x in claims if x)
    result_url = f"{BASE}/agent/jobs/{job['id']}/result"
    success = {
        "claim_id": job["claim_id"],
        "handed_to_queue": True,
        "queue_receipt": "Synthetic_442-117",
        "error_message": None,
    }
    fail = {
        "claim_id": job["claim_id"],
        "handed_to_queue": False,
        "queue_receipt": None,
        "error_message": "Synthetic refusal before native call",
    }
    results = await asyncio.gather(
        *[
            f["client"].post(result_url, json=x, headers=connection["headers"])
            for x in (success, fail)
        ]
    )
    assert sorted(x.status_code for x in results) == [200, 409]
    winner = results[0] if results[0].status_code == 200 else results[1]
    winner_body = success if results[0].status_code == 200 else fail
    repeat = await f["client"].post(result_url, json=winner_body, headers=connection["headers"])
    assert repeat.json() == winner.json()
    assert await claim(f, connection) is None
    assert "напечатано" not in winner.json()["status_text"].lower()
    async with SessionLocal() as session:
        assert await session.scalar(select(func.count()).select_from(BackgroundJob)) == 1


@pytest.mark.asyncio
async def test_opaque_credentials_cannot_access_employee_api_and_scope_cannot_be_forged(
    setup_print,
):
    f = setup_print
    own = await connect(f)
    other = await connect(f, f["warehouse2"], "Other_442")
    for path in ("/auth/me", "/warehouses", "/products", BASE + "/jobs/" + str(uuid.uuid4())):
        response = await f["client"].get(path, headers=own["headers"])
        assert response.status_code == 401, (path, response.text)
    response = await f["client"].post(BASE + "/agent/next", headers=auth(f["admin"]))
    assert response.status_code == 401
    body = intent(f, own)
    assert (await create(f, body)).status_code == 202
    assert await claim(f, other) is None
    job = await claim(f, own)
    assert (await content(f, other, job)).status_code == 404
    bad_claim = {**job, "claim_id": str(uuid.uuid4())}
    assert (await content(f, own, bad_claim)).status_code == 404
    result_url = f"{BASE}/agent/jobs/{job['id']}/result"
    result = {"claim_id": job["claim_id"], "handed_to_queue": True, "queue_receipt": "Synthetic-4"}
    assert (
        await f["client"].post(result_url, json=result, headers=other["headers"])
    ).status_code == 404
    assert (
        await f["client"].get(BASE + "/jobs/" + job["id"], headers=auth(f["outsider"]))
    ).status_code == 404
    assert (
        await f["client"].get(BASE + "/jobs/" + job["id"], headers=auth(f["admin"]))
    ).status_code == 404
    assert (
        await f["client"].get(
            f"/operations/fbs-print-jobs/{job['id']}/content",
            params={"warehouse_id": str(f["warehouse"].id)},
            headers=auth(f["admin"]),
        )
    ).status_code == 404
    generic = await f["client"].get(
        "/operations/background-jobs/" + job["id"], headers=auth(f["worker"])
    )
    assert generic.status_code == 200
    assert "storage_path" not in generic.json()["payload_json"]
    assert "claim_id" not in generic.json()["result_json"]
    assert (
        await create(f, {**intent(f, own, "location"), "object_id": str(f["foreign_location"].id)})
    ).status_code == 404
    # No FBS permission was granted to the sorting employee.
    assert (
        await f["client"].get("/operations/fbs-print-jobs/" + job["id"], headers=auth(f["worker"]))
    ).status_code == 403


@pytest.mark.asyncio
async def test_missing_codes_and_changed_destination_do_not_create_empty_jobs(setup_print):
    f = setup_print
    old = await connect(f)
    old_body = intent(f, old)
    assert (await create(f, old_body)).status_code == 202
    new = await connect(f, name="New_442")
    assert await claim(f, new) is None
    assert (await create(f, old_body)).json()["queue_name"] == "Synthetic_442"
    assert (await create(f, intent(f, old))).status_code == 409
    old_claim = await claim(f, old)
    assert old_claim["queue_name"] == "Synthetic_442"
    async with SessionLocal() as session:
        product = await session.get(Product, f["product"].id)
        product.wb_barcode = None
        link = await session.scalar(select(ProductMarketplaceLink))
        link.external_barcodes = []
        location = await session.get(StorageLocation, f["location"].id)
        location.barcode = ""
        await session.commit()
    for kind, marketplace in (("product", "wb"), ("product", "ozon"), ("location", None)):
        response = await create(f, intent(f, new, kind, marketplace))
        assert response.status_code == 422, response.text
        assert response.json()["detail"]["code"] == "barcode_missing"
    async with SessionLocal() as session:
        assert await session.scalar(select(func.count()).select_from(BackgroundJob)) == 1


@pytest.mark.asyncio
async def test_lost_claim_response_is_unknown_never_returned_to_pending(setup_print):
    f = setup_print
    own = await connect(f)
    response = await create(f, intent(f, own))
    await claim(f, own)  # Agent did not persist/receive this HTTP response.
    for _ in range(3):
        assert await claim(f, own) is None
    recovered = await f["client"].get(
        BASE + "/jobs/" + response.json()["id"], headers=auth(f["worker"])
    )
    assert recovered.json()["status"] == "running"
    assert "неизвестен" in recovered.json()["status_text"]
    assert recovered.json()["queue_receipt"] is None
    assert (await create(f, intent(f, own))).json()["id"] != response.json()["id"]


@pytest.mark.asyncio
async def test_fbs_ready_png_and_operator_pdf_use_same_agent_snapshot_without_state_changes(
    setup_print,
):
    f = setup_print
    own = await connect(f)
    pdf = label_pdf("4601234567893", "Товар", "WB + ЧЗ")
    with fitz.open(stream=pdf, filetype="pdf") as doc:
        png = doc[0].get_pixmap().tobytes("png")
    async with SessionLocal() as session:
        supply = FbsSupply(
            tenant_id=f["tenant"].id,
            seller_id=f["seller"].id,
            warehouse_id=f["warehouse"].id,
            marketplace="ozon",
            name="FBS fixture",
            delivery_type="warehouse_sc",
        )
        session.add(supply)
        await session.flush()
        asset_id = uuid.uuid4()
        path = save_print_file(f"fbs-print-assets/order-stickers/{asset_id}.png", png)
        asset = FbsPrintAsset(
            id=asset_id,
            tenant_id=f["tenant"].id,
            seller_id=f["seller"].id,
            fbs_supply_id=supply.id,
            kind="supply_qr",
            status="ready",
            storage_path=path,
            checksum=sha256_checksum(png),
            content_type="image/png",
        )
        session.add(asset)
        await session.flush()
        job = await create_print_job(
            session,
            f["tenant"].id,
            job_id=uuid.uuid4(),
            asset_id=asset_id,
            warehouse_id=f["warehouse"].id,
            user_id=f["admin"].id,
        )
        old_checksum = job.payload_json["checksum"]
        await create_document_print_job(
            session,
            f["tenant"].id,
            job_id=uuid.uuid4(),
            supply_id=supply.id,
            document=pdf,
            user_id=f["admin"].id,
        )
        await session.commit()
        # The source FBS asset can be replaced; the already queued snapshot cannot.
        save_print_file(path, png + b"changed")
        asset.checksum = sha256_checksum(png + b"changed")
        await session.commit()
        supply_id = supply.id
    first, second = await claim(f, own), await claim(f, own)
    files = [(await content(f, own, job)).content for job in (first, second)]
    assert files == [png, pdf]
    assert first["checksum"] == old_checksum
    assert first["content_type"] == "image/png" and second["content_type"] == "application/pdf"
    async with SessionLocal() as session:
        supply = await session.get(FbsSupply, supply_id)
        assert supply.status == "draft" and supply.delivered_at is None
        assert await session.scalar(select(func.count()).select_from(InventoryMovement)) == 0


@pytest.mark.asyncio
async def test_unpaired_expired_and_foreign_pairing_are_rejected(setup_print):
    f = setup_print
    credential = hashlib.sha256(uuid.uuid4().bytes).hexdigest()
    body = {
        "connection_id": str(uuid.uuid4()),
        "device_token": credential,
        "queue_name": "Synthetic_442",
        "platform": "darwin",
    }
    begin = await f["client"].post(BASE + "/pairing", json=body)
    assert begin.status_code == 200
    headers = {"Authorization": "Bearer " + credential}
    assert (await f["client"].post(BASE + "/agent/next", headers=headers)).status_code == 403
    assert (
        await f["client"].post(BASE + "/pairing", json={**body, "queue_name": "Changed"})
    ).status_code == 409
    forbidden = await f["client"].post(
        f"{BASE}/warehouses/{f['warehouse'].id}/pair",
        json={"pairing_code": begin.json()["pairing_code"]},
        headers=auth(f["outsider"]),
    )
    assert forbidden.status_code == 404
    async with SessionLocal() as session:
        connection = await session.get(PrintConnection, uuid.UUID(body["connection_id"]))
        connection.pairing_expires_at = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()
    assert (await f["client"].post(BASE + "/agent/heartbeat", headers=headers)).status_code == 401
    assert (await f["client"].post(BASE + "/pairing", json=body)).status_code == 410


def test_print_migration_after_identity_upgrade_downgrade_in_isolated_pg_schema():
    """Run real DDL in a private schema of the task's own database, never shared staging."""
    import importlib.util
    import os
    from pathlib import Path

    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import create_engine, inspect, text

    url = os.environ.get("WMS_TEST_DATABASE_URL", "")
    if not url.startswith("postgresql"):
        pytest.skip("PostgreSQL DDL proof requires the isolated task database")
    engine = create_engine(url.replace("+psycopg_async", "+psycopg"))
    schema = "wms442_migration_" + uuid.uuid4().hex[:10]
    module_path = Path(__file__).parents[1] / "alembic/versions/20260913_0305_print_connections.py"
    spec = importlib.util.spec_from_file_location("print_migration_442", module_path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    assert migration.down_revision == "20260913_0443"
    try:
        with engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
            # Minimal referenced tables model the accepted 0443 boundary.
            for name in ("tenants", "warehouses", "users"):
                connection.execute(text(f'CREATE TABLE "{name}" (id uuid PRIMARY KEY)'))
            context = MigrationContext.configure(connection)
            with Operations.context(context):
                migration.upgrade()
            assert "print_connections" in inspect(connection).get_table_names(schema=schema)
            indexes = inspect(connection).get_indexes("print_connections", schema=schema)
            assert any(
                x["name"] == "uq_print_connection_destination" and x["unique"] for x in indexes
            )
            with Operations.context(context):
                migration.downgrade()
            assert "print_connections" not in inspect(connection).get_table_names(schema=schema)
            with Operations.context(context):
                migration.upgrade()
    finally:
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        engine.dispose()
