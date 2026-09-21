"""AVpack home scope remains enforced with historic manager grants and JWTs."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from test_wms488_catalog_isolation import _headers, _seed

from app.db.session import SessionLocal
from app.models.background_job import BackgroundJob
from app.models.seller import Seller
from app.models.seller_shop_delegation import SellerShopDelegation
from app.models.tenant import Tenant
from app.models.user import User


async def enable_avpack_manager(users, products):
    async with SessionLocal() as session:
        tenant = await session.get(Tenant, users["a"].tenant_id)
        tenant.slug = "avpack-9uczh"
        user = await session.get(User, users["a"].id)
        user.can_manage_seller_shops = True
        targets = [products["b"].seller_id]
        for index in range(4):
            seller = Seller(tenant_id=user.tenant_id, name=f"Delegated {index}")
            session.add(seller)
            await session.flush()
            targets.append(seller.id)
        session.add_all(
            [
                SellerShopDelegation(user_id=user.id, target_seller_id=target, enabled=True)
                for target in targets
            ]
        )
        await session.commit()
    return targets


async def grants_snapshot(user_id):
    async with SessionLocal() as session:
        user = await session.get(User, user_id)
        grants = (
            await session.execute(
                select(SellerShopDelegation.__table__)
                .where(SellerShopDelegation.user_id == user_id)
                .order_by(SellerShopDelegation.target_seller_id)
            )
        ).all()
        return user.can_manage_seller_shops, grants


async def test_old_foreign_tokens_auth_and_all_grants_stay_unchanged(async_client: AsyncClient):
    users, products, _ = await _seed()
    targets = await enable_avpack_manager(users, products)
    before = await grants_snapshot(users["a"].id)
    home = str(users["a"].seller_id)
    for target in targets:
        headers = _headers(users["a"], active_seller=target)
        me = await async_client.get("/auth/me", headers=headers)
        assert me.status_code == 200, me.text
        data = me.json()
        assert data["seller_id"] == data["active_seller_id"] == data["home_seller_id"] == home
        assert not data["can_manage_seller_shops"]
        assert [shop["id"] for shop in data["switchable_shops"]] == [home]
        assert data["delegatable_shops"] == []
        for path in ("/products", "/products/wb-catalog", "/products/categories"):
            response = await async_client.get(path, headers=headers)
            assert response.status_code == 200, response.text
            assert products["b"].name not in response.text
        switch = await async_client.post(
            "/auth/switch-seller", headers=headers, json={"seller_id": str(target)}
        )
        assert switch.status_code == 403 and "access_token" not in switch.text
    for ids in ([str(targets[0])], []):
        response = await async_client.put(
            "/auth/seller-shops", headers=headers, json={"enabled_seller_ids": ids}
        )
        assert response.status_code == 403, response.text
    for target in (home, None):
        response = await async_client.post(
            "/auth/switch-seller", headers=headers, json={"seller_id": target}
        )
        assert response.status_code == 200, response.text
    assert await grants_snapshot(users["a"].id) == before


@pytest.mark.parametrize("manager", [False, True])
async def test_jobs_require_proven_home_scope_but_not_seller_initiator(async_client, manager):
    users, products, _ = await _seed()
    await enable_avpack_manager(users, products)
    async with SessionLocal() as session:
        user = await session.get(User, users["a"].id)
        user.can_manage_seller_shops = manager
        await session.commit()
    allowed = [
        "wildberries_cards_sync",
        "storage_measurement_rebuild",
        "wildberries_supplies_sync",
        "wildberries_marketplace_orders_sync",
        "fbs_stock_sync",
    ]
    for kind in [
        *allowed,
        "movements_digest",
        "inbound_marking_check",
        "unknown",
        "fbs_label_print",
    ]:
        for scope in (str(users["a"].seller_id), str(users["b"].seller_id), None, "invalid"):
            async with SessionLocal() as session:
                job = BackgroundJob(
                    tenant_id=users["a"].tenant_id,
                    job_type=kind,
                    status="done",
                    payload_json={"seller_id": scope},
                    result_json={"processed": 1},
                    error_message=None,
                )
                session.add(job)
                await session.commit()
            response = await async_client.get(
                f"/operations/background-jobs/{job.id}",
                headers=_headers(users["a"], active_seller=users["b"].seller_id),
            )
            permitted = kind in allowed and scope == str(users["a"].seller_id)
            assert response.status_code == (
                200 if permitted else 403 if kind == "fbs_label_print" else 404
            ), response.text
            if not permitted:
                assert "payload_json" not in response.text and "result_json" not in response.text
            ff = await async_client.get(
                f"/operations/background-jobs/{job.id}", headers=_headers(users["admin"])
            )
            assert ff.status_code == 200, ff.text
            foreign = await async_client.get(
                f"/operations/background-jobs/{job.id}", headers=_headers(users["foreign"])
            )
            assert foreign.status_code == 404


@pytest.mark.parametrize("celery", [False, True])
async def test_old_token_enqueues_home_and_worker_uses_home(async_client, monkeypatch, celery):
    from app.core.settings import settings
    from app.services import background_job_service as jobs
    from app.tasks.background_jobs import run_wildberries_cards_sync_task

    users, products, _ = await _seed()
    await enable_avpack_manager(users, products)
    called = []
    queued = []

    async def sync(session, tenant_id, seller_id, http_client):
        called.append((tenant_id, seller_id))
        return {"processed": 1}

    monkeypatch.setattr(jobs.wb_sync, "sync_cards_list", sync)
    monkeypatch.setattr(settings, "celery_broker_url", "redis://unused" if celery else None)
    monkeypatch.setattr(
        run_wildberries_cards_sync_task, "delay", lambda job_id: queued.append(job_id)
    )
    response = await async_client.post(
        "/operations/background-jobs/wildberries-cards-sync-self",
        headers=_headers(users["a"], active_seller=users["b"].seller_id),
    )
    assert response.status_code == 202, response.text
    job_id = uuid.UUID(response.json()["id"])
    async with SessionLocal() as session:
        job = await session.get(BackgroundJob, job_id)
        assert job.payload_json == {"seller_id": str(users["a"].seller_id)}
    if celery:
        assert queued == [str(job_id)]
        await jobs.run_wildberries_cards_sync_job(job_id)
    assert called == [(users["a"].tenant_id, users["a"].seller_id)]


@pytest.mark.parametrize("slug", ["avpack", "avpack-9uczh-other", "other-tenant-name"])
async def test_similar_tenant_keeps_delegation(async_client, slug):
    users, products, _ = await _seed()
    await enable_avpack_manager(users, products)
    async with SessionLocal() as session:
        tenant = await session.get(Tenant, users["a"].tenant_id)
        tenant.slug = slug
        tenant.name = "AVpack"
        await session.commit()
    before = await grants_snapshot(users["a"].id)
    headers = _headers(users["a"], active_seller=users["b"].seller_id)
    me = await async_client.get("/auth/me", headers=headers)
    assert me.status_code == 200, me.text
    assert me.json()["active_seller_id"] == str(users["b"].seller_id)
    assert me.json()["can_manage_seller_shops"]
    switched = await async_client.post(
        "/auth/switch-seller", headers=headers, json={"seller_id": str(users["b"].seller_id)}
    )
    assert switched.status_code == 200, switched.text
    assert await grants_snapshot(users["a"].id) == before


@pytest.mark.parametrize("prefix", ["SKU", "WB", "OZN", "OZ"])
async def test_old_token_scan_filters_foreign_and_ambiguity(async_client, prefix):
    from app.models.product import Product

    users, products, _ = await _seed()
    await enable_avpack_manager(users, products)
    headers = _headers(users["a"], active_seller=users["b"].seller_id)
    for target in ("a", "b", "foreign"):
        response = await async_client.get(
            "/operations/scan/resolve", headers=headers, params={"code": f"{prefix}-{target}"}
        )
        assert response.status_code == (200 if target == "a" else 404), response.text
    async with SessionLocal() as session:
        own = await session.get(Product, products["a"].id)
        foreign = await session.get(Product, products["b"].id)
        own.sku_code = foreign.sku_code = "SHARED"
        await session.commit()
    response = await async_client.get(
        "/operations/scan/resolve", headers=headers, params={"code": "SHARED"}
    )
    assert response.status_code == 200 and response.json()["id"] == str(products["a"].id)
    async with SessionLocal() as session:
        second = Product(
            tenant_id=users["a"].tenant_id,
            seller_id=users["a"].seller_id,
            name="Own second",
            sku_code="SECOND",
            wb_barcode="SHARED",
        )
        session.add(second)
        await session.commit()
    response = await async_client.get(
        "/operations/scan/resolve", headers=headers, params={"code": "SHARED"}
    )
    assert response.status_code == 409, response.text
    assert {match["id"] for match in response.json()["detail"]["matches"]} == {
        str(products["a"].id),
        str(second.id),
    }


async def test_own_job_failure_hides_raw_diagnostics_and_mismatched_result(async_client):
    users, products, _ = await _seed()
    await enable_avpack_manager(users, products)
    async with SessionLocal() as session:
        job = BackgroundJob(
            tenant_id=users["a"].tenant_id,
            job_type="storage_measurement_rebuild",
            status="failed",
            payload_json={"seller_id": str(users["a"].seller_id)},
            error_message="SQL foreign-row diagnostics",
        )
        session.add(job)
        await session.commit()
    path = f"/operations/background-jobs/{job.id}"
    own = await async_client.get(path, headers=_headers(users["a"]))
    assert own.status_code == 200 and own.json()["status"] == "failed"
    assert "foreign-row" not in own.text
    assert own.json()["error_message"] == "Не удалось выполнить задачу"
    ff = await async_client.get(path, headers=_headers(users["admin"]))
    assert "foreign-row" in ff.text
    async with SessionLocal() as session:
        stored = await session.get(BackgroundJob, job.id)
        stored.result_json = {"seller_id": str(users["b"].seller_id)}
        await session.commit()
    assert (await async_client.get(path, headers=_headers(users["a"]))).status_code == 404


async def test_direct_marketplace_sync_uses_home(async_client, monkeypatch):
    from app.api import ozon_integration as ozon
    from app.api import wildberries_integration as wb
    from app.services.ozon_product_import_service import OzonProductImportResult

    users, products, _ = await _seed()
    await enable_avpack_manager(users, products)
    seen = []

    async def wb_credentials(session, tenant_id, seller_id):
        seen.append(("wb", seller_id))
        return "fixture", None

    async def cards(*args, **kwargs):
        return [], False

    async def ozon_credentials(self, tenant_id, seller_id):
        seen.append(("ozon", seller_id))
        return "fixture", "fixture"

    async def ozon_import(session, tenant_id, seller_id, *args, **kwargs):
        seen.append(("ozon-import", seller_id))
        return OzonProductImportResult()

    monkeypatch.setattr(wb, "get_decrypted_tokens_for_seller", wb_credentials)
    monkeypatch.setattr(wb, "fetch_all_cards", cards)
    monkeypatch.setattr(ozon.MarketplaceAccountService, "stored_credentials", ozon_credentials)
    monkeypatch.setattr(ozon, "import_ozon_product_cards", ozon_import)
    for marketplace in ("wildberries", "ozon"):
        response = await async_client.post(
            f"/integrations/{marketplace}/self/sync-products",
            headers=_headers(users["a"], active_seller=users["b"].seller_id),
        )
        assert response.status_code == 200, response.text
    assert seen == [(key, users["a"].seller_id) for key in ("wb", "ozon", "ozon-import")]


async def test_old_token_marking_reads_print_and_ff_catalog(async_client):
    from app.models.ff_staff_permissions import FfStaffPermissions

    users, products, _ = await _seed()
    await enable_avpack_manager(users, products)
    headers = _headers(users["a"], active_seller=users["b"].seller_id)
    for target in ("a", "b", "foreign"):
        for action in ("marking-overview", "codes", "print"):
            path = f"/operations/marking-codes/products/{products[target].id}/{action}"
            if action == "print":
                if target == "a":
                    continue  # Own printing needs an available code pool; covered separately.
                response = await async_client.post(path, headers=headers, json={"quantity": 1})
            else:
                response = await async_client.get(path, headers=headers)
            expected = 200 if target == "a" else 403 if target == "b" else 404
            assert response.status_code == expected, response.text
    async with SessionLocal() as session:
        session.add(FfStaffPermissions(user_id=users["staff"].id, can_reception=True))
        await session.commit()
    for actor in ("admin", "staff"):
        response = await async_client.get("/products", headers=_headers(users[actor]))
        assert response.status_code == 200, response.text
        assert products["a"].name in response.text and products["b"].name in response.text
        assert products["foreign"].name not in response.text


@pytest.mark.parametrize(
    "kind", ["inbound-intake", "outbound-shipment", "marketplace-unload-requests"]
)
async def test_old_token_cannot_add_foreign_document_line(async_client, kind):
    users, products, warehouse = await _seed()
    await enable_avpack_manager(users, products)
    headers = _headers(users["a"], active_seller=users["b"].seller_id)
    body = {"warehouse_id": str(warehouse.id)}
    if kind != "outbound-shipment":
        body["seller_id"] = str(users["b"].seller_id)
    path = f"/operations/{kind}" + ("" if kind.endswith("requests") else "-requests")
    created = await async_client.post(path, headers=headers, json=body)
    assert created.status_code == 201, created.text
    request_id = created.json()["id"]
    line = {
        "product_id": str(products["b"].id),
        "expected_qty" if kind == "inbound-intake" else "quantity": 1,
    }
    denied = await async_client.post(f"{path}/{request_id}/lines", headers=headers, json=line)
    assert denied.status_code == (404 if kind.endswith("requests") else 422), denied.text
    # Re-read as FF to verify no foreign product line was actually stored.
    document = await async_client.get(f"{path}/{request_id}", headers=_headers(users["admin"]))
    assert document.status_code == 200, document.text
    assert str(products["b"].id) not in document.text
