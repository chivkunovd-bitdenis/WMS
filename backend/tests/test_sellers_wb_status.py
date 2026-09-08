"""WMS-278: saved WB scope results, with tenant/seller isolation and no secrets."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient

from app.db.session import SessionLocal
from app.models.seller_wildberries_credentials import SellerWildberriesCredentials
from app.services import wildberries_credentials_service as credentials


@pytest.mark.asyncio
async def test_seller_list_reports_saved_wb_states_without_decryption(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    suffix = uuid.uuid4().hex
    registration = await async_client.post('/auth/register', json={
        'organization_name': 'WMS278', 'slug': f'wms278-{suffix}',
        'admin_email': f'admin-{suffix}@example.com', 'password': 'password123',
    })
    assert registration.status_code == 200
    headers = {'Authorization': f'Bearer {registration.json()["access_token"]}'}
    me = (await async_client.get('/auth/me', headers=headers)).json()
    ids = {}
    for name in ['checked', 'rejected', 'unknown', 'absent']:
        response = await async_client.post('/sellers', headers=headers, json={'name': name})
        assert response.status_code == 201
        ids[name] = response.json()['id']
    checked_at = datetime(2026, 9, 7, 12, 30, tzinfo=UTC)
    async with SessionLocal() as session:
        for name, result in [('checked', True), ('rejected', False), ('unknown', None)]:
            session.add(SellerWildberriesCredentials(
                seller_id=uuid.UUID(ids[name]),
                content_token_encrypted='synthetic-not-decryptable',
                marketplace_scope_ok=result,
                marketplace_scope_checked_at=checked_at if result is not None else None,
                updated_at=datetime(2026, 9, 8, 12, 30, tzinfo=UTC),
            ))
        await session.commit()

    def forbidden_decrypt(*args, **kwargs):
        raise AssertionError('Seller list must not decrypt tokens')

    monkeypatch.setattr(credentials, 'decrypt_secret', forbidden_decrypt)
    listed = await async_client.get('/sellers', headers=headers)
    assert listed.status_code == 200
    assert 'synthetic-not-decryptable' not in listed.text
    assert '_encrypted' not in listed.text
    rows = {row['name']: row for row in listed.json()}
    assert set(rows) == set(ids)
    assert rows['checked']['wb_has_key'] is True
    assert rows['checked']['wb_marketplace_scope_ok'] is True
    assert rows['checked']['wb_marketplace_scope_checked_at'].startswith('2026-09-07T12:30:00')
    assert rows['rejected']['wb_marketplace_scope_ok'] is False
    assert rows['rejected']['wb_marketplace_scope_checked_at'].startswith('2026-09-07T12:30:00')
    assert rows['unknown']['wb_has_key'] is True
    assert rows['unknown']['wb_marketplace_scope_ok'] is None
    assert rows['unknown']['wb_marketplace_scope_checked_at'] is None
    assert rows['absent']['wb_has_key'] is False
    assert rows['absent']['wb_marketplace_scope_checked_at'] is None

    account = await async_client.post('/auth/seller-accounts', headers=headers, json={
        'seller_id': ids['checked'], 'email': f'seller-{suffix}@example.com',
        'password': 'password123',
    })
    assert account.status_code in (200, 201)
    login = await async_client.post('/auth/login', json={
        'email': f'seller-{suffix}@example.com', 'password': 'password123',
    })
    seller_headers = {'Authorization': f'Bearer {login.json()["access_token"]}'}
    scoped = await async_client.get('/sellers', headers=seller_headers)
    assert scoped.status_code == 200
    assert [row['id'] for row in scoped.json()] == [ids['checked']]

    other_registration = await async_client.post('/auth/register', json={
        'organization_name': 'Other', 'slug': f'other278-{suffix}',
        'admin_email': f'other-{suffix}@example.com', 'password': 'password123',
    })
    other_headers = {'Authorization': f'Bearer {other_registration.json()["access_token"]}'}
    foreign = await async_client.post('/sellers', headers=other_headers, json={'name': 'foreign'})
    foreign_id = foreign.json()['id']
    async with SessionLocal() as session:
        batch = await credentials.list_public_marketplace_statuses(
            session, uuid.UUID(me['tenant_id']), {uuid.UUID(ids['checked']), uuid.UUID(foreign_id)},
        )
    assert set(batch) == {uuid.UUID(ids['checked'])}
    foreign_list = await async_client.get('/sellers', headers=other_headers)
    assert [row['id'] for row in foreign_list.json()] == [foreign_id]
