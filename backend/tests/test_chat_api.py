"""Chat API happy-path tests — WMS-397/WMS-399.

Cover the flows the coordinator asked for: ensure_main is idempotent,
messages dedupe on retry, seller sees only their seller_id's chats,
document attachment cards survive a reload, seller cannot open FF-only
extra chats, and file/image upload round-trips through the storage."""

from __future__ import annotations

import asyncio
import io
import time
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient


async def _register_admin(async_client: AsyncClient) -> tuple[str, dict[str, str], str]:
    suffix = str(int(time.time() * 1_000_000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": f"Chat Co {suffix}",
            "slug": f"chat-{suffix}",
            "admin_email": f"chat-admin-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200, reg.text
    token = str(reg.json()["access_token"])
    headers = {"Authorization": f"Bearer {token}"}
    me = await async_client.get("/auth/me", headers=headers)
    assert me.status_code == 200
    return suffix, headers, str(me.json()["id"])


async def _create_seller(
    async_client: AsyncClient,
    admin_headers: dict[str, str],
    suffix: str,
) -> tuple[dict[str, str], str, str]:
    email = f"chat-seller-{suffix}@example.com"
    created = await async_client.post(
        "/sellers/with-account",
        headers=admin_headers,
        json={"name": "Chat Seller", "email": email, "password": "password123"},
    )
    assert created.status_code == 201, created.text
    seller_id = str(created.json()["seller_id"])

    login = await async_client.post(
        "/auth/login",
        json={"email": email, "password": "password123"},
    )
    assert login.status_code == 200, login.text
    seller_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    me = await async_client.get("/auth/me", headers=seller_headers)
    seller_user_id = str(me.json()["id"])
    return seller_headers, seller_id, seller_user_id


@pytest.mark.asyncio
async def test_main_chat_is_idempotent_per_seller(async_client: AsyncClient) -> None:
    """Two calls to GET .../conversations/main must return the same UUID."""
    suffix, admin_headers, _ = await _register_admin(async_client)
    _, seller_id, _ = await _create_seller(async_client, admin_headers, suffix)

    first = await async_client.get(
        f"/operations/chat/conversations/main?seller_id={seller_id}",
        headers=admin_headers,
    )
    assert first.status_code == 200, first.text
    second = await async_client.get(
        f"/operations/chat/conversations/main?seller_id={seller_id}",
        headers=admin_headers,
    )
    assert second.status_code == 200, second.text
    assert first.json()["id"] == second.json()["id"]
    assert first.json()["kind"] == "main"
    assert first.json()["seller_id"] == seller_id


@pytest.mark.asyncio
async def test_seller_sees_only_own_main_chat(async_client: AsyncClient) -> None:
    suffix, admin_headers, _ = await _register_admin(async_client)
    _, seller_a_id, _ = await _create_seller(async_client, admin_headers, suffix)
    # Add a second seller and ensure its main chat exists.
    other_suffix = suffix + "b"
    email_b = f"chat-seller-{other_suffix}@example.com"
    created_b = await async_client.post(
        "/sellers/with-account",
        headers=admin_headers,
        json={"name": "Chat Seller B", "email": email_b, "password": "password123"},
    )
    assert created_b.status_code == 201, created_b.text
    seller_b_id = str(created_b.json()["seller_id"])
    login_b = await async_client.post(
        "/auth/login",
        json={"email": email_b, "password": "password123"},
    )
    seller_b_headers = {"Authorization": f"Bearer {login_b.json()['access_token']}"}
    login_a = await async_client.post(
        "/auth/login",
        json={
            "email": f"chat-seller-{suffix}@example.com",
            "password": "password123",
        },
    )
    seller_a_headers = {"Authorization": f"Bearer {login_a.json()['access_token']}"}

    # Materialise both chats.
    await async_client.get(
        f"/operations/chat/conversations/main?seller_id={seller_a_id}",
        headers=admin_headers,
    )
    await async_client.get(
        f"/operations/chat/conversations/main?seller_id={seller_b_id}",
        headers=admin_headers,
    )

    listed_a = await async_client.get("/operations/chat/conversations", headers=seller_a_headers)
    assert listed_a.status_code == 200
    for row in listed_a.json()["items"]:
        assert row["seller_id"] == seller_a_id

    listed_b = await async_client.get("/operations/chat/conversations", headers=seller_b_headers)
    assert listed_b.status_code == 200
    for row in listed_b.json()["items"]:
        assert row["seller_id"] == seller_b_id


@pytest.mark.asyncio
async def test_seller_cannot_open_other_sellers_chat(async_client: AsyncClient) -> None:
    suffix, admin_headers, _ = await _register_admin(async_client)
    _, seller_a_id, _ = await _create_seller(async_client, admin_headers, suffix)
    other_suffix = suffix + "c"
    email_b = f"chat-seller-{other_suffix}@example.com"
    await async_client.post(
        "/sellers/with-account",
        headers=admin_headers,
        json={"name": "Chat Seller C", "email": email_b, "password": "password123"},
    )
    login_b = await async_client.post(
        "/auth/login",
        json={"email": email_b, "password": "password123"},
    )
    seller_b_headers = {"Authorization": f"Bearer {login_b.json()['access_token']}"}

    # A materialises their chat.
    main_a = await async_client.get(
        f"/operations/chat/conversations/main?seller_id={seller_a_id}",
        headers=admin_headers,
    )
    conv_id = main_a.json()["id"]

    # B must not read A's messages.
    resp = await async_client.get(
        f"/operations/chat/conversations/{conv_id}/messages",
        headers=seller_b_headers,
    )
    assert resp.status_code == 403
    # And B must not force-open A's chat by seller_id override either.
    forced = await async_client.get(
        f"/operations/chat/conversations/main?seller_id={seller_a_id}",
        headers=seller_b_headers,
    )
    assert forced.status_code == 403


@pytest.mark.asyncio
async def test_post_message_dedupes_on_retry(async_client: AsyncClient) -> None:
    suffix, admin_headers, _ = await _register_admin(async_client)
    _, seller_id, _ = await _create_seller(async_client, admin_headers, suffix)
    main = await async_client.get(
        f"/operations/chat/conversations/main?seller_id={seller_id}",
        headers=admin_headers,
    )
    conv_id = main.json()["id"]

    client_id = "cli-" + uuid.uuid4().hex[:16]
    first = await async_client.post(
        f"/operations/chat/conversations/{conv_id}/messages",
        headers=admin_headers,
        json={"client_message_id": client_id, "text": "hello seller"},
    )
    assert first.status_code == 201, first.text
    second = await async_client.post(
        f"/operations/chat/conversations/{conv_id}/messages",
        headers=admin_headers,
        json={"client_message_id": client_id, "text": "hello seller"},
    )
    assert second.status_code == 201, second.text
    assert first.json()["id"] == second.json()["id"]

    listed = await async_client.get(
        f"/operations/chat/conversations/{conv_id}/messages",
        headers=admin_headers,
    )
    assert listed.status_code == 200
    assert len([m for m in listed.json()["items"] if m["client_message_id"] == client_id]) == 1


@pytest.mark.asyncio
async def test_attached_document_persists_across_reload(
    async_client: AsyncClient,
) -> None:
    suffix, admin_headers, _ = await _register_admin(async_client)
    seller_headers, seller_id, _ = await _create_seller(async_client, admin_headers, suffix)
    main = await async_client.get(
        f"/operations/chat/conversations/main?seller_id={seller_id}",
        headers=admin_headers,
    )
    conv_id = main.json()["id"]

    from app.db.session import SessionLocal
    from app.models.fbs_order import FbsOrder
    from app.models.user import User

    async with SessionLocal() as session:
        user = await session.get(
            User,
            uuid.UUID((await async_client.get("/auth/me", headers=admin_headers)).json()["id"]),
        )
        order = FbsOrder(
            tenant_id=user.tenant_id,
            seller_id=uuid.UUID(seller_id),
            wb_order_id=42,
            status="new",
            created_at_wb=datetime.now(UTC),
            deadline_at=datetime.now(UTC) + timedelta(days=1),
            mapping_status="unmapped",
            reserve_status="not_reserved",
        )
        session.add(order)
        await session.commit()
        doc_id = str(order.id)
    post = await async_client.post(
        f"/operations/chat/conversations/{conv_id}/messages",
        headers=admin_headers,
        json={
            "client_message_id": "with-doc-" + uuid.uuid4().hex[:8],
            "text": "look at this order",
            "attached_document": {
                "kind": "fbs_order",
                "id": doc_id,
                "title": "FBS #A-42",
                "seller_id": seller_id,
                "seller_name": "Chat Seller",
            },
        },
    )
    assert post.status_code == 201, post.text
    # Second participant (the seller) reloads and still sees the card.
    listed = await async_client.get(
        f"/operations/chat/conversations/{conv_id}/messages",
        headers=seller_headers,
    )
    assert listed.status_code == 200, listed.text
    items = listed.json()["items"]
    assert len(items) == 1
    doc = items[0]["attached_document"]
    assert doc is not None
    assert doc["kind"] == "fbs_order"
    assert doc["id"] == doc_id
    assert doc["seller_id"] == seller_id


@pytest.mark.asyncio
async def test_attached_document_wrong_seller_rejected(
    async_client: AsyncClient,
) -> None:
    suffix, admin_headers, _ = await _register_admin(async_client)
    _, seller_id, _ = await _create_seller(async_client, admin_headers, suffix)
    main = await async_client.get(
        f"/operations/chat/conversations/main?seller_id={seller_id}",
        headers=admin_headers,
    )
    conv_id = main.json()["id"]
    resp = await async_client.post(
        f"/operations/chat/conversations/{conv_id}/messages",
        headers=admin_headers,
        json={
            "client_message_id": "mismatch-" + uuid.uuid4().hex[:8],
            "text": "should fail",
            "attached_document": {
                "kind": "fbs_order",
                "id": str(uuid.uuid4()),
                "title": "wrong seller",
                "seller_id": str(uuid.uuid4()),
            },
        },
    )
    assert resp.status_code == 422
    assert resp.json()["detail"] == "document_seller_mismatch"


@pytest.mark.asyncio
async def test_upload_and_download_attachment(async_client: AsyncClient) -> None:
    suffix, admin_headers, _ = await _register_admin(async_client)
    seller_headers, seller_id, _ = await _create_seller(async_client, admin_headers, suffix)
    main = await async_client.get(
        f"/operations/chat/conversations/main?seller_id={seller_id}",
        headers=admin_headers,
    )
    conv_id = main.json()["id"]

    import fitz

    file_bytes = fitz.Pixmap(fitz.csRGB, (0, 0, 2, 2)).tobytes("png")
    upload = await async_client.post(
        f"/operations/chat/conversations/{conv_id}/attachments",
        headers=admin_headers,
        files={"file": ("paste.png", io.BytesIO(file_bytes), "image/png")},
    )
    assert upload.status_code == 201, upload.text
    att = upload.json()
    assert att["is_image"] is True
    assert att["filename"] == "paste.png"
    assert att["size_bytes"] == len(file_bytes)

    # Attach to a message.
    post = await async_client.post(
        f"/operations/chat/conversations/{conv_id}/messages",
        headers=admin_headers,
        json={
            "client_message_id": "pic-" + uuid.uuid4().hex[:8],
            "text": "screenshot",
            "attachment_ids": [att["id"]],
        },
    )
    assert post.status_code == 201, post.text
    msg = post.json()
    assert len(msg["attachments"]) == 1
    assert msg["attachments"][0]["is_image"] is True

    # Seller reloads and downloads the content.
    listed = await async_client.get(
        f"/operations/chat/conversations/{conv_id}/messages",
        headers=seller_headers,
    )
    items = listed.json()["items"]
    assert len(items) == 1
    attachment_id = items[0]["attachments"][0]["id"]
    download = await async_client.get(
        f"/operations/chat/attachments/{attachment_id}/content",
        headers=seller_headers,
    )
    assert download.status_code == 200
    assert download.content == file_bytes


@pytest.mark.asyncio
async def test_edit_message_only_by_author(async_client: AsyncClient) -> None:
    suffix, admin_headers, _ = await _register_admin(async_client)
    seller_headers, seller_id, _ = await _create_seller(async_client, admin_headers, suffix)
    main = await async_client.get(
        f"/operations/chat/conversations/main?seller_id={seller_id}",
        headers=admin_headers,
    )
    conv_id = main.json()["id"]
    post = await async_client.post(
        f"/operations/chat/conversations/{conv_id}/messages",
        headers=admin_headers,
        json={"client_message_id": "edit-" + uuid.uuid4().hex[:8], "text": "first"},
    )
    msg_id = post.json()["id"]

    ok = await async_client.patch(
        f"/operations/chat/messages/{msg_id}",
        headers=admin_headers,
        json={"text": "fixed typo"},
    )
    assert ok.status_code == 200
    assert ok.json()["text"] == "fixed typo"
    assert ok.json()["edited_at"] is not None

    denied = await async_client.patch(
        f"/operations/chat/messages/{msg_id}",
        headers=seller_headers,
        json={"text": "not allowed"},
    )
    assert denied.status_code == 403


@pytest.mark.asyncio
async def test_extra_chat_requires_admin_and_hides_from_stranger(
    async_client: AsyncClient,
) -> None:
    suffix, admin_headers, _ = await _register_admin(async_client)
    seller_headers, seller_id, seller_user_id = await _create_seller(
        async_client, admin_headers, suffix
    )
    # Seller cannot create extra chats.
    denied = await async_client.post(
        "/operations/chat/conversations/extra",
        headers=seller_headers,
        json={"seller_id": seller_id, "title": "seller attempt"},
    )
    assert denied.status_code == 403

    # Admin creates one and adds the seller-user.
    created = await async_client.post(
        "/operations/chat/conversations/extra",
        headers=admin_headers,
        json={
            "seller_id": seller_id,
            "title": "Escalation",
            "participant_user_ids": [seller_user_id],
        },
    )
    assert created.status_code == 201, created.text
    conv_id = created.json()["id"]

    # Seller can list and read; a stranger seller cannot.
    listed = await async_client.get("/operations/chat/conversations", headers=seller_headers)
    assert any(c["id"] == conv_id for c in listed.json()["items"])

    read_ok = await async_client.get(
        f"/operations/chat/conversations/{conv_id}/messages", headers=seller_headers
    )
    assert read_ok.status_code == 200

    # Second seller (unrelated) does not see it and cannot read.
    other_suffix = suffix + "d"
    email_c = f"chat-seller-{other_suffix}@example.com"
    await async_client.post(
        "/sellers/with-account",
        headers=admin_headers,
        json={"name": "Other seller", "email": email_c, "password": "password123"},
    )
    login_c = await async_client.post(
        "/auth/login", json={"email": email_c, "password": "password123"}
    )
    other_headers = {"Authorization": f"Bearer {login_c.json()['access_token']}"}

    forbidden = await async_client.get(
        f"/operations/chat/conversations/{conv_id}/messages", headers=other_headers
    )
    assert forbidden.status_code == 403
    listed_other = await async_client.get("/operations/chat/conversations", headers=other_headers)
    assert not any(c["id"] == conv_id for c in listed_other.json()["items"])


@pytest.mark.asyncio
async def test_concurrent_main_message_and_attachment_ownership(async_client: AsyncClient) -> None:
    suffix, admin, _ = await _register_admin(async_client)
    seller, sid, _ = await _create_seller(async_client, admin, suffix)
    calls = await asyncio.gather(
        *[
            async_client.get(f"/operations/chat/conversations/main?seller_id={sid}", headers=admin)
            for _ in range(6)
        ]
    )
    assert all(r.status_code == 200 for r in calls), [r.text for r in calls]
    assert len({r.json()["id"] for r in calls}) == 1
    cid = calls[0].json()["id"]
    url = f"/operations/chat/conversations/{cid}/messages"
    results = await asyncio.gather(
        *[
            async_client.post(
                url,
                headers=admin,
                json={"client_message_id": "concurrent-retry", "text": "one message"},
            )
            for _ in range(6)
        ]
    )
    assert all(r.status_code == 201 for r in results), [r.text for r in results]
    assert len({r.json()["id"] for r in results}) == 1
    upload = await async_client.post(
        f"/operations/chat/conversations/{cid}/attachments",
        headers=admin,
        files={"file": ("private.txt", b"draft", "text/plain")},
    )
    aid = upload.json()["id"]
    content_url = f"/operations/chat/attachments/{aid}/content"
    assert (await async_client.get(content_url, headers=seller)).status_code == 403
    assert (await async_client.get(content_url, headers=admin)).status_code == 200
    results = await asyncio.gather(
        *[
            async_client.post(
                url,
                headers=admin,
                json={
                    "client_message_id": f"attach-race-{n}",
                    "text": "file",
                    "attachment_ids": [aid],
                },
            )
            for n in range(2)
        ]
    )
    assert sorted(r.status_code for r in results) == [201, 422], [r.text for r in results]
    messages = (await async_client.get(url, headers=seller)).json()["items"]
    assert len(messages) == 2  # failed attachment does not leave an empty message
    assert (await async_client.get(content_url, headers=seller)).content == b"draft"


@pytest.mark.asyncio
async def test_extra_participants_tenant_revocation_and_cross_chat_retry(
    async_client: AsyncClient,
) -> None:
    from sqlalchemy import delete

    from app.db.session import SessionLocal
    from app.models.chat import ChatParticipant
    from app.models.user import User

    suffix, admin, admin_id = await _register_admin(async_client)
    _seller, sid, seller_uid = await _create_seller(async_client, admin, suffix)
    other_seller, other_sid, other_uid = await _create_seller(async_client, admin, suffix + "other")
    async with SessionLocal() as session:
        owner = await session.get(User, uuid.UUID(admin_id))
        worker = User(
            tenant_id=owner.tenant_id,
            email=f"worker-{suffix}@example.com",
            role="fulfillment_staff",
            password_hash=owner.password_hash,
        )
        session.add(worker)
        await session.commit()
        worker_id = str(worker.id)
    login = await async_client.post(
        "/auth/login", json={"email": f"worker-{suffix}@example.com", "password": "password123"}
    )
    staff = {"Authorization": f"Bearer {login.json()['access_token']}"}
    rejected = await async_client.post(
        "/operations/chat/conversations/extra",
        headers=admin,
        json={"seller_id": sid, "title": "bad", "participant_user_ids": [other_uid]},
    )
    assert rejected.status_code == 422
    extra = await async_client.post(
        "/operations/chat/conversations/extra",
        headers=admin,
        json={"seller_id": sid, "title": "Private", "participant_user_ids": [seller_uid]},
    )
    assert extra.status_code == 201, extra.text
    cid = extra.json()["id"]
    url = f"/operations/chat/conversations/{cid}"
    assert (await async_client.get(url, headers=staff)).status_code == 403
    assert cid not in [
        c["id"]
        for c in (await async_client.get("/operations/chat/conversations", headers=staff)).json()[
            "items"
        ]
    ]
    additions = await asyncio.gather(
        *[
            async_client.post(url + "/participants", headers=admin, json={"user_id": worker_id})
            for _ in range(2)
        ]
    )
    assert all(r.status_code == 201 for r in additions), [r.text for r in additions]
    assert additions[0].json()["id"] == additions[1].json()["id"]
    assert (await async_client.get(url, headers=staff)).status_code == 200
    uploaded = await async_client.post(
        url + "/attachments", headers=staff, files={"file": ("staff.txt", b"private", "text/plain")}
    )
    aid = uploaded.json()["id"]
    posted = await async_client.post(
        url + "/messages",
        headers=staff,
        json={"client_message_id": "staff-one", "text": "private", "attachment_ids": [aid]},
    )
    assert posted.status_code == 201, posted.text
    async with SessionLocal() as session:
        await session.execute(
            delete(ChatParticipant).where(
                ChatParticipant.conversation_id == uuid.UUID(cid),
                ChatParticipant.user_id == uuid.UUID(worker_id),
            )
        )
        await session.commit()
    assert (
        await async_client.get(f"/operations/chat/attachments/{aid}/content", headers=staff)
    ).status_code == 403
    other_main = await async_client.get(
        f"/operations/chat/conversations/main?seller_id={other_sid}", headers=admin
    )
    conflict = await async_client.post(
        f"/operations/chat/conversations/{other_main.json()['id']}/messages",
        headers=staff,
        json={"client_message_id": "staff-one", "text": "new chat"},
    )
    assert conflict.status_code == 409
    _, outsider, _ = await _register_admin(async_client)
    for path in [
        url,
        url + "/messages",
        url + "/participants",
        f"/operations/chat/attachments/{aid}/content",
    ]:
        assert (await async_client.get(path, headers=outsider)).status_code == 404
    assert (await async_client.get(url, headers=other_seller)).status_code == 403


@pytest.mark.asyncio
async def test_document_identity_rights_and_latest_pagination(async_client: AsyncClient) -> None:
    from app.db.session import SessionLocal
    from app.models.fbs_order import FbsOrder
    from app.models.seller_staff_permissions import SellerStaffPermissions
    from app.models.user import User

    suffix, admin, uid = await _register_admin(async_client)
    seller, sid, seller_uid = await _create_seller(async_client, admin, suffix)
    _, sid2, _ = await _create_seller(async_client, admin, suffix + "other")
    async with SessionLocal() as session:
        user = await session.get(User, uuid.UUID(uid))
        order = FbsOrder(
            tenant_id=user.tenant_id,
            seller_id=uuid.UUID(sid),
            wb_order_id=7001,
            status="new",
            created_at_wb=datetime.now(UTC),
            deadline_at=datetime.now(UTC) + timedelta(days=1),
            mapping_status="unmapped",
            reserve_status="not_reserved",
        )
        session.add(order)
        await session.commit()
        oid = str(order.id)
    base = f"/operations/chat/documents/fbs_order/{oid}"
    response = await async_client.get(base + f"?seller_id={sid}", headers=seller)
    assert response.status_code == 200, response.text
    assert response.json()["document"]["title"] == "WB №7001"
    assert (await async_client.get(base + f"?seller_id={sid2}", headers=admin)).status_code == 404
    main = await async_client.get(
        f"/operations/chat/conversations/main?seller_id={sid}", headers=admin
    )
    url = f"/operations/chat/conversations/{main.json()['id']}/messages"
    forged = await async_client.post(
        url,
        headers=admin,
        json={
            "client_message_id": "forged",
            "text": "x",
            "attached_document": {
                "kind": "fbs_order",
                "id": str(uuid.uuid4()),
                "title": "fake",
                "seller_id": sid,
            },
        },
    )
    assert forged.status_code == 404
    real = await async_client.post(
        url,
        headers=admin,
        json={
            "client_message_id": "real",
            "text": "order",
            "attached_document": {
                "kind": "fbs_order",
                "id": oid,
                "title": "spoofed",
                "seller_id": sid,
            },
        },
    )
    assert real.status_code == 201, real.text
    assert real.json()["attached_document"]["title"] == "WB №7001"
    async with SessionLocal() as session:
        session.add(SellerStaffPermissions(user_id=uuid.UUID(seller_uid), can_documents=False))
        await session.commit()
    assert (await async_client.get(base + f"?seller_id={sid}", headers=seller)).status_code == 403
    hidden = (await async_client.get(url, headers=seller)).json()["items"]
    assert hidden[0]["attached_document"] is None
    ids = [real.json()["id"]]
    for n in range(4):
        r = await async_client.post(
            url, headers=admin, json={"client_message_id": f"page-{n}", "text": str(n)}
        )
        ids.append(r.json()["id"])
    newest = (await async_client.get(url + "?limit=2", headers=admin)).json()["items"]
    assert [m["id"] for m in newest] == ids[-2:]
    older = (
        await async_client.get(url + f"?limit=2&before={newest[0]['id']}", headers=admin)
    ).json()["items"]
    assert [m["id"] for m in older] == ids[-4:-2]


@pytest.mark.asyncio
async def test_all_document_types_and_mixed_seller_projection(async_client: AsyncClient) -> None:
    from app.db.session import SessionLocal
    from app.models.fbs_supply import FbsSupply
    from app.models.inbound_intake import InboundIntakeLine, InboundIntakeRequest
    from app.models.marketplace_unload import MarketplaceUnloadLine, MarketplaceUnloadRequest
    from app.models.outbound_shipment import OutboundShipmentLine, OutboundShipmentRequest
    from app.models.product import Product
    from app.models.user import User
    from app.models.warehouse import Warehouse

    suffix, admin, uid = await _register_admin(async_client)
    seller, sid, _ = await _create_seller(async_client, admin, suffix)
    stranger, other_sid, _ = await _create_seller(async_client, admin, suffix + "other")
    async with SessionLocal() as session:
        user = await session.get(User, uuid.UUID(uid))
        warehouse = Warehouse(tenant_id=user.tenant_id, name="Chat only", code="CHAT-QA")
        p1 = Product(
            tenant_id=user.tenant_id, seller_id=uuid.UUID(sid), name="OWN ROW", sku_code="OWN"
        )
        p2 = Product(
            tenant_id=user.tenant_id,
            seller_id=uuid.UUID(other_sid),
            name="OTHER SECRET ROW",
            sku_code="OTHER",
        )
        session.add_all([warehouse, p1, p2])
        await session.flush()
        inbound = InboundIntakeRequest(
            tenant_id=user.tenant_id, warehouse_id=warehouse.id, seller_id=None, status="draft"
        )
        outbound = OutboundShipmentRequest(
            tenant_id=user.tenant_id, warehouse_id=warehouse.id, seller_id=None, status="draft"
        )
        unload = MarketplaceUnloadRequest(
            tenant_id=user.tenant_id,
            warehouse_id=warehouse.id,
            seller_id=uuid.UUID(sid),
            status="draft",
        )
        supply = FbsSupply(
            tenant_id=user.tenant_id,
            seller_id=uuid.UUID(sid),
            warehouse_id=warehouse.id,
            name="CHAT-FBS",
            delivery_type="warehouse",
        )
        session.add_all([inbound, outbound, unload, supply])
        await session.flush()
        session.add_all(
            [
                InboundIntakeLine(request_id=inbound.id, product_id=p1.id, expected_qty=2),
                InboundIntakeLine(request_id=inbound.id, product_id=p2.id, expected_qty=9),
                OutboundShipmentLine(request_id=outbound.id, product_id=p1.id, quantity=2),
                OutboundShipmentLine(request_id=outbound.id, product_id=p2.id, quantity=9),
                MarketplaceUnloadLine(request_id=unload.id, product_id=p1.id, quantity=2),
            ]
        )
        await session.commit()
        documents = {
            "inbound_intake": str(inbound.id),
            "outbound_shipment": str(outbound.id),
            "marketplace_unload": str(unload.id),
            "fbs_supply": str(supply.id),
        }
    main = await async_client.get(
        f"/operations/chat/conversations/main?seller_id={sid}", headers=admin
    )
    url = f"/operations/chat/conversations/{main.json()['id']}/messages"
    for kind, document_id in documents.items():
        doc_url = f"/operations/chat/documents/{kind}/{document_id}?seller_id={sid}"
        response = await async_client.get(doc_url, headers=seller)
        assert response.status_code == 200, response.text
        assert "OTHER SECRET" not in response.text
        assert (await async_client.get(doc_url, headers=stranger)).status_code == 403
        post = await async_client.post(
            url,
            headers=admin,
            json={
                "client_message_id": kind,
                "text": "document",
                "attached_document": {
                    "kind": kind,
                    "id": document_id,
                    "seller_id": sid,
                    "title": "fake title",
                },
            },
        )
        assert post.status_code == 201, post.text
        options = await async_client.get(
            f"/operations/chat/document-options/{kind}/{document_id}", headers=seller
        )
        assert [d["seller_id"] for d in options.json()] == [sid]
    listed = (await async_client.get(url, headers=seller)).json()["items"]
    assert {m["attached_document"]["kind"] for m in listed} == set(documents)
    assert "OTHER SECRET" not in str(listed)


@pytest.mark.asyncio
async def test_attachments_validation_and_ownership(async_client: AsyncClient) -> None:
    suffix, admin, _ = await _register_admin(async_client)
    seller, sid, _ = await _create_seller(async_client, admin, suffix)
    main = await async_client.get(
        f"/operations/chat/conversations/main?seller_id={sid}", headers=admin
    )
    url = f"/operations/chat/conversations/{main.json()['id']}"
    invalid_image = await async_client.post(
        url + "/attachments",
        headers=admin,
        files={"file": ("lie.png", b"<script>evil</script>", "image/png")},
    )
    assert invalid_image.status_code == 422
    svg = await async_client.post(
        url + "/attachments",
        headers=admin,
        files={"file": ("drawing.svg", b"<svg></svg>", "image/svg+xml")},
        data={"is_image": "true"},
    )
    assert svg.status_code == 201 and svg.json()["is_image"] is False
    aid = svg.json()["id"]
    duplicate_ids = await async_client.post(
        url + "/messages",
        headers=admin,
        json={"client_message_id": "duplicate-ids", "text": "file", "attachment_ids": [aid, aid]},
    )
    assert duplicate_ids.status_code == 422
    steal = await async_client.post(
        url + "/messages",
        headers=seller,
        json={"client_message_id": "steal", "text": "file", "attachment_ids": [aid]},
    )
    assert steal.status_code == 422
    posted = await async_client.post(
        url + "/messages",
        headers=admin,
        json={"client_message_id": "ok-file", "text": "file", "attachment_ids": [aid]},
    )
    assert posted.status_code == 201
    download = await async_client.get(f"/operations/chat/attachments/{aid}/content", headers=seller)
    assert download.status_code == 200
    assert download.headers["content-disposition"].startswith("attachment;")
    assert download.headers["x-content-type-options"] == "nosniff"
    assert (
        await async_client.get(f"/operations/chat/attachments/{aid}/content")
    ).status_code == 401
