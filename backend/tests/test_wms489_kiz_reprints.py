from __future__ import annotations

import asyncio
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models.ff_staff_permissions import FfStaffPermissions
from app.models.kiz_reprint import KizReprint
from app.models.marking_code import STATUS_AVAILABLE, MarkingCode, MarkingPool
from app.models.user import User
from app.services.tokens import create_access_token, decode_access_token

PREFIX = "/operations/kiz-reprints"
GS = "\x1d"


def _kiz(serial: str = "RETURN-1") -> str:
    return f"010460000000000121{serial}{GS}91ABCD{GS}92{'X' * 44}"


async def _seed(async_client: AsyncClient) -> tuple[dict[str, str], uuid.UUID, uuid.UUID]:
    suffix = uuid.uuid4().hex[:10]
    registered = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "WMS-489 FF",
            "slug": f"wms489-{suffix}",
            "admin_email": f"wms489-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert registered.status_code in (200, 201), registered.text
    token = registered.json()["access_token"]
    tenant_id = uuid.UUID(str(decode_access_token(token)["tenant_id"]))
    headers = {"Authorization": f"Bearer {token}"}
    seller = await async_client.post(
        "/sellers",
        headers=headers,
        json={"name": "WMS-489 seller", "email": f"seller-{suffix}@example.com"},
    )
    assert seller.status_code == 201, seller.text
    return headers, tenant_id, uuid.UUID(seller.json()["id"])


@pytest.mark.asyncio
async def test_kiz_reprint_persists_exact_gs_without_touching_marking_pool(
    async_client: AsyncClient,
) -> None:
    headers, tenant_id, seller_id = await _seed(async_client)
    kiz = _kiz()
    async with SessionLocal() as session:
        pool = MarkingPool(
            tenant_id=tenant_id,
            seller_id=seller_id,
            gtin="04600000000001",
            title="Existing pool must stay unchanged",
        )
        session.add(pool)
        await session.flush()
        code = MarkingCode(
            tenant_id=tenant_id,
            seller_id=seller_id,
            pool_id=pool.id,
            cis_code=kiz,
            gtin="04600000000001",
            status=STATUS_AVAILABLE,
        )
        session.add(code)
        await session.commit()
        code_id = code.id
        pool_id = pool.id

    created = await async_client.post(
        PREFIX,
        headers=headers,
        json={"seller_id": str(seller_id), "kiz": kiz, "idempotency_key": "scan-1"},
    )
    assert created.status_code == 201, created.text
    assert created.json()["kiz"] == kiz
    assert created.json()["replayed"] is False

    listed = await async_client.get(PREFIX, headers=headers, params={"seller_id": str(seller_id)})
    assert listed.status_code == 200, listed.text
    assert [row["kiz"] for row in listed.json()["rows"]] == [kiz]

    async with SessionLocal() as session:
        code_after = await session.get(MarkingCode, code_id)
        pool_after = await session.get(MarkingPool, pool_id)
        assert code_after is not None and pool_after is not None
        assert code_after.cis_code == kiz
        assert code_after.pool_id == pool_id
        assert code_after.status == STATUS_AVAILABLE
        assert await session.scalar(select(func.count(KizReprint.id))) == 1


@pytest.mark.asyncio
async def test_kiz_reprint_rejects_incomplete_or_invalid_codes_without_history(
    async_client: AsyncClient,
) -> None:
    headers, _tenant_id, seller_id = await _seed(async_client)
    for value in (
        "",
        "not-a-kiz",
        "010460000000000121",
        # A two-byte serial is a truncated short packet, not a full KIZ.
        "010460000000000121AB",
        # Long form needs the key and cryptographic tail, not just the AIs.
        f"010460000000000121SERIAL{GS}91{GS}92",
    ):
        response = await async_client.post(
            PREFIX,
            headers=headers,
            json={
                "seller_id": str(seller_id),
                "kiz": value,
                "idempotency_key": f"bad-{uuid.uuid4()}",
            },
        )
        assert response.status_code == 422, response.text
        assert response.json()["detail"] == "not_a_kiz"

    async with SessionLocal() as session:
        assert await session.scalar(select(func.count(KizReprint.id))) == 0


@pytest.mark.asyncio
async def test_kiz_reprint_retry_after_lost_save_response_claims_one_print(
    async_client: AsyncClient,
) -> None:
    """C8: durable save without its response is still printed exactly once on retry."""
    headers, _tenant_id, seller_id = await _seed(async_client)
    body = {"seller_id": str(seller_id), "kiz": _kiz(), "idempotency_key": "lost-response"}
    committed_but_unread = await async_client.post(PREFIX, headers=headers, json=body)
    assert committed_but_unread.status_code == 201
    reprint_id = committed_but_unread.json()["id"]

    retry = await async_client.post(PREFIX, headers=headers, json=body)
    assert retry.status_code == 201
    assert retry.json()["replayed"] is True
    assert retry.json()["print_started_at"] is None

    claim = await async_client.post(
        f"{PREFIX}/{reprint_id}/print-claim",
        headers=headers,
        json={"attempt_key": "retry-print"},
    )
    assert claim.status_code == 200, claim.text
    assert claim.json()["claimed"] is True
    started = await async_client.post(f"{PREFIX}/{reprint_id}/print-started", headers=headers)
    assert started.status_code == 200, started.text
    assert started.json()["print_started_at"] is not None

    later_retry = await async_client.post(
        f"{PREFIX}/{reprint_id}/print-claim",
        headers=headers,
        json={"attempt_key": "would-duplicate"},
    )
    assert later_retry.status_code == 200, later_retry.text
    assert later_retry.json()["claimed"] is False
    assert later_retry.json()["row"]["print_started_at"] is not None


@pytest.mark.asyncio
async def test_kiz_reprint_concurrent_print_claims_allow_one_automatic_launch(
    async_client: AsyncClient,
) -> None:
    """A duplicate delivery cannot make two browsers auto-open the same label."""
    headers, _tenant_id, seller_id = await _seed(async_client)
    created = await async_client.post(
        PREFIX,
        headers=headers,
        json={"seller_id": str(seller_id), "kiz": _kiz(), "idempotency_key": "claim-race"},
    )
    assert created.status_code == 201, created.text
    reprint_id = created.json()["id"]

    first, second = await asyncio.gather(
        async_client.post(
            f"{PREFIX}/{reprint_id}/print-claim",
            headers=headers,
            json={"attempt_key": "first-browser"},
        ),
        async_client.post(
            f"{PREFIX}/{reprint_id}/print-claim",
            headers=headers,
            json={"attempt_key": "second-browser"},
        ),
    )
    assert first.status_code == second.status_code == 200
    assert sorted([first.json()["claimed"], second.json()["claimed"]]) == [False, True]


@pytest.mark.asyncio
async def test_kiz_reprint_idempotency_allows_new_manual_rescan_but_not_delivery_replay(
    async_client: AsyncClient,
) -> None:
    headers, _tenant_id, seller_id = await _seed(async_client)
    kiz = _kiz()
    body = {"seller_id": str(seller_id), "kiz": kiz, "idempotency_key": "same-request"}
    first = await async_client.post(PREFIX, headers=headers, json=body)
    replay = await async_client.post(PREFIX, headers=headers, json=body)
    assert first.status_code == replay.status_code == 201
    assert first.json()["replayed"] is False
    assert replay.json()["replayed"] is True

    conflicting = await async_client.post(
        PREFIX,
        headers=headers,
        json={**body, "kiz": _kiz("RETURN-2")},
    )
    assert conflicting.status_code == 409
    assert conflicting.json()["detail"] == "idempotency_key_reused"

    separate_scan = await async_client.post(
        PREFIX,
        headers=headers,
        json={**body, "idempotency_key": "new-physical-scan"},
    )
    assert separate_scan.status_code == 201
    assert separate_scan.json()["replayed"] is False

    history = await async_client.get(PREFIX, headers=headers, params={"seller_id": str(seller_id)})
    assert len(history.json()["rows"]) == 2


@pytest.mark.asyncio
async def test_kiz_reprint_concurrent_same_delivery_creates_one_row(
    async_client: AsyncClient,
) -> None:
    headers, _tenant_id, seller_id = await _seed(async_client)
    body = {"seller_id": str(seller_id), "kiz": _kiz(), "idempotency_key": "concurrent-scan"}
    first, second = await asyncio.gather(
        async_client.post(PREFIX, headers=headers, json=body),
        async_client.post(PREFIX, headers=headers, json=body),
    )
    assert {first.status_code, second.status_code} == {201}
    assert sorted([first.json()["replayed"], second.json()["replayed"]]) == [False, True]

    async with SessionLocal() as session:
        assert await session.scalar(select(func.count(KizReprint.id))) == 1


@pytest.mark.asyncio
async def test_kiz_reprint_scopes_history_to_tenant_and_reception_permission(
    async_client: AsyncClient,
) -> None:
    headers, tenant_id, seller_id = await _seed(async_client)
    created = await async_client.post(
        PREFIX,
        headers=headers,
        json={"seller_id": str(seller_id), "kiz": _kiz(), "idempotency_key": "tenant-scan"},
    )
    assert created.status_code == 201

    other_headers, _other_tenant, _other_seller = await _seed(async_client)
    other_tenant_list = await async_client.get(
        PREFIX, headers=other_headers, params={"seller_id": str(seller_id)}
    )
    assert other_tenant_list.status_code == 404

    async with SessionLocal() as session:
        denied_staff = User(
            tenant_id=tenant_id,
            role="fulfillment_staff",
            email=f"denied-{uuid.uuid4().hex}@example.com",
            password_hash="unused",
        )
        allowed_staff = User(
            tenant_id=tenant_id,
            role="fulfillment_staff",
            email=f"allowed-{uuid.uuid4().hex}@example.com",
            password_hash="unused",
        )
        session.add_all([denied_staff, allowed_staff])
        await session.flush()
        session.add(FfStaffPermissions(user_id=denied_staff.id, can_reception=False))
        session.add(FfStaffPermissions(user_id=allowed_staff.id, can_reception=True))
        await session.commit()
        denied_token = create_access_token(
            user_id=denied_staff.id, tenant_id=tenant_id, role=denied_staff.role
        )
        allowed_token = create_access_token(
            user_id=allowed_staff.id, tenant_id=tenant_id, role=allowed_staff.role
        )

    denied = await async_client.get(
        PREFIX,
        headers={"Authorization": f"Bearer {denied_token}"},
        params={"seller_id": str(seller_id)},
    )
    assert denied.status_code == 403
    allowed = await async_client.get(
        PREFIX,
        headers={"Authorization": f"Bearer {allowed_token}"},
        params={"seller_id": str(seller_id)},
    )
    assert allowed.status_code == 200
    assert [row["kiz"] for row in allowed.json()["rows"]] == [_kiz()]
