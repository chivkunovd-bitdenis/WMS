"""AVpack follows the common delegation model, including live revocation."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import delete, select
from test_wms488_catalog_isolation import _headers, _seed
from test_wms488_home_scope import enable_avpack_manager, grants_snapshot

from app.db.session import SessionLocal
from app.models.background_job import BackgroundJob
from app.models.ff_staff_permissions import FfStaffPermissions
from app.models.marketplace_unload import MarketplaceUnloadRequest
from app.models.seller import Seller
from app.models.seller_shop_delegation import SellerShopDelegation
from app.models.user import User


@pytest.mark.parametrize("existing_grants", [False, True])
async def test_ordinary_avpack_seller_cannot_use_existing_grant_or_signed_active_token(
    async_client,
    existing_grants,
):
    users, products, _ = await _seed()
    await enable_avpack_manager(users, products)
    async with SessionLocal() as session:
        user = await session.get(User, users["a"].id)
        user.can_manage_seller_shops = False
        if not existing_grants:
            await session.execute(
                delete(SellerShopDelegation).where(
                    SellerShopDelegation.user_id == user.id,
                )
            )
        await session.commit()
    before = await grants_snapshot(users["a"].id)
    headers = _headers(users["a"], active_seller=users["b"].seller_id)
    me = await async_client.get("/auth/me", headers=headers)
    assert me.status_code == 200, me.text
    assert me.json()["active_seller_id"] == str(users["a"].seller_id)
    assert not me.json()["can_manage_seller_shops"]
    assert me.json()["delegatable_shops"] == []
    assert [shop["id"] for shop in me.json()["switchable_shops"]] == [str(users["a"].seller_id)]
    switch = await async_client.post(
        "/auth/switch-seller", headers=headers, json={"seller_id": str(users["b"].seller_id)}
    )
    assert switch.status_code == 403 and "access_token" not in switch.text
    products_response = await async_client.get("/products", headers=headers)
    assert products_response.status_code == 200, products_response.text
    assert {row["id"] for row in products_response.json()} == {str(products["a"].id)}
    foreign = await async_client.get(f"/products/{products['b'].id}", headers=headers)
    assert foreign.status_code == 404, foreign.text
    assert await grants_snapshot(users["a"].id) == before


@pytest.mark.parametrize("denial", ["disabled", "ungranted", "foreign", "test"])
async def test_avpack_denied_targets_cannot_switch_or_use_signed_token(async_client, denial):
    users, products, _ = await _seed()
    await enable_avpack_manager(users, products)
    async with SessionLocal() as session:
        if denial == "disabled":
            grant = await session.scalar(
                select(SellerShopDelegation).where(
                    SellerShopDelegation.user_id == users["a"].id,
                    SellerShopDelegation.target_seller_id == users["b"].seller_id,
                )
            )
            grant.enabled = False
            target = users["b"].seller_id
        elif denial == "foreign":
            target = users["foreign"].seller_id
            session.add(
                SellerShopDelegation(
                    user_id=users["a"].id,
                    target_seller_id=target,
                    enabled=True,
                )
            )
        else:
            seller = Seller(
                tenant_id=users["a"].tenant_id,
                name=("Test seller" if denial == "test" else "No delegation"),
            )
            session.add(seller)
            await session.flush()
            target = seller.id
            if denial == "test":
                session.add(
                    SellerShopDelegation(
                        user_id=users["a"].id,
                        target_seller_id=target,
                        enabled=True,
                    )
                )
        await session.commit()
    before = await grants_snapshot(users["a"].id)
    switch = await async_client.post(
        "/auth/switch-seller", headers=_headers(users["a"]), json={"seller_id": str(target)}
    )
    assert switch.status_code == 403 and "access_token" not in switch.text
    for path in ("/auth/me", "/products"):
        forged = await async_client.get(path, headers=_headers(users["a"], active_seller=target))
        assert forged.status_code == 403, forged.text
    assert await grants_snapshot(users["a"].id) == before


async def test_avpack_toggle_existing_delegation_revokes_old_token_and_restores_switch(
    async_client,
):
    users, products, _ = await _seed()
    targets = await enable_avpack_manager(users, products)
    before = await grants_snapshot(users["a"].id)
    home_headers = _headers(users["a"])
    switched = await async_client.post(
        "/auth/switch-seller",
        headers=home_headers,
        json={"seller_id": str(users["b"].seller_id)},
    )
    assert switched.status_code == 200, switched.text
    active_headers = {"Authorization": f"Bearer {switched.json()['access_token']}"}
    disabled = await async_client.put(
        "/auth/seller-shops",
        headers=home_headers,
        json={"enabled_seller_ids": []},
    )
    assert disabled.status_code == 200, disabled.text
    me = await async_client.get("/auth/me", headers=home_headers)
    assert [shop["id"] for shop in me.json()["switchable_shops"]] == [str(users["a"].seller_id)]
    for path in ("/auth/me", "/products"):
        stale = await async_client.get(path, headers=active_headers)
        assert stale.status_code == 403, stale.text
    for ids, expected in (
        ([str(users["foreign"].seller_id)], 422),
        ([str(target) for target in targets], 200),
    ):
        update = await async_client.put(
            "/auth/seller-shops",
            headers=home_headers,
            json={"enabled_seller_ids": ids},
        )
        assert update.status_code == expected, update.text
    assert await grants_snapshot(users["a"].id) == before
    restored = await async_client.post(
        "/auth/switch-seller",
        headers=home_headers,
        json={"seller_id": str(users["b"].seller_id)},
    )
    assert restored.status_code == 200, restored.text
    active = await async_client.get(
        "/auth/me", headers={"Authorization": f"Bearer {restored.json()['access_token']}"}
    )
    assert active.json()["active_seller_id"] == str(users["b"].seller_id)


async def test_marketplace_unload_create_rejects_nonactive_seller_without_writes(async_client):
    users, products, warehouse = await _seed()
    await enable_avpack_manager(users, products)
    async with SessionLocal() as session:
        third = Seller(tenant_id=users["a"].tenant_id, name="Unrelated shop")
        session.add(third)
        session.add(FfStaffPermissions(user_id=users["staff"].id, can_mp_shipments=True))
        await session.commit()
    active_headers = _headers(users["a"], active_seller=users["b"].seller_id)
    path = "/operations/marketplace-unload-requests"
    for target in (users["a"].seller_id, third.id, users["foreign"].seller_id):
        response = await async_client.post(
            path,
            headers=active_headers,
            json={
                "warehouse_id": str(warehouse.id),
                "seller_id": str(target),
            },
        )
        assert response.status_code == 403, response.text
        async with SessionLocal() as session:
            assert (await session.scalars(select(MarketplaceUnloadRequest))).all() == []
    active = await async_client.post(
        path,
        headers=active_headers,
        json={
            "warehouse_id": str(warehouse.id),
            "seller_id": str(users["b"].seller_id),
        },
    )
    assert active.status_code == 201, active.text
    assert active.json()["seller_id"] == str(users["b"].seller_id)
    for actor in ("admin", "staff"):
        response = await async_client.post(
            path,
            headers=_headers(users[actor]),
            json={
                "warehouse_id": str(warehouse.id),
                "seller_id": str(third.id),
            },
        )
        assert response.status_code == 201, response.text
        assert response.json()["seller_id"] == str(third.id)


@pytest.mark.parametrize("celery", [False, True])
async def test_storage_rebuild_uses_active_scope_for_worker_and_poll(
    async_client, monkeypatch, celery
):
    from app.core.settings import settings
    from app.services import background_job_service as jobs
    from app.services import storage_measurement_service as storage
    from app.tasks.background_jobs import run_storage_measurement_rebuild_task

    users, products, _ = await _seed()
    await enable_avpack_manager(users, products)
    called = []
    queued = []

    async def rebuild(session, tenant_id, **kwargs):
        called.append((tenant_id, kwargs["seller_id"]))
        return {"processed": 0}

    monkeypatch.setattr(storage, "rebuild_storage_measurements", rebuild)
    monkeypatch.setattr(settings, "celery_broker_url", "redis://unused" if celery else None)
    monkeypatch.setattr(run_storage_measurement_rebuild_task, "delay", queued.append)
    active_headers = _headers(users["a"], active_seller=users["b"].seller_id)
    response = await async_client.post(
        "/operations/storage/measurements/rebuild",
        headers=active_headers,
        json={},
    )
    assert response.status_code == 202, response.text
    job_id = uuid.UUID(response.json()["id"])
    async with SessionLocal() as session:
        job = await session.get(BackgroundJob, job_id)
        assert job.payload_json == {"seller_id": str(users["b"].seller_id)}
    if celery:
        assert queued == [str(job_id)]
        await jobs.run_storage_measurement_rebuild_job(job_id)
    assert called == [(users["a"].tenant_id, users["b"].seller_id)]
    path = f"/operations/background-jobs/{job_id}"
    active = await async_client.get(path, headers=active_headers)
    assert active.status_code == 200 and active.json()["status"] == "done", active.text
    inactive = await async_client.get(path, headers=_headers(users["a"]))
    assert inactive.status_code == 404, inactive.text


@pytest.mark.parametrize("actor", ["admin", "staff"])
async def test_storage_rebuild_ff_remains_unscoped(async_client, monkeypatch, actor):
    from app.core.settings import settings
    from app.tasks.background_jobs import run_storage_measurement_rebuild_task

    users, products, _ = await _seed()
    await enable_avpack_manager(users, products)
    async with SessionLocal() as session:
        session.add(FfStaffPermissions(user_id=users["staff"].id, can_inventory=True))
        await session.commit()
    monkeypatch.setattr(settings, "celery_broker_url", "redis://unused")
    monkeypatch.setattr(run_storage_measurement_rebuild_task, "delay", lambda job_id: None)
    headers = _headers(users[actor])
    response = await async_client.post(
        "/operations/storage/measurements/rebuild",
        headers=headers,
        json={},
    )
    assert response.status_code == 202, response.text
    job_id = uuid.UUID(response.json()["id"])
    async with SessionLocal() as session:
        job = await session.get(BackgroundJob, job_id)
        assert job.payload_json == {}
    poll = await async_client.get(f"/operations/background-jobs/{job_id}", headers=headers)
    assert poll.status_code == 200, poll.text
